"""클라이언트 앱: pygame 창 + moderngl, 장면 관리, 서버 메시지 라우팅."""
import math
import os
import time

import moderngl
import pygame

from ..shared.constants import DEFAULT_PORT
from ..shared.net import NetClient
from . import ui
from .gl import Renderer, model_matrix
from .models import ModelLibrary

WIDTH, HEIGHT = 1280, 720


class Scene:
    def __init__(self, app):
        self.app = app

    def on_enter(self):
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
        self.models = ModelLibrary(self.renderer)
        self.clock = pygame.time.Clock()
        self.net = NetClient()
        self.server = None          # 이 프로세스에서 띄운 서버
        self.my_key = None
        self.my_name = ""
        self.server_addr = ""
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
        self.scene = scene
        scene.on_enter()

    def toast(self, text, dur=3.5):
        self.toasts.append((time.time() + dur, text))

    # ------------------------------------------------------------------ 네트워크
    def host_and_connect(self, name, port=DEFAULT_PORT):
        from ..server.server import GameServer
        if self.server is None:
            try:
                srv = GameServer("0.0.0.0", port, verbose=False)
                srv.start()
                self.server = srv
            except OSError:
                self.toast("이미 이 컴퓨터에서 서버가 실행 중이라 그 서버에 접속합니다.")
        return self.connect("127.0.0.1", port, name)

    def connect(self, host, port, name):
        try:
            self.net = NetClient()
            self.net.connect(host, port)
        except OSError as e:
            self.toast(f"접속 실패: {host}:{port} ({e.strerror or e})")
            return False
        self.server_addr = f"{host}:{port}"
        self.my_name = name
        self.net.send({"t": "hello", "name": name})
        return True

    def send(self, msg):
        self.net.send(msg)

    def process_messages(self):
        from .scenes.game import GameScene
        from .scenes.lobby import LobbyScene
        from .scenes.room import RoomScene
        from .scenes.select import SelectScene
        from .scenes.title import TitleScene

        for msg in self.net.poll():
            t = msg.get("t")
            if t == "welcome":
                self.my_key = msg["key"]
                self.my_name = msg["name"]
                self.set_scene(LobbyScene(self))
            elif t == "rooms":
                self.rooms = msg["rooms"]
            elif t == "room":
                self.room = msg
                phase = msg["phase"]
                if phase == "waiting" and not isinstance(self.scene, RoomScene):
                    self.set_scene(RoomScene(self))
                elif phase == "select" and not isinstance(self.scene, SelectScene):
                    self.set_scene(SelectScene(self))
            elif t == "game_start":
                self.set_scene(GameScene(self, msg))
            elif t == "error":
                self.toast(msg.get("msg", "오류"))
            elif t == "chat":
                self.chat.append((time.time(), msg["name"], msg["text"]))
                self.chat = self.chat[-8:]
            elif t == "disconnected":
                self.room = None
                self.toast("서버와 연결이 끊어졌습니다.")
                self.set_scene(TitleScene(self))
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
            sign = -1 if team == 0 else 1
            for x, z, key in ((22, 0, "turret"), (34, 0, "turret"), (41, 0, "inhibitor"), (47, -2.6, "turret"),
                              (47, 2.6, "turret"), (51, 0, "nexus")):
                self.renderer.draw(meshes[key], model_matrix(x * sign, 0, z))

    # ------------------------------------------------------------------ 루프
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(120) / 1000.0)
            self.time += dt
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                else:
                    self.scene.handle_event(e)
            self.process_messages()
            if self.autotest:
                self.autotest.step(self, dt)
            self.scene.update(dt)
            self.scene.render3d()
            surf = self.renderer.overlay.begin()
            self.scene.draw_ui(surf)
            self.draw_toasts(surf)
            self.renderer.overlay.end()
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
        data = self.ctx.screen.read(components=3)
        img = pygame.image.frombytes(data, (WIDTH, HEIGHT), "RGB", True)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        pygame.image.save(img, path)
