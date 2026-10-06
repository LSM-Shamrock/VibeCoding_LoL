"""개발용 자동 진행: 타이틀 → 로비 → 방(봇 추가) → 선택 → 게임, 단계마다 스크린샷."""
import os


class AutoTest:
    def __init__(self, out_dir, team_size=3):
        self.out = out_dir
        self.size = team_size
        self.stage = "title"
        self.t = 0.0
        self.stage_t = 0.0
        self.shot = None
        self.done = set()

    def snap(self, name):
        self.shot = os.path.join(self.out, f"{name}.png")
        print("[autotest] screenshot", name, flush=True)

    def once(self, key):
        if key in self.done:
            return False
        self.done.add(key)
        return True

    def goto(self, stage):
        self.stage = stage
        self.stage_t = 0.0

    def step(self, app, dt):
        self.t += dt
        self.stage_t += dt
        name = type(app.scene).__name__
        st = self.stage_t
        if self.stage == "title" and name == "TitleScene":
            if st > 1.0 and self.once("title"):
                self.snap("01_title")
            if st > 1.3 and self.once("host"):
                app.host_and_connect("테스터")
        if name == "LobbyScene" and self.stage == "title":
            self.goto("lobby")
        elif self.stage == "lobby":
            if st > 0.6 and self.once("lobby"):
                self.snap("01b_lobby")
            if st > 0.8 and self.once("create"):
                app.send({"t": "create_room", "name": "자동 테스트 방", "size": self.size})
            if name == "RoomScene":
                self.goto("room")
        elif self.stage == "room":
            if st > 0.3 and self.once("bots"):
                for _ in range(self.size - 1):
                    app.send({"t": "add_bot", "team": 0})
                for _ in range(self.size):
                    app.send({"t": "add_bot", "team": 1})
            if st > 1.2 and self.once("room"):
                self.snap("02_room")
            if st > 1.5 and self.once("start"):
                app.send({"t": "start_game"})
            if name == "SelectScene":
                self.goto("select")
        elif self.stage == "select":
            if st > 1.5 and self.once("select"):
                self.snap("03_select")
            if st > 1.8 and self.once("lock"):
                app.send({"t": "lock"})
            if name == "GameScene":
                self.goto("game")
        elif self.stage == "game":
            sc = app.scene
            if name != "GameScene":
                return
            if st > 0.5 and self.once("level"):
                for slot in ("Q", "E", "W", "R"):
                    sc.send_cmd(c="level", slot=slot)
            if st > 2.0 and self.once("g1"):
                self.snap("04_game_start")
            if st > 2.5 and self.once("shop"):
                sc.shop_open = True
            if st > 3.0 and self.once("g_shop"):
                self.snap("05_shop")
            if st > 3.3 and self.once("buy"):
                sc.send_cmd(c="buy", item="swift_boots")
                sc.send_cmd(c="buy", item="long_sword")
                sc.shop_open = False
            if st > 3.5 and self.once("walk"):
                d = 1 if sc.my_team == 0 else -1
                sc.issue_move(-24 * d, 1.0)
            if st > 4.2 and self.once("marker"):
                self.snap("05b_move_marker")
                print("[autotest] window", app.renderer.window_size, "viewport", app.renderer.viewport, "fullscreen", app.fullscreen, flush=True)
            if st > 5.0 and self.once("mm"):
                sc.minimap_camera((1200, 660))
            if st > 5.3 and self.once("mmshot"):
                self.snap("05c_minimap_cam")
                sc.cam_locked = True
            if st > 24 and self.once("g2"):
                self.snap("06_lane")
            if st > 30 and self.once("amove"):
                d = 1 if sc.my_team == 0 else -1
                sc.send_cmd(c="amove", x=-6 * d, z=0.0)
            if st > 25 and self.once("g3"):
                sc.aiming = "R"
                sc.fake_mouse = (760, 330)
            if st > 25.3 and self.once("g3b"):
                self.snap("07_fight_aim")
            if st > 25.6 and self.once("cast"):
                sc.aiming = None
                sc.cast_slot("R")
                sc.fake_mouse = None
            if st > 26.2 and self.once("g4r"):
                self.snap("07b_ult")
            if st > 44 and self.once("g4"):
                self.snap("08_fight")
            if st > 44.3 and self.once("tab"):
                sc.show_score = True
            if st > 44.6 and self.once("g5"):
                self.snap("09_score")
                sc.show_score = False
            if st > 45 and self.once("quit"):
                app.running = False

    def after_frame(self, app):
        if self.shot:
            app.screenshot(self.shot)
            self.shot = None
