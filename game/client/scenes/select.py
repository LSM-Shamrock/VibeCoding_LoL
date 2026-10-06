"""챔피언 선택: 챔피언 목록, 3D 모델 미리보기, 스킬 설명, 확정."""
import math
import time

import pygame

from ...shared import data as gamedata
from ...shared.constants import BLUE, RED, TEAM_NAMES
from .. import ui
from ..app import HEIGHT, WIDTH, Scene
from ..gl import model_matrix

KEYS = ("Q", "W", "E", "R")


class SelectScene(Scene):
    def on_enter(self):
        self.deadline = time.time() + (self.app.room or {}).get("select_left", 40)
        self.angle = 0.0
        self.preview = None
        self.card_rects = []
        self.btn_lock = ui.Button((WIDTH // 2 - 120, 498, 240, 46), "확정", self.lock, color=(40, 130, 80), size=20)
        # 처음엔 첫 번째 챔피언을 미리 선택해 둔다
        self.pick(gamedata.default_champion_id())

    def me(self):
        room = self.app.room
        if not room:
            return None
        return next((m for m in room["members"] if m["key"] == self.app.my_key), None)

    def pick(self, cid):
        self.preview = cid
        self.app.send({"t": "pick", "champ": cid})
        self.app.models.champion(cid)   # 모델 미리 로드

    def lock(self):
        self.app.send({"t": "lock"})

    def on_message(self, msg):
        if msg.get("t") == "room" and msg.get("phase") == "select":
            self.deadline = time.time() + msg.get("select_left", 0)

    def handle_event(self, e):
        if self.btn_lock.handle(e):
            return
        me = self.me()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and me and not me["locked"]:
            for cid, rect in self.card_rects:
                if rect.collidepoint(e.pos):
                    self.pick(cid)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            self.lock()

    def update(self, dt):
        self.angle += dt * 0.6
        me = self.me()
        self.btn_lock.enabled = bool(me and me["champ"] and not me["locked"])
        if me and me["locked"]:
            self.btn_lock.label = "확정 완료"

    def render3d(self):
        r = self.app.renderer
        cam = r.camera
        cam.tx, cam.ty, cam.tz = 0.0, 0.75, 0.0
        cam.distance = 6.0
        cam.pitch = math.radians(12)
        cam.yaw = 0.0
        r.begin_3d(cam, clear=(0.07, 0.1, 0.17))
        models = self.app.models
        r.draw(models.map, model_matrix(0, -0.02, 0))
        r.draw_transparent(models.disc, model_matrix(0, 0.02, 0, scale=1.4), (0.4, 0.7, 1.0, 0.35))
        r.draw_transparent(models.ring, model_matrix(0, 0.03, 0, scale=1.5), (0.6, 0.85, 1.0, 0.8), additive=True)
        if self.preview:
            bob = math.sin(self.app.time * 2) * 0.02
            r.draw(models.champion(self.preview), model_matrix(0, bob, 0, rot_y=self.angle))

    def draw_ui(self, surf):
        room = self.app.room
        if not room:
            return
        left = max(0, int(self.deadline - time.time()))
        ui.text(surf, "챔피언을 선택하세요", (WIDTH // 2, 36), 30, anchor="center", bold=True)
        ui.text(surf, f"{left}", (WIDTH // 2, 80), 34, ui.GOLD if left > 10 else ui.RED_C, anchor="center", bold=True)

        # 챔피언 목록
        ui.panel(surf, (24, 24, 300, 520))
        ui.text(surf, "챔피언", (44, 38), 18, bold=True)
        self.card_rects = []
        y = 74
        me = self.me()
        for cid, ch in gamedata.champions().items():
            rect = pygame.Rect(40, y, 268, 70)
            sel = me and me["champ"] == cid
            col = tuple(ch.get("color", (200, 200, 200)))
            ui.panel(surf, rect, (40, 60, 95, 240) if sel else (24, 34, 54, 230), col if sel else (60, 80, 110))
            pygame.draw.rect(surf, col, (rect.x + 10, rect.y + 10, 50, 50), border_radius=25)
            ui.text(surf, ch["name"][0], (rect.x + 35, rect.y + 35), 24, (20, 30, 50), anchor="center", bold=True,
                    shadow=False)
            ui.text(surf, ch["name"], (rect.x + 72, rect.y + 14), 18, bold=True)
            ui.text(surf, f"{ch['title']} · {ch.get('role', '')}", (rect.x + 72, rect.y + 40), 14, ui.TEXT_DIM)
            self.card_rects.append((cid, rect))
            y += 78
        ui.text(surf, "챔피언은 data/champions/*.json 을", (44, 480), 13, ui.TEXT_DIM)
        ui.text(surf, "추가하면 목록에 나타납니다.", (44, 498), 13, ui.TEXT_DIM)

        # 팀 목록
        ui.panel(surf, (WIDTH - 324, 24, 300, 520))
        y = 40
        for team in (BLUE, RED):
            ui.text(surf, TEAM_NAMES[team], (WIDTH - 304, y), 18, ui.TEAM_UI[team], bold=True)
            y += 30
            for m in room["members"]:
                if m["team"] != team:
                    continue
                champ = gamedata.champion(m["champ"]) if m["champ"] else None
                label = champ["name"] if champ else "선택 중..."
                ui.text(surf, m["name"] + (" (나)" if m["key"] == self.app.my_key else ""), (WIDTH - 300, y), 15)
                ui.text(surf, label, (WIDTH - 44, y), 15, ui.GREEN_C if m["locked"] else ui.TEXT_DIM, anchor="topright")
                y += 24
            y += 16

        # 스킬 설명
        ch = gamedata.champion(self.preview) if self.preview else None
        if ch:
            ui.panel(surf, (24, 560, WIDTH - 48, 140))
            ui.text(surf, f"{ch['name']} - {ch['title']}", (44, 572), 20, bold=True)
            p = ch.get("passive", {})
            entries = [("P", p.get("name", ""), p.get("desc", ""))]
            for k in KEYS:
                ab = ch["abilities"][k]
                entries.append((k, ab["name"], ab.get("desc", "")))
            colw = (WIDTH - 88) // 5
            for i, (k, name, desc) in enumerate(entries):
                x = 44 + i * colw
                pygame.draw.rect(surf, (50, 80, 130), (x, 604, 26, 26), border_radius=4)
                ui.text(surf, k, (x + 13, 617), 15, anchor="center", bold=True)
                ui.text(surf, name, (x + 34, 607), 15, ui.GOLD, bold=True)
                ui.text_block(surf, desc, (x, 636), colw - 14, 12, ui.TEXT_DIM, 2)

        self.btn_lock.draw(surf)
