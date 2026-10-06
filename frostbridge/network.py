"""Newline-delimited JSON over TCP. Only the server mutates match state."""
from dataclasses import dataclass, field
import json
import selectors
import socket
import threading
import time
import uuid

from .content import CHAMPIONS, PORT, TICK_RATE, SNAPSHOT_RATE
from .simulation import World

MAX_PACKET = 16_384
MAX_BACKLOG = 4_000_000


def encode(message):
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False)+"\n").encode("utf-8")


@dataclass
class Room:
    id: str
    name: str
    host: str
    capacity: int
    players: list = field(default_factory=list)
    phase: str = "room"
    world: World | None = None

    def snapshot(self):
        return dict(id=self.id, name=self.name, host=self.host, capacity=self.capacity,
                    players=self.players, phase=self.phase)


class Lobby:
    """Room state machine kept independent of transport for integration tests."""
    def __init__(self):
        self.rooms = {}
        self.membership = {}
        self.names = {}

    def room_for(self, uid):
        return self.rooms.get(self.membership.get(uid))

    def leave(self, uid):
        room = self.room_for(uid)
        self.membership.pop(uid, None)
        if not room:
            return
        if room.phase == "game":
            for player in room.players:
                if player["id"] == uid:
                    player["bot"] = True
                    player["name"] += " [BOT]"
                    room.world.units[uid].bot = True
                    room.world.units[uid].name = player["name"]
        else:
            room.players = [p for p in room.players if p["id"] != uid]
            if room.phase == "select":
                # A departing player leaves a vacant slot: refill in the room.
                room.phase = "room"
                for player in room.players:
                    player["locked"] = player["bot"]
        humans = [p for p in room.players if not p["bot"]]
        if not humans:
            self.rooms.pop(room.id, None)
        else:
            if room.host == uid:
                room.host = humans[0]["id"]
            self.maybe_start(room)

    @staticmethod
    def maybe_start(room):
        if room.phase == "select" and room.players and all(p["locked"] for p in room.players):
            room.world = World(room.players)
            room.phase = "game"

    def command(self, uid, message):
        if not isinstance(message, dict):
            raise ValueError("메시지는 JSON 객체여야 합니다.")
        op = message.get("op")
        room = self.room_for(uid)
        if op == "hello":
            name = str(message.get("name", "플레이어")).strip()[:18]
            self.names[uid] = name or "플레이어"
            return
        if op == "leave":
            self.leave(uid)
            return
        if op == "create":
            if room:
                raise ValueError("먼저 현재 방에서 나가 주세요.")
            capacity = message.get("capacity", 5)
            if type(capacity) is not int or not 1 <= capacity <= 5:
                raise ValueError("팀 인원은 1~5명입니다.")
            if len(self.rooms) >= 32:
                raise ValueError("서버의 방이 가득 찼습니다.")
            rid = uuid.uuid4().hex[:8]
            room = Room(rid, str(message.get("name", "서리 다리 전투")).strip()[:28] or "서리 다리 전투", uid, capacity)
            self.rooms[rid] = room
            self.add_player(room, uid, 0)
            return
        if op == "join":
            if room:
                raise ValueError("먼저 현재 방에서 나가 주세요.")
            room = self.rooms.get(str(message.get("room")))
            if not room or room.phase != "room":
                raise ValueError("입장할 수 없는 방입니다.")
            counts = [sum(p["team"] == team for p in room.players) for team in (0, 1)]
            team = 0 if counts[0] <= counts[1] else 1
            if counts[team] >= room.capacity:
                raise ValueError("방이 가득 찼습니다.")
            self.add_player(room, uid, team)
            return
        if not room:
            raise ValueError("방에 먼저 입장해 주세요.")
        player = next((p for p in room.players if p["id"] == uid and not p["bot"]), None)
        if not player:
            raise ValueError("방 참가자만 사용할 수 있습니다.")
        if op == "action" and room.phase == "game":
            room.world.command(uid, message)
            return
        if op == "team" and room.phase == "room":
            team = 1-player["team"]
            if sum(p["team"] == team for p in room.players) >= room.capacity:
                raise ValueError("상대 팀 슬롯이 가득 찼습니다.")
            player["team"] = team
            return
        if op in ("pick", "lock") and room.phase == "select":
            if op == "pick":
                champion = str(message.get("champion"))
                if champion not in CHAMPIONS:
                    raise ValueError("존재하지 않는 캐릭터입니다.")
                if player["locked"]:
                    raise ValueError("선택 해제 후 캐릭터를 변경해 주세요.")
                player["champion"] = champion
            else:
                player["locked"] = not player["locked"]
                self.maybe_start(room)
            return
        if op in ("bot", "fill", "remove_bot", "start", "cancel_select", "rematch"):
            if room.host != uid:
                raise ValueError("방장만 사용할 수 있습니다.")
            if op == "rematch" and room.phase == "game" and room.world.winner is not None:
                room.phase, room.world = "room", None
                for member in room.players:
                    member["locked"] = member["bot"]
                return
            if op == "cancel_select" and room.phase == "select":
                room.phase = "room"
                for member in room.players:
                    member["locked"] = member["bot"]
                return
            if room.phase != "room":
                raise ValueError("대기실에서만 사용할 수 있습니다.")
            if op in ("bot", "fill"):
                team = message.get("team", 0)
                if type(team) is not int or team not in (0, 1):
                    raise ValueError("잘못된 팀입니다.")
                for side in ((0, 1) if op == "fill" else (team,)):
                    empty = room.capacity-sum(p["team"] == side for p in room.players)
                    for _ in range(empty if op == "fill" else min(1, empty)):
                        bid = "bot_"+uuid.uuid4().hex[:8]
                        self.add_player(room, bid, side, bot=True)
                return
            if op == "remove_bot":
                bid = str(message.get("player"))
                room.players = [p for p in room.players if not (p["id"] == bid and p["bot"])]
                return
            if op == "start":
                counts = [sum(p["team"] == side for p in room.players) for side in (0, 1)]
                if counts != [room.capacity, room.capacity]:
                    raise ValueError("양 팀을 채워 주세요. 빈 자리는 봇으로 채울 수 있습니다.")
                room.phase = "select"
                for member in room.players:
                    member["locked"] = member["bot"]
                return
        raise ValueError("현재 단계에서 사용할 수 없는 명령입니다.")

    def add_player(self, room, uid, team, bot=False):
        champion = list(CHAMPIONS)[len(room.players) % len(CHAMPIONS)]
        name = f"{CHAMPIONS[champion]['name']} 봇" if bot else self.names.get(uid, "플레이어")
        room.players.append(dict(id=uid, name=name, team=team, bot=bot, champion=champion, locked=bot))
        if not bot:
            self.membership[uid] = room.id


@dataclass
class Peer:
    sock: socket.socket
    id: str
    incoming: bytearray = field(default_factory=bytearray)
    outgoing: bytearray = field(default_factory=bytearray)
    rate_at: float = 0
    count: int = 0


class GameServer:
    def __init__(self, host="0.0.0.0", port=PORT):
        self.lobby = Lobby()
        self.selector = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind((host, port))
            self.listener.listen(64)
            self.listener.setblocking(False)
            self.port = self.listener.getsockname()[1]
            self.selector.register(self.listener, selectors.EVENT_READ)
        except OSError:
            self.listener.close()
            self.selector.close()
            raise
        self.peers = {}
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name="frostbridge-server", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stopping.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)

    def drop(self, peer):
        if peer.id not in self.peers:
            return
        self.peers.pop(peer.id, None)
        self.lobby.leave(peer.id)
        self.lobby.names.pop(peer.id, None)
        try:
            self.selector.unregister(peer.sock)
        except (KeyError, ValueError):
            pass
        peer.sock.close()

    def queue(self, peer, message):
        if peer.id not in self.peers:
            return
        peer.outgoing.extend(encode(message))
        if len(peer.outgoing) > MAX_BACKLOG:
            self.drop(peer)
            return
        self.selector.modify(peer.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, peer)

    def accept(self):
        sock, _ = self.listener.accept()
        if len(self.peers) >= 64:
            sock.close()
            return
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        peer = Peer(sock, uuid.uuid4().hex[:12])
        self.peers[peer.id] = peer
        self.selector.register(sock, selectors.EVENT_READ, peer)
        self.queue(peer, dict(type="welcome", id=peer.id))

    def read(self, peer):
        chunk = peer.sock.recv(65536)
        if not chunk:
            self.drop(peer)
            return
        peer.incoming.extend(chunk)
        while b"\n" in peer.incoming:
            raw, _, rest = peer.incoming.partition(b"\n")
            peer.incoming = bytearray(rest)
            if len(raw) > MAX_PACKET:
                self.drop(peer)
                return
            now = time.monotonic()
            if now-peer.rate_at >= 1:
                peer.rate_at, peer.count = now, 0
            peer.count += 1
            if peer.count > 100:
                self.drop(peer)
                return
            try:
                message = json.loads(raw)
                self.lobby.command(peer.id, message)
            except (ValueError, TypeError, OverflowError, RecursionError) as error:
                reason = str(error) if isinstance(error, ValueError) else "잘못된 요청입니다."
                self.queue(peer, dict(type="error", message=reason[:160]))
        if len(peer.incoming) > MAX_PACKET:
            self.drop(peer)

    def broadcast(self):
        rooms = [room.snapshot() for room in self.lobby.rooms.values()]
        worlds = {room.id:room.world.snapshot() for room in self.lobby.rooms.values() if room.world}
        for peer in list(self.peers.values()):
            room = self.lobby.room_for(peer.id)
            self.queue(peer, dict(type="state", rooms=rooms, room=room.snapshot() if room else None,
                                  world=worlds.get(room.id) if room else None))

    def run(self):
        last = time.monotonic()
        accumulated = 0.0
        next_snapshot = last
        try:
            while not self.stopping.is_set():
                for key, mask in self.selector.select(timeout=0.005):
                    if key.data is None:
                        try:
                            self.accept()
                        except BlockingIOError:
                            pass
                        continue
                    peer = key.data
                    try:
                        if mask & selectors.EVENT_READ:
                            self.read(peer)
                        if peer.id in self.peers and mask & selectors.EVENT_WRITE:
                            sent = peer.sock.send(peer.outgoing)
                            del peer.outgoing[:sent]
                            if not peer.outgoing:
                                self.selector.modify(peer.sock, selectors.EVENT_READ, peer)
                    except BlockingIOError:
                        pass
                    except (OSError, UnicodeError):
                        self.drop(peer)
                now = time.monotonic()
                accumulated += min(now-last, 0.25)
                last = now
                while accumulated >= 1/TICK_RATE:
                    for room in list(self.lobby.rooms.values()):
                        if room.world:
                            room.world.update(1/TICK_RATE)
                    accumulated -= 1/TICK_RATE
                if now >= next_snapshot:
                    self.broadcast()
                    next_snapshot = now+1/SNAPSHOT_RATE
        finally:
            for peer in list(self.peers.values()):
                self.drop(peer)
            self.selector.close()
            self.listener.close()


class GameClient:
    def __init__(self, host, port, name):
        self.sock = socket.create_connection((host, port), timeout=2)
        self.sock.setblocking(False)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.id = ""
        self.state = {"rooms":[], "room":None, "world":None}
        self.errors = []
        self.connected = True
        self.last_receive = time.monotonic()
        self.send("hello", name=name)

    def send(self, op, **payload):
        if self.connected:
            self.outgoing.extend(encode(dict(op=op, **payload)))
            if len(self.outgoing) > MAX_BACKLOG:
                self.close()

    def pump(self):
        if not self.connected:
            return
        try:
            if self.outgoing:
                try:
                    sent = self.sock.send(self.outgoing)
                    del self.outgoing[:sent]
                except BlockingIOError:
                    pass
            while True:
                try:
                    data = self.sock.recv(262144)
                except BlockingIOError:
                    break
                if not data:
                    raise ConnectionError("서버와의 연결이 종료되었습니다.")
                self.incoming.extend(data)
                if len(self.incoming) > MAX_BACKLOG:
                    raise ConnectionError("서버 응답이 너무 큽니다.")
                while b"\n" in self.incoming:
                    raw, _, rest = self.incoming.partition(b"\n")
                    self.incoming = bytearray(rest)
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        raise ConnectionError("잘못된 서버 응답입니다.")
                    self.last_receive = time.monotonic()
                    if message.get("type") == "welcome":
                        self.id = message["id"]
                    elif message.get("type") == "state":
                        self.state = message
                    elif message.get("type") == "error":
                        self.errors.append(message["message"])
            if time.monotonic()-self.last_receive > 10:
                raise ConnectionError("서버 응답 시간이 초과되었습니다.")
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.errors.append(str(error))
            self.close()

    def close(self):
        self.connected = False
        self.sock.close()
