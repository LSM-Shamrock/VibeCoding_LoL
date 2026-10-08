"""로비 / 방 / 게임 진행을 관리하는 TCP 서버.

클라이언트 하나가 '호스트'로 이 서버를 같은 프로세스에서 띄울 수도 있고,
server.py 로 전용 서버만 따로 실행할 수도 있다.
"""
import itertools
import socket
import threading
import time

from ..shared import data as gamedata
from ..shared.constants import BLUE, DEFAULT_PORT, MAX_TEAM_SIZE, RED, SELECT_TIME, SNAPSHOT_EVERY, TICK_RATE
from ..shared.net import Connection, encode
from .sim import Simulation

RETURN_TO_ROOM_DELAY = 8.0


class Client:
    def __init__(self, key, conn):
        self.key = key
        self.conn = conn
        self.name = key
        self.room = None


class Member:
    def __init__(self, key, name, team, bot=False, client=None):
        self.key = key
        self.name = name
        self.team = team
        self.bot = bot
        self.client = client
        self.champ = None
        self.locked = False

    def public(self):
        return {"key": self.key, "name": self.name, "team": self.team, "bot": self.bot,
                "champ": self.champ, "locked": self.locked}


class Room:
    def __init__(self, rid, name, team_size, host_key):
        self.id = rid
        self.name = name
        self.team_size = team_size
        self.host_key = host_key
        self.members = []
        self.phase = "waiting"       # waiting / select / ingame / ended
        self.select_deadline = 0.0
        self.sim = None
        self.ended_at = 0.0
        self.tick = 0

    def team_members(self, team):
        return [m for m in self.members if m.team == team]

    def humans(self):
        return [m for m in self.members if not m.bot]

    def member(self, key):
        for m in self.members:
            if m.key == key:
                return m
        return None

    def summary(self):
        return {"id": self.id, "name": self.name, "size": self.team_size, "count": len(self.members),
                "humans": len(self.humans()), "phase": self.phase,
                "host": next((m.name for m in self.members if m.key == self.host_key), "?")}

    def state(self):
        return {"t": "room", "id": self.id, "name": self.name, "size": self.team_size, "host": self.host_key,
                "phase": self.phase, "members": [m.public() for m in self.members],
                "select_left": max(0.0, self.select_deadline - time.time()) if self.phase == "select" else 0}


class GameServer:
    def __init__(self, host="0.0.0.0", port=DEFAULT_PORT, verbose=True):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.lock = threading.RLock()
        self.clients = {}
        self.rooms = {}
        self._ids = itertools.count(1)
        self._room_ids = itertools.count(1)
        self.running = False
        self.sock = None

    def log(self, *a):
        if self.verbose:
            print("[서버]", *a, flush=True)

    # ------------------------------------------------------------------ 시작
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(16)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._game_loop, daemon=True).start()
        self.log(f"{self.host}:{self.port} 에서 대기 중")

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _accept_loop(self):
        while self.running:
            try:
                sock, addr = self.sock.accept()
            except OSError:
                break
            # 락을 잡은 채로 연결을 만들어, 첫 메시지가 conn 할당보다 먼저 처리되지 않게 한다
            with self.lock:
                key = f"p{next(self._ids)}"
                client = Client(key, None)
                self.clients[key] = client
                client.conn = Connection(sock, lambda conn, msg, k=key: self._on_message(k, msg),
                                         lambda conn, k=key: self._on_close(k))
            self.log("접속:", addr, key)

    # ------------------------------------------------------------------ 메시지
    def _on_close(self, key):
        with self.lock:
            client = self.clients.pop(key, None)
            if client and client.room:
                self.leave_room(client)
            self.log("접속 종료:", key)

    def _on_message(self, key, msg):
        with self.lock:
            client = self.clients.get(key)
            if client is None:
                return
            try:
                self.handle(client, msg)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                client.conn.send({"t": "error", "msg": f"서버 오류: {e}"})

    def send_rooms(self, client=None):
        msg = {"t": "rooms", "rooms": [r.summary() for r in self.rooms.values()]}
        targets = [client] if client else [c for c in self.clients.values() if c.room is None]
        for c in targets:
            c.conn.send(msg)

    def broadcast_room(self, room):
        st = room.state()
        for m in room.humans():
            m.client.conn.send(st)
        self.send_rooms()

    def error(self, client, text):
        client.conn.send({"t": "error", "msg": text})

    def handle(self, client, msg):
        t = msg.get("t")
        room = self.rooms.get(client.room) if client.room else None

        if t == "hello":
            client.name = (str(msg.get("name") or client.key)).strip()[:16] or client.key
            client.conn.send({"t": "welcome", "key": client.key, "name": client.name})
            self.send_rooms(client)
        elif t == "list_rooms":
            self.send_rooms(client)
        elif t == "create_room":
            if room:
                return self.error(client, "이미 방에 들어가 있습니다.")
            size = max(1, min(MAX_TEAM_SIZE, int(msg.get("size", 5))))
            name = (str(msg.get("name") or f"{client.name}의 방")).strip()[:24]
            r = Room(next(self._room_ids), name, size, client.key)
            self.rooms[r.id] = r
            self.join(client, r)
        elif t == "join_room":
            r = self.rooms.get(int(msg.get("id", -1)))
            if r is None:
                return self.error(client, "방이 존재하지 않습니다.")
            if r.phase != "waiting":
                return self.error(client, "이미 게임이 진행 중인 방입니다.")
            if len(r.members) >= r.team_size * 2:
                return self.error(client, "방이 가득 찼습니다.")
            self.join(client, r)
        elif room is None:
            return
        elif t == "leave_room":
            self.leave_room(client)
            self.send_rooms(client)
        elif t == "switch_team":
            m = room.member(client.key)
            team = int(msg.get("team", 0))
            if room.phase == "waiting" and m and team in (BLUE, RED) and team != m.team:
                if len(room.team_members(team)) < room.team_size:
                    m.team = team
                    self.broadcast_room(room)
        elif t == "add_bot":
            team = int(msg.get("team", 0))
            if client.key != room.host_key or room.phase != "waiting" or team not in (BLUE, RED):
                return
            if len(room.team_members(team)) >= room.team_size:
                return self.error(client, "팀 자리가 없습니다.")
            room.members.append(Member(f"b{next(self._ids)}", "봇", team, bot=True))
            self.broadcast_room(room)
        elif t == "remove_bot":
            if client.key != room.host_key or room.phase != "waiting":
                return
            m = room.member(msg.get("key"))
            if m and m.bot:
                room.members.remove(m)
                self.broadcast_room(room)
        elif t == "set_size":
            if client.key != room.host_key or room.phase != "waiting":
                return
            size = max(1, min(MAX_TEAM_SIZE, int(msg.get("size", room.team_size))))
            for team in (BLUE, RED):
                while len(room.team_members(team)) > size:
                    bots = [m for m in room.team_members(team) if m.bot]
                    if not bots:
                        return self.error(client, "사람 플레이어가 있어 팀 인원을 줄일 수 없습니다.")
                    room.members.remove(bots[-1])
            room.team_size = size
            self.broadcast_room(room)
        elif t == "start_game":
            if client.key != room.host_key or room.phase != "waiting":
                return
            if not room.team_members(BLUE) or not room.team_members(RED):
                return self.error(client, "양 팀에 최소 1명씩 있어야 합니다.")
            self.begin_select(room)
        elif t == "pick":
            m = room.member(client.key)
            cid = msg.get("champ")
            if room.phase == "select" and m and not m.locked and gamedata.champion(cid):
                m.champ = cid
                self.broadcast_room(room)
        elif t == "lock":
            m = room.member(client.key)
            if room.phase == "select" and m and m.champ:
                m.locked = True
                self.broadcast_room(room)
                if all(x.locked for x in room.members):
                    self.begin_game(room)
        elif t == "cmd":
            if room.phase == "ingame" and room.sim:
                room.sim.handle_command(client.key, msg)
        elif t == "chat":
            text = str(msg.get("text", ""))[:120]
            if text:
                for m in room.humans():
                    m.client.conn.send({"t": "chat", "name": client.name, "text": text})

    # ------------------------------------------------------------------ 방 흐름
    def join(self, client, room):
        blue, red = len(room.team_members(BLUE)), len(room.team_members(RED))
        team = BLUE if blue <= red else RED
        if len(room.team_members(team)) >= room.team_size:
            team = RED if team == BLUE else BLUE
        room.members.append(Member(client.key, client.name, team, client=client))
        client.room = room.id
        self.broadcast_room(room)

    def leave_room(self, client):
        room = self.rooms.get(client.room)
        client.room = None
        if room is None:
            return
        m = room.member(client.key)
        if m:
            if room.phase == "ingame" and room.sim:
                # 게임 중 나가면 봇이 이어서 조종
                m.bot = True
                m.client = None
                m.name = f"{m.name}(봇)"
                ch = room.sim.by_key.get(m.key)
                if ch:
                    from .bot import BotBrain
                    ch.is_bot = True
                    room.sim.brains[ch.id] = BotBrain(ch)
            else:
                room.members.remove(m)
        if not room.humans():
            del self.rooms[room.id]
            self.log("방 삭제:", room.name)
            self.send_rooms()
            return
        if room.host_key == client.key:
            room.host_key = room.humans()[0].key
        self.broadcast_room(room)

    def begin_select(self, room):
        room.phase = "select"
        room.select_deadline = time.time() + SELECT_TIME
        for m in room.members:
            m.champ = None
            m.locked = False
            if m.bot:
                m.champ = gamedata.default_champion_id()
                m.locked = True
        self.broadcast_room(room)

    def begin_game(self, room):
        for m in room.members:
            if not m.champ:
                m.champ = gamedata.default_champion_id()
            m.locked = True
        members = [{"key": m.key, "name": m.name, "team": m.team, "bot": m.bot, "champ": m.champ}
                   for m in room.members]
        room.sim = Simulation(members)
        room.phase = "ingame"
        room.tick = 0
        info = room.sim.static_info()
        for m in room.humans():
            m.client.conn.send({"t": "game_start", "you": m.key, **info})
        self.send_rooms()
        self.log("게임 시작:", room.name, [(m.name, m.team) for m in room.members])

    # ------------------------------------------------------------------ 게임 루프
    def _game_loop(self):
        dt = 1.0 / TICK_RATE
        next_t = time.perf_counter()
        while self.running:
            now = time.perf_counter()
            if now < next_t:
                time.sleep(min(dt, next_t - now))
                continue
            next_t += dt
            if now - next_t > 0.5:      # 너무 밀리면 따라잡지 않고 버린다
                next_t = now + dt
            with self.lock:
                for room in list(self.rooms.values()):
                    try:
                        self._tick_room(room, dt)
                    except Exception:  # noqa: BLE001
                        import traceback
                        traceback.print_exc()

    def _tick_room(self, room, dt):
        if room.phase == "select":
            if time.time() >= room.select_deadline:
                self.begin_game(room)
            return
        if room.phase == "ingame":
            sim = room.sim
            sim.update(dt)
            room.tick += 1
            if room.tick % SNAPSHOT_EVERY == 0 or sim.winner is not None:
                data = encode(sim.snapshot())
                for m in room.humans():
                    m.client.conn.send_raw(data)
            if sim.winner is not None:
                room.phase = "ended"
                room.ended_at = time.time()
                for m in room.humans():
                    m.client.conn.send({"t": "game_over", "winner": sim.winner})
                self.send_rooms()
            return
        if room.phase == "ended" and time.time() - room.ended_at >= RETURN_TO_ROOM_DELAY:
            room.phase = "waiting"
            room.sim = None
            # 게임 중 나간 사람(봇으로 전환됨)은 방에서 제거
            room.members = [m for m in room.members if not (m.bot and m.name.endswith("(봇)"))]
            for m in room.members:
                m.locked = False
            self.broadcast_room(room)


def run_dedicated(port=DEFAULT_PORT):
    srv = GameServer("0.0.0.0", port)
    srv.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
