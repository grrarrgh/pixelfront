"""Map entities: the Entity base, buildings and capture points. Units are in units/."""
import logging
import math

from .config import TILE, BUILDINGS, NEUTRAL, POINT_SIGHT, BURST_GAP

# What manning a structure does for its garrison unless BUILDINGS[kind]["garrison"] says otherwise.
GARRISON_DEFAULTS = dict(reload=1.0, damage=1.0, range=1.0, heal=0.0, sight=0)
# Where shots leave a garrisoned structure: (reach towards the target in x, in y, height above centre).
FIRING_PORTS = {"bunker": (9, 5, -7), "tower": (3, 2, -22)}


log = logging.getLogger(__name__)


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
        self.base_sight = st["sight"]
        self.complete = complete
        self.progress = 1.0 if complete else 0.0
        self.hp = self.max_hp if complete else self.max_hp * 0.1
        self.queue = []  # dicts: kind, loadout, cost, time
        self.prod_timer = 0.0
        self.rally = None  # a tile (tx, ty) or a CapturePoint
        self.capacity = st.get("capacity", 0)   # infantry it can hold (bunkers, towers)
        self.occupants = []
        self.garrison = dict(GARRISON_DEFAULTS, **st.get("garrison", {}))

    @property
    def sight(self):
        """Manned lookouts see further."""
        return self.base_sight + (self.garrison["sight"] if self.occupants else 0)

    def add_progress(self, game, dt):
        inc = dt * game.build_speed / self.stats["time"]
        self.progress = min(1.0, self.progress + inc)
        self.hp = min(self.max_hp, self.hp + self.max_hp * 0.9 * inc)
        if self.progress >= 1.0:
            self.complete = True
            game.notify(self.team, f"{self.name} complete")
            log.info("%s: %s %s at %s complete", game.clock(), "player" if self.team == 0 else "enemy",
                     self.name, (self.tx, self.ty))

    def update(self, game, dt):
        self.flash = max(0.0, self.flash - dt)
        if self.complete and self.occupants:
            self._man_the_walls(game, dt)
        if not self.complete or not self.queue:
            return
        self.prod_timer += dt * game.build_speed
        item = self.queue[0]
        if self.prod_timer >= item["time"]:
            self.prod_timer = 0.0
            self.queue.pop(0)
            game.spawn_unit(item["kind"], self, item["loadout"])

    def _man_the_walls(self, game, dt):
        """Garrisoned soldiers shoot from the structure with its garrison bonuses (a bunker:
        faster reloads, more damage and range, slow healing; a tower: much more range)."""
        reach = self.size * TILE / 2
        gar = self.garrison
        for u in self.occupants:
            u.x, u.y = self.x, self.y
            u.hp = min(u.max_hp, u.hp + gar["heal"] * dt)
            u.cooldown -= dt
            u.lunge = max(0.0, u.lunge - dt)
            if not u.armed:
                continue
            rng = u.range * gar["range"] + reach
            t = u.target
            if t is None or not t.alive or u.edge_dist(t) > rng:
                t = u.target = game.find_enemy_near(u, rng)
            if t is None:
                u.burst_left = 0
                continue
            u.face(t.x, t.y)
            if u.burst_left > 0:
                u.burst_timer -= dt
                if u.burst_timer <= 0:
                    u.burst_left -= 1
                    u.burst_timer = BURST_GAP
                    game.attack(u, t, gar["damage"], self.firing_port(t))
            elif u.cooldown <= 0:
                u.cooldown = u.attack_time * gar["reload"]
                u.lunge = 0.12
                u.burst_left, u.burst_timer = u.burst - 1, BURST_GAP
                game.attack(u, t, gar["damage"], self.firing_port(t))

    def firing_port(self, target):
        """Where shots leave the structure: the slit (or parapet) facing the target."""
        rx, ry, up = FIRING_PORTS.get(self.kind, (9, 5, -7))
        a = math.atan2(target.y - self.y, target.x - self.x)
        return self.x + math.cos(a) * rx, self.y + up + math.sin(a) * ry
