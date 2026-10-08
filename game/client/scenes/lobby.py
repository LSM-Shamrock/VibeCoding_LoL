"""로비: 방 목록 / 방 만들기 / 입장."""
import pygame

from .. import ui
from ..app import HEIGHT, WIDTH, Scene

PHASE_NAMES = {"waiting": "대기 중", "select": "챔피언 선택", "ingame": "게임 중", "ended": "게임 종료"}


class LobbyScene(Scene):
    def on_enter(self):
        self.app.room = None
        self.selected = None
        self.last_click = 0
        self.refresh_t = 0.0
        self.name_in = ui.TextInput((820, 200, 360, 40), f"{self.app.my_name}의 방", 20, "방 이름")
        self.btn_create = ui.Button((820, 256, 360, 48), "방 만들기", self.create, color=(40, 110, 180))
        self.btn_join = ui.Button((90, 620, 200, 46), "입장", self.join, color=(40, 110, 180))
        self.btn_refresh = ui.Button((300, 620, 150, 46), "새로고침", self.refresh)
        self.btn_back = ui.Button((1030, 640, 150, 40), "접속 종료", self.back, color=(90, 45, 55))
        self.buttons = [self.btn_create, self.btn_join, self.btn_refresh, self.btn_back]
        self.row_rects = []
        self.refresh()

    def create(self):
        self.app.send({"t": "create_room", "name": self.name_in.value})

    def join(self, rid=None):
        rid = rid if rid is not None else self.selected
        if rid is not None:
            self.app.send({"t": "join_room", "id": rid})

    def refresh(self):
        self.app.send({"t": "list_rooms"})

    def back(self):
        from .title import TitleScene
        self.app.net.close()
        self.app.set_scene(TitleScene(self.app))

    def handle_event(self, e):
        self.name_in.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            now = pygame.time.get_ticks()
            for rid, rect in self.row_rects:
                if rect.collidepoint(e.pos):
                    # 같은 방을 빠르게 두 번 클릭하면 입장
                    if self.selected == rid and now - self.last_click < 400:
                        self.join(rid)
                    self.selected = rid
                    self.last_click = now

    def update(self, dt):
        self.refresh_t += dt
        if self.refresh_t > 3.0:
            self.refresh_t = 0
            self.refresh()
        self.btn_join.enabled = self.selected is not None and any(
            r["id"] == self.selected and r["phase"] == "waiting" and r["count"] < r["size"] * 2 for r in self.app.rooms)

    def draw_ui(self, surf):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 150))
        surf.blit(shade, (0, 0))
        ui.text(surf, "로비", (90, 50), 36, bold=True)
        ui.text(surf, f"{self.app.my_name} · 접속 주소 {self.app.share_addr}", (90, 100), 16, ui.TEXT_DIM)

        # 방 목록
        ui.panel(surf, (70, 140, 680, 460))
        ui.text(surf, "방 이름", (95, 156), 15, ui.TEXT_DIM)
        ui.text(surf, "방장", (380, 156), 15, ui.TEXT_DIM)
        ui.text(surf, "인원", (580, 156), 15, ui.TEXT_DIM)
        ui.text(surf, "상태", (650, 156), 15, ui.TEXT_DIM)
        self.row_rects = []
        y = 186
        if not self.app.rooms:
            ui.text(surf, "열린 방이 없습니다. 오른쪽에서 방을 만들어 보세요.", (410, 360), 17, ui.TEXT_DIM, anchor="center")
        for r in self.app.rooms[:12]:
            rect = pygame.Rect(82, y, 656, 32)
            sel = r["id"] == self.selected
            hover = rect.collidepoint(ui.mouse_pos())
            if sel or hover:
                pygame.draw.rect(surf, (50, 90, 150, 200) if sel else (40, 60, 90, 160), rect, border_radius=4)
            ui.text(surf, r["name"], (95, y + 16), 16, anchor="midleft")
            ui.text(surf, r["host"], (380, y + 16), 15, ui.TEXT_DIM, anchor="midleft")
            ui.text(surf, f"{r['count']}/{r['size'] * 2}", (580, y + 16), 15, anchor="midleft")
            col = ui.GREEN_C if r["phase"] == "waiting" else ui.GOLD
            ui.text(surf, PHASE_NAMES.get(r["phase"], r["phase"]), (650, y + 16), 15, col, anchor="midleft")
            self.row_rects.append((r["id"], rect))
            y += 34

        # 방 만들기
        ui.panel(surf, (800, 140, 400, 186))
        ui.text(surf, "새 방 만들기", (820, 156), 20, bold=True)
        self.name_in.draw(surf)
        for b in self.buttons:
            b.draw(surf)
