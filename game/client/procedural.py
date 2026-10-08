"""코드로 만드는 로우폴리 모델들. 모든 모델은 발밑이 원점, 앞쪽이 +Z."""
import math
import random

from ..shared import mapdata
from .geometry import MeshBuilder

TEAM_COLORS = {0: (0.25, 0.55, 1.0), 1: (1.0, 0.32, 0.3)}
STONE = (0.55, 0.6, 0.7)
STONE_DARK = (0.35, 0.39, 0.48)
SNOW = (0.88, 0.92, 0.98)


def _mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


# ------------------------------------------------------------------ 챔피언
def build_frost_archer():
    """'세라(서리 궁수)' 플레이스홀더. tools/make_placeholder_model.py 가 OBJ 로 내보낸다."""
    b = MeshBuilder()
    boots = (0.16, 0.18, 0.26)
    pants = (0.22, 0.28, 0.45)
    tunic = (0.5, 0.72, 0.95)
    trim = (0.92, 0.95, 1.0)
    belt = (0.42, 0.3, 0.22)
    skin = (0.96, 0.83, 0.74)
    hair = (0.86, 0.9, 1.0)
    cape = (0.16, 0.28, 0.62)
    ice = (0.6, 0.9, 1.0)

    for sx in (-1, 1):
        b.box((0.13 * sx, 0.1, 0.03), (0.18, 0.2, 0.3), boots)
        b.box((0.13 * sx, 0.52, 0.0), (0.17, 0.66, 0.19), pants, taper=1.1)
    # 치마형 상의 아랫단
    b.cylinder((0, 0.72, 0), 0.31, 0.22, tunic, seg=10, radius_top=0.26)
    b.box((0, 0.92, 0), (0.46, 0.08, 0.28), belt)
    b.box((0, 0.94, 0.15), (0.1, 0.1, 0.03), (0.85, 0.75, 0.4))
    b.box((0, 1.18, 0), (0.5, 0.5, 0.28), tunic, taper=0.92)
    b.box((0, 1.18, 0.142), (0.08, 0.48, 0.02), trim)
    b.octahedron((0, 1.25, 0.16), 0.07, 0.16, ice)
    # 어깨 / 팔
    for sx in (-1, 1):
        b.sphere((0.3 * sx, 1.4, 0), 0.12, trim, seg=8, rings=5, scale=(1.1, 0.8, 1.1))
        b.box((0.33 * sx, 1.15, 0.02), (0.13, 0.46, 0.14), tunic, taper=0.85)
        b.box((0.34 * sx, 0.88, 0.04), (0.11, 0.12, 0.11), skin)
    # 목 / 머리
    b.cylinder((0, 1.42, 0), 0.07, 0.1, skin, seg=8)
    b.sphere((0, 1.65, 0.01), 0.17, skin, seg=12, rings=8)
    b.sphere((0, 1.7, -0.025), 0.185, hair, seg=12, rings=8, scale=(1.04, 0.92, 1.05))
    b.box((0, 1.6, -0.13), (0.3, 0.3, 0.08), hair, taper=0.8)
    b.cone((0, 1.18, -0.2), 0.08, 0.42, hair, seg=8)          # 땋은 머리
    for sx in (-1, 1):
        b.sphere((0.065 * sx, 1.66, 0.155), 0.025, (0.2, 0.45, 0.8), seg=6, rings=4)
    # 망토
    b.box((0, 1.05, -0.18), (0.62, 0.78, 0.04), cape, taper=0.7)
    b.box((0, 0.63, -0.185), (0.64, 0.06, 0.045), trim)
    # 화살통
    b.cylinder((0.14, 0.95, -0.26), 0.08, 0.5, belt, seg=8)
    for i in range(3):
        b.cone((0.1 + i * 0.04, 1.45, -0.26), 0.035, 0.12, ice, seg=6)
    # 활 (왼손)
    cx, cy, cz = -0.42, 1.0, 0.16
    pts = []
    for k in range(13):
        t = (k / 12 - 0.5) * 2.2
        pts.append((cx, cy + math.sin(t) * 0.62, cz + math.cos(t) * 0.18))
    for p in pts:
        b.sphere(p, 0.045, ice, seg=6, rings=4)
    b.box((cx, cy, pts[0][2]), (0.015, abs(pts[-1][1] - pts[0][1]), 0.015), trim)
    b.box((cx, cy, cz + 0.17), (0.07, 0.16, 0.07), belt)
    return b


def build_mannequin(color):
    """챔피언 모델 파일이 없을 때 쓰는 단순 인형."""
    b = MeshBuilder()
    dark = _mix(color, (0.1, 0.1, 0.15), 0.6)
    for sx in (-1, 1):
        b.box((0.14 * sx, 0.42, 0), (0.18, 0.84, 0.2), dark)
        b.box((0.36 * sx, 1.1, 0), (0.13, 0.55, 0.14), color)
    b.box((0, 1.15, 0), (0.52, 0.65, 0.3), color, taper=0.9)
    b.sphere((0, 1.65, 0), 0.2, (0.95, 0.85, 0.75))
    b.box((0, 1.65, 0.19), (0.2, 0.06, 0.04), (0.1, 0.1, 0.1))
    return b


# ------------------------------------------------------------------ 미니언
def build_minion(mtype, team):
    tc = TEAM_COLORS[team]
    metal = (0.62, 0.66, 0.74)
    dark = (0.22, 0.24, 0.3)
    b = MeshBuilder()
    if mtype == "melee":
        for sx in (-1, 1):
            b.box((0.12 * sx, 0.18, 0), (0.13, 0.36, 0.15), dark)
        b.box((0, 0.58, 0), (0.46, 0.46, 0.34), tc, taper=0.85)
        b.sphere((0, 0.95, 0), 0.17, metal, seg=10, rings=6)
        b.box((0, 0.95, 0.15), (0.24, 0.05, 0.04), (0.1, 0.1, 0.12))
        b.cone((0, 1.08, 0), 0.08, 0.16, tc, seg=6)
        b.box((-0.3, 0.6, 0.12), (0.06, 0.4, 0.3), tc)
    elif mtype == "caster":
        b.cylinder((0, 0, 0), 0.3, 0.75, tc, seg=10, radius_top=0.16)
        b.sphere((0, 0.88, 0), 0.15, (0.85, 0.8, 0.75), seg=10, rings=6)
        b.cone((0, 0.96, 0), 0.22, 0.4, _mix(tc, (0.1, 0.1, 0.2), 0.4), seg=10)
    elif mtype == "cannon":
        b.box((0, 0.42, 0), (0.85, 0.42, 1.0), dark)
        b.box((0, 0.66, 0), (0.7, 0.1, 0.85), tc)
        for sx in (-1, 1):
            for sz in (-1, 1):
                b.sphere((0.46 * sx, 0.24, 0.33 * sz), 0.22, (0.3, 0.25, 0.2), seg=10, rings=6, scale=(0.4, 1, 1))
        b.box((0, 0.82, 0.25), (0.24, 0.24, 1.0), metal)
        b.cylinder((0, 0.7, -0.15), 0.2, 0.3, metal, seg=8)
    else:  # super
        for sx in (-1, 1):
            b.box((0.22 * sx, 0.35, 0), (0.25, 0.7, 0.3), dark)
            b.sphere((0.48 * sx, 1.45, 0), 0.22, tc, seg=8, rings=5)
            b.box((0.55 * sx, 1.05, 0.05), (0.2, 0.6, 0.22), metal)
        b.box((0, 1.1, 0), (0.85, 0.8, 0.55), tc, taper=0.85)
        b.sphere((0, 1.72, 0), 0.25, metal, seg=10, rings=6)
        b.box((0, 1.74, 0.22), (0.3, 0.06, 0.05), (1.0, 0.85, 0.3))
        b.box((0.62, 1.0, 0.45), (0.12, 0.12, 0.9), metal)
    return b


# 무기를 따로 만드는 미니언: 몸통과 분리해 공격할 때 휘두른다.
# 반환: (builder, 손 위치) — builder 의 원점이 손(회전축)이다.
MINION_WEAPON_PIVOT = {"melee": (0.32, 0.62, -0.05), "caster": (0.3, 0.55, 0.08)}


def build_minion_weapon(mtype, team):
    tc = TEAM_COLORS[team]
    b = MeshBuilder()
    if mtype == "melee":
        b.box((0, 0, 0.27), (0.06, 0.06, 0.6), (0.62, 0.66, 0.74))      # 앞으로 뻗은 검
    elif mtype == "caster":
        b.box((0, 0, 0), (0.05, 1.0, 0.05), (0.45, 0.32, 0.2))          # 지팡이
        b.sphere((0, 0.53, 0), 0.09, _mix(tc, (1, 1, 1), 0.5), seg=8, rings=5)
    else:
        return None
    return b, MINION_WEAPON_PIVOT[mtype]


# ------------------------------------------------------------------ 부쉬
def build_bush(rx, rz, seed=0):
    """타원 범위를 채우는 풀 덤불. 원점이 부쉬 중심."""
    rng = random.Random(seed)
    b = MeshBuilder()
    dark, light = (0.18, 0.42, 0.26), (0.36, 0.64, 0.36)
    # 둥글게 뭉친 잎 덩어리 (가시처럼 보이지 않게 원뿔 대신 납작한 구)
    n = int(rx * rz * 3.2)
    for _ in range(n):
        a = rng.uniform(0, math.tau)
        k = math.sqrt(rng.uniform(0, 1))
        x, z = math.cos(a) * rx * k * 0.85, math.sin(a) * rz * k * 0.85
        r = rng.uniform(0.42, 0.62) * (1.0 - 0.2 * k)
        y = r * 0.55 + rng.uniform(0.0, 0.25) * (1.0 - k)
        b.sphere((x, y, z), r, _mix(dark, light, rng.uniform(0, 1)), seg=8, rings=5, scale=(1.0, 0.8, 1.0))
    return b


# ------------------------------------------------------------------ 구조물
def build_turret(team):
    tc = TEAM_COLORS[team]
    b = MeshBuilder()
    b.cylinder((0, 0, 0), 1.25, 0.45, STONE_DARK, seg=8, smooth=False)
    b.box((0, 1.9, 0), (1.15, 3.0, 1.15), STONE, taper=0.72, rot_y=math.pi / 4)
    for k in range(4):
        a = k * math.pi / 2
        b.box((math.cos(a) * 0.62, 1.0, math.sin(a) * 0.62), (0.22, 1.6, 0.22), STONE_DARK, taper=0.6)
    b.cylinder((0, 3.35, 0), 0.75, 0.35, STONE_DARK, seg=8, smooth=False)
    for k in range(6):
        a = k / 6 * math.tau
        b.box((math.cos(a) * 0.62, 3.85, math.sin(a) * 0.62), (0.16, 0.5, 0.16), _mix(tc, (1, 1, 1), 0.3), taper=0.4)
    b.octahedron((0, 4.35, 0), 0.42, 1.1, _mix(tc, (1, 1, 1), 0.35), seg=6)
    return b


def build_rubble():
    b = MeshBuilder()
    rng = random.Random(7)
    b.cylinder((0, 0, 0), 1.25, 0.35, STONE_DARK, seg=8, smooth=False)
    for _ in range(7):
        a = rng.random() * math.tau
        r = rng.uniform(0.2, 1.1)
        b.box((math.cos(a) * r, 0.45, math.sin(a) * r), (rng.uniform(0.3, 0.6),) * 3, STONE, rot_y=rng.random() * 3)
    return b


def build_inhibitor(team, alive=True):
    tc = TEAM_COLORS[team] if alive else (0.3, 0.3, 0.35)
    b = MeshBuilder()
    b.cylinder((0, 0, 0), 1.7, 0.3, STONE_DARK, seg=12, smooth=False)
    for k in range(6):
        a = k / 6 * math.tau
        b.box((math.cos(a) * 1.35, 0.9, math.sin(a) * 1.35), (0.28, 1.4, 0.28), STONE, taper=0.6, rot_y=-a)
    if alive:
        b.sphere((0, 1.35, 0), 0.75, _mix(tc, (1, 1, 1), 0.25), seg=14, rings=10)
        b.ring((0, 1.35, 0), 0.95, 1.1, _mix(tc, (1, 1, 1), 0.6))
    else:
        b.sphere((0, 0.45, 0), 0.5, tc, seg=8, rings=5, scale=(1, 0.4, 1))
    return b


def build_nexus(team, alive=True):
    tc = TEAM_COLORS[team] if alive else (0.3, 0.3, 0.35)
    b = MeshBuilder()
    b.cylinder((0, 0, 0), 2.6, 0.5, STONE_DARK, seg=10, smooth=False)
    b.cylinder((0, 0.5, 0), 1.9, 0.6, STONE, seg=10, smooth=False, radius_top=1.5)
    if alive:
        b.octahedron((0, 3.0, 0), 1.25, 3.4, _mix(tc, (1, 1, 1), 0.25), seg=6)
        for k in range(4):
            a = k / 4 * math.tau + 0.4
            b.octahedron((math.cos(a) * 1.9, 2.2, math.sin(a) * 1.9), 0.3, 0.8, _mix(tc, (1, 1, 1), 0.5), seg=4)
    else:
        rng = random.Random(3)
        for _ in range(6):
            a = rng.random() * math.tau
            b.octahedron((math.cos(a) * 1.2, 1.2, math.sin(a) * 1.2), 0.4, 0.9, tc, seg=4)
    return b


def build_relic():
    b = MeshBuilder()
    b.octahedron((0, 0, 0), 0.35, 0.8, (0.4, 1.0, 0.55), seg=6)
    return b


# ------------------------------------------------------------------ 투사체 / 이펙트
def build_arrow(color):
    b = MeshBuilder()
    b.box((0, 0, -0.1), (0.06, 0.06, 0.7), color)
    b.octahedron((0, 0, 0.3), 0.09, 0.09, color, seg=4)
    return b


def build_frost_bolt():
    b = MeshBuilder()
    b.octahedron((0, 0, 0), 0.22, 0.22, (0.75, 0.95, 1.0), seg=6)
    b.box((0, 0, -0.4), (0.12, 0.12, 0.8), (0.5, 0.8, 1.0), taper=0.3)
    return b


def build_orb(color, r=0.18):
    b = MeshBuilder()
    b.sphere((0, 0, 0), r, color, seg=8, rings=6)
    return b


def build_shadow():
    b = MeshBuilder()
    b.disc((0, 0, 0), 1.0, (0, 0, 0), 20)
    return b


# ------------------------------------------------------------------ 맵
PANEL_A = (0.26, 0.29, 0.36)
PANEL_B = (0.235, 0.265, 0.335)
HULL = (0.11, 0.12, 0.17)
GLOW = (0.45, 0.95, 1.0)


def _edge_box(b, p0, p1, y, size_y, size_z, color):
    """두 점 p0-p1 (xz) 을 잇는 방향으로 놓인 박스."""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dz)
    ang = math.atan2(-dz, dx)
    b.box(((p0[0] + p1[0]) / 2, y, (p0[1] + p1[1]) / 2), (length + 0.02, size_y, size_z), color, rot_y=ang)


def build_map():
    """우주에 떠 있는 플랫폼 라인 (칼바람 나락 배치 그대로)."""
    rng = random.Random(42)
    b = MeshBuilder()
    end = mapdata.LANE_END
    depth = 1.4
    step = 2.0

    # 라인 바닥 패널 + 옆면(두께)
    x, ix = -end, 0
    while x < end - 1e-6:
        x1 = x + step
        hw0, hw1 = mapdata.half_width(x), mapdata.half_width(x1)
        cols = 6
        for c in range(cols):
            t0, t1 = c / cols, (c + 1) / cols
            za0, za1 = -hw0 + 2 * hw0 * t0, -hw0 + 2 * hw0 * t1
            zb0, zb1 = -hw1 + 2 * hw1 * t0, -hw1 + 2 * hw1 * t1
            base = PANEL_A if (ix + c) % 2 == 0 else PANEL_B
            shade = rng.uniform(-0.012, 0.012)
            base = tuple(v + shade for v in base)
            n = (0, 1, 0)
            b.tri((x, 0, za0), (x1, 0, zb1), (x1, 0, zb0), base, n, n, n)
            b.tri((x, 0, za0), (x, 0, za1), (x1, 0, zb1), base, n, n, n)
        for side in (-1, 1):
            a0, a1 = (x, side * hw0), (x1, side * hw1)
            # 옆면
            b.quad((a0[0], 0, a0[1]), (a1[0], 0, a1[1]), (a1[0], -depth, a1[1]), (a0[0], -depth, a0[1]), HULL)
            # 안쪽 유도선 (은은한 발광)
            _edge_box(b, (x, side * (hw0 - 0.6)), (x1, side * (hw1 - 0.6)), 0.005, 0.01, 0.1, (0.25, 0.55, 0.7))
            # 난간 + 발광 띠
            _edge_box(b, (x, side * (hw0 + 0.25)), (x1, side * (hw1 + 0.25)), 0.2, 0.4, 0.3, (0.33, 0.36, 0.45))
            _edge_box(b, (x, side * (hw0 + 0.25)), (x1, side * (hw1 + 0.25)), 0.43, 0.06, 0.14, GLOW)
        # 바닥면
        b.quad((x, -depth, -hw0), (x1, -depth, -hw1), (x1, -depth, hw1), (x, -depth, hw0), HULL)
        x = x1
        ix += 1
    # 양 끝 마감
    for sx in (-1, 1):
        hw = mapdata.half_width(end)
        b.quad((sx * end, 0, -hw), (sx * end, 0, hw), (sx * end, -depth, hw), (sx * end, -depth, -hw), HULL)

    # 가장자리 기둥 + 조명
    for k in range(-6, 7):
        px = k * 10.0
        for side in (-1, 1):
            hw = mapdata.half_width(px)
            pz = side * (hw + 0.35)
            b.box((px, 0.8, pz), (0.55, 1.6, 0.55), (0.3, 0.33, 0.42), taper=0.7)
            b.octahedron((px, 1.85, pz), 0.22, 0.5, GLOW, seg=4)

    # 플랫폼 아래 구조물 (엔진 / 지지대)
    for k in range(-11, 12):
        px = k * 5.5 + rng.uniform(-1, 1)
        hw = mapdata.half_width(px)
        w = rng.uniform(1.5, 3.0)
        h = rng.uniform(1.5, 4.0)
        pz = rng.uniform(-hw * 0.6, hw * 0.6)
        b.box((px, -depth - h / 2, pz), (w, h, w * rng.uniform(1.0, 2.2)), HULL, taper=rng.uniform(1.4, 2.0))
        if rng.random() < 0.5:
            b.octahedron((px, -depth - h - 0.3, pz), 0.35, 0.6, (0.4, 0.7, 1.0), seg=6)

    # 우물 발판
    for team in (0, 1):
        fx, fz = mapdata.fountain_pos(team)
        tc = TEAM_COLORS[team]
        b.cylinder((fx, -depth, fz), 8.0, depth + 0.02, _mix(tc, HULL, 0.75), seg=24, smooth=False)
        b.cylinder((fx, -depth - 2.5, fz), 3.0, 2.5, HULL, seg=12, radius_top=6.0, smooth=False)
        b.ring((fx, 0.04, fz), 6.8, 7.4, _mix(tc, (1, 1, 1), 0.3))
        for k in range(8):
            a = k / 8 * math.tau
            b.box((fx + math.cos(a) * 8.6, 1.2, fz + math.sin(a) * 8.6), (0.5, 2.4, 0.5), (0.3, 0.33, 0.42), taper=0.5)
            b.octahedron((fx + math.cos(a) * 8.6, 2.6, fz + math.sin(a) * 8.6), 0.2, 0.45, _mix(tc, (1, 1, 1), 0.4), seg=4)
        b.octahedron((fx + mapdata.team_dir(team) * -2.0, 2.5, fz), 0.7, 2.0, _mix(tc, (1, 1, 1), 0.4), seg=6)

    # 주변을 떠다니는 소행성
    rock_a, rock_b = (0.3, 0.28, 0.3), (0.48, 0.44, 0.42)
    for _ in range(110):
        if rng.random() < 0.65:
            side = rng.choice((-1, 1))
            pos = (rng.uniform(-120, 120), rng.uniform(-28, 3), side * rng.uniform(17, 65))
        else:
            pos = (rng.uniform(-110, 110), rng.uniform(-50, -12), rng.uniform(-16, 16))
        r = rng.uniform(0.5, 3.6)
        col = _mix(rock_a, rock_b, rng.random())
        b.sphere(pos, r, col, seg=7, rings=5,
                 scale=(rng.uniform(0.7, 1.4), rng.uniform(0.6, 1.1), rng.uniform(0.7, 1.4)))
        if rng.random() < 0.25:
            b.octahedron((pos[0], pos[1] + r * 0.8, pos[2]), r * 0.25, r * 0.9, (0.5, 0.9, 1.0), seg=5)
    return b