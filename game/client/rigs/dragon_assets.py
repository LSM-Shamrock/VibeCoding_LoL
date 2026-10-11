"""용 — 보스러시(DEEP NEST) 3층 보스 '겁화의 용'의 메시·무늬 만들기 (렌더러당 한 번).

원본: bosses/dragon/rig.py 의 머리(두개골·뿔·갈기·귀지느러미·이빨·수염·아래턱), 날개 뼈대, 다리·발, 등 가시, 꼬리 칼날.
원본은 scene graph 의 볼록 껍질(hull)과 곡선 관을 썼는데, 이 게임의 렌더러에는 없어서 같은 점들로 볼록 껍질을 직접 계산한다.
모든 치수는 원본과 같은 "보스 단위"이고, 그리는 쪽(dragon.py)이 SC 배로 줄인다.
"""
import itertools
import math

import numpy as np
import pygame

from ..geometry import MeshBuilder
from ..gl import Mesh
from .spider import _S, _T, _from_to, _hex, _xf
from .serpent import _ell, _spike, _tri_out, _tube

PI = math.pi
TAU = PI * 2

# 몸통 치수 (dragon.py 와 같은 값)
M = 8                      # 팔각 단면
VW = M + 1
PLATE = 5                  # 갑옷 판 하나의 길이(마디 수)

# 색
SCALE_RED = 0x4A0F0B       # 머리 비늘
DARK = 0x1C0C0B
HORN = 0xD8C9A4
BONE = 0x2B1210
ARMOR = 0x7A1A12
BLADE = 0x5A1410
TAIL_BLADE = 0x1A0D0C
LEG = 0x6A1A12
KNEE = 0xD9A441
CLAW = 0xE6DCC2
FIN = 0x8A1C0E


# ------------------------------------------------------------------ 기하 도구
def hull(points):
    """점들을 감싸는 볼록 다면체의 삼각형 목록 [(a, b, c)] (바깥에서 봐서 반시계). 점이 몇십 개 이하라서 모든 세 점 조합으로 푼다."""
    P = np.asarray(points, float)
    n = len(P)
    center = P.mean(axis=0)
    seen = set()
    out = []
    for i, j, k in itertools.combinations(range(n), 3):
        nrm = np.cross(P[j] - P[i], P[k] - P[i])
        ln = float(np.linalg.norm(nrm))
        if ln < 1e-9:
            continue
        nrm /= ln
        s = P @ nrm - float(nrm @ P[i])
        pos, neg = bool((s > 1e-6).any()), bool((s < -1e-6).any())
        if pos and neg:
            continue
        if not pos and not neg:
            continue
        on = tuple(np.nonzero(np.abs(s) <= 1e-6)[0])
        if on in seen:
            continue
        seen.add(on)
        out_n = nrm if neg else -nrm                       # 나머지 점이 반대편에 있으면 이쪽이 바깥
        poly = P[list(on)]
        c = poly.mean(axis=0)
        a1 = poly[0] - c
        a1 /= max(1e-9, float(np.linalg.norm(a1)))
        a2 = np.cross(out_n, a1)
        ang = [math.atan2(float((p - c) @ a2), float((p - c) @ a1)) for p in poly]
        order = [on[q] for q in np.argsort(ang)]
        for q in range(1, len(order) - 1):
            out.append((tuple(P[order[0]]), tuple(P[order[q]]), tuple(P[order[q + 1]])))
    return out, center


def _hull_mesh(b, pts, color, flat=True):
    tris, c = hull(pts)
    for a, bb, cc in tris:
        _tri_out(b, a, bb, cc, color, c)


def _mirror(points):
    out = []
    for p in points:
        out.append(tuple(p))
        if abs(p[0]) > 1e-4:
            out.append((-p[0], p[1], p[2]))
    return out


def _catmull(path, samples=14):
    """점들을 매끄럽게 지나는 곡선 위의 점 samples+1 개 (호 길이 간격)."""
    P = [np.asarray(p, float) for p in path]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    dense = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, 12, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(P[-2])
    dense = np.array(dense)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, cum[-1], samples + 1)
    return np.stack([np.interp(u, cum, dense[:, c]) for c in range(3)], axis=1)


def _tube_path(b, path, r0, r1, color, radial=6, samples=14):
    """경로를 따라 r0 → r1 로 가늘어지는 곡선 관 (뿔·수염)."""
    _tube(b, [tuple(p) for p in _catmull(path, samples)], r0, r1, color, radial)


def _aimed_spike(b, pos, direction, length, r, color, seg=4, scale=(1, 1, 1)):
    tmp = MeshBuilder()
    tmp.cylinder((0, 0, 0), r, length, color, seg, radius_top=0.0)
    d = np.asarray(direction, float)
    d /= max(1e-9, float(np.linalg.norm(d)))
    _xf(b, tmp, _T(*pos) @ _from_to((0, 1, 0), d) @ _S(*scale))


# ------------------------------------------------------------------ 머리
JAW_PIVOT = (0.0, -0.35, -0.7)
WHISKER_POS = [(0.45, 0.05, 3.0), (0.25, -0.15, 2.5), (-0.45, 0.05, 3.0), (-0.25, -0.15, 2.5)]
MOUTH = (0.0, -0.2, 3.3)


def head_static(k=1.0):
    """두개골 · 눈두덩 · 콧구멍 · 큰 뿔 · 갈기 · 윗니 (머리에 붙어 같이 움직이는 부분)."""
    b = MeshBuilder()
    scales, dark, horn = _hex(SCALE_RED, 1.5), _hex(DARK, 1.6), _hex(HORN, k)
    skull = _mirror([(0, 1.2, -1.9), (0.85, 0.95, -1.7), (1.15, 0.1, -1.7), (0.75, -0.5, -1.6), (1.2, 0.75, 0.2), (1.3, -0.1, 0.2),
                     (0.95, -0.55, 0.2), (0.55, 0.52, 2.6), (0.62, -0.1, 2.95), (0.46, -0.34, 2.7), (0.34, 0.36, 3.4), (0.34, -0.16, 3.5),
                     (0, 0.6, 2.4)])
    _hull_mesh(b, skull, scales)
    for s in (1, -1):
        brow = [(s * 0.55, 0.78, -0.2), (s * 1.28, 0.74, -0.1), (s * 1.1, 1.18, 0.1), (s * 0.5, 0.95, 1.3), (s * 0.92, 0.62, 1.5), (s * 0.45, 0.7, 0.4)]
        _hull_mesh(b, brow, dark)
        _ell(b, (s * 0.22, 0.46, 3.22), (0.17, 0.17, 0.17), dark, 6, 4)             # 콧구멍 혹
        slit = MeshBuilder()
        slit.box((0, 0, 0), (0.03, 0.26, 0.07), (0.02, 0.01, 0.01))
        _xf(b, slit, _T(s * 1.11, 0.52, 0.8))
    # 큰 뿔 (뒤로 휘어 넘어간다) + 작은 뿔 + 볼 가시
    for s in (1, -1):
        _tube_path(b, [(s * 0.55, 0.85, -0.9), (s * 1.1, 1.5, -2.4), (s * 1.45, 1.55, -4.2), (s * 1.3, 1.1, -5.6)], 0.34, 0.02, horn, 7)
        _tube_path(b, [(s * 0.95, 0.4, -1.0), (s * 1.7, 0.6, -2.0), (s * 2.5, 0.35, -3.1)], 0.2, 0.02, horn, 6, 10)
        _tube_path(b, [(s * 1.1, -0.2, -0.5), (s * 1.9, -0.45, -1.1), (s * 2.5, -0.8, -1.4)], 0.17, 0.02, horn, 6, 8)
    # 이마에서 목으로 이어지는 갈기
    for i in range(7):
        z = 1.4 - i * 0.55
        _aimed_spike(b, (0, 1.0 + (0.0 if i < 2 else 0.15), z), (0, 1.0, -0.7 - i * 0.12), 0.9 + i * 0.12, 0.17, dark, 4)
    # 윗니
    for i in range(8):
        z = 0.5 + i * 0.4
        w = 0.96 - min(0.5, i * 0.06)
        for s in (1, -1):
            _aimed_spike(b, (s * w * 0.62, -0.38, z), (0, -1, 0.12), 0.8 if i == 7 else 0.42, 0.1 if i == 7 else 0.07, horn, 4)
    return b


def head_fins():
    """귀지느러미 (부채처럼 뒤로 펼쳐지는 납작한 가시, 양면)."""
    b = MeshBuilder()
    col = _hex(FIN, 1.2)
    for s in (1, -1):
        for k in range(4):
            ang = 0.15 + k * 0.28
            _aimed_spike(b, (s * 0.95, 0.35 + k * 0.08, -0.9), (s * math.sin(ang) * 0.9, 0.25 - k * 0.1, -math.cos(ang)), 2.6 - k * 0.3, 0.42,
                         col, 3, (1, 1, 0.22))
    return b


def head_jaw(k=1.0):
    """아래턱 (JAW_PIVOT 기준 로컬): 턱뼈 · 아랫니 · 턱 밑 가시."""
    b = MeshBuilder()
    scales, dark, horn = _hex(SCALE_RED, 1.5), _hex(DARK, 1.6), _hex(HORN, k)
    jaw = _mirror([(0.75, 0.0, 0.1), (0.86, -0.28, 0.9), (0.56, -0.34, 2.6), (0.4, -0.18, 3.4), (0.52, 0.04, 1.8), (0.36, 0.04, 3.6),
                   (0, -0.32, 3.7), (0, -0.1, -0.3)])
    _hull_mesh(b, jaw, scales)
    for i in range(6):
        z = 0.8 + i * 0.5
        for s in (1, -1):
            _aimed_spike(b, (s * 0.5, 0.02, z), (0, 1, -0.1), 0.36, 0.06, horn, 4)
    _aimed_spike(b, (0, -0.3, 3.0), (0, -1, -0.6), 1.4, 0.2, dark, 4)
    _aimed_spike(b, (0, -0.3, 2.2), (0, -1, -0.5), 1.0, 0.16, dark, 4)
    return b


def head_mouth():
    """입속 (붉은 살, 불빛을 받아 빛난다)."""
    b = MeshBuilder()
    b.box((0, 0, 1.9), (1.1, 0.12, 3.0), (0.9, 0.16, 0.07))
    return b


def head_whisker(side):
    """수염 한 가닥 (뿌리가 원점)."""
    b = MeshBuilder()
    _tube_path(b, [(0, 0, 0), (side * 1.0, 0.3, 0.2), (side * 2.0, -0.1, -0.9), (side * 2.8, -0.9, -2.4), (side * 3.1, -1.3, -4.0)], 0.07, 0.015,
               _hex(HORN, 1.0), 5)
    return b


def head_eye():
    b = MeshBuilder()
    _ell(b, (0, 0, 0), (0.2 * 0.8, 0.2, 0.2 * 1.35), (1, 1, 1), 8, 6)
    return b


def gem(sx, sy, sz, bezel=True):
    """약점 보석 (팔면체)와 어두운 테두리."""
    b = MeshBuilder()
    c = np.zeros(3)
    pts = [(sx, 0, 0), (-sx, 0, 0), (0, sy, 0), (0, -sy, 0), (0, 0, sz), (0, 0, -sz)]
    for a, bb, cc in ((0, 2, 4), (4, 2, 1), (1, 2, 5), (5, 2, 0), (0, 4, 3), (4, 1, 3), (1, 5, 3), (5, 0, 3)):
        _tri_out(b, pts[a], pts[bb], pts[cc], (1, 1, 1), c)
    return b


def gem_bezel(sx, sy, sz, k=1.3):
    b = MeshBuilder()
    _hull_mesh(b, [(sx * k, 0, 0), (-sx * k, 0, 0), (0, sy * k, 0), (0, -sy * k, 0), (0, 0, sz * k * 0.8), (0, 0, -sz * k * 0.8)], _hex(DARK, 1.6))
    return b


# ------------------------------------------------------------------ 날개 · 다리 · 등 · 꼬리
def unit_segment(top, bottom, color, seg=6):
    """원점(y=0, 반지름 bottom)에서 +y(y=1, 반지름 top)로 뻗는 절두체."""
    b = MeshBuilder()
    b.cylinder((0, 0, 0), bottom, 1.0, color, seg, radius_top=top)
    return b


def unit_spike(r, color, seg=4):
    b = MeshBuilder()
    b.cylinder((0, 0, 0), r, 1.0, color, seg, radius_top=0.0)
    return b


def joint_ball(color):
    b = MeshBuilder()
    _ell(b, (0, 0, 0), (1, 1, 1), color, 6, 4)
    return b


def spine_blade():
    b = MeshBuilder()
    _hull_mesh(b, [(-0.34, 0, -1.3), (0.34, 0, -1.3), (-0.34, 0, 1.5), (0.34, 0, 1.5), (0, 3.0, -1.2), (0, 1.0, 1.0)], _hex(BLADE, 1.5))
    return b


def tail_blade():
    b = MeshBuilder()
    pts = _mirror([(0, 0.14, 0), (0.55, 0.14, -0.6), (1.35, 0.1, -2.0), (0.5, 0.06, -3.6), (0, 0.04, -5.2), (0, -0.14, 0), (0.55, -0.14, -0.6),
                   (1.35, -0.1, -2.0), (0.5, -0.06, -3.6)])
    _hull_mesh(b, pts, _hex(TAIL_BLADE, 2.0))
    return b


def paw():
    """발: 손바닥 + 발가락 3개 + 뒷발톱. 로컬: +Z 앞, +Y 위. (원본은 0.75 배로 줄여 쓴다)"""
    b = MeshBuilder()
    leg, claw = _hex(LEG, 1.2), _hex(CLAW, 1.0)
    _ell(b, (0, 0.6, 0), (2.25, 0.8, 2.15), leg, 8, 5)

    def toe(x, z, yaw, stub, claw_len):
        t = MeshBuilder()
        t.cylinder((0, 0, 0), 1.2, stub, leg, 6, radius_top=0.9)
        tc = MeshBuilder()
        tc.cylinder((0, 0, 0), 1.0, claw_len, claw, 4, radius_top=0.0)
        rot = _from_to((0, 1, 0), (0, 0, 1))                 # 원통은 +y 로 서므로 +z 로 눕힌다
        _xf(b, t, _T(x, 0.8, z) @ _roty(yaw) @ rot)
        _xf(b, tc, _T(x, 0.8, z) @ _roty(yaw) @ _T(0, 0, stub) @ rot)

    FAN = math.radians(22)
    for k in (-1, 0, 1):
        toe(k * 0.45, 1.5, k * FAN, 1.6, 3.6)
    toe(0, -1.5, PI, 1.0, 3.0)
    return b


def _roty(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def chunk():
    """죽을 때 흩어지는 몸 조각 (갑옷 판)."""
    b = MeshBuilder()
    b.box((0, 0, 0), (2.0, 1.6, 2.0), (0.62, 0.14, 0.1))
    return b


def _opaque(surf):
    """무늬 그림의 알파를 전부 255 로 (알파 칸 없는 면을 그대로 올리면 쓰레기 값이 들어가 셰이더가 픽셀을 버린다)."""
    al = pygame.surfarray.pixels_alpha(surf)
    al[:] = 255
    del al
    return surf


# ------------------------------------------------------------------ 무늬
def armor_surface():
    """갑옷 판 무늬. 한 판(세로 1주기)에 팔각 단면의 면 8개(가로 1주기): 등은 진홍, 배는 황갈색, 판 이음매에는 용암빛."""
    S = 256
    faces = 8
    fw = S // faces
    img = np.zeros((S, S, 3), dtype=float)                       # [y, x]
    back = np.array([0.66, 0.12, 0.09])
    belly = np.array([0.92, 0.66, 0.36])
    xs = (np.arange(fw) + 0.5) / fw
    prof = np.interp(xs, [0, 0.18, 0.5, 0.82, 1], [0.51, 0.88, 1.0, 0.82, 0.48])
    for f in range(faces):
        th = (f + 0.5) / faces * TAU
        t = min(1.0, max(0.0, -math.sin(th) * 1.7 - 0.12))
        t = t * t * (3 - 2 * t)
        base = back * (1 - t) + belly * t
        for ix in range(fw):
            img[:, f * fw + ix, :] = base * prof[ix]
    img[S - 22:, :, :] *= 0.5                                     # 판 아래 홈
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    arr = np.clip(img * 255, 0, 255).astype(np.uint8)
    pygame.surfarray.blit_array(surf, np.transpose(arr, (1, 0, 2)))
    seed = [23]

    def rnd():
        seed[0] = (seed[0] * 16807) % 2147483647
        return seed[0] / 2147483647

    for f in range(faces):
        x0 = f * fw
        pygame.draw.rect(surf, (255, 235, 220), (x0 + 3, 6, fw - 6, 5))                     # 윗면 하이라이트
        surf.fill(tuple(int(c * 0.78 + 255 * 0.22) for c in surf.get_at((x0 + 3, 8))[:3]), (x0 + 3, 6, fw - 6, 5))
        for rx in (x0 + 7, x0 + fw - 7):                                                    # 리벳
            pygame.draw.circle(surf, (232, 214, 200), (rx, 16), 3)
            pygame.draw.circle(surf, (90, 30, 24), (rx + 1, 17), 2)
        for _k in range(4):                                                                 # 긁힌 자국
            sx = x0 + 6 + rnd() * (fw - 12)
            sy = 30 + rnd() * 150
            pygame.draw.line(surf, (70, 24, 20), (sx, sy), (sx + (rnd() - 0.5) * 12, sy + 8 + rnd() * 22), 1)
        hot = rnd() < 0.5                                                                   # 이음매에서 새는 용암빛
        pygame.draw.rect(surf, (255, 150, 44) if hot else (240, 100, 34), (x0 + 2, S - 9, fw - 4, 4))
        pygame.draw.rect(surf, (255, 205, 110), (x0 + 6, S - 7, fw - 12, 2))
    return _opaque(surf)


def membrane_surface():
    """날개막: 짙은 적갈색 바탕에 부챗살로 뻗는 핏줄과 힘줄."""
    W = H = 256
    ys = np.linspace(0, 1, H)[:, None]
    stops = [(0.0, (0x5A, 0x17, 0x10)), (0.55, (0x8A, 0x2A, 0x14)), (1.0, (0xB4, 0x42, 0x1C))]
    img = np.zeros((H, W, 3))
    for c in range(3):
        img[:, :, c] = np.interp(ys[:, 0], [s[0] for s in stops], [s[1][c] for s in stops])[:, None]
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.surfarray.blit_array(surf, np.transpose(img.astype(np.uint8), (1, 0, 2)))
    seed = [77]

    def rnd():
        seed[0] = (seed[0] * 16807) % 2147483647
        return seed[0] / 2147483647

    for k in range(20):
        x = (k + 0.5) * (W / 20) + (rnd() - 0.5) * 6
        col = (int(40 + 20 * rnd()), 10, 8)
        for y in range(0, H, 16):
            nx = x + (rnd() - 0.5) * 5
            pygame.draw.line(surf, col, (x, y), (nx, y + 16), 1 + int(rnd() * 1.6))
            x = nx
    for k in range(6):
        y = 30 + k * 36
        pygame.draw.line(surf, (160, 84, 56), (0, y), (W, y + (rnd() - 0.5) * 8), 1)
    return _opaque(surf)


# ------------------------------------------------------------------ 에셋 묶음
class DragonAssets:
    def __init__(self, renderer, nr):
        self.r = renderer
        mk = lambda b: Mesh.from_builder(renderer, b)
        self.head, self.fins, self.jaw, self.mouth = mk(head_static()), mk(head_fins()), mk(head_jaw()), mk(head_mouth())
        self.whisker = [mk(head_whisker(1)), mk(head_whisker(-1))]
        self.eye = mk(head_eye())
        self.gem_f = mk(gem(0.3, 0.46, 0.2))
        self.gem_f_bezel = mk(gem_bezel(0.3, 0.46, 0.2))
        self.gem_c = mk(gem(1.7, 2.8, 1.1))
        self.gem_c_bezel = mk(gem_bezel(1.7, 2.8, 1.1))
        self.spine, self.tail_blade = mk(spine_blade()), mk(tail_blade())
        self.bone = mk(unit_segment(0.62, 1.0, _hex(BONE, 2.2)))
        self.cuff = mk(unit_segment(1.2, 1.34, _hex(ARMOR, 1.3)))
        self.joint = mk(joint_ball(_hex(ARMOR, 1.3)))
        self.claw = mk(unit_spike(0.16, _hex(HORN, 1.0)))
        self.thumb = mk(unit_spike(0.3, _hex(HORN, 1.0)))
        self.upper = mk(unit_segment(0.8, 1.0, _hex(LEG, 1.3), 7))
        self.lower = mk(unit_segment(0.34, 0.9, _hex(LEG, 1.3), 7))
        self.knee = mk(joint_ball(_hex(KNEE, 1.0)))
        self.paw = mk(paw())
        self.chunk = mk(chunk())
        sph = MeshBuilder()
        sph.sphere((0, 0, 0), 1.0, (1, 1, 1), 10, 8)
        self.orb = mk(sph)
        sh = MeshBuilder()
        sh.disc((0, 0, 0), 1.0, (0, 0, 0), 18)
        self.shadow = mk(sh)
        self.body_tex = renderer.make_texture(armor_surface())
        self.mem_tex = renderer.make_texture(membrane_surface())
        # 몸통 관: 정점 배열의 위상 (위치·법선은 매 프레임 채운다)
        a = (np.arange(nr - 1)[:, None] * VW + np.arange(M)[None, :]).ravel()
        b_, c, d = a + 1, a + VW, a + VW + 1
        self.body_idx = np.stack([a, c, b_, b_, c, d], axis=1).ravel()
        uv = np.zeros((nr * VW, 2))
        uv[:, 0] = (np.arange(VW) / M)[None, :].repeat(nr, axis=0).ravel()
        uv[:, 1] = (np.arange(nr) / PLATE)[:, None].repeat(VW, axis=1).ravel()
        tmpl = np.zeros((len(self.body_idx), 11), dtype="f4")
        tmpl[:, 6:9] = 1.0
        tmpl[:, 9:11] = uv[self.body_idx]
        self.body_template = tmpl
        self._pool = []

    def take_body(self):
        if self._pool:
            return self._pool.pop()
        return Mesh(self.r, [(self.body_template, self.body_tex)])

    def recycle(self, mesh):
        self._pool.append(mesh)
