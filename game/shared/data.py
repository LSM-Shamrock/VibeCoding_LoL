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


def buy_plan(owned, iid):
    """롤식 아이템 트리: iid(2단계)를 살 때 가진 하위 아이템(from)을 재료로 써서 값을 깎는다.
    반환: (재료로 쓰이는 아이템 id 목록, 지불할 가격). 1단계 아이템은 재료 없이 정가."""
    its = items()
    item = its[iid]
    left = list(owned)
    used = []
    price = item["cost"]
    for comp in item.get("from", []):
        if comp in left:
            left.remove(comp)
            used.append(comp)
            price -= its[comp]["cost"]
    return used, price


def is_boots(iid):
    """신발류(기본 신발 + 그 상위 신발)인가. 신발은 하나만 살 수 있고 인벤토리와 따로 한 칸을 쓴다."""
    return bool(items().get(iid, {}).get("boots"))


def regular_count(owned):
    """신발을 뺀 일반 아이템 개수 (인벤토리 8칸을 차지하는 것)."""
    return sum(1 for i in owned if not is_boots(i))


def can_buy(owned, iid, slots):
    """(살 수 있는가, 재료 목록, 가격, 이유). 신발은 이미 하나 가졌으면 그 신발을 재료로 쓰는 상위 신발만 살 수 있다.
    일반 아이템은 재료로 빠지는 것을 빼고 slots 칸이 남아 있어야 한다."""
    if iid not in items():
        return False, [], 0, "없는 아이템"
    used, price = buy_plan(owned, iid)
    if is_boots(iid):
        have = [i for i in owned if is_boots(i)]
        if have and not any(b in used for b in have):
            return False, used, price, "신발은 하나만 살 수 있습니다"
    else:
        if regular_count(owned) - sum(1 for u in used if not is_boots(u)) >= slots:
            return False, used, price, "인벤토리가 가득 찼습니다"
    return True, used, price, ""


def upgrades_of(iid):
    """iid 를 재료로 쓰는 2단계 아이템 id 목록."""
    return [i for i, it in items().items() if iid in it.get("from", [])]


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
