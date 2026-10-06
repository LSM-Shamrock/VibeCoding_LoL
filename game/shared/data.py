"""챔피언 / 아이템 데이터 로더 (서버·클라이언트 공용)."""
import glob
import json
import os

from .constants import DATA_DIR

_champions = None
_items = None
_world_models = None


def champions():
    """{champion_id: data} — data/champions/*.json 을 모두 읽는다."""
    global _champions
    if _champions is None:
        _champions = {}
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "champions", "*.json"))):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _champions[data["id"]] = data
    return _champions


def champion(cid):
    return champions().get(cid)


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
