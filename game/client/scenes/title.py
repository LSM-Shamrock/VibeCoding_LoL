"""타이틀: 닉네임 + 서버 주소 입력 후 시작.

서버 주소를 비워 두면 내 PC 에서 서버를 열고(방장), 입력하면 그 서버에 접속한다.
"""
import random

import pygame

from ...shared.constants import DEFAULT_PORT
from .. import ui
from ..app import HEIGHT, WIDTH, Scene, local_ip


class TitleScene(Scene):
    def on_enter(self):
        cx = WIDTH // 2
        name = self.app.my_name or f"플레이어{random.randint(100, 999)}"
        self.name_in = ui.TextInput((cx - 160, 300, 320, 40), name, 12, "닉네임")
        self.addr_in = ui.TextInput((cx - 160, 386, 220, 40), "", 40, "비우면 내 PC에서 열기")
        self.port_in = ui.TextInput((cx + 70, 386, 90, 40), str(DEFAULT_PORT), 5, "포트")
        self.inputs = [self.name_in, self.addr_in, self.port_in]
        self.btn_start = ui.Button((cx - 160, 446, 320, 48), "시작", self.start, color=(40, 100, 170), size=18)
        self.buttons = [
            self.btn_start,
            ui.Button((cx - 160, 506, 320, 38), "종료", self.quit, color=(80, 40, 50)),
        ]
        self.ip = local_ip()

    def _name(self):
        return self.name_in.value.strip() or "플레이어"

    def _port(self):
        try:
            return int(self.port_in.value)
        except ValueError:
            return DEFAULT_PORT

    def start(self):
        """주소가 비어 있으면 내 PC 에서 서버를 열고, 있으면 그 서버에 접속."""
        addr = self.addr_in.value.strip()
        if addr:
            self.app.connect(addr, self._port(), self._name())
        else:
            self.app.host_and_connect(self._name(), self._port())

    def quit(self):
        self.app.running = False

    def handle_event(self, e):
        for inp in self.inputs:
            inp.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN and not any(i.focused for i in self.inputs):
            self.start()

    def update(self, dt):
        # 버튼 글자로 무엇을 하게 될지 보여준다
        self.btn_start.label = "접속" if self.addr_in.value.strip() else "서버 열고 시작"

    def draw_ui(self, surf):
        cx = WIDTH // 2
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 120))
        surf.blit(shade, (0, 0))
        ui.text(surf, "칼바람 아레나", (cx, 120), 64, (220, 240, 255), anchor="center", bold=True)
        ui.panel(surf, (cx - 190, 250, 380, 316))
        ui.text(surf, "닉네임", (cx - 160, 276), 15, ui.TEXT_DIM)
        ui.text(surf, "서버 주소 / 포트", (cx - 160, 362), 15, ui.TEXT_DIM)
        for inp in self.inputs:
            inp.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        ui.text(surf, f"같은 네트워크의 친구는 이 주소로 접속할 수 있습니다: {self.ip}:{self._port()}",
                (cx, HEIGHT - 50), 15, ui.TEXT_DIM, anchor="center")
