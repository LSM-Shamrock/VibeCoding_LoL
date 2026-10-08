"""칼바람 모드 게임 시뮬레이션 (서버 권한).

- 단일 라인, 양 팀 외곽/내부 포탑 → 억제기 → 쌍둥이 포탑 → 넥서스
- 레벨 3, 1400 골드로 시작 / B 귀환(8초) / 상점은 사망 중이거나 우물에서만
- 우물에서 체력·마나 회복, 라인에는 체력 회복 유물(구슬)도 생성
- 시야: 팀마다 챔피언·미니언·구조물 주변만 보이고, 부쉬 안은 같은 부쉬 안에서만 보인다
- 포탑 방패: 포탑 체력이 한 칸(1/5) 깎일 때마다 근처 적 챔피언에게 골드
- 30초마다 미니언 웨이브, 억제기 파괴 시 슈퍼 미니언
- 소환사 주문: D 점멸, F 표식(눈덩이)
"""
import math
import random

from ..shared import data as gamedata
from ..shared import mapdata
from ..shared.constants import (
    ASSIST_GOLD_TOTAL, ASSIST_WINDOW, BLUE, FIRST_BLOOD_BONUS, FIRST_WAVE_TIME, FLASH_COOLDOWN,
    FLASH_RANGE, FOUNTAIN_HEAL_PCT, FOUNTAIN_LASER_DPS, FOUNTAIN_LASER_RADIUS, FOUNTAIN_RADIUS, INHIBITOR_RESPAWN,
    INVENTORY_SLOTS, KILL_GOLD, MARK_COOLDOWN, MARK_DASH_SPEED, MARK_RANGE, MARK_RECAST_TIME,
    MARK_SPEED, MAX_LEVEL, PASSIVE_GOLD_PER_SEC, PASSIVE_XP_PER_SEC, PLATE_SHARE_RANGE, RECALL_TIME, RED,
    RELIC_FIRST_SPAWN, RELIC_HEAL_PCT, RELIC_RADIUS, RELIC_RESPAWN, SELL_RATIO, SIGHT, WAVE_INTERVAL, XP_SHARE_RANGE,
    death_timer, xp_to_next,
)
from .bot import BotBrain
from .entities import (
    MINION_CODES, TURRET_MINION_DMG, Champion, GroundEffect, Minion, Projectile, Relic, Structure,
)

MINION_AGGRO = 7.0
TURRET_PERIOD = 0.85
TURRET_CHAMP_DMG = 85.0         # 포탑 → 챔피언 기본 피해 (+분당 2.5, 연속 공격 시 증가)
SLOTS = ("Q", "W", "E", "R")


def point_segment_dist(px, pz, ax, az, bx, bz):
    vx, vz = bx - ax, bz - az
    wx, wz = px - ax, pz - az
    vv = vx * vx + vz * vz
    t = 0.0 if vv <= 1e-9 else max(0.0, min(1.0, (wx * vx + wz * vz) / vv))
    cx, cz = ax + vx * t, az + vz * t
    return math.hypot(px - cx, pz - cz)


def other(team):
    return RED if team == BLUE else BLUE


class Simulation:
    def __init__(self, members):
        """members: [{"key", "name", "team", "bot", "champ"}]"""
        self.time = 0.0
        self._next_id = 1
        self.champions = {}         # id -> Champion
        self.by_key = {}            # member_key -> Champion
        self.minions = {}
        self.structures = {}
        self.projectiles = {}
        self.effects = {}
        self.relics = []
        self.events = []
        self.help_calls = []        # (만료, 가해 챔피언 id, 피해 팀, x, z)
        self.brains = {}
        self.wave_index = 0
        self.next_wave_at = FIRST_WAVE_TIME
        self.first_blood = False
        self.winner = None
        self.score = {BLUE: 0, RED: 0}
        self.rng = random.Random()
        self.visible = {BLUE: set(), RED: set()}    # 팀별로 보이는 적 유닛 id
        self._observers = {BLUE: [], RED: []}
        self.gone_minions = []      # 지난 스냅샷 이후 죽은 미니언 (클라이언트 사라짐 효과용)

        for info in mapdata.structure_layout():
            s = Structure(self.new_id(), info)
            self.structures[s.id] = s

        for i, (x, z) in enumerate(mapdata.RELIC_POSITIONS):
            r = Relic(self.new_id(), x, z)
            r.respawn_at = RELIC_FIRST_SPAWN
            self.relics.append(r)

        for team in (BLUE, RED):
            ms = [m for m in members if m["team"] == team]
            pts = mapdata.spawn_points(team, len(ms))
            for m, (x, z) in zip(ms, pts):
                c = Champion(self.new_id(), team, x, z, m["key"], m["name"], m["champ"], m["bot"])
                c.facing = 0.0 if team == BLUE else math.pi
                self.champions[c.id] = c
                self.by_key[m["key"]] = c
                if m["bot"]:
                    self.brains[c.id] = BotBrain(c)

    # ------------------------------------------------------------------ 유틸
    def new_id(self):
        self._next_id += 1
        return self._next_id

    def event(self, **kw):
        self.events.append(kw)

    def unit(self, uid):
        return (self.champions.get(uid) or self.minions.get(uid) or self.structures.get(uid))

    def structure_by_key(self, team, key):
        for s in self.structures.values():
            if s.team == team and s.key == key:
                return s
        return None

    def vulnerable(self, s):
        if not s.alive:
            return False
        for key in s.requires:
            req = self.structure_by_key(s.team, key)
            if req is not None and req.alive:
                return False
        return True

    def targetable(self, u, by_team):
        """by_team 팀이 u 를 공격 대상으로 삼을 수 있는가."""
        if u is None or u.team == by_team or not u.alive:
            return False
        if isinstance(u, Champion):
            return not u.dead
        if isinstance(u, Structure):
            return self.vulnerable(u)
        return True

    def enemies_in_radius(self, team, x, z, radius, champions=True, minions=True):
        out = []
        if champions:
            for c in self.champions.values():
                if c.team != team and not c.dead and math.hypot(c.x - x, c.z - z) <= radius + c.radius:
                    out.append(c)
        if minions:
            for m in self.minions.values():
                if m.team != team and math.hypot(m.x - x, m.z - z) <= radius + m.radius:
                    out.append(m)
        return out

    # ------------------------------------------------------------------ 시야
    def observers(self, team):
        """team 의 시야 제공자 목록: (x, z, 시야 반경, 서 있는 부쉬 번호)."""
        fx, fz = mapdata.fountain_pos(team)
        out = [(fx, fz, SIGHT["fountain"], -1)]
        for c in self.champions.values():
            if c.team == team and not c.dead:
                out.append((c.x, c.z, SIGHT["champion"], mapdata.bush_at(c.x, c.z)))
        for m in self.minions.values():
            if m.team == team:
                out.append((m.x, m.z, SIGHT["minion"], mapdata.bush_at(m.x, m.z)))
        for st in self.structures.values():
            if st.team == team and st.alive:
                out.append((st.x, st.z, SIGHT[st.skind], -1))
        return out

    @staticmethod
    def seen_by(obs, x, z):
        """(x, z) 가 시야 제공자들 중 하나에게 보이는가. 부쉬 안은 같은 부쉬에 있어야 보인다."""
        bush = mapdata.bush_at(x, z)
        for ox, oz, r, ob in obs:
            if (x - ox) ** 2 + (z - oz) ** 2 <= r * r and (bush < 0 or bush == ob):
                return True
        return False

    def update_vision(self):
        for team in (BLUE, RED):
            obs = self.observers(team)
            vis = set()
            for c in self.champions.values():
                if c.team != team and not c.dead and self.seen_by(obs, c.x, c.z):
                    vis.add(c.id)
            for m in self.minions.values():
                if m.team != team and self.seen_by(obs, m.x, m.z):
                    vis.add(m.id)
            self.visible[team] = vis
            self._observers[team] = obs

    def can_see(self, team, u):
        """team 이 유닛 u 를 볼 수 있는가 (아군과 구조물은 항상 보임)."""
        return u.team == team or isinstance(u, Structure) or u.id in self.visible[team]

    def in_fountain(self, c):
        fx, fz = mapdata.fountain_pos(c.team)
        return math.hypot(c.x - fx, c.z - fz) <= FOUNTAIN_RADIUS

    def can_shop(self, c):
        return c.dead or self.in_fountain(c)

    # ------------------------------------------------------------------ 이동
    def obstacles(self):
        # 부서진 구조물(잔해)도 살아 있을 때와 같은 크기로 길을 막는다
        return list(self.structures.values())

    def move_unit(self, u, tx, tz, speed, dt, stop_dist=0.0):
        """u 를 (tx, tz) 쪽으로 이동. 도착하면 True."""
        dx, dz = tx - u.x, tz - u.z
        d = math.hypot(dx, dz)
        if d <= stop_dist + 1e-3:
            return True
        step = min(speed * dt, d - stop_dist)
        ux, uz = dx / d, dz / d
        # 앞에 구조물이 있으면 옆으로 비켜간다
        for s in self.obstacles():
            ox, oz = s.x - u.x, s.z - u.z
            along = ox * ux + oz * uz
            if 0.0 < along < s.radius + 3.0 and along < d:
                perp = -ox * uz + oz * ux
                clear = s.radius + u.radius + 0.25
                if abs(perp) < clear:
                    side = -1.0 if perp > 0 else 1.0
                    if abs(perp) < 1e-3:
                        side = 1.0 if (u.z >= 0) else -1.0
                    k = (clear - abs(perp)) / clear * 2.0
                    nx_, nz_ = -uz * side, ux * side
                    ux, uz = ux + nx_ * k, uz + nz_ * k
                    n = math.hypot(ux, uz) or 1.0
                    ux, uz = ux / n, uz / n
        nx, nz = u.x + ux * step, u.z + uz * step
        u.x, u.z = self.resolve_position(nx, nz, u.radius)
        u.facing = math.atan2(uz, ux)
        return False

    def resolve_position(self, x, z, radius):
        x, z = mapdata.clamp_to_map(x, z, radius)
        for s in self.obstacles():
            dx, dz = x - s.x, z - s.z
            d = math.hypot(dx, dz)
            min_d = s.radius + radius
            if d < min_d:
                if d < 1e-4:
                    dx, dz, d = 0.0, 1.0, 1.0
                x, z = s.x + dx / d * min_d, s.z + dz / d * min_d
        return mapdata.clamp_to_map(x, z, radius)

    def face(self, u, x, z):
        if abs(x - u.x) + abs(z - u.z) > 1e-4:
            u.facing = math.atan2(z - u.z, x - u.x)

    # ------------------------------------------------------------------ 피해
    def deal_damage(self, src, target, amount, dtype, ability=False, basic=False):
        if target is None or not target.alive or amount <= 0:
            return 0.0
        if isinstance(target, Champion) and target.dead:
            return 0.0
        if isinstance(target, Structure):
            if ability or not self.vulnerable(target):
                return 0.0
        if dtype == "physical":
            res = target.armor
        elif dtype == "magic":
            res = target.mr
        else:
            res = None
        if res is None:
            dmg = amount
        elif res >= 0:
            dmg = amount * 100.0 / (100.0 + res)
        else:
            dmg = amount * (2.0 - 100.0 / (100.0 - res))
        target.hp -= dmg
        if isinstance(target, Champion) and dmg > 0:
            target.recall_at = None         # 피해를 받으면 귀환 취소
            target.last_hit_at = self.time
        if isinstance(target, Structure):
            while target.plates_left > 0 and target.hp <= target.max_hp * (target.plates_left - 1) / target.plates:
                self.break_plate(target)

        src_id = src.id if src is not None else 0
        self.event(e="dmg", s=src_id, d=target.id, v=int(round(dmg)), ty=dtype[0])

        if isinstance(src, Champion):
            if isinstance(target, Champion):
                target.damage_log[src.id] = self.time
                self.help_calls.append((self.time + 2.0, src.id, target.team, target.x, target.z))
            if basic and src.stats.get("life_steal", 0) > 0 and not src.dead:
                src.hp = min(src.max_hp, src.hp + dmg * src.stats["life_steal"])

        if target.hp <= 0:
            target.hp = 0
            self.on_death(target, src)
        return dmg

    def break_plate(self, s):
        """포탑 방패 한 칸 파괴: 근처 적 챔피언들이 골드를 나눠 갖는다."""
        s.plates_left -= 1
        near = [c for c in self.champions.values()
                if c.team != s.team and not c.dead and c.dist_to(s) <= PLATE_SHARE_RANGE]
        if near and s.plate_gold:
            share = s.plate_gold / len(near)
            for c in near:
                c.gold += share
                self.event(e="gold", d=c.id, v=int(round(share)), x=round(s.x, 2), z=round(s.z, 2))
        self.event(e="fx", fx="plate", x=round(s.x, 2), z=round(s.z, 2))

    def heal(self, c, amount):
        c.hp = min(c.max_hp, c.hp + amount)

    # ------------------------------------------------------------------ 처치
    def on_death(self, target, killer):
        if isinstance(target, Champion):
            self.champion_died(target, killer)
        elif isinstance(target, Minion):
            target.alive = False
            self.minions.pop(target.id, None)
            self.gone_minions.append(target.id)
            if isinstance(killer, Champion):
                killer.gold += target.gold
                killer.cs += 1
                self.event(e="gold", d=killer.id, v=target.gold, x=round(target.x, 2), z=round(target.z, 2))
            near = [c for c in self.champions.values()
                    if c.team != target.team and not c.dead and c.dist_to(target) <= XP_SHARE_RANGE]
            for c in near:
                self.give_xp(c, target.xp / len(near))
        elif isinstance(target, Structure):
            self.structure_destroyed(target, killer)

    def champion_died(self, victim, killer):
        victim.dead = True
        victim.recall_at = None
        victim.deaths += 1
        victim.respawn_at = self.time + death_timer(victim.level)
        victim.clear_orders()
        victim.dash = None
        victim.buffs = []
        victim.empower = None
        victim.slows = []
        victim.stun_until = victim.root_until = 0.0

        recent = {cid: t for cid, t in victim.damage_log.items() if self.time - t <= ASSIST_WINDOW}
        victim.damage_log = {}
        killer_champ = killer if isinstance(killer, Champion) else None
        if killer_champ is None and recent:
            # 포탑·미니언에게 처치되면 마지막으로 피해를 준 챔피언이 처치 관여
            killer_champ = self.champions.get(max(recent, key=recent.get))
        if killer_champ is not None and killer_champ.team == victim.team:
            killer_champ = None

        assists = [self.champions[cid] for cid in recent
                   if killer_champ is None or cid != killer_champ.id]
        assists = [a for a in assists if a.team != victim.team]

        if killer_champ is not None:
            killer_champ.kills += 1
            gold = KILL_GOLD
            if not self.first_blood:
                self.first_blood = True
                gold += FIRST_BLOOD_BONUS
                self.event(e="announce", text=f"{killer_champ.name} 님이 선취점을 올렸습니다!")
            killer_champ.gold += gold
            self.score[killer_champ.team] += 1
        else:
            self.score[other(victim.team)] += 1
        for a in assists:
            a.assists += 1
            a.gold += ASSIST_GOLD_TOTAL / len(assists)

        xp_total = 100 + 35 * victim.level
        gainers = ([killer_champ] if killer_champ else []) + assists
        for g in gainers:
            self.give_xp(g, xp_total / len(gainers))

        self.event(e="kill", k=killer_champ.id if killer_champ else (killer.id if killer else 0),
                   kn=killer_champ.name if killer_champ else ("포탑" if isinstance(killer, Structure) else "미니언"),
                   kt=other(victim.team), v=victim.id, vn=victim.name, vt=victim.team)

    def structure_destroyed(self, s, killer):
        s.alive = False
        s.hp = 0
        names = {"turret": "포탑", "inhibitor": "억제기", "nexus": "넥서스"}
        enemy = other(s.team)
        if s.skind == "turret":
            for c in self.champions.values():
                if c.team == enemy:
                    c.gold += 150
        elif s.skind == "inhibitor":
            s.respawn_at = self.time + INHIBITOR_RESPAWN
            for c in self.champions.values():
                if c.team == enemy:
                    c.gold += 50
        self.event(e="announce", text=f"{'블루' if s.team == BLUE else '레드'}팀 {names[s.skind]}이(가) 파괴되었습니다!")
        if s.skind == "nexus":
            self.winner = enemy
            self.event(e="victory", team=enemy)

    def give_xp(self, c, amount):
        if c.level >= MAX_LEVEL:
            return
        c.xp += amount
        while c.level < MAX_LEVEL and c.xp >= xp_to_next(c.level):
            c.xp -= xp_to_next(c.level)
            c.level += 1
            c.skill_points += 1
            c.recompute_stats(self.time)
            self.event(e="levelup", d=c.id, lv=c.level)
        if c.level >= MAX_LEVEL:
            c.xp = 0

    # ------------------------------------------------------------------ 명령
    def handle_command(self, key, msg):
        c = self.by_key.get(key)
        if c is None or self.winner is not None:
            return
        cmd = msg.get("c")
        try:
            if cmd == "level":
                self.level_ability(c, msg["slot"])
            elif cmd == "buy":
                self.buy(c, msg["item"])
            elif cmd == "sell":
                self.sell(c, int(msg["slot"]))
            elif c.dead:
                return
            elif cmd == "recall":
                self.recall(c)
            elif cmd == "move":
                c.recall_at = None
                self.cmd_move(c, float(msg["x"]), float(msg["z"]))
            elif cmd == "amove":
                c.recall_at = None
                self.cmd_move(c, float(msg["x"]), float(msg["z"]))
                c.attack_move = True
            elif cmd == "attack":
                c.recall_at = None
                self.cmd_attack(c, int(msg["id"]))
            elif cmd == "stop":
                c.recall_at = None
                c.clear_orders()
            elif cmd == "cast":
                self.cast(c, msg["slot"], float(msg["x"]), float(msg["z"]))
            elif cmd == "spell":
                if msg["slot"] == "D":
                    self.flash(c, float(msg["x"]), float(msg["z"]))
                elif msg["slot"] == "F":
                    self.mark(c, float(msg["x"]), float(msg["z"]))
        except (KeyError, TypeError, ValueError):
            pass

    def cmd_move(self, c, x, z):
        if c.dash:
            return
        c.windup = None
        c.attack_target = None
        c.attack_move = False
        c.move_target = mapdata.clamp_to_map(x, z, c.radius)

    def cmd_attack(self, c, uid):
        if c.dash:
            return
        target = self.unit(uid)
        if not self.targetable(target, c.team) or not self.can_see(c.team, target):
            return
        if c.attack_target != uid:
            c.windup = None
        c.attack_target = uid
        c.move_target = None
        c.attack_move = False

    def recall(self, c):
        """귀환 시작: RECALL_TIME 동안 가만히 있으면 우물로 이동 (이동·공격·스킬·피해·기절 시 취소)."""
        if c.dead or c.dash or c.recall_at is not None or c.stunned(self.time):
            return
        c.clear_orders()
        c.recall_at = self.time + RECALL_TIME

    def level_ability(self, c, slot):
        if slot not in SLOTS or c.skill_points <= 0:
            return
        if c.ranks[slot] >= c.max_rank(slot):
            return
        c.ranks[slot] += 1
        c.skill_points -= 1

    def buy(self, c, iid):
        item = gamedata.items().get(iid)
        if item is None or not self.can_shop(c):
            return
        if len(c.items) >= INVENTORY_SLOTS or c.gold < item["cost"]:
            return
        c.gold -= item["cost"]
        c.items.append(iid)
        c.recompute_stats(self.time)

    def sell(self, c, slot):
        if not self.can_shop(c) or not (0 <= slot < len(c.items)):
            return
        iid = c.items.pop(slot)
        c.gold += gamedata.items()[iid]["cost"] * SELL_RATIO
        c.recompute_stats(self.time)

    # ------------------------------------------------------------------ 스킬
    def ability_damage(self, c, ab, rank):
        base = ab.get("damage", [0])[rank - 1]
        return (base + ab.get("ad_ratio", 0) * c.stats["ad"] + ab.get("bonus_ad_ratio", 0) * c.stats["bonus_ad"]
                + ab.get("ap_ratio", 0) * c.stats["ap"])

    def cast(self, c, slot, x, z):
        if slot not in SLOTS or c.dead or c.stunned(self.time) or c.dash:
            return
        rank = c.ranks[slot]
        if rank <= 0 or self.time < c.ready_at[slot]:
            return
        ab = c.data["abilities"][slot]
        cost = ab.get("mana", [0])[rank - 1]
        if c.mana < cost:
            return
        dx, dz = x - c.x, z - c.z
        d = math.hypot(dx, dz)
        if d < 1e-3:
            dx, dz, d = math.cos(c.facing), math.sin(c.facing), 1.0
        ux, uz = dx / d, dz / d
        typ = ab["type"]

        if typ == "skillshot":
            p = Projectile(self.new_id(), c.team, c, c.x + ux * 0.6, c.z + uz * 0.6, ab.get("style", "bolt"), ab["speed"])
            p.dx, p.dz = ux, uz
            p.remaining = ab["range"]
            p.width = ab["width"]
            dmg = self.ability_damage(c, ab, rank)
            dtype = ab.get("damage_type", "physical")

            def on_hit(sim, target, c=c, dmg=dmg, dtype=dtype, ab=ab):
                sim.deal_damage(c, target, dmg, dtype, ability=True)
                if ab.get("slow"):
                    target.apply_slow(sim.time, ab["slow"], ab.get("slow_duration", 1.0))
                if ab.get("stun"):
                    target.apply_stun(sim.time, ab["stun"])
            p.on_hit = on_hit
            self.projectiles[p.id] = p
        elif typ == "self_buff":
            c.buffs.append({
                "until": self.time + ab["duration"],
                "attack_speed_pct": ab.get("attack_speed_pct", [0] * 5)[rank - 1],
                "move_speed_pct": ab.get("move_speed_pct", [0] * 5)[rank - 1],
            })
            c.recompute_stats(self.time)
        elif typ == "dash":
            if c.rooted(self.time):
                return
            dist = min(d, ab["range"])
            tx, tz = self.resolve_position(c.x + ux * dist, c.z + uz * dist, c.radius)
            emp = None
            if ab.get("empower_magic"):
                emp = {"magic": ab["empower_magic"][rank - 1] + ab.get("empower_ap_ratio", 0) * c.stats["ap"],
                       "duration": ab.get("empower_duration", 3.0)}
            c.clear_orders()
            c.dash = {"x": tx, "z": tz, "speed": ab["speed"], "follow": None, "empower": emp}
        elif typ == "ground_aoe":
            dist = min(d, ab["range"])
            gx, gz = c.x + ux * dist, c.z + uz * dist
            dmg = self.ability_damage(c, ab, rank)
            dtype = ab.get("damage_type", "magic")

            def on_trigger(sim, eff, c=c, dmg=dmg, dtype=dtype, ab=ab):
                for t in sim.enemies_in_radius(eff.team, eff.x, eff.z, eff.radius):
                    sim.deal_damage(c, t, dmg, dtype, ability=True)
                    if ab.get("stun"):
                        t.apply_stun(sim.time, ab["stun"])
                    if ab.get("slow"):
                        t.apply_slow(sim.time, ab["slow"], ab.get("slow_duration", 1.0))
                sim.event(e="fx", fx=eff.style + "_burst", x=round(eff.x, 2), z=round(eff.z, 2), r=eff.radius)
            eff = GroundEffect(self.new_id(), c.team, c, gx, gz, ab["radius"], self.time + ab.get("delay", 0.5),
                               ab.get("style", "aoe"), on_trigger)
            self.effects[eff.id] = eff
        else:
            return

        c.mana -= cost
        c.recall_at = None
        c.ready_at[slot] = self.time + c.cooldown_of(slot)
        c.windup = None
        c.cast_anim_until = self.time + 0.3
        self.face(c, x, z)
        self.event(e="cast", d=c.id, slot=slot)

    def flash(self, c, x, z):
        if self.time < c.ready_at["D"] or c.stunned(self.time):
            return
        dx, dz = x - c.x, z - c.z
        d = math.hypot(dx, dz)
        if d < 1e-3:
            dx, dz, d = math.cos(c.facing), math.sin(c.facing), 1.0
        dist = min(d, FLASH_RANGE)
        ox, oz = c.x, c.z
        c.x, c.z = self.resolve_position(c.x + dx / d * dist, c.z + dz / d * dist, c.radius)
        c.dash = None
        c.windup = None
        c.recall_at = None
        c.ready_at["D"] = self.time + FLASH_COOLDOWN
        self.face(c, x, z)
        self.event(e="fx", fx="flash", x=round(ox, 2), z=round(oz, 2), x2=round(c.x, 2), z2=round(c.z, 2))

    def mark(self, c, x, z):
        # 표식 재사용: 맞힌 대상에게 돌진
        if c.mark and self.time <= c.mark[1]:
            target = self.unit(c.mark[0])
            c.mark = None
            if self.targetable(target, c.team) and not c.rooted(self.time):
                c.clear_orders()
                c.recall_at = None
                c.dash = {"x": target.x, "z": target.z, "speed": MARK_DASH_SPEED, "follow": target.id, "empower": None}
            return
        if self.time < c.ready_at["F"] or c.stunned(self.time):
            return
        dx, dz = x - c.x, z - c.z
        d = math.hypot(dx, dz)
        if d < 1e-3:
            dx, dz, d = math.cos(c.facing), math.sin(c.facing), 1.0
        p = Projectile(self.new_id(), c.team, c, c.x, c.z, "snowball", MARK_SPEED)
        p.dx, p.dz = dx / d, dz / d
        p.remaining = MARK_RANGE
        p.width = 0.7

        def on_hit(sim, target, c=c):
            sim.deal_damage(c, target, 10 + 5 * c.level, "true", ability=True)
            c.mark = (target.id, sim.time + MARK_RECAST_TIME)
        p.on_hit = on_hit
        self.projectiles[p.id] = p
        c.recall_at = None
        c.ready_at["F"] = self.time + MARK_COOLDOWN
        self.face(c, x, z)

    # ------------------------------------------------------------------ 기본 공격
    def basic_attack_payload(self, c, target):
        dmg = c.stats["ad"]
        crit = self.rng.random() < c.stats["crit"]
        if crit:
            dmg *= 1.75
        self.deal_damage(c, target, dmg, "physical", basic=True)
        if not target.alive or (isinstance(target, Champion) and target.dead):
            return
        c.attack_count += 1
        passive = c.data.get("passive", {})
        if passive.get("type") == "every_nth_attack" and c.attack_count % passive.get("n", 3) == 0:
            bonus = (passive.get("bonus_magic_base", 0) + passive.get("bonus_magic_per_level", 0) * c.level
                     + passive.get("ap_ratio", 0) * c.stats["ap"])
            self.deal_damage(c, target, bonus, "magic")
            if passive.get("slow") and not isinstance(target, Structure):
                target.apply_slow(self.time, passive["slow"], passive.get("slow_duration", 1.0))
        if c.empower and self.time <= c.empower["until"]:
            self.deal_damage(c, target, c.empower["magic"], "magic")
            c.empower = None

    def release_attack(self, attacker, target, damage_fn, style, speed, ranged):
        if ranged:
            p = Projectile(self.new_id(), attacker.team, attacker, attacker.x, attacker.z, style, speed)
            p.target = target.id
            p.on_hit = damage_fn
            self.projectiles[p.id] = p
        else:
            damage_fn(self, target)

    # ------------------------------------------------------------------ 갱신
    def update(self, dt):
        if self.winner is not None:
            return
        self.time += dt
        t = self.time
        self.help_calls = [h for h in self.help_calls if h[0] > t]

        if t >= self.next_wave_at:
            self.spawn_wave()
            self.wave_index += 1
            self.next_wave_at += WAVE_INTERVAL

        for brain in self.brains.values():
            brain.update(self, dt)

        for c in self.champions.values():
            self.update_champion(c, dt)
        for m in list(self.minions.values()):
            if m.alive:
                self.update_minion(m, dt)
        self.separate_minions()
        for s in self.structures.values():
            self.update_structure(s, dt)
        self.update_projectiles(dt)
        for e in list(self.effects.values()):
            if t >= e.trigger_at:
                del self.effects[e.id]
                e.on_trigger(self, e)
        self.update_relics()
        self.update_vision()

    def update_champion(self, c, dt):
        t = self.time
        if c.dead:
            if t >= c.respawn_at:
                c.dead = False
                c.recompute_stats(t)
                c.hp, c.mana = c.max_hp, c.max_mana
                pts = mapdata.spawn_points(c.team, 5)
                c.x, c.z = pts[c.id % 5]
                c.clear_orders()
                self.event(e="respawn", d=c.id)
            return

        c.gold += PASSIVE_GOLD_PER_SEC * dt
        self.give_xp(c, PASSIVE_XP_PER_SEC * dt)
        c.recompute_stats(t)
        c.hp = min(c.max_hp, c.hp + c.stats["hp_regen"] / 5.0 * dt)
        c.mana = min(c.max_mana, c.mana + c.stats["mana_regen"] / 5.0 * dt)
        if c.empower and t > c.empower["until"]:
            c.empower = None
        if c.mark and t > c.mark[1]:
            c.mark = None
        if self.in_fountain(c):
            self.heal(c, c.max_hp * FOUNTAIN_HEAL_PCT * dt)
            c.mana = min(c.max_mana, c.mana + c.max_mana * FOUNTAIN_HEAL_PCT * dt)

        # 귀환
        if c.recall_at is not None:
            if c.stunned(t):
                c.recall_at = None
            elif t >= c.recall_at:
                c.recall_at = None
                ox, oz = c.x, c.z
                c.x, c.z = mapdata.spawn_points(c.team, 5)[c.id % 5]
                c.clear_orders()
                self.event(e="fx", fx="recall", x=round(ox, 2), z=round(oz, 2), x2=round(c.x, 2), z2=round(c.z, 2))

        # 적 우물 레이저
        efx, efz = mapdata.fountain_pos(other(c.team))
        if math.hypot(c.x - efx, c.z - efz) < FOUNTAIN_LASER_RADIUS:
            self.deal_damage(None, c, FOUNTAIN_LASER_DPS * dt, "true")
            if c.dead:
                return

        c.anim = 0
        if c.dash:
            self.update_dash(c, dt)
            c.anim = 1
            return
        if c.stunned(t):
            c.windup = None
            return
        if t < c.cast_anim_until:
            c.anim = 3

        # 공격 준비 동작
        if c.windup:
            fire_at, tid = c.windup
            target = self.unit(tid)
            if not self.targetable(target, c.team):
                c.windup = None
            elif t >= fire_at:
                c.windup = None
                self.release_attack(c, target, lambda sim, tg, c=c: sim.basic_attack_payload(c, tg),
                                    "arrow", c.data["stats"].get("projectile_speed", 20), c.data["stats"].get("ranged", True))
            else:
                c.anim = 2
                return

        target = self.unit(c.attack_target) if c.attack_target else None
        if c.attack_target and (not self.targetable(target, c.team) or not self.can_see(c.team, target)):
            c.attack_target = None
            target = None

        if target is None and c.attack_move:
            target = self.nearest_enemy_for_champion(c, c.stats["attack_range"] + 2.0)
            if target:
                c.attack_target = target.id
            elif c.move_target:
                if self.move_unit(c, c.move_target[0], c.move_target[1], c.stats["move_speed"], dt) or c.rooted(t):
                    pass
                c.anim = 1
                if c.dist_xy(*c.move_target) < 0.1:
                    c.clear_orders()
                return

        if target is not None:
            reach = c.stats["attack_range"] + c.radius + target.radius
            if c.dist_to(target) <= reach:
                self.face(c, target.x, target.z)
                if t >= c.attack_ready_at:
                    period = 1.0 / c.stats["attack_speed"]
                    c.attack_ready_at = t + period
                    c.windup = (t + max(0.08, period * 0.22), target.id)
                    c.anim = 2
                    if isinstance(target, Champion):
                        self.help_calls.append((t + 2.0, c.id, target.team, target.x, target.z))
            elif not c.rooted(t):
                self.move_unit(c, target.x, target.z, c.stats["move_speed"], dt, stop_dist=reach * 0.95)
                c.anim = 1
            return

        if c.move_target and not c.rooted(t):
            if self.move_unit(c, c.move_target[0], c.move_target[1], c.stats["move_speed"], dt):
                c.move_target = None
            else:
                c.anim = 1

    def update_dash(self, c, dt):
        d = c.dash
        if d["follow"]:
            tg = self.unit(d["follow"])
            if not self.targetable(tg, c.team):
                c.dash = None
                return
            d["x"], d["z"] = tg.x, tg.z
            stop = c.radius + tg.radius
        else:
            stop = 0.0
        dx, dz = d["x"] - c.x, d["z"] - c.z
        dist = math.hypot(dx, dz)
        step = d["speed"] * dt
        if dist - stop <= step:
            if dist > 1e-4:
                k = max(0.0, dist - stop) / dist
                c.x, c.z = self.resolve_position(c.x + dx * k, c.z + dz * k, c.radius)
            if d.get("empower"):
                c.empower = {"magic": d["empower"]["magic"], "until": self.time + d["empower"]["duration"]}
            if d["follow"]:
                c.attack_target = d["follow"]
            c.dash = None
            return
        c.facing = math.atan2(dz, dx)
        c.x, c.z = self.resolve_position(c.x + dx / dist * step, c.z + dz / dist * step, c.radius)

    def nearest_enemy_for_champion(self, c, radius):
        best, best_d = None, radius
        for u in list(self.champions.values()) + list(self.minions.values()) + list(self.structures.values()):
            if not self.targetable(u, c.team) or not self.can_see(c.team, u):
                continue
            d = c.dist_to(u) - u.radius
            if d < best_d:
                best, best_d = u, d
        return best

    # ------------------------------------------------------------------ 미니언
    def spawn_wave(self):
        minutes = self.time / 60.0
        for team in (BLUE, RED):
            types = ["melee"] * 3
            if self.wave_index % 3 == 2 or (minutes >= 20 and self.wave_index % 2 == 1):
                types.append("cannon")
            enemy_inhib = self.structure_by_key(other(team), "inhib")
            if enemy_inhib is not None and not enemy_inhib.alive:
                types.append("super")
            types += ["caster"] * 3
            sx, sz = mapdata.minion_spawn(team)
            direction = mapdata.team_dir(team)
            for i, mt in enumerate(types):
                row = i // 3
                col = (i % 3) - 1
                x = sx - direction * row * 1.3
                z = sz + col * 1.4
                m = Minion(self.new_id(), team, x, z, mt, minutes)
                m.facing = 0.0 if team == BLUE else math.pi
                self.minions[m.id] = m

    def minion_pick_target(self, m):
        t = self.time
        # 아군 챔피언을 공격한 적 챔피언 (도움 요청)
        for exp, aid, hteam, hx, hz in self.help_calls:
            if hteam == m.team and math.hypot(hx - m.x, hz - m.z) <= MINION_AGGRO:
                a = self.champions.get(aid)
                if self.targetable(a, m.team) and m.dist_to(a) <= MINION_AGGRO and self.can_see(m.team, a):
                    return a
        best, best_d = None, MINION_AGGRO
        for e in self.minions.values():
            if e.team != m.team and self.can_see(m.team, e):
                d = m.dist_to(e)
                if d < best_d:
                    best, best_d = e, d
        if best:
            return best
        for s in self.structures.values():
            if self.targetable(s, m.team):
                d = m.dist_to(s) - s.radius
                if d < best_d:
                    best, best_d = s, d
        if best:
            return best
        for c in self.champions.values():
            if self.targetable(c, m.team) and self.can_see(m.team, c):
                d = m.dist_to(c)
                if d < best_d:
                    best, best_d = c, d
        _ = t
        return best

    def update_minion(self, m, dt):
        t = self.time
        m.anim = 0
        if m.stunned(t):
            m.windup = None
            return
        if m.windup:
            fire_at, tid = m.windup
            target = self.unit(tid)
            if not self.targetable(target, m.team) or not self.can_see(m.team, target):
                m.windup = None
            elif t >= fire_at:
                m.windup = None
                dmg = m.ad
                style = "cannon_ball" if m.mtype == "cannon" else "minion_bolt"
                self.release_attack(m, target, lambda sim, tg, m=m, dmg=dmg: sim.deal_damage(m, tg, dmg, "physical"),
                                    style, 14.0, m.ranged)
            else:
                m.anim = 2
                return

        target = self.unit(m.target) if m.target else None
        if target is not None and not self.can_see(m.team, target):
            target = None                   # 시야에서 사라지면(부쉬 등) 놓친다
        if target is None or not self.targetable(target, m.team) or t >= m.retarget_at:
            # 이미 교전 중인 대상이 사거리 안에 있으면 유지
            keep = (self.targetable(target, m.team)
                    and m.dist_to(target) <= m.attack_range + m.radius + target.radius + 0.3
                    and not isinstance(target, Champion))
            if not keep:
                target = self.minion_pick_target(m)
                m.target = target.id if target else None
            m.retarget_at = t + 0.4

        if target is not None:
            reach = m.attack_range + m.radius + target.radius
            if m.dist_to(target) <= reach:
                self.face(m, target.x, target.z)
                if t >= m.attack_ready_at:
                    period = 1.0 / m.attack_speed
                    m.attack_ready_at = t + period
                    m.windup = (t + period * 0.3, target.id)
                    m.anim = 2
            elif not m.rooted(t):
                self.move_unit(m, target.x, target.z, m.move_speed * (1 - m.slow_amount(t)), dt, stop_dist=reach * 0.9)
                m.anim = 1
            return

        if not m.rooted(t):
            ex = -mapdata.fountain_pos(m.team)[0] * 0.85
            self.move_unit(m, ex, m.lane_z * 0.5, m.move_speed * (1 - m.slow_amount(t)), dt)
            m.anim = 1

    def separate_minions(self):
        ms = list(self.minions.values())
        n = len(ms)
        for i in range(n):
            a = ms[i]
            for j in range(i + 1, n):
                b = ms[j]
                dx, dz = b.x - a.x, b.z - a.z
                min_d = (a.radius + b.radius) * 0.9
                if abs(dx) > min_d or abs(dz) > min_d:
                    continue
                d = math.hypot(dx, dz)
                if d < min_d:
                    if d < 1e-4:
                        dx, dz, d = self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), 1.0
                        d = math.hypot(dx, dz) or 1.0
                    push = (min_d - d) * 0.5
                    ux, uz = dx / d, dz / d
                    a.x, a.z = self.resolve_position(a.x - ux * push, a.z - uz * push, a.radius)
                    b.x, b.z = self.resolve_position(b.x + ux * push, b.z + uz * push, b.radius)

    # ------------------------------------------------------------------ 구조물
    def update_structure(self, s, dt):
        t = self.time
        if not s.alive:
            if s.skind == "inhibitor" and s.respawn_at is not None and t >= s.respawn_at:
                s.alive = True
                s.hp = s.max_hp
                s.respawn_at = None
                self.event(e="announce", text=f"{'블루' if s.team == BLUE else '레드'}팀 억제기가 재생성되었습니다.")
            return
        if s.skind != "turret":
            return
        rng = mapdata.TURRET_RANGE

        def in_range(u):
            return u is not None and s.dist_to(u) <= rng + u.radius

        target = self.unit(s.target) if s.target else None
        if not self.targetable(target, s.team) or not in_range(target):
            target = None

        # 아군 챔피언을 공격한 적 챔피언 우선
        if not isinstance(target, Champion):
            for exp, aid, hteam, hx, hz in self.help_calls:
                if hteam == s.team and math.hypot(hx - s.x, hz - s.z) <= rng:
                    a = self.champions.get(aid)
                    if self.targetable(a, s.team) and in_range(a):
                        target = a
                        break
        if target is None:
            best, best_d = None, 1e9
            for m in self.minions.values():
                if m.team != s.team and in_range(m):
                    d = s.dist_to(m)
                    if d < best_d:
                        best, best_d = m, d
            if best is None:
                for c in self.champions.values():
                    if self.targetable(c, s.team) and in_range(c):
                        d = s.dist_to(c)
                        if d < best_d:
                            best, best_d = c, d
            target = best

        new_id = target.id if target else None
        if new_id != s.target:
            s.ramp = 0
        s.target = new_id
        if target is None or t < s.attack_ready_at:
            return
        s.attack_ready_at = t + TURRET_PERIOD
        if isinstance(target, Champion):
            dmg = (TURRET_CHAMP_DMG + 2.5 * min(30.0, t / 60.0)) * (1 + 0.4 * min(s.ramp, 3))
            s.ramp += 1

            def hit(sim, tg, s=s, dmg=dmg):
                sim.deal_damage(s, tg, dmg, "physical")
        else:
            pct = TURRET_MINION_DMG.get(target.mtype, 0.3)

            def hit(sim, tg, s=s, pct=pct):
                sim.deal_damage(s, tg, tg.max_hp * pct, "true")
        self.release_attack(s, target, hit, "turret_shot", 16.0, True)

    # ------------------------------------------------------------------ 투사체
    def update_projectiles(self, dt):
        for p in list(self.projectiles.values()):
            if p.target is not None:
                tg = self.unit(p.target)
                if tg is None or not tg.alive or (isinstance(tg, Champion) and tg.dead):
                    p.dead = True
                else:
                    dx, dz = tg.x - p.x, tg.z - p.z
                    d = math.hypot(dx, dz)
                    step = p.speed * dt
                    if d <= step + tg.radius * 0.5:
                        p.dead = True
                        if p.on_hit:
                            p.on_hit(self, tg)
                    else:
                        p.dx, p.dz = dx / d, dz / d
                        p.x += p.dx * step
                        p.z += p.dz * step
            else:
                step = min(p.speed * dt, p.remaining)
                ox, oz = p.x, p.z
                p.x += p.dx * step
                p.z += p.dz * step
                p.remaining -= step
                hit, hit_along = None, 1e9
                for u in list(self.champions.values()) + list(self.minions.values()):
                    if not self.targetable(u, p.team) or isinstance(u, Structure):
                        continue
                    if point_segment_dist(u.x, u.z, ox, oz, p.x, p.z) <= p.width * 0.5 + u.radius:
                        along = (u.x - ox) * p.dx + (u.z - oz) * p.dz
                        if along < hit_along:
                            hit, hit_along = u, along
                if hit is not None:
                    p.dead = True
                    if p.on_hit:
                        p.on_hit(self, hit)
                    self.event(e="fx", fx=p.style + "_hit", x=round(hit.x, 2), z=round(hit.z, 2))
                elif p.remaining <= 1e-4:
                    p.dead = True
            if p.dead:
                self.projectiles.pop(p.id, None)

    # ------------------------------------------------------------------ 유물
    def update_relics(self):
        t = self.time
        for r in self.relics:
            if not r.active:
                if t >= r.respawn_at:
                    r.active = True
                continue
            for c in self.champions.values():
                if not c.dead and math.hypot(c.x - r.x, c.z - r.z) <= RELIC_RADIUS + c.radius:
                    self.heal(c, c.max_hp * RELIC_HEAL_PCT)
                    c.mana = min(c.max_mana, c.mana + c.max_mana * RELIC_HEAL_PCT)
                    r.active = False
                    r.respawn_at = t + RELIC_RESPAWN
                    self.event(e="fx", fx="relic", x=r.x, z=r.z, d=c.id)
                    break

    # ------------------------------------------------------------------ 직렬화
    def static_info(self):
        return {
            "structures": [{"i": s.id, "k": s.skind, "key": s.key, "tm": s.team, "x": s.x, "z": s.z,
                            "r": s.radius, "mhp": s.max_hp, "pl": s.plates} for s in self.structures.values()],
            "champions": [{"i": c.id, "pk": c.member_key, "n": c.name, "c": c.champ_id, "tm": c.team, "bot": c.is_bot}
                          for c in self.champions.values()],
        }

    def event_visible(self, team, ev):
        """이 이벤트를 team 에게 보내도 되는가 (안 보이는 곳의 정보는 숨긴다)."""
        e = ev.get("e")
        if e in ("dmg", "gold"):
            keys = ("s", "d") if e == "dmg" else ("d",)
            return any((ch := self.champions.get(ev.get(k))) is not None and ch.team == team for k in keys)
        if e in ("cast", "levelup"):
            u = self.champions.get(ev.get("d"))
            return u is not None and self.can_see(team, u)
        if e == "fx" and "x" in ev:
            obs = self._observers[team]
            pts = [(ev["x"], ev["z"])] + ([(ev["x2"], ev["z2"])] if "x2" in ev else [])
            return any(self.seen_by(obs, x, z) for x, z in pts)
        return True

    def champion_row(self, c, t):
        st = []
        if c.stunned(t):
            st.append("stun")
        if c.slow_amount(t) > 0:
            st.append("slow")
        if c.buffs:
            st.append("buff")
        if c.empower:
            st.append("emp")
        return {
            "i": c.id, "x": round(c.x, 2), "z": round(c.z, 2), "f": round(c.facing, 2),
            "hp": round(c.hp), "mhp": round(c.max_hp), "mp": round(c.mana), "mmp": round(c.max_mana),
            "lv": c.level, "xp": round(c.xp), "xpn": xp_to_next(c.level), "g": int(c.gold), "it": c.items,
            "ab": c.ranks, "sp": c.skill_points,
            "cd": {k: round(max(0.0, v - t), 1) for k, v in c.ready_at.items()},
            "mk": bool(c.mark), "dead": c.dead, "rt": round(max(0.0, c.respawn_at - t), 1) if c.dead else 0,
            "rc": round(max(0.0, c.recall_at - t), 1) if c.recall_at is not None else 0,
            "st": st, "a": c.anim, "k": c.kills, "d": c.deaths, "as": c.assists, "cs": c.cs,
            "shop": self.can_shop(c),
            "s": {"ad": round(c.stats["ad"]), "ap": round(c.stats["ap"]), "ar": round(c.stats["armor"]),
                  "mr": round(c.stats["mr"]), "aspd": round(c.stats["attack_speed"], 2),
                  "ms": round(c.stats["move_speed"] * 100), "ah": round(c.stats["ability_haste"]),
                  "cr": round(c.stats["crit"] * 100)},
        }

    def snapshots(self):
        """팀별 스냅샷 {팀: 스냅샷}. 각 팀은 자기 시야에 있는 적만 받는다."""
        t = self.time
        champs = {c.id: self.champion_row(c, t) for c in self.champions.values()}
        # 점수판(Tab)은 시야와 상관없이 모두에게
        board = [[c.id, c.level, c.kills, c.deaths, c.assists, c.cs, int(c.gold), c.items, c.dead,
                  round(max(0.0, c.respawn_at - t)) if c.dead else 0] for c in self.champions.values()]
        structs = [[s.id, round(s.hp), int(s.alive), int(self.vulnerable(s)), s.target or 0]
                   for s in self.structures.values()]
        out = {}
        for team in (BLUE, RED):
            obs = self._observers[team]
            vis = self.visible[team]
            minions = [[m.id, MINION_CODES[m.mtype], m.team, round(m.x, 2), round(m.z, 2), round(m.facing, 2),
                        round(m.hp), round(m.max_hp), m.anim]
                       for m in self.minions.values() if m.team == team or m.id in vis]
            projs = [[p.id, p.style, p.team, round(p.x, 2), round(p.z, 2), round(p.dx, 2), round(p.dz, 2)]
                     for p in self.projectiles.values() if p.team == team or self.seen_by(obs, p.x, p.z)]
            effs = [[e.id, e.style, e.team, round(e.x, 2), round(e.z, 2), e.radius, round(e.trigger_at - t, 2)]
                    for e in self.effects.values() if e.team == team or self.seen_by(obs, e.x, e.z)]
            # 회복 구슬은 시야 안에 있을 때만 있다고 알려준다
            relics = [[r.id, r.x, r.z, int(r.active and self.seen_by(obs, r.x, r.z))] for r in self.relics]
            out[team] = {
                "t": "snap", "time": round(t, 2), "score": [self.score[BLUE], self.score[RED]],
                "ch": [row for cid, row in champs.items() if self.champions[cid].team == team or cid in vis],
                "mn": minions, "st": structs, "pj": projs, "ef": effs, "rl": relics, "sb": board,
                "gone": self.gone_minions,
                "ev": [ev for ev in self.events if self.event_visible(team, ev)],
                "wave": round(max(0.0, self.next_wave_at - t), 1),
            }
        self.events = []
        self.gone_minions = []
        return out
