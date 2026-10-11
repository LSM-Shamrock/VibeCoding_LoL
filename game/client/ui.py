"""pygame 2D UI: 폰트, 텍스트, 버튼, 입력창."""
import os

import pygame

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "fonts")
# 게임에 같이 들어 있는 Noto Sans KR (OFL). 맑은 고딕은 작은 크기에서 ㅏ·ㅓ 세로 획이 사라지는 문제가 있어 맨 뒤 대체용.
FONT_CANDIDATES = [
    os.path.join(_FONT_DIR, "NotoSansKR-Regular.otf"),
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
BOLD_CANDIDATES = [os.path.join(_FONT_DIR, "NotoSansKR-Bold.otf"), r"C:\Windows\Fonts\malgunbd.ttf"]

# 색상 테마
BG = (12, 18, 32)
PANEL = (18, 28, 48, 225)
PANEL_LIGHT = (30, 46, 74, 235)
BORDER = (0, 0, 0)
HIGHLIGHT = (235, 240, 250)      # 선택/포커스 테두리
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
_sfx = None
_hot = None         # 마우스가 올라가 있는 버튼 (자리 기준). 매 프레임 버튼을 새로 만들어도 소리가 반복되지 않게 전역으로 기억


def set_sfx(fn):
    """효과음 재생 함수 연결 (app.audio.play). 버튼 클릭·마우스 올림 소리에 쓴다."""
    global _sfx
    _sfx = fn


def sfx(name, **kw):
    if _sfx:
        _sfx(name, **kw)


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


class _SuperFont:
    """작은 글자용 폰트: 2배 크기로 그린 뒤 절반으로 줄인다.
    말굿 고딕을 작은 크기로 바로 그리면 힌팅 때문에 ㅏ·ㅓ 의 세로 획이 사라져 글자가 깨져 보인다."""
    S = 2

    def __init__(self, path, size, bold):
        if path:
            self.f = pygame.font.Font(path, size * self.S)
        else:
            self.f = pygame.font.SysFont("malgungothic,applegothic,nanumgothic,notosanscjkkr,arial", size * self.S, bold=bold)

    def size(self, s):
        w, h = self.f.size(s)
        return (w + 1) // self.S, (h + 1) // self.S

    def render(self, s, aa, color, *a):
        big = self.f.render(s, True, color)
        w, h = big.get_size()
        return pygame.transform.smoothscale(big, (max(1, w // self.S), max(1, h // self.S)))

    def get_height(self):
        return self.f.get_height() // self.S

    def get_linesize(self):
        return self.f.get_linesize() // self.S


def font(size, bold=False):
    key = (size, bold)
    f = _fonts.get(key)
    if f is None:
        path = _font_path(bold)
        if size <= 16:
            f = _SuperFont(path, size, bold)
        elif path:
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


NO_LINE_START = ",.!?)]}%·、。」』》:;"      # 줄 맨 앞에 오면 보기 싫은 글자 (앞 줄에 붙여 둔다)


def wrap(s, size, width, bold=False):
    f = font(size, bold)
    lines = []
    for para in str(s).split("\n"):
        cur = ""
        for ch in para:
            if f.size(cur + ch)[0] > width and cur and ch not in NO_LINE_START:
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


_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_icons = {}


def icon(path, size):
    """프로젝트 기준 경로의 이미지를 size x size 로 읽어 둔다. 파일이 없으면 None."""
    key = (path, size)
    if key not in _icons:
        full = os.path.join(_ROOT, path)
        img = None
        if os.path.exists(full):
            try:
                img = pygame.transform.smoothscale(pygame.image.load(full).convert_alpha(), (size, size))
            except (pygame.error, ValueError):
                img = None
        _icons[key] = img
    return _icons[key]


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
            sfx("ui_click")
            self.on_click()
            return True
        return False

    def draw(self, surface):
        if not self.visible:
            return
        global _hot
        hover = self.rect.collidepoint(mouse_pos())
        key = (self.rect.x, self.rect.y, self.rect.w, self.rect.h)
        if hover:
            if _hot != key:
                _hot = key
                if self.enabled:
                    sfx("ui_hover")
        elif _hot == key:
            _hot = None
        if not self.enabled:
            col = (45, 50, 62)
        elif hover:
            col = tuple(min(255, c + 35) for c in self.color)
        else:
            col = self.color
        pygame.draw.rect(surface, col, self.rect, border_radius=6)
        pygame.draw.rect(surface, BORDER, self.rect, 1, border_radius=6)
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
                sfx("ui_click")
                pygame.key.start_text_input()
                pygame.key.set_text_input_rect(self.rect)
            elif was and not self.focused:
                pygame.key.stop_text_input()
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
                pygame.key.stop_text_input()
                return True
        return False

    def draw(self, surface):
        pygame.draw.rect(surface, (10, 16, 28, 240), self.rect, border_radius=5)
        pygame.draw.rect(surface, HIGHLIGHT if self.focused else BORDER, self.rect, 1, border_radius=5)
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
