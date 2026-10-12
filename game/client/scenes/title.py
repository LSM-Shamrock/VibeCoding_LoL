"""타이틀: 닉네임 + 서버 주소 입력 후 시작.

서버 주소를 비워 두면 내 PC 에서 서버를 열고(방장), 입력하면 그 서버에 접속한다.
주소 앞부분(같은 네트워크면 똑같은 `172.16.` 같은 부분)은 이 PC 의 IP 에서 가져와 미리 채워 두므로 뒷부분만 입력하면 된다.
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
        self.addr_in = ui.TextInput((cx - 160, 386, 220, 40), "", 40, "비우면 서버 열기")
        self.port_in = ui.TextInput((cx + 70, 386, 90, 40), str(DEFAULT_PORT), 5, "포트", charset="0123456789")
        self.inputs = [self.name_in, self.addr_in, self.port_in]
        self.btn_start = ui.Button((cx - 160, 446, 320, 48), "시작", self.start, color=(40, 100, 170), size=18)
        self.buttons = [
            self.btn_start,
            ui.Button((cx - 160, 506, 320, 38), "종료", self.quit, color=(80, 40, 50)),
        ]
        self.ip = local_ip()
        self.pre_n = 2 if self.ip.count(".") == 3 and not self.ip.startswith("127.") else 0   # 자동으로 채울 앞 자리 수 (0 이면 끔)
        self.pre_rect = pygame.Rect(0, 0, 0, 0)
        self.layout_addr()

    # ---- 주소 앞부분 자동 입력
    def prefix(self):
        """내 IP 의 앞 pre_n 자리 ('172.16.' 처럼 끝에 점 포함). 끄면 빈 문자열."""
        if not self.pre_n:
            return ""
        return ".".join(self.ip.split(".")[: self.pre_n]) + "."

    def layout_addr(self):
        """앞부분 칸(왼쪽)과 입력칸(오른쪽)을 나눠 배치한다."""
        cx = WIDTH // 2
        pre = self.prefix()
        pw = (ui.font(17).size(pre)[0] + 16) if pre else 44
        self.pre_rect = pygame.Rect(cx - 160, 386, pw, 40)
        self.addr_in.rect = pygame.Rect(cx - 160 + pw, 386, 220 - pw, 40)

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
        """숫자 주소인데 자리가 모자라면 안내 문구를 돌려준다."""
        host = full.split(":")[0]
        if host and all(ch in "0123456789." for ch in host) and host.count(".") != 3:
            return "주소가 덜 입력되었습니다. 나머지 숫자까지 입력하세요. (예: 3.45)"
        return None

    def _name(self):
        return self.name_in.value.strip() or "플레이어"

    def _port(self):
        try:
            return int(self.port_in.value)
        except ValueError:
            return DEFAULT_PORT

    def start(self):
        """주소가 비어 있으면 내 PC 에서 서버를 열고, 있으면 그 서버에 접속."""
        addr = self.full_addr()
        if addr:
            err = self.addr_error(addr)
            if err:
                self.app.toast(err)
                return
            self.app.connect(addr, self._port(), self._name())
        else:
            self.app.host_and_connect(self._name(), self._port())

    def quit(self):
        self.app.running = False

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
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN and not any(i.focused for i in self.inputs):
            self.start()

    def update(self, dt):
        # 버튼 글자로 무엇을 하게 될지 보여준다
        self.btn_start.label = "접속" if self.addr_in.value.strip() else "서버 열고 시작"
        self.layout_addr()

    def draw_ui(self, surf):
        cx = WIDTH // 2
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 12, 24, 120))
        surf.blit(shade, (0, 0))
        ui.text(surf, "칼바람 아레나", (cx, 120), 64, (220, 240, 255), anchor="center", bold=True)
        ui.panel(surf, (cx - 190, 250, 380, 316))
        ui.text(surf, "닉네임", (cx - 160, 276), 15, ui.TEXT_DIM)
        ui.text(surf, "서버 주소 / 포트", (cx - 160, 362), 15, ui.TEXT_DIM)
        full = self.full_addr()
        if full:
            ui.text(surf, f"접속 주소  {full}:{self._port()}", (cx + 160, 362), 14, ui.GOLD, anchor="topright")
        # 앞부분 칸: 클릭하면 자리 수가 바뀐다 (2 → 3 → 1 → 끄기)
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
                    (cx, HEIGHT - 76), 14, ui.TEXT_DIM, anchor="center")
        ui.text(surf, f"같은 네트워크의 친구는 이 주소로 접속할 수 있습니다: {self.ip}:{self._port()}",
                (cx, HEIGHT - 50), 15, ui.TEXT_DIM, anchor="center")
