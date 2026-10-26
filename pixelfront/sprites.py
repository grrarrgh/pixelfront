"""Pixel art for the game. Units are pre-rendered from the small 3D models in model3d.py
(any facing, any loadout, every animation frame) on first use and cached; buildings, icons
and terrain are painted directly.
"""
import math
import random

import pygame

from . import model3d as m3
from .config import TILE, TEAM_COLORS, PLAYER, ENEMY, KNEEL_TIME, STEER_MAX
from .units import UNITS
from .modules import default_loadout
from .world import SAND, DUNE, ROCK, CLIFF, RAMP, HIGH

K = (20, 20, 26)
GOLD = (248, 208, 72)
CYAN = (110, 232, 244)
CLEAR = (0, 0, 0, 0)

BASE_PAL = {"k": K, "w": (240, 240, 240)}

CURSOR_ART = [
    "k.........",
    "kk........",
    "kwk.......",
    "kwwk......",
    "kwwwk.....",
    "kwwwwk....",
    "kwwwwwk...",
    "kwwwwwwk..",
    "kwwwwkkkk.",
    "kwkwwk....",
    "kk.kwwk...",
    "....kk....",
]


def art_surface(rows, pal):
    w = max(len(r) for r in rows)
    surf = pygame.Surface((w, len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            col = pal.get(c)
            if col:
                surf.set_at((x, y), col)
    return surf


def silhouette(surf, color=(255, 255, 255)):
    return pygame.mask.from_surface(surf).to_surface(setcolor=color + (255,), unsetcolor=CLEAR)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


# ---- units ------------------------------------------------------------------

ICON_FACING = 30          # degrees; three-quarter view used for icons and portraits
FACINGS = {"infantry": 8, "vehicle": 16}

# Animation -> frame count. Infantry "prone"/"pfire" are the pinned-down crawl and prone firing.
FRAMES = {
    "infantry": dict(idle=4, walk=4, fire=2, work=2, prone=2, pfire=2, kneel=2, kfire=2, die=4, check=2),
    "vehicle": dict(idle=2, walk=3, fire=2, die=1, idlegun=len(m3.IDLE_ELEV)),
}
DEATH_STEPS = (0.08, 0.18, 0.3)   # seconds at which each infantry death frame ends
WALK_RATE = {"infantry": 8.0, "vehicle": 10.0}  # frames per second at the unit's base speed


def unit_anim(u):
    """(animation, frame) for a unit's current state."""
    busy = u.order in ("attack", "heal", "repair", "construct") and not u.moving
    firing = u.lunge > 0.05
    if u.is_infantry and u.suppressed:
        if busy and u.order == "attack":
            return "pfire", int(firing)
        return "prone", int(u.anim * 4) % 2 if u.moving else 0
    if u.kneeling:
        if u.kneel < KNEEL_TIME:
            return "kneel", int(u.kneel >= KNEEL_TIME / 2)
        return ("kfire", int(firing)) if busy else ("kneel", 1)
    if busy:
        return ("fire" if u.order == "attack" else "work"), int(firing)
    if u.moving:
        return "walk", int(u.anim * WALK_RATE["vehicle" if u.is_vehicle else "infantry"])
    # Idle: soldiers breathe slowly (and now and then check their weapon), vehicles shake with
    # the engine running; a fixed gun slowly raises and lowers its barrel instead of turning a
    # turret. The unit id offsets the cycle so a squad doesn't breathe in unison.
    if u.is_vehicle:
        if u.armed and not u.has_turret:
            return "idlegun", int((u.idle_t + u.id * 0.7) * 2.0) % len(m3.IDLE_ELEV)
        return "idle", int(u.idle_t * 10) % 2
    if u.check_t > 0:
        return "check", int(u.check_t * 2.5) % 2
    return "idle", int((u.idle_t + u.id * 0.37) * 2.5) % 4


def death_frame(age):
    for i, t in enumerate(DEATH_STEPS):
        if age < t:
            return i
    return len(DEATH_STEPS)


STEER_STEPS = (-1, 0, 1)   # front wheels: hard left, straight, hard right


def _render_unit(kind, light, lo, anim, i, facing, turret=0.0, steer=0.0):
    if UNITS[kind]["cls"] == "vehicle":
        build = m3.tank if kind == "tank" else m3.jeep
        darken = 1.0
        if anim == "walk":
            b, _ = build(light, lo, phase=i, moving=True, turret=turret, steer=steer)
        elif anim == "fire":
            b, _ = build(light, lo, recoil=1.5 if i else 0, flash=bool(i), turret=turret)
        elif anim == "die":
            b, _ = build(light, lo, wreck=True, turret=turret)
            darken = 0.4
        elif anim == "idlegun":   # fixed gun nodding its barrel up and down
            b, _ = build(light, lo, turret=turret, steer=steer, shake=m3.IDLE_SHAKE[i % len(m3.IDLE_SHAKE)],
                         elev=m3.IDLE_ELEV[i])
        else:
            b, _ = build(light, lo, turret=turret, steer=steer, shake=m3.IDLE_SHAKE[i % len(m3.IDLE_SHAKE)])
        return m3.render(b, facing, darken=darken)
    b, _, fall, lift = m3.soldier(kind, light, lo, anim, i)
    return m3.render(b, facing, fall, lift, scale=m3.INF_SCALE, ss=m3.INF_SS)


class UnitSprite:
    """Every frame of one unit type + loadout + team, rendered lazily per facing."""

    def __init__(self, kind, team, loadout):
        self.kind = kind
        self.light = TEAM_COLORS[team][0]
        self.loadout = dict(loadout)
        self.cls = UNITS[kind]["cls"]
        self.facings = FACINGS[self.cls]
        self.frames = FRAMES[self.cls]
        self._cache = {}
        self._flash = {}

    def facing_index(self, angle):
        return int(round(angle / (360 / self.facings))) % self.facings

    def frame(self, anim, i, angle, turret=0.0, steer=0.0):
        """(surface, origin) for animation `anim`, frame i, facing `angle` degrees; vehicles
        also take the turret's angle relative to the hull and the front wheels' steering."""
        if anim not in self.frames:
            anim = "fire" if anim == "work" else "idle"
        i %= self.frames[anim]
        fi = self.facing_index(angle)
        vehicle = self.cls == "vehicle"
        ti = self.facing_index(turret) if vehicle else 0
        si = (0 if abs(steer) < STEER_MAX / 3 else (1 if steer > 0 else -1)) if vehicle else 0
        key = (anim, i, fi, ti, si)
        got = self._cache.get(key)
        if got is None:
            step = 360 / self.facings
            got = self._cache[key] = _render_unit(self.kind, self.light, self.loadout, anim, i,
                                                  fi * step, ti * step, si * STEER_MAX)
        return got

    def flash(self, anim, i, angle, turret=0.0, steer=0.0):
        """White silhouette of a frame, for hit flashes."""
        surf, origin = self.frame(anim, i, angle, turret, steer)
        key = id(surf)
        got = self._flash.get(key)
        if got is None:
            got = self._flash[key] = silhouette(surf)
        return got, origin

    @property
    def image(self):
        return self.frame("idle", 0, ICON_FACING)[0]


_muzzles = {}


def muzzle_offset(kind, loadout, angle, prone=False, turret=0.0, kneel=False):
    """Screen offset from a unit's position to its gun muzzle at this facing (and, for
    vehicles, this turret angle relative to the hull)."""
    vehicle = UNITS[kind]["cls"] == "vehicle"
    n = FACINGS["vehicle" if vehicle else "infantry"]
    step = 360 / n
    tq = round(turret / step) * step if vehicle else 0.0
    key = (kind, tuple(sorted(loadout.items())), prone, kneel, tq)
    point = _muzzles.get(key)
    if point is None:
        if vehicle:
            _, mz = (m3.tank if kind == "tank" else m3.jeep)((0, 0, 0), loadout, turret=tq)
        else:
            anim = "pfire" if prone else "kfire" if kneel else "fire"
            _, mz, _, _ = m3.soldier(kind, (0, 0, 0), loadout, anim, 0)
        point = _muzzles[key] = mz or (0, 0, 10)
    return m3.project(point, round(angle / step) * step, 1.0 if vehicle else m3.INF_SCALE)


# ---- buildings -------------------------------------------------------------

BUILD_STAGES = 6   # construction is shown in this many height steps


def render_building(kind, team, stage=BUILD_STAGES, manned=False, scale=1.0):
    model = m3.BUILDING_MODELS[kind]
    garrisoned = kind in ("bunker", "tower")   # models that show their garrison
    boxes = model(TEAM_COLORS[team][0], manned) if garrisoned else model(TEAM_COLORS[team][0])
    if stage < BUILD_STAGES:
        boxes = m3.under_construction(boxes, (stage + 1) / (BUILD_STAGES + 1))
    return m3.render(boxes, m3.BUILD_FACING, scale=scale, ss=2, texture=0.07)


METAL, METAL_D, METAL_L = (150, 156, 166), (96, 102, 114), (198, 204, 212)


# ---- command icons (24x24) ---------------------------------------------------

def _icon():
    return pygame.Surface((24, 24), pygame.SRCALPHA)


def icon_move():
    s = _icon()
    pts = [(3, 10), (12, 10), (12, 5), (20, 12), (12, 19), (12, 14), (3, 14)]
    pygame.draw.polygon(s, (96, 206, 96), pts)
    pygame.draw.polygon(s, K, pts, 1)
    return s


def icon_stop():
    s = _icon()
    pts = [(8, 3), (16, 3), (21, 8), (21, 16), (16, 21), (8, 21), (3, 16), (3, 8)]
    pygame.draw.polygon(s, (200, 50, 44), pts)
    pygame.draw.polygon(s, K, pts, 1)
    pygame.draw.rect(s, (240, 240, 240), (7, 11, 10, 3))
    return s


def icon_attack():
    s = _icon()
    red = (235, 70, 60)
    pygame.draw.circle(s, K, (12, 12), 9, 3)
    pygame.draw.circle(s, red, (12, 12), 8, 1)
    for a, b in (((12, 1), (12, 8)), ((12, 16), (12, 23)), ((1, 12), (8, 12)), ((16, 12), (23, 12))):
        pygame.draw.line(s, K, a, b, 3)
        pygame.draw.line(s, red, a, b, 1)
    s.set_at((12, 12), red)
    return s


def icon_repair():
    s = _icon()
    pygame.draw.line(s, K, (6, 18), (16, 8), 6)
    pygame.draw.line(s, METAL_L, (6, 18), (16, 8), 3)
    pygame.draw.circle(s, K, (17, 7), 5)
    pygame.draw.circle(s, METAL_L, (17, 7), 4)
    pygame.draw.rect(s, CLEAR, (17, 2, 4, 5))
    pygame.draw.circle(s, GOLD, (6, 19), 2)
    return s


def icon_design():
    s = _icon()
    pygame.draw.rect(s, (40, 90, 170), (2, 3, 20, 18))
    for x in range(5, 22, 4):
        pygame.draw.line(s, (90, 140, 210), (x, 4), (x, 19))
    for y in range(6, 21, 4):
        pygame.draw.line(s, (90, 140, 210), (3, y), (20, y))
    pygame.draw.rect(s, K, (2, 3, 20, 18), 1)
    pygame.draw.circle(s, (240, 240, 240), (12, 12), 5, 2)
    for dx, dy in ((0, -6), (0, 6), (-6, 0), (6, 0)):
        pygame.draw.rect(s, (240, 240, 240), (11 + dx, 11 + dy, 2, 2))
    return s


def icon_cancel():
    s = _icon()
    pygame.draw.line(s, K, (5, 5), (19, 19), 6)
    pygame.draw.line(s, K, (19, 5), (5, 19), 6)
    pygame.draw.line(s, (220, 60, 50), (6, 6), (18, 18), 3)
    pygame.draw.line(s, (220, 60, 50), (18, 6), (6, 18), 3)
    return s


def fit(surf, size):
    """Scale by a whole factor (or down) so pixel art fits in a size x size box."""
    w, h = surf.get_size()
    f = size / max(w, h)
    if f >= 1:
        f = int(f)
    return pygame.transform.scale(surf, (max(1, int(w * f)), max(1, int(h * f))))


# ---- terrain -----------------------------------------------------------------

TERRAIN_COLORS = {SAND: (220, 186, 124), DUNE: (204, 166, 106), ROCK: (170, 146, 110), CLIFF: (130, 80, 50),
                  RAMP: (190, 154, 108)}
HIGH_COLOR = (214, 162, 104)     # plateau tops on the minimap
Q = 4                            # cliff outlines are drawn on a grid of Q x Q px cells


def _field(world, pick, gw, gh):
    """A tile mask (pick(i) -> bool) blurred up to the cell grid: bytes, one 0-255 value per cell."""
    small = pygame.Surface((world.w, world.h))
    for i in range(world.w * world.h):
        if pick(i):
            small.set_at((i % world.w, i // world.w), (255, 255, 255))
    return pygame.image.tobytes(pygame.transform.smoothscale(small, (gw, gh)), "RGB")[::3]


def _ramp_groups(world):
    """Each ramp as (its tiles, (dx, dy) uphill)."""
    w, h = world.w, world.h
    seen = set()
    out = []
    for i in range(w * h):
        p = (i % w, i // w)
        if world.tiles[i] != RAMP or p in seen:
            continue
        group, todo = [], [p]
        seen.add(p)
        while todo:
            x, y = todo.pop()
            group.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if q not in seen and world.in_bounds(*q) and world.tile(*q) == RAMP:
                    seen.add(q)
                    todo.append(q)
        out.append((group, world.ramp_dir(*p)))
    return out


def _shape_ramp(group, dx, dy, cls, along, noise, gw, gh, classes):
    """Mark one ramp's cells. Its sides wander like the cliff edge, narrowing a little towards
    the top, and it spills out onto the ground at its foot in a rounded apron."""
    LOW_C, FACE_C, TOP_C, RAMP_C = classes
    n = len(group)
    mx = sum(x for x, _ in group) / n * TILE + TILE / 2      # ramp centre, px
    my = sum(y for _, y in group) / n * TILE + TILE / 2
    hw = n * TILE / 2                                          # half width across the slope, px
    sx, sy = -dy, dx                                           # across the slope
    x0, y0 = (min(x for x, _ in group) - 2) * TILE, (min(y for _, y in group) - 2) * TILE
    x1, y1 = (max(x for x, _ in group) + 3) * TILE, (max(y for _, y in group) + 3) * TILE
    for cy in range(max(0, y0 // Q), min(gh, y1 // Q)):
        for cx in range(max(0, x0 // Q), min(gw, x1 // Q)):
            c = cy * gw + cx
            px, py = cx * Q + Q / 2 - mx, cy * Q + Q / 2 - my
            s = px * dx + py * dy        # along the slope: -8 at the foot edge, +8 at the top edge
            across = px * sx + py * sy
            t = abs(across)              # distance from the centre line
            side = 1 if across > 0 else 2   # each side wanders on its own
            wob = ((noise[c] - 128) / 128 * 2.0
                   + 2.6 * math.sin(s * 0.55 + mx * 0.37 * side) + 1.6 * math.sin(s * 1.3 + my * 0.29 * side))
            if -TILE / 2 <= s <= TILE / 2:                       # the cut through the cliff
                limit = hw - 1.5 - (s + TILE / 2) * 0.3 + wob   # narrowing towards the top
                if t <= limit:
                    cls[c] = RAMP_C
                    along[c] = (s + TILE / 2) / TILE
                elif t <= hw + TILE * 0.6 and cls[c] != TOP_C:
                    cls[c] = FACE_C                              # flanking wall
            elif -TILE / 2 - 9 <= s < -TILE / 2:                 # the apron at the foot
                reach = 9 * (1 - min(1.0, t / (hw + 4)) ** 2) + wob
                if s >= -TILE / 2 - reach and t <= hw + 2 + wob and cls[c] == LOW_C:
                    cls[c] = RAMP_C
                    along[c] = 0.0
            elif TILE / 2 < s <= TILE / 2 + 4 and t <= hw - 2 + wob:
                cls[c] = TOP_C                                   # clean lip at the top


def render_terrain(world, seed=1):
    rng = random.Random(seed)
    surf = pygame.Surface((world.w * TILE, world.h * TILE))
    sand, sand_d, sand_l = (220, 186, 124), (204, 168, 108), (234, 204, 146)
    dune, dune_d = (208, 170, 108), (184, 144, 88)
    rock, rock_d, rock_l = (176, 150, 112), (150, 126, 92), (198, 174, 136)
    mesa, mesa_d, mesa_l = (212, 162, 104), (192, 142, 88), (230, 186, 128)    # plateau tops
    mesa_dune = (200, 150, 94)
    walls = [(156, 98, 60), (138, 84, 50), (120, 72, 43), (104, 62, 37), (92, 54, 32)]
    slope, slope_d, slope_l = (170, 116, 76), (146, 98, 62), (192, 138, 94)
    lip, rim_line, base_line = (238, 196, 140), (150, 102, 64), (72, 44, 28)
    w, h = world.w, world.h

    def speckle(x, y, base, dark, light, n, size=TILE):
        pygame.draw.rect(surf, base, (x, y, size, size))
        for _ in range(n):
            surf.set_at((x + rng.randrange(size), y + rng.randrange(size)), rng.choice((dark, dark, light)))

    # 1. Ground texture per tile: desert floor below, warmer mesa rock on the plateaus.
    for ty in range(h):
        for tx in range(w):
            t = world.tile(tx, ty)
            x, y = tx * TILE, ty * TILE
            top = world.level(tx, ty) == HIGH and t != CLIFF
            if top:
                if t == DUNE:
                    pygame.draw.rect(surf, mesa_dune, (x, y, TILE, TILE))
                    for ry in range(y + rng.randrange(4), y + TILE, 5):
                        ox = rng.randrange(-3, 3)
                        pygame.draw.line(surf, mesa_d, (x + 2 + ox, ry), (x + 9 + ox, ry + 1))
                else:
                    speckle(x, y, mesa, mesa_d, mesa_l, 14)
                    if rng.random() < 0.06:   # loose boulders
                        px, py = x + rng.randrange(2, 12), y + rng.randrange(2, 12)
                        pygame.draw.rect(surf, mesa_d, (px, py, 3, 2))
                        surf.set_at((px, py), mesa_l)
                continue
            if t == DUNE:
                pygame.draw.rect(surf, dune, (x, y, TILE, TILE))
                for ry in range(y + rng.randrange(4), y + TILE, 5):
                    ox = rng.randrange(-3, 3)
                    pygame.draw.line(surf, dune_d, (x + 2 + ox, ry), (x + 9 + ox, ry + 1))
            elif t == ROCK:
                speckle(x, y, rock, rock_d, rock_l, 16)
            else:
                speckle(x, y, sand, sand_d, sand_l, 10)
                r = rng.random()
                if t == SAND and r < 0.04:
                    px, py = x + rng.randrange(2, 12), y + rng.randrange(2, 12)
                    pygame.draw.rect(surf, (150, 126, 92), (px, py, 3, 2))
                    surf.set_at((px, py), (190, 166, 128))
                elif t == SAND and r < 0.05:
                    px, py = x + rng.randrange(4, 11), y + rng.randrange(3, 8)
                    green, green_d = (96, 140, 70), (60, 98, 50)
                    pygame.draw.rect(surf, green_d, (px, py, 2, 7))
                    pygame.draw.rect(surf, green, (px, py, 1, 6))
                    pygame.draw.rect(surf, green_d, (px - 2, py + 2, 2, 1))
                    pygame.draw.rect(surf, green_d, (px - 2, py, 1, 2))

    # 2. Cliff outlines: blur the high-ground and plateau-top masks up to quarter tiles and
    #    wobble them with smooth noise, so edges come out rounded and irregular, not square.
    gw, gh = w * TILE // Q, h * TILE // Q
    tiles, height = world.tiles, world.height
    f_high = _field(world, lambda i: height[i] == HIGH, gw, gh)
    f_top = _field(world, lambda i: height[i] == HIGH and tiles[i] != CLIFF, gw, gh)
    noise = pygame.Surface((w // 2 + 1, h // 2 + 1))
    for y in range(noise.get_height()):
        for x in range(noise.get_width()):
            v = rng.randrange(256)
            noise.set_at((x, y), (v, v, v))
    f_noise = pygame.image.tobytes(pygame.transform.smoothscale(noise, (gw, gh)), "RGB")[::3]
    LOW_C, FACE_C, TOP_C, RAMP_C = 0, 1, 2, 3
    cls = bytearray(gw * gh)
    for c in range(gw * gh):
        n = (f_noise[c] - 128) * 0.45
        if f_top[c] + n > 128:
            cls[c] = TOP_C
        elif f_high[c] + n * 0.8 > 120:
            cls[c] = FACE_C
    ramp_along = {}   # cell -> 0 (foot) .. 1 (top), for shading the slope
    for group, (dx, dy) in _ramp_groups(world):
        _shape_ramp(group, dx, dy, cls, ramp_along, f_noise, gw, gh, (LOW_C, FACE_C, TOP_C, RAMP_C))
    ramp = bytearray(1 if c == RAMP_C else 0 for c in cls)

    def at(cx, cy):
        return cls[cy * gw + cx] if 0 <= cx < gw and 0 <= cy < gh else FACE_C

    stripe = [rng.randrange(3) for _ in range(gw)]
    for cy in range(gh):
        for cx in range(gw):
            c = cls[cy * gw + cx]
            px, py = cx * Q, cy * Q
            ti = (py // TILE) * w + px // TILE
            base_top = height[ti] == HIGH and tiles[ti] != CLIFF
            if c == TOP_C and not base_top:
                speckle(px, py, mesa, mesa_d, mesa_l, 2, Q)
            elif c == LOW_C and base_top:
                speckle(px, py, sand, sand_d, sand_l, 2, Q)
            elif c == RAMP_C:
                f = ramp_along[cy * gw + cx]
                col = tuple(int(a + (b - a) * f) for a, b in zip((182, 142, 96), mesa_l))
                pygame.draw.rect(surf, col, (px, py, Q, Q))
                if int(f * 12) % 2 == 0:   # treads worn across the slope
                    dark = tuple(int(v * 0.92) for v in col)
                    pygame.draw.line(surf, dark, (px, py + Q // 2), (px + Q - 1, py + Q // 2))
                if rng.random() < 0.5:
                    surf.set_at((px + rng.randrange(Q), py + rng.randrange(Q)), (156, 118, 80))
                continue
            elif c == FACE_C:
                depth = next((d for d in range(1, 6) if at(cx, cy - d) == TOP_C), 0)
                if depth:   # south-facing wall, seen from the camera: darker the further down
                    col = walls[min(depth - 1, len(walls) - 1)]
                    pygame.draw.rect(surf, col, (px, py, Q, Q))
                    if (cx + stripe[cx]) % 3 == 0:   # vertical striations
                        pygame.draw.line(surf, walls[min(depth, len(walls) - 1)], (px + 1, py), (px + 1, py + Q - 1))
                    if depth == 2:                    # a stratum line part-way down
                        pygame.draw.line(surf, walls[0], (px, py), (px + Q - 1, py))
                else:       # faces turned away from the camera: a sunlit rubble slope
                    speckle(px, py, slope, slope_d, slope_l, 3, Q)

    # 3. Contour lines, lips and shadows.
    shade = pygame.Surface((Q, Q), pygame.SRCALPHA)
    shade.fill((70, 34, 10, 70))
    for cy in range(gh):
        for cx in range(gw):
            c = cls[cy * gw + cx]
            px, py = cx * Q, cy * Q
            if c == TOP_C:
                if at(cx, cy + 1) == FACE_C:      # bright lip where the top drops away
                    pygame.draw.line(surf, lip, (px, py + Q - 1), (px + Q - 1, py + Q - 1))
                if at(cx, cy - 1) != TOP_C:       # contour line around the plateau
                    pygame.draw.line(surf, rim_line, (px, py), (px + Q - 1, py))
                if at(cx - 1, cy) != TOP_C:
                    pygame.draw.line(surf, rim_line, (px, py), (px, py + Q - 1))
                if at(cx + 1, cy) == FACE_C:
                    pygame.draw.line(surf, rim_line, (px + Q - 1, py), (px + Q - 1, py + Q - 1))
            elif c == FACE_C:
                if at(cx, cy + 1) == LOW_C:
                    pygame.draw.line(surf, base_line, (px, py + Q - 1), (px + Q - 1, py + Q - 1))
            elif c == RAMP_C:   # dark cut where the ramp meets the cliff wall either side
                for nx, ny, a, b in ((cx - 1, cy, (px, py), (px, py + Q - 1)),
                                     (cx + 1, cy, (px + Q - 1, py), (px + Q - 1, py + Q - 1)),
                                     (cx, cy - 1, (px, py), (px + Q - 1, py)),
                                     (cx, cy + 1, (px, py + Q - 1), (px + Q - 1, py + Q - 1))):
                    if at(nx, ny) == FACE_C:
                        pygame.draw.line(surf, base_line, a, b)
            elif c == LOW_C and not ramp[cy * gw + cx]:
                # Shadow cast down and to the right (light from the upper left).
                if at(cx, cy - 1) != LOW_C or at(cx - 1, cy) != LOW_C or at(cx - 1, cy - 1) != LOW_C:
                    surf.blit(shade, (px, py))

    return surf


def render_minimap(world):
    surf = pygame.Surface((world.w, world.h))
    for ty in range(world.h):
        for tx in range(world.w):
            t = world.tile(tx, ty)
            col = HIGH_COLOR if world.level(tx, ty) == HIGH and t != CLIFF else TERRAIN_COLORS[t]
            surf.set_at((tx, ty), col)
    return surf


class Sprites:
    def __init__(self):
        self._units = {}
        self._buildings = {}
        self._flashes = {}
        # All pump frames share one canvas, so only the beam moves and the base stays still.
        models = [m3.derrick(m3.derrick_rock(i)) for i in range(m3.DERRICK_FRAMES)]
        bounds = m3.measure(models, m3.BUILD_FACING)
        self.derrick_frames = [m3.render(b, m3.BUILD_FACING, ss=2, texture=0.06, bounds=bounds) for b in models]
        self.icons = {"move": icon_move(), "stop": icon_stop(), "attack": icon_attack(),
                      "repair": icon_repair(), "design": icon_design(), "cancel": icon_cancel()}
        for kind in UNITS:
            self.icons["unit:" + kind] = fit(self.unit(kind, PLAYER).image, 24)
        for kind in m3.BUILDING_MODELS:
            self.icons["bld:" + kind] = fit(self.building(kind, PLAYER)[0], 24)
        self.cursor = art_surface(CURSOR_ART, BASE_PAL)
        self._portraits = {}

    def unit(self, kind, team, loadout=None):
        loadout = loadout or default_loadout(kind)
        key = (kind, team, tuple(sorted(loadout.items())))
        spr = self._units.get(key)
        if spr is None:
            spr = self._units[key] = UnitSprite(kind, team, loadout)
        return spr

    def building(self, kind, team, progress=1.0, manned=False):
        """(surface, origin) for a building; origin sits on the footprint's centre."""
        stage = BUILD_STAGES if progress >= 1 else min(BUILD_STAGES - 1, int(progress * BUILD_STAGES))
        key = (kind, team, stage, manned)
        got = self._buildings.get(key)
        if got is None:
            got = self._buildings[key] = render_building(kind, team, stage, manned)
        return got

    def derrick(self, t):
        """(surface, origin) of the pump jack at game time t: it pumps continuously."""
        i = int(t / m3.DERRICK_PERIOD * m3.DERRICK_FRAMES) % m3.DERRICK_FRAMES
        return self.derrick_frames[i]

    def building_shadow(self, kind, size):
        """A soft ground shadow cast to the lower right (light comes from the upper left)."""
        key = ("shadow", kind)
        got = self._buildings.get(key)
        if got is None:
            img, (ox, oy) = self.building(kind, PLAYER)
            foot = size * TILE
            rise = max(4, img.get_height() - foot)            # how tall the building stands on screen
            sw = int(rise * 0.45)
            surf = pygame.Surface((foot + sw, foot + sw // 2), pygame.SRCALPHA)
            col = (40, 24, 10, 100)
            # East band (the building's right side) and south band (in front), sheared down-right.
            pygame.draw.polygon(surf, col, [(foot, 2), (foot + sw, 2 + sw // 2), (foot + sw, foot + sw // 2),
                                            (sw, foot + sw // 2), (sw // 2, foot), (foot, foot)])
            got = self._buildings[key] = surf
        return got

    def building_flash(self, kind, team):
        key = (kind, team)
        got = self._flashes.get(key)
        if got is None:
            got = self._flashes[key] = silhouette(self.building(kind, team)[0])
        return got

    def building_portrait(self, kind, team, width):
        """A building re-rendered at a larger scale (real detail, not an upscale) to fit `width`."""
        key = ("hq", kind, team, width)
        p = self._portraits.get(key)
        if p is None:
            base = self.building(kind, team)[0].get_width()
            img = render_building(kind, team, scale=width / base)[0]
            p = self._portraits[key] = img
        return p

    def entity_image(self, e):
        if e.is_unit:
            return self.unit(e.kind, e.team, e.loadout).image
        if e.is_point:
            return self.derrick_frames[0][0]
        return self.building(e.kind, e.team)[0]

    def portrait(self, e):
        key = (e.kind, e.team, tuple(sorted(e.loadout.items())) if e.is_unit else None)
        p = self._portraits.get(key)
        if p is None:
            img = self.entity_image(e)
            if e.is_unit and e.is_infantry:
                img = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
            p = fit(img, 36)
            self._portraits[key] = p
        return p

    def window_icon(self):
        return fit(self.unit("tank", PLAYER).image, 48)
