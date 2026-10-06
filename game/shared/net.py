"""줄 단위 JSON TCP 프로토콜.

모든 메시지는 {"t": "<종류>", ...} 형태의 JSON 한 줄이다.
"""
import json
import queue
import socket
import threading


def encode(msg):
    return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


class Connection:
    """소켓 하나를 감싸 읽기/쓰기 스레드를 돌린다.

    on_message(conn, msg) 와 on_close(conn) 콜백은 읽기 스레드에서 호출된다.
    """

    def __init__(self, sock, on_message, on_close):
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.on_message = on_message
        self.on_close = on_close
        self.alive = True
        self._out = queue.Queue()
        self._closed_once = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._writer, daemon=True).start()

    def send(self, msg):
        if self.alive:
            self._out.put(encode(msg))

    def send_raw(self, data):
        if self.alive:
            self._out.put(data)

    def close(self):
        if not self._closed_once.acquire(blocking=False):
            return
        self.alive = False
        self._out.put(None)
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        try:
            self.on_close(self)
        except Exception as e:  # noqa: BLE001
            print("[net] on_close 오류:", e)

    def _reader(self):
        buf = b""
        try:
            while self.alive:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    self.on_message(self, msg)
        except OSError:
            pass
        finally:
            self.close()

    def _writer(self):
        try:
            while True:
                data = self._out.get()
                if data is None:
                    break
                # 쌓인 메시지를 한 번에 보낸다
                parts = [data]
                while not self._out.empty():
                    nxt = self._out.get_nowait()
                    if nxt is None:
                        self.sock.sendall(b"".join(parts))
                        return
                    parts.append(nxt)
                self.sock.sendall(b"".join(parts))
        except OSError:
            pass
        finally:
            self.close()


class NetClient:
    """클라이언트 쪽 연결. 받은 메시지는 큐에 쌓고 메인 루프에서 poll() 로 꺼낸다."""

    def __init__(self):
        self.conn = None
        self.inbox = queue.Queue()
        self.connected = False

    def connect(self, host, port, timeout=3.0):
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(None)
        self.connected = True
        self.conn = Connection(sock, self._on_message, self._on_close)

    def _on_message(self, conn, msg):
        self.inbox.put(msg)

    def _on_close(self, conn):
        self.connected = False
        self.inbox.put({"t": "disconnected"})

    def send(self, msg):
        if self.conn and self.connected:
            self.conn.send(msg)

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if self.conn:
            self.conn.close()
