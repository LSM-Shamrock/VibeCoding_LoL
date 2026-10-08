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
FOUNTAIN_HEAL_PCT = 0.085 # 우물 안 초당 체력/마나 회복 (최대치 비율, 협곡 우물처럼)
RECALL_TIME = 8.0         # 귀환 정신집중 시간 (초)
FOUNTAIN_LASER_RADIUS = 9.0
FOUNTAIN_LASER_DPS = 1200.0

RELIC_FIRST_SPAWN = 60.0
RELIC_RESPAWN = 40.0
RELIC_HEAL_PCT = 0.15
RELIC_RADIUS = 1.0

# ---- 시야 (롤 100 유닛 = 1) ----
SIGHT = {"champion": 12.0, "minion": 10.0, "turret": 13.0, "inhibitor": 8.0, "nexus": 10.0, "fountain": 14.0}

# ---- 포탑 방패(골드) ----
TURRET_PLATES = 5         # 포탑 체력을 5칸으로 나눠 한 칸 깎일 때마다 근처 적 챔피언에게 골드
PLATE_GOLD = {"outer": 150, "inner": 120, "nexus_t1": 80, "nexus_t2": 80}
PLATE_SHARE_RANGE = 15.0

INVENTORY_SLOTS = 8
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
