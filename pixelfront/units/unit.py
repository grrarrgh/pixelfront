"""The Unit class: what every soldier and vehicle does.

Per-type data (stats, weapons, tiers) lives next door in units/<kind>.py; weapons and how they
fire live in weapons.py. This module is behaviour only: orders, movement, combat, suppression.
"""
import logging
import math

from ..config import (TILE, BUILDINGS, INTERACT, REPAIR_RATE, PRONE_SPEED, SUPPRESS_ON, SUPPRESS_OFF,
                      SUPPRESS_DECAY, SUPPRESS_CALM, PRONE_RANGE, TURRET_SPEED, KNEEL_TIME, STEER_MAX,
                      RETREAT_DISTANCE, RETREAT_COOLDOWN, RETREAT_TIMEOUT)
from ..entities import Entity, dist_point_rect
from ..modules import compute_stats, default_loadout
from ..pathfinding import find_path
from ..weapons import weapon as weapon_def
from .registry import UNITS

log = logging.getLogger(__name__)


class Unit(Entity):
    is_unit = True

    def __init__(self, kind, team, x, y, loadout=None):
        super().__init__(kind, team, x, y)
        base = UNITS[kind]
        self.loadout = dict(loadout) if loadout else default_loadout(kind)
        st = compute_stats(kind, self.loadout)
        self.name = base["name"]
        self.is_vehicle = base["cls"] == "vehicle"
        self.is_infantry = not self.is_vehicle
        self.target_class = base.get("target_class", "light_vehicle" if self.is_vehicle else "infantry")
        self.radius = base["radius"]
        self.hull_turn = base.get("hull_turn", 180)   # vehicles: degrees per second
        self.kneels = base.get("kneels", False)       # must kneel before firing
        self.weapon = st["weapon"]   # the loadout can swap the weapon type
        # A second weapon on the first (an underbarrel launcher), fired when its reload allows.
        self.secondary = weapon_def(self.weapon)["secondary"] if self.weapon else None
        self.sec_cooldown = 0.0
        self.supply = base["supply"]
        self.max_hp = self.hp = max(1, round(st["hp"]))
        self.armor = round(st["armor"])
        self.armor_rank = st["armor_rank"]   # how much each weapon type is shrugged off (weapons.py)
        self.damage = st["damage"]
        self.range = st["range"]
        self.attack_time = st["cooldown"]
        self.speed = st["speed"]
        self.sight = int(round(st["sight"]))
        self.heal = st["heal"]
        self.work = st["work"]
        self.vs_vehicle = st["vs_vehicle"]
        self.accuracy = st["accuracy"]
        self.burst = max(1, int(st["burst"]))   # rounds per trigger pull (machine guns)
        self.burst_left = 0
        self.burst_timer = 0.0
        wd = weapon_def(self.weapon) if self.weapon else dict(burst_gap=0.0, volley=False, mag=0, reload=0.0)
        self.burst_gap = wd["burst_gap"]   # seconds between a burst's rounds
        self.volley = wd["volley"]         # the burst is one shot: later rounds just show
        self.volley_hit = False            # whether this burst's first round hit
        self.mag = self.mag_left = wd["mag"]   # bursts before a long reload (0 = no magazine)
        self.reload_time = wd["reload"]
        self.passive = False  # test-range targets never acquire or return fire
        self.inside = None    # the bunker this soldier is manning, if any
        self.assist = None    # (kind, tx, ty) of a building site this engineer is helping on
        self.idle_t = 0.0     # drives the idle animation
        # Idle scanning: turrets sweep to random bearings; soldiers look around and now and then
        # check their weapon (check_t > 0 while they do).
        self.look = None      # bearing being turned to (turret: relative to hull; infantry: absolute)
        self.look_t = 0.0     # seconds until the next look-around
        self.check_t = 0.0
        self.armed = self.damage > 0 and self.weapon is not None
        # Front-line troops; medics and engineers (even with a sidearm) hang back in a group.
        self.fighter = self.armed and not self.heal and not self.work

        self.order = "idle"
        self.path = []
        self.goal = None         # (tile_rect, adjacent) the current path leads to
        self.target = None
        self.amove_dest = None
        self.build_plan = None   # (kind, tx, ty), credits already paid
        self.group_speed = None  # px/s pace of the group this unit was ordered to move with
        self.convoy = None       # dict(hx, hy, vehicles) when moving with vehicles that must lead
        self.hold_t = 0.0        # seconds spent waiting for the convoy's vehicles to pass
        self.timer = 0.0

        self.cooldown = 0.0
        self.scan = 0.0
        self.repath = 0.0
        self.facing = 0.0        # degrees, 0 = east, 90 = south (screen down)
        self.moving = False
        self.anim = 0.0          # advances while moving; drives walk/crawl frames
        self.lunge = 0.0         # >0 just after firing/working; drives the recoil frame

        # Suppression (infantry only): heavy fire pins soldiers down; they crawl, are harder
        # to hit, and crawl back out of the line of fire until it lets up.
        self.suppression = 0.0
        self.suppressed = False
        self.calm = 0.0
        self.threat = None        # (x, y) of whatever last pinned this soldier down
        self.retreat = None       # dict(timer, goal) while crawling away from the threat
        self.retreat_cd = 0.0

        # Vehicles aim a turret (absolute degrees) independently of the hull, except
        # fixed guns (artillery), which have to turn the whole vehicle.
        self.has_turret = (self.is_vehicle and self.weapon is not None
                           and not weapon_def(self.weapon)["fixed"])
        self.turret = self.facing
        self.aiming = False
        self.steer = 0.0          # front-wheel angle for the renderer (model degrees, + = left)
        # Heavy infantry kneel before firing; this counts up to KNEEL_TIME while they settle.
        self.kneel = 0.0
        # Artillery digs in before firing: deploy runs 0 (ready to drive) .. 1 (ready to fire).
        self.deploy_time = weapon_def(self.weapon)["deploy"] if self.weapon else 0.0
        self.deploy = 0.0
        self.packing = False
        self.dug_in = False   # deployed on the player's order: holds its ground until told to pack up

    def rect(self):
        r = self.radius
        return (self.x - r, self.y - r, self.x + r, self.y + r)

    def tile_rect(self):
        tx, ty = self.tile()
        return (tx, ty, tx, ty)

    @property
    def turret_free(self):
        """Whether the turret aims on its own: always for turrets, and for artillery once dug in
        (its gun house traverses on the hull)."""
        return self.has_turret or (self.deploy_time > 0 and self.deploy >= 1)

    @property
    def turret_rel(self):
        """The turret's angle relative to the hull, as drawn."""
        return self.turret - self.facing if self.turret_free else 0.0

    def muzzle_pos(self):
        from ..sprites import muzzle_offset  # geometry lives with the 3D models
        dx, dy = muzzle_offset(self.kind, self.loadout, self.facing, self.suppressed, self.turret_rel,
                               self.kneeling, self.deploy >= 1)
        return self.x + dx, self.y + dy

    @property
    def move_speed(self):
        speed = self.speed
        if self.group_speed and self.order in ("move", "amove"):
            speed = min(speed, self.group_speed)   # keep pace with the group
            if self.holding():
                return 0.0
        return speed * (PRONE_SPEED if self.suppressed else 1.0)

    HOLD_GAP = TILE      # how far behind the convoy's rearmost vehicle soldiers keep
    HOLD_MAX = 6.0       # give up waiting after this long (a vehicle stuck on something)

    def holding(self):
        """Soldiers moving with vehicles let them go first: a soldier ahead of the rearmost
        vehicle still on its way waits for it to pass."""
        c = self.convoy
        if c is None or self.is_vehicle or self.hold_t >= self.HOLD_MAX:
            return False
        hx, hy = c["hx"], c["hy"]
        rolling = [v.x * hx + v.y * hy for v in c["vehicles"]
                   if v.alive and v.path and v.order in ("move", "amove")]
        return bool(rolling) and self.x * hx + self.y * hy > min(rolling) - self.HOLD_GAP

    def path_length(self):
        """Pixels left to walk along the current path."""
        dist, x, y = 0.0, self.x, self.y
        for tx, ty in self.path:
            gx, gy = tx * TILE + TILE / 2, ty * TILE + TILE / 2
            dist += math.hypot(gx - x, gy - y)
            x, y = gx, gy
        return dist

    @property
    def kneeling(self):
        return self.kneels and self.kneel > 0 and not self.suppressed

    @property
    def attack_range(self):
        return self.range * (PRONE_RANGE if self.suppressed else 1.0)

    GUN_HOUSE_SPEED = 0.45   # fraction of TURRET_SPEED a dug-in gun house traverses at

    def _swing_turret(self, want, speed, dt):
        """Turn the turret towards absolute bearing `want`. Returns how far off it still is."""
        diff = (want - self.turret + 180) % 360 - 180
        step = speed * dt
        self.turret = want if abs(diff) <= step else (self.turret + math.copysign(step, diff)) % 360
        return abs((want - self.turret + 180) % 360 - 180)

    def aim_at(self, x, y, dt):
        """Turn the turret (or hull, for fixed guns) towards a point. Returns True once on target."""
        want = math.degrees(math.atan2(y - self.y, x - self.x)) % 360
        if not self.has_turret:
            if self.is_vehicle:   # fixed gun
                if self.deploy >= 1:   # dug in: the gun house traverses
                    self.packing = False
                    return self._swing_turret(want, TURRET_SPEED * self.GUN_HOUSE_SPEED, dt) <= 6
                if self.deploy > 0:    # part dug in: finish digging in, then traverse
                    return True
                diff = (want - self.facing + 180) % 360 - 180   # travelling: swing the whole hull
                step = self.hull_turn * dt
                self.facing = (self.facing + max(-step, min(step, diff))) % 360
                return abs(diff) <= 6
            self.face(x, y)
            return True
        return self._swing_turret(want, TURRET_SPEED, dt) <= 8

    def _pack(self, dt):
        """Artillery packing up: the gun house swings back to the front, then spades up and
        barrel down, before it can turn or drive."""
        if not self.packing:
            log.debug("%s #%d packing up", self.name, self.id)
        self.packing = True
        self.dug_in = False
        if self.deploy >= 1 and self._swing_turret(self.facing, TURRET_SPEED * self.GUN_HOUSE_SPEED, dt) > 0:
            return
        self.deploy = max(0.0, self.deploy - dt / self.deploy_time)
        if self.deploy <= 0:
            self.packing = False
            log.debug("%s #%d packed up", self.name, self.id)

    def _dig_in(self, dt):
        self.packing = False
        self.deploy = min(1.0, self.deploy + dt / self.deploy_time)
        if self.deploy >= 1:
            log.debug("%s #%d deployed", self.name, self.id)

    def _relax_turret(self, dt):
        if self.deploy_time and not self.turret_free:
            self.turret = self.facing   # travelling artillery: the gun house is locked forward
        elif self.has_turret:
            diff = (self.facing - self.turret + 180) % 360 - 180
            step = TURRET_SPEED * 0.5 * dt
            self.turret = self.facing if abs(diff) <= step else (self.turret + math.copysign(step, diff)) % 360

    def suppress(self, amount, source=None):
        """Incoming fire. source = (x, y) it came from: a shooter, or an explosion."""
        if not self.is_infantry:
            return
        self.suppression = min(100.0, self.suppression + amount)
        self.calm = SUPPRESS_CALM
        if source is not None:
            self.threat = source
        if self.suppression >= SUPPRESS_ON and not self.suppressed:
            self.suppressed = True
            log.debug("%s #%d (team %d) pinned down", self.name, self.id, self.team)

    def _update_suppression(self, dt):
        if self.calm > 0:
            self.calm -= dt
        elif self.suppression > 0:
            self.suppression = max(0.0, self.suppression - SUPPRESS_DECAY * dt)
        if self.suppressed and self.suppression < SUPPRESS_OFF:
            self.suppressed = False
            self.threat = None

    # ---- retreating from suppression --------------------------------------

    def _wants_retreat(self):
        return (self.suppressed and self.threat is not None and self.retreat is None
                and self.retreat_cd <= 0 and self.inside is None and self.order != "move")

    def _start_retreat(self, game):
        """Pick a walkable tile about RETREAT_DISTANCE tiles directly away from the threat
        (or as close to directly away as the ground allows) and crawl for it."""
        tx_, ty_ = self.threat
        dx, dy = self.x - tx_, self.y - ty_
        if dx * dx + dy * dy < 1:   # right on top of us (a shell at our feet): any way out
            a = game.rng.uniform(0, math.tau)
            dx, dy = math.cos(a), math.sin(a)
        away = math.atan2(dy, dx)
        w = game.world
        dest = None
        for frac in (1.0, 0.66, 0.33):
            for turn in (0, 30, -30, 60, -60, 90, -90):
                a = away + math.radians(turn)
                d = RETREAT_DISTANCE * TILE * frac
                tx, ty = int((self.x + math.cos(a) * d) // TILE), int((self.y + math.sin(a) * d) // TILE)
                if w.walkable(tx, ty) and (tx, ty) != self.tile():
                    dest = (tx, ty)
                    break
            if dest:
                break
        self.retreat_cd = RETREAT_COOLDOWN
        if dest is None:
            return   # cornered: stay down and take it
        self.retreat = dict(timer=RETREAT_TIMEOUT, goal=self.goal, dest=dest)
        self.burst_left = 0
        self.plan_to_tile(game, *dest)
        log.debug("%s: %s #%d (team %d) pinned by fire from (%d, %d); crawling back to %s",
                  game.clock(), self.name, self.id, self.team, tx_, ty_, dest)

    def _do_retreat(self, game, dt):
        r = self.retreat
        r["timer"] -= dt
        if self.follow(game, dt) or r["timer"] <= 0 or not self.suppressed:
            self._end_retreat(game)

    def _end_retreat(self, game):
        """Back to whatever the soldier was doing, re-planning any route the retreat replaced."""
        goal = self.retreat["goal"]
        self.retreat = None
        self.retreat_cd = RETREAT_COOLDOWN
        self.goal = goal
        self.path = find_path(game.world, self.tile(), *goal) if goal else []
        self.repath = 0.0

    def edge_dist(self, other):
        if other.is_unit:
            return max(0.0, math.hypot(other.x - self.x, other.y - self.y) - self.radius - other.radius)
        return max(0.0, dist_point_rect(self.x, self.y, other.rect()) - self.radius)

    @property
    def status(self):
        if self.suppressed:
            return "Pinned down!"
        if self.deploy > 0 and self.packing:
            return "Packing up"
        if 0 < self.deploy < 1 or self.order == "deploy":
            return "Deploying"
        if self.order == "build":
            return "Going to build " + BUILDINGS[self.build_plan[0]]["name"]
        if self.deploy >= 1 and self.order in ("idle", "attack"):
            if self.order == "attack":
                return "Firing (deployed)"
            return "Dug in" if self.dug_in else "Deployed"
        return {"idle": "Idle", "pack": "Packing up", "move": "Moving", "amove": "Attack-moving", "attack": "Attacking",
                "heal": "Healing", "repair": "Repairing", "construct": "Building",
                "assist": "Helping to build", "garrison": "Heading for the bunker",
                "escort": "Following"}[self.order]

    # ---- orders -----------------------------------------------------------

    def _reset(self, game):
        if self.build_plan:
            game.refund(self.team, BUILDINGS[self.build_plan[0]]["cost"])
            self.build_plan = None
        self.order = "idle"
        self.path = []
        self.goal = None
        self.target = None
        self.amove_dest = None
        self.assist = None
        self.group_speed = None
        self.convoy = None
        self.hold_t = 0.0
        self.burst_left = 0
        self.repath = 0.0
        self.dug_in = False

    def plan_to(self, game, rect, adjacent):
        self.goal = (rect, adjacent)
        self.path = find_path(game.world, self.tile(), rect, adjacent)

    def plan_to_tile(self, game, tx, ty):
        self.plan_to(game, (tx, ty, tx, ty), not game.world.walkable(tx, ty))

    def stop(self, game):
        self._reset(game)

    def order_move(self, game, tx, ty):
        self._reset(game)
        self.retreat = None   # a direct move order overrides the urge to crawl away
        self.order = "move"
        self.plan_to_tile(game, tx, ty)

    def order_amove(self, game, tx, ty):
        if not self.armed:
            self.order_move(game, tx, ty)
            return
        self._reset(game)
        self.order = "amove"
        self.amove_dest = (tx, ty)
        self.plan_to_tile(game, tx, ty)

    def _order_target(self, game, order, target):
        self._reset(game)
        self.order = order
        self.target = target

    def order_attack(self, game, target):
        if self.armed:
            self._order_target(game, "attack", target)

    def order_heal(self, game, target):
        self._order_target(game, "heal", target)

    def order_repair(self, game, target):
        self._order_target(game, "repair", target)

    def order_construct(self, game, building):
        self._order_target(game, "construct", building)

    def order_deploy(self, game):
        """Artillery digs in where it stands and holds its ground, firing on anything in range."""
        if not self.deploy_time:
            return
        self._reset(game)
        self.order = "deploy"
        self.dug_in = True
        log.info("%s: %s #%d (team %d) ordered to deploy", game.clock(), self.name, self.id, self.team)

    def order_pack(self, game):
        """Artillery packs up, ready to drive."""
        if not self.deploy_time:
            return
        self._reset(game)
        self.order = "pack"
        log.info("%s: %s #%d (team %d) ordered to pack up", game.clock(), self.name, self.id, self.team)

    def order_garrison(self, game, bunker):
        self._order_target(game, "garrison", bunker)

    def order_escort(self, game, leader):
        """Medics and engineers sent along on an attack stay behind a fighter instead of leading."""
        self._order_target(game, "escort", leader)

    def order_assist(self, game, kind, tx, ty):
        """Go and help another engineer put up a building at (tx, ty)."""
        self._reset(game)
        self.order = "assist"
        self.assist = (kind, tx, ty)
        s = BUILDINGS[kind]["size"]
        self.plan_to(game, (tx, ty, tx + s - 1, ty + s - 1), True)

    def order_build(self, game, kind, tx, ty):
        self._reset(game)
        self.order = "build"
        self.build_plan = (kind, tx, ty)
        s = BUILDINGS[kind]["size"]
        self.plan_to(game, (tx, ty, tx + s - 1, ty + s - 1), True)

    # ---- movement ---------------------------------------------------------

    def face(self, x, y):
        dx, dy = x - self.x, y - self.y
        if dx * dx + dy * dy > 0.25:
            self.facing = math.degrees(math.atan2(dy, dx)) % 360

    def _drive(self, gx, gy, dt):
        """Vehicles turn their hull towards (gx, gy) at their turn rate, steering the front wheels
        into the bend. Returns the fraction of full speed they can move this frame."""
        want = math.degrees(math.atan2(gy - self.y, gx - self.x)) % 360
        diff = (want - self.facing + 180) % 360 - 180
        step = self.hull_turn * dt
        self.facing = (self.facing + max(-step, min(step, diff))) % 360
        self.steer = -max(-STEER_MAX, min(STEER_MAX, diff))
        if abs(diff) > 70:
            return 0.0   # turn on the spot first
        return max(0.35, math.cos(math.radians(diff)))

    def follow(self, game, dt):
        """Advance along the current path. Returns True once there is nowhere left to go."""
        if not self.path:
            return True
        if self.deploy > 0:   # artillery packs up before it can drive off
            self._pack(dt)
            return False
        world = game.world
        tx, ty = self.path[0]
        if not world.walkable(tx, ty):
            self.path = find_path(world, self.tile(), *self.goal) if self.goal else []
            if not self.path or not world.walkable(*self.path[0]):
                self.path = []
                return True
            tx, ty = self.path[0]
        if len(self.path) > 1 and self.tile() == (tx, ty):
            # Already on this waypoint's tile: head on for the next one. In a crowd moving at
            # one pace, everyone can't stand on the tile's centre at once.
            self.path.pop(0)
            tx, ty = self.path[0]
        gx, gy = tx * TILE + TILE / 2, ty * TILE + TILE / 2
        dx, dy = gx - self.x, gy - self.y
        d = math.hypot(dx, dy)
        step = self.move_speed * dt
        if step <= 0:
            self.hold_t += dt   # waiting for the convoy's vehicles to go by
            return False
        self.moving = True
        if self.is_vehicle:
            step *= self._drive(gx, gy, dt)
            if step <= 0:
                return False
        else:
            self.face(gx, gy)
        if d <= step:
            self.x, self.y = gx, gy
            self.path.pop(0)
            return not self.path
        ux, uy = dx / d, dy / d
        if self.is_infantry:
            sx, sy = game.steer_around(self, ux, uy)   # walk round anyone standing in the way
            if (sx, sy) != (ux, uy) and game.world.walkable_px(self.x + sx * step, self.y + sy * step):
                ux, uy = sx, sy
                self.face(self.x + ux, self.y + uy)
        self.x += ux * step
        self.y += uy * step
        return False

    def step_toward(self, game, gx, gy, dt):
        dx, dy = gx - self.x, gy - self.y
        d = math.hypot(dx, dy)
        if d < 0.5:
            return
        if self.deploy > 0:
            self._pack(dt)
            return
        step = min(d, self.move_speed * dt)
        if self.is_vehicle:
            step *= self._drive(gx, gy, dt)
            self.moving = True
            if step <= 0:
                return
        nx, ny = self.x + dx / d * step, self.y + dy / d * step
        w = game.world
        if w.walkable_px(nx, ny):
            self.x, self.y = nx, ny
        elif w.walkable_px(nx, self.y):
            self.x = nx
        elif w.walkable_px(self.x, ny):
            self.y = ny
        else:
            return
        self.moving = True
        if not self.is_vehicle:
            self.face(gx, gy)

    def chase(self, game, target, reach, dt):
        """Close in on target until within `reach` px of its edge. Returns True once there."""
        d = self.edge_dist(target)
        if d <= reach:
            self.path = []
            if not self.is_vehicle:   # vehicles aim with the turret, or turn the hull in aim_at()
                self.face(target.x, target.y)
            return True
        if d < 12:
            self.step_toward(game, target.x, target.y, dt)
            return False
        self.repath -= dt
        if self.repath <= 0:
            self.repath = 0.7
            self.plan_to(game, target.tile_rect(), True)
        if self.follow(game, dt):
            self.step_toward(game, target.x, target.y, dt)
        return False

    # ---- behaviour --------------------------------------------------------

    def update(self, game, dt):
        self.cooldown -= dt
        self.sec_cooldown -= dt
        self.flash = max(0.0, self.flash - dt)
        self.lunge = max(0.0, self.lunge - dt)
        self._update_suppression(dt)
        self.moving = False
        self.aiming = False
        self.steer = 0.0
        self.retreat_cd -= dt
        if self._wants_retreat():
            self._start_retreat(game)
        if self.retreat:
            self._do_retreat(game, dt)
        else:
            getattr(self, "do_" + self.order)(game, dt)
        self.idle_t += dt
        if self.moving:
            self.anim += dt * self.move_speed / self.speed
            self.kneel = 0.0   # heavy infantry stand up to move
        on_watch = self.order == "idle" and not self.moving and not self.suppressed and not self.retreat
        if on_watch:
            self._look_around(game, dt)
        else:
            self.look, self.check_t = None, 0.0
        if not self.aiming and not (on_watch and self.turret_free) and not self.packing:
            self._relax_turret(dt)

    IDLE_TURRET_SPEED = 0.35   # fraction of TURRET_SPEED a turret sweeps at while scanning
    IDLE_TURN_SPEED = 160      # degrees per second soldiers turn to look around

    def _look_around(self, game, dt):
        """Idle units keep watch: a turret sweeps to random bearings and pauses; a soldier turns
        to face a random direction every few seconds and sometimes checks their weapon."""
        rng = game.rng
        self.look_t -= dt
        self.check_t = max(0.0, self.check_t - dt)
        if self.look_t <= 0 and self.check_t <= 0:
            self.look_t = rng.uniform(2.0, 5.0)
            if self.is_vehicle:
                self.look = 0.0 if rng.random() < 0.25 else rng.uniform(-120, 120)
            elif rng.random() < 0.3 and self.armed or rng.random() < 0.2:
                self.check_t = 1.6          # look the weapon (or kit) over
                self.look = None
            else:
                self.look = (self.facing + rng.choice((-1, 1)) * rng.uniform(45, 150)) % 360
        if self.look is None:
            return
        if self.is_vehicle:
            if not self.turret_free:
                return
            speed = TURRET_SPEED * self.IDLE_TURRET_SPEED * (self.GUN_HOUSE_SPEED if not self.has_turret else 1)
            self._swing_turret((self.facing + self.look) % 360, speed, dt)
        else:
            diff = (self.look - self.facing + 180) % 360 - 180
            step = self.IDLE_TURN_SPEED * dt
            self.facing = self.look if abs(diff) <= step else (self.facing + math.copysign(step, diff)) % 360

    def do_deploy(self, game, dt):
        if self.deploy < 1:
            self._dig_in(dt)
        else:
            self.order = "idle"
            self.scan = 0.0

    def do_pack(self, game, dt):
        if self.deploy > 0:
            self._pack(dt)
        else:
            self.order = "idle"
            self.scan = 0.0

    def do_idle(self, game, dt):
        if self.kind == "engineer" or self.passive:
            return
        self.scan -= dt
        if self.scan > 0:
            return
        self.scan = 0.4
        if self.heal:
            patient = game.find_patient(self, self.sight * TILE)
            if patient:
                self.order = "heal"
                self.target = patient
                self.repath = 0.0
        elif self.armed:
            # Dug in on orders, it only takes on what it can reach from where it stands.
            enemy = game.find_enemy_near(self, self.attack_range if self.dug_in else self.sight * TILE)
            if enemy:
                self.order = "attack"
                self.target = enemy
                self.repath = 0.0

    def do_move(self, game, dt):
        if self.follow(game, dt):
            self.order = "idle"
            self.goal = None

    def do_amove(self, game, dt):
        self.scan -= dt
        if self.scan <= 0:
            self.scan = 0.3
            enemy = game.find_enemy_near(self, self.sight * TILE)
            if enemy:
                self.order = "attack"
                self.target = enemy
                self.path = []
                self.repath = 0.0
                return
        if self.follow(game, dt):
            self.order = "idle"
            self.amove_dest = None

    def _target_gone(self, game):
        self.target = None
        if self.amove_dest:
            self.order = "amove"
            self.plan_to_tile(game, *self.amove_dest)
        else:
            self.order = "idle"
            self.scan = 0.0

    def do_attack(self, game, dt):
        t = self.target
        if t is None or not t.alive or getattr(t, "inside", None) or not game.can_target(self, t):
            # gone, inside a structure, or out of sight up on a cliff
            self._target_gone(game)
            return
        if self.dug_in and self.edge_dist(t) > self.attack_range:
            self._target_gone(game)   # holding its ground: don't pack up to chase
            return
        if self.burst_left > 0:   # finish the burst before anything else
            self.aiming = True
            if not self.is_vehicle:
                self.face(t.x, t.y)
            self.burst_step(game, t, dt)
            return
        if self.suppressed and self.edge_dist(t) > self.attack_range:
            # Pinned soldiers don't crawl towards the enemy: shoot at whoever is in reach, or
            # keep their heads down until the fire lets up.
            near = game.find_enemy_near(self, self.attack_range)
            if near is None:
                return
            t = self.target = near
        if not self.chase(game, t, self.attack_range, dt):
            return
        self.aiming = True
        on_target = self.aim_at(t.x, t.y, dt)
        if self.kneels and not self.suppressed and self.kneel < KNEEL_TIME:
            self.kneel += dt   # kneel down before the first shot
            return
        if self.deploy_time and self.deploy < 1:
            if on_target:
                self._dig_in(dt)   # artillery: spades down and barrel up before the first shot
            return
        if on_target and self.cooldown <= 0:
            sec = self.secondary and weapon_def(self.secondary)
            if sec and self.sec_cooldown <= 0 and self.edge_dist(t) <= sec["range"]:
                self.cooldown = self.attack_time
                self.lunge = 0.12
                self.sec_cooldown = sec["cooldown"]   # this pull fires the grenade instead
                game.attack(self, t, wid=self.secondary)
                return
            self.pull_trigger(game, t)

    def pull_trigger(self, game, t, mult=1.0, origin=None, reload=1.0):
        """Fire the first round of a burst at t; burst_step() fires the rest. A weapon with a
        magazine reloads after its last burst. reload scales the wait (a bunker's bonus)."""
        self.cooldown = self.attack_time * reload
        if self.mag:
            self.mag_left -= 1
            if self.mag_left <= 0:
                self.mag_left = self.mag
                self.cooldown = max(self.cooldown, self.reload_time * reload)
                log.debug("%s #%d (team %d) reloading (%.1fs)", self.name, self.id, self.team, self.cooldown)
        self.lunge = 0.12
        self.burst_left, self.burst_timer = self.burst - 1, self.burst_gap
        self.volley_hit = game.attack(self, t, mult, origin)

    def burst_step(self, game, t, dt, mult=1.0, origin=None):
        """The rest of a burst, one round every burst_gap seconds."""
        self.burst_timer -= dt
        if self.burst_timer <= 0:
            self.burst_left -= 1
            self.burst_timer = self.burst_gap
            self.lunge = 0.08
            game.attack(self, t, mult, origin, follow=self.volley_hit if self.volley else None)

    def do_garrison(self, game, dt):
        b = self.target
        if b is None or not b.alive or not b.complete:
            self._target_gone(game)
            return
        if len(b.occupants) >= b.capacity:
            game.notify(self.team, "Bunker is full")
            self._target_gone(game)
            return
        if self.chase(game, b, INTERACT, dt):
            game.enter(self, b)

    def do_assist(self, game, dt):
        kind, tx, ty = self.assist
        occ = game.world.occupant[ty * game.world.w + tx]
        if occ is not None and occ.is_building and occ.kind == kind and occ.team == self.team:
            if occ.complete:
                self._target_gone(game)
            else:
                self.order_construct(game, occ)   # the foundation is down: pitch in
            return
        if not any(u.build_plan == (kind, tx, ty) for u in game.units if u.team == self.team):
            self._target_gone(game)                # the builder gave up or died
            return
        self.follow(game, dt)                     # walk over and wait for the foundation

    ESCORT_GAP = 1.5 * TILE   # how close behind its fighter an escort keeps

    def do_escort(self, game, dt):
        lead = self.target
        if lead is None or not lead.alive or lead.inside:
            self._target_gone(game)
            return
        if self.chase(game, lead, self.ESCORT_GAP, dt) and lead.order == "idle" and not lead.moving:
            self._target_gone(game)   # the fight's over and the fighter has stopped: wait here
            return
        if self.heal:
            self.scan -= dt
            if self.scan <= 0:
                self.scan = 0.4
                patient = game.find_patient(self, self.sight * TILE)
                if patient:
                    self.order_heal(game, patient)   # patch them up, then stay put to help

    def do_heal(self, game, dt):
        t = self.target
        if t is None or not t.alive or t.hp >= t.max_hp or t.inside:
            self._target_gone(game)
            return
        if self.chase(game, t, INTERACT, dt) and self.cooldown <= 0:  # hands-on: must touch
            self.cooldown = self.attack_time
            self.lunge = 0.12
            t.hp = min(t.max_hp, t.hp + self.heal)
            game.puff(t.x, t.y - 6, (120, 240, 120), 3, 15)

    def do_repair(self, game, dt):
        t = self.target
        if t is None or not t.alive or t.hp >= t.max_hp:
            self._target_gone(game)
            return
        if self.chase(game, t, INTERACT, dt):
            t.hp = min(t.max_hp, t.hp + REPAIR_RATE * self.work * dt)
            self.timer -= dt
            if self.timer <= 0:
                self.timer = 0.4
                self.lunge = 0.12
                game.puff(*self.muzzle_pos(), (255, 230, 120), 2, 25)

    def do_build(self, game, dt):
        kind, tx, ty = self.build_plan
        s = BUILDINGS[kind]["size"]
        rect = (tx * TILE, ty * TILE, (tx + s) * TILE, (ty + s) * TILE)
        if dist_point_rect(self.x, self.y, rect) - self.radius <= INTERACT:
            game.start_construction(self)
            return
        if self.follow(game, dt):
            self.step_toward(game, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, dt)

    def do_construct(self, game, dt):
        b = self.target
        if b is None or not b.alive or b.complete:
            self._target_gone(game)
            return
        if self.chase(game, b, INTERACT, dt):
            b.add_progress(game, dt * self.work)
            self.timer -= dt
            if self.timer <= 0:
                self.timer = 0.5
                self.lunge = 0.12
