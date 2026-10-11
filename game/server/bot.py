"""챔피언 봇 AI. 플레이어와 같은 명령 함수(sim.cast, sim.cmd_move 등)를 사용한다.

스킬은 type 별 규칙(plan / plan_support)으로 쓸 시점과 조준 지점을 정한다.
챔피언 data 에 "bot_priority": ["R","E","W","Q"] 를 넣으면 스킬을 검토하는 순서를 바꿀 수 있다.
"""
import math
import random

from ..shared import data as gamedata
from ..shared import mapdata
from ..shared.constants import EXHAUST_RANGE, IGNITE_RANGE, MARK_RANGE

SUPPORT_TYPES = ("ally_heal", "cleanse", "team_heal", "ally_shield", "ally_buff")
POKE_TYPES = ("skillshot", "line_aoe", "cone", "volley")


class BotBrain:
    def __init__(self, champ):
        self.c = champ
        self.rng = random.Random(champ.id * 7919)
        self.think_at = 0.0
        self.reaction = self.rng.uniform(0.18, 0.3)
        self.lane_offset = self.rng.uniform(-3.0, 3.0)

    # ------------------------------------------------------------------
    def update(self, sim, dt):
        c = self.c
        if sim.time < self.think_at:
            return
        self.think_at = sim.time + self.reaction
        self.level_up(sim)
        if sim.can_shop(c):
            self.shop(sim)
        if not c.dead:
            self.use_spells(sim)            # 소환사 주문은 기절 중에도 쓴다 (정화)
        if c.dead or c.dash or c.stunned(sim.time):
            return
        self.decide(sim)

    def use_spells(self, sim):
        """점멸·표식 외의 소환사 주문(회복·유체화·방어막·정화·탈진·점화)을 쓸 때를 정한다."""
        c = self.c
        t = sim.time
        enemies = [e for e in sim.champions.values()
                   if e.team != c.team and not e.dead and c.dist_to(e) <= 9 and sim.can_see(c.team, e)]
        hp = c.hp / max(1.0, c.max_hp)
        hurt = t - c.last_hit_at < 1.5
        for slot, spell in zip(("D", "F"), c.spells):
            if spell in ("flash", "mark") or t < c.ready_at[slot]:
                continue
            aim = None
            if spell == "cleanse":
                fire = bool(enemies) and (c.rooted(t) or c.silenced(t))
            elif spell == "heal":
                fire = hp < 0.4 and (bool(enemies) or hurt)
            elif spell == "barrier":
                fire = hp < 0.5 and (bool(enemies) or hurt)
            elif spell == "ghost":
                weak = [e for e in enemies if e.hp / max(1.0, e.max_hp) < 0.3 and c.dist_to(e) > 4.0]
                fire = bool(enemies) and (hp < 0.3 or bool(weak))
            elif spell == "exhaust":
                near = [e for e in enemies if c.dist_to(e) <= EXHAUST_RANGE - 0.5]
                fire = bool(near) and hp < 0.7
                aim = min(near, key=lambda e: c.dist_to(e)) if near else None
            else:       # ignite
                weak = [e for e in enemies if c.dist_to(e) <= IGNITE_RANGE - 0.5 and e.hp / max(1.0, e.max_hp) < 0.35]
                fire = bool(weak)
                aim = min(weak, key=lambda e: e.hp) if weak else None
            if fire:
                sim.cast_spell(c, slot, aim.x if aim else c.x, aim.z if aim else c.z)

    def level_up(self, sim):
        c = self.c
        for _ in range(c.skill_points):
            order = [s for s in ("Q", "E", "W") if c.ranks[s] == 0] + c.data.get("skill_order", ["R", "Q", "E", "W"])
            for slot in order:
                if c.ranks[slot] < c.max_rank(slot):
                    sim.level_ability(c, slot)
                    break

    def shop(self, sim):
        c = self.c
        for iid in c.data.get("bot_build", []):
            if c.items.count(iid) > 0:
                continue
            item = gamedata.items().get(iid)
            if item is None:
                continue
            used, price = gamedata.buy_plan(c.items, iid)
            if c.gold >= price:
                sim.buy(c, iid)
                continue
            # 모자라면 이 아이템의 재료 중 빠진 것부터 산다 (롤처럼 하위 템 먼저)
            left = list(used)
            for comp in item.get("from", []):
                if comp in left:
                    left.remove(comp)
                    continue
                if c.gold >= gamedata.items()[comp]["cost"]:
                    sim.buy(c, comp)
                break
            break

    # ------------------------------------------------------------------ 판단 보조
    def enemy_turrets(self, sim):
        return [s for s in sim.structures.values() if s.skind == "turret" and s.alive and s.team != self.c.team]

    def turret_threat(self, sim, x, z):
        """(x,z) 가 적 포탑 사거리 안이고 그 포탑이 미니언을 노리고 있지 않으면 위험."""
        for s in self.enemy_turrets(sim):
            if math.hypot(s.x - x, s.z - z) <= mapdata.TURRET_RANGE + 1.0:
                tank = [m for m in sim.minions.values()
                        if m.team == self.c.team and s.dist_to(m) <= mapdata.TURRET_RANGE]
                if len(tank) < 2:
                    return True
                tgt = sim.unit(s.target) if s.target else None
                if tgt is self.c:
                    return True
        return False

    def in_danger(self, sim):
        """귀환하면 안 되는 상황: 최근 피해, 근처에 보이는 적 챔피언/미니언, 적 포탑 사거리."""
        c = self.c
        if sim.time - c.last_hit_at < 3.0:
            return True
        for e in sim.champions.values():
            if e.team != c.team and not e.dead and c.dist_to(e) <= 16 and sim.can_see(c.team, e):
                return True
        for m in sim.minions.values():
            if m.team != c.team and c.dist_to(m) <= 8 and sim.can_see(c.team, m):
                return True
        return any(c.dist_to(s) <= mapdata.TURRET_RANGE + 2 for s in self.enemy_turrets(sim))

    def ab(self, slot):
        return self.c.data["abilities"][slot]

    def ready(self, sim, slot):
        c = self.c
        if c.ranks.get(slot, 0) <= 0 or sim.time < c.ready_at[slot] or c.silenced(sim.time):
            return False
        ab = self.ab(slot)
        return c.mana >= gamedata.rank_value(ab, "mana", c.ranks[slot], 0)

    def aim(self, sim, target, travel_speed=None):
        """대상 위치에 약간의 예측과 오차를 섞어 조준."""
        x, z = target.x, target.z
        if travel_speed and getattr(target, "move_target", None):
            mx, mz = target.move_target
            d = math.hypot(mx - x, mz - z)
            if d > 0.1:
                lead = min(d, self.c.dist_to(target) / travel_speed * 3.0)
                x += (mx - x) / d * lead * 0.7
                z += (mz - z) / d * lead * 0.7
        return x + self.rng.uniform(-0.4, 0.4), z + self.rng.uniform(-0.4, 0.4)

    @staticmethod
    def count_near(enemies, target, radius):
        return sum(1 for e in enemies if e.dist_to(target) <= radius)

    def safe_relic(self, sim, max_dist):
        best, bd = None, max_dist
        for r in sim.relics:
            if not r.active:
                continue
            d = self.c.dist_xy(r.x, r.z)
            if d < bd and not self.turret_threat(sim, r.x, r.z):
                best, bd = r, d
        return best

    @staticmethod
    def needs_cleanse(a, t):
        return a.stunned(t) or t < a.root_until or a.silenced(t)

    # ------------------------------------------------------------------ 스킬 규칙
    def plan(self, sim, slot, target, enemies, allies, hp_ratio):
        """적 챔피언(target)을 상대로 slot 스킬을 쓸 때 조준 지점. 쓰지 않으면 None."""
        c = self.c
        t = sim.time
        ab = self.ab(slot)
        typ = ab["type"]
        ult = slot == "R"
        dist = c.dist_to(target)
        their = target.hp / max(1.0, target.max_hp)
        tx, tz = target.x, target.z
        me = (c.x, c.z)
        clustered = self.count_near(enemies, target, 3.4) >= 2

        if typ == "skillshot":
            rng = min(ab["range"], 13.0)
            if ab.get("pierce") and ult:                    # 멀리서 체력이 낮은 적을 마무리
                return self.aim(sim, target, ab["speed"]) if their < 0.4 else None
            if ult and not (their < 0.55 or clustered):
                return None
            return self.aim(sim, target, ab["speed"]) if dist <= rng * 0.9 else None
        if typ == "hook_dash":
            in_bush = mapdata.bush_at(c.x, c.z) >= 0 or t < c.bush_until
            rng = ab["bush_range"] if in_bush else ab["range"]
            if (dist <= rng * 0.92 and dist > 2.0 and hp_ratio > 0.4
                    and not self.turret_threat(sim, tx, tz) and len(enemies) <= 2):
                return self.aim(sim, target, ab["speed"])
            return None
        if typ == "knife_throw":
            if t < c.q_hit_until or c.rope:
                return (tx, tz) if dist <= ab.get("fast_range", 4.5) - 0.3 else None
            return self.aim(sim, target, ab.get("speed", 11)) if 3.0 < dist <= ab.get("range", 8.0) - 1.0 else None
        if typ == "self_aoe":
            return me if dist <= ab["radius"] * 0.9 else None
        if typ in ("counter_shield", "echo_guard"):
            hit_recently = t - c.last_hit_at < 1.5
            near = sum(1 for e in enemies if c.dist_to(e) <= 6.0)
            return me if near and (hit_recently or near >= 2 or hp_ratio < 0.8) else None
        if typ == "lifesteal_buff":
            return me if dist <= 3.5 else None
        if typ == "ghost_walk":
            if their < 0.45 and 3.0 < dist < 9.0 and not self.turret_threat(sim, tx, tz):
                return (tx, tz)
            return None
        if typ == "knockback":
            return (tx, tz) if dist <= ab["range"] else None
        if typ == "teleport_strike":
            if (dist >= 5.0 and (clustered or their < 0.35) and not self.turret_threat(sim, tx, tz)
                    and hp_ratio > 0.5):
                return (tx, tz)
            return None
        if typ == "cone":
            return (tx, tz) if dist <= ab["range"] * 0.95 else None
        if typ == "silence_marked":
            marked = [e for e in enemies if e.mark_of("resonance", t, c.id) and c.dist_to(e) <= ab["radius"]]
            return me if marked and (len(marked) >= 2 or their < 0.6 or c.dist_to(marked[0]) <= 5.0) else None
        if typ == "cage":
            if dist <= ab["range"] and (their < 0.7 or clustered):
                return self.aim(sim, target)
            return None
        if typ == "anchor":
            if c.anchor_id in sim.anchors:
                a = sim.anchors[c.anchor_id]
                far = math.hypot(a.x - c.x, a.z - c.z) > 2.5
                # 콤보를 넣은 뒤(칼을 던지고 났을 때)나 위험하면 말뚝으로 복귀
                if far and (hp_ratio < 0.5 or a.until - t < 1.2 or (c.q_hit_until == 0 and t - c.last_hit_at < 1.0)):
                    return me
                return None
            return me if (dist <= 8.5 and hp_ratio > 0.5 and their < 0.85) else None
        if typ == "rope_walk":
            if c.rope:
                return None                                  # 줄 위 행동은 rope_tick 이 한다
            if dist <= 8.0 and ((len(enemies) >= 2 and hp_ratio < 0.8) or hp_ratio < 0.5):
                return (tx, tz)
            return None
        if typ == "trap":
            if 4.0 <= dist <= ab["range"] + 1.0:
                return (c.x + (tx - c.x) * 0.65, c.z + (tz - c.z) * 0.65)
            return None
        if typ == "self_buff":
            return me if dist <= c.stats["attack_range"] + 1.5 else None
        if typ == "dash":
            if c.stats["attack_range"] > 3.0:               # 원거리: 붙은 적에게서 구르며 빠진다
                if dist < 3.4 and not self.turret_threat(sim, c.x, c.z):
                    d = dist or 1.0
                    return (c.x - (tx - c.x) / d * 4.0, c.z - (tz - c.z) / d * 4.0)
                return None
            rng_atk = c.stats["attack_range"]
            if their < 0.4 and rng_atk + 1 < dist < rng_atk + ab["range"] and not self.turret_threat(sim, tx, tz):
                return (tx, tz)
            return None
        if typ == "line_aoe":
            return self.aim(sim, target, None) if dist <= ab["range"] * 0.9 else None
        if typ == "ground_aoe":
            if dist <= ab["range"] and (their < 0.55 or clustered):
                return self.aim(sim, target)
            return None
        if typ == "volley":
            return (tx, tz) if dist <= ab["range"] * 0.95 else None
        if typ == "cocoon":                                  # 고치: 적 근처에 깔아 새끼 거미가 달려들게
            return (tx, tz) if 1.5 < dist <= ab["range"] else None
        if typ == "spit_pool":                               # 독 뱉기: 가까운 적의 발밑에 독 웅덩이
            return self.aim(sim, target, None) if dist <= ab["range"] else None
        if typ == "lunge":                                   # 일직선 돌진: 사거리 안에서 적을 겨눠 달려든다
            return self.aim(sim, target, None) if 2.0 < dist <= ab["range"] * 0.85 and not self.turret_threat(sim, tx, tz) else None
        if typ == "serpent_slam":                            # 내려찍기: 가까이 선 적 한가운데로
            return self.aim(sim, target, None) if dist <= ab["range"] and (their < 0.7 or clustered or dist < 3.5) else None
        if typ == "dive":                                    # 잠행: 떨어져 있는 적에게 솟구친다
            if 5.0 <= dist <= ab["range"] + 1.0 and hp_ratio > 0.4 and not self.turret_threat(sim, tx, tz):
                return (tx, tz)
            return None
        if typ == "tornado":                                 # 회오리: 사거리 안의 적을 겨눠 굴린다
            return self.aim(sim, target, None) if dist <= ab["range"] * 0.9 else None
        if typ == "wing_sweep":                              # 날개 후려치기: 몸 둘레에 적이 붙어 있을 때
            return me if dist <= ab["radius"] * 0.85 else None
        if typ == "sky_dive":                                # 급강하: 모여 있거나 체력이 낮은 적 위로 (날아오르는 동안 움직임을 예측해 앞에)
            if dist <= ab["range"] and (clustered or their < 0.55) and not self.turret_threat(sim, tx, tz):
                return self.aim(sim, target, 7.0)
            return None
        if typ == "leap_slam":                               # 도약: 떨어져 있는 적에게 덮친다
            if (2.2 < dist <= ab["range"] + 0.5 and hp_ratio > 0.35 and not self.turret_threat(sim, tx, tz)):
                return (tx, tz)
            return None
        if typ == "zone" and (ab.get("root") or ab.get("damage_per_sec")):   # 공격형 장판 (대자연의 정원, 독 거미줄)
            if dist <= ab["range"] and (clustered or their < 0.5):
                return (tx, tz)
            return None
        return None

    def plan_support(self, sim, slot, enemies, allies):
        """아군을 돕는 스킬: 조준 지점 또는 None."""
        c = self.c
        t = sim.time
        ab = self.ab(slot)
        typ = ab["type"]
        rng = ab.get("range", 9.0)
        hurt = [a for a in allies if a.hp / max(1.0, a.max_hp) < 0.7 and c.dist_to(a) <= rng]
        under_fire = [a for a in allies if t - a.last_hit_at < 2.0 and c.dist_to(a) <= rng]
        fighting = bool(enemies)

        if typ == "ally_heal":
            pool = hurt if hurt else [a for a in allies if a.hp < a.max_hp * 0.9 and c.dist_to(a) <= rng and fighting]
            if not pool:
                return None
            a = min(pool, key=lambda a: a.hp / max(1.0, a.max_hp))
            return (a.x, a.z)
        if typ == "cleanse":
            for a in allies:
                if self.needs_cleanse(a, t) and c.dist_to(a) <= rng:
                    return (a.x, a.z)
            return None
        if typ == "team_heal":
            low = [a for a in allies if a.hp / max(1.0, a.max_hp) < 0.45 and c.dist_to(a) <= ab["radius"]]
            if len(low) >= 2 or (low and fighting and c.hp / max(1.0, c.max_hp) < 0.4):
                return (c.x, c.z)
            return None
        if typ == "ally_shield":
            if not fighting:
                return None
            pool = [a for a in under_fire if a.hp / max(1.0, a.max_hp) < 0.9]
            if not pool:
                return None
            a = min(pool, key=lambda a: a.hp / max(1.0, a.max_hp))
            return (a.x, a.z)
        if typ == "ally_buff":
            if not fighting:
                return None
            carriers = [a for a in allies if a is not c and c.dist_to(a) <= rng
                        and (a.attack_target is not None or a.windup)]
            if carriers:
                a = max(carriers, key=lambda a: a.stats["ad"])
                return (a.x, a.z)
            return (c.x, c.z) if c.attack_target is not None else None
        if typ == "zone" and not ab.get("root"):             # 회복 장판 (성역)
            if not fighting or not hurt:
                return None
            a = min(hurt, key=lambda a: a.hp / max(1.0, a.max_hp))
            return (a.x, a.z)
        return None

    def support_cast(self, sim, allies, enemies):
        c = self.c
        for slot in ("R", "E", "W", "Q"):
            typ = self.ab(slot)["type"]
            if typ not in SUPPORT_TYPES and not (typ == "zone" and not self.ab(slot).get("root")):
                continue
            if not self.ready(sim, slot):
                continue
            pt = self.plan_support(sim, slot, enemies, allies)
            if pt is not None and sim.cast(c, slot, pt[0], pt[1]):
                return True
        return False

    def try_skills(self, sim, target, enemies, allies, hp_ratio):
        c = self.c
        for slot in c.data.get("bot_priority", ["R", "E", "W", "Q"]):
            typ = self.ab(slot)["type"]
            if typ in SUPPORT_TYPES or (typ == "zone" and not self.ab(slot).get("root")):
                continue
            if not self.ready(sim, slot):
                continue
            pt = self.plan(sim, slot, target, enemies, allies, hp_ratio)
            if pt is not None and sim.cast(c, slot, pt[0], pt[1]):
                return True
        return False

    def escape(self, sim, close, fx, fz):
        """위험할 때 쓰는 탈출·방어 스킬."""
        c = self.c
        t = sim.time
        for slot in ("E", "Q", "W", "R"):
            if not self.ready(sim, slot):
                continue
            ab = self.ab(slot)
            typ = ab["type"]
            if typ in ("dash", "ghost_walk"):
                return sim.cast(c, slot, fx, fz)
            if typ == "anchor" and c.anchor_id in sim.anchors:
                return sim.cast(c, slot, c.x, c.z)
            if typ == "rope_walk" and not c.rope:
                return sim.cast(c, slot, fx, fz)
            if typ == "knockback" and c.dist_to(close[0]) <= ab["range"]:
                return sim.cast(c, slot, close[0].x, close[0].z)
            if typ in ("counter_shield", "echo_guard"):
                return sim.cast(c, slot, c.x, c.z)
            if typ == "ally_shield":
                return sim.cast(c, slot, c.x, c.z)
            if typ == "self_aoe" and c.dist_to(close[0]) <= ab["radius"]:
                return sim.cast(c, slot, c.x, c.z)
        _ = t
        return False

    def rope_tick(self, sim, enemies):
        """공중 외줄 위: 가까운 적에게 칼을 내리꽂고, 시간이 다 되어 가면 내려온다."""
        c = self.c
        r = c.rope
        t = sim.time
        ex = [e for e in enemies if math.hypot(e.x - c.x, e.z - c.z) <= 5.5]
        if ex:
            e = min(ex, key=lambda e: c.dist_to(e))
            if self.ready(sim, "W") and self.ab("W")["type"] == "knife_throw" and c.dist_to(e) <= 4.2:
                sim.cast(c, "W", e.x, e.z)
        if enemies:
            e = min(enemies, key=lambda e: c.dist_to(e))
            sim.cmd_move(c, e.x, e.z)
        landing = r["until"] - t < 0.4 or (not enemies and t > r["until"] - 2.0)
        if landing:
            sim.cast(c, "R", c.x, c.z)

    # ------------------------------------------------------------------
    def decide(self, sim):
        c = self.c
        t = sim.time
        direction = mapdata.team_dir(c.team)
        hp_ratio = c.hp / max(1.0, c.max_hp)
        fx, fz = mapdata.fountain_pos(c.team)
        rng_atk = c.stats["attack_range"]

        # 봇도 시야 안의 적만 안다
        enemies = [e for e in sim.champions.values()
                   if e.team != c.team and not e.dead and c.dist_to(e) <= 13 and sim.can_see(c.team, e)]
        allies = [a for a in sim.champions.values() if a.team == c.team and not a.dead and c.dist_to(a) <= 10]

        if c.rope:
            self.rope_tick(sim, enemies)
            return

        # ---- 귀환 중: 안전하면 그대로 두고, 위험해지면 귀환을 멈추고 아래 판단(후퇴 등)으로
        if c.recall_at is not None:
            if not self.in_danger(sim):
                return
            c.recall_at = None
        # 우물에서는 거의 다 찰 때까지 회복
        if sim.in_fountain(c) and (hp_ratio < 0.9 or c.mana < c.max_mana * 0.6):
            return

        # ---- 말뚝이 남아 있고 주변에 적이 없으면 복귀 (쿨타임을 돌리기 위해)
        if c.anchor_id in sim.anchors and not enemies:
            for slot in ("E", "Q", "W"):
                if self.ab(slot)["type"] == "anchor" and self.ready(sim, slot):
                    sim.cast(c, slot, c.x, c.z)
                    break

        # ---- 위험: 후퇴
        if hp_ratio < 0.28:
            # 안전할 때만 귀환, 아니면 먼저 우물 쪽으로 물러난다
            if not sim.in_fountain(c) and not self.in_danger(sim):
                sim.recall(c)
                return
            relic = self.safe_relic(sim, 16)
            if relic and not enemies:
                sim.cmd_move(c, relic.x, relic.z)
                return
            close = [e for e in enemies if c.dist_to(e) < 5]
            if close and self.support_cast(sim, allies, enemies):
                return
            if close and self.escape(sim, close, fx, fz):
                return
            if close and hp_ratio < 0.15 and t >= c.ready_at["D"] and c.spells[0] == "flash":
                sim.flash(c, fx, fz)
                return
            if close:
                self.poke(sim, close[0], c.dist_to(close[0]))
            sim.cmd_move(c, fx + direction * 4, fz)
            return

        # ---- 아군 지원 (치유·정화·보호막·버프)
        if self.support_cast(sim, allies, enemies):
            return

        if hp_ratio < 0.65:
            relic = self.safe_relic(sim, 9)
            if relic:
                sim.cmd_move(c, relic.x, relic.z)
                return

        # ---- 교전
        target = None
        best = 1e9
        for e in enemies:
            if self.turret_threat(sim, e.x, e.z) and e.hp / e.max_hp > 0.25:
                continue
            score = e.hp / max(1.0, e.max_hp) * 10 + c.dist_to(e)
            if score < best:
                best, target = score, e
        if target is not None:
            their = target.hp / max(1.0, target.max_hp)
            dist = c.dist_to(target)
            outnumbered = len(enemies) > len(allies) + 1
            engage = (their < 0.35 or (hp_ratio >= their * 0.85 and not outnumbered) or dist <= rng_atk * 0.7)
            self.poke(sim, target, dist)
            if engage:
                if self.try_skills(sim, target, enemies, allies, hp_ratio):
                    return
                if c.mark and their < 0.45 and hp_ratio > 0.5:
                    sim.mark(c, target.x, target.z)
                    return
                if (c.spells[1] == "mark" and t >= c.ready_at["F"] and not c.mark and dist <= MARK_RANGE * 0.8
                        and their < 0.6 and hp_ratio > 0.55 and self.rng.random() < 0.3):
                    sim.mark(c, *self.aim(sim, target, 25))
                if c.attack_target != target.id:
                    sim.cmd_attack(c, target.id)
                return
            if dist < rng_atk * 0.9 and rng_atk > 3.0:
                # 불리하면 거리를 벌린다 (원거리 챔피언만)
                sim.cmd_move(c, c.x - direction * 3, c.z)
                return

        # ---- 파밍 / 푸시
        allied_minions = [m for m in sim.minions.values() if m.team == c.team]
        if allied_minions:
            front_x = max(m.x * direction for m in allied_minions) * direction
            # 포탑 공격: 미니언이 포탑 어그로를 받는 중이면
            for s in sim.structures.values():
                if s.team != c.team and sim.vulnerable(s) and c.dist_to(s) <= rng_atk + s.radius + 4:
                    if s.skind != "turret" or not self.turret_threat(sim, c.x, c.z):
                        if not enemies:
                            if c.attack_target != s.id:
                                sim.cmd_attack(c, s.id)
                            return
            # 막타 / 미니언 처치
            cand = None
            cand_hp = 1e9
            for m in sim.minions.values():
                if m.team == c.team or c.dist_to(m) > rng_atk + 3.5:
                    continue
                if self.turret_threat(sim, m.x, m.z):
                    continue
                if m.hp < cand_hp:
                    cand, cand_hp = m, m.hp
            if cand is not None:
                if c.attack_target != cand.id:
                    sim.cmd_attack(c, cand.id)
                return
            hold_x = front_x - direction * (rng_atk * 0.6 + 1.0)
        else:
            # 아군 미니언이 없으면 아군 최전방 포탑 근처에서 대기
            own = [s for s in sim.structures.values() if s.team == c.team and s.skind == "turret" and s.alive]
            if own:
                front = max(own, key=lambda s: s.x * direction)
                hold_x = front.x + direction * 3.0
            else:
                hold_x = fx + direction * 10

        hold_z = self.lane_offset
        if self.turret_threat(sim, hold_x, hold_z):
            for s in self.enemy_turrets(sim):
                if abs(s.x - hold_x) < mapdata.TURRET_RANGE + 1.5:
                    hold_x = s.x - direction * (mapdata.TURRET_RANGE + 1.5)
        if c.dist_xy(hold_x, hold_z) > 1.2:
            if c.move_target is None or math.hypot(c.move_target[0] - hold_x, c.move_target[1] - hold_z) > 1.0:
                sim.cmd_move(c, hold_x, hold_z)

    def poke(self, sim, target, dist):
        """멀리서 견제할 수 있는 직선·부채꼴 스킬 (궁극기 제외)."""
        c = self.c
        if c.mana < c.max_mana * 0.3:
            return
        for slot in ("Q", "W", "E"):
            ab = self.ab(slot)
            if ab["type"] not in POKE_TYPES or not self.ready(sim, slot):
                continue
            rng = ab.get("range", 8)
            if ab["type"] == "line_aoe" and dist > rng * 0.9:
                continue
            if dist <= rng * 0.9:
                sim.cast(c, slot, *self.aim(sim, target, ab.get("speed")))
                return
