"""소환사 주문 목록. 서버(효과 계산)와 클라이언트(이름·설명·아이콘)가 함께 쓴다.

선택 화면에서 두 개를 골라 D / F 칸에 넣는다 (같은 주문을 두 칸에 넣을 수는 없다).
효과 구현은 game/server/sim.py 의 cast_spell, 숫자는 game/shared/constants.py 에 있다.
아이콘은 assets/ui/spells/<id>.png.

aim (조준 방식): "ground" 바닥 지점 / "self" 바로 발동 / "enemy" 마우스에 가장 가까운 적 챔피언
"""
from .constants import (
    BARRIER_BASE, BARRIER_COOLDOWN, BARRIER_PER_LEVEL, BARRIER_TIME, CLEANSE_COOLDOWN, CLEANSE_IMMUNE,
    EXHAUST_COOLDOWN, EXHAUST_DMG_REDUCE, EXHAUST_RANGE, EXHAUST_SLOW, EXHAUST_TIME, FLASH_COOLDOWN, FLASH_RANGE,
    GHOST_COOLDOWN, GHOST_SPEED_PCT, GHOST_TIME, HEAL_ALLY_RATIO, HEAL_BASE, HEAL_COOLDOWN, HEAL_PER_LEVEL,
    HEAL_RANGE, HEAL_SPEED_PCT, HEAL_SPEED_TIME, IGNITE_BASE, IGNITE_COOLDOWN, IGNITE_HEAL_CUT, IGNITE_PER_LEVEL,
    IGNITE_RANGE, IGNITE_TIME, MARK_COOLDOWN, MARK_RANGE, MARK_RECAST_TIME)

SPELL_ORDER = ["flash", "mark", "heal", "ghost", "barrier", "cleanse", "exhaust", "ignite"]
DEFAULT_SPELLS = ["flash", "mark"]


def _cd(v):
    return ("재사용 대기시간", f"{v:g}초")


SPELLS = {
    "flash": {
        "name": "점멸", "color": (235, 200, 70), "aim": "ground", "cooldown": FLASH_COOLDOWN, "range": FLASH_RANGE,
        "desc": "마우스 방향으로 짧은 거리를 순간이동합니다. 벽 너머로도 이동할 수 있습니다.",
        "details": [("사거리", f"{FLASH_RANGE * 100:g}"), _cd(FLASH_COOLDOWN)]},
    "mark": {
        "name": "표식", "color": (110, 190, 245), "aim": "ground", "cooldown": MARK_COOLDOWN, "range": MARK_RANGE,
        "desc": "눈덩이를 던져 처음 맞은 적에게 피해를 주고 표식을 남깁니다. 표식이 남아 있는 동안 한 번 더 누르면 그 적에게 돌진합니다.",
        "details": [("피해량", "10 + 레벨 × 5 (고정)"), ("사거리", f"{MARK_RANGE * 100:g}"),
                    ("돌진 가능 시간", f"{MARK_RECAST_TIME:g}초"), _cd(MARK_COOLDOWN)]},
    "heal": {
        "name": "회복", "color": (90, 210, 120), "aim": "self", "cooldown": HEAL_COOLDOWN, "radius": HEAL_RANGE,
        "desc": "체력을 회복하고, 근처에서 체력이 가장 낮은 아군 챔피언도 함께 회복시킵니다. 잠깐 동안 이동 속도가 증가합니다.",
        "details": [("회복량", f"{HEAL_BASE:g} + 레벨 × {HEAL_PER_LEVEL:g}"),
                    ("아군 회복량", f"{HEAL_ALLY_RATIO * 100:g}%"), ("아군 범위", f"{HEAL_RANGE * 100:g}"),
                    ("이동 속도", f"+{HEAL_SPEED_PCT * 100:g}% ({HEAL_SPEED_TIME:g}초)"), _cd(HEAL_COOLDOWN)]},
    "ghost": {
        "name": "유체화", "color": (150, 170, 230), "aim": "self", "cooldown": GHOST_COOLDOWN,
        "desc": "일정 시간 동안 이동 속도가 크게 증가합니다. 추격하거나 도망칠 때 씁니다.",
        "details": [("이동 속도", f"+{GHOST_SPEED_PCT * 100:g}%"), ("지속 시간", f"{GHOST_TIME:g}초"),
                    _cd(GHOST_COOLDOWN)]},
    "barrier": {
        "name": "방어막", "color": (225, 170, 70), "aim": "self", "cooldown": BARRIER_COOLDOWN,
        "desc": "잠시 동안 피해를 대신 받아 주는 보호막을 두릅니다.",
        "details": [("보호막", f"{BARRIER_BASE:g} + 레벨 × {BARRIER_PER_LEVEL:g}"),
                    ("지속 시간", f"{BARRIER_TIME:g}초"), _cd(BARRIER_COOLDOWN)]},
    "cleanse": {
        "name": "정화", "color": (90, 215, 220), "aim": "self", "cooldown": CLEANSE_COOLDOWN,
        "desc": "기절·속박·침묵·둔화·공중 띄움 같은 군중 제어를 모두 풀고, 짧게 군중 제어에 면역이 됩니다. 제어당한 중에도 쓸 수 있습니다.",
        "details": [("면역 시간", f"{CLEANSE_IMMUNE:g}초"), _cd(CLEANSE_COOLDOWN)]},
    "exhaust": {
        "name": "탈진", "color": (170, 120, 220), "aim": "enemy", "cooldown": EXHAUST_COOLDOWN,
        "range": EXHAUST_RANGE,
        "desc": "마우스에 가장 가까운 적 챔피언을 지치게 만들어 이동 속도를 늦추고, 그 적이 주는 피해를 줄입니다.",
        "details": [("사거리", f"{EXHAUST_RANGE * 100:g}"), ("이동 속도", f"-{EXHAUST_SLOW * 100:g}%"),
                    ("주는 피해", f"-{EXHAUST_DMG_REDUCE * 100:g}%"), ("지속 시간", f"{EXHAUST_TIME:g}초"),
                    _cd(EXHAUST_COOLDOWN)]},
    "ignite": {
        "name": "점화", "color": (240, 110, 70), "aim": "enemy", "cooldown": IGNITE_COOLDOWN, "range": IGNITE_RANGE,
        "desc": "마우스에 가장 가까운 적 챔피언을 불태워 지속 시간 동안 고정 피해를 주고, 그 적이 받는 회복량을 줄입니다.",
        "details": [("총 피해량", f"{IGNITE_BASE:g} + 레벨 × {IGNITE_PER_LEVEL:g} (고정)"),
                    ("사거리", f"{IGNITE_RANGE * 100:g}"), ("지속 시간", f"{IGNITE_TIME:g}초"),
                    ("회복 감소", f"-{IGNITE_HEAL_CUT * 100:g}%"), _cd(IGNITE_COOLDOWN)]},
}


def valid_pair(spells):
    """[D 칸 주문, F 칸 주문] 이 올바른 선택인가 (알려진 주문 두 개, 서로 달라야 함)."""
    return (isinstance(spells, (list, tuple)) and len(spells) == 2 and all(s in SPELLS for s in spells)
            and spells[0] != spells[1])
