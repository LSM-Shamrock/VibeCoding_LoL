"""인게임 화면.

조작 (롤과 비슷하게)
- 우클릭: 이동 / 적 클릭 시 공격 (누르고 있으면 계속 이동)
- Q W E R: 누르고 있으면 범위 표시, 떼면 마우스 위치로 시전 (W 처럼 즉시형은 바로 시전)
- Ctrl + Q/W/E/R: 스킬 레벨 업 (HUD 의 + 버튼 클릭도 가능)
- D: 점멸, F: 표식(눈덩이) — 맞힌 뒤 F 를 다시 누르면 대상에게 돌진
- A + 좌클릭: 공격 이동, S: 정지
- B: 귀환 (8초 정신집중, 이동/공격/스킬/피해 시 취소), P: 상점 (사망 중이거나 우물 안에서만 구매), Tab: 점수판
- 시야: 아군 주변만 보이고(전장의 안개), 부쉬 안의 적은 같은 부쉬에 들어가야 보인다
- Y: 카메라 고정/해제, Space: 내 챔피언으로 카메라 이동, 마우스 휠: 줌
- Enter: 채팅 (Enter 로 보내기, Esc 로 취소). 킬·포탑 파괴 같은 알림도 채팅창에 올라온다
"""
import math
import time

import moderngl
import numpy as np
import pygame

from ...shared import data as gamedata
from ...shared import mapdata
from ...shared.constants import (
    BLUE, FLASH_COOLDOWN, FLASH_RANGE, INVENTORY_SLOTS, MARK_COOLDOWN, MARK_RANGE, MARK_RECAST_TIME, RECALL_TIME, RED,
    SELL_RATIO, SIGHT,
)
from .. import ui
from ..app import HEIGHT, WIDTH, Scene
from ..geometry import MeshBuilder
from ..keybinds import ACTIONS
from ..gl import Mesh, facing_to_rot, model_matrix
from ..procedural import build_bush

MINION_KEYS = {0: "minion_melee", 1: "minion_caster", 2: "minion_cannon", 3: "minion_super"}
MINION_RADIUS = {0: 0.45, 1: 0.4, 2: 0.6, 3: 0.75}
MINION_HEIGHT = {0: 1.2, 1: 1.25, 2: 1.1, 3: 2.0}
PROJ_SPEED = {"arrow": 22, "frost_arrow": 24, "snowball": 25, "turret_shot": 16, "minion_bolt": 14,
              "cannon_ball": 14}
STAT_LABELS = [("ad", "공격력", 1), ("ap", "주문력", 1), ("hp", "체력", 1), ("mana", "마나", 1),
               ("armor", "방어력", 1), ("mr", "마법 저항력", 1), ("attack_speed", "공격 속도 %", 100),
               ("move_speed", "이동 속도", 100), ("ability_haste", "스킬 가속", 1), ("crit", "치명타 %", 100),
               ("life_steal", "생명력 흡수 %", 100), ("hp_regen", "체력 재생", 1)]
SLOTS = ("Q", "W", "E", "R")
# 마우스 아래 유닛 판정 반경 (줌 22 기준 화면 픽셀). 모델보다 넉넉하게 잡아 평타 클릭이 쉽게
HOVER_RADIUS = {"champion": 58, "minion": 38}

HUD_RECT = pygame.Rect(300, 606, 680, 108)
MINIMAP_X = 70.0                        # 미니맵이 덮는 x 범위 (±)
INV_COLS = 4                            # 인벤토리 4칸 x 2줄
CHAT_X, CHAT_Y, CHAT_W = 12, 572, 400     # 채팅 입력칸 (왼쪽 아래, 로그는 그 위로 쌓임)
CHAT_SHOW = 10.0                           # 채팅창이 닫혀 있을 때 새 줄이 보이는 시간 (초)
SETTINGS_RECT = pygame.Rect(WIDTH // 2 - 260, 70, 520, 560)
MOVE_COLOR = (0.35, 0.65, 1.0)          # 이동 지점 표시 색
MOVE_COLOR_UI = (110, 175, 255)
# 능력치 패널: (아이콘 파일 키, 이름, 값 함수). 아이콘은 assets/ui/stats/<키>.png 를 넣으면 쓰인다.
STAT_ICONS = [
    ("ad", "공격력", lambda st: st["ad"]), ("ap", "주문력", lambda st: st["ap"]),
    ("armor", "방어력", lambda st: st["ar"]), ("mr", "마법 저항력", lambda st: st["mr"]),
    ("attack_speed", "공격 속도", lambda st: st["aspd"]), ("move_speed", "이동 속도", lambda st: st["ms"]),
    ("ability_haste", "스킬 가속", lambda st: st["ah"]), ("crit", "치명타 확률", lambda st: f"{st['cr']}%"),
]
# 아이콘 파일이 없을 때 쓰는 임시 아이콘 (색, 글자)
STAT_FALLBACK = {"ad": ((230, 140, 60), "공"), "ap": ((160, 110, 240), "주"), "armor": ((210, 170, 80), "방"),
                 "mr": ((110, 170, 240), "마"), "attack_speed": ((240, 210, 90), "속"),
                 "move_speed": ((200, 210, 220), "이"), "ability_haste": ((120, 210, 230), "가"),
                 "crit": ((235, 90, 80), "치")}
MINIMAP = pygame.Rect(1000, 606, 270, 108)
ABILITY_X = {"Q": 392, "W": 454, "E": 516, "R": 578}
SPELL_X = {"D": 652, "F": 702}


def _seg_dist(px, py, a, b):
    """점 (px, py) 와 화면 선분 a-b 사이의 거리."""
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    ll = vx * vx + vy * vy
    k = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / ll))
    return math.hypot(px - (ax + vx * k), py - (ay + vy * k))


# 스킬 상세 설명 (Shift): 레벨마다 바뀌는 값 / 고정 값. (데이터 키, 이름, 표시 형식)
RANK_STATS = [("cooldown", "재사용 대기시간", "{:g}초"), ("mana", "마나 소모", "{:g}"), ("damage", "피해량", "{:g}"),
              ("attack_speed_pct", "공격 속도", "+{:.0%}"), ("move_speed_pct", "이동 속도", "+{:.0%}"),
              ("empower_magic", "강화 공격 추가 피해", "{:g}")]
FLAT_STATS = [("ad_ratio", "공격력 계수", "{:.0%}"), ("bonus_ad_ratio", "추가 공격력 계수", "{:.0%}"),
              ("ap_ratio", "주문력 계수", "{:.0%}"), ("empower_ap_ratio", "강화 공격 주문력 계수", "{:.0%}"),
              ("range", "사거리", lambda v: f"{v * 100:g}"), ("radius", "범위 반경", lambda v: f"{v * 100:g}"),
              ("slow", "둔화", "{:.0%}"), ("slow_duration", "둔화 시간", "{:g}초"), ("stun", "기절", "{:g}초"),
              ("duration", "지속 시간", "{:g}초"), ("empower_duration", "강화 지속 시간", "{:g}초"),
              ("delay", "발동 지연", "{:g}초")]
DAMAGE_TYPES = {"physical": "물리", "magic": "마법", "true": "고정"}
# 소환사 주문: 주문 id -> (이름, 아이콘 색, 설명, 상세)
SPELL_INFO = {
    "D": ("점멸", (90, 80, 40), "짧은 거리 순간이동",
          [("사거리", f"{FLASH_RANGE * 100:g}"), ("재사용 대기시간", f"{FLASH_COOLDOWN:g}초")]),
    "F": ("표식", (60, 90, 110), "눈덩이 투척 · 적중 후 재사용 시 돌진",
          [("피해량", "10 + 레벨 × 5 (고정)"), ("사거리", f"{MARK_RANGE * 100:g}"),
           ("돌진 가능 시간", f"{MARK_RECAST_TIME:g}초"), ("재사용 대기시간", f"{MARK_COOLDOWN:g}초")]),
}


def ability_details(ab):
    """스킬 데이터 -> [(이름, 값)] — 값이 리스트면 스킬 레벨별 값."""
    rows = []
    for key, label, fmt in RANK_STATS:
        if key in ab:
            rows.append((label, [fmt.format(v) for v in ab[key]]))
    if "damage_type" in ab:
        rows.append(("피해 유형", DAMAGE_TYPES.get(ab["damage_type"], ab["damage_type"])))
    for key, label, fmt in FLAT_STATS:
        if key in ab:
            rows.append((label, fmt(ab[key]) if callable(fmt) else fmt.format(ab[key])))
    return rows


def draw_item(surf, iid, rect, font_size=14):
    """아이템 아이콘 (assets/items/<id>.png). 파일이 없으면 색 사각형 + 첫 글자."""
    rect = pygame.Rect(rect)
    icon = ui.icon(f"assets/items/{iid}.png", rect.width)
    if icon:
        surf.blit(icon, rect)
        return
    it = gamedata.items()[iid]
    pygame.draw.rect(surf, tuple(it["color"]), rect, border_radius=4)
    ui.text(surf, it["name"][0], rect.center, font_size, (20, 20, 30), anchor="center", bold=True, shadow=False)


def item_stat_text(item):
    parts = []
    for key, label, mul in STAT_LABELS:
        v = item["stats"].get(key)
        if v:
            parts.append(f"{label} +{round(v * mul)}")
    return ", ".join(parts)


class CEnt:
    """스냅샷 사이를 부드럽게 보간하는 클라이언트 쪽 유닛."""

    def __init__(self, eid, x, z, f=0.0):
        self.id = eid
        self.x = self.tx = x
        self.z = self.tz = z
        self.f = self.tf = f
        self.d = None
        self.swing_t = -10.0        # 마지막 공격 휘두르기 시작 시각 (미니언 무기 모션)
        self.visible = True         # 이번 스냅샷에 포함됐는가 (시야 밖의 적은 빠진다)

    def set_target(self, x, z, f):
        if math.hypot(x - self.x, z - self.z) > 6.0:      # 순간이동(점멸, 부활 등)
            self.x, self.z = x, z
        self.tx, self.tz, self.tf = x, z, f

    def step(self, dt):
        k = min(1.0, dt * 14.0)
        self.x += (self.tx - self.x) * k
        self.z += (self.tz - self.z) * k
        df = (self.tf - self.f + math.pi) % math.tau - math.pi
        self.f += df * min(1.0, dt * 16.0)


class GameScene(Scene):
    fullscreen = True       # 인게임은 전체 화면 (Alt+Enter 로 전환 가능)
    grab_mouse = True       # 커서를 화면 안에 가둬 화면 끝 카메라 이동이 되게

    def __init__(self, app, start):
        super().__init__(app)
        self.structs = {s["i"]: s for s in start["structures"]}
        self.struct_state = {s["i"]: [s["i"], s["mhp"], 1, 0, 0] for s in start["structures"]}
        self.champ_info = {c["i"]: c for c in start["champions"]}
        self.my_id = next((c["i"] for c in start["champions"] if c["pk"] == start["you"]), None)
        self.my_team = self.champ_info[self.my_id]["tm"] if self.my_id else BLUE
        self.champs = {}
        self.minions = {}
        self.projs = {}
        self.ground_effects = []
        self.relics = []
        self.fx = []
        self.floaters = []
        self.killfeed = []
        self.announces = []
        self.server_time = 0.0
        self.score = [0, 0]
        self.wave_in = 0.0
        self.winner = None
        self.over_at = 0.0

        self.shop_open = False
        self.show_score = False
        self.cam_locked = True
        self.aiming = None
        self.amove_pending = False
        self.rmb_down = False
        self.rmb_repeat = 0.0
        self.hover = None
        self.hover_slot = None
        self.click_marker = None
        self.move_dest = None       # 이동 목적지 (도착할 때까지 바닥에 표시)
        self.minimap_drag = False   # 미니맵을 좌클릭한 채로 끌면 카메라 이동
        self.rmb_minimap = False    # 미니맵을 우클릭한 채로 있으면 계속 이동 명령
        self.shop_rects = []
        self.levelup_rects = []
        self.hud_inv_rects = []     # HUD 인벤토리 칸 (상점이 열려 있으면 우클릭 판매)
        self.gold_rect = None       # 골드 글자 (클릭하면 상점 열기/닫기)
        self.hud_tooltip = None     # 상점·점수판 위에 그리도록 마지막에 그린다
        self.chat_lines = []        # (시각, [(글자, 색), ...]) — 플레이어 채팅과 킬·파괴 알림
        self.chat_open = False
        self.chat_in = ui.TextInput((CHAT_X, CHAT_Y, CHAT_W, 26), "", 100, "Enter 로 보내기 · Esc 취소")
        self.zoom = 22.0
        self.fake_mouse = None      # 자동 테스트용
        self.binds = app.keybinds
        self.held = set()           # 누르고 있는 행동 (카메라 중심 등)
        self.settings_open = False  # ESC 설정 창
        self.rebinding = None       # 새 키를 기다리는 행동
        self.settings_rects = []
        self.stat_rects = []

        # 스킬 범위 표시용 사각형 메시 (x: -0.5~0.5, z: 0~1)
        b = MeshBuilder()
        b.rect_xz(-0.5, 0.0, 0.5, 1.0, 0.0, (1, 1, 1))
        self.quad = Mesh.from_builder(app.renderer, b)

        for cid, info in self.champ_info.items():
            app.models.champion(info["c"])

        # 부쉬
        self.bush_meshes = [Mesh.from_builder(app.renderer, build_bush(rx, rz, seed=i))
                            for i, (bx, bz, rx, rz) in enumerate(mapdata.BUSHES)]
        self.board = {}             # 점수판(Tab): 챔피언 id -> [id, 레벨, 킬, 데스, 어시, CS, 골드, 아이템, 사망, 부활초]
        # 시야 격자: 칸 중심 좌표와 각 칸의 부쉬 번호를 미리 계산
        self.vis_nx = int((mapdata.VIS_X1 - mapdata.VIS_X0) / mapdata.VIS_CELL)
        self.vis_nz = int((mapdata.VIS_Z1 - mapdata.VIS_Z0) / mapdata.VIS_CELL)
        xs = mapdata.VIS_X0 + (np.arange(self.vis_nx) + 0.5) * mapdata.VIS_CELL
        zs = mapdata.VIS_Z0 + (np.arange(self.vis_nz) + 0.5) * mapdata.VIS_CELL
        self.vis_x, self.vis_z = np.meshgrid(xs, zs)
        self.vis_bush = np.full(self.vis_x.shape, -1, dtype=np.int8)
        for i, (bx, bz, rx, rz) in enumerate(mapdata.BUSHES):
            self.vis_bush[((self.vis_x - bx) / rx) ** 2 + ((self.vis_z - bz) / rz) ** 2 <= 1.0] = i
        self.vis = np.ones(self.vis_x.shape, dtype=np.float32)
        self.vis_tex = app.renderer.ctx.texture((self.vis_nx, self.vis_nz), 1, dtype="f1")
        self.vis_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.vis_tex.repeat_x = self.vis_tex.repeat_y = False
        self.vis_rect = (mapdata.VIS_X0, mapdata.VIS_Z0, mapdata.VIS_X1 - mapdata.VIS_X0,
                         mapdata.VIS_Z1 - mapdata.VIS_Z0)
        self.vis_timer = 0.0
        self.minimap_fog = None

        cam = app.renderer.camera
        x, z = mapdata.fountain_pos(self.my_team)
        cam.tx, cam.ty, cam.tz = x, 0.0, z
        cam.pitch = math.radians(56)
        cam.yaw = 0.0
        cam.distance = self.zoom

    def on_enter(self):
        # 텍스트 입력(IME)이 켜져 있으면 한글 모드에서 스킬 키가 입력기로 빠져 나가므로 끈다
        pygame.key.stop_text_input()
        self.app.renderer.vision = (self.vis_tex, self.vis_rect)

    # ------------------------------------------------------------------ 시야
    def update_vision(self):
        """아군 시야 제공자로 시야 격자를 계산해 셰이더(전장의 안개)와 미니맵에 쓴다.

        서버가 실제로 보내 주는 적 정보도 같은 규칙(시야 반경, 부쉬)을 따른다.
        """
        obs = [(*mapdata.fountain_pos(self.my_team), SIGHT["fountain"])]
        for cid, e in self.champs.items():
            if self.champ_info[cid]["tm"] == self.my_team and e.d and not e.d["dead"]:
                obs.append((e.x, e.z, SIGHT["champion"]))
        for e in self.minions.values():
            if e.d[2] == self.my_team:
                obs.append((e.x, e.z, SIGHT["minion"]))
        for sid, st in self.structs.items():
            if st["tm"] == self.my_team and self.struct_state[sid][2]:
                obs.append((st["x"], st["z"], SIGHT[st["k"]]))
        vis = np.zeros(self.vis_x.shape, dtype=bool)
        for ox, oz, r in obs:
            m = (self.vis_x - ox) ** 2 + (self.vis_z - oz) ** 2 <= r * r
            ob = mapdata.bush_at(ox, oz)
            vis |= m & ((self.vis_bush < 0) | (self.vis_bush == ob))
        # 부드럽게 밝아지고 어두워지게
        self.vis += (vis.astype(np.float32) - self.vis) * 0.5
        self.vis_tex.write((self.vis * 255).astype(np.uint8).tobytes())
        # 미니맵용 안개 (안 보이는 곳을 어둡게)
        fog = np.zeros((self.vis_nx, self.vis_nz, 4), dtype=np.uint8)
        fog[..., 3] = ((1.0 - self.vis.T) * 150).astype(np.uint8)
        surf = pygame.image.frombuffer(np.ascontiguousarray(fog.transpose(1, 0, 2)).tobytes(),
                                       (self.vis_nx, self.vis_nz), "RGBA")
        x0, z0 = self.world_to_minimap(mapdata.VIS_X0, mapdata.VIS_Z0)
        x1, z1 = self.world_to_minimap(mapdata.VIS_X1, mapdata.VIS_Z1)
        self.minimap_fog = (pygame.transform.smoothscale(surf, (max(1, x1 - x0), max(1, z1 - z0))), (x0, z0))

    # ------------------------------------------------------------------ 도우미
    @property
    def me(self):
        e = self.champs.get(self.my_id)
        return e.d if e else None

    def my_data(self):
        return gamedata.champion(self.champ_info[self.my_id]["c"]) if self.my_id else None

    def mouse_pos(self):
        return self.fake_mouse or ui.mouse_pos()

    def mouse_ground(self):
        mx, my = self.mouse_pos()
        return self.app.renderer.camera.screen_to_ground(mx, my) or (0.0, 0.0)

    def send_cmd(self, **kw):
        self.app.send({"t": "cmd", **kw})

    def max_rank(self, slot, level):
        if slot == "R":
            return sum(1 for lv in (6, 11, 16) if level >= lv)
        return min(5, (level + 1) // 2)

    # ------------------------------------------------------------------ 메시지
    def on_message(self, msg):
        t = msg.get("t")
        if t == "snap":
            self.apply_snapshot(msg)
        elif t == "chat":
            col = ui.TEAM_UI.get(msg.get("team"), ui.TEXT)
            self.add_chat([(f"{msg['name']}: ", col), (msg["text"], ui.TEXT)])
        elif t == "game_over":
            self.winner = msg["winner"]
            self.over_at = time.time()

    def apply_snapshot(self, s):
        now = time.time()
        self.server_time = s["time"]
        self.score = s["score"]
        self.wave_in = s.get("wave", 0)

        seen = set()
        for d in s["ch"]:
            e = self.champs.get(d["i"])
            if e is None:
                e = self.champs[d["i"]] = CEnt(d["i"], d["x"], d["z"], d["f"])
            if (e.d and e.d["dead"] and not d["dead"]) or not e.visible:
                e.x, e.z = d["x"], d["z"]       # 부활하거나 안개에서 나타나면 바로 그 자리에
            e.set_target(d["x"], d["z"], d["f"])
            e.d = d
            e.visible = True
            seen.add(d["i"])
        for cid, e in self.champs.items():
            if cid not in seen:
                e.visible = False               # 시야 밖
        self.board = {row[0]: row for row in s.get("sb", [])}
        gone = set(s.get("gone", []))

        seen = set()
        for row in s["mn"]:
            mid = row[0]
            e = self.minions.get(mid)
            if e is None:
                e = self.minions[mid] = CEnt(mid, row[3], row[4], row[5])
            if row[8] == 2 and (e.d is None or e.d[8] != 2) and now - e.swing_t > 0.3:
                e.swing_t = now
            e.set_target(row[3], row[4], row[5])
            e.d = row
            seen.add(mid)
        for mid in list(self.minions):
            if mid not in seen:
                e = self.minions.pop(mid)
                if mid in gone:                 # 죽은 경우만 효과 (시야 밖으로 나간 경우는 그냥 사라짐)
                    self.add_fx("poof", e.x, e.z, 0.4, color=(0.9, 0.9, 1.0))

        for row in s["st"]:
            old = self.struct_state.get(row[0])
            if old and old[2] and not row[2]:
                info = self.structs[row[0]]
                self.add_fx("burst", info["x"], info["z"], 1.2, radius=4.0, color=(1.0, 0.7, 0.4))
            self.struct_state[row[0]] = row

        seenp = set()
        for row in s["pj"]:
            pid, style, team, x, z, dx, dz = row
            sp = PROJ_SPEED.get(style, 18)
            self.projs[pid] = {"style": style, "team": team, "x": x, "z": z, "dx": dx, "dz": dz,
                               "vx": dx * sp, "vz": dz * sp, "t": now}
            seenp.add(pid)
        for pid in list(self.projs):
            if pid not in seenp:
                del self.projs[pid]

        self.ground_effects = [(row, now) for row in s["ef"]]
        self.relics = s["rl"]
        for ev in s["ev"]:
            self.handle_event_msg(ev)

    def handle_event_msg(self, ev):
        e = ev.get("e")
        now = time.time()
        if e == "dmg":
            if ev["s"] == self.my_id:
                tgt = self.entity_pos(ev["d"])
                if tgt:
                    col = {"p": (255, 170, 90), "m": (170, 140, 255), "t": (255, 255, 255)}.get(ev["ty"], (255, 255, 255))
                    self.floaters.append({"x": tgt[0], "z": tgt[1], "text": str(ev["v"]), "color": col, "t": now,
                                          "dur": 0.9, "size": 18})
            elif ev["d"] == self.my_id and ev["v"] >= 30:
                tgt = self.entity_pos(ev["d"])
                if tgt:
                    self.floaters.append({"x": tgt[0], "z": tgt[1], "text": f"-{ev['v']}", "color": (255, 80, 80),
                                          "t": now, "dur": 0.8, "size": 15})
        elif e == "gold" and ev["d"] == self.my_id:
            self.floaters.append({"x": ev["x"], "z": ev["z"], "text": f"+{ev['v']}", "color": (250, 210, 90),
                                  "t": now, "dur": 1.0, "size": 16})
        elif e == "kill":
            self.killfeed.append((now, ev))
            self.killfeed = self.killfeed[-6:]
            self.add_chat([(ev["kn"], ui.TEAM_UI.get(ev["kt"], ui.TEXT)), (" 님이 ", ui.TEXT_DIM),
                           (ev["vn"], ui.TEAM_UI.get(ev["vt"], ui.TEXT)), (" 님을 처치했습니다.", ui.TEXT_DIM)])
            if ev["v"] == self.my_id:
                self.announces.append((now, "처치당했습니다!", ui.RED_C))
            elif ev["k"] == self.my_id:
                self.announces.append((now, "적을 처치했습니다!", ui.GOLD))
        elif e == "announce":
            self.announces.append((now, ev["text"], ui.TEXT))
            self.add_chat([(ev["text"], ui.GOLD)])
        elif e == "levelup":
            pos = self.entity_pos(ev["d"])
            if pos:
                self.add_fx("ring_up", pos[0], pos[1], 0.8, radius=1.4, color=(1.0, 0.85, 0.4))
                if ev["d"] == self.my_id:
                    self.floaters.append({"x": pos[0], "z": pos[1], "text": "레벨 업!", "color": (255, 220, 120),
                                          "t": now, "dur": 1.4, "size": 20})
        elif e == "fx":
            kind = ev["fx"]
            if kind == "blizzard_burst":
                self.add_fx("burst", ev["x"], ev["z"], 0.8, radius=ev.get("r", 3.5), color=(0.7, 0.92, 1.0))
                self.add_fx("shards", ev["x"], ev["z"], 0.9, radius=ev.get("r", 3.5), color=(0.8, 0.95, 1.0))
            elif kind == "flash":
                self.add_fx("poof", ev["x"], ev["z"], 0.5, color=(1.0, 1.0, 0.6))
                self.add_fx("poof", ev["x2"], ev["z2"], 0.5, color=(1.0, 1.0, 0.6))
            elif kind == "relic":
                self.add_fx("ring_up", ev["x"], ev["z"], 0.8, radius=1.6, color=(0.4, 1.0, 0.5))
            elif kind == "recall":
                self.add_fx("ring_up", ev["x"], ev["z"], 0.7, radius=1.4, color=(0.4, 0.7, 1.0))
                self.add_fx("ring_up", ev["x2"], ev["z2"], 0.9, radius=1.6, color=(0.4, 0.7, 1.0))
            elif kind == "plate":
                self.add_fx("burst", ev["x"], ev["z"], 0.6, radius=2.2, color=(1.0, 0.82, 0.35))
            elif kind.endswith("_hit"):
                col = (0.95, 0.97, 1.0) if kind.startswith("snowball") else (0.6, 0.9, 1.0)
                self.add_fx("poof", ev["x"], ev["z"], 0.35, color=col)
        elif e == "cast":
            pos = self.entity_pos(ev["d"])
            if pos and ev.get("slot") == "W":
                self.add_fx("ring_up", pos[0], pos[1], 0.6, radius=1.2, color=(0.6, 0.9, 1.0))

    def add_chat(self, parts):
        self.chat_lines.append((time.time(), parts))
        self.chat_lines = self.chat_lines[-40:]

    # ---- 채팅 입력
    def open_chat(self):
        self.chat_open = True
        self.chat_in.value = ""
        self.chat_in.composing = ""
        self.chat_in.focused = True
        self.aiming = None
        self.amove_pending = False
        self.held.clear()
        pygame.key.start_text_input()       # 한글 입력
        pygame.key.set_text_input_rect(self.chat_in.rect)

    def close_chat(self, send=False):
        text = self.chat_in.value.strip()
        if send and text:
            self.app.send({"t": "chat", "text": text})
        self.chat_open = False
        self.chat_in.focused = False
        self.chat_in.composing = ""
        pygame.key.stop_text_input()        # 다시 게임 키가 입력기로 새지 않게

    def handle_chat_event(self, e):
        """채팅 입력 중 키보드 이벤트. 처리했으면 True (게임 조작으로 넘기지 않음)."""
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.chat_in.composing:
                self.close_chat(send=True)
                return True
            if e.key == pygame.K_ESCAPE:
                self.close_chat()
                return True
            self.chat_in.handle(e)
            return True
        if e.type in (pygame.KEYUP, pygame.TEXTINPUT, pygame.TEXTEDITING):
            self.chat_in.handle(e)
            return True
        return False

    def entity_pos(self, eid):
        e = self.champs.get(eid) or self.minions.get(eid)
        if e:
            return e.x, e.z
        s = self.structs.get(eid)
        if s:
            return s["x"], s["z"]
        return None

    def add_fx(self, kind, x, z, dur, radius=1.0, color=(1, 1, 1)):
        self.fx.append({"kind": kind, "x": x, "z": z, "t": time.time(), "dur": dur, "r": radius, "color": color})

    # ------------------------------------------------------------------ 입력
    def enemy_targetable(self, kind, eid):
        if kind == "champion":
            d = self.champs[eid].d
            return d and not d["dead"] and self.champ_info[eid]["tm"] != self.my_team
        if kind == "minion":
            return self.minions[eid].d[2] != self.my_team
        if kind == "structure":
            st = self.struct_state[eid]
            return self.structs[eid]["tm"] != self.my_team and st[2] and st[3]
        return False

    def find_hover(self):
        """마우스 아래에 있는 유닛 (kind, id)."""
        cam = self.app.renderer.camera
        mx, my = self.mouse_pos()
        zoom_k = 22.0 / max(1.0, cam.distance)
        best, best_d = None, 1e9
        cands = []
        for eid, e in self.champs.items():
            if e.visible and e.d and not e.d["dead"]:
                cands.append(("champion", eid, e.x, e.z, 2.0, HOVER_RADIUS["champion"]))
        for eid, e in self.minions.items():
            cands.append(("minion", eid, e.x, e.z, MINION_HEIGHT[e.d[1]], HOVER_RADIUS["minion"]))
        for eid, s in self.structs.items():
            if self.struct_state[eid][2]:
                h = 4.0 if s["k"] == "turret" else 2.0
                cands.append(("structure", eid, s["x"], s["z"], h, 60 if s["k"] != "turret" else 50))
        for kind, eid, x, z, h, rad in cands:
            # 발밑~머리 위 세로 선분과의 거리로 판정해, 모델 어디를 눌러도 / 조금 빗나가도 잡히게
            a = cam.world_to_screen(x, 0.0, z)
            b = cam.world_to_screen(x, h, z)
            if a is None or b is None:
                continue
            d = _seg_dist(mx, my, a, b) / (rad * zoom_k)   # 판정 반경 대비 거리 (작을수록 가까움)
            if d < 1.0 and d < best_d:
                best, best_d = (kind, eid), d
        return best

    def slot_rects(self):
        rects = [(slot, pygame.Rect(ABILITY_X[slot], 614, 54, 54)) for slot in SLOTS]
        rects += [(slot, pygame.Rect(SPELL_X[slot], 619, 44, 44)) for slot in ("D", "F")]
        return rects

    def find_hover_slot(self):
        """마우스가 올라가 있는 스킬/주문 아이콘 (롤처럼 범위 미리보기용)."""
        mouse = self.mouse_pos()
        return next((slot for slot, rect in self.slot_rects() if rect.collidepoint(mouse)), None)

    def right_click(self, repeat=False, attack_move=False):
        """우클릭(또는 A + 좌클릭): 적 위면 공격, 아니면 이동(공격 이동)."""
        if self.my_id is None or not self.me or self.me["dead"]:
            return
        hov = self.hover
        if hov and self.enemy_targetable(*hov):
            if not repeat:
                self.send_cmd(c="attack", id=hov[1])
                self.move_dest = None
            return
        x, z = self.mouse_ground()
        self.issue_move(x, z, cmd="amove" if attack_move else "move", marker=not repeat)

    def issue_move(self, x, z, cmd="move", marker=True):
        """이동 명령 + 바닥 이동 지점 표시."""
        if self.my_id is None or not self.me or self.me["dead"]:
            return
        x, z = mapdata.clamp_to_map(x, z, 0.5)
        self.send_cmd(c=cmd, x=round(x, 2), z=round(z, 2))
        self.move_dest = (x, z)
        if marker:
            self.click_marker = (x, z, time.time())

    def cast_slot(self, slot):
        x, z = self.mouse_ground()
        self.send_cmd(c="cast", slot=slot, x=round(x, 2), z=round(z, 2))

    def handle_event(self, e):
        if self.settings_open:
            self.handle_settings_event(e)
            return
        if self.chat_open and self.handle_chat_event(e):
            return
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.open_chat()
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                # ESC: 열린 것(상점/조준)을 먼저 닫고, 없으면 설정 창
                if self.shop_open or self.aiming:
                    self.shop_open = False
                    self.aiming = None
                else:
                    self.open_settings()
                return
            mods = pygame.key.get_mods()
            act = self.binds.action(e)
            if act:
                self.held.add(act)
            if act in SLOTS:
                slot = act
                if mods & pygame.KMOD_CTRL:
                    self.send_cmd(c="level", slot=slot)
                    return
                data = self.my_data()
                if data and data["abilities"][slot]["type"] == "self_buff":
                    self.cast_slot(slot)
                else:
                    self.aiming = slot
                return
            if act in ("D", "F"):
                x, z = self.mouse_ground()
                self.send_cmd(c="spell", slot=self.binds.spell_at(act), x=round(x, 2), z=round(z, 2))
            elif act == "stop":
                self.send_cmd(c="stop")
                self.move_dest = None
            elif act == "attack_move":
                self.amove_pending = True
            elif act == "recall":
                self.send_cmd(c="recall")
                self.move_dest = None
            elif act == "shop":
                self.shop_open = not self.shop_open
            elif act == "score":
                self.show_score = True
            elif act == "cam_lock":
                self.cam_locked = not self.cam_locked
        elif e.type == pygame.KEYUP:
            act = self.binds.action(e)
            self.held.discard(act)
            if act == "score":
                self.show_score = False
            elif act == "attack_move":
                self.amove_pending = False      # 누르고 있는 동안만 공격 범위 표시
            elif self.aiming and act == self.aiming:
                self.cast_slot(self.aiming)
                self.aiming = None
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                if self.click_ui(e.pos):
                    return
                if self.aiming:
                    self.cast_slot(self.aiming)
                    self.aiming = None
                elif self.amove_pending:
                    # A + 좌클릭: 적을 누르면 그 적을 공격, 땅을 누르면 공격 이동
                    self.right_click(attack_move=True)
            elif e.button == 3:
                self.aiming = None
                if MINIMAP.collidepoint(e.pos):
                    x, z = self.minimap_to_world(*e.pos)
                    self.issue_move(x, z)
                    self.rmb_down = True
                    self.rmb_minimap = True
                    self.rmb_repeat = 0.15
                    return
                if self.shop_open and self.shop_panel().collidepoint(e.pos):
                    self.shop_right_click(e.pos)
                    return
                if self.shop_open:
                    hit = next((i for i, rect in self.hud_inv_rects if rect.collidepoint(e.pos)), None)
                    if hit is not None:
                        self.send_cmd(c="sell", slot=hit)
                        return
                if HUD_RECT.collidepoint(e.pos):
                    return
                self.rmb_down = True
                self.rmb_minimap = False
                self.rmb_repeat = 0.15
                self.right_click()
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 3:
            self.rmb_down = False
            self.rmb_minimap = False
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.minimap_drag = False
        elif e.type == pygame.MOUSEMOTION and self.minimap_drag:
            self.minimap_camera(e.pos)
        elif e.type == pygame.MOUSEWHEEL:
            self.zoom = max(16.0, min(36.0, self.zoom - e.y * 2.0))

    # ---- 설정 (ESC)
    def open_settings(self):
        self.settings_open = True
        self.rebinding = None
        self.aiming = None
        self.amove_pending = False
        self.rmb_down = False
        self.held.clear()

    def handle_settings_event(self, e):
        if e.type == pygame.KEYDOWN:
            if self.rebinding:
                if e.key != pygame.K_ESCAPE:
                    self.binds.assign(self.rebinding, e)
                self.rebinding = None
            elif e.key == pygame.K_ESCAPE:
                self.settings_open = False
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.rebinding = None
            for kind, rect in self.settings_rects:
                if rect.collidepoint(e.pos):
                    if kind == "close":
                        self.settings_open = False
                    elif kind == "reset":
                        self.binds.reset()
                    else:
                        self.rebinding = kind

    def draw_settings(self, surf):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        surf.blit(shade, (0, 0))
        p = SETTINGS_RECT
        ui.panel(surf, p, (12, 18, 30, 245), ui.BORDER)
        ui.text(surf, "조작키", (p.x + 24, p.y + 16), 22, bold=True)
        ui.text(surf, "스킬 레벨업: Ctrl + 스킬 키", (p.right - 24, p.y + 26), 13, ui.TEXT_DIM, anchor="topright")
        mouse = ui.mouse_pos()
        self.settings_rects = []
        y = p.y + 60
        for action, label in ACTIONS:
            ui.text(surf, label, (p.x + 30, y + 14), 15, anchor="midleft")
            box = pygame.Rect(p.right - 170, y, 140, 28)
            waiting = self.rebinding == action
            hover = box.collidepoint(mouse)
            pygame.draw.rect(surf, (40, 60, 95) if waiting or hover else (24, 32, 48), box, border_radius=4)
            pygame.draw.rect(surf, ui.HIGHLIGHT if waiting else ui.BORDER, box, 1, border_radius=4)
            ui.text(surf, "키 입력..." if waiting else self.binds.name(action), box.center, 15,
                    ui.GOLD if waiting else ui.TEXT, anchor="center", bold=not waiting)
            self.settings_rects.append((action, box))
            y += 34
        for kind, label, rect in (("reset", "기본값", pygame.Rect(p.x + 24, p.bottom - 52, 120, 36)),
                                  ("close", "닫기", pygame.Rect(p.right - 144, p.bottom - 52, 120, 36))):
            pygame.draw.rect(surf, (40, 60, 95) if rect.collidepoint(mouse) else (28, 38, 58), rect, border_radius=6)
            pygame.draw.rect(surf, ui.BORDER, rect, 1, border_radius=6)
            ui.text(surf, label, rect.center, 16, anchor="center")
            self.settings_rects.append((kind, rect))

    def click_ui(self, pos):
        for slot, rect in self.levelup_rects:
            if rect.collidepoint(pos):
                self.send_cmd(c="level", slot=slot)
                return True
        if self.shop_open:
            if self.shop_panel().collidepoint(pos):
                for iid, rect in self.shop_rects:
                    if rect.collidepoint(pos):
                        self.send_cmd(c="buy", item=iid)
                return True
        me = self.me
        if self.gold_rect and self.gold_rect.collidepoint(pos) and me:
            self.shop_open = not self.shop_open
            return True
        if MINIMAP.collidepoint(pos):
            self.minimap_drag = True
            self.minimap_camera(pos)
            return True
        if HUD_RECT.collidepoint(pos):
            return True
        return False

    def minimap_camera(self, pos):
        """미니맵 위치로 카메라 이동 (미니맵 밖으로 끌어도 가장자리까지 따라감)."""
        px = max(MINIMAP.left, min(MINIMAP.right - 1, pos[0]))
        py = max(MINIMAP.top, min(MINIMAP.bottom - 1, pos[1]))
        x, z = self.minimap_to_world(px, py)
        cam = self.app.renderer.camera
        cam.tx, cam.tz = x, z
        self.cam_locked = False

    def shop_right_click(self, pos):
        for iid, rect in self.shop_rects:
            if rect.collidepoint(pos):
                self.send_cmd(c="buy", item=iid)

    # ------------------------------------------------------------------ 갱신
    def update(self, dt):
        for e in self.champs.values():
            e.step(dt)
        for e in self.minions.values():
            e.step(dt)
        self.vis_timer -= dt
        if self.vis_timer <= 0:
            self.vis_timer = 0.1
            self.update_vision()
        self.hover = self.find_hover()
        self.hover_slot = self.find_hover_slot()

        if self.rmb_down:
            self.rmb_repeat -= dt
            if self.rmb_repeat <= 0:
                self.rmb_repeat = 0.15
                if self.rmb_minimap:
                    mp = ui.mouse_pos()
                    if MINIMAP.collidepoint(mp):
                        self.issue_move(*self.minimap_to_world(*mp), marker=False)
                else:
                    self.right_click(repeat=True)
        if self.minimap_drag:
            if pygame.mouse.get_pressed()[0]:
                self.minimap_camera(ui.mouse_pos())
            else:
                self.minimap_drag = False

        # 목적지 도착 / 사망 시 이동 표시 제거
        me = self.champs.get(self.my_id)
        if self.move_dest and (not me or not me.d or me.d["dead"]
                               or math.hypot(me.x - self.move_dest[0], me.z - self.move_dest[1]) < 0.6):
            self.move_dest = None

        cam = self.app.renderer.camera
        cam.distance += (self.zoom - cam.distance) * min(1.0, dt * 10)
        keys = pygame.key.get_pressed()
        me = self.champs.get(self.my_id)
        if me and (self.cam_locked or "cam_center" in self.held):
            cam.tx += (me.x - cam.tx) * min(1.0, dt * 10)
            cam.tz += (me.z - cam.tz) * min(1.0, dt * 10)
        elif not self.minimap_drag and not self.settings_open:
            # 롤처럼 커서를 화면 끝에 대면 그 방향으로 카메라 이동 (방향키도 가능)
            ex, ey = self.app.mouse_edge()
            if keys[pygame.K_LEFT]:
                ex = -1
            if keys[pygame.K_RIGHT]:
                ex = 1
            if keys[pygame.K_UP]:
                ey = -1
            if keys[pygame.K_DOWN]:
                ey = 1
            speed = 32.0 * dt * (cam.distance / 22.0)
            cam.tx = max(-70, min(70, cam.tx + ex * speed))
            cam.tz = max(-15, min(15, cam.tz + ey * speed))

        now = time.time()
        self.fx = [f for f in self.fx if now - f["t"] < f["dur"]]
        self.floaters = [f for f in self.floaters if now - f["t"] < f["dur"]]
        self.announces = [a for a in self.announces if now - a[0] < 3.0][-3:]

    # ------------------------------------------------------------------ 3D
    def render3d(self):
        r = self.app.renderer
        m = self.app.models
        cam = r.camera
        r.begin_3d(cam)
        r.draw(m.map, model_matrix())
        now = time.time()
        t = self.app.time

        # 우물 범위 표시
        for team in (BLUE, RED):
            fx, fz = mapdata.fountain_pos(team)
            col = (0.3, 0.6, 1.0) if team == BLUE else (1.0, 0.35, 0.3)
            r.draw_transparent(m.ring_thin, model_matrix(fx, 0.06, fz, scale=7.5), (*col, 0.5))

        hov_id = self.hover[1] if self.hover else None

        # 부쉬: 내 챔피언이 들어가 있는 부쉬는 반투명
        me = self.champs.get(self.my_id)
        my_bush = mapdata.bush_at(me.x, me.z) if me and me.d and not me.d["dead"] else -1
        for i, (bx, bz, rx, rz) in enumerate(mapdata.BUSHES):
            if i == my_bush:
                r.draw_transparent(self.bush_meshes[i], model_matrix(bx, 0, bz), (1, 1, 1, 0.45), unlit=0.0)
            else:
                r.draw(self.bush_meshes[i], model_matrix(bx, 0, bz))

        # 구조물
        for sid, s in self.structs.items():
            st = self.struct_state[sid]
            alive = st[2]
            meshes = m.team_meshes[s["tm"]]
            emis = (0.18, 0.18, 0.18) if sid == hov_id else (0, 0, 0)
            if s["k"] == "turret":
                mesh = meshes["turret"] if alive else m.rubble
            elif s["k"] == "inhibitor":
                mesh = meshes["inhibitor"] if alive else meshes["inhibitor_dead"]
            else:
                mesh = meshes["nexus"] if alive else meshes["nexus_dead"]
            r.draw(mesh, model_matrix(s["x"], 0, s["z"], rot_y=0.0), emissive=emis)
            if alive and s["k"] == "turret":
                # 포탑 사거리: 내 챔피언이 가까이 있으면 표시
                me = self.champs.get(self.my_id)
                if me and s["tm"] != self.my_team and math.hypot(me.x - s["x"], me.z - s["z"]) < mapdata.TURRET_RANGE + 4:
                    r.draw_transparent(m.ring_thin, model_matrix(s["x"], 0.05, s["z"], scale=mapdata.TURRET_RANGE),
                                       (1.0, 0.3, 0.25, 0.7))
            if alive and not st[3] and s["tm"] != self.my_team:
                # 무적 구조물: 보호막
                r.draw_transparent(m.orb, model_matrix(s["x"], 1.5, s["z"], scale=s["r"] + 0.7),
                                   (0.6, 0.7, 1.0, 0.08), additive=True)

        # 유물
        for rid, x, z, active in self.relics:
            # 생성 위치 바닥 표시 (없을 때도 보임)
            r.draw_transparent(m.disc, model_matrix(x, 0.035, z, scale=0.2), (0.6, 0.6, 0.62, 0.35))
            r.draw_transparent(m.ring_thin, model_matrix(x, 0.04, z, scale=0.2), (0.7, 0.7, 0.72, 0.7))
            if active:
                r.draw_transparent(m.shadow, model_matrix(x, 0.03, z, scale=0.5), (0, 0, 0, 0.3))
                r.draw(m.relic, model_matrix(x, 0.9 + math.sin(t * 2 + rid) * 0.15, z, rot_y=t * 1.5),
                       emissive=(0.1, 0.45, 0.15))
                r.draw_transparent(m.ring, model_matrix(x, 0.05, z, scale=0.9), (0.4, 1.0, 0.5, 0.6), additive=True)

        # 미니언
        for mid, e in self.minions.items():
            row = e.d
            code, team, anim = row[1], row[2], row[8]
            key = MINION_KEYS[code]
            bob = abs(math.sin(t * 9 + mid)) * 0.08 if anim == 1 else 0.0
            rot = facing_to_rot(e.f)
            rad = MINION_RADIUS[code]
            r.draw_transparent(m.shadow, model_matrix(e.x, 0.03, e.z, scale=rad * 1.1), (0, 0, 0, 0.3))
            emis = (0.2, 0.2, 0.2) if mid == hov_id else (0, 0, 0)
            r.draw(m.team_meshes[team][key], model_matrix(e.x, bob, e.z, rot_y=rot), emissive=emis)
            weapon = m.minion_weapons[team].get(key)
            if weapon:
                # 무기는 손을 축으로 따로 그려, 공격할 때 뒤로 젖혔다가 앞으로 휘두른다
                wmesh, (px, py, pz) = weapon
                c, s_ = math.cos(rot), math.sin(rot)
                wx, wz = c * px + s_ * pz, -s_ * px + c * pz
                r.draw(wmesh, model_matrix(e.x + wx, bob + py, e.z + wz, rot_y=rot,
                                           rot_x=self.swing_angle(now - e.swing_t)), emissive=emis)

        # 챔피언
        for cid, e in self.champs.items():
            d = e.d
            if not d or d["dead"] or not e.visible:
                continue
            info = self.champ_info[cid]
            mesh = m.champion(info["c"])
            if cid == self.my_id:
                ring_col = (0.6, 1.0, 0.3, 0.9)
            elif info["tm"] == self.my_team:
                ring_col = (0.3, 0.6, 1.0, 0.85)
            else:
                ring_col = (1.0, 0.3, 0.3, 0.85)
            r.draw_transparent(m.shadow, model_matrix(e.x, 0.03, e.z, scale=0.65), (0, 0, 0, 0.35))
            r.draw_transparent(m.ring, model_matrix(e.x, 0.05, e.z, scale=0.85), ring_col)
            anim = d["a"]
            bob = abs(math.sin(t * 10 + cid)) * 0.06 if anim == 1 else 0.0
            tilt = 0.08 if anim == 1 else 0.0
            tint = (1, 1, 1, 1)
            emis = [0.0, 0.0, 0.0]
            if "slow" in d["st"]:
                tint = (0.75, 0.85, 1.15, 1)
            if "buff" in d["st"]:
                emis = [0.05, 0.12, 0.25]
            if cid == hov_id:
                emis = [v + 0.15 for v in emis]
            r.draw(mesh, model_matrix(e.x, bob, e.z, rot_y=facing_to_rot(e.f), rot_x=tilt), tint=tint,
                   emissive=emis)
            if "stun" in d["st"]:
                for k in range(3):
                    a = t * 5 + k * math.tau / 3
                    r.draw(m.orb, model_matrix(e.x + math.cos(a) * 0.4, 2.15, e.z + math.sin(a) * 0.4, scale=0.08),
                           tint=(1, 0.9, 0.3, 1), unlit=1.0)
            if d.get("rc", 0) > 0:
                # 귀환 중: 발밑 원 + 위로 올라가는 고리
                k = 1 - d["rc"] / RECALL_TIME
                r.draw_transparent(m.disc, model_matrix(e.x, 0.06, e.z, scale=1.1), (0.35, 0.6, 1.0, 0.25 + 0.2 * k),
                                   additive=True)
                for j in range(2):
                    ph = (t * 0.8 + j * 0.5) % 1.0
                    r.draw_transparent(m.ring, model_matrix(e.x, 0.1 + ph * 2.2, e.z, scale=0.9),
                                       (0.45, 0.7, 1.0, 0.8 * (1 - ph)), additive=True)
            if "emp" in d["st"]:
                r.draw_transparent(m.orb, model_matrix(e.x, 1.0, e.z, scale=0.9), (0.5, 0.85, 1.0, 0.18), additive=True)

        # 투사체
        for p in self.projs.values():
            age = min(0.15, now - p["t"])
            x, z = p["x"] + p["vx"] * age, p["z"] + p["vz"] * age
            mesh = m.proj.get(p["style"], m.proj["minion_bolt"])
            y = 3.2 if p["style"] == "turret_shot" else 1.1
            if p["style"] in ("minion_bolt", "cannon_ball"):
                y = 0.8
            rot = math.atan2(p["dx"], p["dz"])
            emis = (0.3, 0.3, 0.3) if p["style"] in ("frost_arrow", "turret_shot", "snowball") else (0, 0, 0)
            tint = (1, 1, 1, 1)
            if p["style"] in ("minion_bolt", "cannon_ball"):
                # 미니언 투사체는 팀 색 (블루 / 레드)
                tint = (0.4, 0.65, 1.0, 1) if p["team"] == BLUE else (1.0, 0.4, 0.35, 1)
                emis = (0.1, 0.2, 0.45) if p["team"] == BLUE else (0.45, 0.12, 0.1)
            r.draw(mesh, model_matrix(x, y, z, rot_y=rot), tint=tint, emissive=emis)

        # 장판 (궁극기 예고 등)
        for row, recv in self.ground_effects:
            eid, style, team, x, z, radius, remaining = row
            left = remaining - (now - recv)
            pulse = 0.25 + 0.15 * math.sin(t * 12)
            col = (0.6, 0.9, 1.0) if team == self.my_team else (1.0, 0.45, 0.35)
            r.draw_transparent(m.disc, model_matrix(x, 0.06, z, scale=radius), (*col, pulse))
            r.draw_transparent(m.ring, model_matrix(x, 0.07, z, scale=radius), (*col, 0.9))
            if left > 0:
                r.draw_transparent(m.disc, model_matrix(x, 0.08, z, scale=radius * max(0.0, 1 - left / 0.8)),
                                   (*col, 0.35))

        # 로컬 이펙트
        for f in self.fx:
            k = (now - f["t"]) / f["dur"]
            col = f["color"]
            if f["kind"] == "burst":
                r.draw_transparent(m.disc, model_matrix(f["x"], 0.09, f["z"], scale=f["r"] * (0.4 + 0.6 * k)),
                                   (*col, 0.6 * (1 - k)), additive=True)
                r.draw_transparent(m.ring, model_matrix(f["x"], 0.1, f["z"], scale=f["r"] * (0.6 + 0.6 * k)),
                                   (*col, 1 - k), additive=True)
            elif f["kind"] == "ring_up":
                r.draw_transparent(m.ring, model_matrix(f["x"], 0.1 + k * 1.5, f["z"], scale=f["r"] * (1 - 0.3 * k)),
                                   (*col, 1 - k), additive=True)
            elif f["kind"] == "poof":
                r.draw_transparent(m.orb, model_matrix(f["x"], 1.0, f["z"], scale=0.25 + k * 0.6),
                                   (*col, 0.6 * (1 - k)), additive=True)
            elif f["kind"] == "shards":
                for i in range(10):
                    a = i / 10 * math.tau + f["x"]
                    rr = f["r"] * (0.2 + 0.8 * ((i * 37) % 10) / 10)
                    r.draw(m.relic, model_matrix(f["x"] + math.cos(a) * rr, (1 - k) * 2.5, f["z"] + math.sin(a) * rr,
                                                 scale=0.4, rot_y=a), tint=(0.8, 0.95, 1.2, 1), emissive=(0.3, 0.4, 0.5))

        # 클릭 표시 (줄어드는 고리) + 도착할 때까지 남는 목적지 표시
        if self.click_marker:
            x, z, ct = self.click_marker
            k = (now - ct) / 0.45
            if k < 1:
                col = MOVE_COLOR
                r.draw_transparent(m.ring, model_matrix(x, 0.06, z, scale=0.9 * (1 - k) + 0.15), (*col, 1 - k),
                                   additive=True)
                r.draw_transparent(m.disc, model_matrix(x, 0.055, z, scale=0.35 * (1 - k) + 0.05),
                                   (*col, 0.6 * (1 - k)), additive=True)
        if self.move_dest:
            x, z = self.move_dest
            pulse = 0.5 + 0.2 * math.sin(t * 6)
            r.draw_transparent(m.ring, model_matrix(x, 0.06, z, scale=0.32), (*MOVE_COLOR, pulse), additive=True)
            r.draw_transparent(m.disc, model_matrix(x, 0.055, z, scale=0.08), (*MOVE_COLOR, 0.9), additive=True)

        self.draw_indicators()

    @staticmethod
    def swing_angle(age, dur=0.45):
        """미니언 무기 휘두르기 각도: 뒤로 젖혔다가(-) 앞으로 내려친 뒤(+) 제자리로."""
        if age < 0 or age > dur:
            return 0.0
        k = age / dur
        if k < 0.3:
            return -0.7 * (k / 0.3)
        if k < 0.55:
            p = (k - 0.3) / 0.25
            return -0.7 + 2.0 * (1 - (1 - p) ** 2)
        return 1.3 * (1 - (k - 0.55) / 0.45)

    def draw_indicators(self):
        r = self.app.renderer
        m = self.app.models
        me = self.champs.get(self.my_id)
        if not me or not me.d or me.d["dead"]:
            return
        if self.amove_pending:
            rng = 5.5
            data = self.my_data()
            if data:
                rng = data["stats"]["attack_range"] + 0.55
            r.draw_transparent(m.ring_thin, model_matrix(me.x, 0.06, me.z, scale=rng), (1.0, 0.5, 0.4, 0.8))
        # 조준 중인 스킬, 아니면 마우스를 올린 스킬 아이콘의 범위와 조준 바를 보여준다 (롤과 같은 방식)
        slot = self.aiming or self.hover_slot
        if not slot:
            return
        spell = self.binds.spell_at(slot) if slot in ("D", "F") else None
        if spell == "D":
            ab = {"type": "dash", "range": FLASH_RANGE, "width": 0.0}
        elif spell == "F":
            ab = {"type": "skillshot", "range": MARK_RANGE, "width": 0.7}
        else:
            ab = self.my_data()["abilities"][slot]
        mx, mz = self.mouse_ground()
        dx, dz = mx - me.x, mz - me.z
        dist = math.hypot(dx, dz) or 1.0
        ang = math.atan2(dx, dz)
        # 재사용 대기 중이면 빨간색
        cd = me.d["cd"].get(spell or slot, 0) if me.d else 0
        if spell == "F" and me.d and me.d["mk"]:
            cd = 0                          # 표식 적중 후 돌진(재사용)은 가능
        col = (1.0, 0.32, 0.28) if cd > 0 else (0.55, 0.85, 1.0)
        if ab["type"] in ("skillshot", "dash"):
            r.draw_transparent(m.ring_thin, model_matrix(me.x, 0.06, me.z, scale=ab["range"]), (*col, 0.45))
            length = ab["range"] if ab["type"] == "skillshot" else min(dist, ab["range"])
            width = ab.get("width", 0.9)
            if width > 0:
                r.draw_transparent(self.quad, model_matrix(me.x, 0.07, me.z, rot_y=ang, sx=width, sy=1, sz=length),
                                   (*col, 0.35))
            if ab["type"] == "dash":
                ex, ez = me.x + dx / dist * length, me.z + dz / dist * length
                r.draw_transparent(m.ring, model_matrix(ex, 0.08, ez, scale=0.6), (*col, 0.9))
        elif ab["type"] == "self_buff":
            r.draw_transparent(m.ring, model_matrix(me.x, 0.07, me.z, scale=1.2), (*col, 0.8))
        elif ab["type"] == "ground_aoe":
            r.draw_transparent(m.ring_thin, model_matrix(me.x, 0.06, me.z, scale=ab["range"]), (*col, 0.6))
            k = min(1.0, ab["range"] / dist)
            ex, ez = me.x + dx * k, me.z + dz * k
            r.draw_transparent(m.disc, model_matrix(ex, 0.07, ez, scale=ab["radius"]), (*col, 0.25))
            r.draw_transparent(m.ring, model_matrix(ex, 0.08, ez, scale=ab["radius"]), (*col, 0.9))

    # ------------------------------------------------------------------ 2D
    def draw_ui(self, surf):
        self.draw_world_bars(surf)
        self.draw_floaters(surf)
        self.draw_top(surf)
        self.draw_killfeed(surf)
        self.draw_announces(surf)
        self.draw_hud(surf)
        self.draw_minimap(surf)
        self.draw_chat(surf)
        me = self.me
        if me and me["dead"] and self.winner is None:
            shade = pygame.Surface((WIDTH, 120), pygame.SRCALPHA)
            shade.fill((20, 20, 30, 150))
            surf.blit(shade, (0, 230))
            ui.text(surf, f"부활까지 {math.ceil(me['rt'])}초", (WIDTH // 2, 270), 34, (230, 230, 240), anchor="center",
                    bold=True)
        if me and not me["dead"] and me.get("rc", 0) > 0:
            k = 1 - me["rc"] / RECALL_TIME
            r = pygame.Rect(WIDTH // 2 - 130, 560, 260, 14)
            ui.bar(surf, r, k, (90, 150, 255))
            ui.text(surf, f"귀환 {me['rc']:.1f}", (r.centerx, r.y - 3), 14, anchor="midbottom", bold=True)
        if self.shop_open:
            self.draw_shop(surf)
        if self.show_score:
            self.draw_scoreboard(surf)
        if self.winner is not None:
            self.draw_game_over(surf)
        if self.hud_tooltip and not self.settings_open:
            mouse, tip = self.hud_tooltip
            self.draw_tooltip(surf, mouse, *tip)
        if self.settings_open:
            self.draw_settings(surf)

    def draw_world_bars(self, surf):
        cam = self.app.renderer.camera
        for sid, s in self.structs.items():
            st = self.struct_state[sid]
            if not st[2]:
                continue
            h = {"turret": 5.2, "inhibitor": 2.8, "nexus": 5.0}[s["k"]]
            p = cam.world_to_screen(s["x"], h, s["z"])
            if not p:
                continue
            col = ui.TEAM_UI[s["tm"]] if s["tm"] != self.my_team else (90, 170, 255)
            if s["tm"] != self.my_team:
                col = (230, 70, 60)
            w = 90 if s["k"] != "nexus" else 120
            x0 = int(p[0] - w // 2)
            ui.bar(surf, (x0, p[1], w, 9), st[1] / s["mhp"], col)
            # 포탑은 방패(골드) 한 칸 간격, 나머지 구조물은 1000 단위
            unit = s["mhp"] / s["pl"] if s.get("pl") else 1000
            self.draw_hp_ticks(surf, x0, int(p[1]), w, 9 if s.get("pl") else 5, st[1], s["mhp"], unit)
            if not st[3]:
                ui.text(surf, "무적", (p[0], p[1] - 4), 12, ui.TEXT_DIM, anchor="midbottom")
        for mid, e in self.minions.items():
            row = e.d
            if row[6] >= row[7]:
                continue
            p = cam.world_to_screen(e.x, MINION_HEIGHT[row[1]] + 0.2, e.z)
            if p:
                col = (90, 170, 255) if row[2] == self.my_team else (230, 70, 60)
                ui.bar(surf, (p[0] - 18, p[1], 36, 5), row[6] / row[7], col)
        for cid, e in self.champs.items():
            d = e.d
            if not d or d["dead"] or not e.visible:
                continue
            p = cam.world_to_screen(e.x, 2.45, e.z)
            if not p:
                continue
            info = self.champ_info[cid]
            if cid == self.my_id:
                col = (120, 220, 80)
            elif info["tm"] == self.my_team:
                col = (90, 170, 255)
            else:
                col = (230, 70, 60)
            x0, y0 = int(p[0] - 52), int(p[1])
            pygame.draw.rect(surf, (10, 10, 16, 220), (x0 - 22, y0 - 2, 128, 21))
            pygame.draw.rect(surf, (30, 30, 40, 255), (x0 - 22, y0 - 2, 20, 21))
            ui.text(surf, str(d["lv"]), (x0 - 12, y0 + 8), 13, ui.TEXT, anchor="center", bold=True, shadow=False)
            ui.bar(surf, (x0, y0, 104, 11), d["hp"] / max(1, d["mhp"]), col, border=None)
            self.draw_hp_ticks(surf, x0, y0, 104, 5, d["hp"], d["mhp"], 250)
            ui.bar(surf, (x0, y0 + 12, 104, 5), d["mp"] / max(1, d["mmp"]), (80, 140, 255), border=None)
            ui.text(surf, info["n"], (p[0], y0 - 4), 13, ui.TEXT, anchor="midbottom")

    @staticmethod
    def draw_hp_ticks(surf, x0, y0, w, h, hp, mhp, unit):
        """체력바에 unit 체력마다 눈금선을 긋는다 (남은 체력 부분에만)."""
        if mhp <= 0:
            return
        step = w * unit / mhp
        xx = x0 + step
        while xx < x0 + w * hp / mhp:
            pygame.draw.line(surf, (0, 0, 0), (int(xx), y0), (int(xx), y0 + h))
            xx += step

    def draw_floaters(self, surf):
        cam = self.app.renderer.camera
        now = time.time()
        for f in self.floaters:
            k = (now - f["t"]) / f["dur"]
            p = cam.world_to_screen(f["x"], 2.0 + k * 1.2, f["z"])
            if p:
                ui.text(surf, f["text"], p, f["size"], f["color"], anchor="center", bold=True)

    def draw_top(self, surf):
        # 롤처럼 우측 상단: 팀 킬 (우리 vs 상대) | 내 K/D/A | 경기 시간
        r = pygame.Rect(WIDTH - 286, 6, 280, 32)
        ui.panel(surf, r, (14, 20, 34, 120), None, radius=4)
        y = r.centery
        ours, theirs = self.my_team, 1 - self.my_team
        ui.text(surf, str(self.score[ours]), (r.x + 30, y), 18, ui.TEAM_UI[ours], anchor="center", bold=True)
        ui.text(surf, "vs", (r.x + 55, y), 12, ui.TEXT_DIM, anchor="center")
        ui.text(surf, str(self.score[theirs]), (r.x + 80, y), 18, ui.TEAM_UI[theirs], anchor="center", bold=True)
        pygame.draw.line(surf, (50, 56, 70), (r.x + 106, r.y + 6), (r.x + 106, r.bottom - 6))
        me = self.me
        if me:
            ui.text(surf, f"{me['k']}/{me['d']}/{me['as']}", (r.x + 158, y), 15, anchor="center", bold=True)
        pygame.draw.line(surf, (50, 56, 70), (r.x + 210, r.y + 6), (r.x + 210, r.bottom - 6))
        mm, ss = divmod(int(self.server_time), 60)
        ui.text(surf, f"{mm:02d}:{ss:02d}", (r.right - 35, y), 16, anchor="center", bold=True)

    def draw_killfeed(self, surf):
        now = time.time()
        y = 48
        for t, ev in self.killfeed:
            if now - t > 8:
                continue
            kc = ui.TEAM_UI.get(ev["kt"], ui.TEXT)
            vc = ui.TEAM_UI.get(ev["vt"], ui.TEXT)
            kw = ui.font(14).size(ev["kn"])[0]
            vw = ui.font(14).size(ev["vn"])[0]
            w = kw + vw + 64
            x0 = WIDTH - 6 - w
            ui.panel(surf, (x0, y - 2, w, 26), (14, 20, 34, 120), None, radius=4)
            ui.text(surf, ev["kn"], (x0 + 10, y + 11), 14, kc, anchor="midleft")
            ui.text(surf, "▶", (x0 + 10 + kw + 20, y + 11), 12, ui.TEXT_DIM, anchor="center")
            ui.text(surf, ev["vn"], (x0 + 10 + kw + 40, y + 11), 14, vc, anchor="midleft")
            y += 30

    def draw_chat(self, surf):
        """왼쪽 아래 채팅창. 닫혀 있으면 최근 줄만 잠깐 보이고 흐려진다."""
        now = time.time()
        if self.chat_open:
            lines = self.chat_lines[-10:]
            bg = pygame.Surface((CHAT_W, 10 * 19 + 8), pygame.SRCALPHA)
            bg.fill((8, 12, 22, 140))
            surf.blit(bg, (CHAT_X, CHAT_Y - 10 * 19 - 10))
        else:
            lines = [ln for ln in self.chat_lines[-8:] if now - ln[0] < CHAT_SHOW]
        y = CHAT_Y - 6
        for t, parts in reversed(lines):
            fade = 1.0 if self.chat_open else min(1.0, (CHAT_SHOW - (now - t)) / 2.0)
            x = CHAT_X + 6
            for text, col in parts:
                c = tuple(int(v * (0.35 + 0.65 * fade)) for v in col)
                x = ui.text(surf, text, (x, y), 14, c, anchor="bottomleft").right
            y -= 19
        if self.chat_open:
            self.chat_in.draw(surf)

    def draw_announces(self, surf):
        now = time.time()
        y = 110
        for t, text, col in self.announces:
            ui.text(surf, text, (WIDTH // 2, y), 24, col, anchor="center", bold=True)
            y += 34

    # ---- 하단 HUD
    def draw_hud(self, surf):
        me = self.me
        data = self.my_data()
        self.levelup_rects = []
        if not me or not data:
            return
        ui.panel(surf, HUD_RECT, (14, 20, 34, 235), ui.BORDER)
        # 초상화
        col = tuple(data.get("color", (200, 200, 200)))
        pygame.draw.circle(surf, col, (338, 650), 30)
        pygame.draw.circle(surf, (230, 230, 240), (338, 650), 30, 2)
        ui.text(surf, data["name"][0], (338, 650), 26, (20, 30, 50), anchor="center", bold=True, shadow=False)
        pygame.draw.circle(surf, (20, 25, 40), (360, 678), 13)
        ui.text(surf, str(me["lv"]), (360, 678), 14, anchor="center", bold=True)
        # 경험치
        xp_ratio = me["xp"] / max(1, me["xpn"]) if me["lv"] < 18 else 1
        pygame.draw.arc(surf, (180, 120, 255), (306, 618, 64, 64), -math.pi / 2, -math.pi / 2 + math.tau * xp_ratio, 3)

        # 스킬
        mouse = ui.mouse_pos()
        tooltip = None
        for slot in SLOTS:
            x = ABILITY_X[slot]
            rect = pygame.Rect(x, 614, 54, 54)
            ab = data["abilities"][slot]
            rank = me["ab"][slot]
            cd = me["cd"][slot]
            mana_ok = rank > 0 and me["mp"] >= ab.get("mana", [0])[rank - 1]
            base = (40, 70, 110) if rank > 0 else (35, 38, 48)
            pygame.draw.rect(surf, base, rect, border_radius=6)
            ui.text(surf, ab["name"][:2], rect.center, 16, (220, 235, 255) if rank else ui.TEXT_DIM, anchor="center",
                    bold=True)
            if rank > 0 and cd > 0:
                sh = pygame.Surface(rect.size, pygame.SRCALPHA)
                sh.fill((0, 0, 0, 160))
                surf.blit(sh, rect)
                ui.text(surf, f"{cd:.0f}" if cd >= 1 else f"{cd:.1f}", rect.center, 20, anchor="center", bold=True)
            elif rank > 0 and not mana_ok:
                sh = pygame.Surface(rect.size, pygame.SRCALPHA)
                sh.fill((20, 40, 140, 140))
                surf.blit(sh, rect)
            border = ui.HIGHLIGHT if self.aiming == slot else ui.BORDER
            pygame.draw.rect(surf, border, rect, 2 if self.aiming == slot else 1, border_radius=6)
            ui.text(surf, self.binds.name(slot), (x + 3, 614), 12, ui.GOLD, bold=True)
            # 랭크 표시
            maxr = len(ab["cooldown"])
            for i in range(maxr):
                px = x + 4 + i * (46 / maxr)
                pygame.draw.rect(surf, (255, 210, 90) if i < rank else (60, 64, 76), (int(px), 671, int(46 / maxr) - 2, 4))
            # 레벨업 버튼
            if me["sp"] > 0 and rank < self.max_rank(slot, me["lv"]):
                lr = pygame.Rect(x + 15, 588, 24, 22)
                pygame.draw.rect(surf, (230, 190, 70), lr, border_radius=4)
                ui.text(surf, "+", lr.center, 18, (40, 30, 10), anchor="center", bold=True, shadow=False)
                self.levelup_rects.append((slot, lr))
            if rect.collidepoint(mouse):
                cost = ab.get("mana", [0])[max(0, rank - 1)]
                tooltip = (f"[{self.binds.name(slot)}] {ab['name']}  ·  마나 {cost}  ·  "
                           f"{ab['cooldown'][max(0, rank - 1)]}초", ab.get("desc", ""), ability_details(ab), rank)
        # 소환사 주문
        for slot in ("D", "F"):
            sid = self.binds.spell_at(slot)
            name, col, desc, details = SPELL_INFO[sid]
            marked = sid == "F" and me["mk"]
            x = SPELL_X[slot]
            rect = pygame.Rect(x, 619, 44, 44)
            pygame.draw.rect(surf, col, rect, border_radius=6)
            ui.text(surf, name, rect.center, 14, anchor="center", bold=True)
            cd = me["cd"][sid]
            if marked:
                pygame.draw.rect(surf, ui.HIGHLIGHT, rect, 3, border_radius=6)     # 재사용(돌진) 가능
            elif cd > 0:
                sh = pygame.Surface(rect.size, pygame.SRCALPHA)
                sh.fill((0, 0, 0, 170))
                surf.blit(sh, rect)
                ui.text(surf, f"{cd:.0f}", rect.center, 17, anchor="center", bold=True)
            if not marked:
                pygame.draw.rect(surf, ui.BORDER, rect, 1, border_radius=6)
            ui.text(surf, self.binds.name(slot), (x + 3, 619), 11, ui.GOLD, bold=True)
            if rect.collidepoint(mouse):
                tooltip = (f"[{self.binds.name(slot)}] {name}", desc, details, 0)

        # 체력 / 마나
        ui.bar(surf, (392, 680, 356, 15), me["hp"] / max(1, me["mhp"]), (70, 190, 70))
        ui.text(surf, f"{me['hp']} / {me['mhp']}", (570, 687), 12, anchor="center", shadow=True)
        ui.bar(surf, (392, 697, 356, 11), me["mp"] / max(1, me["mmp"]), (70, 120, 230))
        ui.text(surf, f"{me['mp']} / {me['mmp']}", (570, 702), 10, anchor="center", shadow=True)

        # 아이템
        self.hud_inv_rects = []
        for i in range(INVENTORY_SLOTS):
            x = 764 + (i % INV_COLS) * 37
            y = 616 + (i // INV_COLS) * 38
            rect = pygame.Rect(x, y, 34, 34)
            pygame.draw.rect(surf, (25, 30, 42), rect, border_radius=4)
            if i < len(me["it"]):
                it = gamedata.items()[me["it"][i]]
                draw_item(surf, me["it"][i], rect.inflate(-2, -2))
                self.hud_inv_rects.append((i, rect))
                if rect.collidepoint(mouse):
                    sell = round(it["cost"] * SELL_RATIO)
                    tooltip = (it["name"], f"{item_stat_text(it)}\n판매 시 {sell} G ({int(SELL_RATIO * 100)}%)"
                               + ("  ·  우클릭으로 판매" if self.shop_open else ""))
            pygame.draw.rect(surf, ui.BORDER, rect, 1, border_radius=4)
        self.gold_rect = ui.text(surf, f"{me['g']} G", (914, 706), 18, ui.GREEN_C if me.get("shop") else ui.GOLD,
                                 anchor="bottomleft", bold=True)

        # 능력치
        st = me["s"]
        ui.panel(surf, (160, 606, 136, 108), (14, 20, 34, 225), ui.BORDER)
        for i, (key, label, value) in enumerate(STAT_ICONS):
            x = 168 + (i % 2) * 64
            y = 614 + (i // 2) * 24
            icon_rect = pygame.Rect(x, y, 20, 20)
            icon = ui.icon(f"assets/ui/stats/{key}.png", 20)
            if icon:
                surf.blit(icon, icon_rect)
            else:
                col, ch = STAT_FALLBACK[key]
                pygame.draw.rect(surf, col, icon_rect, border_radius=4)
                ui.text(surf, ch, icon_rect.center, 12, (20, 20, 30), anchor="center", bold=True, shadow=False)
            ui.text(surf, str(value(st)), (x + 26, y + 10), 13, anchor="midleft", shadow=False)
            if pygame.Rect(x, y, 60, 20).collidepoint(mouse):
                tooltip = (label, "")

        self.hud_tooltip = (mouse, tooltip) if tooltip else None

    def draw_tooltip(self, surf, mouse, title, body, details=None, rank=0):
        """HUD 툴팁. details 가 있으면 Shift 를 누르고 있는 동안 상세 값(레벨별 값은 현재 레벨 강조)을 보여준다."""
        shift = bool(details) and bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        lines = ui.wrap(body, 13, 320) if body else []
        h = 30 + len(lines) * 17 + (10 + len(details) * 20 if shift else 0)
        w = (400 if shift else 340) if body else ui.font(14, True).size(title)[0] + 20
        r = pygame.Rect(0, 0, w, h)
        r.bottomleft = (mouse[0] - 20, 580 if body else mouse[1] - 8)
        r.x = max(4, min(WIDTH - w - 4, r.x))
        ui.panel(surf, r, (12, 18, 30, 245), ui.BORDER)
        ui.text(surf, title, (r.x + 10, r.y + 6), 14, ui.GOLD, bold=True)
        if details and not shift:
            ui.text(surf, "Shift 상세", (r.right - 10, r.y + 8), 11, ui.TEXT_DIM, anchor="topright")
        ui.text_block(surf, body, (r.x + 10, r.y + 26), 320, 13, ui.TEXT, 3)
        if not shift:
            return
        y = r.y + 30 + len(lines) * 17 + 4
        pygame.draw.line(surf, (50, 60, 80), (r.x + 10, y), (r.right - 10, y))
        y += 6
        for label, value in details:
            ui.text(surf, label, (r.x + 10, y), 13, ui.TEXT_DIM)
            if isinstance(value, list):
                x = r.x + 150
                for i, v in enumerate(value):
                    cur = i == rank - 1
                    x = ui.text(surf, v, (x, y), 13, ui.GOLD if cur else ui.TEXT, bold=cur).right
                    if i < len(value) - 1:
                        x = ui.text(surf, " / ", (x, y), 13, ui.TEXT_DIM).right
            else:
                ui.text(surf, value, (r.x + 150, y), 13, ui.TEXT)
            y += 20

    # ---- 미니맵
    def world_to_minimap(self, x, z):
        mx = MINIMAP.x + 8 + (x + MINIMAP_X) / (2 * MINIMAP_X) * (MINIMAP.width - 16)
        my = MINIMAP.centery + z / 13 * (MINIMAP.height / 2 - 6)
        return int(mx), int(my)

    def minimap_to_world(self, sx, sy):
        x = (sx - MINIMAP.x - 8) / (MINIMAP.width - 16) * (2 * MINIMAP_X) - MINIMAP_X
        z = (sy - MINIMAP.centery) / (MINIMAP.height / 2 - 6) * 13
        return mapdata.clamp_to_map(x, z)

    def draw_minimap(self, surf):
        ui.panel(surf, MINIMAP, (10, 14, 24, 235), ui.BORDER, radius=4)
        pts_top, pts_bot = [], []
        x = -mapdata.LANE_END
        while x <= mapdata.LANE_END + 1e-6:
            hw = mapdata.half_width(x)
            pts_top.append(self.world_to_minimap(x, -hw))
            pts_bot.append(self.world_to_minimap(x, hw))
            x += 4.0
        pygame.draw.polygon(surf, (70, 85, 105), pts_top + pts_bot[::-1])
        for sid, s in self.structs.items():
            st = self.struct_state[sid]
            col = ui.TEAM_UI[s["tm"]] if st[2] else (60, 60, 70)
            p = self.world_to_minimap(s["x"], s["z"])
            size = 4 if s["k"] == "turret" else 6
            pygame.draw.rect(surf, col, (p[0] - size // 2, p[1] - size // 2, size, size))
        for rid, x, z, active in self.relics:
            if active:
                pygame.draw.circle(surf, (90, 230, 120), self.world_to_minimap(x, z), 3)
        for e in self.minions.values():
            col = (120, 170, 255) if e.d[2] == BLUE else (255, 120, 110)
            p = self.world_to_minimap(e.x, e.z)
            pygame.draw.rect(surf, col, (p[0] - 1, p[1] - 1, 2, 2))
        if self.minimap_fog:
            surf.blit(self.minimap_fog[0], self.minimap_fog[1])
        for cid, e in self.champs.items():
            if not e.d or e.d["dead"] or not e.visible:
                continue
            info = self.champ_info[cid]
            p = self.world_to_minimap(e.x, e.z)
            pygame.draw.circle(surf, ui.TEAM_UI[info["tm"]], p, 5)
            pygame.draw.circle(surf, (255, 230, 100) if cid == self.my_id else (20, 20, 30), p, 5, 2 if cid == self.my_id else 1)
        # 내 이동 경로
        me = self.champs.get(self.my_id)
        if self.move_dest and me:
            a = self.world_to_minimap(me.x, me.z)
            b = self.world_to_minimap(*self.move_dest)
            pygame.draw.line(surf, MOVE_COLOR_UI, a, b, 1)
            pygame.draw.circle(surf, MOVE_COLOR_UI, b, 3)
        if self.click_marker and time.time() - self.click_marker[2] < 0.45:
            k = (time.time() - self.click_marker[2]) / 0.45
            p = self.world_to_minimap(self.click_marker[0], self.click_marker[1])
            pygame.draw.circle(surf, MOVE_COLOR_UI, p, int(9 - 6 * k), 1)
        cam = self.app.renderer.camera
        a = self.world_to_minimap(cam.tx - 14, cam.tz - 8)
        b = self.world_to_minimap(cam.tx + 14, cam.tz + 8)
        pygame.draw.rect(surf, (220, 220, 230), (a[0], a[1], b[0] - a[0], b[1] - a[1]), 1)

    # ---- 상점
    def shop_panel(self):
        return pygame.Rect(WIDTH // 2 - 380, 90, 760, 400)

    def draw_shop(self, surf):
        me = self.me
        p = self.shop_panel()
        ui.panel(surf, p, (12, 18, 30, 245), ui.BORDER)
        ui.text(surf, "상점", (p.x + 20, p.y + 14), 24, bold=True)
        can = me and me.get("shop")
        if not can:
            ui.text(surf, "우물 / 사망 시 구매 가능", (p.x + 90, p.y + 22), 14, ui.RED_C)
        if me:
            ui.text(surf, f"{me['g']} G", (p.right - 20, p.y + 16), 22, ui.GOLD, anchor="topright", bold=True)
        self.shop_rects = []
        mouse = ui.mouse_pos()
        cols = 3
        cw = (p.width - 40) // cols
        for i, (iid, it) in enumerate(gamedata.items().items()):
            x = p.x + 20 + (i % cols) * cw
            y = p.y + 60 + (i // cols) * 66
            rect = pygame.Rect(x, y, cw - 10, 60)
            affordable = me and me["g"] >= it["cost"] and len(me["it"]) < INVENTORY_SLOTS
            hover = rect.collidepoint(mouse)
            ui.panel(surf, rect, (40, 60, 95, 240) if hover else (22, 32, 50, 230),
                     ui.HIGHLIGHT if hover else ui.BORDER, radius=5)
            draw_item(surf, iid, (x + 8, y + 10, 40, 40))
            ui.text(surf, it["name"], (x + 58, y + 6), 15, ui.TEXT if affordable else ui.TEXT_DIM, bold=True)
            ui.text(surf, f"{it['cost']} G", (rect.right - 8, y + 6), 14, ui.GOLD if affordable else (150, 110, 90),
                    anchor="topright")
            ui.text_block(surf, item_stat_text(it), (x + 58, y + 28), cw - 80, 12, ui.TEXT_DIM, 1)
            self.shop_rects.append((iid, rect))

    # ---- 점수판
    def draw_scoreboard(self, surf):
        """Tab 점수판 (롤처럼): 위에 팀 요약, 아래 블루팀은 왼쪽 / 레드팀은 오른쪽에 플레이어별 정보.

        시야와 상관없이 모두 보인다 (레벨, K/D/A, CS, 아이템, 골드).
        """
        items = gamedata.items()
        per_team = max(sum(1 for c in self.champ_info.values() if c["tm"] == t) for t in (BLUE, RED))
        p = pygame.Rect(WIDTH // 2 - 600, 70, 1200, 82 + per_team * 90)
        ui.panel(surf, p, (10, 14, 24, 238), ui.BORDER)
        mouse = ui.mouse_pos()
        col_w = (p.width - 36) // 2
        cols = {BLUE: p.x + 12, RED: p.x + 24 + col_w}

        # ---- 위쪽 요약: 블루 킬 · 골드 · 포탑 | 시간 | 레드 ...
        rows_by_team = {team: [self.board[cid] for cid in self.champ_info
                               if self.champ_info[cid]["tm"] == team and cid in self.board] for team in (BLUE, RED)}
        towers = {team: sum(1 for sid, st in self.structs.items()
                            if st["k"] == "turret" and st["tm"] != team and not self.struct_state[sid][2])
                  for team in (BLUE, RED)}
        cy = p.y + 30
        for team in (BLUE, RED):
            rows = rows_by_team[team]
            total = sum(r[6] + sum(items[i]["cost"] for i in r[7]) for r in rows)
            col = ui.TEAM_UI[team]
            left = team == BLUE
            x = cols[team] + (12 if left else col_w - 12)
            anchor = "midleft" if left else "midright"
            pygame.draw.rect(surf, col, (x - (0 if left else 4), cy - 10, 4, 20), border_radius=2)
            info = f"포탑 {towers[team]}   ·   {total:,} G"
            ix = x + (14 if left else -14)
            ui.text(surf, info, (ix, cy + 1), 15, ui.TEXT_DIM, anchor=anchor)
        mm, ss = divmod(int(self.server_time), 60)
        ui.text(surf, f"{self.score[BLUE]}", (p.centerx - 60, cy), 28, ui.BLUE_C, anchor="center", bold=True)
        ui.text(surf, f"{mm:02d}:{ss:02d}", (p.centerx, cy), 15, ui.TEXT_DIM, anchor="center")
        ui.text(surf, f"{self.score[RED]}", (p.centerx + 60, cy), 28, ui.RED_C, anchor="center", bold=True)
        pygame.draw.line(surf, (40, 50, 70), (p.x + 12, p.y + 58), (p.right - 12, p.y + 58))

        # ---- 플레이어 줄 (팀마다 한 열)
        tip = None
        for team in (BLUE, RED):
            x0 = cols[team]
            y = p.y + 70
            for cid, lv, k, dth, a, cs, gold, inv, dead, rt in rows_by_team[team]:
                info = self.champ_info[cid]
                ch = gamedata.champion(info["c"])
                row = pygame.Rect(x0, y, col_w, 84)
                mine = cid == self.my_id
                pygame.draw.rect(surf, (32, 46, 74) if mine else (18, 25, 40), row, border_radius=6)
                pygame.draw.rect(surf, ui.TEAM_UI[team], (row.x, row.y, 4, row.height), border_radius=2)
                if mine:
                    pygame.draw.rect(surf, ui.HIGHLIGHT, row, 1, border_radius=6)
                # 초상화 + 레벨 (사망 시 어둡게 + 부활 시간)
                pc = (row.x + 38, row.centery)
                face = tuple(ch.get("color", (200, 200, 200)))
                if dead:
                    face = tuple(v // 3 for v in face)
                pygame.draw.circle(surf, face, pc, 26)
                pygame.draw.circle(surf, ui.TEAM_UI[team], pc, 26, 2)
                ui.text(surf, ch["name"][0], pc, 22, (20, 30, 50) if not dead else (90, 90, 100), anchor="center",
                        bold=True, shadow=False)
                if dead:
                    ui.text(surf, f"{math.ceil(rt)}", pc, 18, ui.RED_C, anchor="center", bold=True)
                lvp = (pc[0] + 19, pc[1] + 19)
                pygame.draw.circle(surf, (14, 18, 28), lvp, 10)
                ui.text(surf, str(lv), lvp, 12, anchor="center", bold=True)
                # 이름 / 챔피언
                ui.text(surf, info["n"] + (" (나)" if mine else ""), (row.x + 76, row.centery - 11), 15,
                        ui.TEXT_DIM if dead else ui.TEXT, anchor="midleft", bold=True)
                ui.text(surf, ch["name"], (row.x + 76, row.centery + 12), 12, ui.TEXT_DIM, anchor="midleft")
                # K/D/A, CS
                ui.text(surf, f"{k} / {dth} / {a}", (row.x + 236, row.centery - 9), 16, anchor="center", bold=True)
                ui.text(surf, f"CS {cs}", (row.x + 236, row.centery + 13), 12, ui.TEXT_DIM, anchor="center")
                # 아이템 (인벤토리처럼 4칸 x 2줄)
                for i in range(INVENTORY_SLOTS):
                    ir = pygame.Rect(row.x + 300 + (i % INV_COLS) * 36, row.y + 7 + (i // INV_COLS) * 36, 34, 34)
                    pygame.draw.rect(surf, (10, 13, 20), ir, border_radius=4)
                    if i < len(inv):
                        draw_item(surf, inv[i], ir.inflate(-2, -2), 13)
                        if ir.collidepoint(mouse):
                            tip = (items[inv[i]]["name"], ir)
                    pygame.draw.rect(surf, ui.BORDER, ir, 1, border_radius=4)
                # 골드
                ui.text(surf, f"{gold:,} G", (row.right - 12, row.centery), 14, ui.GOLD, anchor="midright", bold=True)
                y += 90
        if tip:
            name, ir = tip
            w = ui.font(14, True).size(name)[0] + 20
            r = pygame.Rect(ir.centerx - w // 2, ir.y - 30, w, 26)
            ui.panel(surf, r, (12, 18, 30, 250), ui.BORDER, radius=4)
            ui.text(surf, name, r.center, 14, ui.GOLD, anchor="center", bold=True)

    def draw_game_over(self, surf):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 8, 16, 150))
        surf.blit(shade, (0, 0))
        win = self.winner == self.my_team
        ui.text(surf, "승리" if win else "패배", (WIDTH // 2, HEIGHT // 2 - 40), 96,
                (255, 220, 120) if win else (220, 90, 90), anchor="center", bold=True)
