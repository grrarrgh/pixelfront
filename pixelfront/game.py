"""Simulation state: entities, economy, capture points, combat and win conditions."""
import logging
import math
import random
from collections import deque

from . import weapons
from .ai import AI
from .config import (TILE, PLAYER, ENEMY, NEUTRAL, BUILDINGS, START_CREDITS, SUPPLY_CAP,
                     BASE_INCOME, POINT_INCOME, CAPTURE_TIME, CAPTURE_RADIUS, MAX_CAPTURERS,
                     BUILD_GRID, GRID_OFFSET, BUILD_SPEED, SANDBOX_BUILD_SPEED, TRACER_LIFE)
from .entities import Building, CapturePoint, dist_point_rect
from .fog import Fog
from .modules import default_loadout, loadout_cost, loadout_time, loadout_summary
from .units import UNITS
from .units.unit import Unit
from .world import generate

log = logging.getLogger(__name__)
TEAM_NAMES = {PLAYER: "player", ENEMY: "enemy", NEUTRAL: "neutral"}

BOOM_TIME = 0.35  # seconds an explosion flash lasts
YIELD_SPEED = 45  # px/s a soldier sidesteps out of a vehicle's way
TEST_TARGET_SPACING = 2          # tiles between test-range targets
TEST_TARGET_OFFSET = (17, 13)    # tiles from the player's Command Center to the targets (~21 away)


class Team:
    def __init__(self, tid, credits):
        self.id = tid
        self.credits = credits
        self.income = 0.0
        self.supply_used = 0
        self.supply_cap = SUPPLY_CAP
        # The loadout each unit type is currently trained with.
        self.designs = {kind: default_loadout(kind) for kind in UNITS}


TEST_TARGETS = [  # (kind, loadout overrides) for the test range
    ("rifleman", {}), ("rifleman", {"armor": 0}), ("rifleman", {"armor": 2}),
    ("rifleman", {"weapon": 0}), ("rifleman", {"weapon": 2}), ("rifleman", {"engine": 2}),
    ("medic", {}), ("engineer", {}), ("heavy", {}), ("heavy", {"armor": 2, "engine": 0}),
    ("jeep", {}), ("jeep", {"armor": 2, "weapon": 2}), ("tank", {}), ("tank", {"armor": 0, "engine": 2}),
]


class Game:
    def __init__(self, seed=None, sandbox=False):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.world, bases, points = generate(self.rng)
        log.info("New %s: seed %d, map %dx%d, bases at %s and %s, %d derricks",
                 "test range" if sandbox else "match", self.seed, self.world.w, self.world.h,
                 bases[0], bases[1], len(points))
        self.entities = []
        self.units, self.buildings, self.points = [], [], []
        self.projectiles = []
        self.tracers = []    # [x1, y1, x2, y2, age]
        self.booms = []      # [x, y, start time, radius]
        self.particles = []  # [x, y, vx, vy, life, colour]
        self.decals = []
        self.messages = []
        self.teams = {PLAYER: Team(PLAYER, START_CREDITS), ENEMY: Team(ENEMY, START_CREDITS)}
        self.time = 0.0
        self.winner = None
        self.build_speed = BUILD_SPEED * (SANDBOX_BUILD_SPEED if sandbox else 1.0)   # test range builds faster
        self.last_alert = -99.0
        self.alert_pos = None
        self.fog = Fog(self.world)
        self._fog_timer = 0.0
        self._check_timer = 0.0

        for tx, ty in points:
            self.add(CapturePoint(tx, ty))
        for team, (tx, ty) in zip((PLAYER, ENEMY), bases):
            cc = self.add(Building("command", team, tx, ty))
            for kind in ("engineer", "engineer", "rifleman", "rifleman"):
                self.refresh()
                self.spawn_unit(kind, cc, announce=False)
        self.refresh()
        self.sandbox = sandbox
        self.ai = None if sandbox else AI(self, ENEMY)
        if sandbox:
            self.fog.reveal_all = True
            self.teams[PLAYER].credits = 5000
            cc = self.buildings[0]
            helper = AI(self, PLAYER)   # borrow the AI's site finder to lay out the base
            for kind in ("barracks", "yard", "bunker"):
                spot = helper.find_spot(kind, cc)
                if spot:
                    self.add(Building(kind, PLAYER, *spot))
            self.refresh()
            for kind, lo in (("tank", {}), ("jeep", {}), ("heavy", {}), ("rifleman", {"weapon": 0}),
                             ("rifleman", {}), ("rifleman", {"weapon": 2}), ("medic", {})):
                self.refresh()
                self.spawn_unit(kind, cc, dict(default_loadout(kind), **lo), announce=False)
            self.spawn_test_targets()
        self.fog.update(self)

    def spawn_test_targets(self):
        """Passive enemy dummies near the player's base, one of each kind plus loadout variants."""
        cc = next(b for b in self.buildings if b.team == PLAYER)
        cx, cy = cc.center_tile()
        # Well out of sight and range of the starting units, so nothing fires until you send it.
        # The riflemen stand packed together (for splash and suppression tests); the rest spread out.
        ox, oy = cx + TEST_TARGET_OFFSET[0], cy + TEST_TARGET_OFFSET[1]
        packed = [t for t in TEST_TARGETS if t[0] == "rifleman"]
        spread = [t for t in TEST_TARGETS if t[0] != "rifleman"]
        spots = self.spread_spots(ox, oy, len(spread), TEST_TARGET_SPACING)
        taken = set(spots)
        squad = [p for p in self.formation(ox, oy - 5, len(packed) + len(taken)) if p not in taken]
        for (kind, lo), (tx, ty) in zip(spread + packed, spots + squad[:len(packed)]):
            u = self.add(Unit(kind, ENEMY, tx * TILE + TILE / 2, ty * TILE + TILE / 2,
                              dict(default_loadout(kind), **lo)))
            u.passive = True
            u.facing = 180.0
        self.refresh()
        self.notify(PLAYER, "Test targets deployed")

    def spread_spots(self, tx, ty, n, gap):
        """n walkable, unoccupied tiles on a grid `gap` tiles apart, spiralling out from (tx, ty)."""
        taken = {u.tile() for u in self.units}
        out = []
        for r in range(0, 12):
            ring = [(tx + i * gap, ty + j * gap) for j in range(-r, r + 1) for i in range(-r, r + 1)
                    if max(abs(i), abs(j)) == r]
            for p in ring:
                if self.world.walkable(*p) and p not in taken:
                    out.append(p)
                    if len(out) == n:
                        return out
        return out + self.formation(tx, ty, n - len(out))   # crowded map: fall back to packing in

    # ---- bookkeeping ------------------------------------------------------

    def add(self, e):
        self.entities.append(e)
        if not e.is_unit:
            self.world.occupy(e)
        return e

    def refresh(self):
        self.units = [e for e in self.entities if e.is_unit]
        self.buildings = [e for e in self.entities if e.is_building]
        self.points = [e for e in self.entities if e.is_point]
        for t in self.teams.values():
            t.supply_used = 0
            t.income = 0.0
        for u in self.units:
            self.teams[u.team].supply_used += u.supply
        for b in self.buildings:
            t = self.teams[b.team]
            t.supply_used += sum(UNITS[item["kind"]]["supply"] for item in b.queue)
            t.supply_used += sum(u.supply for u in b.occupants)
            if b.kind == "command" and b.complete:
                t.income += BASE_INCOME
        for p in self.points:
            if p.team != NEUTRAL:
                self.teams[p.team].income += POINT_INCOME

    def clock(self):
        """Game time as m:ss, for log lines."""
        t = int(self.time)
        return f"{t // 60}:{t % 60:02d}"

    def notify(self, team, text):
        if team != PLAYER:
            return
        log.debug("%s: message to player: %s", self.clock(), text)
        if self.messages and self.messages[-1][0] == text:
            self.messages[-1][1] = self.time
            return
        self.messages.append([text, self.time])
        del self.messages[:-5]

    def refund(self, team, amount):
        self.teams[team].credits += amount

    def puff(self, x, y, color, n, speed, gravity=1.0, life=0.5):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(0.3, 1.0) * speed
            t = self.rng.uniform(0.6, 1.4) * life
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - speed * 0.5, t, color, gravity])

    # ---- main update ------------------------------------------------------

    def update(self, dt):
        if self.winner is not None:
            return
        self.time += dt
        for e in list(self.entities):
            if e.alive:
                e.update(self, dt)
        for p in self.projectiles:
            p.update(self, dt)
        self._separate(dt)
        self._update_points(dt)
        for t in self.teams.values():
            t.credits += t.income * dt

        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 120 * p[6] * dt
            p[4] -= dt
        for d in self.decals:
            if d["kind"] == "wreck" and self.time - d["t"] < d["life"] - 5 and self.rng.random() < dt * 6:
                self.particles.append([d["x"] + self.rng.uniform(-4, 4), d["y"] - 6, self.rng.uniform(-3, 3),
                                       -14, self.rng.uniform(0.8, 1.6), (70, 66, 64), 0.0])
        self.particles = [p for p in self.particles if p[4] > 0]
        for tr in self.tracers:
            tr[4] += dt
        self.tracers = [tr for tr in self.tracers if tr[4] < TRACER_LIFE]
        self.booms = [b for b in self.booms if self.time - b[2] < BOOM_TIME]
        self.decals = [d for d in self.decals if self.time - d["t"] < d["life"]]
        self.messages = [m for m in self.messages if self.time - m[1] < 6]

        self.entities = [e for e in self.entities if e.alive]
        self.projectiles = [p for p in self.projectiles if p.alive]
        self.refresh()
        if self.ai:
            self.ai.update(dt)

        self._fog_timer -= dt
        if self._fog_timer <= 0:
            self._fog_timer = 0.2
            self.fog.update(self)

        self._check_timer -= dt
        if self._check_timer <= 0:
            self._check_timer = 0.5
            alive = {b.team for b in self.buildings}
            if PLAYER not in alive:
                self.winner = ENEMY
            elif ENEMY not in alive:
                self.winner = PLAYER
            if self.winner is not None:
                log.info("%s: %s wins (all %s buildings destroyed)", self.clock(), TEAM_NAMES[self.winner],
                         TEAM_NAMES[ENEMY if self.winner == PLAYER else PLAYER])

    def _update_points(self, dt):
        for p in self.points:
            counts = {}
            for u in self.units:
                if abs(u.x - p.x) <= CAPTURE_RADIUS and abs(u.y - p.y) <= CAPTURE_RADIUS \
                        and math.hypot(u.x - p.x, u.y - p.y) <= CAPTURE_RADIUS:
                    counts[u.team] = counts.get(u.team, 0) + 1
            p.contested = len(counts) > 1
            if len(counts) != 1:
                if not counts and p.team == NEUTRAL and p.progress > 0:
                    p.progress = max(0.0, p.progress - dt / (CAPTURE_TIME * 2))
                continue
            team, n = next(iter(counts.items()))
            rate = min(n, MAX_CAPTURERS) / CAPTURE_TIME * dt
            if p.team == team:
                p.progress = min(1.0, p.progress + rate)
            elif p.team != NEUTRAL or (p.capturer not in (None, team) and p.progress > 0):
                # Someone else owns it (or was part-way there): wind their progress down first.
                p.progress -= rate
                if p.progress <= 0:
                    p.progress = 0.0
                    p.capturer = None
                    if p.team != NEUTRAL:
                        lost = p.team
                        p.team = NEUTRAL
                        log.info("%s: derrick at %s neutralised by %s", self.clock(), p.center_tile(),
                                 TEAM_NAMES[team])
                        self.notify(lost, "Derrick lost")
            else:
                p.capturer = team
                p.progress += rate
                if p.progress >= 1.0:
                    p.progress = 1.0
                    p.team = team
                    log.info("%s: derrick at %s captured by %s", self.clock(), p.center_tile(), TEAM_NAMES[team])
                    self.notify(team, "Derrick captured")

    def _separate(self, dt):
        """Gently push overlapping units apart."""
        us = self.units
        k = min(1.0, dt * 8)
        n = len(us)
        for i in range(n):
            a = us[i]
            for j in range(i + 1, n):
                b = us[j]
                need = a.radius + b.radius
                dx, dy = b.x - a.x, b.y - a.y
                if dx >= need or dx <= -need or dy >= need or dy <= -need:
                    continue
                d2 = dx * dx + dy * dy
                if d2 >= need * need:
                    continue
                if d2 < 0.01:
                    ang = (a.id * 2.399) % math.tau
                    ux, uy, d = math.cos(ang), math.sin(ang), 0.0
                else:
                    d = math.sqrt(d2)
                    ux, uy = dx / d, dy / d
                push = (need - d) * 0.5 * k
                veh = a if a.is_vehicle else b if b.is_vehicle else None
                if veh is not None and veh.moving and (a.is_infantry or b.is_infantry):
                    # Infantry give way to a moving vehicle; it doesn't get shoved by soldiers.
                    # (A parked vehicle shares the push, so soldiers can squeeze past it.)
                    if a is veh:
                        self._nudge(b, ux * push * 2, uy * push * 2)
                    else:
                        self._nudge(a, -ux * push * 2, -uy * push * 2)
                    continue
                self._nudge(a, -ux * push, -uy * push)
                self._nudge(b, ux * push, uy * push)

        # Soldiers standing in a moving vehicle's path step aside before it reaches them.
        for v in us:
            if not (v.is_vehicle and v.moving):
                continue
            a = math.radians(v.facing)
            fx, fy = math.cos(a), math.sin(a)
            reach = v.radius + 14
            for u in us:
                if u.is_vehicle:
                    continue
                dx, dy = u.x - v.x, u.y - v.y
                ahead = dx * fx + dy * fy
                side = -dx * fy + dy * fx
                if 0 < ahead < reach and abs(side) < v.radius + u.radius + 2:
                    s = 1 if side >= 0 else -1
                    self._nudge(u, -fy * s * YIELD_SPEED * dt, fx * s * YIELD_SPEED * dt)

    def _nudge(self, u, dx, dy):
        if self.world.walkable_px(u.x + dx, u.y + dy):
            u.x += dx
            u.y += dy

    # ---- queries ----------------------------------------------------------

    def seen(self, e):
        """Whether the player can currently see (units) or has discovered (structures) an entity."""
        if e.team == PLAYER:
            return True
        fog = self.fog
        if e.is_unit:
            tx, ty = e.tile()
            return fog.visible[ty * fog.w + tx] == 1
        for y in range(e.ty, e.ty + e.size):
            for x in range(e.tx, e.tx + e.size):
                if fog.explored[y * fog.w + x]:
                    return True
        return False

    def find_enemy_near(self, unit, radius):
        best, bd = None, radius
        for e in self.units:
            if e.team != unit.team:
                d = math.hypot(e.x - unit.x, e.y - unit.y)
                if d < bd:
                    best, bd = e, d
        if best:
            return best
        for b in self.buildings:
            if b.team != unit.team:
                d = dist_point_rect(unit.x, unit.y, b.rect())
                if d < bd:
                    best, bd = b, d
        return best

    def find_patient(self, medic, radius):
        best, bd = None, radius
        for u in self.units:
            if u.team == medic.team and u.is_infantry and u.hp < u.max_hp and u is not medic:
                d = math.hypot(u.x - medic.x, u.y - medic.y)
                if d < bd:
                    best, bd = u, d
        return best

    def free_tile_near(self, rect, near=None):
        """Closest open tile around a tile rect, preferring tiles near `near` (default: below it)."""
        x0, y0, x1, y1 = rect
        occupied = {u.tile() for u in self.units if u.alive}
        cx, cy = near if near else ((x0 + x1) / 2, y1 + 1)
        for r in range(1, 14):
            ring = [(x, y) for y in range(y0 - r, y1 + r + 1) for x in range(x0 - r, x1 + r + 1)
                    if max(x0 - x, x - x1, y0 - y, y - y1) == r]
            ring.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            for p in ring:
                if self.world.walkable(*p) and p not in occupied:
                    return p
        return (x0, y1 + 1)

    def formation(self, tx, ty, n):
        """n distinct walkable tiles clustered around (tx, ty)."""
        w = self.world
        if not w.walkable(tx, ty):
            tx, ty = self.free_tile_near((tx, ty, tx, ty), near=(tx, ty))
        out, seen, q = [], {(tx, ty)}, deque([(tx, ty)])
        while q and len(out) < n:
            x, y = q.popleft()
            out.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = (x + dx, y + dy)
                if p not in seen and w.walkable(*p):
                    seen.add(p)
                    q.append(p)
        while len(out) < n:
            out.append(out[-1])
        return out

    def can_place(self, kind, tx, ty, team=None):
        """Buildings sit on the build grid (every tile, by default), on clear ground, with a tile
        of clearance from any other structure, so there are always lanes for units to move through."""
        s = BUILDINGS[kind]["size"]
        if (tx - GRID_OFFSET) % BUILD_GRID or (ty - GRID_OFFSET) % BUILD_GRID:
            return False
        if not all(self.placeable_tile(x, y, team) for y in range(ty, ty + s) for x in range(tx, tx + s)):
            return False
        w = self.world
        for y in range(ty - 1, ty + s + 1):
            for x in range(tx - 1, tx + s + 1):
                if w.in_bounds(x, y) and w.occupant[y * w.w + x] is not None:
                    return False
        return True

    @staticmethod
    def snap_to_grid(tx, ty):
        """Nearest build-grid origin to a tile position."""
        snap = lambda v: int(round((v - GRID_OFFSET) / BUILD_GRID)) * BUILD_GRID + GRID_OFFSET
        return snap(tx), snap(ty)

    def placeable_tile(self, x, y, team=None):
        if not self.world.buildable(x, y):
            return False
        if team == PLAYER and not self.fog.explored[y * self.world.w + x]:
            return False
        return True

    # ---- commands ---------------------------------------------------------

    def command_move(self, units, tx, ty, attack=False):
        spots = self.formation(tx, ty, len(units))
        cx, cy = tx * TILE + TILE / 2, ty * TILE + TILE / 2
        ordered = sorted(units, key=lambda u: (u.x - cx) ** 2 + (u.y - cy) ** 2)
        for u, (sx, sy) in zip(ordered, spots):
            if attack:
                u.order_amove(self, sx, sy)
            else:
                u.order_move(self, sx, sy)

    def train(self, building, kind):
        team = self.teams[building.team]
        loadout = dict(team.designs[kind])
        cost = loadout_cost(kind, loadout)
        if len(building.queue) >= 5:
            self.notify(building.team, "Queue is full")
            return False
        if team.credits < cost:
            self.notify(building.team, "Not enough credits")
            return False
        if team.supply_used + UNITS[kind]["supply"] > team.supply_cap:
            self.notify(building.team, "Supply limit reached")
            return False
        team.credits -= cost
        team.supply_used += UNITS[kind]["supply"]
        building.queue.append(dict(kind=kind, loadout=loadout, cost=cost, time=loadout_time(kind, loadout)))
        log.info("%s: %s queued %s at %s (%s) for %d credits", self.clock(), TEAM_NAMES[building.team],
                 kind, building.name, loadout_summary(kind, loadout), cost)
        return True

    def cancel_train(self, building, index):
        if 0 <= index < len(building.queue):
            item = building.queue.pop(index)
            self.refund(building.team, item["cost"])
            if index == 0:
                building.prod_timer = 0.0
            self.refresh()
            log.info("%s: %s cancelled %s at %s (refund %d)", self.clock(), TEAM_NAMES[building.team],
                     item["kind"], building.name, item["cost"])

    def cancel_construction(self, building):
        if building.alive and not building.complete:
            self.refund(building.team, BUILDINGS[building.kind]["cost"])
            building.alive = False
            self.world.vacate(building)
            self.puff(building.x, building.y, (190, 160, 110), 12, 40)
            log.info("%s: %s cancelled construction of %s at %s", self.clock(), TEAM_NAMES[building.team],
                     building.name, (building.tx, building.ty))

    def start_construction(self, worker):
        kind, tx, ty = worker.build_plan
        worker.build_plan = None
        if not self.can_place(kind, tx, ty):
            self.refund(worker.team, BUILDINGS[kind]["cost"])
            self.notify(worker.team, "Can't build there")
            log.info("%s: %s could not start %s at %s (site blocked), refunded", self.clock(),
                     TEAM_NAMES[worker.team], kind, (tx, ty))
            worker.stop(self)
            return
        b = self.add(Building(kind, worker.team, tx, ty, complete=False))
        log.info("%s: %s started building %s at %s", self.clock(), TEAM_NAMES[worker.team], b.name, (tx, ty))
        self._push_out(b)
        worker.order_construct(self, b)

    def _push_out(self, structure):
        rect = structure.tile_rect()
        x0, y0, x1, y1 = rect
        for u in self.units:
            tx, ty = u.tile()
            if x0 <= tx <= x1 and y0 <= ty <= y1:
                nx, ny = self.free_tile_near(rect, near=(tx, ty))
                u.x, u.y = nx * TILE + TILE / 2, ny * TILE + TILE / 2
                if u.goal:
                    u.plan_to(self, *u.goal)

    def spawn_unit(self, kind, building, loadout=None, announce=True):
        rally = building.rally
        near = None
        if rally is not None:
            near = rally.center_tile() if hasattr(rally, "center_tile") else rally
        tx, ty = self.free_tile_near(building.tile_rect(), near=near)
        u = self.add(Unit(kind, building.team, tx * TILE + TILE / 2, ty * TILE + TILE / 2, loadout))
        if rally is not None:
            dest = rally.center_tile() if hasattr(rally, "center_tile") else rally
            u.order_move(self, *self.formation(*dest, 1)[0])
        if announce:
            self.notify(building.team, f"{u.name} ready")
            log.info("%s: %s %s ready at %s (#%d, %s)", self.clock(), TEAM_NAMES[u.team], u.name,
                     building.name, u.id, loadout_summary(kind, u.loadout))
        return u

    # ---- combat -----------------------------------------------------------

    def attack(self, attacker, target, mult=1.0, origin=None):
        """Fire one round of the attacker's weapon (see weapons.fire)."""
        weapons.fire(self, attacker, target, mult, origin)

    def enter(self, unit, bunker):
        """A soldier climbs into a bunker: off the map until unloaded or the bunker falls."""
        if len(bunker.occupants) >= bunker.capacity:
            self.notify(unit.team, "Bunker is full")
            return False
        unit.order = "idle"
        unit.path = []
        unit.target = None
        unit.suppressed = False
        unit.suppression = 0.0
        unit.kneel = 0.0
        unit.inside = bunker
        bunker.occupants.append(unit)
        if unit in self.entities:
            self.entities.remove(unit)
        log.info("%s: %s %s #%d entered the bunker at %s (%d/%d)", self.clock(), TEAM_NAMES[unit.team],
                 unit.name, unit.id, (bunker.tx, bunker.ty), len(bunker.occupants), bunker.capacity)
        return True

    def unload(self, bunker):
        """Everyone out, onto open tiles around the bunker."""
        if bunker.occupants:
            log.info("%s: %d soldiers left the bunker at %s%s", self.clock(), len(bunker.occupants),
                     (bunker.tx, bunker.ty), "" if bunker.alive else " as it fell")
        for u in bunker.occupants:
            tx, ty = self.free_tile_near(bunker.tile_rect())
            u.x, u.y = tx * TILE + TILE / 2, ty * TILE + TILE / 2
            u.inside = None
            u.target = None
            self.add(u)
            self.refresh()
        bunker.occupants = []

    def boom(self, x, y, r):
        """An explosion flash for the renderer to draw."""
        self.booms.append([x, y, self.time, r])

    def damage(self, target, amount, attacker=None):
        if not target.alive or target.team == NEUTRAL:
            return
        dmg = max(1, amount - target.armor) * self.rng.uniform(0.8, 1.0)
        target.hp -= dmg
        target.flash = 0.08
        self.puff(target.x, target.y - 3, (255, 230, 160), 2, 30)
        if target.team == PLAYER and self.time - self.last_alert > 12:
            self.last_alert = self.time
            self.alert_pos = (target.x, target.y)
            self.notify(PLAYER, "We are under attack!")
        if (attacker is not None and attacker.alive and attacker.team != target.team
                and not getattr(target, "passive", False)):
            if target.is_unit and target.order == "idle" and target.armed:
                target.order = "attack"
                target.target = attacker
                target.repath = 0.0
            for u in self.units:
                if (u.team == target.team and u.order == "idle" and u.armed and u.kind != "engineer"
                        and not u.passive
                        and abs(u.x - target.x) < 96 and abs(u.y - target.y) < 96):
                    u.order = "attack"
                    u.target = attacker
                    u.repath = 0.0
        if target.hp <= 0:
            self.kill(target, attacker)

    def kill(self, e, killer=None):
        if not e.alive:
            return
        e.alive = False
        by = f" by {TEAM_NAMES[killer.team]} {killer.name} #{killer.id}" if killer is not None else ""
        if e.is_unit:
            log.info("%s: %s %s #%d killed%s", self.clock(), TEAM_NAMES[e.team], e.name, e.id, by)
        elif e.is_building:
            log.info("%s: %s %s at %s destroyed%s", self.clock(), TEAM_NAMES[e.team], e.name, (e.tx, e.ty), by)
        if e.is_unit:
            if e.build_plan:
                self.refund(e.team, BUILDINGS[e.build_plan[0]]["cost"])
                e.build_plan = None
            # The renderer animates these: infantry topple and fade, vehicles blow up and smoulder.
            death = dict(x=e.x, y=e.y, t=self.time, unit=e.kind, team=e.team, loadout=e.loadout,
                         facing=e.facing, r=e.radius, prone=e.suppressed,
                         turret=e.turret - e.facing if e.has_turret else 0.0)
            if e.is_vehicle:
                self.decals.append(dict(death, kind="wreck", life=30))
                self.puff(e.x, e.y - 4, (255, 220, 120), 10, 70)
                self.puff(e.x, e.y - 4, (250, 130, 40), 22, 55)
                self.puff(e.x, e.y - 6, (90, 86, 84), 12, 20, gravity=-0.2, life=1.2)
            else:
                self.decals.append(dict(death, kind="fall", life=20))
                self.puff(e.x, e.y - 4, (170, 30, 30), 6, 35)
            return
        self.world.vacate(e)
        if e.is_building and e.occupants:
            self.unload(e)   # the garrison scrambles out of the ruins
        stones = [(self.rng.randrange(e.size * TILE - 4), self.rng.randrange(e.size * TILE - 4),
                   self.rng.choice(((96, 92, 90), (130, 120, 104), (70, 66, 64))))
                  for _ in range(e.size * 10)]
        self.decals.append(dict(kind="rubble", x=e.tx * TILE, y=e.ty * TILE, size=e.size,
                                stones=stones, t=self.time, life=60))
        self.puff(e.x, e.y, (250, 150, 50), 30, 70)
        self.puff(e.x, e.y, (110, 104, 100), 24, 50)
        if e.team == PLAYER:
            self.notify(PLAYER, f"{e.name} destroyed")
