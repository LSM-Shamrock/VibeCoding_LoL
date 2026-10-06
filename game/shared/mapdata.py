"""칼바람 나락(모티브) 맵 정의.

좌표계: x축이 라인 방향(블루팀 -x, 레드팀 +x), z축이 라인 폭 방향, y는 높이.
1 유닛 ≈ 롤의 100 유닛.
"""
import math

from .constants import BLUE, RED

LANE_END = 64.0          # 맵 끝 (x 절댓값)
LANE_HALF_WIDTH = 7.5    # 라인 구간 절반 폭
BASE_HALF_WIDTH = 11.5   # 본진 구간 절반 폭
BASE_START = 40.0        # |x| 가 이 이상이면 본진 구간으로 넓어짐
BASE_BLEND = 6.0

FOUNTAIN_X = 60.0


def team_dir(team):
    """해당 팀이 공격해 나가는 x 방향."""
    return 1.0 if team == BLUE else -1.0


def fountain_pos(team):
    return (-FOUNTAIN_X if team == BLUE else FOUNTAIN_X, 0.0)


def half_width(x):
    ax = abs(x)
    t = (ax - BASE_START) / BASE_BLEND
    t = max(0.0, min(1.0, t))
    t = t * t * (3 - 2 * t)
    return LANE_HALF_WIDTH + (BASE_HALF_WIDTH - LANE_HALF_WIDTH) * t


def clamp_to_map(x, z, radius=0.0):
    x = max(-LANE_END + radius, min(LANE_END - radius, x))
    hw = half_width(x) - radius
    z = max(-hw, min(hw, z))
    return x, z


# 구조물: (key, kind, x(블루 기준, 음수), z, max_hp, radius, 선행조건 key 목록)
# 선행조건 구조물이 모두 파괴되어야 피해를 받을 수 있다.
_STRUCTURE_LAYOUT = [
    ("outer", "turret", -22.0, 0.0, 4000, 1.1, []),
    ("inner", "turret", -34.0, 0.0, 3600, 1.1, ["outer"]),
    ("inhib", "inhibitor", -41.0, 0.0, 4000, 1.6, ["inner"]),
    ("nexus_t1", "turret", -47.0, -2.6, 2700, 1.0, ["inhib"]),
    ("nexus_t2", "turret", -47.0, 2.6, 2700, 1.0, ["inhib"]),
    ("nexus", "nexus", -51.0, 0.0, 5500, 2.4, ["nexus_t1", "nexus_t2"]),
]


def structure_layout():
    """양 팀의 구조물 목록을 돌려준다."""
    out = []
    for team in (BLUE, RED):
        sign = 1.0 if team == BLUE else -1.0
        for key, kind, x, z, hp, r, req in _STRUCTURE_LAYOUT:
            out.append({
                "key": key, "kind": kind, "team": team,
                "x": x * sign, "z": z, "hp": hp, "radius": r, "requires": list(req),
            })
    return out


RELIC_POSITIONS = [(-27.0, 5.0), (-13.0, -5.0), (13.0, 5.0), (27.0, -5.0)]

TURRET_RANGE = 7.75


def spawn_points(team, count):
    fx, fz = fountain_pos(team)
    pts = []
    for i in range(count):
        ang = (i / max(1, count)) * math.tau + 0.3
        pts.append((fx + math.cos(ang) * 2.2, fz + math.sin(ang) * 2.2))
    return pts


def minion_spawn(team):
    return (-45.5 if team == BLUE else 45.5, 0.0)
