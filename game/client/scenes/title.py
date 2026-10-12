"""타이틀: 닉네임을 정하고 플레이(→ 로비) 또는 종료."""
import random

import pygame

from .. import ui
from ..app import HEIGHT, WIDTH, Scene


class TitleScene(Scene):
    def on_enter(self):
        cx = WIDTH // 2
        name = self.app.my_name or f"플레이어{random.randint(100, 999)}"
        self.name_in = ui.TextInput((cx - 160, 336, 320, 40), name, 12, "닉네임")
        self.inputs = [self.name_in]
        self.buttons = [
            ui.Button((cx - 160, 400, 320, 48), "플레이", self.play, color=(40, 100, 170), size=18),
            ui.Button((cx - 160, 460, 320, 38), "종료", self.quit, color=(80, 40, 50)),
        ]

    def _name(self):
        return self.name_in.value.strip() or "플레이어"

    def play(self):
        from .browse import BrowseScene
        self.app.my_name = self._name()
        self.app.set_scene(BrowseScene(self.app))

    def quit(self):
        self.app.running = False

    def handle_event(self, e):
        for inp in self.inputs:
            inp.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN and not any(i.focused for i in self.inputs):
            self.play()

    def draw_ui(self, surf):
        cx = WIDTH // 2
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 120))
        surf.blit(shade, (0, 0))
        ui.text(surf, "칼바람 아레나", (cx, 120), 64, (220, 240, 255), anchor="center", bold=True)
        ui.panel(surf, (cx - 190, 270, 380, 250))
        ui.text(surf, "닉네임", (cx - 160, 312), 15, ui.TEXT_DIM)
        for inp in self.inputs:
            inp.draw(surf)
        for b in self.buttons:
            b.draw(surf)
