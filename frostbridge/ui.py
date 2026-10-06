"""Responsive 16:9 Pygame UI, uploaded as an OpenGL overlay."""
from functools import lru_cache
import logging
import math
import pygame

from .content import CHAMPIONS, asset_path
from .display import UI_SIZE

BG = (9, 17, 28)
PANEL = (16, 29, 44)
LINE = (43, 64, 82)
WHITE = (230, 240, 246)
MUTED = (136, 158, 177)
CYAN = (113, 217, 239)
GOLD = (228, 194, 127)
RED = (243, 124, 140)
BLUE = (92, 196, 245)


class UI:
    def __init__(self):
        self.surface = pygame.Surface(UI_SIZE, pygame.SRCALPHA)
        self.modal_layers = 0
        self.font_path = pygame.font.match_font("malgungothic,malgun gothic,notosanscjkkr,nanumgothic,arial")
        self.fields = {"name":"플레이어", "address":"127.0.0.1:27355", "room_name":"서리 다리 전투"}
        self.focus = None
        self.mouse = (0, 0)
        self.clicks = []
        self.portraits = {}
        self.background = self.make_background()
        self.ime = ""

    @lru_cache(maxsize=32)
    def font(self, size, bold=False):
        font = pygame.font.Font(self.font_path, size)
        font.set_bold(bold)
        return font

    @lru_cache(maxsize=1024)
    def raster_text(self, text, size, color, bold):
        return self.font(size, bold).render(text, True, color)

    def text(self, text, x, y, size=18, color=WHITE, bold=False, center=False):
        image = self.raster_text(str(text), size, tuple(color), bold)
        self.surface.blit(image, (int(x-image.get_width()/2) if center else int(x), int(y)))

    def paragraph(self, text, x, y, width, size=17, color=MUTED, line_height=26):
        line = ""
        for char in text:
            if self.font(size).size(line+char)[0] > width or char == "\n":
                self.text(line, x, y, size, color)
                y += line_height
                line = "" if char == "\n" else char
            else:
                line += char
        if line:
            self.text(line, x, y, size, color)
        return y+line_height

    def panel(self, rect, color=PANEL, border=LINE, radius=12):
        pygame.draw.rect(self.surface, color, rect, border_radius=radius)
        if border:
            pygame.draw.rect(self.surface, border, rect, 1, border_radius=radius)

    def line(self, start, end, color=LINE, width=1):
        pygame.draw.line(self.surface, color, start, end, width)

    def button(self, label, rect, primary=False, enabled=True, danger=False, size=18):
        rect = pygame.Rect(rect)
        hovered = rect.collidepoint(self.mouse) and enabled
        fill = (34, 63, 76) if hovered else PANEL
        border = RED if danger else CYAN if primary else LINE
        ink = BG if primary else WHITE
        if primary:
            fill = (145,231,246) if hovered else CYAN
        if not enabled:
            fill, border, ink = (19, 29, 40), (32, 44, 55), (73, 90, 104)
        self.panel(rect, fill, border, 7)
        self.text(label, rect.centerx, rect.centery-size*.72, size, ink, primary, center=True)
        for index, position in enumerate(self.clicks):
            if enabled and rect.collidepoint(position):
                self.clicks.pop(index)
                self.focus = None
                pygame.key.stop_text_input()
                return True
        return False

    def field(self, key, label, rect, limit=28):
        rect = pygame.Rect(rect)
        self.text(label, rect.x, rect.y-29, 15, MUTED)
        focused = self.focus == key
        self.panel(rect, BG, CYAN if focused else LINE, 6)
        value = self.fields[key]
        caret = "|" if focused and pygame.time.get_ticks()%1000 < 500 else ""
        shown = value+self.ime+caret if focused else value
        while self.font(19).size(shown)[0] > rect.width-26:
            shown = shown[1:]
        self.text(shown, rect.x+13, rect.y+11, 19)
        for index, position in enumerate(self.clicks):
            if rect.collidepoint(position):
                self.clicks.pop(index)
                self.focus = key
                pygame.key.start_text_input()
                break
        self.fields[key] = value[:limit]

    def begin(self, events, mouse, transparent=False):
        self.modal_layers = 0
        self.mouse = mouse
        self.clicks = [event.pos for event in events if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1]
        self.surface.fill((0,0,0,0)) if transparent else self.surface.blit(self.background, (0,0))
        for event in events:
            if self.focus:
                if event.type == pygame.TEXTINPUT:
                    self.fields[self.focus] += event.text
                    self.ime = ""
                elif event.type == pygame.TEXTEDITING:
                    self.ime = event.text
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_BACKSPACE:
                        self.fields[self.focus] = self.fields[self.focus][:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB):
                        self.focus = None
                        self.ime = ""
                        pygame.key.stop_text_input()

    @staticmethod
    def make_background():
        surface = pygame.Surface(UI_SIZE, pygame.SRCALPHA)
        for y in range(UI_SIZE[1]):
            t = y/UI_SIZE[1]
            pygame.draw.line(surface, (int(10+5*t), int(20+9*t), int(34+12*t)), (0,y),(1280,y))
        # A code-native geometric bridge illustration, no external art required.
        for i in range(14):
            x = 90+i*105
            pygame.draw.line(surface, (23,42,58), (x,0), (x-620,800), 1)
        pygame.draw.polygon(surface, (19,39,55), [(230,800),(900,205),(1070,238),(590,800)])
        pygame.draw.lines(surface, (42,72,86), False, [(230,800),(900,205),(1070,238),(590,800)], 2)
        for i in range(12):
            t = i/12
            x, y = 270+640*t, 770-540*t
            pygame.draw.line(surface, (34,58,73), (x,y), (x+320-160*t,y+35-20*t), 2)
        for x,y in [(1130,155),(760,580),(180,480),(980,640),(1110,340)]:
            pygame.draw.polygon(surface, (30,58,73), [(x,y-42),(x+17,y),(x,y+21),(x-17,y)])
            pygame.draw.line(surface, (51,98,114), (x,y-42),(x,y+21))
        return surface

    def header(self, subtitle, connection=None):
        self.text("FROSTBRIDGE", 44, 23, 27, WHITE, True)
        self.text(subtitle, 280, 32, 16, MUTED)
        if connection:
            pygame.draw.circle(self.surface, CYAN, (1030,43), 4)
            self.text(connection[:24], 1044, 31, 14, MUTED)
        self.line((44,79), (1236,79))

    def portrait(self, key, rect):
        rect = pygame.Rect(rect)
        cache_key = (key, rect.size)
        if cache_key not in self.portraits:
            spec = CHAMPIONS[key]
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            loaded = False
            try:
                path = asset_path(spec["portrait"])
                if path.is_file():
                    source = pygame.image.load(str(path)).convert_alpha()
                    ratio = max(rect.width/source.get_width(), rect.height/source.get_height())
                    source = pygame.transform.smoothscale(source, (int(source.get_width()*ratio), int(source.get_height()*ratio)))
                    surface.blit(source, ((rect.width-source.get_width())//2, (rect.height-source.get_height())//2))
                    loaded = True
            except (ValueError, OSError, pygame.error) as error:
                logging.getLogger(__name__).warning("Portrait %s: %s", key, error)
            if not loaded:
                tint = spec["color"]
                w,h = rect.size
                surface.fill(tuple(int(c*.13) for c in tint))
                for i in range(7):
                    pygame.draw.line(surface, tuple(int(c*.24) for c in tint), (0,int(h*.15+i*h*.15)),(w,int(i*h*.15)),1)
                pygame.draw.circle(surface, tuple(int(c*.27) for c in tint), (int(w*.5),int(h*.43)), int(min(w,h)*.35), 1)
                pygame.draw.polygon(surface, tuple(int(c*.5) for c in tint), [(int(w*.12),h),(int(w*.3),int(h*.58)),(int(w*.7),int(h*.58)),(int(w*.88),h)])
                pygame.draw.polygon(surface, tint, [(int(w*.5),int(h*.12)),(int(w*.7),int(h*.32)),(int(w*.65),int(h*.56)),(int(w*.5),int(h*.65)),(int(w*.35),int(h*.56)),(int(w*.3),int(h*.32))])
                pygame.draw.line(surface, WHITE, (int(w*.39),int(h*.38)),(int(w*.61),int(h*.38)),max(1,w//50))
                if key in ("mage","healer"):
                    pygame.draw.circle(surface, WHITE,(int(w*.81),int(h*.3)),max(2,w//16),2)
                if key in ("blade","shade"):
                    pygame.draw.line(surface, WHITE,(int(w*.82),int(h*.8)),(int(w*.9),int(h*.25)),max(2,w//30))
            self.portraits[cache_key] = surface
        self.surface.blit(self.portraits[cache_key], rect)

    def bar(self, rect, value, maximum, tint):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.surface, (10,17,26), rect, border_radius=3)
        if maximum > 0 and value > 0:
            fill = rect.copy()
            fill.width = max(1, int(rect.width*min(1,value/maximum)))
            pygame.draw.rect(self.surface, tint, fill, border_radius=3)

    def modal_shade(self):
        self.modal_layers += 1
        shade = pygame.Surface(UI_SIZE, pygame.SRCALPHA)
        shade.fill((1,6,12,195))
        self.surface.blit(shade,(0,0))
