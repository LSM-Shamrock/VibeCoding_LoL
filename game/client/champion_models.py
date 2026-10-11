"""챔피언 모델과 스킬 투사체·장치 모델 (코드로 만드는 로우폴리).

모든 모델은 발밑이 원점, 앞쪽이 +Z. 챔피언 JSON 의 "model": {"procedural": "<id>"} 로 고른다.
모델 파일(.obj/.glb)을 쓰고 싶으면 JSON 의 "model" 을 {"file": "...", "height": 1.8} 로 바꾸면 이 모델 대신 쓰인다.
"""
import math

from .geometry import MeshBuilder

TAU = math.tau
SKIN = (0.96, 0.82, 0.70)
SKIN_D = (0.80, 0.60, 0.46)
STEEL = (0.62, 0.66, 0.74)
STEEL_D = (0.34, 0.37, 0.46)
STEEL_L = (0.80, 0.84, 0.92)
GOLD = (0.94, 0.76, 0.30)
DARK = (0.12, 0.10, 0.16)


def _mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


# ------------------------------------------------------------------ 기하 도우미
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    ln = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def _face(b, pts, center, color):
    """사각형을 바깥쪽(center 에서 멀어지는 쪽)을 보도록 감아서 추가."""
    n = _cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0]))
    fc = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    if _dot(n, _sub(fc, center)) < 0:
        pts = pts[::-1]
    b.quad(pts[0], pts[1], pts[2], pts[3], color)


def bar(b, p0, p1, w, color, w1=None, t=None, t1=None, hint=(0, 1, 0)):
    """p0→p1 을 잇는 사각 단면 막대. w 는 폭, t 는 두께(생략하면 w), w1/t1 은 끝쪽 값(끝으로 갈수록 가늘어짐).

    폭 방향은 (진행 방향 x hint) 에 수직인 쪽이라, 납작한 칼날은 hint 로 눕는 방향을 정한다.
    """
    w1 = w if w1 is None else w1
    if t is None:
        t, t1 = w, w1
    elif t1 is None:
        t1 = t
    w1, t1 = max(w1, 0.003), max(t1, 0.003)
    d = _norm(_sub(p1, p0))
    h = _norm(hint)
    if abs(_dot(d, h)) > 0.95:
        h = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 0.0, 1.0)
    u = _norm(_cross(d, h))
    v = _cross(d, u)

    def ring(p, wi, ti):
        return [(p[0] + u[0] * wi / 2 * sx + v[0] * ti / 2 * sy,
                 p[1] + u[1] * wi / 2 * sx + v[1] * ti / 2 * sy,
                 p[2] + u[2] * wi / 2 * sx + v[2] * ti / 2 * sy) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    r0, r1 = ring(p0, w, t), ring(p1, w1, t1)
    c = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2)
    for i in range(4):
        j = (i + 1) % 4
        _face(b, [r0[i], r0[j], r1[j], r1[i]], c, color)
    _face(b, r0, c, color)
    _face(b, r1, c, color)


def curve(b, pts, w0, w1, color, t0=None, t1=None, hint=(0, 1, 0)):
    """점들을 이어 붙인 굽은 막대 (폭이 w0 → w1 로 변함)."""
    n = len(pts) - 1
    for i in range(n):
        a, c = i / n, (i + 1) / n
        wa, wc = w0 + (w1 - w0) * a, w0 + (w1 - w0) * c
        ta = None if t0 is None else t0 + (t1 - t0) * a
        tc = None if t0 is None else t0 + (t1 - t0) * c
        bar(b, pts[i], pts[i + 1], wa, color, wc, ta, tc, hint)


def _legs(b, x, shoe, leg, shoe_size=(0.2, 0.16, 0.36), leg_w=0.17, leg_h=0.66):
    for s in (-1, 1):
        b.box((x * s, shoe_size[1] / 2, 0.06), shoe_size, shoe)
        b.box((x * s, 0.1 + leg_h / 2, 0.0), (leg_w, leg_h, leg_w * 1.1), leg, taper=1.12)


def _hand(b, p, color=SKIN, r=0.07):
    b.sphere(p, r, color, seg=8, rings=5)


def _head(b, y=1.66, skin=SKIN, r=0.18):
    b.cylinder((0, y - 0.24, 0), 0.07, 0.12, skin, seg=8)
    b.sphere((0, y, 0.01), r, skin, seg=12, rings=8)


# ------------------------------------------------------------------ 1. 바르고 — 강습의 선봉 (중갑 탱커)
def build_vanguard():
    b = MeshBuilder()
    cloth, leather = (0.62, 0.17, 0.15), (0.33, 0.22, 0.16)
    for s in (-1, 1):
        b.box((0.17 * s, 0.11, 0.07), (0.25, 0.22, 0.46), STEEL_D)                      # 철제 신발
        b.box((0.17 * s, 0.5, 0.0), (0.27, 0.6, 0.28), STEEL, taper=1.12)               # 다리갑옷
        b.sphere((0.17 * s, 0.8, 0.13), 0.12, GOLD, seg=8, rings=5, scale=(1, 0.9, 0.8))  # 무릎보호대
    b.cylinder((0, 0.72, 0), 0.38, 0.27, cloth, seg=10, radius_top=0.31)                  # 갑옷 치마
    for s in (-1, 1):
        b.box((0.2 * s, 0.76, 0.3), (0.2, 0.32, 0.05), STEEL_D, taper=0.8)
    b.box((0, 0.97, 0), (0.62, 0.12, 0.4), leather)
    b.box((0, 0.97, 0.21), (0.17, 0.15, 0.04), GOLD)
    b.box((0, 1.24, 0), (0.74, 0.56, 0.46), STEEL, taper=0.86)                           # 몸통
    b.box((0, 1.2, 0.236), (0.3, 0.44, 0.03), STEEL_L)
    b.octahedron((0, 1.27, 0.26), 0.1, 0.26, GOLD)                                        # 문장
    for s in (-1, 1):                                                                     # 어깨 방어구
        b.sphere((0.48 * s, 1.47, 0), 0.23, STEEL, seg=10, rings=6, scale=(1.15, 0.72, 1.15))
        b.cone((0.5 * s, 1.55, 0), 0.07, 0.2, GOLD, seg=6)
    bar(b, (-0.48, 1.4, 0.0), (-0.52, 0.98, 0.26), 0.2, STEEL_D, 0.17)
    bar(b, (0.48, 1.4, 0.0), (0.54, 1.0, 0.2), 0.2, STEEL_D, 0.17)
    _hand(b, (-0.52, 0.95, 0.28), STEEL, 0.12)
    _hand(b, (0.54, 0.98, 0.22), STEEL, 0.12)
    b.cylinder((0, 1.5, 0), 0.11, 0.13, STEEL_D, seg=8)                                   # 투구
    b.sphere((0, 1.73, 0.0), 0.21, STEEL, seg=12, rings=8, scale=(1.0, 1.05, 1.05))
    b.box((0, 1.7, 0.2), (0.3, 0.05, 0.04), (0.04, 0.04, 0.07))
    b.box((0, 1.64, 0.2), (0.05, 0.22, 0.04), STEEL_D)
    b.box((0, 1.94, -0.02), (0.07, 0.2, 0.46), cloth, taper=0.6)
    # 방패
    sh = MeshBuilder()
    sh.box((0, 0, 0), (0.66, 1.0, 0.1), STEEL_D, taper=0.9)
    sh.box((0, 0, 0.055), (0.52, 0.86, 0.03), STEEL)
    sh.box((0, 0, 0.075), (0.1, 0.9, 0.03), GOLD)
    sh.box((0, 0.1, 0.075), (0.55, 0.1, 0.03), GOLD)
    sh.sphere((0, 0.1, 0.1), 0.11, GOLD, seg=8, rings=5, scale=(1, 1, 0.6))
    b.extend(sh, offset=(-0.64, 1.0, 0.26), rot_y=-0.35)
    # 해머 (어깨에 걸침)
    bar(b, (0.54, 0.95, 0.2), (0.42, 1.85, -0.18), 0.09, leather)
    b.box((0.42, 1.95, -0.18), (0.6, 0.34, 0.34), STEEL_D)
    for s in (-1, 1):
        b.box((0.42 + 0.31 * s, 1.95, -0.18), (0.08, 0.42, 0.42), GOLD)
    return b


# ------------------------------------------------------------------ 2. 카론 — 낫의 사신
def build_reaper():
    b = MeshBuilder()
    robe, robe_l, trim = (0.22, 0.16, 0.34), (0.36, 0.26, 0.52), (0.58, 0.4, 0.78)
    bone, soul, wood = (0.92, 0.9, 0.82), (0.35, 1.0, 0.8), (0.3, 0.22, 0.17)
    b.cylinder((0, 0.1, 0), 0.44, 0.9, robe, seg=12, radius_top=0.25)
    for k in range(12):                                                                   # 찢어진 아랫단
        a = k / 12 * TAU
        b.octahedron((math.cos(a) * 0.42, 0.14, math.sin(a) * 0.42), 0.1, 0.2 + 0.09 * ((k * 5) % 3), robe)
    b.cylinder((0, 0.74, 0), 0.31, 0.07, trim, seg=10)
    b.sphere((0, 0.8, 0.29), 0.07, bone, seg=8, rings=5)                                  # 허리의 해골
    b.box((0, 1.25, 0), (0.5, 0.52, 0.3), robe_l, taper=0.85)
    b.box((0, 1.27, 0.152), (0.1, 0.5, 0.02), trim)
    b.cylinder((0, 1.4, 0), 0.27, 0.2, robe, seg=10, radius_top=0.2)                      # 높은 깃
    b.sphere((0, 1.7, -0.02), 0.23, robe, seg=12, rings=8, scale=(1, 1.08, 1.1))          # 후드
    bar(b, (0, 1.84, -0.1), (0, 1.6, -0.44), 0.3, robe, 0.02, 0.3, 0.02)
    b.sphere((0, 1.66, 0.1), 0.14, (0.02, 0.02, 0.04), seg=10, rings=6, scale=(1, 1.1, 0.8))
    for s in (-1, 1):
        b.sphere((0.06 * s, 1.68, 0.2), 0.03, soul, seg=6, rings=4)
    bar(b, (-0.3, 1.4, 0), (-0.38, 1.0, 0.28), 0.2, robe_l, 0.16)
    bar(b, (0.3, 1.4, 0), (0.45, 1.02, 0.28), 0.2, robe_l, 0.16)
    _hand(b, (-0.38, 0.98, 0.3), bone)
    _hand(b, (0.45, 1.0, 0.28), bone)
    # 낫
    bar(b, (0.45, 0.1, 0.35), (0.45, 2.0, 0.17), 0.06, wood)
    curve(b, [(0.45, 2.0, 0.17), (0.52, 2.02, 0.45), (0.5, 1.98, 0.72), (0.38, 1.92, 0.95), (0.2, 1.86, 1.08)],
          0.24, 0.01, STEEL_L, 0.04, 0.02)
    b.octahedron((0.45, 2.02, 0.15), 0.06, 0.16, trim)
    b.octahedron((-0.38, 1.2, 0.36), 0.08, 0.3, soul)                                      # 영혼 불꽃
    b.octahedron((-0.55, 1.45, 0.1), 0.05, 0.2, soul)
    return b


# ------------------------------------------------------------------ 3. 무진 — 범종의 수도승
def build_monk():
    b = MeshBuilder()
    saffron, maroon = (0.95, 0.6, 0.14), (0.55, 0.14, 0.12)
    bronze, bronze_d, wood = (0.74, 0.5, 0.2), (0.5, 0.32, 0.12), (0.45, 0.3, 0.18)
    bell_c, bell_d = (0.5, 0.36, 0.2), (0.78, 0.6, 0.25)
    for s in (-1, 1):
        b.box((0.14 * s, 0.05, 0.07), (0.19, 0.1, 0.34), wood)                            # 짚신
        b.box((0.14 * s, 0.14, 0.0), (0.15, 0.2, 0.16), SKIN_D)                           # 발목
    b.cylinder((0, 0.14, 0), 0.4, 0.64, saffron, seg=12, radius_top=0.27)                 # 승복 하의
    b.cylinder((0, 0.74, 0), 0.29, 0.11, maroon, seg=10)                                  # 허리띠
    b.box((0, 1.2, 0), (0.7, 0.62, 0.4), saffron, taper=0.82)                             # 상의
    bar(b, (0.34, 1.5, 0.12), (-0.3, 0.88, 0.2), 0.11, maroon, 0.11, 0.05)                 # 가사 띠
    b.sphere((0.36, 1.4, 0), 0.15, SKIN, seg=8, rings=5)                                  # 드러낸 오른쪽 어깨
    bar(b, (0.36, 1.38, 0), (0.5, 1.0, 0.3), 0.19, SKIN, 0.15)
    bar(b, (-0.36, 1.4, 0), (-0.5, 1.0, 0.3), 0.2, saffron, 0.17)
    _hand(b, (0.5, 0.97, 0.32), SKIN, 0.09)
    _hand(b, (-0.5, 0.97, 0.32), SKIN, 0.09)
    for k in range(11):                                                                    # 염주
        a = (k / 10 - 0.5) * 2.3
        b.sphere((math.sin(a) * 0.23, 1.38 - 0.12 * math.cos(a) * (1 - abs(k - 5) / 6) - 0.04, 0.12 + math.cos(a) * 0.1),
                 0.035, bronze_d, seg=6, rings=4)
    _head(b, 1.68, SKIN, 0.19)
    for s in (-1, 1):
        b.sphere((0.19 * s, 1.67, 0.0), 0.04, SKIN, seg=6, rings=4)                        # 귀
        b.box((0.07 * s, 1.7, 0.18), (0.08, 0.018, 0.02), (0.15, 0.1, 0.08))               # 감은 눈
        b.box((0.07 * s, 1.76, 0.17), (0.09, 0.02, 0.03), (0.2, 0.15, 0.1))               # 눈썹
    b.box((0, 1.6, 0.18), (0.07, 0.015, 0.02), (0.55, 0.3, 0.25))
    # 등에 멘 범종
    bell = MeshBuilder()
    bell.cylinder((0, -0.4, 0), 0.36, 0.66, bell_c, seg=12, radius_top=0.14)
    bell.sphere((0, 0.26, 0), 0.14, bell_c, seg=10, rings=6, scale=(1, 0.8, 1))
    bell.cylinder((0, -0.44, 0), 0.39, 0.07, bell_d, seg=12)
    bell.cylinder((0, -0.12, 0), 0.31, 0.05, bell_d, seg=12, radius_top=0.3)
    bell.cylinder((0, 0.1, 0), 0.22, 0.04, bell_d, seg=12, radius_top=0.21)
    bell.sphere((0, 0.4, 0), 0.07, bell_d, seg=6, rings=4)
    bell.sphere((0, -0.38, 0), 0.08, bell_d, seg=6, rings=4)
    b.extend(bell, offset=(0, 1.1, -0.5))
    for s in (-1, 1):
        bar(b, (0.27 * s, 1.46, 0.0), (0.1 * s, 1.5, -0.42), 0.07, maroon)
    # 당목(나무 망치)
    bar(b, (0.5, 0.92, 0.3), (0.5, 1.45, 0.45), 0.06, wood)
    b.box((0.5, 1.5, 0.47), (0.22, 0.2, 0.34), wood)
    b.box((0.5, 1.5, 0.37), (0.24, 0.22, 0.04), bronze)
    b.box((0.5, 1.5, 0.57), (0.24, 0.22, 0.04), bronze)
    return b


# ------------------------------------------------------------------ 4. 꼭두 — 외줄 광대
def build_acrobat():
    b = MeshBuilder()
    red, teal, cream = (0.86, 0.18, 0.26), (0.1, 0.66, 0.72), (0.97, 0.94, 0.86)
    rope, wood = (0.8, 0.65, 0.4), (0.45, 0.3, 0.18)
    for s, col, other in ((-1, red, teal), (1, teal, red)):
        b.box((0.13 * s, 0.07, 0.12), (0.17, 0.14, 0.5), other)                            # 뾰족한 신발
        b.octahedron((0.13 * s, 0.14, 0.4), 0.05, 0.18, GOLD)
        b.box((0.13 * s, 0.5, 0.0), (0.15, 0.7, 0.17), col, taper=1.1)
        for y in (0.3, 0.5, 0.7):
            b.box((0.13 * s, y, 0.0), (0.162, 0.06, 0.182), cream)                         # 다리 줄무늬
        b.box((0.14 * s, 1.15, 0), (0.27, 0.56, 0.28), col, taper=0.9)                     # 반반 옷
    b.box((0, 0.9, 0), (0.56, 0.07, 0.32), DARK)                                           # 허리띠
    b.box((0, 0.9, 0.17), (0.1, 0.1, 0.03), GOLD)
    for k in range(11):                                                                     # 주름 칼라
        a = k / 11 * TAU
        b.octahedron((math.cos(a) * 0.24, 1.43, math.sin(a) * 0.22), 0.07, 0.18, cream)
    # 가슴의 단검 띠
    bar(b, (-0.26, 0.98, 0.17), (0.26, 1.36, 0.17), 0.07, DARK, 0.07, 0.03)
    for k in range(5):
        t = k / 4
        px, py = -0.2 + 0.4 * t, 1.04 + 0.28 * t
        b.box((px, py + 0.07, 0.19), (0.03, 0.14, 0.02), STEEL_L)
        b.box((px, py - 0.03, 0.19), (0.04, 0.07, 0.025), GOLD)
    # 허리의 밧줄 묶음
    for j in range(3):
        b.ring((-0.36, 0.84 + j * 0.05, 0.0), 0.1 + 0.02 * j, 0.17 + 0.01 * j, rope, seg=14)
    # 팔 + 균형봉
    bar(b, (-0.34, 1.4, 0), (-0.4, 1.2, 0.23), 0.16, red, 0.13)
    bar(b, (0.34, 1.4, 0), (0.4, 1.2, 0.23), 0.16, teal, 0.13)
    _hand(b, (-0.4, 1.18, 0.24), cream, 0.075)
    _hand(b, (0.4, 1.18, 0.24), cream, 0.075)
    bar(b, (-0.85, 1.19, 0.24), (0.85, 1.19, 0.24), 0.05, wood)
    for s in (-1, 1):
        b.octahedron((0.88 * s, 1.19, 0.24), 0.07, 0.28, GOLD)
    # 얼굴
    b.cylinder((0, 1.42, 0), 0.07, 0.1, cream, seg=8)
    b.sphere((0, 1.64, 0.02), 0.19, (0.98, 0.94, 0.9), seg=12, rings=8)
    b.sphere((0, 1.62, 0.2), 0.05, red, seg=6, rings=4)                                    # 빨간 코
    for s in (-1, 1):
        b.sphere((0.07 * s, 1.68, 0.18), 0.026, DARK, seg=6, rings=4)
        b.octahedron((0.12 * s, 1.58, 0.17), 0.03, 0.09, teal if s < 0 else red)
    b.box((0, 1.55, 0.185), (0.14, 0.025, 0.02), red)                                       # 웃는 입
    # 광대 모자
    b.cylinder((0, 1.76, 0), 0.19, 0.09, GOLD, seg=12)
    curve(b, [(-0.08, 1.84, 0), (-0.26, 2.04, 0), (-0.46, 2.0, 0), (-0.6, 1.82, 0)], 0.17, 0.04, red)
    curve(b, [(0.08, 1.84, 0), (0.26, 2.04, 0), (0.46, 2.0, 0), (0.6, 1.82, 0)], 0.17, 0.04, teal)
    for s in (-1, 1):
        b.sphere((0.62 * s, 1.78, 0), 0.06, GOLD, seg=6, rings=4)
    return b


# ------------------------------------------------------------------ 5. 아린 — 숲의 사냥꾼
def build_hunter():
    b = MeshBuilder()
    green, green_d = (0.22, 0.42, 0.24), (0.14, 0.28, 0.17)
    leather, leather_d = (0.45, 0.3, 0.18), (0.3, 0.2, 0.13)
    cream, fur, pants = (0.92, 0.88, 0.74), (0.76, 0.73, 0.66), (0.52, 0.44, 0.31)
    for s in (-1, 1):
        b.box((0.13 * s, 0.1, 0.06), (0.19, 0.22, 0.36), leather_d)
        b.box((0.13 * s, 0.5, 0.0), (0.16, 0.6, 0.18), pants, taper=1.1)
        b.box((0.13 * s, 0.32, 0.0), (0.185, 0.2, 0.205), leather)                          # 정강이 가죽
    b.cylinder((0, 0.7, 0), 0.33, 0.24, green, seg=10, radius_top=0.27)
    b.box((0, 0.93, 0), (0.5, 0.08, 0.3), leather_d)
    b.box((0.3, 0.88, 0.04), (0.14, 0.18, 0.12), leather)                                   # 주머니
    b.ring((-0.3, 0.86, 0.1), 0.04, 0.1, STEEL, seg=10)                                     # 덫 고리
    b.box((0, 1.18, 0), (0.5, 0.5, 0.3), green, taper=0.9)
    bar(b, (-0.24, 1.42, 0.17), (0.24, 0.98, 0.17), 0.08, leather_d, 0.08, 0.03)
    # 망토 (등)
    b.box((0, 1.0, -0.2), (0.62, 0.9, 0.04), green_d, taper=0.75)
    for k in range(6):
        b.octahedron((-0.25 + 0.1 * k, 0.55, -0.2), 0.07, 0.2, green_d)
    # 어깨 털
    for k in range(9):
        a = k / 9 * TAU
        b.sphere((math.cos(a) * 0.27, 1.41, math.sin(a) * 0.2), 0.075, fur, seg=6, rings=4)
    # 팔
    bar(b, (-0.3, 1.38, 0), (-0.46, 1.1, 0.4), 0.15, green, 0.12)
    bar(b, (0.3, 1.38, 0), (0.28, 1.0, 0.3), 0.15, green, 0.12)
    _hand(b, (-0.46, 1.1, 0.42), leather, 0.07)
    _hand(b, (0.28, 0.98, 0.32), leather, 0.07)
    # 후드 + 얼굴
    b.cylinder((0, 1.42, 0), 0.07, 0.1, SKIN, seg=8)
    b.sphere((0, 1.65, 0.08), 0.16, SKIN, seg=10, rings=7)
    b.sphere((0, 1.72, -0.08), 0.21, green, seg=12, rings=8, scale=(1.0, 1.0, 1.0))
    b.box((0, 1.56, 0.15), (0.2, 0.08, 0.08), green_d)                                       # 복면 목도리
    for s in (-1, 1):
        b.sphere((0.06 * s, 1.68, 0.225), 0.025, (0.15, 0.4, 0.25), seg=6, rings=4)
    bar(b, (0, 1.86, -0.05), (0, 1.74, -0.4), 0.26, green, 0.02, 0.26, 0.02)
    bar(b, (0.14, 1.88, -0.02), (0.3, 2.08, -0.2), 0.04, cream, 0.01, 0.015, 0.01)           # 깃털
    # 화살통
    b.cylinder((0.14, 0.78, -0.3), 0.09, 0.6, leather, seg=8)
    for k in range(4):
        b.octahedron((0.1 + 0.035 * k, 1.44, -0.3), 0.03, 0.14, cream)
    bar(b, (0.1, 1.38, -0.28), (-0.25, 1.4, 0.15), 0.05, leather_d)
    # 활 (왼손)
    pts = []
    for k in range(11):
        t = (k / 10 - 0.5) * 2
        pts.append((-0.46, 1.1 + t * 0.66, 0.45 - 0.2 * (1 - t * t)))
    curve(b, pts, 0.05, 0.03, leather)
    bar(b, pts[0], pts[-1], 0.012, cream)
    # 쥐고 있는 화살
    bar(b, (0.28, 0.96, 0.32), (0.28, 1.45, 0.4), 0.025, cream)
    b.octahedron((0.28, 1.47, 0.4), 0.04, 0.12, STEEL_L)
    return b


# ------------------------------------------------------------------ 6. 엘리아 — 빛의 성직자
def build_cleric():
    b = MeshBuilder()
    white, blue = (0.97, 0.96, 0.94), (0.55, 0.72, 0.95)
    hair, wing_c, wing_s = (0.98, 0.88, 0.58), (0.99, 0.99, 1.0), (0.78, 0.87, 0.98)
    b.cylinder((0, 0.06, 0), 0.46, 0.95, white, seg=14, radius_top=0.24)
    b.cylinder((0, 0.06, 0), 0.47, 0.06, GOLD, seg=14)
    b.cylinder((0, 0.78, 0), 0.27, 0.09, blue, seg=12)
    b.box((0, 1.22, 0), (0.46, 0.5, 0.28), white, taper=0.85)
    b.box((0, 1.27, 0.15), (0.04, 0.22, 0.02), GOLD)                                         # 가슴의 십자 문양
    b.box((0, 1.3, 0.15), (0.14, 0.04, 0.02), GOLD)
    for s in (-1, 1):
        bar(b, (0.12 * s, 1.44, 0.14), (0.12 * s, 0.4, 0.3), 0.1, blue, 0.1, 0.02, 0.02, hint=(0, 0, 1))   # 영대
        b.sphere((0.28 * s, 1.42, 0), 0.12, white, seg=8, rings=5)
    bar(b, (-0.3, 1.4, 0), (-0.4, 1.05, 0.26), 0.19, white, 0.14)
    bar(b, (0.3, 1.4, 0), (0.46, 1.1, 0.24), 0.19, white, 0.14)
    _hand(b, (-0.4, 1.02, 0.28))
    _hand(b, (0.46, 1.08, 0.25))
    # 머리 + 긴 금발
    _head(b, 1.66, SKIN, 0.17)
    b.sphere((0, 1.7, -0.03), 0.185, hair, seg=12, rings=8, scale=(1.04, 0.95, 1.06))
    bar(b, (0, 1.62, -0.15), (0, 0.92, -0.2), 0.36, hair, 0.14, 0.1, 0.06)
    for s in (-1, 1):
        b.sphere((0.065 * s, 1.66, 0.155), 0.026, (0.25, 0.5, 0.85), seg=6, rings=4)
    # 후광
    b.ring((0, 2.02, -0.02), 0.19, 0.27, GOLD, seg=24)
    b.ring((0, 2.015, -0.02), 0.19, 0.27, GOLD, seg=24)
    # 날개
    lens = [0.7, 0.88, 0.95, 0.9, 0.78, 0.6]
    for s in (-1, 1):
        root = (0.1 * s, 1.34, -0.2)
        for k in range(6):
            ang = math.radians(8 + k * 19)
            L = lens[k]
            end = (root[0] + s * math.sin(ang) * L, root[1] + math.cos(ang) * L, -0.34 - 0.03 * k)
            bar(b, root, end, 0.2, wing_c, 0.11, 0.03, 0.02, hint=(0, 0, 1))
            mid = (root[0] + (end[0] - root[0]) * 0.55, root[1] + (end[1] - root[1]) * 0.55, -0.27)
            bar(b, root, mid, 0.22, wing_s, 0.13, 0.035, 0.025, hint=(0, 0, 1))
    # 지팡이 (끝에 태양)
    bar(b, (0.47, 0.02, 0.26), (0.47, 1.92, 0.22), 0.06, (0.85, 0.75, 0.5))
    c = (0.47, 2.12, 0.22)
    b.sphere(c, 0.1, blue, seg=8, rings=5)
    for k in range(8):
        a = k / 8 * TAU
        bar(b, c, (c[0] + math.cos(a) * 0.3, c[1] + math.sin(a) * 0.3, c[2]), 0.05, GOLD, 0.01, 0.04, 0.01,
            hint=(0, 0, 1))
    return b


# ------------------------------------------------------------------ 7. 로웬 — 숲의 계약자
def build_druid():
    b = MeshBuilder()
    moss, moss_d = (0.34, 0.5, 0.22), (0.2, 0.34, 0.15)
    bark, bark_d = (0.42, 0.29, 0.18), (0.28, 0.19, 0.12)
    cream, petal, petal2 = (0.93, 0.9, 0.78), (1.0, 0.6, 0.72), (1.0, 0.86, 0.4)
    leaf, leaf_d, hair = (0.42, 0.72, 0.3), (0.24, 0.5, 0.22), (0.5, 0.36, 0.22)
    for s in (-1, 1):
        b.box((0.13 * s, 0.07, 0.07), (0.19, 0.14, 0.34), cream)                            # 발 감개
        b.box((0.13 * s, 0.46, 0.0), (0.16, 0.68, 0.18), bark, taper=1.1)
        for y in (0.3, 0.52):
            b.box((0.13 * s, y, 0.0), (0.18, 0.06, 0.2), moss)                              # 덩굴 감개
    for k in range(11):                                                                     # 잎사귀 치마
        a = k / 11 * TAU
        b.octahedron((math.cos(a) * 0.3, 0.7, math.sin(a) * 0.3), 0.1, 0.46, leaf if k % 2 else leaf_d)
    b.box((0, 1.18, 0), (0.5, 0.52, 0.3), moss, taper=0.88)
    b.cylinder((0, 0.88, 0), 0.26, 0.08, bark_d, seg=10)
    for k in range(5):                                                                      # 허리의 꽃
        a = k / 5 * TAU
        b.octahedron((math.cos(a) * 0.07, 0.92, 0.27 + math.sin(a) * 0.07), 0.04, 0.12, petal)
    # 잎 망토
    for row in range(4):
        for col in range(-2, 3):
            if row == 3 and abs(col) > 1:
                continue
            b.octahedron((col * 0.17, 1.46 - row * 0.24, -0.2 - row * 0.02), 0.1, 0.36, leaf if (row + col) % 2 else leaf_d)
    for s in (-1, 1):
        b.sphere((0.3 * s, 1.42, 0), 0.14, moss_d, seg=8, rings=5, scale=(1.1, 0.8, 1.1))
        b.octahedron((0.38 * s, 1.5, 0), 0.07, 0.3, leaf)
    bar(b, (-0.3, 1.4, 0), (-0.44, 1.08, 0.26), 0.16, moss, 0.12)
    bar(b, (0.3, 1.4, 0), (0.42, 1.08, 0.26), 0.16, moss, 0.12)
    _hand(b, (-0.45, 1.06, 0.28))
    _hand(b, (0.42, 1.06, 0.28))
    # 머리 + 머리카락 + 뿔
    _head(b, 1.66, SKIN, 0.17)
    b.sphere((0, 1.71, -0.03), 0.19, hair, seg=12, rings=8, scale=(1.05, 0.95, 1.08))
    bar(b, (0, 1.62, -0.14), (0, 1.0, -0.2), 0.32, hair, 0.12, 0.1, 0.06)
    for s in (-1, 1):
        b.sphere((0.065 * s, 1.66, 0.155), 0.026, (0.2, 0.55, 0.3), seg=6, rings=4)
        curve(b, [(0.1 * s, 1.82, 0), (0.2 * s, 2.0, -0.04), (0.33 * s, 2.12, -0.04), (0.42 * s, 2.28, 0)],
              0.055, 0.02, bark_d)
        curve(b, [(0.2 * s, 2.0, -0.04), (0.14 * s, 2.18, 0.0)], 0.04, 0.015, bark_d)
        curve(b, [(0.33 * s, 2.12, -0.04), (0.5 * s, 2.18, -0.06)], 0.04, 0.015, bark_d)
        b.octahedron((0.2 * s, 2.0, -0.04), 0.045, 0.12, petal)
        b.octahedron((0.42 * s, 2.28, 0), 0.04, 0.1, petal2)
    # 꽃 지팡이
    curve(b, [(-0.46, 0.0, 0.26), (-0.44, 0.7, 0.27), (-0.5, 1.4, 0.24), (-0.48, 1.85, 0.22)], 0.08, 0.06, bark)
    c = (-0.48, 1.95, 0.22)
    b.sphere(c, 0.1, petal2, seg=8, rings=5)
    for k in range(7):
        a = k / 7 * TAU
        b.octahedron((c[0] + math.cos(a) * 0.17, c[1] + 0.03, c[2] + math.sin(a) * 0.17), 0.09, 0.3,
                     petal if k % 2 else _mix(petal, (1, 1, 1), 0.4))
    b.octahedron((c[0], c[1] + 0.3, c[2]), 0.07, 0.18, (0.55, 1.0, 0.55))
    return b


CHAMPION_BUILDERS = {
    "vanguard": build_vanguard, "reaper": build_reaper, "monk": build_monk, "acrobat": build_acrobat,
    "hunter": build_hunter, "cleric": build_cleric, "druid": build_druid,
}


# ------------------------------------------------------------------ 스킬 투사체 (앞쪽이 +Z)
def build_knife():
    b = MeshBuilder()
    bar(b, (0, 0, -0.08), (0, 0, 0.4), 0.1, STEEL_L, 0.01, 0.03, 0.015)
    b.box((0, 0, -0.1), (0.2, 0.04, 0.05), GOLD)
    b.box((0, 0, -0.22), (0.045, 0.045, 0.2), (0.25, 0.15, 0.2))
    b.sphere((0, 0, -0.34), 0.04, GOLD, seg=6, rings=4)
    return b


def build_knife_fast():
    b = build_knife()
    bar(b, (0, 0, -0.9), (0, 0, -0.34), 0.01, (0.85, 0.9, 1.0), 0.07, 0.01, 0.02)
    return b


def build_hook():
    b = MeshBuilder()
    rope = (0.82, 0.68, 0.42)
    bar(b, (0, 0, -1.4), (0, 0, -0.1), 0.045, rope)
    b.sphere((0, 0, -0.05), 0.09, STEEL, seg=8, rings=5)
    for dx, dy in ((0.2, 0.0), (-0.2, 0.0), (0.0, 0.2)):
        curve(b, [(0, 0, -0.05), (dx * 0.8, dy * 0.8, 0.1), (dx, dy, 0.3)], 0.06, 0.012, STEEL_L)
    return b


def build_chain():
    b = MeshBuilder()
    link, soul = (0.55, 0.45, 0.8), (0.4, 1.0, 0.85)
    bar(b, (0, 0, -1.0), (0, 0, 0.0), 0.04, link)
    for k in range(7):
        z = -0.95 + k * 0.15
        b.octahedron((0, 0, z), 0.09 if k % 2 else 0.05, 0.1, link, seg=4)
    b.octahedron((0, 0, 0.12), 0.2, 0.34, soul, seg=6)
    return b


def build_giant_arrow():
    b = MeshBuilder()
    wood, cream = (0.82, 0.66, 0.38), (0.98, 0.96, 0.9)
    bar(b, (0, 0, -1.7), (0, 0, 0.6), 0.1, wood)
    bar(b, (0, 0, 0.55), (0, 0, 1.3), 0.4, (1.0, 0.92, 0.6), 0.01, 0.4, 0.01)
    b.box((0, 0, -1.45), (0.03, 0.5, 0.6), cream)
    b.box((0, 0, -1.45), (0.5, 0.03, 0.6), cream)
    bar(b, (0, 0, -3.6), (0, 0, -1.7), 0.01, (1.0, 0.95, 0.7), 0.16, 0.01, 0.04)
    return b


def build_light_bolt():
    b = MeshBuilder()
    gold, white = (1.0, 0.88, 0.45), (1.0, 0.98, 0.85)
    b.sphere((0, 0, 0), 0.15, white, seg=8, rings=6)
    b.octahedron((0, 0, 0), 0.07, 0.6, gold, seg=4)
    bar(b, (0, 0, -0.55), (0, 0, -0.05), 0.01, gold, 0.14, 0.01, 0.1)
    return b


def build_tornado_layer(i, n=9, seg=12):
    """보스러시 용의 회오리 한 겹: 위로 갈수록 넓어지는 속 빈 원뿔대. 겹마다 반지름이 0.5 씩 커지고, 줄무늬가 있어 돌면 소용돌이로 보인다."""
    b = MeshBuilder()
    r0, r1 = 0.7 + i * 0.5, 0.7 + (i + 1) * 0.5
    for j in range(seg):
        a0, a1 = j / seg * math.tau, (j + 1) / seg * math.tau
        c = (1.0, 1.0, 1.0) if j % 2 else (0.62, 0.62, 0.62)
        p = lambda r, a, y: (math.cos(a) * r, y, math.sin(a) * r)
        b.quad(p(r0, a0, 0.0), p(r0, a1, 0.0), p(r1, a1, 1.0), p(r1, a0, 1.0), c)
    return b


def build_leaf_bolt():
    b = MeshBuilder()
    leaf, vein = (0.45, 0.85, 0.35), (0.7, 1.0, 0.55)
    bar(b, (0, 0, -0.3), (0, 0, 0.35), 0.24, leaf, 0.01, 0.025, 0.01)
    bar(b, (0, 0.02, -0.3), (0, 0.02, 0.3), 0.025, vein, 0.01, 0.02, 0.01)
    b.sphere((0, 0, -0.32), 0.04, vein, seg=6, rings=4)
    return b


# ------------------------------------------------------------------ 장치·이펙트 메시
def build_anchor():
    """아크로뱃의 줄 말뚝: 땅에 박힌 나무 말뚝 + 감긴 밧줄 + 작은 깃발."""
    b = MeshBuilder()
    wood, rope = (0.45, 0.3, 0.18), (0.82, 0.68, 0.42)
    b.cylinder((0, 0, 0), 0.13, 0.78, wood, seg=8, radius_top=0.09)
    b.cylinder((0, 0.74, 0), 0.115, 0.07, STEEL_D, seg=8)
    for j in range(3):
        b.ring((0, 0.2 + j * 0.07, 0), 0.11, 0.16, rope, seg=12)
    b.ring((0, 0.03, 0), 0.3, 0.37, rope, seg=16)
    b.box((0.15, 0.7, 0), (0.28, 0.2, 0.02), (0.1, 0.66, 0.72), taper=0.7)
    return b


def build_cocoon():
    """거미 여왕의 새끼 거미 고치: 누런 비단으로 감싼 알 + 바닥에 퍼진 거미줄."""
    b = MeshBuilder()
    silk, band = (0.93, 0.86, 0.68), (0.78, 0.68, 0.48)
    b.sphere((0, 0.5, 0), 0.5, silk, seg=12, rings=8, scale=(0.85, 1.15, 0.85))
    for j, y in enumerate((0.3, 0.5, 0.7)):
        w = (0.43, 0.46, 0.4)[j]
        b.ring((0, y, 0), w - 0.03, w + 0.03, band, seg=14)
    b.ring((0, 0.03, 0), 0.3, 0.62, (0.85, 0.82, 0.74), seg=16)
    return b


def build_trap():
    """사냥꾼의 덫: 쇠 이빨이 달린 둥근 덫."""
    b = MeshBuilder()
    metal, dark = (0.6, 0.62, 0.68), (0.28, 0.3, 0.36)
    b.disc((0, 0.04, 0), 0.26, dark, seg=14)
    b.ring((0, 0.06, 0), 0.24, 0.4, metal, seg=18)
    for k in range(10):
        a = k / 10 * TAU
        b.cone((math.cos(a) * 0.32, 0.06, math.sin(a) * 0.32), 0.05, 0.22, STEEL_L, seg=5)
    b.box((0, 0.08, 0), (0.2, 0.05, 0.2), (0.7, 0.2, 0.15))
    return b


def build_bell():
    """무진의 대종: 밑지름 1 인 종 (원점이 바닥 가운데). scale 로 크기를 맞춘다."""
    b = MeshBuilder()
    bronze, bronze_d = (0.74, 0.5, 0.2), (0.5, 0.32, 0.12)
    b.cylinder((0, 0.05, 0), 1.0, 1.25, bronze, seg=20, radius_top=0.36)
    b.sphere((0, 1.3, 0), 0.36, bronze, seg=14, rings=8, scale=(1, 0.8, 1))
    b.cylinder((0, 0.0, 0), 1.08, 0.12, bronze_d, seg=20)
    for y, r in ((0.45, 0.86), (0.85, 0.66)):
        b.cylinder((0, y, 0), r + 0.02, 0.1, bronze_d, seg=20, radius_top=r)
    b.cylinder((0, 1.5, 0), 0.12, 0.3, bronze_d, seg=8)
    b.sphere((0, 1.85, 0), 0.2, bronze_d, seg=8, rings=5)
    return b
