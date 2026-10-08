"""타이틀: 닉네임 입력, 서버 열기(호스트) / 서버 접속."""
import random

import pygame

from ...shared.constants import DEFAULT_PORT
from .. import ui
from ..app import HEIGHT, WIDTH, Scene, local_ip


class TitleScene(Scene):
    def on_enter(self):
        cx = WIDTH // 2
        name = self.app.my_name or f"소환사{random.randint(100, 999)}"
        self.name_in = ui.TextInput((cx - 160, 300, 320, 40), name, 12, "닉네임")
        self.addr_in = ui.TextInput((cx - 160, 446, 220, 40), "", 40, "서버 주소")
        self.port_in = ui.TextInput((cx + 70, 446, 90, 40), str(DEFAULT_PORT), 5, "포트")
        self.inputs = [self.name_in, self.addr_in, self.port_in]
        self.buttons = [
            ui.Button((cx - 160, 355, 320, 44), "서버 열고 시작 (방장)", self.host, color=(40, 100, 170)),
            ui.Button((cx - 160, 496, 320, 44), "서버에 접속", self.join, color=(50, 80, 120)),
            ui.Button((cx - 160, 566, 320, 38), "종료", self.quit, color=(80, 40, 50)),
        ]
        self.ip = local_ip()

    def _name(self):
        return self.name_in.value.strip() or "소환사"

    def _port(self):
        try:
            return int(self.port_in.value)
        except ValueError:
            return DEFAULT_PORT

    def host(self):
        self.app.host_and_connect(self._name(), self._port())

    def join(self):
        self.app.connect(self.addr_in.value.strip() or "127.0.0.1", self._port(), self._name())

    def quit(self):
        self.app.running = False

    def handle_event(self, e):
        for inp in self.inputs:
            inp.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN and not any(i.focused for i in self.inputs):
            self.host()

    def draw_ui(self, surf):
        cx = WIDTH // 2
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 120))
        surf.blit(shade, (0, 0))
        ui.text(surf, "칼바람 아레나", (cx, 120), 64, (220, 240, 255), anchor="center", bold=True)
        ui.text(surf, "하나의 라인, 무작위 난투 · 파이게임 3D", (cx, 180), 20, ui.TEXT_DIM, anchor="center")
        ui.panel(surf, (cx - 190, 250, 380, 376))
        ui.text(surf, "닉네임", (cx - 160, 276), 15, ui.TEXT_DIM)
        ui.text(surf, "다른 사람의 서버에 접속 (주소 / 포트)", (cx - 160, 422), 15, ui.TEXT_DIM)
        for inp in self.inputs:
            inp.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        ui.text(surf, f"같은 네트워크의 친구는 이 주소로 접속할 수 있습니다: {self.ip}:{self._port()}",
                (cx, HEIGHT - 50), 15, ui.TEXT_DIM, anchor="center")
