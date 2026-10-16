"""챔피언 스킬 동작.

sim.cast() 가 스킬 data 의 "type" 으로 HANDLERS 에서 핸들러를 골라 부른다.
핸들러는 Cast 를 받아 성공하면 True (마나·재사용 대기시간이 소모됨), 실패하면 False 를 돌려준다.
cx.cooldown 을 정하면 기본 재사용 대기시간 대신 그 값을 쓴다 (재시전이 있는 스킬이 쓴다).

수치는 data/champions/*.json 의 스킬 항목에서 읽는다. 리스트면 스킬 레벨별 값이다.
  피해량:   damage + ad_ratio / bonus_ad_ratio / ap_ratio
  그 밖의 수치(회복·보호막 등):  <키> + <키>_ap × 주문력 + <키>_ad × 공격력
"""
import math
import random

from ..shared import data as gamedata
from ..shared import mapdata
from .entities import Anchor, Champion, Cocoon, GroundEffect, Minion, Projectile, Zone

HANDLERS = {}
ZONE_TICK = {}
ZONE_END = {}


class Cast:
    def __init__(self, sim, c, slot, ab, rank, x, z, ux, uz, d):
        self.sim, self.c, self.slot, self.ab, self.rank = sim, c, slot, ab, rank
        self.x, self.z = x, z           # 마우스가 가리킨 바닥 좌표
        self.ux, self.uz = ux, uz       # 시전자 -> 마우스 방향 (단위 벡터)
        self.d = d                      # 시전자와 마우스 사이 거리
        self.cooldown = None

    def val(self, key, default=0.0):
        return gamedata.rank_value(self.ab, key, self.rank, default)

    def ground_point(self, rng):
        """사거리 안으로 제한한 지정 지점."""
        dist = min(self.d, rng)
        gx, gz = self.c.x + self.ux * dist, self.c.z + self.uz * dist
        return mapdata.clamp_to_map(gx, gz)


def handler(*types):
    def deco(fn):
        for t in types:
            HANDLERS[t] = fn
        return fn
    return deco


def fx(sim, kind, x, z, tm=None, **kw):
    """화면 효과 이벤트. tm = 이 스킬을 쓴 쪽의 팀 (클라이언트가 아군 파랑 / 적 빨강으로 칠하는 데 쓴다)."""
    ev = {"e": "fx", "fx": kind, "x": round(x, 2), "z": round(z, 2)}
    if tm is not None:
        ev["tm"] = tm
    for k, v in kw.items():
        ev[k] = round(v, 2) if isinstance(v, float) else v
    sim.event(**ev)


def can_recast(sim, c, ab):
    """다시 누르면 마나 없이 발동하는 상태인가 (줄 말뚝 복귀, 외줄에서 내려오기)."""
    typ = ab.get("type")
    if typ == "anchor":
        return c.anchor_id in sim.anchors
    if typ == "rope_walk":
        return c.rope is not None
    return False


def interrupt(u):
    """공중에 뜨거나 밀려날 때 하던 동작을 끊는다."""
    if isinstance(u, Champion):
        u.dash = None
        u.clear_orders()
    elif hasattr(u, "windup"):
        u.windup = None


def apply_cc(sim, ab, rank, target):
    """스킬 data 의 slow / stun / airborne / root / silence 를 대상에게 건다."""
    t = sim.time
    rv = gamedata.rank_value
    if ab.get("slow"):
        target.apply_slow(t, rv(ab, "slow", rank), rv(ab, "slow_duration", rank, 1.0))
    if ab.get("stun"):
        target.apply_stun(t, rv(ab, "stun", rank))
    if ab.get("airborne"):
        if target.apply_stun(t, rv(ab, "airborne", rank), airborne=True):
            interrupt(target)
    if ab.get("root"):
        target.apply_root(t, rv(ab, "root", rank))
    if ab.get("silence"):
        target.apply_silence(t, rv(ab, "silence", rank))


def nearest_ally(sim, c, x, z, rng):
    """마우스(x, z) 에서 가장 가까운 아군 챔피언 (자신 포함, 시전 사거리 안)."""
    best, bd = None, 1e9
    for a in sim.champions.values():
        if a.team != c.team or a.dead:
            continue
        if a.dist_to(c) > rng + a.radius:
            continue
        d = math.hypot(a.x - x, a.z - z)
        if d < bd:
            best, bd = a, d
    return best


def rotate(ux, uz, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return ux * ca - uz * sa, ux * sa + uz * ca


# ====================================================================== 공용 타입
@handler("skillshot")
def skillshot(cx):
    """직선 투사체. pierce 면 관통, distance_bonus/distance_full 이면 멀리 날아갈수록 피해 증가."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    p = Projectile(sim.new_id(), c.team, c, c.x + cx.ux * 0.6, c.z + cx.uz * 0.6, ab.get("style", "bolt"), ab["speed"])
    p.dx, p.dz = cx.ux, cx.uz
    p.remaining = ab["range"]
    p.width = ab["width"]
    p.pierce = bool(ab.get("pierce"))
    base = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "physical")
    bonus, full = ab.get("distance_bonus", 0.0), ab.get("distance_full", 1.0)

    def on_hit(sim_, target):
        dmg = base * (1 + bonus * min(1.0, p.traveled / full)) if bonus else base
        sim_.deal_damage(c, target, dmg, dtype, ability=True)
        apply_cc(sim_, ab, cx.rank, target)
    p.on_hit = on_hit
    sim.projectiles[p.id] = p
    return True


@handler("self_buff")
def self_buff(cx):
    sim, c, ab = cx.sim, cx.c, cx.ab
    dur = cx.val("duration")
    c.buffs.append({"until": sim.time + dur, "attack_speed_pct": cx.val("attack_speed_pct"),
                    "move_speed_pct": cx.val("move_speed_pct")})
    if ab.get("pierce"):
        c.pierce_until = sim.time + dur             # 기본 공격이 뒤의 적까지 관통
    c.recompute_stats(sim.time)
    fx(sim, "buff", c.x, c.z, style=ab.get("style", "buff"), tm=c.team)
    return True


@handler("dash")
def dash(cx):
    sim, c, ab = cx.sim, cx.c, cx.ab
    if c.rooted(sim.time):
        return False
    dist = min(cx.d, ab["range"])
    tx, tz = sim.resolve_position(c.x + cx.ux * dist, c.z + cx.uz * dist, c.radius)
    emp = None
    if ab.get("empower_magic"):
        emp = {"dmg": cx.val("empower_magic") + ab.get("empower_ap_ratio", 0) * c.stats["ap"], "dtype": "magic",
               "duration": ab.get("empower_duration", 3.0)}
    elif ab.get("empower_damage"):
        emp = {"dmg": sim.ability_amount(c, ab, cx.rank, "empower_damage"),
               "dtype": ab.get("empower_damage_type", "physical"), "duration": ab.get("empower_duration", 3.0)}
    c.clear_orders()
    c.dash = {"x": tx, "z": tz, "speed": ab["speed"], "follow": None, "empower": emp}
    return True


@handler("ground_aoe")
def ground_aoe(cx):
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "magic")

    def on_trigger(sim_, eff):
        for t in sim_.enemies_in_radius(eff.team, eff.x, eff.z, eff.radius):
            sim_.deal_damage(c, t, dmg, dtype, ability=True)
            apply_cc(sim_, ab, cx.rank, t)
        sim_.event(e="fx", fx=eff.style + "_burst", x=round(eff.x, 2), z=round(eff.z, 2), r=eff.radius, tm=eff.team)
    eff = GroundEffect(sim.new_id(), c.team, c, gx, gz, ab["radius"], sim.time + ab.get("delay", 0.5),
                       ab.get("style", "aoe"), on_trigger)
    sim.effects[eff.id] = eff
    return True


# ====================================================================== 1번: 돌진형 탱커
@handler("self_aoe")
def self_aoe(cx):
    """시전자 주변 원형 범위 피해 (+ 둔화·기절 등)."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    radius = ab["radius"]
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "physical")
    for t in sim.enemies_in_radius(c.team, c.x, c.z, radius):
        sim.deal_damage(c, t, dmg, dtype, ability=True)
        apply_cc(sim, ab, cx.rank, t)
    fx(sim, "slam", c.x, c.z, r=radius, style=ab.get("style", "slam"), tm=c.team)
    return True


@handler("counter_shield")
def counter_shield(cx):
    """duration 동안 받는 피해의 ratio 만큼 보호막이 쌓인다."""
    sim, c = cx.sim, cx.c
    c.counter = {"until": sim.time + cx.val("duration"), "ratio": cx.val("ratio", 0.3),
                 "life": cx.val("shield_life", 3.0)}
    fx(sim, "buff", c.x, c.z, style="counter", tm=c.team)
    return True


@handler("knockback")
def knockback(cx):
    """전방 직사각형 안의 적을 밀어낸다. 벽·구조물에 부딪히면 스턴."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    length, half = ab["range"], ab["width"] / 2
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "physical")
    dist, speed = cx.val("knock_distance", 3.0), cx.val("knock_speed", 14.0)
    for u in sim.enemies_in_radius(c.team, c.x, c.z, length + 1.5):
        rx, rz = u.x - c.x, u.z - c.z
        along = rx * cx.ux + rz * cx.uz
        perp = abs(-rx * cx.uz + rz * cx.ux)
        if not (-0.3 <= along <= length + u.radius and perp <= half + u.radius):
            continue
        sim.deal_damage(c, u, dmg, dtype, ability=True)
        if u.apply_stun(sim.time, dist / speed + 0.05):         # 밀려나는 동안 행동 불가
            interrupt(u)
            u.kb = {"dx": cx.ux, "dz": cx.uz, "left": dist, "speed": speed, "stun": cx.val("wall_stun", 1.0)}
    fx(sim, "knock", c.x, c.z, x2=c.x + cx.ux * length, z2=c.z + cx.uz * length, w=ab["width"], tm=c.team)
    return True


@handler("teleport_strike")
def teleport_strike(cx):
    """지정한 먼 지점으로 순간이동해 착지 주변 적을 공중으로 띄운다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    ox, oz = c.x, c.z
    c.x, c.z = sim.resolve_position(gx, gz, c.radius)
    interrupt(c)
    dmg = sim.ability_damage(c, ab, cx.rank)
    for u in sim.enemies_in_radius(c.team, c.x, c.z, ab["radius"]):
        sim.deal_damage(c, u, dmg, ab.get("damage_type", "physical"), ability=True)
        apply_cc(sim, ab, cx.rank, u)
    fx(sim, "teleport", ox, oz, x2=c.x, z2=c.z, tm=c.team)
    fx(sim, "slam", c.x, c.z, r=ab["radius"], style="land", tm=c.team)
    return True


# ====================================================================== 2번: 근접 브루저
@handler("lifesteal_buff")
def lifesteal_buff(cx):
    sim, c = cx.sim, cx.c
    c.vamp = {"until": sim.time + cx.val("duration"), "pct": cx.val("pct")}
    fx(sim, "buff", c.x, c.z, style="vamp", tm=c.team)
    return True


@handler("ghost_walk")
def ghost_walk(cx):
    """망령 상태: 구조물을 통과하고 이동 속도가 오른다."""
    sim, c = cx.sim, cx.c
    dur = cx.val("duration")
    c.ghost_until = sim.time + dur
    c.buffs.append({"until": sim.time + dur, "move_speed_pct": cx.val("move_speed_pct")})
    c.recompute_stats(sim.time)
    fx(sim, "buff", c.x, c.z, style="ghost", tm=c.team)
    return True


# ====================================================================== 3번: 소리 탱커
@handler("cone")
def cone(cx):
    """전방 부채꼴 피해 + 울림 표식."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    rng = ab["range"]
    half = math.radians(ab["angle"]) / 2
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "magic")
    t = sim.time
    for u in sim.enemies_in_radius(c.team, c.x, c.z, rng):
        rx, rz = u.x - c.x, u.z - c.z
        d = math.hypot(rx, rz)
        if d > 1e-6:
            ang = math.acos(max(-1.0, min(1.0, (rx * cx.ux + rz * cx.uz) / d)))
            if ang > half + math.asin(min(1.0, u.radius / d)):
                continue
        sim.deal_damage(c, u, dmg, dtype, ability=True)
        if ab.get("mark_duration"):
            u.marks["resonance"] = (t + cx.val("mark_duration"), c.id)
        apply_cc(sim, ab, cx.rank, u)
    fx(sim, "cone", c.x, c.z, a=math.atan2(cx.uz, cx.ux), r=rng, w=ab["angle"], tm=c.team)
    return True


@handler("echo_guard")
def echo_guard(cx):
    """duration 동안 받는 피해의 일부를 나눠 받고, 표식이 있는 적 수만큼 방어력 증가."""
    sim, c = cx.sim, cx.c
    c.echo = {"until": sim.time + cx.val("duration"), "pct": cx.val("defer_pct", 0.3),
              "time": cx.val("defer_time", 3.0), "armor_per_mark": cx.val("armor_per_mark")}
    fx(sim, "buff", c.x, c.z, style="echo", tm=c.team)
    return True


@handler("silence_marked")
def silence_marked(cx):
    """울림 표식이 있는 주변 적을 침묵시키고 표식을 모두 지운다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    t = sim.time
    radius = ab["radius"]
    targets = [e for e in sim.champions.values()
               if e.team != c.team and not e.dead and not e.untargetable(t) and e.mark_of("resonance", t, c.id)
               and c.dist_to(e) <= radius + e.radius]
    if not targets:
        return False                                # 표식이 하나도 없으면 시전되지 않는다
    for e in targets:
        e.apply_silence(t, cx.val("silence", 1.0))
    for u in list(sim.champions.values()) + list(sim.minions.values()):
        m = u.marks.get("resonance")
        if m and m[1] == c.id:
            del u.marks["resonance"]
    fx(sim, "silence_ring", c.x, c.z, r=radius, tm=c.team)
    return True


@handler("cage")
def cage(cx):
    """지정 지점에 범종을 떨어뜨려 범위 안의 적 챔피언을 최대 N명까지 가두고, 풀릴 때 피해를 준다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    radius = ab["radius"]
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "magic")
    dur = cx.val("duration")

    def on_trigger(sim_, eff):
        t = sim_.time
        cands = [u for u in sim_.champions.values()
                 if u.team != c.team and not u.dead and not u.untargetable(t) and not sim_.is_caged(u)
                 and math.hypot(u.x - gx, u.z - gz) <= radius + u.radius]
        cands.sort(key=lambda u: math.hypot(u.x - gx, u.z - gz))
        chosen = cands[:int(ab.get("max_targets", 2))]
        fx(sim_, "bell_drop", gx, gz, r=radius, tm=c.team)
        if not chosen:
            return
        z = Zone(sim_.new_id(), "cage", c.team, c, gx, gz, radius, t + dur, ab.get("style", "cage"),
                 data={"ids": [u.id for u in chosen], "dmg": dmg, "dtype": dtype})
        z.born = t
        sim_.zones[z.id] = z
        for u in chosen:
            u.cage_id = z.id
            u.caged_until = z.until
    eff = GroundEffect(sim.new_id(), c.team, c, gx, gz, radius, sim.time + cx.val("delay", 0.8), "bell", on_trigger)
    sim.effects[eff.id] = eff
    return True


def tick_cage(sim, z, dt):
    for uid in z.data["ids"]:
        u = sim.champions.get(uid)
        if u is None or u.dead or u.cage_id != z.id:
            continue
        dx, dz = u.x - z.x, u.z - z.z
        d = math.hypot(dx, dz)
        lim = max(0.3, z.radius - u.radius)
        if d > lim:                                  # 종 밖으로 나갈 수 없다
            u.x, u.z = z.x + dx / d * lim, z.z + dz / d * lim


def end_cage(sim, z):
    for uid in z.data["ids"]:
        u = sim.champions.get(uid)
        if u is None or u.cage_id != z.id:
            continue
        u.caged_until = 0.0
        u.cage_id = None
        if not u.dead:
            sim.deal_damage(z.owner, u, z.data["dmg"], z.data["dtype"], ability=True)
    fx(sim, "cage_end", z.x, z.z, r=z.radius, tm=z.owner.team)


# ====================================================================== 4번: 줄타기 암살자
@handler("hook_dash")
def hook_dash(cx):
    """줄을 던져 맞은 적에게 날아붙는다. 부쉬 안(나온 뒤 잠깐 포함)에서는 사거리가 늘어난다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    t = sim.time
    in_bush = mapdata.bush_at(c.x, c.z) >= 0 or t < c.bush_until
    rng = ab["bush_range"] if in_bush else ab["range"]
    p = Projectile(sim.new_id(), c.team, c, c.x + cx.ux * 0.5, c.z + cx.uz * 0.5, "hook", ab["speed"])
    p.dx, p.dz = cx.ux, cx.uz
    p.remaining = rng
    p.width = ab["width"]
    dmg = sim.ability_damage(c, ab, cx.rank)

    def on_hit(sim_, target):
        sim_.deal_damage(c, target, dmg, "physical", ability=True)
        c.q_hit_until = sim_.time + ab.get("w_window", 2.0)          # 이 안에 W 를 쓰면 즉발
        if not c.dead and not c.rooted(sim_.time) and target.alive:
            c.clear_orders()
            c.dash = {"x": target.x, "z": target.z, "speed": ab.get("dash_speed", 28.0), "follow": target.id,
                      "empower": None}

    def on_miss(sim_, proj):
        refund = ab.get("miss_refund", 0.3) * c.cooldown_of(cx.slot)
        c.ready_at[cx.slot] = max(sim_.time, c.ready_at[cx.slot] - refund)
    p.on_hit, p.on_miss = on_hit, on_miss
    sim.projectiles[p.id] = p
    return True


@handler("knife_throw")
def knife_throw(cx):
    """칼 N자루. 평소엔 간격을 두고 느리게, Q 적중 직후/줄 위에서는 근거리 부채꼴로 즉발."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    instant = sim.time < c.q_hit_until or c.rope is not None
    dmg = sim.ability_damage(c, ab, cx.rank)
    count = int(ab.get("count", 3))

    def launch(sim_, dx, dz, speed, rng, style, width=0.5):
        if c.dead:
            return
        p = Projectile(sim_.new_id(), c.team, c, c.x + dx * 0.5, c.z + dz * 0.5, style, speed)
        p.dx, p.dz = dx, dz
        p.remaining = rng
        p.width = width
        p.on_hit = lambda s_, tg: s_.deal_damage(c, tg, dmg, "physical", ability=True)
        sim_.projectiles[p.id] = p

    if instant:
        fan = math.radians(ab.get("fan_angle", 16))
        for i in range(count):
            ang = 0.0 if count == 1 else -fan + 2 * fan * i / (count - 1)
            dx, dz = rotate(cx.ux, cx.uz, ang)
            launch(sim, dx, dz, ab.get("fast_speed", 40.0), ab.get("fast_range", 4.5), "knife_fast", 0.8)
        c.q_hit_until = 0.0
        fx(sim, "knife_burst", c.x, c.z, a=math.atan2(cx.uz, cx.ux), tm=c.team)
    else:
        interval = ab.get("interval", 0.4)
        for i in range(count):
            args = (cx.ux, cx.uz, ab.get("speed", 11.0), ab.get("range", 8.0), "knife")
            if i == 0:
                launch(sim, *args)
            else:
                sim.schedule(i * interval, lambda s_, a=args: launch(s_, *a))
    return True


def remove_anchor(sim, a, hatch=False):
    if sim.anchors.pop(a.id, None) is None:
        return
    a.alive = False
    if getattr(a, "cocoon", False):                       # 새끼 거미 고치: 시간이 다 되면 부화, 부서지면 그냥 터진다
        if hatch:
            hatch_cocoon(sim, a)
        else:
            fx(sim, "cocoon_break", a.x, a.z, tm=a.owner.team)
        return
    owner = a.owner
    if owner.anchor_id == a.id:
        owner.anchor_id = None
        slot = a.slot
        # 쿨타임은 복귀하거나 말뚝이 사라진 뒤부터 돈다
        owner.ready_at[slot] = max(owner.ready_at[slot], sim.time + owner.cooldown_of(slot))
    fx(sim, "anchor_break", a.x, a.z, tm=owner.team)


def anchor_destroyed(sim, a):
    remove_anchor(sim, a)


@handler("anchor")
def anchor(cx):
    """줄 말뚝 설치. 말뚝이 남아 있을 때 다시 쓰면 말뚝 위치로 즉시 돌아간다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    a = sim.anchors.get(c.anchor_id) if c.anchor_id else None
    if a is not None:
        ox, oz = c.x, c.z
        c.x, c.z = sim.resolve_position(a.x, a.z, c.radius)
        interrupt(c)
        fx(sim, "rope_pull", ox, oz, x2=c.x, z2=c.z, tm=c.team)
        remove_anchor(sim, a)
        return True
    a = Anchor(sim.new_id(), c.team, c, c.x, c.z, sim.time + cx.val("duration"))
    a.slot = cx.slot
    sim.anchors[a.id] = a
    c.anchor_id = a.id
    cx.cooldown = 0.6                       # 재시전까지 잠깐만 막고, 진짜 쿨타임은 말뚝이 사라질 때 시작
    fx(sim, "anchor_set", c.x, c.z, tm=c.team)
    return True


@handler("rope_walk")
def rope_walk(cx):
    """공중에 외줄을 걸고 올라가 걷는다. 줄 위에서는 대상으로 지정되지 않는다. 다시 누르면 내려온다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    if c.rope:
        end_rope(sim, c)
        return True
    length = cx.val("length", 8.0)
    x0, z0 = c.x, c.z
    x1, z1 = mapdata.clamp_to_map(x0 + cx.ux * length, z0 + cx.uz * length, c.radius)
    total = math.hypot(x1 - x0, z1 - z0)
    if total < 1.5:
        return False
    until = sim.time + cx.val("duration")
    c.rope = {"x0": x0, "z0": z0, "x1": x1, "z1": z1, "dx": (x1 - x0) / total, "dz": (z1 - z0) / total,
              "len": total, "s": 0.0, "until": until, "ab": ab, "rank": cx.rank, "slot": cx.slot}
    c.untarget_until = until + 0.05
    interrupt(c)
    cx.cooldown = 0.5                       # 진짜 쿨타임은 내려온 뒤부터
    fx(sim, "rope_up", x0, z0, x2=x1, z2=z1, tm=c.team)
    return True


def update_rope(sim, c, dt):
    r = c.rope
    c.attack_target = None
    c.windup = None
    if sim.time >= r["until"]:
        end_rope(sim, c)
        return
    moving = False
    if c.move_target:
        tx, tz = c.move_target
        s_target = max(0.0, min(r["len"], (tx - r["x0"]) * r["dx"] + (tz - r["z0"]) * r["dz"]))
        ds = s_target - r["s"]
        step = c.stats["move_speed"] * dt
        if abs(ds) <= step:
            r["s"] = s_target
            c.move_target = None
        else:
            r["s"] += step if ds > 0 else -step
            moving = True
        sign = 1.0 if ds >= 0 else -1.0
        c.facing = math.atan2(r["dz"] * sign, r["dx"] * sign)
    c.x = r["x0"] + r["dx"] * r["s"]
    c.z = r["z0"] + r["dz"] * r["s"]
    c.anim = 1 if moving else 0


def end_rope(sim, c, land=True):
    r = c.rope
    if not r:
        return
    c.rope = None
    c.untarget_until = 0.0
    c.move_target = None
    ab, rank = r["ab"], r["rank"]
    c.ready_at[r["slot"]] = sim.time + c.cooldown_of(r["slot"])
    if land and not c.dead:
        dmg = sim.ability_damage(c, ab, rank)
        for u in sim.enemies_in_radius(c.team, c.x, c.z, ab["land_radius"]):
            sim.deal_damage(c, u, dmg, ab.get("damage_type", "physical"), ability=True)
            apply_cc(sim, ab, rank, u)
        fx(sim, "slam", c.x, c.z, r=ab["land_radius"], style="land", tm=c.team)


# ====================================================================== 5번: 원거리 지속딜러
@handler("trap")
def trap(cx):
    """바닥에 덫을 숨겨 둔다 (적에게는 안 보임). 적 챔피언이 밟으면 속박 + 위치 노출."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    mine = [z for z in sim.zones.values() if z.kind == "trap" and z.owner is c]
    mine.sort(key=lambda z: z.born)
    while len(mine) >= int(ab.get("max_traps", 2)):
        sim.end_zone(mine.pop(0))
    t = sim.time
    z = Zone(sim.new_id(), "trap", c.team, c, gx, gz, ab.get("trigger_radius", 1.1), t + ab.get("lifetime", 40.0),
             "trap", hidden=True,
             data={"armed_at": t + ab.get("arm_delay", 0.6), "root": cx.val("root", 1.0),
                   "reveal": cx.val("reveal", 4.0), "dmg": sim.ability_damage(c, ab, cx.rank) if ab.get("damage") else 0.0,
                   "dtype": ab.get("damage_type", "physical")})
    z.born = t
    sim.zones[z.id] = z
    fx(sim, "trap_set", gx, gz, pv=c.team, tm=c.team)          # 숨긴 덫 설치는 아군에게만 알린다
    return True


def tick_trap(sim, z, dt):
    t = sim.time
    if t < z.data["armed_at"]:
        return
    for u in sim.champions.values():
        if u.team == z.team or u.dead or u.untargetable(t):
            continue
        if math.hypot(u.x - z.x, u.z - z.z) <= z.radius + u.radius:
            u.apply_root(t, z.data["root"])
            u.revealed_until = max(u.revealed_until, t + z.data["reveal"])
            if z.data["dmg"] > 0:
                sim.deal_damage(z.owner, u, z.data["dmg"], z.data["dtype"], ability=True)
            fx(sim, "trap_snap", z.x, z.z, tm=z.owner.team)
            sim.end_zone(z)
            return


# ====================================================================== 6번·7번: 힐러
def _pick(cx, rng):
    return nearest_ally(cx.sim, cx.c, cx.x, cx.z, rng)


@handler("ally_heal")
def ally_heal(cx):
    sim, c, ab = cx.sim, cx.c, cx.ab
    tg = _pick(cx, ab["range"])
    if tg is None:
        return False
    sim.heal(tg, sim.ability_amount(c, ab, cx.rank, "heal"), c)
    fx(sim, "heal", tg.x, tg.z, tm=c.team)
    return True


@handler("cleanse")
def cleanse(cx):
    """아군 한 명의 군중 제어를 풀고 잠깐 면역을 준다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    tg = _pick(cx, ab["range"])
    if tg is None:
        return False
    tg.cleanse(sim.time)
    tg.cc_immune_until = sim.time + cx.val("immune", 1.0)
    fx(sim, "cleanse", tg.x, tg.z, tm=c.team)
    return True


@handler("team_heal")
def team_heal(cx):
    """주변 모든 아군을 크게 회복시키고 잠깐 죽지 않게 한다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    amt = sim.ability_amount(c, ab, cx.rank, "heal")
    undying = cx.val("undying", 0.0)
    for a in sim.allies_in_radius(c.team, c.x, c.z, ab["radius"]):
        sim.heal(a, amt, c)
        if undying:
            a.undying_until = max(a.undying_until, sim.time + undying)
    fx(sim, "holy", c.x, c.z, r=ab["radius"], tm=c.team)
    return True


@handler("zone")
def zone(cx):
    """바닥에 장판을 깐다: 안의 아군은 지속 회복, 안의 적은 둔화 (+ 처음에 속박)."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    spawn_zone(sim, c, ab, cx.rank, gx, gz)
    return True


def spawn_zone(sim, c, ab, rank, gx, gz):
    """(gx, gz) 에 장판을 만든다 (ab 의 radius / duration / slow / heal_per_sec / damage_per_sec ...). 점프 내려찍기도 이걸 쓴다."""
    radius = ab["radius"]
    rv = gamedata.rank_value
    dur = rv(ab, "duration", rank)
    data = {"slow": rv(ab, "slow", rank), "heal_ps": sim.ability_amount(c, ab, rank, "heal_per_sec"),
            "acc": {}, "next_ev": 0.0,
            "dps": sim.ability_amount(c, ab, rank, "damage_per_sec"), "dtype": ab.get("damage_type", "magic"),
            "dps_next": 0.0}
    root = rv(ab, "root", rank)
    style = ab.get("style", "zone")

    def spawn(sim_, eff=None):
        t = sim_.time
        z = Zone(sim_.new_id(), "aura", c.team, c, gx, gz, radius, t + dur, style, data=data)
        z.born = t
        sim_.zones[z.id] = z
        if root:
            for u in sim_.enemies_in_radius(c.team, gx, gz, radius):
                u.apply_root(t, root)
        fx(sim_, "zone_start", gx, gz, r=radius, style=style, tm=c.team)
    delay = ab.get("delay", 0.0)
    if delay > 0:
        eff = GroundEffect(sim.new_id(), c.team, c, gx, gz, radius, sim.time + delay, style, lambda s_, e: spawn(s_))
        sim.effects[eff.id] = eff
    else:
        spawn(sim)


def tick_aura(sim, z, dt):
    t = sim.time
    d = z.data
    owner = z.owner
    if d["heal_ps"] > 0:
        for a in sim.allies_in_radius(z.team, z.x, z.z, z.radius):
            gained = sim.heal(a, d["heal_ps"] * dt, owner, quiet=True)
            d["acc"][a.id] = d["acc"].get(a.id, 0.0) + gained
    if d["slow"]:
        for u in sim.enemies_in_radius(z.team, z.x, z.z, z.radius):
            u.apply_slow(t, d["slow"], 0.4)
    if d.get("dps") and t >= d["dps_next"]:                 # 장판 위의 적에게 0.5초마다 피해 (독 거미줄)
        d["dps_next"] = t + 0.5
        for u in sim.enemies_in_radius(z.team, z.x, z.z, z.radius):
            sim.deal_damage(owner, u, d["dps"] * 0.5, d["dtype"], ability=True)
    if t >= d["next_ev"]:                                   # 회복량 숫자는 1초에 한 번만 보여 준다
        d["next_ev"] = t + 1.0
        for uid, amt in d["acc"].items():
            if amt >= 1.0:
                sim.event(e="heal", d=uid, v=int(round(amt)))
        d["acc"] = {}


@handler("line_aoe")
def line_aoe(cx):
    """전방 직선(덩굴): 적은 피해+둔화, 아군은 회복."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    length, half = ab["range"], ab["width"] / 2
    dmg = sim.ability_damage(c, ab, cx.rank)
    heal = sim.ability_amount(c, ab, cx.rank, "heal")

    def inside(u):
        rx, rz = u.x - c.x, u.z - c.z
        along = rx * cx.ux + rz * cx.uz
        perp = abs(-rx * cx.uz + rz * cx.ux)
        return 0.0 <= along <= length + u.radius and perp <= half + u.radius
    for u in sim.enemies_in_radius(c.team, c.x, c.z, length + 1.0):
        if inside(u):
            sim.deal_damage(c, u, dmg, ab.get("damage_type", "magic"), ability=True)
            apply_cc(sim, ab, cx.rank, u)
    if heal > 0:
        for a in sim.allies_in_radius(c.team, c.x, c.z, length + 1.0):
            if a is not c and inside(a):
                sim.heal(a, heal, c)
    fx(sim, "vine", c.x, c.z, x2=c.x + cx.ux * length, z2=c.z + cx.uz * length, w=ab["width"], tm=c.team)
    return True


@handler("ally_shield")
def ally_shield(cx):
    """아군에게 꽃잎 보호막. 보호막이 깨지면 주변 적에게 피해."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    tg = _pick(cx, ab["range"])
    if tg is None:
        return False
    burst = sim.ability_amount(c, ab, cx.rank, "burst_damage")
    radius = ab.get("burst_radius", 3.0)

    def on_break(sim_, unit):
        for u in sim_.enemies_in_radius(c.team, unit.x, unit.z, radius):
            sim_.deal_damage(c, u, burst, ab.get("damage_type", "magic"), ability=True)
        fx(sim_, "petal_burst", unit.x, unit.z, r=radius, tm=c.team)
    if not sim.add_shield(tg, sim.ability_amount(c, ab, cx.rank, "shield"), cx.val("duration"), c,
                          on_break if burst > 0 else None):
        return False
    fx(sim, "shield", tg.x, tg.z, tm=c.team)
    return True


@handler("ally_buff")
def ally_buff(cx):
    sim, c, ab = cx.sim, cx.c, cx.ab
    tg = _pick(cx, ab["range"])
    if tg is None:
        return False
    tg.buffs.append({"until": sim.time + cx.val("duration"), "attack_speed_pct": cx.val("attack_speed_pct"),
                     "move_speed_pct": cx.val("move_speed_pct")})
    tg.recompute_stats(sim.time)
    fx(sim, "wind", tg.x, tg.z, tm=c.team)
    return True


# ====================================================================== 8번: 동굴 여왕 거미 (보스러시 이식)
@handler("volley")
def volley(cx):
    """부채꼴로 여러 발을 동시에 쏜다 (독침 탄막). 한 발씩 따로 명중한다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    n = max(1, int(ab.get("count", 5)))
    spread = math.radians(ab.get("spread", 55))
    dmg = sim.ability_damage(c, ab, cx.rank)
    dtype = ab.get("damage_type", "magic")
    for j in range(n):
        ang = (j / (n - 1) - 0.5) * spread if n > 1 else 0.0
        ux, uz = rotate(cx.ux, cx.uz, ang)
        p = Projectile(sim.new_id(), c.team, c, c.x + ux * 0.7, c.z + uz * 0.7, ab.get("style", "spine"), ab["speed"])
        p.dx, p.dz = ux, uz
        p.remaining = ab["range"] - 0.7                      # 시전자 중심에서 range 까지 (표시 범위와 같다)
        p.width = ab["width"]
        p.pierce = False

        def on_hit(sim_, target, dmg=dmg):
            sim_.deal_damage(c, target, dmg, dtype, ability=True)
            apply_cc(sim_, ab, cx.rank, target)
        p.on_hit = on_hit
        sim.projectiles[p.id] = p
    fx(sim, "volley", c.x, c.z, a=math.atan2(cx.uz, cx.ux), w=ab.get("spread", 55), style=ab.get("style", "spine"), tm=c.team)
    return True


@handler("leap_slam")
def leap_slam(cx):
    """도약해 내리꽂는다. 대상 지정형("aim": "enemy")이면 마우스에 가장 가까운 적 챔피언에게 뛰어들어 스턴을 걸고
    그 자리에 장판("zone")을 깐다 (거미 여왕 R). 아니면 지정한 지점으로 도약 (피해 + 둔화)."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    if c.rooted(sim.time):
        return False
    ox, oz = c.x, c.z
    land = {"ab": ab, "rank": cx.rank, "dmg": sim.ability_damage(c, ab, cx.rank), "target": None}
    follow = None
    if ab.get("aim") == "enemy":
        tg = sim.pick_enemy_champion(c, cx.x, cx.z, ab["range"])
        if tg is None:
            return False
        follow = tg.id
        land["target"] = tg.id
        tx, tz = tg.x, tg.z
    else:
        dist = min(cx.d, ab["range"])
        tx, tz = sim.resolve_position(c.x + cx.ux * dist, c.z + cx.uz * dist, c.radius)
    flight = ab.get("flight") or max(0.15, math.hypot(tx - c.x, tz - c.z) / ab["speed"])    # 공중에 떠 있는 시간
    windup = ab.get("windup", 0.0)                                                          # 웅크렸다가 뛰기까지
    c.clear_orders()
    c.dash = {"x": tx, "z": tz, "speed": ab.get("speed", 22.0), "follow": follow, "empower": None, "land": land,
              "flight": flight if ab.get("flight") else None, "delay": windup}
    fx(sim, "leap", ox, oz, x2=tx, z2=tz, dur=flight, delay=windup, d=c.id, tm=c.team, tg=follow,
       r=ab.get("radius", 0.0), zr=(ab.get("zone") or {}).get("radius", 0.0))
    return True


def land_slam(sim, c, land):
    """leap_slam 의 착지: 반경 안의 적에게 피해와 둔화, 지정한 대상은 스턴, 그 자리에 장판."""
    ab = land["ab"]
    rank = land["rank"]
    for u in sim.enemies_in_radius(c.team, c.x, c.z, ab["radius"]):
        sim.deal_damage(c, u, land["dmg"], ab.get("damage_type", "physical"), ability=True)
        apply_cc(sim, ab, rank, u)
    tg = sim.unit(land["target"]) if land.get("target") else None
    if tg is not None and tg.alive and not getattr(tg, "dead", False):
        if tg.apply_stun(sim.time, gamedata.rank_value(ab, "stun", rank, 1.2)):
            interrupt(tg)
    if land.get("dive") or land.get("sky"):
        c.untarget_until = 0.0
    if land.get("dive"):
        fx(sim, "dive_out", c.x, c.z, r=ab["radius"], d=c.id, tm=c.team)
    fx(sim, "slam", c.x, c.z, r=ab["radius"], style=ab.get("style", "pounce"), tm=c.team)
    if ab.get("zone"):
        spawn_zone(sim, c, ab["zone"], rank, c.x, c.z)


# ====================================================================== 거미 여왕 E: 새끼 거미 고치
@handler("cocoon")
def cocoon(cx):
    """지정한 곳에 시전자→마우스 선과 수직(T자)으로 고치 여러 개를 놓는다. 시간이 지나면 고치마다 새끼 거미가 부화한다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    n = max(1, int(ab.get("count", 3)))
    gap = ab.get("spacing", 1.7)
    hatch = cx.val("hatch", 6.5)
    mine = sorted((a for a in sim.anchors.values() if getattr(a, "cocoon", False) and a.owner is c), key=lambda a: a.until)
    while len(mine) + n > int(ab.get("max_cocoons", 6)) and mine:
        remove_anchor(sim, mine.pop(0))                        # 너무 많으면 가장 오래된 것부터 터뜨린다
    baby = {"hp": cx.val("baby_hp", 80.0), "speed": ab.get("baby_speed", 5.4),
            "dmg": cx.val("baby_ad", 10.0) + cx.val("baby_ad_ratio", 0.1) * c.stats["ad"],      # 평타 한 대의 피해 (물리)
            "proj_speed": c.data["stats"].get("projectile_speed", 20), "max_babies": ab.get("max_babies", 12), "ab": ab, "rank": cx.rank}
    px, pz = -cx.uz, cx.ux                                     # 시전 방향에 수직인 방향
    for k in range(n):
        off = (k - (n - 1) / 2) * gap
        x, z = mapdata.clamp_to_map(gx + px * off, gz + pz * off)
        a = Cocoon(sim.new_id(), c.team, c, x, z, sim.time + hatch, hp=cx.val("cocoon_hp", 100.0))
        a.born = sim.time
        a.baby = baby
        sim.anchors[a.id] = a
        fx(sim, "cocoon_set", x, z, tm=c.team, hatch=hatch)
    return True


def hatch_cocoon(sim, a):
    """고치가 부화: 새끼 거미 한 마리가 튀어나온다."""
    c, b = a.owner, a.baby
    m = Minion(sim.new_id(), c.team, a.x, a.z, "spiderling", 0.0)
    m.max_hp = m.hp = b["hp"]
    m.owner = c
    m.baby = b
    m.move_speed = b["speed"]
    m.attack_speed = b.get("attack_speed", m.attack_speed)
    m.facing = c.facing
    sim.minions[m.id] = m
    kids = sorted((e for e in sim.minions.values() if e.mtype == "spiderling" and e.owner is c), key=lambda e: e.id)
    while len(kids) > int(b.get("max_babies", 12)):          # 새끼 거미가 너무 많이 쌓이면 가장 오래된 것부터 정리
        o = kids.pop(0)
        sim.minions.pop(o.id, None)
        sim.gone_minions.append(o.id)
        o.alive = False
    fx(sim, "cocoon_hatch", a.x, a.z, tm=c.team)


ZONE_TICK.update({"aura": tick_aura, "trap": tick_trap, "cage": tick_cage})
ZONE_END.update({"cage": end_cage})


# ====================================================================== 이무기 (보스러시 2층 보스에서 옮김)
@handler("spit_pool")
def spit_pool(cx):
    """Q 독 뱉기 / 화염 뱉기: 덩어리를 포물선으로 뱉어 착지한 자리에 웅덩이(장판)를 남긴다. style 이 모양을 정한다 (venom 독 / fire 불)."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    gx, gz = cx.ground_point(ab["range"])
    flight = ab.get("flight", 0.7)
    windup = ab.get("windup", 0.0)                      # 머리를 쳐들었다가 뱉기까지 (그동안 입에서 아직 안 나간다)
    style = ab.get("style", "venom")

    def launch(sim_):
        fx(sim_, "spit", c.x, c.z, x2=gx, z2=gz, dur=flight, d=c.id, style=style, tm=c.team)
    if windup > 0:
        sim.schedule(windup, launch)
    else:
        launch(sim)
    spawn_zone(sim, c, dict(ab, delay=windup + flight), cx.rank, gx, gz)
    land_dmg = sim.ability_damage(c, ab, cx.rank)
    r = ab["radius"]

    def land(sim_, rank=cx.rank):
        for u in sim_.enemies_in_radius(c.team, gx, gz, r):
            sim_.deal_damage(c, u, land_dmg, ab.get("damage_type", "magic"), ability=True)
        fx(sim_, "spit_land", gx, gz, r=r, style=style, tm=c.team)
    sim.schedule(windup + flight, land)
    return True


@handler("lunge")
def lunge(cx):
    """W 일직선 돌진: 잠깐 몸을 쳐들고 노려본 뒤(예고선) 쏜살같이 일직선으로 달려들며 지나는 길의 적을 물어뜯는다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    if c.rooted(sim.time):
        return False
    dist = ab["range"]
    tx, tz = sim.resolve_position(c.x + cx.ux * dist, c.z + cx.uz * dist, c.radius)
    windup = ab.get("windup", 0.4)
    c.clear_orders()
    sweep = {"ab": ab, "rank": cx.rank, "dmg": sim.ability_damage(c, ab, cx.rank), "half": ab.get("width", 1.6) / 2, "hit": set()}
    c.dash = {"x": tx, "z": tz, "speed": ab["speed"], "follow": None, "empower": None, "delay": windup, "sweep": sweep}
    fx(sim, "lunge", c.x, c.z, x2=tx, z2=tz, delay=windup, dur=math.hypot(tx - c.x, tz - c.z) / ab["speed"], w=ab.get("width", 1.6),
       d=c.id, tm=c.team)
    return True


def sweep_hit(sim, c, sw, ox, oz):
    """돌진하는 머리가 (ox,oz)->현재 위치로 지나간 길에 닿은 적을 한 번씩 물어뜯는다."""
    ab = sw["ab"]
    mx, mz = (ox + c.x) / 2, (oz + c.z) / 2
    reach = math.hypot(c.x - ox, c.z - oz) / 2 + sw["half"] + 1.0
    inner_hit = sw.setdefault("inner_hit", set())
    for u in sim.enemies_in_radius(c.team, mx, mz, reach):
        inner_done = not sw.get("inner") or u.id in inner_hit
        if u.id in sw["hit"] and inner_done:
            continue
        # 선분 (o -> c) 과 u 사이 거리
        vx, vz = c.x - ox, c.z - oz
        ll = vx * vx + vz * vz
        k = 0.0 if ll < 1e-9 else max(0.0, min(1.0, ((u.x - ox) * vx + (u.z - oz) * vz) / ll))
        dd = math.hypot(u.x - (ox + vx * k), u.z - (oz + vz * k))
        if dd > sw["half"] + u.radius:
            continue
        if u.id not in sw["hit"]:                                      # 바깥 바에 처음 닿으면 기본 피해
            sw["hit"].add(u.id)
            sim.deal_damage(c, u, sw["dmg"], ab.get("damage_type", "physical"), ability=True)
            apply_cc(sim, ab, sw["rank"], u)
            fx(sim, sw.get("fx", "bite"), u.x, u.z, tm=c.team)
        if sw.get("inner") and u.id not in inner_hit and dd <= sw["inner"] + u.radius:     # 안쪽 바에 들어오면 나머지 피해 (합쳐서 mult 배)
            inner_hit.add(u.id)
            sim.deal_damage(c, u, sw["dmg"] * (sw.get("mult", 2.0) - 1.0), ab.get("damage_type", "physical"), ability=True)


@handler("serpent_slam")
def serpent_slam(cx):
    """E 내려찍기: 머리를 높이 쳐들었다가(예고 원) 한가운데로 내리꽂는다. 충격파 고리가 바깥으로 퍼지며 맞은 적을 늦춘다.
    대상 지정형("aim": "enemy")이면 마우스에 가장 가까운 적 챔피언을 노리고, 쳐든 동안 대상이 움직이면 예고 원도 따라간다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    follow = None
    if ab.get("aim") == "enemy":
        tg = sim.pick_enemy_champion(c, cx.x, cx.z, ab["range"])
        if tg is None:
            return False
        follow = tg.id
        gx, gz = tg.x, tg.z
    else:
        gx, gz = cx.ground_point(ab["range"])
    r = ab["radius"]
    wr = ab.get("wave_radius", r * 2.0)
    delay = ab.get("delay", 0.75)
    dmg = sim.ability_damage(c, ab, cx.rank)
    wdmg = dmg * ab.get("wave_ratio", 0.5)
    dtype = ab.get("damage_type", "physical")
    hit = set()

    def strike(sim_, eff):
        gx, gz = eff.x, eff.z
        for u in sim_.enemies_in_radius(c.team, eff.x, eff.z, r):
            hit.add(u.id)
            sim_.deal_damage(c, u, dmg, dtype, ability=True)
            apply_cc(sim_, ab, cx.rank, u)
        fx(sim_, "slam", eff.x, eff.z, r=r, style="serpent", tm=c.team)

        steps = 4
        for i in range(1, steps + 1):
            def wave(s2, i=i):
                inner, outer = r + (wr - r) * (i - 1) / steps, r + (wr - r) * i / steps
                for u in s2.enemies_in_radius(c.team, gx, gz, outer + 0.4):
                    d = math.hypot(u.x - gx, u.z - gz)
                    if u.id in hit or d < inner - u.radius or d > outer + u.radius:
                        continue
                    hit.add(u.id)
                    s2.deal_damage(c, u, wdmg, dtype, ability=True)
                    u.apply_slow(s2.time, ab.get("wave_slow", 0.4), ab.get("wave_slow_duration", 1.2))
            sim.schedule(ab.get("wave_delay", 0.14) * i, wave)
        fx(sim_, "shockwave", eff.x, eff.z, r=r, r2=wr, dur=ab.get("wave_delay", 0.14) * steps, tm=c.team)
    eff = GroundEffect(sim.new_id(), c.team, c, gx, gz, r, sim.time + delay, "serpent", strike)
    eff.follow = follow
    sim.effects[eff.id] = eff
    c.clear_orders()
    c.lock_until = sim.time + delay                    # 머리를 쳐들었다 내리꽂는 동안은 움직이거나 다른 행동을 할 수 없다
    fx(sim, "serpent_rear", c.x, c.z, d=c.id, dur=delay, x2=gx, z2=gz, tm=c.team, tg=follow)
    return True


@handler("dive")
def dive(cx):
    """R 잠행: 머리부터 땅속으로 가라앉아(그동안 맞힐 수 없다) 땅속을 헤엄쳐 지정한 곳에서 솟구쳐 주변 적을 띄운다."""
    sim, c, ab = cx.sim, cx.c, cx.ab
    if c.rooted(sim.time):
        return False
    gx, gz = cx.ground_point(ab["range"])
    gx, gz = sim.resolve_position(gx, gz, c.radius)
    sink = ab.get("sink", 0.6)
    travel = max(0.25, min(ab.get("travel_max", 0.9), math.hypot(gx - c.x, gz - c.z) / ab.get("speed", 20.0)))
    c.clear_orders()
    interrupt(c)
    c.untarget_until = sim.time + sink + travel + 0.05
    land = {"ab": ab, "rank": cx.rank, "dmg": sim.ability_damage(c, ab, cx.rank), "target": None, "dive": True}
    c.dash = {"x": gx, "z": gz, "speed": ab.get("speed", 20.0), "follow": None, "empower": None, "land": land,
              "flight": travel, "delay": sink}
    fx(sim, "dive", c.x, c.z, x2=gx, z2=gz, sink=sink, dur=travel, d=c.id, r=ab["radius"], tm=c.team)
    return True


# ====================================================================== 용 (보스러시 3층 보스에서 옮김)
def knock_away(sim, c, ab, rank, u, dx, dz, default_dist=2.0):
    """u 를 (dx, dz) 방향(단위 벡터)으로 밀어낸다. 밀리는 동안 행동 불가, 벽에 부딪히면 wall_stun 만큼 기절."""
    dist = gamedata.rank_value(ab, "knock_distance", rank, default_dist)
    speed = gamedata.rank_value(ab, "knock_speed", rank, 14.0)
    if dist <= 0:
        return
    if u.apply_stun(sim.time, dist / speed + 0.05):
        interrupt(u)
        u.kb = {"dx": dx, "dz": dz, "left": dist, "speed": speed, "stun": gamedata.rank_value(ab, "wall_stun", rank, 0.8)}


@handler("tornado")
def tornado(cx):
    """W 날개 바람 + 회오리: 날개를 치켜들었다가 휘두르는 순간(delay),
    ① 전방 부채꼴(cone_range, angle)의 적은 피해 + 둔화 + 밀려나고, ② 한가운데로는 회오리 투사체가 굴러가며 닿는 적을 공중에 띄운다(에어본)."""
    sim, c, ab, rank = cx.sim, cx.c, cx.ab, cx.rank
    delay = ab.get("delay", 0.35)
    ux, uz = cx.ux, cx.uz
    dmg = sim.ability_damage(c, ab, rank)
    dtype = ab.get("damage_type", "magic")
    cone_r = ab.get("cone_range", 6.5)
    half = math.radians(ab.get("angle", 100)) / 2
    cone_dmg = sim.ability_amount(c, ab, rank, "cone_damage")
    fx(sim, "gust_wind", c.x, c.z, a=math.atan2(uz, ux), r=cone_r, w=ab.get("angle", 100), delay=delay, d=c.id, tm=c.team)

    def launch(sim_):
        if c.dead or c.stunned(sim_.time):                      # 준비하는 동안 쓰러지거나 기절하면 불발
            return
        for u in sim_.enemies_in_radius(c.team, c.x, c.z, cone_r):      # ① 부채꼴 바람
            rx, rz = u.x - c.x, u.z - c.z
            d = math.hypot(rx, rz)
            if d > 1e-6:
                ang = math.acos(max(-1.0, min(1.0, (rx * ux + rz * uz) / d)))
                if ang > half + math.asin(min(1.0, u.radius / d)):
                    continue
            sim_.deal_damage(c, u, cone_dmg, dtype, ability=True)
            u.apply_slow(sim_.time, gamedata.rank_value(ab, "slow", rank), gamedata.rank_value(ab, "slow_duration", rank, 1.0))
            nx, nz = (rx / d, rz / d) if d > 1e-6 else (ux, uz)
            knock_away(sim_, c, ab, rank, u, nx, nz, 2.0)
        fx(sim_, "gust", c.x, c.z, a=math.atan2(uz, ux), r=cone_r, w=ab.get("angle", 100), tm=c.team)
        p = Projectile(sim_.new_id(), c.team, c, c.x + ux * 1.2, c.z + uz * 1.2, ab.get("style", "tornado"), ab["speed"])    # ② 회오리
        p.dx, p.dz = ux, uz
        p.remaining = ab["range"]
        p.width = ab["width"]
        p.pierce = True

        def on_hit(s_, target):
            s_.deal_damage(c, target, dmg, dtype, ability=True)
            if target.apply_stun(s_.time, gamedata.rank_value(ab, "airborne", rank, 0.9), airborne=True):
                interrupt(target)
            target.apply_slow(s_.time, gamedata.rank_value(ab, "slow", rank), gamedata.rank_value(ab, "slow_duration", rank, 1.0))
        p.on_hit = on_hit
        sim_.projectiles[p.id] = p
    sim.schedule(delay, launch)
    return True


@handler("wing_sweep")
def wing_sweep(cx):
    """E 날개 후려치기: 날개를 뒤로 젖혔다가(delay) 몸 둘레를 크게 후려친다. 맞은 적은 피해 + 둔화 + 바깥으로 밀려난다."""
    sim, c, ab, rank = cx.sim, cx.c, cx.ab, cx.rank
    R = ab["radius"]
    delay = ab.get("delay", 0.45)
    dmg = sim.ability_damage(c, ab, rank)
    dtype = ab.get("damage_type", "physical")
    fx(sim, "wing_wind", c.x, c.z, r=R, delay=delay, d=c.id, tm=c.team)

    def strike(sim_):
        if c.dead or c.stunned(sim_.time):
            return
        for u in sim_.enemies_in_radius(c.team, c.x, c.z, R):
            sim_.deal_damage(c, u, dmg, dtype, ability=True)
            apply_cc(sim_, ab, rank, u)
            rx, rz = u.x - c.x, u.z - c.z
            d = math.hypot(rx, rz)
            knock_away(sim_, c, ab, rank, u, *((rx / d, rz / d) if d > 1e-6 else (cx.ux, cx.uz)), 1.8)
        fx(sim_, "slam", c.x, c.z, r=R, style="wing", tm=c.team)
    sim.schedule(delay, strike)
    return True


@handler("sky_dive")
def sky_dive(cx):
    """R 불꽃 비행: 하늘 높이 떠오른 뒤(rise 동안 대상 지정 불가) 지정한 곳으로 수평으로 날아가며 입에서 아래로 불을 쏟고,
    도착하면 내려앉는다. 지나는 길은 바깥 바(path_width)에 닿으면 불길 피해, 안쪽 바(inner_width)에 있으면 inner_mult 배 피해, 착지 지점은 큰 피해 + 둔화 + 불길 웅덩이."""
    sim, c, ab, rank = cx.sim, cx.c, cx.ab, cx.rank
    if c.rooted(sim.time):
        return False
    gx, gz = cx.ground_point(ab["range"])
    gx, gz = sim.resolve_position(gx, gz, c.radius)
    dist = math.hypot(gx - c.x, gz - c.z)
    rise = ab.get("rise", 1.0)
    flight = max(ab.get("min_flight", 0.7), dist / ab.get("speed", 10.0))
    c.clear_orders()
    interrupt(c)
    c.untarget_until = sim.time + rise + flight + 0.05
    sweep = {"ab": ab, "rank": rank, "dmg": sim.ability_amount(c, ab, rank, "path_damage"), "half": ab.get("path_width", 5.0) / 2,
             "inner": ab.get("inner_width", 3.0) / 2, "mult": ab.get("inner_mult", 2.0), "hit": set(), "fx": "burn"}
    land = {"ab": ab, "rank": rank, "dmg": sim.ability_damage(c, ab, rank), "target": None, "sky": True}
    c.dash = {"x": gx, "z": gz, "speed": 20.0, "follow": None, "empower": None, "land": land, "sweep": sweep,
              "delay": rise, "flight": flight}
    fx(sim, "sky_dive", c.x, c.z, x2=gx, z2=gz, rise=rise, dur=round(flight, 3), h=ab.get("height", 6.5), r=ab["radius"],
       w=ab.get("path_width", 5.0), w2=ab.get("inner_width", 3.0), zr=ab.get("zone", {}).get("radius", 0.0), d=c.id, tm=c.team)
    return True
