"""서버와 클라이언트가 함께 쓰는 상수."""
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT_DIR, "data")
ASSET_DIR = os.path.join(ROOT_DIR, "assets")

DEFAULT_PORT = 5555

TICK_RATE = 30            # 서버 시뮬레이션 틱 (Hz)
SNAPSHOT_EVERY = 2        # N틱마다 스냅샷 전송 (15Hz)

BLUE, RED = 0, 1
TEAM_NAMES = {BLUE: "블루팀", RED: "레드팀"}

MAX_TEAM_SIZE = 5
SELECT_TIME = 40.0        # 챔피언 선택 제한 시간 (초)

# ---- 칼바람 규칙 ----
START_LEVEL = 3
MAX_LEVEL = 18
START_GOLD = 1400
PASSIVE_GOLD_PER_SEC = 3.0
PASSIVE_XP_PER_SEC = 2.5
KILL_GOLD = 300
FIRST_BLOOD_BONUS = 100
ASSIST_GOLD_TOTAL = 150
ASSIST_WINDOW = 10.0      # 이 시간 안에 피해를 준 아군이 어시스트
XP_SHARE_RANGE = 16.0

FIRST_WAVE_TIME = 20.0
WAVE_INTERVAL = 30.0
INHIBITOR_RESPAWN = 300.0

FOUNTAIN_RADIUS = 7.5     # 상점 이용 가능 범위
FOUNTAIN_LASER_RADIUS = 9.0
FOUNTAIN_LASER_DPS = 1200.0

RELIC_FIRST_SPAWN = 60.0
RELIC_RESPAWN = 40.0
RELIC_HEAL_PCT = 0.15
RELIC_RADIUS = 1.0

INVENTORY_SLOTS = 6
SELL_RATIO = 0.7

FLASH_RANGE = 4.0
FLASH_COOLDOWN = 240.0
MARK_RANGE = 16.0
MARK_SPEED = 25.0
MARK_COOLDOWN = 40.0
MARK_RECAST_TIME = 3.0
MARK_DASH_SPEED = 24.0


def xp_to_next(level):
    """level -> level+1 에 필요한 경험치."""
    return 180 + 100 * level


def death_timer(level):
    return 4.0 + level * 1.6
