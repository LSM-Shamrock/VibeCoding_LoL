"""챔피언 / 아이템 데이터 로더 (서버·클라이언트 공용)."""
import glob
import json
import os

from .constants import DATA_DIR

_champions = None
_items = None
_world_models = None


def all_champions():
    """{champion_id: data} — data/champions/*.json 을 모두 읽는다 (숨김 챔피언 포함)."""
    global _champions
    if _champions is None:
        _champions = {}
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "champions", "*.json"))):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _champions[data["id"]] = data
    return _champions


def champions():
    """선택 화면·봇이 고를 수 있는 챔피언. 데이터에 "hidden": true 가 있으면 코드는 남겨 두고 목록에서만 뺀다."""
    return {cid: d for cid, d in all_champions().items() if not d.get("hidden")}


def champion(cid):
    """챔피언 데이터 (숨김 챔피언도 id 로는 찾을 수 있다)."""
    return all_champions().get(cid)


def default_champion_id():
    return next(iter(champions()))


def items():
    """{item_id: data} — 입력 순서를 유지한다."""
    global _items
    if _items is None:
        with open(os.path.join(DATA_DIR, "items.json"), encoding="utf-8") as f:
            _items = {it["id"]: it for it in json.load(f)}
    return _items


def world_models():
    global _world_models
    if _world_models is None:
        path = os.path.join(DATA_DIR, "world_models.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _world_models = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
        else:
            _world_models = {}
    return _world_models


# ---------------------------------------------------------------- 스킬 데이터 도우미
def rank_value(ab, key, rank, default=0.0):
    """스킬 값: 리스트면 스킬 레벨(rank, 1부터)에 맞는 값, 아니면 그대로."""
    v = ab.get(key, default)
    if isinstance(v, (list, tuple)):
        if not v:
            return default
        return v[max(0, min(len(v) - 1, rank - 1))]
    return v


# 스킬 type 별 조준 방식 (클라이언트의 조준 표시·즉시 시전 여부와 봇 판단에 쓴다)
#   line     방향 지정 (직선)        cone     방향 지정 (부채꼴)
#   ground   바닥 지점 지정          teleport 먼 거리 지점 지정 (미니맵 클릭 가능)
#   ally     아군 지정 (마우스에서 가장 가까운 아군)
#   circle   누르고 있으면 자기 둘레 범위(radius)를 보여 주고, 떼면 시전 (자기 중심 광역)
#   self     누르면 바로 시전
AIM_BY_TYPE = {
    "skillshot": "line", "hook_dash": "line", "line_aoe": "line", "knife_throw": "line",
    "dash": "line", "knockback": "line", "rope_walk": "line",
    "cone": "cone", "volley": "cone",
    "ground_aoe": "ground", "zone": "ground", "cage": "ground", "trap": "ground", "cocoon": "ground", "leap_slam": "ground",
    "spit_pool": "ground", "lunge": "line", "serpent_slam": "ground", "dive": "teleport",
    "tornado": "cone", "wing_sweep": "circle", "sky_dive": "ground",
    "teleport_strike": "teleport",
    "ally_heal": "ally", "ally_shield": "ally", "ally_buff": "ally", "cleanse": "ally",
    "self_buff": "self", "self_aoe": "self", "counter_shield": "self", "lifesteal_buff": "self",
    "ghost_walk": "self", "echo_guard": "self", "silence_marked": "self", "anchor": "self",
    "team_heal": "self",
}


def aim_mode(ab):
    return ab.get("aim") or AIM_BY_TYPE.get(ab.get("type"), "line")


def is_instant(ab):
    """키를 누르자마자 시전되는 스킬인가 (조준 불필요)."""
    return aim_mode(ab) == "self"
