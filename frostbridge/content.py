"""Shared, data-driven content. The server is authoritative for these values."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_catalog(filename):
    entries = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in entries}


CHAMPIONS = load_catalog("champions.json")
ITEMS = load_catalog("items.json")
PORT = 27355
TICK_RATE = 30
SNAPSHOT_RATE = 10
MAP_X = 59.0
MAP_Z = 7.4
SPAWN_X = 55.0
WAVE_INTERVAL = 20.0
INHIBITOR_RESPAWN = 180.0
RELIC_RESPAWN = 45.0


def asset_path(relative):
    """Only local files below assets/ are accepted by the renderer."""
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / "assets").resolve()):
        raise ValueError("Asset paths must stay inside assets/")
    return path
