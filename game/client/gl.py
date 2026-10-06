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
        self.prog["u_fog_color"].value = (0.09, 0.12, 0.2)
        self.prog["u_fog"].value = 1.0
        self.camera = Camera(width, height)
        self._white = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        self.overlay = Overlay(ctx, width, height)
        self.unit_quad = None

    def begin_3d(self, camera=None, clear=(0.09, 0.12, 0.2)):
        cam = camera or self.camera
        cam.update()
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.clear(*clear, 1.0)
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.disable(moderngl.CULL_FACE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.depth_mask = True
        self.prog["u_vp"].write(gl_bytes(cam.vp))
        self.prog["u_cam"].value = tuple(float(v) for v in cam.eye())
        self.prog["u_fog_color"].value = clear

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

    def make_texture(self, surface_or_bytes, size=None):
        if isinstance(surface_or_bytes, pygame.Surface):
            size = surface_or_bytes.get_size()
            data = pygame.image.tobytes(surface_or_bytes, "RGBA", True)
        else:
            data = surface_or_bytes
        tex = self.ctx.texture(size, 4, data)
        tex.build_mipmaps()
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.repeat_x = True
        tex.repeat_y = True
        return tex

    def mesh(self, builder):
        return Mesh.from_builder(self, builder)


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

    def end(self):
        self.texture.write(pygame.image.tobytes(self.surface, "RGBA", True))
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.texture.use(0)
        self.prog["u_tex"].value = 0
        self.vao.render(moderngl.TRIANGLES)


def unit_builder_disc():
    b = MeshBuilder()
    b.disc((0, 0, 0), 1.0, (1, 1, 1), 40)
    return b


def unit_builder_ring(thickness=0.12):
    b = MeshBuilder()
    b.ring((0, 0, 0), 1.0 - thickness, 1.0, (1, 1, 1), 48)
    return b
