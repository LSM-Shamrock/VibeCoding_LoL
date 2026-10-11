"""챔피언 한 명의 동작 제어: 서버가 알려주는 상태(가만히/이동/공격/시전/기절/사망 …)를 뼈대 동작으로 바꾼다.

동작 이름은 챔피언 JSON 의 model.anim 에서 정한다 (README "챔피언 모델 애니메이션" 참고).
    "idle" "run" "death" "spawn" "air" "stun" "recall" "win" : 상태별 동작 (생략하면 아래 DEFAULTS)
    "attack"                : 기본 공격 동작 (목록이면 돌아가며 쓴다)
    "Q" "W" "E" "R"         : 스킬을 쓸 때 동작
    "cast"                  : 스킬 동작이 따로 없을 때 쓰는 기본 시전 동작
값은 동작 이름 문자열, 또는 {"clip": 이름, "speed": 배속, "max": 최대 재생 시간(초)} 형태.
"""
from .skin import Animator

DEFAULTS = {
    "idle": "Idle", "run": "Running_A", "death": "Death_A", "spawn": "Jump_Land", "air": "Jump_Idle",
    "stun": "Hit_B", "recall": "Spellcasting", "win": "Cheer",
}

HIT_FRAC = 0.4          # 공격 동작에서 "때리는 순간"이 시작 부분 몇 % 쯤인가 (서버의 선딜이 끝나는 순간과 맞춘다)
DEATH_SHOW = 2.2        # 죽은 뒤 쓰러진 모습을 보여 주는 시간 (초)
DEATH_FADE = 0.6        # 그중 마지막 몇 초 동안 서서히 사라진다
RUN_BASE_MS = 345       # 이동속도가 이 값(= 이동속도 3.45)일 때 달리기 동작을 1배속으로 재생


class ChampAnim:
    is_rig = False
    def __init__(self, skin, cfg=None, base_attack_speed=0.7):
        self.skin = skin
        self.cfg = cfg or {}
        self.anim = Animator(skin)
        self.base_as = base_attack_speed
        self.clock = 0.0
        self.act_kind = None        # 재생 중인 한 번짜리 동작 종류: attack / cast / spawn / win
        self.act_start = 0.0
        self.act_end = 0.0
        self.attack_i = 0
        self.prev_a = 0
        self.last_attack = -9.0
        self.last_cast = -9.0
        self.was_dead = False
        self.dead_clock = 0.0
        self.alive_clock = 99.0     # 부활한 지 얼마나 됐나
        self.won = False
        self._loco(force=True)

    # ------------------------------------------------------------ 동작 이름 찾기
    def entries(self, key):
        v = self.cfg.get(key)
        if v is None:
            v = DEFAULTS.get(key)
        if v is None:
            return []
        if not isinstance(v, list):
            v = [v]
        out = []
        for it in v:
            it = {"clip": it} if isinstance(it, str) else it
            if self.skin.has(it["clip"]):
                out.append(it)
        return out

    def first(self, key):
        e = self.entries(key)
        return e[0] if e else None

    # ------------------------------------------------------------ 한 번짜리 동작
    def _start(self, kind, ent, speed, length):
        self.act_kind = kind
        self.act_start = self.clock
        self.act_end = self.clock + length
        self.anim.play(ent["clip"], loop=False, speed=speed, fade=0.07, restart=True)

    def attack(self, windup):
        """기본 공격 시작 (windup: 서버의 공격 선딜 시간)."""
        ents = self.entries("attack")
        if not ents:
            return
        ent = ents[self.attack_i % len(ents)]
        self.attack_i += 1
        dur = self.skin.clips[ent["clip"]].dur
        speed = ent.get("speed") or min(3.5, max(1.2, dur * HIT_FRAC / max(windup, 0.12)))
        length = min(dur / speed, ent.get("max", 1.2))
        self._start("attack", ent, speed, length)
        self.last_attack = self.clock

    def cast(self, slot):
        """스킬 시전 (slot: "Q" "W" "E" "R")."""
        ent = self.first(slot) or self.first("cast")
        if not ent:
            return
        dur = self.skin.clips[ent["clip"]].dur
        max_t = ent.get("max", 1.0)
        speed = ent.get("speed") or max(1.0, min(2.5, dur / max_t))
        length = min(dur / speed, max_t)
        self._start("cast", ent, speed, length)
        self.last_cast = self.clock

    def play_key(self, key):
        """미리보기용: 이름(attack / Q / W / E / R)으로 동작을 한 번 보여 준다."""
        if key == "attack":
            self.attack(0.4)
        else:
            self.cast(key)

    def win(self):
        ent = self.first("win")
        if ent and not self.won:
            self.won = True
            self._start("win", ent, 1.0, 1e9)

    # ------------------------------------------------------------ 매 프레임
    def _loco(self, moving=False, speed=1.0, force=False):
        key = "run" if moving else "idle"
        ent = self.first(key) or self.first("idle")
        if ent:
            self.anim.play(ent["clip"], loop=True, speed=speed if moving else 1.0, fade=0.15)

    def update(self, dt, d, ent=None):
        """dt: 지난 시간, d: 서버가 보낸 이 챔피언의 상태 (없으면 가만히). ent: 화면 위치 정보 (절차적 리그만 씀)."""
        dt = min(dt, 0.1)
        self.clock += dt
        d = d or {}
        st = d.get("st", ())
        a = d.get("a", 0)
        dead = bool(d.get("dead"))

        if dead:
            if not self.was_dead:
                self.was_dead = True
                self.dead_clock = 0.0
                self.act_kind = None
                ent = self.first("death")
                if ent:
                    self.anim.play(ent["clip"], loop=False, speed=1.0, fade=0.08, restart=True)
            self.dead_clock += dt
            self.anim.update(dt)
            self.prev_a = a
            return
        if self.was_dead:           # 부활
            self.was_dead = False
            self.alive_clock = 0.0
            self.act_kind = None
            ent = self.first("spawn")
            if ent:
                self._start("spawn", ent, 1.0, min(self.skin.clips[ent["clip"]].dur, 0.7))
        self.alive_clock += dt

        # 새로 시작된 기본 공격 / 시전 (이벤트를 못 받은 경우를 위한 보조)
        if self.act_kind != "win":
            if a == 2:
                period = 1.0 / max(0.2, (d.get("s") or {}).get("aspd", self.base_as))
                if self.prev_a != 2 or self.clock - self.last_attack > period * 0.9:
                    self.attack(max(0.08, 0.22 * period))
            elif a == 3 and self.prev_a != 3 and self.clock - self.last_cast > 0.35:
                self.cast("cast")
        self.prev_a = a

        # 한 번짜리 동작이 끝났거나, 움직이기 시작하면 끊는다
        if self.act_kind and self.act_kind != "win":
            elapsed = self.clock - self.act_start
            if self.clock >= self.act_end or (a == 1 and elapsed >= (0.3 if self.act_kind == "cast" else 0.0)):
                self.act_kind = None

        if "air" in st:
            self.act_kind = None
            ent = self.first("air")
            if ent:
                self.anim.play(ent["clip"], loop=True, fade=0.1)
        elif "stun" in st or "caged" in st:
            self.act_kind = None
            ent = self.first("stun")
            if ent:
                self.anim.play(ent["clip"], loop=False, fade=0.08)
        elif self.act_kind:
            pass                    # 한 번짜리 동작 재생 중
        elif d.get("rc", 0) > 0:
            ent = self.first("recall")
            if ent:
                self.anim.play(ent["clip"], loop=True, fade=0.15)
        else:
            ms = (d.get("s") or {}).get("ms", RUN_BASE_MS)
            self._loco(a == 1, min(1.6, max(0.8, ms / RUN_BASE_MS)))
        self.anim.update(dt)

    # ------------------------------------------------------------ 그리기 정보
    @property
    def corpse_visible(self):
        """죽은 모습을 아직 그려야 하는가."""
        return self.dead_clock < DEATH_SHOW

    @property
    def alpha(self):
        if self.was_dead:
            return max(0.0, min(1.0, (DEATH_SHOW - self.dead_clock) / DEATH_FADE))
        return 1.0

    def bones(self):
        return self.anim.bones()
