"""마우스 커서: 평상시 손 / 공격할 수 있는 대상 위 칼 / 대상 지정 스킬 조준 중 조준경.

시스템 커서를 숨기고 매 프레임 마지막에 직접 그린다 (assets/ui/cursors/*.png, tools/build_cursors.py 로 만든 이미지).
이미지가 없으면 시스템 커서를 그대로 쓴다.
"""
import pygame

from . import ui

# 이미지 안의 "클릭 지점" (왼쪽 위 기준 픽셀)
HOTSPOTS = {"default": (10, 2), "attack": (3, 3), "target": (16, 16)}
SIZES = {"default": 23, "attack": 32, "target": 32}      # 손 모양이 더 커 보여서 작게
KINDS = tuple(HOTSPOTS)


class CursorManager:
    def __init__(self):
        self.images = {k: ui.icon(f"assets/ui/cursors/{k}.png", SIZES[k]) for k in KINDS}
        self.enabled = all(self.images.values())
        self.hidden = False

    def draw(self, surf, kind="default"):
        """kind 가 None 이면 (로비 등 인게임이 아닐 때) 일반 윈도우 커서를 쓴다."""
        want_hidden = self.enabled and kind is not None
        if want_hidden != self.hidden:
            pygame.mouse.set_visible(not want_hidden)
            self.hidden = want_hidden
        if not want_hidden or not pygame.mouse.get_focused():
            return
        img = self.images.get(kind) or self.images["default"]
        hx, hy = HOTSPOTS.get(kind, HOTSPOTS["default"])
        x, y = ui.mouse_pos()
        surf.blit(img, (x - hx, y - hy))
