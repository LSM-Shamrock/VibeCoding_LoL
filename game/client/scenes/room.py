"""방: 팀 배치, 봇 추가/제거, 팀 인원 변경, 방장의 게임 시작."""
import pygame

from ...shared.constants import BLUE, MAX_TEAM_SIZE, RED, TEAM_NAMES
from .. import ui
from ..app import HEIGHT, WIDTH, Scene

COL_X = {BLUE: 110, RED: 690}
COL_W = 480
SLOT_H = 58


class RoomScene(Scene):
    def on_enter(self):
        self.btn_start = ui.Button((WIDTH // 2 - 130, 600, 260, 54), "게임 시작", self.start, color=(40, 130, 80), size=20)
        self.btn_leave = ui.Button((40, 650, 140, 40), "방 나가기", self.leave, color=(90, 45, 55))
        self.btn_minus = ui.Button((WIDTH // 2 - 90, 98, 36, 34), "-", lambda: self.set_size(-1))
        self.btn_plus = ui.Button((WIDTH // 2 + 54, 98, 36, 34), "+", lambda: self.set_size(1))
        self.slot_buttons = []

    @property
    def room(self):
        return self.app.room

    def is_host(self):
        return self.room and self.room["host"] == self.app.my_key

    def set_size(self, d):
        size = max(1, min(MAX_TEAM_SIZE, self.room["size"] + d))
        self.app.send({"t": "set_size", "size": size})

    def start(self):
        self.app.send({"t": "start_game"})

    def leave(self):
        from .lobby import LobbyScene
        self.app.send({"t": "leave_room"})
        self.app.set_scene(LobbyScene(self.app))

    def _build_slot_buttons(self):
        """방 상태에 따라 슬롯별 버튼(봇 추가/제거, 팀 이동)을 만든다."""
        btns = []
        room = self.room
        host = self.is_host()
        for team in (BLUE, RED):
            members = [m for m in room["members"] if m["team"] == team]
            for i in range(room["size"]):
                y = 170 + i * (SLOT_H + 8)
                x = COL_X[team]
                if i < len(members):
                    m = members[i]
                    if m["bot"] and host:
                        btns.append(ui.Button((x + COL_W - 90, y + 14, 76, 30), "제거",
                                              lambda k=m["key"]: self.app.send({"t": "remove_bot", "key": k}),
                                              color=(110, 50, 60), size=15))
                else:
                    if host:
                        btns.append(ui.Button((x + COL_W - 110, y + 14, 96, 30), "+ 봇 추가",
                                              lambda t=team: self.app.send({"t": "add_bot", "team": t}),
                                              color=(50, 90, 130), size=15))
                    me = next((m for m in room["members"] if m["key"] == self.app.my_key), None)
                    if me and me["team"] != team:
                        btns.append(ui.Button((x + 14, y + 14, 110, 30), "이 팀으로",
                                              lambda t=team: self.app.send({"t": "switch_team", "team": t}),
                                              color=(60, 70, 100), size=15))
        return btns

    def handle_event(self, e):
        if not self.room:
            return
        if self.btn_leave.handle(e):
            return
        if self.is_host():
            for b in (self.btn_start, self.btn_minus, self.btn_plus):
                if b.handle(e):
                    return
        for b in self.slot_buttons:
            if b.handle(e):
                return

    def update(self, dt):
        if not self.room:
            return
        self.slot_buttons = self._build_slot_buttons()
        teams = [sum(1 for m in self.room["members"] if m["team"] == t) for t in (BLUE, RED)]
        self.btn_start.enabled = self.is_host() and all(teams)
        self.btn_start.visible = self.is_host()
        self.btn_minus.visible = self.btn_plus.visible = self.is_host()

    def draw_ui(self, surf):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 160))
        surf.blit(shade, (0, 0))
        room = self.room
        if not room:
            return
        ui.text(surf, room["name"], (WIDTH // 2, 50), 32, anchor="center", bold=True)
        ui.text(surf, f"{room['size']} vs {room['size']}", (WIDTH // 2, 115), 24, anchor="center", bold=True)
        if self.is_host():
            self.btn_minus.draw(surf)
            self.btn_plus.draw(surf)

        for team in (BLUE, RED):
            x = COL_X[team]
            col = ui.TEAM_UI[team]
            members = [m for m in room["members"] if m["team"] == team]
            ui.text(surf, f"{TEAM_NAMES[team]}  {len(members)}/{room['size']}", (x, 135), 20, col, bold=True)
            for i in range(room["size"]):
                y = 170 + i * (SLOT_H + 8)
                rect = pygame.Rect(x, y, COL_W, SLOT_H)
                if i < len(members):
                    m = members[i]
                    me = m["key"] == self.app.my_key
                    ui.panel(surf, rect, (30, 44, 70, 230), col if me else (70, 90, 120))
                    pygame.draw.rect(surf, col, (x, y, 6, SLOT_H), border_radius=3)
                    label = m["name"] + ("  (나)" if me else "")
                    ui.text(surf, label, (x + 22, y + SLOT_H // 2), 19, anchor="midleft")
                    tags = []
                    if m["key"] == room["host"]:
                        tags.append("방장")
                    if m["bot"]:
                        tags.append("봇")
                    if tags:
                        ui.text(surf, " · ".join(tags), (x + COL_W - (100 if m["bot"] else 20), y + SLOT_H // 2), 15,
                                ui.GOLD, anchor="midright")
                else:
                    ui.panel(surf, rect, (16, 22, 36, 180), (45, 60, 85))
                    ui.text(surf, "빈 자리", (x + COL_W // 2, y + SLOT_H // 2), 16, ui.TEXT_DIM, anchor="center")
        for b in self.slot_buttons:
            b.draw(surf)

        if self.is_host():
            self.btn_start.draw(surf)
            if not self.btn_start.enabled:
                ui.text(surf, "양 팀에 최소 1명(봇 포함)이 있어야 시작할 수 있습니다.", (WIDTH // 2, 668), 14,
                        ui.TEXT_DIM, anchor="center")
        else:
            ui.text(surf, "방장이 게임을 시작하기를 기다리는 중...", (WIDTH // 2, 625), 18, ui.TEXT_DIM, anchor="center")
        self.btn_leave.draw(surf)

        # 채팅 (최근 몇 줄)
        y = 520
        for _, name, msg in self.app.chat[-3:]:
            ui.text(surf, f"{name}: {msg}", (WIDTH - 40, y), 14, ui.TEXT_DIM, anchor="topright")
            y += 18
