"""pygame 2D UI: 폰트, 텍스트, 버튼, 입력창."""
import os

import pygame

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
BOLD_CANDIDATES = [r"C:\Windows\Fonts\malgunbd.ttf"]

# 색상 테마
BG = (12, 18, 32)
PANEL = (18, 28, 48, 225)
PANEL_LIGHT = (30, 46, 74, 235)
BORDER = (90, 140, 200)
GOLD = (230, 200, 120)
TEXT = (225, 235, 250)
TEXT_DIM = (140, 160, 190)
BLUE_C = (80, 150, 255)
RED_C = (255, 90, 85)
GREEN_C = (90, 220, 110)
TEAM_UI = {0: BLUE_C, 1: RED_C}

_fonts = {}
_text_cache = {}
_mouse_mapper = None


def set_mouse_mapper(fn):
    """창 좌표 -> 논리 화면 좌표 변환 함수 (전체 화면 확대 대응)."""
    global _mouse_mapper
    _mouse_mapper = fn


def mouse_pos():
    pos = pygame.mouse.get_pos()
    if _mouse_mapper:
        x, y = _mouse_mapper(pos)
        return int(x), int(y)
    return pos


def _font_path(bold):
    for p in (BOLD_CANDIDATES if bold else []) + FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def font(size, bold=False):
    key = (size, bold)
    f = _fonts.get(key)
    if f is None:
        path = _font_path(bold)
        if path:
            f = pygame.font.Font(path, size)
        else:
            f = pygame.font.SysFont("malgungothic,applegothic,nanumgothic,notosanscjkkr,arial", size, bold=bold)
        _fonts[key] = f
    return f


def render_text(s, size=16, color=TEXT, bold=False):
    key = (s, size, color, bold)
    surf = _text_cache.get(key)
    if surf is None:
        if len(_text_cache) > 3000:
            _text_cache.clear()
        surf = font(size, bold).render(str(s), True, color)
        _text_cache[key] = surf
    return surf


def text(surface, s, pos, size=16, color=TEXT, anchor="topleft", bold=False, shadow=True):
    surf = render_text(s, size, color, bold)
    rect = surf.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow:
        sh = render_text(s, size, (0, 0, 0), bold)
        surface.blit(sh, rect.move(1, 1))
    surface.blit(surf, rect)
    return rect


def wrap(s, size, width, bold=False):
    f = font(size, bold)
    lines = []
    for para in str(s).split("\n"):
        cur = ""
        for ch in para:
            if f.size(cur + ch)[0] > width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def text_block(surface, s, pos, width, size=14, color=TEXT, line_gap=4):
    x, y = pos
    for line in wrap(s, size, width):
        text(surface, line, (x, y), size, color, shadow=False)
        y += size + line_gap
    return y


def panel(surface, rect, color=PANEL, border=BORDER, radius=8, width=1):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surface, border, rect, width, border_radius=radius)


def bar(surface, rect, ratio, color, back=(20, 20, 28, 220), border=(0, 0, 0)):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, back, rect)
    if ratio > 0:
        r = rect.copy()
        r.width = max(1, int(rect.width * max(0.0, min(1.0, ratio))))
        pygame.draw.rect(surface, color, r)
    if border:
        pygame.draw.rect(surface, border, rect, 1)


class Button:
    def __init__(self, rect, label, on_click, enabled=True, color=(40, 80, 140), size=17, tooltip=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.enabled = enabled
        self.color = color
        self.size = size
        self.tooltip = tooltip
        self.visible = True

    def handle(self, e):
        if not (self.visible and self.enabled):
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.on_click()
            return True
        return False

    def draw(self, surface):
        if not self.visible:
            return
        hover = self.rect.collidepoint(mouse_pos())
        if not self.enabled:
            col = (45, 50, 62)
        elif hover:
            col = tuple(min(255, c + 35) for c in self.color)
        else:
            col = self.color
        pygame.draw.rect(surface, col, self.rect, border_radius=6)
        pygame.draw.rect(surface, (150, 190, 240) if self.enabled else (80, 85, 95), self.rect, 1, border_radius=6)
        text(surface, self.label, self.rect.center, self.size, TEXT if self.enabled else TEXT_DIM, anchor="center")


class TextInput:
    def __init__(self, rect, value="", max_len=16, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.max_len = max_len
        self.placeholder = placeholder
        self.focused = False
        self.composing = ""

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            was = self.focused
            self.focused = self.rect.collidepoint(e.pos)
            if self.focused and not was:
                pygame.key.start_text_input()
                pygame.key.set_text_input_rect(self.rect)
            return self.focused
        if not self.focused:
            return False
        if e.type == pygame.TEXTINPUT:
            self.composing = ""
            self.value = (self.value + e.text)[: self.max_len]
            return True
        if e.type == pygame.TEXTEDITING:
            self.composing = e.text
            return True
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE and not self.composing:
                self.value = self.value[:-1]
                return True
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                self.focused = False
                return True
        return False

    def draw(self, surface):
        pygame.draw.rect(surface, (10, 16, 28, 240), self.rect, border_radius=5)
        pygame.draw.rect(surface, (120, 180, 255) if self.focused else (70, 100, 140), self.rect, 1, border_radius=5)
        shown = self.value + self.composing
        y = self.rect.centery
        if shown:
            r = text(surface, shown, (self.rect.x + 10, y), 17, TEXT, anchor="midleft", shadow=False)
        else:
            r = pygame.Rect(self.rect.x + 10, y, 0, 0)
            text(surface, self.placeholder, (self.rect.x + 10, y), 17, TEXT_DIM, anchor="midleft", shadow=False)
        if self.focused and (pygame.time.get_ticks() // 500) % 2 == 0:
            x = r.right + 2 if shown else self.rect.x + 10
            pygame.draw.line(surface, TEXT, (x, y - 10), (x, y + 10), 1)
