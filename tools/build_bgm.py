"""BGM 합성: 외부 음원 없이 numpy 로 직접 작곡·합성해 assets/music/*.ogg 로 저장한다 (ffmpeg 필요).
  bgm_menu.ogg  - 타이틀/로비/방/챔피언 선택 (느린 아르페지오 + 패드)
  bgm_game.ogg  - 인게임 (드럼 + 베이스 + 아르페지오 + 리드, 총 64마디 루프)
사용: python tools/build_bgm.py    (곡을 바꾸고 싶으면 아래 PROG/MELODY 를 고치면 된다)
모든 곡은 이어 붙여 반복해도 끊김이 없도록 잔향을 원형으로 처리한다.
"""
import os
import subprocess
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "music")
rng = np.random.default_rng(7)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Track:
    def __init__(self, bpm, bars, beats=4):
        self.spb = 60.0 / bpm
        self.n = int(round(bars * beats * self.spb * SR))
        self.l = np.zeros(self.n)
        self.r = np.zeros(self.n)
        self.beats = beats

    def t(self, beat):
        return int(round(beat * self.spb * SR))

    def add(self, sig, beat, pan=0.0, gain=1.0):
        i = self.t(beat)
        m = min(len(sig), self.n - i)
        if m <= 0:
            return
        gl, gr = gain * (1 - max(0, pan) * 0.7), gain * (1 + min(0, pan) * 0.7)
        self.l[i:i + m] += sig[:m] * gl
        self.r[i:i + m] += sig[:m] * gr
        # 곡 끝을 넘어가는 부분은 처음으로 이어 붙인다 (루프)
        if m < len(sig):
            rest = sig[m:m + self.n]
            self.l[:len(rest)] += rest * gl
            self.r[:len(rest)] += rest * gr


def env(n, a, d, s, r_):
    e = np.ones(n)
    na, nd, nr = int(a * SR), int(d * SR), int(r_ * SR)
    na, nr = min(na, n), min(nr, n)
    e[:na] = np.linspace(0, 1, max(na, 1))
    nd = min(nd, max(n - na, 0))
    e[na:na + nd] = np.linspace(1, s, max(nd, 1))
    e[na + nd:] = s
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    from scipy.signal import lfilter
    return lfilter([1 - a], [1, -a], x)


def saw(f, n, detune=0.0, voices=1):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for v in range(voices):
        d = (v - (voices - 1) / 2) * detune
        out += 2 * ((t * f * (1 + d)) % 1.0) - 1
    return out / voices


def pad(m, dur):
    n = int(dur * SR)
    s = sum(saw(hz(m + o), n, 0.004, 3) for o in (0, 0.0)) * 0.5
    s = lowpass(s, 1400)
    return s * env(n, 0.5, 0.3, 0.8, 0.8)


def pluck(m, dur, bright=3000):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) * np.exp(-t * 6) + 0.2 * np.sin(6 * np.pi * f * t) * np.exp(-t * 9))
    return s * np.exp(-t * 4.5) * env(n, 0.004, 0, 1, 0.05)


def bell(m, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3) + 0.3 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 6)
    return s * np.exp(-t * 1.6) * env(n, 0.003, 0, 1, 0.1)


def lead(m, dur, vib=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m) * (1 + (0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t * 3, 0, 1) if vib else 0))
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sign(np.sin(ph)) * 0.35 + np.sin(ph) * 0.5 + np.sin(2 * ph) * 0.15
    s = lowpass(s, 2600)
    return s * env(n, 0.01, 0.15, 0.7, 0.12)


def bass(m, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.25 * (2 * ((t * f) % 1) - 1)
    s = lowpass(s, 700)
    return s * env(n, 0.006, 0.1, 0.8, 0.06)


def kick():
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 1.2


def snare():
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    noise = lowpass(rng.standard_normal(n), 9000) - lowpass(rng.standard_normal(n), 1200) * 0.0
    from scipy.signal import lfilter
    noise = lfilter([1, -0.9], [1], rng.standard_normal(n))
    return (noise * 0.6 + np.sin(2 * np.pi * 190 * t) * 0.5) * np.exp(-t * 20)


def hat(open_=False):
    n = int((0.25 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    from scipy.signal import lfilter
    return lfilter([1, -0.97], [1], rng.standard_normal(n)) * np.exp(-t * (14 if open_ else 70)) * 0.35


def reverb(x_l, x_r, secs=2.4, wet=0.28):
    from scipy.signal import fftconvolve
    n = len(x_l)
    k = int(secs * SR)
    t = np.arange(k) / SR
    out = []
    for x in (x_l, x_r):
        ir = rng.standard_normal(k) * np.exp(-t * 3.0)
        ir = lowpass(ir, 5000)
        ir /= np.sqrt((ir ** 2).sum())
        tri = np.concatenate([x, x, x])                  # 원형 잔향 (루프 이음매 없음)
        y = fftconvolve(tri, ir)[n:2 * n]
        out.append(x * (1 - wet) + y * wet)
    return out


def finish(tr, name, gain=0.85, rv=(2.4, 0.28)):
    l, r = reverb(tr.l, tr.r, *rv)
    peak = max(np.abs(l).max(), np.abs(r).max(), 1e-6)
    st = np.stack([l, r], 1) / peak * gain
    pcm = (np.clip(st, -1, 1) * 32767).astype("<i2")
    os.makedirs(OUT, exist_ok=True)
    wav = os.path.join(OUT, name + ".wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    ogg = os.path.join(OUT, name + ".ogg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libvorbis", "-q:a", "4", ogg], check=True)
    os.remove(wav)
    print("저장:", ogg, f"{len(st) / SR:.1f}초")


# ---------------------------------------------------------------- 화성
# 코드: (뿌리음 MIDI, [코드음 MIDI])  -- A 단조 / D 단조 계열
def tri(root, kind):
    return {"m": [0, 3, 7], "M": [0, 4, 7], "m7": [0, 3, 7, 10], "M7": [0, 4, 7, 11]}[kind]


def chord(root, kind):
    return [root + i for i in tri(root, kind)]


def melody_from(chords_per_bar, seed, density, octave=72, steps=8):
    """코드톤 위주의 선율: 마디마다 steps 개의 8분음표 자리 중 density 확률로 음을 놓는다."""
    g = np.random.default_rng(seed)
    notes = []
    last = octave
    for bar, ch in enumerate(chords_per_bar):
        tones = [n + 12 * k for n in ch for k in range(-3, 4)]
        tones = [x for x in tones if octave - 5 <= x <= octave + 9]
        pos = 0
        while pos < steps:
            if g.random() < density or pos == 0:
                cand = sorted(tones, key=lambda x: abs(x - last) + g.random() * 3)
                nxt = cand[0] if g.random() < 0.8 else cand[min(2, len(cand) - 1)]
                ln = int(g.choice([1, 2, 2, 3, 4]))
                ln = min(ln, steps - pos)
                notes.append((bar, pos / 2, ln / 2, nxt))
                last = nxt
                pos += ln
            else:
                pos += 1
    return notes


def build_menu():
    bpm, bars = 84, 16
    tr = Track(bpm, bars)
    prog = [(48, "M7"), (55, "M"), (57, "m7"), (53, "M7")] * 4          # Cmaj7 G Am7 Fmaj7 (밝고 맑은 분위기)
    chs = [chord(r, k) for r, k in prog]
    for b, (root, kind) in enumerate(prog):
        ch = chs[b]
        for m in ch:
            tr.add(pad(m, 4.1 * tr.spb), b * 4, pan=0.0, gain=0.16)
        tr.add(bass(root - 12, 3.8 * tr.spb), b * 4, gain=0.5)
        # 느린 아르페지오 (8분음표)
        order = [0, 2, 1, 3 if len(ch) > 3 else 2, 1, 2, 0, 2]
        for i, o in enumerate(order):
            m = ch[o % len(ch)] + 12
            tr.add(pluck(m, 1.2 * tr.spb), b * 4 + i * 0.5, pan=(-0.3 if i % 2 else 0.3), gain=0.22)
    if True:
        mel = melody_from(chs, 23, 0.45, octave=79)
        for bar, pos, ln, m in mel:
            if bar >= 4:                                   # 처음 4마디는 반주만
                tr.add(bell(m, ln * 2 * tr.spb + 0.8), bar * 4 + pos * 2, gain=0.20, pan=0.15)
    finish(tr, "bgm_menu", gain=0.8, rv=(3.2, 0.34))


def build_game():
    bpm, bars = 140, 64
    tr = Track(bpm, bars)
    A = [(45, "m"), (41, "M"), (48, "M"), (43, "M")]      # Am F C G
    B = [(41, "M"), (43, "M"), (45, "m"), (52, "M")]      # F G Am E  (고조)
    sections = [A, A, B, A]                                 # 16마디씩 x4 = 64
    prog = []
    for sec in sections:
        prog += sec * 4
    chs = [chord(r, k) for r, k in prog]
    mel = melody_from(chs, 31, 0.6, octave=76)
    for b, (root, kind) in enumerate(prog):
        sec = b // 16
        inner = b % 16
        ch = chs[b]
        base = b * 4
        intro = (b < 4)
        # 드럼
        for beat in range(4):
            if not (intro and beat % 2):
                tr.add(kick(), base + beat, gain=0.55)
        if b >= 2:
            tr.add(snare(), base + 1, gain=0.34)
            tr.add(snare(), base + 3, gain=0.34)
        for i in range(8):
            tr.add(hat(i == 7), base + i * 0.5, gain=0.26 if i % 2 else 0.18, pan=0.25)
        # 베이스 (8분음표 펄스)
        for i in range(8):
            m = root - 12 + (7 if i in (3, 7) and sec == 2 else 0)
            tr.add(bass(m, 0.45 * tr.spb), base + i * 0.5, gain=0.4 if i % 2 == 0 else 0.3)
        # 패드
        for m in ch:
            tr.add(pad(m, 4.05 * tr.spb), base, gain=0.1)
        # 16분음표 아르페지오
        if b >= 4:
            order = [0, 1, 2, 1] * 4
            for i, o in enumerate(order):
                m = ch[o % len(ch)] + 12
                tr.add(pluck(m, 0.5 * tr.spb), base + i * 0.25, gain=0.12, pan=(-0.4 if i % 2 else 0.4))
    for bar, pos, ln, m in mel:
        if bar >= 8 and not (24 <= bar < 32 and False):
            tr.add(lead(m, ln * 2 * tr.spb * 0.95 + 0.1), bar * 4 + pos * 2, gain=0.26, pan=0.1)
    finish(tr, "bgm_game", gain=0.8, rv=(1.8, 0.22))


if __name__ == "__main__":
    build_menu()
    build_game()
