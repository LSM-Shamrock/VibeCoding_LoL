"""뼈대 애니메이션 데이터(.skin.npz) 읽기 + 동작 재생기.

tools/bake_skin.py 가 .glb 캐릭터를 구워 만든 파일을 읽는다.
- 정점(위치·법선·색·UV) + 뼈 번호/가중치 : GPU 스키닝용 메시 (gl.SkinnedMesh)
- 동작(clip)마다 프레임별 뼈 행렬 : Animator 가 시간에 맞춰 골라 섞어서 셰이더로 넘긴다
"""
import json

import numpy as np

from .gl import MAX_BONES


class Clip:
    def __init__(self, name, frames, dur, loop):
        self.name = name
        self.frames = frames        # (F, MAX_BONES*16) float32 — 열 우선 4x4 행렬이 이어 붙은 형태
        self.n = len(frames)
        self.dur = max(0.05, float(dur))
        self.loop = bool(loop)

    def sample(self, t, loop=None):
        """t 초 시점의 뼈 행렬 (프레임 사이는 선형 보간)."""
        loop = self.loop if loop is None else loop
        n1 = self.n - 1
        pos = t / self.dur * n1
        if loop:
            pos %= n1
        else:
            pos = min(max(pos, 0.0), float(n1))
        i = int(pos)
        f = pos - i
        if i >= n1:
            return self.frames[n1]
        a, b = self.frames[i], self.frames[i + 1]
        return a + (b - a) * f


class SkinData:
    """파일 하나(챔피언 한 명)의 스키닝 데이터."""

    def __init__(self, path):
        z = np.load(path, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        self.fps = meta["fps"]
        self.joint_names = meta["joint_names"]
        nj = meta["joints"]
        if nj > MAX_BONES:
            raise ValueError(f"뼈가 너무 많음: {nj} > {MAX_BONES}")
        self.parts = []     # (정점 배열, 뼈 정보, 텍스처 파일 이름 또는 None)
        for i, pm in enumerate(meta["parts"]):
            self.parts.append((z[f"p{i}_arr"], z[f"p{i}_jw"], pm.get("tex")))
        self.clips = {}
        ident = np.eye(4, dtype="f4")
        pad = np.tile(ident.T.reshape(-1), MAX_BONES - nj)          # 안 쓰는 뼈는 단위 행렬
        for name, cm in meta["clips"].items():
            raw = z[f"c_{name}"]                                    # (F, J, 12): 3x4 행렬(행 우선)
            f = len(raw)
            m = np.zeros((f, nj, 4, 4), dtype="f4")
            m[:, :, :3, :] = raw.reshape(f, nj, 3, 4)
            m[:, :, 3, 3] = 1.0
            cols = m.transpose(0, 1, 3, 2).reshape(f, nj * 16)      # OpenGL 은 열 우선
            frames = np.concatenate([cols, np.tile(pad, (f, 1))], axis=1).astype("f4")
            self.clips[name] = Clip(name, frames, cm["dur"], cm["loop"])
        self.rest = self.clips["Idle"].frames[0] if "Idle" in self.clips else np.tile(ident.T.reshape(-1), MAX_BONES)

    def has(self, name):
        return name in self.clips


class Animator:
    """한 캐릭터의 동작 재생기. 동작을 바꿀 때 짧게 섞어(크로스페이드) 뚝 끊기지 않게 한다.

    play(이름, loop, speed, fade) 로 동작을 바꾸고, update(dt) 로 시간을 흘리고, bones() 로 행렬을 받는다."""

    def __init__(self, skin):
        self.skin = skin
        self.clip = None
        self.t = 0.0
        self.speed = 1.0
        self.loop = True
        self.prev = None            # 섞는 중인 이전 자세
        self.blend = 1.0            # 0 → 1 (1 이면 섞기 끝)
        self.fade = 0.12
        self.pose = skin.rest
        self._bytes = None

    @property
    def name(self):
        return self.clip.name if self.clip else None

    @property
    def finished(self):
        """한 번만 재생하는 동작이 끝까지 갔는가."""
        return bool(self.clip) and not self.loop and self.t >= self.clip.dur

    def play(self, name, loop=None, speed=1.0, fade=0.12, restart=False, start=0.0):
        clip = self.skin.clips.get(name)
        if clip is None:
            return False
        if self.clip is clip and not restart:
            self.speed = speed
            return True
        if self.clip is not None and fade > 0:
            self.prev = self.pose
            self.blend = 0.0
            self.fade = fade
        else:
            self.prev = None
            self.blend = 1.0
        self.clip = clip
        self.loop = clip.loop if loop is None else loop
        self.speed = speed
        self.t = start
        self._eval()
        return True

    def update(self, dt):
        if self.clip is None:
            return
        self.t += dt * self.speed
        if not self.loop and self.t > self.clip.dur:
            self.t = self.clip.dur
        if self.blend < 1.0:
            self.blend = min(1.0, self.blend + dt / max(self.fade, 1e-3))
        self._eval()

    def _eval(self):
        cur = self.clip.sample(self.t, self.loop)
        if self.prev is not None and self.blend < 1.0:
            k = self.blend
            cur = self.prev + (cur - self.prev) * (k * k * (3 - 2 * k))
        else:
            self.prev = None
        self.pose = cur
        self._bytes = None

    def bones(self):
        """셰이더로 넘길 뼈 행렬 (bytes)."""
        if self._bytes is None:
            self._bytes = np.ascontiguousarray(self.pose, dtype="f4").tobytes()
        return self._bytes
