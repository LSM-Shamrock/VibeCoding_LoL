"""챔피언 봇 AI. 플레이어와 같은 명령 함수(sim.cast, sim.cmd_move 등)를 사용한다."""
import math
import random

from ..shared import data as gamedata
from ..shared import mapdata
from ..shared.constants import MARK_RANGE


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
        if c.dead or c.dash or c.stunned(sim.time):
            return
        self.decide(sim)

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
            if c.gold >= item["cost"]:
                sim.buy(c, iid)
            else:
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

    def ready(self, sim, slot):
        c = self.c
        if c.ranks.get(slot, 0) <= 0 or sim.time < c.ready_at[slot]:
            return False
        ab = c.data["abilities"][slot]
        return c.mana >= ab.get("mana", [0])[c.ranks[slot] - 1]

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

    # ------------------------------------------------------------------
    def decide(self, sim):
        c = self.c
        t = sim.time
        direction = mapdata.team_dir(c.team)
        hp_ratio = c.hp / max(1.0, c.max_hp)
        fx, fz = mapdata.fountain_pos(c.team)
        rng_atk = c.stats["attack_range"]

        enemies = [e for e in sim.champions.values() if e.team != c.team and not e.dead and c.dist_to(e) <= 13]
        allies = [a for a in sim.champions.values() if a.team == c.team and not a.dead and c.dist_to(a) <= 10]

        # ---- 위험: 후퇴
        if hp_ratio < 0.28:
            relic = self.safe_relic(sim, 16)
            if relic and not enemies:
                sim.cmd_move(c, relic.x, relic.z)
                return
            close = [e for e in enemies if c.dist_to(e) < 5]
            if close and self.ready(sim, "E") and c.data["abilities"]["E"]["type"] == "dash":
                sim.cast(c, "E", fx, fz)
                return
            if close and hp_ratio < 0.15 and t >= c.ready_at["D"]:
                sim.flash(c, fx, fz)
                return
            if close and self.ready(sim, "Q"):
                e = close[0]
                sim.cast(c, "Q", *self.aim(sim, e))
            sim.cmd_move(c, fx + direction * 4, fz)
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
                abil = c.data["abilities"]
                if self.ready(sim, "R") and dist <= abil["R"].get("range", 10) and (
                        their < 0.55 or self.count_near(enemies, target, abil["R"].get("radius", 3)) >= 2):
                    sim.cast(c, "R", *self.aim(sim, target))
                    return
                if self.ready(sim, "W") and dist <= rng_atk + 1.5:
                    sim.cast(c, "W", c.x, c.z)
                if (self.ready(sim, "E") and their < 0.4 and rng_atk + 1 < dist < rng_atk + abil["E"].get("range", 4)
                        and not self.turret_threat(sim, target.x, target.z)):
                    sim.cast(c, "E", target.x, target.z)
                    return
                if c.mark and their < 0.45 and hp_ratio > 0.5:
                    sim.mark(c, target.x, target.z)
                    return
                if (t >= c.ready_at["F"] and not c.mark and dist <= MARK_RANGE * 0.8 and their < 0.6
                        and hp_ratio > 0.55 and self.rng.random() < 0.3):
                    sim.mark(c, *self.aim(sim, target, 25))
                if c.attack_target != target.id:
                    sim.cmd_attack(c, target.id)
                return
            if dist < rng_atk * 0.9:
                # 불리하면 거리를 벌린다
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
        c = self.c
        q = c.data["abilities"]["Q"]
        if self.ready(sim, "Q") and dist <= q.get("range", 8) * 0.9 and c.mana > c.max_mana * 0.3:
            sim.cast(c, "Q", *self.aim(sim, target, q.get("speed")))

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
