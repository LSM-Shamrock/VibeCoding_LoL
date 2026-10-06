"""Deterministic, graphics-free authoritative arena simulation."""
from dataclasses import asdict, dataclass, field
import math
import random

from .content import (CHAMPIONS, ITEMS, MAP_X, MAP_Z, SPAWN_X,
                      WAVE_INTERVAL, INHIBITOR_RESPAWN, RELIC_RESPAWN)


def clamp(value, low, high):
    return max(low, min(high, value))


def distance(a, b):
    return math.hypot(a.x - b.x, a.z - b.z)


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("잘못된 좌표입니다.")
    x, z = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(z):
        raise ValueError("잘못된 좌표입니다.")
    return clamp(x, -MAP_X, MAP_X), clamp(z, -MAP_Z, MAP_Z)


@dataclass
class Unit:
    id: str
    kind: str
    team: int
    x: float
    z: float
    hp: float
    max_hp: float
    damage: float
    armor: float = 0
    speed: float = 0
    attack_range: float = 2
    interval: float = 1
    radius: float = 0.65
    champion: str = ""
    name: str = ""
    bot: bool = False
    mana: float = 0
    max_mana: float = 0
    level: int = 3
    xp: float = 0
    gold: float = 1375
    power: float = 0
    haste: float = 0
    items: list = field(default_factory=list)
    cooldowns: list = field(default_factory=lambda: [0.0] * 6)
    attack_cd: float = 0
    respawn: float = 0
    target: str = ""
    destination: list | None = None
    attack_move: bool = False
    shop_allowed: bool = True
    shield: float = 0
    shield_time: float = 0
    slow: float = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    facing: float = 0
    tier: int = 0
    aggro: str = ""
    aggro_time: float = 0
    ramp: int = 0
    mark: str = ""
    mark_time: float = 0
    attackers: dict = field(default_factory=dict)

    @property
    def alive(self):
        return self.hp > 0


class World:
    def __init__(self, players, seed=7):
        self.random = random.Random(seed)
        self.units = {}
        self.time = 0.0
        self.wave_at = 8.0
        self.wave = 0
        self.serial = 0
        self.winner = None
        self.effects = []
        self.projectiles = []
        self.feed = []
        self.relics = [{"x":x, "z":z, "timer":15.0, "burst":0.0}
                       for x, z in [(-28, -5), (-10, 5), (10, -5), (28, 5)]]
        self.bot_at = 0.0
        for player in players:
            spec = CHAMPIONS[player["champion"]]
            team = player["team"]
            unit = Unit(player["id"], "hero", team, self.spawn_x(team),
                        self.random.uniform(-3, 3), spec["hp"], spec["hp"],
                        spec["damage"], spec["armor"], spec["speed"],
                        spec["range"], spec["attack_interval"], champion=spec["id"],
                        name=player["name"], bot=player.get("bot", False),
                        mana=spec["mana"], max_mana=spec["mana"])
            self.units[unit.id] = unit
        for team in (0, 1):
            sign = -1 if team == 0 else 1
            for tier, x in [(0, 19), (1, 33)]:
                self.add_structure(f"t{team}_{tier}", "tower", team, sign*x, 0, 2300, tier)
            self.add_structure(f"i{team}", "inhibitor", team, sign*40, 0, 1700, 2)
            for i, z in enumerate((-3.4, 3.4)):
                self.add_structure(f"nt{team}_{i}", "tower", team, sign*47, z, 1900, 3)
            self.add_structure(f"n{team}", "nexus", team, sign*54, 0, 3200, 4)

    @staticmethod
    def spawn_x(team):
        return -SPAWN_X if team == 0 else SPAWN_X

    def add_structure(self, uid, kind, team, x, z, hp, tier):
        self.units[uid] = Unit(uid, kind, team, x, z, hp, hp, 145,
                              armor=25, attack_range=9, interval=1.15,
                              radius=1.35 if kind == "tower" else 1.8, tier=tier)

    def vulnerable(self, unit):
        if unit.kind not in ("tower", "inhibitor", "nexus"):
            return True
        team = unit.team
        if unit.tier == 0:
            return True
        if unit.tier == 1:
            return not self.units[f"t{team}_0"].alive
        if unit.tier == 2:
            return not self.units[f"t{team}_1"].alive
        if unit.tier == 3:
            return not self.units[f"i{team}"].alive
        return (not self.units[f"i{team}"].alive and
                not any(self.units[f"nt{team}_{i}"].alive for i in (0, 1)))

    def effect(self, kind, x, z, team, radius=1, duration=0.45, **extra):
        self.serial += 1
        self.effects.append(dict(id=self.serial, kind=kind, x=x, z=z, team=team,
                                 radius=radius, life=duration, duration=duration, **extra))

    def notify(self, text):
        self.feed.append({"text":text, "time":round(self.time, 1)})
        self.feed = self.feed[-5:]

    def command(self, uid, command):
        hero = self.units.get(uid)
        if not hero or hero.kind != "hero" or self.winner is not None:
            return
        action = command.get("action")
        if action == "buy":
            self.buy(hero, command.get("item"))
            return
        if not hero.alive:
            return
        if action in ("move", "attack_move"):
            hero.destination = list(point(command.get("point")))
            hero.target = ""
            hero.attack_move = action == "attack_move"
        elif action == "attack":
            target = self.units.get(str(command.get("target")))
            if target and target.team != hero.team and target.alive and self.vulnerable(target):
                hero.target = target.id
                hero.destination = None
                hero.attack_move = False
        elif action == "stop":
            hero.destination = None
            hero.target = ""
            hero.attack_move = False
        elif action == "cast":
            slot = command.get("slot")
            if type(slot) is int and 0 <= slot <= 5:
                self.cast(hero, slot, point(command.get("point")))

    def buy(self, hero, item_id):
        item = ITEMS.get(str(item_id))
        if not item:
            raise ValueError("존재하지 않는 아이템입니다.")
        at_spawn = abs(hero.x - self.spawn_x(hero.team)) < 6
        if hero.alive and (not hero.shop_allowed or not at_spawn):
            raise ValueError("상점은 출발 전 또는 사망 중에만 이용할 수 있습니다.")
        if len(hero.items) >= 6:
            raise ValueError("아이템 슬롯이 가득 찼습니다.")
        if item.get("unique") and item_id in hero.items:
            raise ValueError("이미 보유한 고유 아이템입니다.")
        if hero.gold < item["cost"]:
            raise ValueError("골드가 부족합니다.")
        hero.gold -= item["cost"]
        hero.items.append(item_id)
        for stat in ("damage", "armor", "speed", "power", "haste"):
            setattr(hero, stat, getattr(hero, stat) + item.get(stat, 0))
        hero.max_hp += item.get("hp", 0)
        hero.max_mana += item.get("mana", 0)
        if hero.alive:
            hero.hp += item.get("hp", 0)
            hero.mana += item.get("mana", 0)

    def enemies(self, unit, radius, structures=True):
        return [other for other in self.units.values()
                if other.alive and other.team != unit.team and
                (structures or other.kind in ("hero", "minion", "super")) and
                distance(unit, other) <= radius + other.radius and self.vulnerable(other)]

    def cast(self, hero, slot, aim):
        if slot == 4 and hero.mark_time > 0:
            target = self.units.get(hero.mark)
            if target and target.alive:
                hero.x, hero.z = point([target.x - (1 if hero.team == 0 else -1), target.z])
                hero.destination = None
                hero.target = target.id
                self.hurt(target, 65, hero, magic=True)
                self.effect("dash", hero.x, hero.z, hero.team, 2)
            hero.mark_time = 0
            return
        if hero.cooldowns[slot] > 0:
            return
        dx, dz = aim[0] - hero.x, aim[1] - hero.z
        length = math.hypot(dx, dz)
        nx, nz = (dx/length, dz/length) if length > 0.01 else ((1 if hero.team == 0 else -1), 0)
        hero.facing = math.degrees(math.atan2(nx, nz))
        if slot == 5:
            hero.x, hero.z = point([hero.x + nx*min(length, 5), hero.z + nz*min(length, 5)])
            hero.destination = None
            hero.cooldowns[5] = 90
            self.effect("dash", hero.x, hero.z, hero.team, 2)
            return
        if slot == 4:
            hero.cooldowns[4] = 45
            self.launch(hero, nx, nz, 23, 80, 0.7, mark=True)
            return
        if slot == 3 and hero.level < 6:
            return
        spec = CHAMPIONS[hero.champion]["skills"][slot]
        if hero.mana < spec["cost"]:
            return
        hero.mana -= spec["cost"]
        hero.cooldowns[slot] = spec["cooldown"]
        amount = spec["damage"] + hero.power*0.65 + (hero.level-3)*9
        kind = spec["kind"]
        if kind == "bolt":
            self.launch(hero, nx, nz, spec["range"], amount, spec["radius"])
        elif kind == "shield":
            hero.shield = amount
            hero.shield_time = 4
            self.effect("shield", hero.x, hero.z, hero.team, 2)
        elif kind == "heal":
            for ally in self.units.values():
                if ally.kind == "hero" and ally.alive and ally.team == hero.team and distance(hero, ally) <= spec["radius"]:
                    ally.hp = min(ally.max_hp, ally.hp + amount*(1 if ally.id == hero.id else 0.5))
            self.effect("heal", hero.x, hero.z, hero.team, spec["radius"], 0.7)
        else:
            cx, cz = hero.x, hero.z
            if kind in ("nova", "dash"):
                cx += nx*min(length, spec["range"])
                cz += nz*min(length, spec["range"])
                cx, cz = point([cx, cz])
            if kind == "dash":
                hero.x, hero.z = cx, cz
                hero.destination = None
            for target in list(self.units.values()):
                if not target.alive or target.team == hero.team or target.kind not in ("hero", "minion", "super"):
                    continue
                tx, tz = target.x-cx, target.z-cz
                if kind == "cone":
                    hit = math.hypot(tx, tz) <= spec["range"]+target.radius and tx*nx + tz*nz >= 0
                else:
                    hit = math.hypot(tx, tz) <= spec["radius"]+target.radius
                if hit:
                    self.hurt(target, amount, hero, magic=True)
                    if kind == "nova":
                        target.slow = 2
            self.effect(kind, cx, cz, hero.team, spec["radius"], 0.65)

    def launch(self, hero, nx, nz, reach, damage, radius, mark=False):
        self.serial += 1
        self.projectiles.append(dict(id=self.serial, owner=hero.id, team=hero.team,
                                     x=hero.x, z=hero.z, nx=nx, nz=nz, remaining=reach,
                                     damage=damage, radius=radius, mark=mark))

    def hurt(self, target, amount, source, magic=False):
        if not target.alive or not self.vulnerable(target):
            return
        if target.kind in ("tower", "nexus"):
            # Backdoor protection when no attacking minions are near the building.
            supported = any(u.alive and u.team == source.team and u.kind in ("minion", "super")
                            and distance(u, target) < 11 for u in self.units.values())
            if not supported:
                amount *= 0.25
        amount *= 100/(100+(25 if magic else target.armor))
        absorbed = min(target.shield, amount)
        target.shield -= absorbed
        target.hp = max(0, target.hp - amount + absorbed)
        if source.kind == "hero":
            target.attackers[source.id] = self.time
        if target.kind == "hero" and source.kind == "hero":
            for tower in self.units.values():
                if tower.kind == "tower" and tower.alive and tower.team == target.team and distance(tower, source) < tower.attack_range:
                    tower.aggro, tower.aggro_time = source.id, 3
        if not target.alive:
            self.kill(target, source)

    def kill(self, target, source):
        self.effect("death", target.x, target.z, target.team, 2.4, 0.8)
        target.target = ""
        target.destination = None
        if target.kind == "hero":
            target.deaths += 1
            target.respawn = min(45, 8 + target.level*1.8 + self.time/90)
            target.shield = 0
            target.mark_time = 0
            target.shop_allowed = True
            if source.kind == "hero":
                source.kills += 1
                source.gold += 300
                source.xp += 100
            for uid, hit_at in target.attackers.items():
                helper = self.units.get(uid)
                if helper and helper.id != source.id and self.time-hit_at <= 10:
                    helper.assists += 1
                    helper.gold += 100
            target.attackers.clear()
            self.notify(f"{source.name or '포탑/미니언'} → {target.name}")
        elif target.kind in ("minion", "super"):
            for hero in self.units.values():
                if hero.kind == "hero" and hero.team != target.team and hero.alive and distance(hero, target) < 16:
                    hero.xp += 18 if target.kind == "minion" else 45
                    hero.gold += 8
            if source.kind == "hero":
                source.gold += 22 if target.kind == "minion" else 50
        elif target.kind == "inhibitor":
            target.respawn = INHIBITOR_RESPAWN
            self.notify(f"{'블루' if target.team == 0 else '레드'} 억제기 파괴")
        elif target.kind == "nexus":
            self.winner = source.team
            self.notify(f"{'블루' if source.team == 0 else '레드'} 팀 승리")
        else:
            self.notify(f"{'블루' if target.team == 0 else '레드'} 포탑 파괴")
            for hero in self.units.values():
                if hero.kind == "hero" and hero.team != target.team:
                    hero.gold += 150

    def spawn_wave(self):
        self.wave += 1
        for team in (0, 1):
            super_wave = not self.units[f"i{1-team}"].alive
            for index in range(7 if super_wave or self.wave % 3 == 0 else 6):
                self.serial += 1
                special = index == 6
                ranged = 3 <= index <= 5
                hp = (720 if super_wave else 450) if special else (210 if ranged else 320)
                hp += self.time*0.3
                unit = Unit(f"m{self.serial}", "super" if special else "minion", team,
                            self.spawn_x(team) + (index//3)*(1 if team == 0 else -1),
                            (index % 3 - 1)*1.5, hp, hp,
                            65 if special else (24 if ranged else 30), armor=5,
                            speed=3.2, attack_range=6 if ranged else 1.8, interval=1.25,
                            radius=0.8 if special else 0.45)
                self.units[unit.id] = unit

    def move(self, unit, x, z, dt):
        dx, dz = x-unit.x, z-unit.z
        length = math.hypot(dx, dz)
        if length < 0.1:
            unit.destination = None
            return
        # Steer around solid buildings, including friendly towers in the lane.
        # A deterministic side prevents a unit on the lane center getting stuck.
        for building in self.units.values():
            if not building.alive or building.kind not in ("tower", "inhibitor", "nexus"):
                continue
            if building.team != unit.team and math.hypot(x-building.x,z-building.z)<0.1:
                continue
            safe = building.radius + unit.radius*0.6 + 0.45
            bx,bz = building.x-unit.x,building.z-unit.z
            along = (bx*dx+bz*dz)/length
            across = abs(bx*dz-bz*dx)/length
            if -safe*.3 < along < safe+1.2 and across < safe and math.hypot(bx,bz) < safe+2:
                side = 1 if unit.z >= building.z else -1
                dx = (1 if x > unit.x else -1)*0.5
                dz = building.z + side*(safe+0.7)-unit.z
                length = math.hypot(dx,dz)
                break
        step = min(length, unit.speed*dt*(0.55 if unit.slow > 0 else 1))
        unit.x, unit.z = point([unit.x+dx/length*step, unit.z+dz/length*step])
        unit.facing = math.degrees(math.atan2(dx, dz))
        # Buildings are solid. This also stops click-through on their centers.
        for building in self.units.values():
            if building.kind not in ("tower", "inhibitor", "nexus") or not building.alive:
                continue
            bx, bz = unit.x-building.x, unit.z-building.z
            d = math.hypot(bx, bz)
            minimum = building.radius + unit.radius*0.6
            if 0.001 < d < minimum:
                unit.x, unit.z = point([building.x+bx/d*minimum, building.z+bz/d*minimum])

    def bot_think(self, hero):
        if hero.shop_allowed and (not hero.alive or abs(hero.x-self.spawn_x(hero.team)) < 6):
            priority = ["crystal", "boots", "crown", "armor"] if hero.champion in ("mage", "healer") else ["sword", "boots", "armor", "bow"]
            for item_id in priority:
                if item_id == "boots" and item_id in hero.items:
                    continue
                if len(hero.items) < 6 and hero.gold >= ITEMS[item_id]["cost"]:
                    self.buy(hero, item_id)
        if not hero.alive:
            return
        nearby = self.enemies(hero, 14, structures=False)
        nearby.sort(key=lambda u: distance(hero, u) + (0 if u.kind == "hero" else 2))
        enemy = nearby[0] if nearby else None
        if hero.hp < hero.max_hp*0.28 and enemy:
            available = [r for r in self.relics if r["timer"] <= 0]
            if available:
                relic = min(available, key=lambda r: math.hypot(r["x"]-hero.x, r["z"]-hero.z))
                hero.destination = [relic["x"], relic["z"]]
            else:
                hero.destination = [hero.x + (-6 if hero.team == 0 else 6), hero.z]
            hero.target = ""
            for slot, spec in enumerate(CHAMPIONS[hero.champion]["skills"]):
                if spec["kind"] in ("heal", "shield"):
                    self.cast(hero, slot, (hero.x, hero.z))
            return
        if enemy:
            hero.target = enemy.id
            hero.destination = None
            d = distance(hero, enemy)
            if d < hero.attack_range*0.55 and hero.attack_range > 5 and enemy.kind == "hero":
                hero.destination = [hero.x + (hero.x-enemy.x)/max(d, 0.1)*3,
                                    hero.z + (hero.z-enemy.z)/max(d, 0.1)*3]
                hero.target = ""
            for slot, spec in enumerate(CHAMPIONS[hero.champion]["skills"]):
                if spec["kind"] in ("heal", "shield"):
                    if hero.hp < hero.max_hp*0.7:
                        self.cast(hero, slot, (enemy.x, enemy.z))
                elif d < spec["range"]+1:
                    self.cast(hero, slot, (enemy.x, enemy.z))
        else:
            buildings = [u for u in self.units.values() if u.alive and u.team != hero.team and u.kind in ("tower", "inhibitor", "nexus") and self.vulnerable(u)]
            if buildings:
                target = min(buildings, key=lambda u: distance(hero, u))
                allies = [u for u in self.units.values() if u.alive and u.team == hero.team and u.kind in ("minion", "super") and distance(u, target) < 11]
                if target.kind == "tower" and not allies and distance(hero, target) < 12:
                    direction = -1 if hero.team == 0 else 1
                    hero.destination = [target.x+direction*12, hero.z]
                    hero.target = ""
                else:
                    hero.target = target.id
                    hero.destination = None

    def update(self, dt):
        if self.winner is not None:
            return
        self.time += dt
        for effect in self.effects:
            effect["life"] -= dt
        self.effects = [e for e in self.effects if e["life"] > 0]
        if self.time >= self.wave_at:
            self.spawn_wave()
            self.wave_at += WAVE_INTERVAL
        think = self.time >= self.bot_at
        if think:
            self.bot_at = self.time + 0.35
        for unit in list(self.units.values()):
            unit.attack_cd = max(0, unit.attack_cd-dt)
            unit.slow = max(0, unit.slow-dt)
            unit.aggro_time = max(0, unit.aggro_time-dt)
            if unit.kind == "hero":
                unit.cooldowns = [max(0, cd-dt) for cd in unit.cooldowns]
                unit.shield_time = max(0, unit.shield_time-dt)
                unit.mark_time = max(0, unit.mark_time-dt)
                if unit.shield_time <= 0:
                    unit.shield = 0
                unit.gold += 5.5*dt
                unit.xp += 4*dt
                if unit.level < 18 and unit.xp >= 100+unit.level*45:
                    unit.xp -= 100+unit.level*45
                    unit.level += 1
                    unit.max_hp += 80
                    unit.max_mana += 35
                    unit.damage += 4
                    unit.armor += 2
                    if unit.alive:
                        unit.hp += 80
                        unit.mana += 35
                    self.effect("heal", unit.x, unit.z, unit.team, 2.5)
                if unit.bot and think:
                    self.bot_think(unit)
            if not unit.alive:
                if unit.kind in ("hero", "inhibitor"):
                    unit.respawn = max(0, unit.respawn-dt)
                    if unit.respawn <= 0:
                        unit.hp = unit.max_hp
                        if unit.kind == "hero":
                            unit.x, unit.z = self.spawn_x(unit.team), self.random.uniform(-2.5, 2.5)
                            unit.mana = unit.max_mana
                            unit.shop_allowed = True
                            unit.slow = 0
                            unit.attack_move = False
                        else:
                            self.notify("억제기가 재생되었습니다.")
                continue
            if unit.kind == "hero":
                unit.mana = min(unit.max_mana, unit.mana+3*dt)
                unit.hp = min(unit.max_hp, unit.hp+0.9*dt)
                if abs(unit.x-self.spawn_x(unit.team)) >= 6:
                    unit.shop_allowed = False
            if unit.kind in ("inhibitor", "nexus"):
                continue
            target = self.units.get(unit.target)
            if target and (not target.alive or not self.vulnerable(target)):
                target = None
                unit.target = ""
            if unit.kind == "tower":
                aggro = self.units.get(unit.aggro) if unit.aggro_time > 0 else None
                if aggro and aggro.alive and distance(unit, aggro) <= unit.attack_range+aggro.radius:
                    target = aggro
                if not target or distance(unit, target) > unit.attack_range+target.radius:
                    enemies = self.enemies(unit, unit.attack_range, structures=False)
                    target = min(enemies, key=lambda u: (u.kind == "hero", distance(unit, u)), default=None)
                    unit.ramp = 0
                unit.target = target.id if target else ""
            elif unit.kind in ("minion", "super") or (unit.kind == "hero" and (unit.attack_move or (not unit.target and not unit.destination))):
                if not target:
                    enemies = self.enemies(unit, 9 if unit.kind != "hero" else unit.attack_range+0.5)
                    target = min(enemies, key=lambda u: distance(unit, u), default=None)
                    unit.target = target.id if target else ""
            if target:
                d = distance(unit, target)
                if d <= unit.attack_range+target.radius:
                    unit.facing = math.degrees(math.atan2(target.x-unit.x, target.z-unit.z))
                    if unit.attack_cd <= 0:
                        unit.attack_cd = unit.interval/(1+unit.haste)
                        amount = unit.damage*(1+unit.ramp*0.25 if unit.kind == "tower" else 1)
                        self.hurt(target, amount, unit)
                        if unit.kind == "tower":
                            unit.ramp = min(3, unit.ramp+1) if target.kind == "hero" else 0
                        self.effect("attack", unit.x, unit.z, unit.team, duration=0.15,
                                    tx=target.x, tz=target.z)
                elif unit.speed > 0:
                    self.move(unit, target.x, target.z, dt)
            elif unit.destination:
                self.move(unit, *unit.destination, dt)
            elif unit.kind in ("minion", "super"):
                self.move(unit, self.spawn_x(1-unit.team), unit.z, dt)
            if self.winner is not None:
                return
        for projectile in list(self.projectiles):
            step = min(projectile["remaining"], 24*dt)
            old_x, old_z = projectile["x"], projectile["z"]
            projectile["x"] += projectile["nx"]*step
            projectile["z"] += projectile["nz"]*step
            projectile["remaining"] -= step
            hits = []
            for target in self.units.values():
                if not target.alive or target.team == projectile["team"] or target.kind not in ("hero", "minion", "super"):
                    continue
                along = clamp((target.x-old_x)*projectile["nx"]+(target.z-old_z)*projectile["nz"], 0, step)
                d = math.hypot(target.x-old_x-projectile["nx"]*along,
                               target.z-old_z-projectile["nz"]*along)
                if d <= projectile["radius"]+target.radius:
                    hits.append((along, target))
            if hits:
                target = min(hits, key=lambda pair: pair[0])[1]
                owner = self.units.get(projectile["owner"])
                if owner:
                    self.hurt(target, projectile["damage"], owner, magic=True)
                    if projectile["mark"] and target.alive and owner.alive:
                        owner.mark, owner.mark_time = target.id, 3
                self.effect("nova", target.x, target.z, projectile["team"], 1.3, 0.3)
                projectile["remaining"] = 0
        self.projectiles = [p for p in self.projectiles if p["remaining"] > 0]
        for relic in self.relics:
            if relic["burst"] > 0:
                relic["burst"] -= dt
                if relic["burst"] <= 0:
                    for hero in self.units.values():
                        if hero.kind == "hero" and hero.alive and math.hypot(hero.x-relic["x"], hero.z-relic["z"]) < 4:
                            hero.hp = min(hero.max_hp, hero.hp+hero.max_hp*0.18)
                            hero.mana = min(hero.max_mana, hero.mana+hero.max_mana*0.18)
                    self.effect("heal", relic["x"], relic["z"], 0, 4, 0.8)
            relic["timer"] = max(0, relic["timer"]-dt)
            if relic["timer"] <= 0:
                for hero in self.units.values():
                    if hero.kind == "hero" and hero.alive and math.hypot(hero.x-relic["x"], hero.z-relic["z"]) < 1.3:
                        hero.hp = min(hero.max_hp, hero.hp+hero.max_hp*0.08)
                        hero.mana = min(hero.max_mana, hero.mana+hero.max_mana*0.08)
                        relic["timer"], relic["burst"] = RELIC_RESPAWN, 2.0
                        break
        self.units = {uid:u for uid, u in self.units.items() if u.alive or u.kind not in ("minion", "super")}

    def snapshot(self):
        units = []
        for unit in self.units.values():
            data = asdict(unit)
            data.pop("attackers")
            data["vulnerable"] = self.vulnerable(unit)
            units.append(data)
        return dict(time=self.time, winner=self.winner, wave=self.wave, units=units,
                    projectiles=self.projectiles, effects=self.effects, relics=self.relics, feed=self.feed)
