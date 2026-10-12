"""로비: 같은 네트워크에서 열린 방 목록 + 방 열기 + 주소로 직접 접속.

방 목록은 호스트가 UDP 로 방송하는 것을 받아 보여 준다 (game/client/lan.py).
접속하면 로비를 거치지 않고 그 방의 대기실로 바로 들어간다 (한 호스트 당 방 하나).
주소 앞부분(같은 네트워크면 똑같은 `172.16.` 같은 부분)은 이 PC 의 IP 에서 가져와 미리 채워 둔다.
"""
import pygame

from ...shared.constants import DEFAULT_PORT
from .. import ui
from ..app import HEIGHT, WIDTH, Scene, local_ip
from ..lan import LanFinder

PHASE_NAMES = {"waiting": "대기 중", "select": "챔피언 선택", "ingame": "게임 중", "ended": "게임 종료"}


class BrowseScene(Scene):
    def on_enter(self):
        self.app.room = None
        self.finder = LanFinder()
        self.found = []
        self.selected = None            # (ip, port, id)
        self.last_click = 0
        self.row_rects = []
        self.ip = local_ip()
        self.pre_n = 2 if self.ip.count(".") == 3 and not self.ip.startswith("127.") else 0   # 자동으로 채울 앞 자리 수 (0 이면 끔)
        self.pre_rect = pygame.Rect(0, 0, 0, 0)
        self.addr_in = ui.TextInput((0, 0, 100, 40), "", 40, "")
        self.port_in = ui.TextInput((0, 0, 90, 40), str(DEFAULT_PORT), 5, "포트", charset="0123456789")
        self.inputs = [self.addr_in, self.port_in]
        self.btn_join = ui.Button((90, 470, 200, 46), "입장", self.join_selected, color=(40, 110, 180))
        self.btn_open = ui.Button((830, 190, 340, 54), "방 열기", self.open_room, color=(40, 110, 180), size=18)
        self.btn_connect = ui.Button((1040, 574, 130, 40), "접속", self.connect_addr, color=(40, 110, 180))
        self.btn_back = ui.Button((1030, 650, 150, 40), "뒤로", self.back, color=(90, 45, 55))
        self.buttons = [self.btn_join, self.btn_open, self.btn_connect, self.btn_back]
        self.layout_addr()

    def on_exit(self):
        self.finder.close()

    # ---- 주소 입력 (앞부분 자동 입력)
    def prefix(self):
        """내 IP 의 앞 pre_n 자리 ('172.16.' 처럼 끝에 점 포함). 끄면 빈 문자열."""
        if not self.pre_n:
            return ""
        return ".".join(self.ip.split(".")[: self.pre_n]) + "."

    def layout_addr(self):
        pw = 108                                         # 앞부분 칸과 입력칸은 같은 가로 크기
        x = 90
        self.pre_rect = pygame.Rect(x, 574, pw, 40)
        self.addr_in.rect = pygame.Rect(x + pw + 4, 574, pw, 40)
        self.port_in.rect = pygame.Rect(x + 2 * pw + 18, 574, 90, 40)

    def full_addr(self):
        """입력한 값을 접속 주소로 바꾼다. 점이 3개 미만인 숫자 주소는 앞부분을 붙이고, 글자가 섞였거나 이미 전체 주소면 그대로 쓴다."""
        t = self.addr_in.value.strip()
        if not t:
            return ""
        pre = self.prefix()
        if pre and all(ch in "0123456789." for ch in t) and t.count(".") < 3:
            return pre + t.lstrip(".")
        return t

    def addr_error(self, full):
        host = full.split(":")[0]
        if host and all(ch in "0123456789." for ch in host) and host.count(".") != 3:
            return "주소가 덜 입력되었습니다. 나머지 숫자까지 입력하세요. (예: 3.45)"
        return None

    def _port(self):
        try:
            return int(self.port_in.value)
        except ValueError:
            return DEFAULT_PORT

    # ---- 동작
    def open_room(self):
        self.app.host_and_connect(self.app.my_name, self._port())

    def connect_addr(self):
        addr = self.full_addr()
        if not addr:
            self.app.toast("접속할 주소를 입력하세요.")
            return
        err = self.addr_error(addr)
        if err:
            self.app.toast(err)
            return
        self.app.connect(addr, self._port(), self.app.my_name)

    def join_selected(self):
        if self.selected is None:
            return
        ip, port, _rid = self.selected
        self.app.connect(ip, port, self.app.my_name)

    def back(self):
        from .title import TitleScene
        self.app.set_scene(TitleScene(self.app))

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.pre_rect.collidepoint(e.pos):
            order = [2, 3, 1, 0] if self.ip.count(".") == 3 else [0]   # 앞 2자리 → 3자리 → 1자리 → 끄기
            self.pre_n = order[(order.index(self.pre_n) + 1) % len(order)] if self.pre_n in order else order[0]
            self.layout_addr()
            self.app.audio.play("ui_select")
            return
        for inp in self.inputs:
            inp.handle(e)
        for b in self.buttons:
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.addr_in.value.strip() \
                and not any(i.focused for i in self.inputs):
            self.connect_addr()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            now = pygame.time.get_ticks()
            for key, rect in self.row_rects:
                if rect.collidepoint(e.pos):
                    if self.selected == key and now - self.last_click < 400:     # 같은 방을 빠르게 두 번 클릭하면 입장
                        self.app.audio.play("ui_confirm")
                        self.join_selected()
                    elif self.selected != key:
                        self.app.audio.play("ui_select")
                    self.selected = key
                    self.last_click = now

    def update(self, dt):
        self.found = self.finder.poll()
        keys = {(r["ip"], r["port"], r["id"]) for r in self.found}
        if self.selected not in keys:
            self.selected = None
        sel = next((r for r in self.found if (r["ip"], r["port"], r["id"]) == self.selected), None)
        self.btn_join.enabled = bool(sel) and sel["phase"] == "waiting" and sel["count"] < sel["size"] * 2
        self.layout_addr()

    def draw_ui(self, surf):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 150))
        surf.blit(shade, (0, 0))
        ui.text(surf, "로비", (90, 50), 36, bold=True)
        ui.text(surf, f"{self.app.my_name} · 내 주소 {self.ip}", (90, 100), 16, ui.TEXT_DIM)

        # 같은 네트워크에서 열린 방
        ui.panel(surf, (70, 140, 720, 400))
        ui.text(surf, "같은 네트워크의 열린 방", (95, 154), 15, ui.TEXT_DIM)
        ui.text(surf, "방장", (360, 154), 15, ui.TEXT_DIM)
        ui.text(surf, "주소", (480, 154), 15, ui.TEXT_DIM)
        ui.text(surf, "인원", (640, 154), 15, ui.TEXT_DIM)
        ui.text(surf, "상태", (690, 154), 15, ui.TEXT_DIM)
        self.row_rects = []
        y = 182
        if not self.found:
            ui.text(surf, "열린 방이 없습니다.", (430, 300), 18, ui.TEXT_DIM, anchor="center")
            ui.text(surf, "'방 열기'로 직접 열거나, 아래에 주소를 입력해 접속하세요.", (430, 330), 15, ui.TEXT_DIM, anchor="center")
        for r in self.found[:10]:
            key = (r["ip"], r["port"], r["id"])
            rect = pygame.Rect(82, y, 696, 32)
            sel = key == self.selected
            if sel or rect.collidepoint(ui.mouse_pos()):
                pygame.draw.rect(surf, (50, 90, 150, 200) if sel else (40, 60, 90, 160), rect, border_radius=4)
            ui.text(surf, r["name"], (95, y + 16), 16, anchor="midleft")
            ui.text(surf, r["host"], (360, y + 16), 15, ui.TEXT_DIM, anchor="midleft")
            ui.text(surf, f"{r['ip']}:{r['port']}", (480, y + 16), 14, ui.TEXT_DIM, anchor="midleft")
            ui.text(surf, f"{r['count']}/{r['size'] * 2}", (640, y + 16), 15, anchor="midleft")
            ui.text(surf, PHASE_NAMES.get(r["phase"], r["phase"]), (690, y + 16), 14,
                    ui.GREEN_C if r["phase"] == "waiting" else ui.GOLD, anchor="midleft")
            self.row_rects.append((key, rect))
            y += 34

        # 방 열기
        ui.panel(surf, (810, 140, 380, 160))
        ui.text(surf, "내 PC에서 방 열기", (830, 154), 18, bold=True)
        ui.text(surf, "같은 네트워크 사람들의 목록에 이 방이 보입니다.", (830, 262), 13, ui.TEXT_DIM)

        # 직접 접속
        ui.panel(surf, (70, 550, 1120, 80))
        ui.text(surf, "주소로 직접 접속 / 포트", (90, 556), 14, ui.TEXT_DIM)
        full = self.full_addr()
        if full:
            ui.text(surf, f"접속 주소  {full}:{self._port()}", (1020, 556), 14, ui.GOLD, anchor="topright")
        hov = self.pre_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surf, (30, 46, 74) if hov else (22, 34, 58), self.pre_rect, border_radius=5)
        pygame.draw.rect(surf, ui.BORDER, self.pre_rect, 1, border_radius=5)
        pre = self.prefix()
        ui.text(surf, pre if pre else "전체", self.pre_rect.center, 17, ui.GOLD if pre else ui.TEXT_DIM, anchor="center", shadow=False)
        for inp in self.inputs:
            inp.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        if pre:
            ui.text(surf, f"앞의 '{pre}' 는 자동 입력됩니다. 칸을 누르면 자리 수가 바뀌고, 전체 주소를 붙여넣어도 됩니다.",
                    (90, 640), 13, ui.TEXT_DIM)
