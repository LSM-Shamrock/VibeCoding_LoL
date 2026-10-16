"""클라이언트 앱: pygame 창 + moderngl, 장면 관리, 서버 메시지 라우팅."""
import json
import math
import os
import socket
import time

import moderngl
import pygame

from ..shared import mapdata
from ..shared.constants import DEFAULT_PORT
from ..shared.net import NetClient
from . import ui
from .keybinds import KeyBinds
from .gl import Renderer, model_matrix
from .audio import SETTINGS_PATH, Audio
from .cursors import CursorManager
from .models import ModelLibrary

WIDTH, HEIGHT = 1280, 720
MOUSE_EVENTS = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
SENS_MIN, SENS_MAX = 0.3, 3.0   # 마우스 감도 (커서가 움직이는 배율) 범위
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class Scene:
    fullscreen = False      # True 인 장면(인게임)에 들어가면 전체 화면으로 전환
    grab_mouse = False      # True 면 커서를 창 안에 가둔다 (화면 끝 카메라 이동용)

    def __init__(self, app):
        self.app = app

    def cursor_kind(self):
        """이 장면에서 보여 줄 마우스 커서: None(일반 윈도우 커서) / default(손) / attack(칼) / target(조준경)."""
        return None

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def handle_event(self, e):
        pass

    def on_message(self, msg):
        pass

    def update(self, dt):
        pass

    def render3d(self):
        self.app.draw_background()

    def draw_ui(self, surf):
        pass


class App:
    def __init__(self, autotest=None):
        # 전체 화면에서 다른 창으로 전환해도 최소화되지 않게
        os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
        pygame.init()
        pygame.display.set_caption("칼바람 아레나")
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
        except pygame.error:
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 0)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 0)
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
        self.ctx = moderngl.create_context()
        self.renderer = Renderer(self.ctx, WIDTH, HEIGHT)
        ui.set_mouse_mapper(self.renderer.to_logical)
        self.models = ModelLibrary(self.renderer)
        self.fullscreen = False
        try:
            from pygame._sdl2.video import Window
            self.window = Window.from_display_module()
        except Exception:  # noqa: BLE001
            self.window = None
        # SDL 은 기본으로 텍스트 입력(IME)을 켜 둔다. 켜져 있으면 한글 입력 모드에서 게임 키가
        # 입력기로 넘어가므로 꺼 두고, 입력칸에 포커스가 있을 때만 켠다 (ui.TextInput).
        pygame.key.stop_text_input()
        self.clock = pygame.time.Clock()
        self.keybinds = KeyBinds.load()   # 조작키 (게임 중 ESC 설정 창에서 변경)
        self.cursors = CursorManager()    # 손 / 칼 / 조준경 커서 (시스템 커서는 숨김)
        # 마우스 감도: 인게임에서는 커서를 창에 가두고 숨겨서(SDL 상대 이동 모드) 움직인 양에 감도를 곱한 가상 커서를 쓴다
        self.mouse_sens = 1.0
        self.vmouse = None                # 가상 커서 위치 (창 좌표). None 이면 실제 커서
        self.load_mouse_sens()
        ui.set_mouse_source(self.window_mouse_pos)
        self.audio = Audio()              # 효과음 (data/sounds.json). 소리 크기는 ESC 설정 창에서 변경
        self.audio.preload()
        ui.set_sfx(self.audio.play)
        self.net = NetClient()
        self.server = None          # 이 프로세스에서 띄운 서버
        self.hosting = False        # 내가 방장 겸 서버인가 (로비 없이 자동으로 방을 만든다)
        self.auto_join = False      # 접속 직후 열려 있는 방에 바로 들어갈 차례인가 (로비 생략)
        self.joining = False        # 방 입장을 요청해 놓고 답을 기다리는 중
        self.my_key = None
        self.my_name = ""
        self.server_addr = ""
        self.share_addr = ""        # 다른 사람이 접속할 때 쓸 주소 (루프백이면 이 PC의 LAN IP)
        self.rooms = []
        self.room = None
        self.toasts = []            # (만료 시각, 텍스트)
        self.chat = []
        self.running = True
        self.time = 0.0
        self.autotest = autotest
        self.scene = None
        from .scenes.title import TitleScene
        self.set_scene(TitleScene(self))

    # ------------------------------------------------------------------ 장면
    def set_scene(self, scene):
        if self.scene is not None:
            self.scene.on_exit()
        self.scene = scene
        self.renderer.vision = None     # 전장의 안개는 인게임 장면에서만
        self.set_fullscreen(scene.fullscreen)
        pygame.event.set_grab(scene.grab_mouse)
        self.audio.play_music("bgm_game" if type(scene).__name__ == "GameScene" else "bgm_menu")
        scene.on_enter()

    # ------------------------------------------------------------------ 창 모드
    def set_fullscreen(self, on):
        """테두리 없는 전체 화면(바탕화면 해상도) <-> 1280x720 창 모드. GL 컨텍스트는 유지된다."""
        if on == self.fullscreen or self.window is None:
            return
        try:
            if on:
                self.window.set_fullscreen(desktop=True)
            else:
                from pygame._sdl2.video import WINDOWPOS_CENTERED
                self.window.set_windowed()
                self.window.size = (WIDTH, HEIGHT)
                self.window.position = WINDOWPOS_CENTERED
        except pygame.error as e:
            print("[화면] 전환 실패:", e)
            return
        self.fullscreen = on
        self.sync_window_size()

    def sync_window_size(self):
        w, h = pygame.display.get_window_size()
        self.renderer.set_window_size(w, h)

    def mouse_edge(self):
        """커서가 실제 창(화면) 끝에 닿아 있으면 그 방향 (-1/0/1, -1/0/1)."""
        if not pygame.mouse.get_focused():
            return 0, 0
        mx, my = self.window_mouse_pos()
        w, h = self.renderer.window_size
        m = 3
        dx = -1 if mx <= m else (1 if mx >= w - 1 - m else 0)
        dy = -1 if my <= m else (1 if my >= h - 1 - m else 0)
        return dx, dy

    # ------------------------------------------------------------------ 마우스 감도 (가상 커서)
    def load_mouse_sens(self):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                self.mouse_sens = float(json.load(f).get("mouse_sens", 1.0))
        except (OSError, ValueError, TypeError, AttributeError):
            self.mouse_sens = 1.0
        self.mouse_sens = max(SENS_MIN, min(SENS_MAX, self.mouse_sens))

    def set_mouse_sens(self, v):
        self.mouse_sens = round(max(SENS_MIN, min(SENS_MAX, v)), 1)

    def save_mouse_sens(self):
        try:
            data = {}
            try:
                with open(SETTINGS_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                pass
            data["mouse_sens"] = self.mouse_sens
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def window_mouse_pos(self):
        """커서 위치 (창 좌표). 인게임에서는 감도를 적용한 가상 커서."""
        if self.vmouse is not None:
            return int(self.vmouse[0]), int(self.vmouse[1])
        return pygame.mouse.get_pos()

    def sync_virtual_mouse(self):
        """커서를 숨기고 창에 가둔 장면(인게임)이면 가상 커서를 켜고, 아니면 끄면서 실제 커서를 그 자리로 옮긴다."""
        on = self.scene.grab_mouse and self.cursors.hidden
        if on and self.vmouse is None:
            x, y = pygame.mouse.get_pos()
            self.vmouse = (float(x), float(y))
        elif not on and self.vmouse is not None:
            x, y = self.window_mouse_pos()
            self.vmouse = None
            try:
                pygame.mouse.set_pos((x, y))
            except pygame.error:
                pass

    def _virtual_event(self, e):
        """가상 커서가 켜져 있으면 마우스 이벤트의 위치를 가상 커서 위치로 바꾼다 (움직임은 감도만큼 늘이거나 줄인다)."""
        if self.vmouse is None or e.type not in MOUSE_EVENTS:
            return e
        d = dict(e.dict)
        if e.type == pygame.MOUSEMOTION:
            w, h = self.renderer.window_size
            rx, ry = e.rel[0] * self.mouse_sens, e.rel[1] * self.mouse_sens
            self.vmouse = (max(0.0, min(w - 1.0, self.vmouse[0] + rx)), max(0.0, min(h - 1.0, self.vmouse[1] + ry)))
            d["rel"] = (int(round(rx)), int(round(ry)))
        d["pos"] = self.window_mouse_pos()
        return pygame.event.Event(e.type, d)

    def _to_logical_event(self, e):
        if e.type in MOUSE_EVENTS and self.renderer.viewport != (0, 0, WIDTH, HEIGHT):
            d = dict(e.dict)
            d["pos"] = tuple(int(v) for v in self.renderer.to_logical(e.pos))
            return pygame.event.Event(e.type, d)
        return e

    def toast(self, text, dur=3.5):
        self.toasts.append((time.time() + dur, text))

    # ------------------------------------------------------------------ 네트워크
    def host_and_connect(self, name, port=DEFAULT_PORT):
        """내 PC 에서 서버를 열고 접속한다. 한 호스트당 방 하나라서 접속하면 방을 자동으로 만들어 로비 없이 대기실로 간다."""
        from ..server.server import GameServer
        if self.server is not None and self.server.port != port:
            self.stop_hosting()                      # 예전에 연 서버가 다른 포트면 닫고 새 포트로 다시 연다
        self.hosting = False
        self.auto_join = False
        if self.server is None:
            try:
                srv = GameServer("0.0.0.0", port, verbose=False)
                srv.start()
                self.server = srv
                self.hosting = True
            except OSError:
                self.toast(f"포트 {port} 는 이미 사용 중이라 그 서버에 접속합니다. ")
        else:
            self.hosting = True
        if not self.connect("127.0.0.1", port, name):
            self.hosting = False
            return False
        return True

    def drop_connection(self):
        """서버와의 연결을 끊는다 ('연결 끊김' 안내가 뜨지 않게 새 연결 객체로 교체)."""
        self.net.close()
        self.net = NetClient()

    def stop_hosting(self):
        """내가 연 서버를 닫는다 (방장이 방을 나가거나 포트를 바꿔 다시 열 때)."""
        self.hosting = False
        self.net.close()
        self.net = NetClient()                       # 닫힘 알림이 '연결 끊김' 안내로 뜨지 않게 새 연결 객체로 교체
        if self.server is not None:
            self.server.stop()
            self.server = None
        self.room = None

    def connect(self, host, port, name):
        host = host.strip()
        for prefix in ("tcp://", "http://", "https://"):
            if host.lower().startswith(prefix):
                host = host[len(prefix):]
        host = host.rstrip("/")
        if host.count(":") == 1:                     # "192.168.0.5:6000" 처럼 주소칸에 포트까지 적은 경우
            h, _, p = host.partition(":")
            if p.isdigit():
                host, port = h, int(p)
        if not (1 <= int(port) <= 65535):
            self.toast("포트는 1 ~ 65535 사이 숫자여야 합니다.")
            return False
        self.net.close()
        self.net = NetClient()
        try:
            self.net.connect(host, int(port))
        except socket.gaierror:
            self.toast(f"접속 실패: 주소 '{host}' 를 찾을 수 없습니다.")
            return False
        except socket.timeout:
            self.toast(f"접속 실패: {host}:{port} 응답이 없습니다. 주소·포트와 방화벽(TCP {port})을 확인하세요.")
            return False
        except ConnectionRefusedError:
            self.toast(f"접속 실패: {host}:{port} 에서 서버가 열려 있지 않습니다. 호스트가 먼저 '서버 열고 시작'을 눌렀는지, 포트가 같은지 확인하세요.")
            return False
        except OSError as e:
            self.toast(f"접속 실패: {host}:{port} ({e.strerror or e})")
            return False
        self.server_addr = f"{host}:{port}"
        self.share_addr = f"{local_ip() if host in LOOPBACK else host}:{port}"
        self.my_name = name
        self.net.send({"t": "hello", "name": name})
        return True

    def send(self, msg):
        self.net.send(msg)

    def process_messages(self):
        from .scenes.game import GameScene
        from .scenes.browse import BrowseScene
        from .scenes.room import RoomScene
        from .scenes.select import SelectScene

        for msg in self.net.poll():
            t = msg.get("t")
            if t == "welcome":
                self.my_key = msg["key"]
                self.my_name = msg["name"]
                self.audio.play("ui_confirm")
                if self.hosting:
                    # 한 호스트당 방 하나: 로비를 건너뛰고 바로 내 방을 만든다 (곧 대기실 화면으로 넘어간다)
                    self.send({"t": "create_room", "name": f"{self.my_name}의 방"})
                else:
                    self.auto_join = True            # 한 호스트당 방 하나: 로비를 거치지 않고 곧 도착할 방 목록에서 바로 들어간다
            elif t == "rooms":
                self.rooms = msg["rooms"]
                if self.auto_join:
                    self.auto_join = False
                    open_rooms = [r for r in self.rooms if r["phase"] == "waiting" and r["count"] < r["size"] * 2]
                    if open_rooms:
                        self.joining = True
                        self.send({"t": "join_room", "id": open_rooms[0]["id"]})
                    elif not self.rooms:                 # 전용 서버에 방이 하나도 없으면 내가 방을 만든다
                        self.send({"t": "create_room", "name": f"{self.my_name}의 방"})
                    else:
                        self.toast("들어갈 수 있는 방이 없습니다. (게임이 이미 진행 중이거나 방이 가득 찼습니다)")
                        self.drop_connection()
                        self.set_scene(BrowseScene(self))
            elif t == "room":
                self.room = msg
                self.joining = False
                phase = msg["phase"]
                if phase == "waiting" and not isinstance(self.scene, RoomScene):
                    self.set_scene(RoomScene(self))
                elif phase == "select" and not isinstance(self.scene, SelectScene):
                    self.set_scene(SelectScene(self))
            elif t == "game_start":
                self.set_scene(GameScene(self, msg))
            elif t == "error":
                self.audio.play("ui_error")
                self.toast(msg.get("msg", "오류"))
                if self.joining:                     # 바로 접속하던 방에 못 들어가면 로비로 돌아간다
                    self.joining = False
                    self.drop_connection()
                    self.set_scene(BrowseScene(self))
            elif t == "chat":
                self.audio.play("ui_chat")
                self.chat.append((time.time(), msg["name"], msg["text"]))
                self.chat = self.chat[-8:]
            elif t == "disconnected":
                self.room = None
                self.audio.play("ui_error")
                self.toast("서버와 연결이 끊어졌습니다.")
                self.set_scene(BrowseScene(self))
            if self.scene is not None:
                self.scene.on_message(msg)

    # ------------------------------------------------------------------ 배경
    def draw_background(self):
        """메뉴 화면 뒤에 천천히 움직이는 맵."""
        cam = self.renderer.camera
        cam.tx = math.sin(self.time * 0.05) * 30
        cam.ty = 0.0
        cam.tz = 0
        cam.distance = 34
        cam.pitch = math.radians(50)
        cam.yaw = 0.0
        self.renderer.begin_3d(cam)
        self.renderer.draw(self.models.map, model_matrix())
        for team in (0, 1):
            meshes = self.models.team_meshes[team]
            for st in mapdata.structure_layout():           # 실제 맵과 같은 자리에 구조물을 놓는다
                if st["team"] == team:
                    self.renderer.draw(meshes[st["kind"]], model_matrix(st["x"], 0, st["z"]))

    # ------------------------------------------------------------------ 루프
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(120) / 1000.0)
            self.audio.tick_music()
            self.time += dt
            self.renderer.time = self.time
            self.sync_virtual_mouse()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type in (pygame.WINDOWSIZECHANGED, pygame.WINDOWRESTORED):
                    self.sync_window_size()
                elif (e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                      and e.mod & pygame.KMOD_ALT):
                    self.set_fullscreen(not self.fullscreen)      # Alt+Enter: 전체 화면 전환
                else:
                    self.scene.handle_event(self._to_logical_event(self._virtual_event(e)))
            self.process_messages()
            if self.autotest:
                self.autotest.step(self, dt)
            self.scene.update(dt)
            self.scene.render3d()
            surf = self.renderer.overlay.begin()
            self.scene.draw_ui(surf)
            self.draw_toasts(surf)
            self.cursors.draw(surf, self.scene.cursor_kind())
            self.renderer.end_overlay()
            if self.autotest:
                self.autotest.after_frame(self)
            pygame.display.flip()
        self.net.close()
        if self.server:
            self.server.stop()
        pygame.quit()

    def draw_toasts(self, surf):
        now = time.time()
        self.toasts = [t for t in self.toasts if t[0] > now]
        y = 18
        for _, text in self.toasts[-4:]:
            w = ui.font(16).size(text)[0] + 30
            r = pygame.Rect(0, 0, w, 32)
            r.midtop = (WIDTH // 2, y)
            ui.panel(surf, r, (60, 25, 30, 235), (230, 110, 110))
            ui.text(surf, text, r.center, 16, anchor="center")
            y += 38

    def screenshot(self, path):
        size = self.renderer.window_size
        data = self.ctx.screen.read(viewport=(0, 0, *size), components=3)
        img = pygame.image.frombytes(data, size, "RGB", True)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        pygame.image.save(img, path)
