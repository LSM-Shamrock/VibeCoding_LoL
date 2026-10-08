"""서버 시뮬레이션 유닛 정의."""
import math

from ..shared import data as gamedata
from ..shared.constants import PLATE_GOLD, START_GOLD, START_LEVEL, TURRET_PLATES


class Unit:
    kind = "unit"

    def __init__(self, uid, team, x, z, radius):
        self.id = uid
        self.team = team
        self.x = x
        self.z = z
        self.radius = radius
        self.hp = 1.0
        self.max_hp = 1.0
        self.alive = True
        self.armor = 0.0
        self.mr = 0.0
        self.facing = 0.0
        self.anim = 0               # 0 대기, 1 이동, 2 공격, 3 시전
        self.slows = []             # [(만료 시각, 둔화율)]
        self.stun_until = 0.0
        self.root_until = 0.0

    # ---- 상태이상 ----
    def stunned(self, t):
        return t < self.stun_until

    def rooted(self, t):
        return t < self.root_until or t < self.stun_until

    def slow_amount(self, t):
        self.slows = [s for s in self.slows if s[0] > t]
        return max((s[1] for s in self.slows), default=0.0)

    def apply_slow(self, t, amount, duration):
        self.slows.append((t + duration, amount))

    def apply_stun(self, t, duration):
        self.stun_until = max(self.stun_until, t + duration)

    def dist_to(self, other):
        return math.hypot(other.x - self.x, other.z - self.z)

    def dist_xy(self, x, z):
        return math.hypot(x - self.x, z - self.z)


class Champion(Unit):
    kind = "champion"

    def __init__(self, uid, team, x, z, member_key, name, champ_id, is_bot):
        cdata = gamedata.champion(champ_id)
        super().__init__(uid, team, x, z, cdata["stats"].get("radius", 0.55))
        self.member_key = member_key
        self.name = name
        self.champ_id = champ_id
        self.data = cdata
        self.is_bot = is_bot

        self.level = START_LEVEL
        self.xp = 0.0
        self.gold = float(START_GOLD)
        self.items = []
        self.ranks = {"Q": 0, "W": 0, "E": 0, "R": 0}
        self.skill_points = START_LEVEL
        self.ready_at = {"Q": 0.0, "W": 0.0, "E": 0.0, "R": 0.0, "D": 0.0, "F": 0.0}

        self.buffs = []              # [{"until", "attack_speed_pct", "move_speed_pct"}]
        self.empower = None          # {"until", "magic"}
        self.attack_count = 0

        self.dead = False
        self.respawn_at = 0.0
        self.kills = self.deaths = self.assists = self.cs = 0
        self.damage_log = {}         # {적 챔피언 id: 마지막으로 피해를 준 시각}

        # 명령 상태
        self.move_target = None
        self.attack_target = None
        self.attack_move = False
        self.attack_ready_at = 0.0
        self.windup = None           # (발사 시각, 대상 id)
        self.dash = None             # {"x","z","speed","follow","on_end"}
        self.cast_anim_until = 0.0
        self.mark = None             # (표식 대상 id, 만료 시각)
        self.recall_at = None        # 귀환 완료 시각 (정신집중 중일 때만)
        self.last_hit_at = -99.0     # 마지막으로 피해를 받은 시각 (봇의 귀환 판단용)

        self.stats = {}
        self.recompute_stats(0.0, first=True)
        self.hp = self.max_hp
        self.mana = self.max_mana

    def recompute_stats(self, t, first=False):
        s = self.data["stats"]
        lv = self.level - 1
        item_stats = {}
        for iid in self.items:
            for k, v in gamedata.items()[iid]["stats"].items():
                item_stats[k] = item_stats.get(k, 0.0) + v
        self.buffs = [b for b in self.buffs if b["until"] > t]
        buff_as = sum(b.get("attack_speed_pct", 0.0) for b in self.buffs)
        buff_ms = sum(b.get("move_speed_pct", 0.0) for b in self.buffs)

        base_ad = s["ad"] + s["ad_per_level"] * lv
        old_max_hp = getattr(self, "max_hp", 0)
        old_max_mana = getattr(self, "max_mana", 0)
        st = {
            "max_hp": s["hp"] + s["hp_per_level"] * lv + item_stats.get("hp", 0),
            "max_mana": s["mana"] + s["mana_per_level"] * lv + item_stats.get("mana", 0),
            "hp_regen": s["hp_regen"] + s["hp_regen_per_level"] * lv + item_stats.get("hp_regen", 0),
            "mana_regen": s["mana_regen"] + s["mana_regen_per_level"] * lv,
            "base_ad": base_ad,
            "bonus_ad": item_stats.get("ad", 0),
            "ad": base_ad + item_stats.get("ad", 0),
            "ap": item_stats.get("ap", 0),
            "armor": s["armor"] + s["armor_per_level"] * lv + item_stats.get("armor", 0),
            "mr": s["mr"] + s["mr_per_level"] * lv + item_stats.get("mr", 0),
            "attack_speed": min(2.5, s["attack_speed"] * (1 + s["attack_speed_per_level"] * lv
                                                          + item_stats.get("attack_speed", 0) + buff_as)),
            "attack_range": s["attack_range"],
            "ability_haste": item_stats.get("ability_haste", 0),
            "crit": min(1.0, item_stats.get("crit", 0)),
            "life_steal": item_stats.get("life_steal", 0),
        }
        ms = (s["move_speed"] + item_stats.get("move_speed", 0)) * (1 + buff_ms)
        st["move_speed"] = ms * (1 - self.slow_amount(t))
        self.stats = st
        self.max_hp = st["max_hp"]
        self.max_mana = st["max_mana"]
        self.armor = st["armor"]
        self.mr = st["mr"]
        if not first:
            # 최대 체력이 늘어나면 늘어난 만큼 현재 체력도 올려준다
            if self.max_hp > old_max_hp:
                self.hp += self.max_hp - old_max_hp
            if self.max_mana > old_max_mana:
                self.mana += self.max_mana - old_max_mana
            self.hp = min(self.hp, self.max_hp)
            self.mana = min(self.mana, self.max_mana)

    def cooldown_of(self, slot):
        ab = self.data["abilities"][slot]
        cd = ab["cooldown"][max(0, self.ranks[slot] - 1)]
        return cd * 100.0 / (100.0 + self.stats["ability_haste"])

    def max_rank(self, slot):
        if slot == "R":
            return sum(1 for lv in (6, 11, 16) if self.level >= lv)
        return min(5, (self.level + 1) // 2)

    def clear_orders(self):
        self.move_target = None
        self.attack_target = None
        self.attack_move = False
        self.windup = None


MINION_TYPES = {
    #           hp,  ad, 사거리, 공속, 이속, 반경, 골드, 경험치, 원거리
    "melee":  (480, 4.9, 1.2, 1.25, 3.25, 0.45, 21, 60, False),
    "caster": (300, 9.0, 5.0, 0.67, 3.25, 0.40, 14, 30, True),
    "cannon": (920, 15.8, 3.0, 1.00, 3.25, 0.60, 60, 93, True),
    "super":  (1600, 41, 1.7, 0.85, 3.25, 0.75, 40, 97, False),
}
MINION_CODES = {"melee": 0, "caster": 1, "cannon": 2, "super": 3}
TURRET_MINION_DMG = {"melee": 0.45, "caster": 0.70, "cannon": 0.14, "super": 0.07}


class Minion(Unit):
    kind = "minion"

    def __init__(self, uid, team, x, z, mtype, minutes):
        hp, ad, rng, aspd, ms, radius, gold, xp, ranged = MINION_TYPES[mtype]
        super().__init__(uid, team, x, z, radius)
        self.mtype = mtype
        self.max_hp = self.hp = hp * (1 + 0.05 * minutes)
        self.ad = ad * (1 + 0.04 * minutes)
        self.armor = 0.0 if mtype != "super" else 30.0
        self.attack_range = rng
        self.attack_speed = aspd
        self.move_speed = ms
        self.gold = gold
        self.xp = xp
        self.ranged = ranged
        self.lane_z = z
        self.target = None
        self.retarget_at = 0.0
        self.attack_ready_at = 0.0
        self.windup = None


class Structure(Unit):
    kind = "structure"

    def __init__(self, uid, info):
        super().__init__(uid, info["team"], info["x"], info["z"], info["radius"])
        self.key = info["key"]
        self.skind = info["kind"]     # turret / inhibitor / nexus
        self.requires = info["requires"]
        self.max_hp = self.hp = float(info["hp"])
        self.armor = 40.0
        self.mr = 40.0
        self.respawn_at = None
        self.target = None
        self.attack_ready_at = 0.0
        self.ramp = 0
        # 포탑 방패: 체력을 plates 칸으로 나눠 한 칸 깎일 때마다 골드
        self.plates = TURRET_PLATES if self.skind == "turret" else 0
        self.plates_left = self.plates
        self.plate_gold = PLATE_GOLD.get(self.key, 0)


class Projectile:
    def __init__(self, pid, team, owner, x, z, style, speed):
        self.id = pid
        self.team = team
        self.owner = owner            # 발사한 유닛 (없을 수 있음)
        self.x = x
        self.z = z
        self.style = style
        self.speed = speed
        self.dead = False
        # 유도형
        self.target = None
        # 직선형
        self.dx = 0.0
        self.dz = 0.0
        self.remaining = 0.0
        self.width = 0.0
        self.on_hit = None            # 콜백 f(sim, target)


class GroundEffect:
    def __init__(self, eid, team, owner, x, z, radius, trigger_at, style, on_trigger):
        self.id = eid
        self.team = team
        self.owner = owner
        self.x = x
        self.z = z
        self.radius = radius
        self.trigger_at = trigger_at
        self.style = style
        self.on_trigger = on_trigger


class Relic:
    def __init__(self, rid, x, z):
        self.id = rid
        self.x = x
        self.z = z
        self.active = False
        self.respawn_at = 0.0
