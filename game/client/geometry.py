"""삼각형 메시를 코드로 만드는 도구 (OpenGL 의존성 없음).

정점 형식: 위치(3) + 법선(3) + 색(3) + UV(2) = 11 float
"""
import math

import numpy as np

STRIDE = 11


def _rot_y(v, ang):
    c, s = math.cos(ang), math.sin(ang)
    x, y, z = v
    return (x * c + z * s, y, -x * s + z * c)


class MeshBuilder:
    def __init__(self):
        self.verts = []   # (x,y,z, nx,ny,nz, r,g,b, u,v)

    # ------------------------------------------------------------ 기본
    def tri(self, a, b, c, color, na=None, nb=None, nc=None, uva=(0, 0), uvb=(0, 0), uvc=(0, 0)):
        if na is None:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            na = nb = nc = (nx / ln, ny / ln, nz / ln)
        r, g, bl = color
        self.verts.append((*a, *na, r, g, bl, *uva))
        self.verts.append((*b, *nb, r, g, bl, *uvb))
        self.verts.append((*c, *nc, r, g, bl, *uvc))

    def quad(self, a, b, c, d, color):
        """반시계 방향 a-b-c-d."""
        self.tri(a, b, c, color)
        self.tri(a, c, d, color)

    def extend(self, other, offset=(0, 0, 0), rot_y=0.0, scale=1.0):
        ox, oy, oz = offset
        for v in other.verts:
            p = _rot_y((v[0] * scale, v[1] * scale, v[2] * scale), rot_y)
            n = _rot_y(v[3:6], rot_y)
            self.verts.append((p[0] + ox, p[1] + oy, p[2] + oz, *n, *v[6:]))

    # ------------------------------------------------------------ 도형
    def box(self, center, size, color, rot_y=0.0, taper=1.0):
        """center: 박스 중심, size: (w,h,d). taper<1 이면 윗면이 좁아진다."""
        cx, cy, cz = center
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        tx, tz = hx * taper, hz * taper
        p = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz),
             (-tx, hy, -tz), (tx, hy, -tz), (tx, hy, tz), (-tx, hy, tz)]
        p = [_rot_y(v, rot_y) for v in p]
        p = [(v[0] + cx, v[1] + cy, v[2] + cz) for v in p]
        self.quad(p[3], p[2], p[6], p[7], color)  # +z
        self.quad(p[1], p[0], p[4], p[5], color)  # -z
        self.quad(p[2], p[1], p[5], p[6], color)  # +x
        self.quad(p[0], p[3], p[7], p[4], color)  # -x
        self.quad(p[7], p[6], p[5], p[4], color)  # top
        self.quad(p[0], p[1], p[2], p[3], color)  # bottom

    def cylinder(self, base, radius, height, color, seg=12, radius_top=None, cap=True, smooth=True):
        bx, by, bz = base
        rt = radius if radius_top is None else radius_top
        slope = (radius - rt) / height if height else 0
        for i in range(seg):
            a0 = i / seg * math.tau
            a1 = (i + 1) / seg * math.tau
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            b0 = (bx + c0 * radius, by, bz + s0 * radius)
            b1 = (bx + c1 * radius, by, bz + s1 * radius)
            t0 = (bx + c0 * rt, by + height, bz + s0 * rt)
            t1 = (bx + c1 * rt, by + height, bz + s1 * rt)
            if smooth:
                ln = math.sqrt(1 + slope * slope)
                n0 = (c0 / ln, slope / ln, s0 / ln)
                n1 = (c1 / ln, slope / ln, s1 / ln)
                self.tri(b0, t1, b1, color, n0, n1, n1)
                if rt > 1e-5:
                    self.tri(b0, t0, t1, color, n0, n0, n1)
            else:
                self.tri(b0, t1, b1, color)
                if rt > 1e-5:
                    self.tri(b0, t0, t1, color)
            if cap:
                self.tri((bx, by, bz), b0, b1, color, (0, -1, 0), (0, -1, 0), (0, -1, 0))
                if rt > 1e-5:
                    top = (bx, by + height, bz)
                    self.tri(top, t1, t0, color, (0, 1, 0), (0, 1, 0), (0, 1, 0))

    def cone(self, base, radius, height, color, seg=12):
        self.cylinder(base, radius, height, color, seg, radius_top=0.0)

    def sphere(self, center, radius, color, seg=12, rings=8, scale=(1, 1, 1)):
        cx, cy, cz = center
        sx, sy, sz = scale

        def pt(i, j):
            th = j / rings * math.pi
            ph = i / seg * math.tau
            n = (math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph))
            return (cx + n[0] * radius * sx, cy + n[1] * radius * sy, cz + n[2] * radius * sz), n

        for j in range(rings):
            for i in range(seg):
                (a, na), (b, nb) = pt(i, j), pt(i + 1, j)
                (c, nc), (d, nd) = pt(i + 1, j + 1), pt(i, j + 1)
                if j > 0:
                    self.tri(a, b, c, color, na, nb, nc)
                if j < rings - 1:
                    self.tri(a, c, d, color, na, nc, nd)

    def octahedron(self, center, radius, height, color, seg=4):
        cx, cy, cz = center
        top = (cx, cy + height / 2, cz)
        bot = (cx, cy - height / 2, cz)
        for i in range(seg):
            a0 = i / seg * math.tau
            a1 = (i + 1) / seg * math.tau
            p0 = (cx + math.cos(a0) * radius, cy, cz + math.sin(a0) * radius)
            p1 = (cx + math.cos(a1) * radius, cy, cz + math.sin(a1) * radius)
            self.tri(top, p1, p0, color)
            self.tri(bot, p0, p1, color)

    def disc(self, center, radius, color, seg=32):
        cx, cy, cz = center
        n = (0, 1, 0)
        for i in range(seg):
            a0 = i / seg * math.tau
            a1 = (i + 1) / seg * math.tau
            p0 = (cx + math.cos(a0) * radius, cy, cz + math.sin(a0) * radius)
            p1 = (cx + math.cos(a1) * radius, cy, cz + math.sin(a1) * radius)
            self.tri((cx, cy, cz), p1, p0, color, n, n, n,
                     (0.5, 0.5), (0.5 + math.cos(a1) * 0.5, 0.5 + math.sin(a1) * 0.5),
                     (0.5 + math.cos(a0) * 0.5, 0.5 + math.sin(a0) * 0.5))

    def ring(self, center, r_in, r_out, color, seg=40):
        cx, cy, cz = center
        n = (0, 1, 0)
        for i in range(seg):
            a0 = i / seg * math.tau
            a1 = (i + 1) / seg * math.tau
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            i0 = (cx + c0 * r_in, cy, cz + s0 * r_in)
            i1 = (cx + c1 * r_in, cy, cz + s1 * r_in)
            o0 = (cx + c0 * r_out, cy, cz + s0 * r_out)
            o1 = (cx + c1 * r_out, cy, cz + s1 * r_out)
            self.tri(i0, o1, o0, color, n, n, n)
            self.tri(i0, i1, o1, color, n, n, n)

    def rect_xz(self, x0, z0, x1, z1, y, color):
        n = (0, 1, 0)
        self.tri((x0, y, z0), (x1, y, z1), (x1, y, z0), color, n, n, n, (0, 0), (1, 1), (1, 0))
        self.tri((x0, y, z0), (x0, y, z1), (x1, y, z1), color, n, n, n, (0, 0), (0, 1), (1, 1))

    # ------------------------------------------------------------ 출력
    def array(self):
        if not self.verts:
            return np.zeros((0, STRIDE), dtype="f4")
        return np.array(self.verts, dtype="f4")

    def color_groups(self):
        """OBJ 내보내기용: 색별 삼각형 묶음."""
        groups = {}
        for i in range(0, len(self.verts), 3):
            key = tuple(round(c, 3) for c in self.verts[i][6:9])
            groups.setdefault(key, []).append(self.verts[i:i + 3])
        return groups


def export_obj(builder, obj_path, mtl_name):
    """MeshBuilder 를 OBJ + MTL 로 저장 (색은 재질 Kd 로)."""
    import os
    groups = builder.color_groups()
    mtl_path = os.path.join(os.path.dirname(obj_path), mtl_name)
    with open(mtl_path, "w", encoding="utf-8") as f:
        for i, col in enumerate(groups):
            f.write(f"newmtl mat{i}\nKd {col[0]:.4f} {col[1]:.4f} {col[2]:.4f}\nKa 0 0 0\nKs 0 0 0\n\n")
    with open(obj_path, "w", encoding="utf-8") as f:
        f.write("# 자동 생성된 플레이스홀더 모델\n")
        f.write(f"mtllib {mtl_name}\n")
        vi = 1
        for i, (col, tris) in enumerate(groups.items()):
            f.write(f"o part{i}\nusemtl mat{i}\n")
            lines_v, lines_n, lines_f = [], [], []
            for tri in tris:
                for v in tri:
                    lines_v.append(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
                    lines_n.append(f"vn {v[3]:.4f} {v[4]:.4f} {v[5]:.4f}\n")
                lines_f.append(f"f {vi}//{vi} {vi + 1}//{vi + 1} {vi + 2}//{vi + 2}\n")
                vi += 3
            f.writelines(lines_v)
            f.writelines(lines_n)
            f.writelines(lines_f)
