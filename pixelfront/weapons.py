"""Every weapon in the game, and how weapons work, in one place.

Weapons come in three types:

- bullet      Instant-hit rounds (drawn as tracers). Every round pins down the soldier it's
              aimed at, hit or miss.
- explosive   Projectiles that burst over an area: splash damage, and they pin down every
              soldier near the blast.
- anti_armor  Rockets and penetrators: big hits, extra damage against vehicles, only a small
              blast.

WEAPON_TYPES holds each type's defaults; WEAPONS holds each weapon's numbers and overrides;
ARMOR_RANKS says how much each rank of armour shrugs off of each weapon type.
To add a weapon: add an entry to WEAPONS, point a unit's `weapons` at it (units/*.py), and
give it a look in model3d (models pick their weapon visuals by weapon id).
"""
import math

from .config import (BURST_GAP, SUPPRESS_PER_SHOT, SUPPRESS_EXPLOSIVE, SUPPRESS_RADIUS, PRONE_ACCURACY,
                     PRONE_TARGET_HIT)
from .entities import dist_point_rect

# vs = damage multiplier against each target class (see target_class()): bullets barely
# scratch tanks and buildings and do moderate damage to jeeps; explosives wreck tanks and
# buildings.
WEAPON_TYPES = {
    "bullet": dict(vs_vehicle=1.0, pin_per_round=True, blast_pin=0, blast_radius=0,
                   vs=dict(infantry=1.0, light_vehicle=0.8, heavy_vehicle=0.2, building=0.2),
                   desc="Instant-hit rounds that pin down whoever they're aimed at."),
    "explosive": dict(vs_vehicle=1.0, pin_per_round=False, blast_pin=SUPPRESS_EXPLOSIVE,
                      blast_radius=SUPPRESS_RADIUS,
                      vs=dict(infantry=1.0, light_vehicle=1.0, heavy_vehicle=1.25, building=1.25),
                      desc="Bursts over an area: splash damage, and pins down infantry near the blast."),
    "anti_armor": dict(vs_vehicle=1.75, pin_per_round=False, blast_pin=SUPPRESS_EXPLOSIVE // 2,
                       blast_radius=10,
                       vs=dict(infantry=1.0, light_vehicle=1.0, heavy_vehicle=1.0, building=1.0),
                       desc="Built to kill vehicles: heavy hits, small blast."),
}

# Armour ranks: what fraction of each weapon type's damage gets through (before the unit's flat
# armour value is taken off). A unit's rank is its Armor tier, plus `armor_rank` from its unit
# file for units that always wear more (heavy infantry). The ballistic shield is far better
# against bullets and blast fragments than body armour alone.
ARMOR_RANKS = {
    "infantry": [
        dict(name="Unarmoured", bullet=1.0, explosive=1.0, anti_armor=1.0),
        dict(name="Helmet + vest", bullet=0.85, explosive=0.85, anti_armor=1.0),
        dict(name="Full body", bullet=0.7, explosive=0.75, anti_armor=0.95),
        dict(name="Full body + shield", bullet=0.45, explosive=0.55, anti_armor=0.9),
    ],
    "vehicle": [
        dict(name="Light plating", bullet=0.85, explosive=0.9, anti_armor=1.0),
        dict(name="Medium plating", bullet=0.7, explosive=0.8, anti_armor=1.0),
        dict(name="Heavy plating", bullet=0.55, explosive=0.7, anti_armor=0.9),
    ],
}


def armor_rank(cls, rank):
    """The ARMOR_RANKS entry for a unit class ("infantry" / "vehicle") and rank (clamped)."""
    ranks = ARMOR_RANKS[cls]
    return ranks[max(0, min(len(ranks) - 1, rank))]


def target_class(target):
    """infantry / light_vehicle / heavy_vehicle / building: what WEAPON_TYPES[...]["vs"] keys on."""
    if target.is_building:
        return "building"
    return target.target_class


def effectiveness(target, wtype, vs=None):
    """Fraction of a `wtype` hit that gets through: the type (or the weapon's own `vs`) against
    this class of target, then the target's armour rank (units only)."""
    if wtype is None:
        return 1.0
    f = (vs or WEAPON_TYPES[wtype]["vs"])[target_class(target)]
    if target.is_unit:
        f *= armor_rank("vehicle" if target.is_vehicle else "infantry", target.armor_rank)[wtype]
        if (wtype == "explosive" and target.is_infantry and target.suppressed
                and target.armor_rank >= 1):
            f *= PRONE_ARMORED_BLAST
    return f


def _hit(game, target, amount, source, wtype, vs=None):
    game.damage(target, amount * effectiveness(target, wtype, vs), source)


# Armoured infantry lying prone take only this much from explosives: flat on the ground, the
# plating soaks up the blast and fragments. (Unarmoured soldiers get no such benefit.)
PRONE_ARMORED_BLAST = 0.6


# How a projectile flies and looks. speed in px/s; arc = peak height in px (0 = flies straight
# and homes in on its target; arcing rounds are lobbed at the spot the target stood on);
# boom = size of the explosion drawn; trail = what it leaves behind; homing = an arcing round
# that still steers onto its target.
PROJECTILE_STYLES = {
    "rocket":     dict(speed=150, arc=0, boom=5, trail="smoke"),
    "atgm":       dict(speed=130, arc=0, boom=6, trail="wire"),
    "javelin":    dict(speed=110, arc=40, boom=7, trail="smoke", homing=True),   # top attack
    "shell":      dict(speed=220, arc=0, boom=6, trail=None),
    "autocannon": dict(speed=320, arc=0, boom=2, trail=None),
    "grenade":    dict(speed=100, arc=14, boom=5, trail=None),
    "artillery":  dict(speed=120, arc=55, boom=10, trail="smoke"),
}

# damage per round, cooldown = seconds between trigger pulls, range in px, accuracy 0..1,
# burst = rounds per trigger pull, projectile = a PROJECTILE_STYLES key (None = instant hit),
# splash = blast radius in px, fixed = can't traverse (the vehicle turns to aim), deploy = seconds
# to dig in before it can fire (and to pack up again before moving), burst_gap = seconds between
# rounds of a burst, volley = the burst counts as one shot (one hit roll, one hit of `damage`; the
# other rounds are for show), spread = px lobbed rounds scatter round the target even when on
# target, mag = bursts before a reload of `reload` seconds, vs = the weapon's own damage
# multipliers per target class (instead of its type's), sure = never misses.
WEAPONS = {
    # Bullets
    "sniper": dict(name="Sniper rifle", type="bullet", damage=16, cooldown=2.4, range=100, accuracy=0.95,
                   vs=dict(infantry=1.5, light_vehicle=0.25, heavy_vehicle=0.05, building=0.05),
                   desc="Long reach, slow and deadly against soldiers; next to useless against "
                        "vehicles and buildings."),
    "pistol": dict(name="Pistol", type="bullet", damage=3.6, cooldown=0.72, range=38, accuracy=0.97,
                   desc="Light sidearm: accurate, short range."),
    "rifle": dict(name="Rifle", type="bullet", damage=8, cooldown=1.2, burst=5, volley=True, range=64,
                  accuracy=0.85, desc="All-purpose rifle, fired in 5-round bursts."),
    # secondary = a second weapon fired whenever its own (much longer) reload allows.
    "rifle_ugl": dict(name="Rifle + grenade launcher", type="bullet", damage=6, cooldown=0.9, range=64,
                      accuracy=0.85, secondary="ugl",
                      desc="Rifle with an underbarrel launcher that lobs a grenade every 9s."),
    "m60": dict(name="M60", type="bullet", damage=5, cooldown=1.0, burst=4, range=70, accuracy=0.62,
                desc="Machine gun: 4-round bursts that pin infantry down; inaccurate, weak vs armour."),
    "m2": dict(name="M2 Browning", type="bullet", damage=7, cooldown=0.3, range=76, accuracy=0.8,
               desc="Heavy machine gun: fast and accurate."),
    # Explosives
    "grenade_launcher": dict(name="Grenade launcher", type="explosive", damage=14, cooldown=1.6, range=80,
                             accuracy=0.8, projectile="grenade", splash=12,
                             desc="Lobbed grenades that burst over a small area."),
    "ugl": dict(name="40mm underbarrel grenade", type="explosive", damage=22, cooldown=9.0, range=80,
                accuracy=0.8, vs_vehicle=1.6, projectile="grenade", splash=12,
                desc="Dual-purpose grenade: splash, and good against light armour."),
    "agl6": dict(name="Auto grenade launcher", type="explosive", damage=9, cooldown=5.5, burst=6,
                 burst_gap=0.3, range=84,
                 accuracy=0.7, vs_vehicle=1.3, projectile="grenade", splash=10,
                 desc="6-round automatic grenade launcher: bursts of splashing grenades, then a long reload."),
    "uag40": dict(name="UAG-40", type="explosive", damage=8, cooldown=0.9, burst=3, spread=7, mag=5,
                  reload=6.0, range=84, accuracy=0.75, projectile="grenade", splash=12,
                  desc="Automatic grenade launcher: 3-round bursts that spread over the target, "
                       "then a 6s reload after every 5 bursts."),
    # Low damage per round, so armour soaks a lot of each hit: one wears a tank down slowly,
    # several together take it apart. (Tank guns reload slowest of all: see tests.)
    "bushmaster": dict(name="Bushmaster II 30mm", type="explosive", damage=7, cooldown=3.0, burst=10,
                       range=84, accuracy=0.85, projectile="autocannon", splash=5,
                       desc="Autocannon: fast 10-round bursts of light HE rounds, then a reload. "
                            "Wears tanks down; deadly in numbers."),
    "howitzer_155": dict(name="155mm artillery", type="explosive", damage=55, cooldown=5.0, range=160,
                         accuracy=0.65, projectile="artillery", splash=22, fixed=True, deploy=2.0,
                         desc="Huge range and blast, slow and inaccurate. Must deploy (2s) before "
                              "firing and pack up before moving; the vehicle turns to aim."),
    # Anti-armour
    "rocket_launcher": dict(name="Rocket launcher", type="anti_armor", damage=24, cooldown=2.4, range=84,
                            accuracy=0.9, projectile="rocket",
                            desc="Shoulder-fired rockets: slow to reload, devastating vs vehicles."),
    # Low base damage with a big multiplier against vehicles: poor at killing soldiers.
    "javelin": dict(name="Javelin", type="anti_armor", damage=18, cooldown=4.0, range=124, accuracy=1.0,
                    sure=True, vs_vehicle=3.4, projectile="javelin",
                    desc="Missile that arcs up and dives onto its target, tracking it as it moves: "
                         "never misses, longest reach, wrecks vehicles, weak against soldiers, "
                         "slow to reload."),
    "tow": dict(name="Twin TOW", type="anti_armor", damage=32, cooldown=2.8, range=110, accuracy=0.95,
                vs_vehicle=1.8, projectile="atgm",
                desc="Wire-guided missiles: long range, deadly vs vehicles, slow to reload."),
    "cannon_120": dict(name="120mm cannon", type="anti_armor", damage=50, cooldown=3.5, range=88,
                       accuracy=0.85, vs_vehicle=1.3, projectile="shell",
                       desc="The all-round tank gun."),
}

# Bullets fan out in a cone (visual only: hits are decided by accuracy). Each round strays
# sideways by up to SPRAY_CONE px per px of range, scaled up for inaccurate guns; hits stay on
# the target's body, misses fly on past it.
SPRAY_CONE = 0.07
HIT_SCATTER = 3.0      # px a hit lands from the target's centre
MISS_OVERSHOOT = 14    # px a miss can carry on beyond the target

# Stats a weapon contributes to its unit (see modules.compute_stats).
WEAPON_STATS = ("damage", "cooldown", "range", "accuracy", "burst", "vs_vehicle")


def weapon(wid):
    """A weapon's full definition: its type's defaults overlaid with its own entries."""
    w = WEAPONS[wid]
    out = dict(burst=1, splash=0, projectile=None, fixed=False, secondary=None, deploy=0.0,
               burst_gap=BURST_GAP, volley=False, spread=0, mag=0, reload=0.0, sure=False)
    out.update(WEAPON_TYPES[w["type"]])
    out.update(w)
    return out


def stats(wid):
    """The unit stats a weapon provides (zeros for unarmed units)."""
    if wid is None:
        return dict(damage=0, range=0, accuracy=0, burst=1, vs_vehicle=1.0)
    w = weapon(wid)
    return {k: w[k] for k in WEAPON_STATS}


# ---- firing -----------------------------------------------------------------------

def fire(game, shooter, target, mult=1.0, origin=None, wid=None, follow=None):
    """One trigger pull's round from `shooter` at `target`. Accuracy decides whether it hits;
    misses land somewhere nearby. mult scales damage (garrison bonus); origin overrides where
    the shot starts (a bunker's firing slit); wid fires another weapon the shooter carries (an
    underbarrel launcher) with that weapon's own numbers. follow = True/False for the later
    rounds of a volley: they only show, hitting (or missing) as the first round did.
    Returns whether the round hit."""
    w = weapon(wid or shooter.weapon)
    if follow is not None:
        _fire_bullet(game, shooter, target, w, mult, origin or shooter.muzzle_pos(), follow,
                     None if follow else _miss_offset(game.rng, shooter.accuracy), show=True)
        return follow
    if wid:
        mult *= w["damage"] / max(0.01, shooter.damage)
    accuracy = (w["accuracy"] if wid else shooter.accuracy) * (PRONE_ACCURACY if shooter.suppressed else 1.0)
    if target.is_unit and target.suppressed:
        accuracy *= PRONE_TARGET_HIT   # a soldier hugging the dirt is a small target
    rng = game.rng
    hit = w["sure"] or rng.random() < accuracy
    miss = None if hit else _miss_offset(rng, accuracy)
    if hit and w["spread"] and w["splash"]:
        # A spreading burst: lobbed rounds land round the target, close enough that their
        # blast still catches it.
        a, d = rng.uniform(0, math.tau), rng.uniform(0.3, 1.0) * w["spread"]
        miss = (math.cos(a) * d, math.sin(a) * d * 0.6)
    start = origin or shooter.muzzle_pos()
    if w["projectile"] is None:
        _fire_bullet(game, shooter, target, w, mult, start, hit, miss)
    else:
        game.projectiles.append(Projectile(shooter, target, shooter.damage * mult, w, start, miss,
                                           w["vs_vehicle"] if wid else None))
    return hit


def _miss_offset(rng, accuracy):
    spread = 6 + (1 - accuracy) * 30
    a = rng.uniform(0, math.tau)
    return math.cos(a) * spread, math.sin(a) * spread * 0.6


VOLLEY_SCATTER = 5.0   # px a volley's hits spread over the target's body


def _fire_bullet(game, shooter, target, w, mult, start, hit, miss, show=False):
    """A bullet's tracer, pin and damage; show=True draws only the tracer (a volley's later rounds)."""
    rng = game.rng
    tx, ty = target.x, target.y - 3
    dx, dy = tx - start[0], ty - start[1]
    dist = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / dist, dy / dist
    if hit:
        sc = VOLLEY_SCATTER if w["volley"] else HIT_SCATTER
        end = (tx + rng.uniform(-sc, sc), ty + rng.uniform(-sc, sc) * 0.8)
    else:
        # Off to one side of the line, and carrying on past the target.
        side = rng.uniform(-1, 1) * dist * SPRAY_CONE * (2.4 - w["accuracy"] * 1.4) + rng.choice((-1, 1)) * 4
        on = rng.uniform(0, MISS_OVERSHOOT)
        end = (tx + miss[0] * 0.5 - uy * side + ux * on, ty + miss[1] * 0.5 + ux * side * 0.6 + uy * on)
        game.particles.append([end[0], end[1], 0, -15, 0.25, (200, 176, 130), 1.0])
    game.tracers.append([start[0], start[1], end[0], end[1], 0.0, rng.random()])
    if show:
        return
    if w["pin_per_round"] and target.is_unit:
        # Rounds snapping past keep heads down whether or not they hit.
        target.suppress(SUPPRESS_PER_SHOT + shooter.damage, (shooter.x, shooter.y))
    if hit:
        amount = shooter.damage * mult * (shooter.vs_vehicle if target.is_vehicle else 1.0)
        _hit(game, target, amount, shooter, w["type"], w["vs"])


def splash(game, x, y, radius, damage, vs_vehicle, team, source, wtype="explosive", vs=None):
    """Area damage: full at the centre, half at the edge, enemies only."""
    for u in list(game.units):
        d = math.hypot(u.x - x, u.y - y) - u.radius
        if u.team != team and u.alive and d <= radius:
            f = 1 - 0.5 * max(0.0, d) / radius
            _hit(game, u, damage * f * (vs_vehicle if u.is_vehicle else 1.0), source, wtype, vs)
    for b in list(game.buildings):
        if b.team != team and b.alive and dist_point_rect(x, y, b.rect()) <= radius:
            _hit(game, b, damage, source, wtype, vs)


def pin_area(game, x, y, radius, amount):
    """Everyone's infantry near a blast hits the dirt, whoever fired it."""
    for u in game.units:
        if u.is_infantry and math.hypot(u.x - x, u.y - y) <= radius:
            u.suppress(amount, (x, y))


class Projectile:
    """Flies over the ground at (gx, gy) at height h; drawn at (x, y) = (gx, gy - h)."""

    def __init__(self, source, target, damage, w, start, miss_offset=None, vs_vehicle=None):
        style = PROJECTILE_STYLES[w["projectile"]]
        self.source = source
        self.target = target
        self.damage = damage
        self.weapon = w
        self.style = w["projectile"]
        self.team = source.team
        self.vs_vehicle = source.vs_vehicle if vs_vehicle is None else vs_vehicle
        self.speed, self.arc = style["speed"], style["arc"]
        self.boom, self.trail = style["boom"], style["trail"]
        self.splash = w["splash"]
        self.gx, self.gy = source.x, source.y
        self.h0 = self.h = max(0.0, source.y - start[1])
        self.x, self.y = start
        # Misses and lobbed rounds fly at a fixed spot; straight hits (and homing missiles) home
        # in on the target.
        self.locked = (self.arc > 0 and not style.get("homing")) or miss_offset is not None
        mx, my = miss_offset or (0.0, 0.0)
        self.aim = (target.x + mx, target.y + my)
        self.total = max(1.0, math.hypot(self.aim[0] - self.gx, self.aim[1] - self.gy))
        a = math.radians(source.facing)
        self.dx, self.dy = math.cos(a), math.sin(a)
        self.alive = True

    def update(self, game, dt):
        t = self.target
        if not self.locked:
            if t.alive:
                self.aim = (t.x, t.y)
            else:
                self.locked = True
        ax, ay = self.aim
        dx, dy = ax - self.gx, ay - self.gy
        d = math.hypot(dx, dy)
        step = self.speed * dt
        if d <= step:
            self.gx, self.gy = ax, ay
            self.explode(game)
            return
        self.dx, self.dy = dx / d, dy / d
        self.gx += self.dx * step
        self.gy += self.dy * step
        progress = min(1.0, max(0.0, 1 - (d - step) / self.total))
        if self.arc:
            self.h = self.h0 * (1 - progress) + self.arc * 4 * progress * (1 - progress)
        else:
            self.h = 3 + (self.h0 - 3) * (1 - progress)
        self.x, self.y = self.gx, self.gy - self.h
        if self.trail == "smoke" and game.rng.random() < 0.6:
            game.particles.append([self.x, self.y, 0, -8, 0.5, (190, 180, 170), 0.0])

    def explode(self, game):
        self.alive = False
        x, y = self.gx, self.gy
        t = self.target
        w = self.weapon
        if self.splash:
            splash(game, x, y, self.splash, self.damage, self.vs_vehicle, self.team, self.source, w["type"],
                   w["vs"])
        elif not self.locked and t.alive:
            _hit(game, t, self.damage * (self.vs_vehicle if t.is_vehicle else 1.0), self.source, w["type"],
                 w["vs"])
        if w["blast_pin"]:   # explosives pin down infantry around the blast
            pin_area(game, x, y, max(w["blast_radius"], self.splash * 1.5), w["blast_pin"])
        game.boom(x, y - 2, self.boom)
        game.puff(x, y - 2, (200, 180, 140), 3 + self.boom, 20 + self.boom * 3)
