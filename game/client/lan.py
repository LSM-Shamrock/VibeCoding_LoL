"""같은 네트워크(와이파이)에서 호스트가 방송하는 열린 방 목록을 받는다 (UDP, game/server/server.py 의 _beacon_loop)."""
import json
import socket
import time

from ..shared.constants import DISCOVERY_PORT

EXPIRE = 4.0        # 이 시간 동안 방송이 없으면 목록에서 뺀다


class LanFinder:
    def __init__(self):
        self.sock = None
        self.seen = {}          # (ip, tcp 포트) -> (마지막으로 받은 시각, 방 목록)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            s.setblocking(False)
            self.sock = s
        except OSError:
            self.sock = None    # 포트를 못 쓰면 목록만 비어 있고 직접 접속은 그대로 된다

    def poll(self):
        """받은 방송을 반영하고 지금 열려 있는 방 목록 [{ip, port, id, name, host, count, size, phase}] 을 돌려준다."""
        now = time.time()
        while self.sock is not None:
            try:
                data, addr = self.sock.recvfrom(8192)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
                if msg.get("g") != "kalbaram":
                    continue
                self.seen[(addr[0], int(msg["port"]))] = (now, list(msg["rooms"]))
            except (ValueError, KeyError, TypeError):
                continue
        self.seen = {k: v for k, v in self.seen.items() if now - v[0] < EXPIRE}
        out = []
        for (ip, port), (_t, rooms) in sorted(self.seen.items()):
            for r in rooms:
                out.append({"ip": ip, "port": port, **r})
        return out

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
