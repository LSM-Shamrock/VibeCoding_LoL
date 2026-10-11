"""효과음 재생. data/sounds.json 의 소리 이름 → 파일 연결을 읽어 pygame.mixer 로 재생한다.

- play(이름) 은 화면 중앙에서 나는 소리(UI·내 챔피언), play(이름, pos=(x, z)) 는 월드 좌표에서 나는 소리
  (카메라에서 멀수록 작아지고, 화면 왼쪽/오른쪽에 따라 좌우로 치우친다).
- 같은 소리가 한꺼번에 너무 자주 나오지 않게 소리마다 최소 간격(gap)이 있고, 재생 채널이 꽉 차면 새 소리는 건너뛴다.
  (pri 가 1 인 아나운서 소리는 다른 소리를 밀어내고 재생한다.)
- 사운드 장치가 없거나 파일이 없어도 게임은 그대로 돌아간다 (소리만 안 난다).
- 음량은 설정 창(ESC)에서 바꾸고 settings.json 에 저장된다.
"""
import json
import math
import os
import random
import time

import numpy as np
import pygame

from ..shared.constants import ASSET_DIR, DATA_DIR, ROOT_DIR

SOUND_DIR = os.path.join(ASSET_DIR, "sounds")
MUSIC_DIR = os.path.join(ASSET_DIR, "music")
MUSIC_GAIN = 0.35           # BGM 은 효과음 음량 슬라이더에 이 배율을 곱한 크기로 나온다
CONFIG_PATH = os.path.join(DATA_DIR, "sounds.json")
SETTINGS_PATH = os.path.join(ROOT_DIR, "settings.json")
CHANNELS = 40
WORLD_GAIN = 0.75           # 게임 속 소리(전투·스킬·발소리 …)의 전체 음량 배율 (UI·아나운서는 그대로)
NEAR_DIST = 8.0             # 이 거리 안(내 주변)에서 나는 소리는 한 번 더 줄인다
NEAR_GAIN = 0.85            # 바로 옆(거리 0)에서 나는 소리의 추가 배율


class Audio:
    def __init__(self):
        self.ok = False
        self.volume = 0.8
        self.muted = False
        self.cfg = {"sounds": {}}
        self.defs = {}
        self.cache = {}             # 파일 → pygame Sound (없으면 None)
        self.variants = {}          # (파일, 음높이 배율) → Sound
        self.last_play = {}         # 소리 이름 → 마지막 재생 시각
        self.last_file = {}         # 소리 이름 → 마지막으로 고른 파일 (연달아 같은 걸 피한다)
        self.listener = (0.0, 0.0)  # 소리를 듣는 위치 (카메라가 보는 곳)
        self.missing = set()
        self.music = None           # 지금 틀어 둔 BGM 이름 (None 이면 없음)
        self.music_ok = False
        self.load_settings()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            pygame.mixer.set_num_channels(CHANNELS)
            self.ok = True
        except pygame.error as e:
            print("[소리] 사운드 장치를 쓸 수 없어 효과음을 끕니다:", e)
        self.reload_config()

    # ------------------------------------------------------------ 설정
    def reload_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.cfg = json.load(f)
        except (OSError, ValueError) as e:
            print("[소리] sounds.json 을 읽지 못했습니다:", e)
            self.cfg = {"sounds": {}}
        self.defs = self.cfg.get("sounds", {})
        self.default_range = float(self.cfg.get("default_range", 30.0))

    def load_settings(self):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.volume = max(0.0, min(1.0, float(data.get("sfx_volume", self.volume))))
            self.muted = bool(data.get("muted", False))
        except (OSError, ValueError, TypeError):
            pass

    def save_settings(self):
        try:
            data = {}
            try:
                with open(SETTINGS_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                pass
            data["sfx_volume"] = round(self.volume, 2)
            data["muted"] = self.muted
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------ BGM (assets/music/<이름>.ogg, tools/build_bgm.py 로 생성)
    def play_music(self, name, fade_ms=1200):
        """BGM 을 반복 재생한다. 이미 같은 곡이면 그대로 둔다. name 이 None 이면 서서히 끈다."""
        if not self.ok or name == self.music:
            return
        try:
            if name is None:
                pygame.mixer.music.fadeout(fade_ms)
                self.music = None
                return
            path = os.path.join(MUSIC_DIR, name + ".ogg")
            if not os.path.exists(path):
                self.music = None
                return
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.music_volume())
            pygame.mixer.music.play(-1, fade_ms=fade_ms)
            self.music = name
        except pygame.error as e:
            print("[소리] BGM 을 재생하지 못했습니다:", e)
            self.music = None

    def music_volume(self):
        return 0.0 if self.muted else self.volume * MUSIC_GAIN

    def tick_music(self):
        """음량 설정(슬라이더·음소거)이 바뀌면 BGM 음량도 따라가게 한다. 매 프레임 불러도 가볍다."""
        if self.ok and self.music:
            v = self.music_volume()
            if abs(v - getattr(self, "_mv", -1)) > 0.001:
                self._mv = v
                pygame.mixer.music.set_volume(v)

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v))

    # ------------------------------------------------------------ 불러오기
    def _load(self, rel):
        if rel in self.cache:
            return self.cache[rel]
        snd = None
        path = os.path.join(SOUND_DIR, rel)
        try:
            snd = pygame.mixer.Sound(path)
        except (pygame.error, FileNotFoundError):
            if rel not in self.missing:
                self.missing.add(rel)
                print("[소리] 파일을 읽을 수 없음:", rel)
        self.cache[rel] = snd
        return snd

    def _pitched(self, rel, ratio):
        """음높이를 바꾼 복사본 (재생 속도를 ratio 배로 — 높아지면 짧아진다)."""
        key = (rel, ratio)
        if key in self.variants:
            return self.variants[key]
        base = self._load(rel)
        out = base
        init = pygame.mixer.get_init()
        if base is not None and init and init[1] == -16:
            try:
                ch = init[2]
                pcm = np.frombuffer(base.get_raw(), dtype=np.int16).reshape(-1, ch)
                n = len(pcm)
                m = max(2, int(n / ratio))
                src = np.linspace(0, n - 1, m)
                idx = np.arange(n)
                res = np.stack([np.interp(src, idx, pcm[:, c]) for c in range(ch)], axis=1)
                out = pygame.mixer.Sound(buffer=res.astype(np.int16).tobytes())
            except Exception:  # noqa: BLE001
                out = base
        self.variants[key] = out
        return out

    def preload(self):
        """모든 소리를 미리 읽어 둔다 (게임 중 처음 재생할 때 끊김이 없게)."""
        if not self.ok:
            return
        for d in self.defs.values():
            for rel in d.get("files", []):
                self._load(rel)

    # ------------------------------------------------------------ 재생
    def has(self, name):
        return name in self.defs

    def play(self, name, pos=None, vol=1.0, world=False):
        """소리 이름으로 재생. pos=(x, z) 면 월드의 그 위치에서 나는 소리.
        world=True 는 게임 속 소리: 전체를 조금 줄이고, 듣는 사람 바로 옆(위치 없는 내 챔피언 소리 포함)에서 나는 소리는 더 줄인다."""
        if not self.ok or self.muted or not name:
            return False
        d = self.defs.get(name)
        if d is None:
            return False
        now = time.time()
        if now - self.last_play.get(name, -9.0) < d.get("gap", 0.04):
            return False
        gain = d.get("vol", 1.0) * vol * self.volume
        left = right = 1.0
        dist = 0.0
        if pos is not None:
            dx, dz = pos[0] - self.listener[0], pos[1] - self.listener[1]
            rng = float(d.get("range", self.default_range))
            dist = math.hypot(dx, dz)
            if dist >= rng:
                return False
            gain *= (1.0 - dist / rng) ** 1.4
            pan = max(-1.0, min(1.0, dx / (rng * 0.45)))
            left = 1.0 - max(0.0, pan) * 0.65
            right = 1.0 + min(0.0, pan) * 0.65
        if world:
            gain *= WORLD_GAIN * (NEAR_GAIN + (1.0 - NEAR_GAIN) * min(1.0, dist / NEAR_DIST))
        if gain < 0.012:
            return False
        files = d.get("files") or []
        if not files:
            return False
        rel = random.choice(files)
        if len(files) > 1 and rel == self.last_file.get(name):
            rel = random.choice(files)
        self.last_file[name] = rel
        pitch = float(d.get("pitch", 0.0))
        if pitch > 0:
            snd = self._pitched(rel, random.choice((1 - pitch, 1.0, 1 + pitch)))
        else:
            snd = self._load(rel)
        if snd is None:
            return False
        ch = pygame.mixer.find_channel(force=d.get("pri", 0) > 0)
        if ch is None:
            return False
        ch.set_volume(min(1.0, gain * left), min(1.0, gain * right))
        ch.play(snd)
        self.last_play[name] = now
        return True

    # ------------------------------------------------------------ 게임 상황 → 소리 이름
    def attack_sound(self, champ_id, kind):
        """챔피언 기본 공격 소리. kind: "swing"(휘두를/쏠 때) / "hit"(맞을 때)."""
        table = self.cfg.get("attack", {})
        return (table.get(champ_id) or table.get("_default") or {}).get(kind)

    def cast_sound(self, ability):
        """스킬 데이터(JSON)에서 시전 소리 이름을 찾는다. 스킬의 "sfx" 항목이 있으면 그게 우선."""
        if ability.get("sfx"):
            return ability["sfx"]
        table = self.cfg.get("cast", {})
        typ = ability.get("type", "")
        style = ability.get("style")
        return (table.get(f"{typ}:{style}") if style else None) or table.get(typ) or table.get("_default")

    def fx_sound(self, kind, style=None):
        table = self.cfg.get("fx", {})
        return (table.get(f"{kind}:{style}") if style else None) or table.get(kind)

    def projectile_sound(self, style):
        return self.cfg.get("projectile", {}).get(style)
