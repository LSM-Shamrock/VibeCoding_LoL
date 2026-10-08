"""moderngl 기반 렌더러: 셰이더, 메시, 카메라, pygame 2D 오버레이."""
import math

import moderngl
import numpy as np
import pygame

from .geometry import MeshBuilder

MESH_VS = """
#version 330
uniform mat4 u_vp;
uniform mat4 u_model;
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
in vec2 in_uv;
out vec3 v_nrm;
out vec3 v_col;
out vec2 v_uv;
out vec3 v_wpos;
void main() {
    vec4 w = u_model * vec4(in_pos, 1.0);
    v_wpos = w.xyz;
    v_nrm = mat3(u_model) * in_nrm;
    v_col = in_col;
    v_uv = in_uv;
    gl_Position = u_vp * w;
}
"""

MESH_FS = """
#version 330
uniform vec3 u_light;
uniform vec4 u_tint;
uniform vec3 u_emissive;
uniform float u_unlit;
uniform bool u_use_tex;
uniform sampler2D u_tex;
uniform vec3 u_cam;
uniform vec3 u_fog_color;
uniform float u_fog;
uniform bool u_use_vis;      // 전장의 안개: 시야 밖은 어둡게
uniform sampler2D u_vis;     // 시야 격자 (r: 1 보임, 0 안 보임)
uniform vec4 u_vis_rect;     // 격자가 덮는 월드 범위 (x0, z0, 폭, 높이)
in vec3 v_nrm;
in vec3 v_col;
in vec2 v_uv;
in vec3 v_wpos;
out vec4 f_color;
void main() {
    vec3 base = v_col;
    float a = 1.0;
    if (u_use_tex) {
        vec4 tx = texture(u_tex, v_uv);
        base *= tx.rgb;
        a = tx.a;
        if (a < 0.35) discard;
    }
    base *= u_tint.rgb;
    vec3 n = normalize(v_nrm);
    float diff = max(dot(n, -u_light), 0.0);
    float hemi = 0.5 + 0.5 * n.y;
    vec3 view = normalize(u_cam - v_wpos);
    float rim = pow(1.0 - max(dot(n, view), 0.0), 3.0) * 0.25;
    vec3 lit = base * (0.32 + 0.28 * hemi + 0.62 * diff) + vec3(0.55, 0.7, 0.9) * rim;
    vec3 c = mix(lit, base, u_unlit) + u_emissive;
    float dist = length(u_cam - v_wpos);
    float fog = clamp((dist - 45.0) / 70.0, 0.0, 1.0) * u_fog;
    c = mix(c, u_fog_color, fog);
    if (u_use_vis) {
        vec2 vuv = (v_wpos.xz - u_vis_rect.xy) / u_vis_rect.zw;
        if (vuv.x >= 0.0 && vuv.x <= 1.0 && vuv.y >= 0.0 && vuv.y <= 1.0) {
            float v = texture(u_vis, vuv).r;
            c = mix(c * vec3(0.32, 0.34, 0.42), c, v);
        }
    }
    f_color = vec4(c, a * u_tint.a);
}
"""

OVERLAY_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

OVERLAY_FS = """
#version 330
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 f_color;
void main() {
    f_color = texture(u_tex, v_uv);
}
"""


# ---------------------------------------------------------------- 행렬
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2)
    m = np.zeros((4, 4), dtype="f4")
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def look_at(eye, target, up=(0, 1, 0)):
    eye = np.array(eye, dtype="f4")
    target = np.array(target, dtype="f4")
    up = np.array(up, dtype="f4")
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.identity(4, dtype="f4")
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def model_matrix(x=0.0, y=0.0, z=0.0, rot_y=0.0, scale=1.0, sx=None, sy=None, sz=None, rot_x=0.0):
    c, s = math.cos(rot_y), math.sin(rot_y)
    sx = scale if sx is None else sx
    sy = scale if sy is None else sy
    sz = scale if sz is None else sz
    m = np.array([
        [c * sx, 0, s * sz, x],
        [0, sy, 0, y],
        [-s * sx, 0, c * sz, z],
        [0, 0, 0, 1],
    ], dtype="f4")
    if rot_x:
        cx, sxr = math.cos(rot_x), math.sin(rot_x)
        rx = np.array([[1, 0, 0, 0], [0, cx, -sxr, 0], [0, sxr, cx, 0], [0, 0, 0, 1]], dtype="f4")
        m = m @ rx
    return m


def facing_to_rot(facing):
    """서버 facing(각도, (cos,sin)=(dx,dz)) → 모델의 +Z 가 그 방향을 보도록 하는 Y 회전."""
    return math.atan2(math.cos(facing), math.sin(facing))


def gl_bytes(m):
    return m.T.astype("f4").tobytes()


# ---------------------------------------------------------------- 메시
class Mesh:
    """여러 부분 메시(각자 텍스처 가능)의 묶음."""

    def __init__(self, renderer, parts, bounds=None):
        self.parts = []   # (vao, vbo, texture or None)
        ctx = renderer.ctx
        for arr, tex in parts:
            if len(arr) == 0:
                continue
            vbo = ctx.buffer(np.ascontiguousarray(arr, dtype="f4").tobytes())
            vao = ctx.vertex_array(renderer.prog, [(vbo, "3f 3f 3f 2f", "in_pos", "in_nrm", "in_col", "in_uv")])
            self.parts.append((vao, vbo, tex))
        self.bounds = bounds

    @classmethod
    def from_builder(cls, renderer, builder):
        arr = builder.array()
        return cls(renderer, [(arr, None)], bounds_of(arr))

    def release(self):
        for vao, vbo, tex in self.parts:
            vao.release()
            vbo.release()


def bounds_of(arr):
    if len(arr) == 0:
        return (np.zeros(3), np.zeros(3))
    return arr[:, :3].min(axis=0), arr[:, :3].max(axis=0)


# ---------------------------------------------------------------- 카메라
class Camera:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tx = 0.0
        self.ty = 0.0
        self.tz = 0.0
        self.distance = 26.0
        self.pitch = math.radians(56)
        self.yaw = 0.0
        self.fov = 38.0
        self.update()

    def eye(self):
        horiz = math.cos(self.pitch) * self.distance
        return (self.tx + math.sin(self.yaw) * horiz,
                self.ty + math.sin(self.pitch) * self.distance,
                self.tz + math.cos(self.yaw) * horiz)

    def update(self):
        self.view = look_at(self.eye(), (self.tx, self.ty, self.tz))
        self.proj = perspective(self.fov, self.width / self.height, 0.5, 300.0)
        self.vp = self.proj @ self.view
        self.inv_vp = np.linalg.inv(self.vp)

    def world_to_screen(self, x, y, z):
        p = self.vp @ np.array([x, y, z, 1.0], dtype="f4")
        if p[3] <= 0.01:
            return None
        nx, ny = p[0] / p[3], p[1] / p[3]
        return (float((nx * 0.5 + 0.5) * self.width), float((1 - (ny * 0.5 + 0.5)) * self.height))

    def screen_to_ground(self, sx, sy, plane_y=0.0):
        nx = sx / self.width * 2 - 1
        ny = 1 - sy / self.height * 2
        p0 = self.inv_vp @ np.array([nx, ny, -1, 1], dtype="f4")
        p1 = self.inv_vp @ np.array([nx, ny, 1, 1], dtype="f4")
        p0 = p0[:3] / p0[3]
        p1 = p1[:3] / p1[3]
        d = p1 - p0
        if abs(d[1]) < 1e-6:
            return None
        t = (plane_y - p0[1]) / d[1]
        hit = p0 + d * t
        return float(hit[0]), float(hit[2])


# ---------------------------------------------------------------- 렌더러
class Renderer:
    def __init__(self, ctx, width, height):
        self.ctx = ctx
        self.width = width
        self.height = height
        self.prog = ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.prog["u_light"].value = tuple(np.array([-0.35, -1.0, -0.45]) / np.linalg.norm([-0.35, -1.0, -0.45]))
        self.prog["u_fog_color"].value = (0.02, 0.02, 0.05)
        self.prog["u_fog"].value = 0.0          # 우주 배경: 안개 없음
        self.camera = Camera(width, height)
        self._white = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        self.overlay = Overlay(ctx, width, height)
        self.sky = SpaceSky(ctx)
        self.time = 0.0
        self.unit_quad = None
        self.vision = None              # (텍스처, (x0, z0, 폭, 높이)) — 설정되면 시야 밖을 어둡게
        # 실제 창(프레임버퍼) 크기와, 논리 화면(width x height)이 그려질 영역
        self.window_size = (width, height)
        self.viewport = (0, 0, width, height)
        self.scale = 1.0

    def set_window_size(self, w, h):
        """창 크기에 맞춰 논리 화면을 비율 유지(레터박스)로 배치한다."""
        self.window_size = (w, h)
        s = min(w / self.width, h / self.height)
        vw, vh = int(round(self.width * s)), int(round(self.height * s))
        self.viewport = ((w - vw) // 2, (h - vh) // 2, vw, vh)
        self.scale = s

    def to_logical(self, pos):
        """창 좌표 -> 논리 화면 좌표 (UI·카메라 계산용)."""
        vx, vy, vw, vh = self.viewport
        _, h = self.window_size
        top = h - vy - vh
        return ((pos[0] - vx) / self.scale, (pos[1] - top) / self.scale)

    def end_overlay(self):
        self.ctx.viewport = self.viewport
        self.overlay.end(scaled=abs(self.scale - 1.0) > 1e-3)

    def begin_3d(self, camera=None, clear=(0.01, 0.012, 0.03), sky=True):
        cam = camera or self.camera
        cam.update()
        self.ctx.viewport = (0, 0, *self.window_size)
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)
        self.ctx.viewport = self.viewport
        self.ctx.clear(*clear, 1.0, viewport=self.viewport)
        if sky:
            self.sky.draw(cam, self.time)
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.disable(moderngl.CULL_FACE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.depth_mask = True
        self.prog["u_vp"].write(gl_bytes(cam.vp))
        if self.vision:
            tex, rect = self.vision
            tex.use(1)
            self.prog["u_vis"].value = 1
            self.prog["u_vis_rect"].value = rect
            self.prog["u_use_vis"].value = True
        else:
            self.prog["u_use_vis"].value = False
        self.prog["u_cam"].value = tuple(float(v) for v in cam.eye())

    def draw(self, mesh, model, tint=(1, 1, 1, 1), emissive=(0, 0, 0), unlit=0.0):
        if mesh is None:
            return
        self.prog["u_model"].write(gl_bytes(model))
        self.prog["u_tint"].value = tuple(tint) if len(tint) == 4 else (*tint, 1.0)
        self.prog["u_emissive"].value = tuple(emissive)
        self.prog["u_unlit"].value = float(unlit)
        for vao, vbo, tex in mesh.parts:
            if tex is not None:
                tex.use(0)
                self.prog["u_use_tex"].value = True
                self.prog["u_tex"].value = 0
            else:
                self.prog["u_use_tex"].value = False
            vao.render(moderngl.TRIANGLES)

    def draw_transparent(self, mesh, model, tint, emissive=(0, 0, 0), unlit=1.0, additive=False):
        """지면 장식/이펙트용: 깊이 쓰기 없이 블렌딩."""
        self.ctx.depth_mask = False
        if additive:
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        self.draw(mesh, model, tint, emissive, unlit)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.depth_mask = True

    def make_texture(self, surface_or_bytes, size=None, pixelated=False):
        if isinstance(surface_or_bytes, pygame.Surface):
            size = surface_or_bytes.get_size()
            data = pygame.image.tobytes(surface_or_bytes, "RGBA", True)
        else:
            data = surface_or_bytes
        tex = self.ctx.texture(size, 4, data)
        if pixelated:
            # 픽셀아트 텍스처: 보간 없이 또렷하게
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        else:
            tex.build_mipmaps()
            tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.repeat_x = True
        tex.repeat_y = True
        return tex

    def mesh(self, builder):
        return Mesh.from_builder(self, builder)


SKY_VS = """
#version 330
in vec2 in_pos;
out vec2 v_ndc;
void main() {
    v_ndc = in_pos;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

SKY_FS = """
#version 330
uniform mat4 u_inv_vp;
uniform float u_time;
in vec2 v_ndc;
out vec4 f_color;

float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
                   mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
                   mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float fbm(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p = p * 2.03 + vec3(1.7, 9.2, 3.1);
        a *= 0.5;
    }
    return v;
}

// 방향 d 의 별 한 층. scale 이 클수록 촘촘하고 작은 별
vec3 stars(vec3 d, float scale, float density, float size) {
    vec3 p = d * scale;
    vec3 cell = floor(p);
    vec3 f = fract(p);
    float h = hash(cell);
    if (h > density) return vec3(0.0);
    vec3 sp = vec3(hash(cell + 11.1), hash(cell + 23.7), hash(cell + 37.3)) * 0.6 + 0.2;
    float dist = length(f - sp);
    float s = size * (0.6 + 0.8 * hash(cell + 5.3));
    float b = smoothstep(s, 0.0, dist);
    vec3 col = mix(vec3(0.65, 0.78, 1.0), vec3(1.0, 0.86, 0.7), hash(cell + 3.1));
    float tw = 0.75 + 0.25 * sin(u_time * (1.5 + 3.0 * h) + h * 60.0);
    return col * b * tw;
}

// 구 행성. 맞으면 (색, 알파) 반환
vec4 planet(vec3 d, vec3 pd, float ang_r, vec3 c1, vec3 c2, float bands, vec3 light, out float t_hit) {
    t_hit = 1e9;
    float R = sin(ang_r);
    vec3 C = pd;
    float b = dot(d, C);
    float disc = R * R - (dot(C, C) - b * b);
    // 대기 빛 번짐
    float edge = acos(clamp(dot(d, pd), -1.0, 1.0)) - ang_r;
    vec3 glow = c2 * 0.6 * exp(-max(edge, 0.0) * 40.0);
    if (disc < 0.0) return vec4(glow, 0.0);
    float t = b - sqrt(disc);
    t_hit = t;
    vec3 N = normalize(d * t - C);
    float n = fbm(N * 3.0);
    float stripe = 0.5 + 0.5 * sin(N.y * bands + n * 6.0);
    vec3 base = mix(c1, c2, stripe * 0.8 + n * 0.3);
    float lit = clamp(dot(N, light), 0.0, 1.0);
    float rim = pow(1.0 - clamp(dot(N, -d), 0.0, 1.0), 2.5);
    vec3 col = base * (0.06 + 1.05 * lit) + c2 * rim * 0.6 * (0.3 + lit);
    return vec4(col, 1.0);
}

void main() {
    vec4 pn = u_inv_vp * vec4(v_ndc, -1.0, 1.0);
    vec4 pf = u_inv_vp * vec4(v_ndc, 1.0, 1.0);
    vec3 d = normalize(pf.xyz / pf.w - pn.xyz / pn.w);

    // 바탕 + 성운
    vec3 col = vec3(0.008, 0.01, 0.025);
    float n1 = fbm(d * 2.2 + vec3(4.0, 1.0, 7.0));
    float n2 = fbm(d * 3.7 + vec3(9.0, 3.0, 1.0));
    float n3 = fbm(d * 6.0 - vec3(2.0, 5.0, 3.0));
    float neb = pow(clamp(n1 * 1.25 - 0.25, 0.0, 1.0), 2.6);
    vec3 nebc = mix(vec3(0.45, 0.12, 0.6), vec3(0.08, 0.35, 0.75), n2);
    nebc = mix(nebc, vec3(0.85, 0.3, 0.45), smoothstep(0.55, 0.75, n3) * 0.6);
    col += nebc * neb * 1.1;
    col += vec3(0.1, 0.2, 0.45) * pow(n2, 4.0) * 0.5;

    // 별 (세 겹)
    col += stars(d, 90.0, 0.06, 0.32) * 1.6;
    col += stars(d, 170.0, 0.10, 0.30);
    col += stars(d, 320.0, 0.18, 0.35) * 0.55 * (0.4 + neb * 2.0);

    // 행성 (고리 행성 + 작은 위성)
    vec3 light = normalize(vec3(-0.7, 0.45, 0.4));
    vec3 pd = normalize(vec3(0.42, -0.62, -0.66));
    float t1;
    vec4 p1 = planet(d, pd, 0.13, vec3(0.75, 0.42, 0.25), vec3(0.95, 0.75, 0.5), 22.0, light, t1);
    // 고리
    vec3 rn = normalize(vec3(0.5, 0.75, 0.9));
    float denom = dot(d, rn);
    vec4 ring = vec4(0.0);
    float t2 = 1e9;
    if (abs(denom) > 1e-4) {
        t2 = dot(pd, rn) / denom;
        if (t2 > 0.0) {
            float r = length(d * t2 - pd) / sin(0.13);
            if (r > 1.3 && r < 2.0) {
                float band = 0.6 + 0.4 * sin(r * 30.0) * sin(r * 9.0 + 1.3);
                float a = smoothstep(1.3, 1.38, r) * smoothstep(2.0, 1.9, r) * band * 0.8;
                ring = vec4(vec3(0.9, 0.8, 0.65) * (0.35 + 0.65 * band), a);
            }
        }
    }
    if (p1.a > 0.0) col = p1.rgb; else col += p1.rgb;
    if (ring.a > 0.0 && (t2 < t1 || p1.a == 0.0)) col = mix(col, ring.rgb, ring.a);

    float t3;
    vec4 p2 = planet(d, normalize(vec3(-0.55, -0.42, -0.72)), 0.055, vec3(0.35, 0.38, 0.45),
                     vec3(0.55, 0.7, 0.9), 6.0, light, t3);
    if (p2.a > 0.0) col = p2.rgb; else col += p2.rgb;

    f_color = vec4(col, 1.0);
}
"""


class SpaceSky:
    """화면 전체에 별·성운·행성을 셰이더로 그린다 (텍스처 불필요)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.prog = ctx.program(vertex_shader=SKY_VS, fragment_shader=SKY_FS)
        tri = np.array([-1, -1, 3, -1, -1, 3], dtype="f4")
        self.vbo = ctx.buffer(tri.tobytes())
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, "2f", "in_pos")])

    def draw(self, cam, t):
        self.ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.prog["u_inv_vp"].write(gl_bytes(cam.inv_vp.astype("f4")))
        self.prog["u_time"].value = float(t)
        self.vao.render(moderngl.TRIANGLES)


class Overlay:
    """pygame Surface 에 2D UI 를 그리고 텍스처로 올려 화면 위에 덮는다."""

    def __init__(self, ctx, width, height):
        self.ctx = ctx
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.texture = ctx.texture((width, height), 4)
        self.texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.prog = ctx.program(vertex_shader=OVERLAY_VS, fragment_shader=OVERLAY_FS)
        quad = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype="f4")
        self.vbo = ctx.buffer(quad.tobytes())
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, "2f", "in_pos")])

    def begin(self):
        self.surface.fill((0, 0, 0, 0))
        return self.surface

    def end(self, scaled=False):
        # 확대 표시(전체 화면) 시 글자 가장자리가 검게 번지지 않도록 미리 곱한 알파로 올린다
        self.texture.write(pygame.image.tobytes(self.surface.premul_alpha(), "RGBA", True))
        f = moderngl.LINEAR if scaled else moderngl.NEAREST
        self.texture.filter = (f, f)
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        self.texture.use(0)
        self.prog["u_tex"].value = 0
        self.vao.render(moderngl.TRIANGLES)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA


def unit_builder_disc():
    b = MeshBuilder()
    b.disc((0, 0, 0), 1.0, (1, 1, 1), 40)
    return b


def unit_builder_ring(thickness=0.12):
    b = MeshBuilder()
    b.ring((0, 0, 0), 1.0 - thickness, 1.0, (1, 1, 1), 48)
    return b
