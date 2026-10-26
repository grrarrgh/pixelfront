"""Units, buildings, capture points and projectiles."""
import math

from .config import (TILE, UNITS, BUILDINGS, NEUTRAL, INTERACT, REPAIR_RATE, POINT_SIGHT, PRONE_SPEED,
                     SUPPRESS_ON, SUPPRESS_OFF, SUPPRESS_DECAY, SUPPRESS_CALM, PRONE_RANGE,
                     TURRET_SPEED, KNEEL_TIME)
from .modules import compute_stats, default_loadout
from .pathfinding import find_path


def dist_point_rect(px, py, rect):
    l, t, r, b = rect
    dx = max(l - px, 0.0, px - r)
    dy = max(t - py, 0.0, py - b)
    return math.hypot(dx, dy)


class Entity:
    _next_id = 0
    is_unit = is_building = is_point = False
    is_vehicle = is_infantry = False
    radius = 5
    armor = 0
    sight = 0

    def __init__(self, kind, team, x, y):
        Entity._next_id += 1
        self.id = Entity._next_id
        self.kind = kind
        self.team = team
        self.x, self.y = x, y
        self.alive = True
        self.flash = 0.0
        self.hp = self.max_hp = 1

    def tile(self):
        return int(self.x // TILE), int(self.y // TILE)

    def update(self, game, dt):
        pass


class Structure(Entity):
    def __init__(self, kind, team, tx, ty, size):
        super().__init__(kind, team, (tx + size / 2) * TILE, (ty + size / 2) * TILE)
        self.tx, self.ty, self.size = tx, ty, size

    def rect(self):
        return (self.tx * TILE, self.ty * TILE,
                (self.tx + self.size) * TILE, (self.ty + self.size) * TILE)

    def tile_rect(self):
        return (self.tx, self.ty, self.tx + self.size - 1, self.ty + self.size - 1)

    def center_tile(self):
        return self.tx + self.size // 2, self.ty + self.size // 2


class CapturePoint(Structure):
    """An oil derrick. Owned by whoever captured it last; pays its owner credits."""
    is_point = True
    name = "Oil Derrick"
    sight = POINT_SIGHT

    def __init__(self, tx, ty):
        super().__init__("derrick", NEUTRAL, tx, ty, 1)
        self.progress = 0.0   # 0..1 towards `capturer` owning it (1 when owned)
        self.capturer = None  # team currently making progress
        self.contested = False


class Building(Structure):
    is_building = True

    def __init__(self, kind, team, tx, ty, complete=True):
        st = BUILDINGS[kind]
        super().__init__(kind, team, tx, ty, st["size"])
        self.stats = st
        self.name = st["name"]
        self.max_hp = st["hp"]
        self.armor = st["armor"]
        self.sight = st["sight"]
        self.complete = complete
        self.progress = 1.0 if complete else 0.0
        self.hp = self.max_hp if complete else self.max_hp * 0.1
        self.queue = []  # dicts: kind, loadout, cost, time
        self.prod_timer = 0.0
        self.rally = None  # a tile (tx, ty) or a CapturePoint

    def add_progress(self, game, dt):
        inc = dt / self.stats["time"]
        self.progress = min(1.0, self.progress + inc)
        self.hp = min(self.max_hp, self.hp + self.max_hp * 0.9 * inc)
        if self.progress >= 1.0:
            self.complete = True
            game.notify(self.team, f"{self.name} complete")

    def update(self, game, dt):
        self.flash = max(0.0, self.flash - dt)
        if not self.complete or not self.queue:
            return
        self.prod_timer += dt
        item = self.queue[0]
        if self.prod_timer >= item["time"]:
            self.prod_timer = 0.0
            self.queue.pop(0)
            game.spawn_unit(item["kind"], self, item["loadout"])


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
        self.radius = base["radius"]
        self.weapon = st["weapon"]   # the loadout can swap the weapon type
        self.supply = base["supply"]
        self.max_hp = self.hp = max(1, round(st["hp"]))
        self.armor = round(st["armor"])
        self.damage = st["damage"]
        self.range = st["range"]
        self.attack_time = st["cooldown"]
        self.speed = st["speed"]
        self.sight = int(round(st["sight"]))
        self.heal = st["heal"]
        self.work = st["work"]
        self.vs_vehicle = st["vs_vehicle"]
        self.accuracy = st["accuracy"]
        self.passive = False  # test-range targets never acquire or return fire
        self.armed = self.damage > 0 and self.weapon is not None

        self.order = "idle"
        self.path = []
        self.goal = None         # (tile_rect, adjacent) the current path leads to
        self.target = None
        self.amove_dest = None
        self.build_plan = None   # (kind, tx, ty), credits already paid
        self.timer = 0.0

        self.cooldown = 0.0
        self.scan = 0.0
        self.repath = 0.0
        self.facing = 0.0        # degrees, 0 = east, 90 = south (screen down)
        self.moving = False
        self.anim = 0.0          # advances while moving; drives walk/crawl frames
        self.lunge = 0.0         # >0 just after firing/working; drives the recoil frame

        # Suppression (infantry only): heavy fire pins soldiers down; they crawl and take
        # less bullet damage until the fire lets up.
        self.suppression = 0.0
        self.suppressed = False
        self.calm = 0.0

        # Vehicles aim a turret (absolute degrees) independently of the hull, except
        # fixed-gun artillery, which has to turn the whole vehicle.
        self.has_turret = self.is_vehicle and self.weapon != "artillery"
        self.turret = self.facing
        self.aiming = False
        # Heavy infantry kneel before firing; this counts up to KNEEL_TIME while they settle.
        self.kneel = 0.0

    def rect(self):
        r = self.radius
        return (self.x - r, self.y - r, self.x + r, self.y + r)

    def tile_rect(self):
        tx, ty = self.tile()
        return (tx, ty, tx, ty)

    def muzzle_pos(self):
        from .sprites import muzzle_offset  # geometry lives with the 3D models
        dx, dy = muzzle_offset(self.kind, self.loadout, self.facing, self.suppressed,
                               self.turret - self.facing if self.has_turret else 0.0, self.kneeling)
        return self.x + dx, self.y + dy

    @property
    def move_speed(self):
        return self.speed * (PRONE_SPEED if self.suppressed else 1.0)

    @property
    def kneeling(self):
        return self.kind == "heavy" and self.kneel > 0 and not self.suppressed

    @property
    def attack_range(self):
        return self.range * (PRONE_RANGE if self.suppressed else 1.0)

    def aim_at(self, x, y, dt):
        """Turn the turret (or hull, for fixed guns) towards a point. Returns True once on target."""
        want = math.degrees(math.atan2(y - self.y, x - self.x)) % 360
        if not self.has_turret:
            self.face(x, y)
            return True
        diff = (want - self.turret + 180) % 360 - 180
        step = TURRET_SPEED * dt
        self.turret = want if abs(diff) <= step else (self.turret + math.copysign(step, diff)) % 360
        return abs(diff) <= 8

    def _relax_turret(self, dt):
        if self.has_turret:
            diff = (self.facing - self.turret + 180) % 360 - 180
            step = TURRET_SPEED * 0.5 * dt
            self.turret = self.facing if abs(diff) <= step else (self.turret + math.copysign(step, diff)) % 360

    def suppress(self, amount):
        if not self.is_infantry:
            return
        self.suppression = min(100.0, self.suppression + amount)
        self.calm = SUPPRESS_CALM
        if self.suppression >= SUPPRESS_ON:
            self.suppressed = True

    def _update_suppression(self, dt):
        if self.calm > 0:
            self.calm -= dt
        elif self.suppression > 0:
            self.suppression = max(0.0, self.suppression - SUPPRESS_DECAY * dt)
        if self.suppressed and self.suppression < SUPPRESS_OFF:
            self.suppressed = False

    def edge_dist(self, other):
        if other.is_unit:
            return max(0.0, math.hypot(other.x - self.x, other.y - self.y) - self.radius - other.radius)
        return max(0.0, dist_point_rect(self.x, self.y, other.rect()) - self.radius)

    @property
    def status(self):
        if self.suppressed:
            return "Pinned down!"
        if self.order == "build":
            return "Going to build " + BUILDINGS[self.build_plan[0]]["name"]
        return {"idle": "Idle", "move": "Moving", "amove": "Attack-moving", "attack": "Attacking",
                "heal": "Healing", "repair": "Repairing", "construct": "Building"}[self.order]

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
        self.repath = 0.0

    def plan_to(self, game, rect, adjacent):
        self.goal = (rect, adjacent)
        self.path = find_path(game.world, self.tile(), rect, adjacent)

    def plan_to_tile(self, game, tx, ty):
        self.plan_to(game, (tx, ty, tx, ty), not game.world.walkable(tx, ty))

    def stop(self, game):
        self._reset(game)

    def order_move(self, game, tx, ty):
        self._reset(game)
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

    def follow(self, game, dt):
        """Advance along the current path. Returns True once there is nowhere left to go."""
        if not self.path:
            return True
        world = game.world
        tx, ty = self.path[0]
        if not world.walkable(tx, ty):
            self.path = find_path(world, self.tile(), *self.goal) if self.goal else []
            if not self.path or not world.walkable(*self.path[0]):
                self.path = []
                return True
            tx, ty = self.path[0]
        gx, gy = tx * TILE + TILE / 2, ty * TILE + TILE / 2
        dx, dy = gx - self.x, gy - self.y
        d = math.hypot(dx, dy)
        step = self.move_speed * dt
        self.moving = True
        self.face(gx, gy)
        if d <= step:
            self.x, self.y = gx, gy
            self.path.pop(0)
            return not self.path
        self.x += dx / d * step
        self.y += dy / d * step
        return False

    def step_toward(self, game, gx, gy, dt):
        dx, dy = gx - self.x, gy - self.y
        d = math.hypot(dx, dy)
        if d < 0.5:
            return
        step = min(d, self.move_speed * dt)
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
        self.face(gx, gy)

    def chase(self, game, target, reach, dt):
        """Close in on target until within `reach` px of its edge. Returns True once there."""
        d = self.edge_dist(target)
        if d <= reach:
            self.path = []
            if not self.has_turret:   # turreted vehicles aim with the turret, not the hull
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
        self.flash = max(0.0, self.flash - dt)
        self.lunge = max(0.0, self.lunge - dt)
        self._update_suppression(dt)
        self.moving = False
        self.aiming = False
        getattr(self, "do_" + self.order)(game, dt)
        if self.moving:
            self.anim += dt * self.move_speed / self.speed
            self.kneel = 0.0   # heavy infantry stand up to move
        if not self.aiming:
            self._relax_turret(dt)

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
            enemy = game.find_enemy_near(self, self.sight * TILE)
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
        if t is None or not t.alive:
            self._target_gone(game)
            return
        if not self.chase(game, t, self.attack_range, dt):
            return
        self.aiming = True
        on_target = self.aim_at(t.x, t.y, dt)
        if self.kind == "heavy" and not self.suppressed and self.kneel < KNEEL_TIME:
            self.kneel += dt   # kneel down before the first shot
            return
        if on_target and self.cooldown <= 0:
            self.cooldown = self.attack_time
            self.lunge = 0.12
            game.attack(self, t)

    def do_heal(self, game, dt):
        t = self.target
        if t is None or not t.alive or t.hp >= t.max_hp:
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


# Projectile kinds. speed in px/s; arc = peak height in px (0 = flies straight and homes in on
# its target; arcing shots are lobbed at the spot the target stood on); splash = blast radius
# in px (0 = direct hit only); boom = explosion size drawn; trail = what it leaves behind.
PROJECTILES = {
    "rocket":     dict(speed=150, arc=0, splash=0, boom=5, trail="smoke"),
    "atgm":       dict(speed=130, arc=0, splash=0, boom=6, trail="wire"),
    "shell":      dict(speed=220, arc=0, splash=0, boom=6, trail=None),
    "autocannon": dict(speed=320, arc=0, splash=5, boom=2, trail=None),
    "grenade":    dict(speed=100, arc=14, splash=12, boom=5, trail=None),
    "artillery":  dict(speed=120, arc=55, splash=22, boom=10, trail="smoke"),
}


class Projectile:
    """Flies over the ground at (gx, gy) at height h; drawn at (x, y) = (gx, gy - h)."""

    def __init__(self, source, target, damage, style, start, miss_offset=None):
        spec = PROJECTILES[style]
        self.source = source
        self.target = target
        self.damage = damage
        self.style = style
        self.team = source.team
        self.vs_vehicle = source.vs_vehicle
        self.speed, self.arc, self.splash = spec["speed"], spec["arc"], spec["splash"]
        self.boom, self.trail = spec["boom"], spec["trail"]
        self.gx, self.gy = source.x, source.y
        self.h0 = self.h = max(0.0, source.y - start[1])
        self.x, self.y = start
        # Misses and lobbed shots fly at a fixed spot; straight hits home in on the target.
        self.locked = self.arc > 0 or miss_offset is not None
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
        if self.splash:
            game.splash(x, y, self.splash, self.damage, self.vs_vehicle, self.team, self.source)
        elif not self.locked and t.alive:
            game.damage(t, self.damage * (self.vs_vehicle if t.is_vehicle else 1.0), self.source)
        game.blast(x, y, max(self.splash, 14))
        game.boom(x, y - 2, self.boom)
        game.puff(x, y - 2, (200, 180, 140), 3 + self.boom, 20 + self.boom * 3)
