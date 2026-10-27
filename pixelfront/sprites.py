"""Pixel art for the game. Units are pre-rendered from the small 3D models in model3d.py
(any facing, any loadout, every animation frame) on first use and cached; buildings, icons
and terrain are painted directly. Everything here is drawn at full screen resolution: RES
pixels per game pixel.
"""
import math
import random

import pygame

from . import model3d as m3
from .config import TILE, TEAM_COLORS, PLAYER, ENEMY, KNEEL_TIME, STEER_MAX, RES
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
    "vehicle": dict(idle=2, walk=3, fire=2, die=1, idlegun=len(m3.IDLE_ELEV), deploy=4, dfire=2),
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
    if u.deploy_time:   # artillery: digging in / packing up, firing and idling dug in
        if 0 < u.deploy < 1:
            return "deploy", min(3, int(u.deploy * 4))
        if u.deploy >= 1:
            if busy:
                return "dfire", int(firing)
            return "idlegun", int((u.idle_t + u.id * 0.7) * 2.0) % len(m3.IDLE_ELEV)
        if busy:
            return "idle", int(u.idle_t * 10) % 2   # still turning to face the target
    if u.kneeling:
        if u.kneel < KNEEL_TIME:
            return "kneel", int(u.kneel >= KNEEL_TIME / 2)
        return ("kfire", int(firing)) if busy else ("kneel", 1)
    if busy:
        return ("fire" if u.order == "attack" else "work"), int(firing)
    if u.moving:
        return "walk", int(u.anim * WALK_RATE["vehicle" if u.is_vehicle else "infantry"])
    # Idle: soldiers breathe slowly (and now and then check their weapon), vehicles shake with
    # the engine running (dug-in artillery nods its barrel, above). The unit id offsets the cycle
    # so a squad doesn't breathe in unison.
    if u.is_vehicle:
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


VEH_EDGES = 0.78   # vehicle faces get edges this much darker (fine panel lines)
BLD_EDGES = 0.62   # ... and buildings more so


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
        elif anim == "idlegun":   # dug-in artillery nodding its barrel up and down
            b, _ = build(light, lo, turret=turret, steer=steer, shake=m3.IDLE_SHAKE[i % len(m3.IDLE_SHAKE)],
                         elev=m3.IDLE_ELEV[i], deploy=1.0)
        elif anim == "deploy":    # artillery part way between travelling and dug in
            b, _ = build(light, lo, turret=turret, deploy=(i + 1) / 5)
        elif anim == "dfire":
            b, _ = build(light, lo, recoil=1.5 if i else 0, flash=bool(i), turret=turret, deploy=1.0)
        else:
            b, _ = build(light, lo, turret=turret, steer=steer, shake=m3.IDLE_SHAKE[i % len(m3.IDLE_SHAKE)])
        return m3.render(b, facing, darken=darken, scale=RES, edges=VEH_EDGES)
    b, _, fall, lift = m3.soldier(kind, light, lo, anim, i)
    return m3.render(b, facing, fall, lift, scale=m3.INF_SCALE * RES, ss=m3.INF_SS)


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


def muzzle_offset(kind, loadout, angle, prone=False, turret=0.0, kneel=False, deployed=False):
    """Screen offset from a unit's position to its gun muzzle at this facing (and, for
    vehicles, this turret angle relative to the hull, and whether artillery is dug in)."""
    vehicle = UNITS[kind]["cls"] == "vehicle"
    n = FACINGS["vehicle" if vehicle else "infantry"]
    step = 360 / n
    tq = round(turret / step) * step if vehicle else 0.0
    key = (kind, tuple(sorted(loadout.items())), prone, kneel, tq, deployed)
    point = _muzzles.get(key)
    if point is None:
        if vehicle:
            if kind == "tank":
                _, mz = m3.tank((0, 0, 0), loadout, turret=tq, deploy=1.0 if deployed else 0.0)
            else:
                _, mz = m3.jeep((0, 0, 0), loadout, turret=tq)
        else:
            anim = "pfire" if prone else "kfire" if kneel else "fire"
            _, mz, _, _ = m3.soldier(kind, (0, 0, 0), loadout, anim, 0)
        point = _muzzles[key] = mz or (0, 0, 10)
    return m3.project(point, round(angle / step) * step, 1.0 if vehicle else m3.INF_SCALE)


# ---- buildings -------------------------------------------------------------

BUILD_STAGES = 6   # construction is shown in this many height steps


def render_building(kind, team, stage=BUILD_STAGES, manned=False, scale=RES):
    model = m3.BUILDING_MODELS[kind]
    garrisoned = kind in ("bunker", "tower")   # models that show their garrison
    boxes = model(TEAM_COLORS[team][0], manned) if garrisoned else model(TEAM_COLORS[team][0])
    if stage < BUILD_STAGES:
        boxes = m3.under_construction(boxes, (stage + 1) / (BUILD_STAGES + 1))
    return m3.render(boxes, m3.BUILD_FACING, scale=scale, ss=2, texture=0.07, edges=BLD_EDGES)


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
    """Scale by a whole factor so pixel art fits in a size x size box; detailed art that has to
    shrink is filtered rather than having pixels dropped."""
    w, h = surf.get_size()
    f = size / max(w, h)
    if f >= 1:
        f = int(f)
        return pygame.transform.scale(surf, (max(1, int(w * f)), max(1, int(h * f))))
    return pygame.transform.smoothscale(surf, (max(1, int(w * f)), max(1, int(h * f))))


# ---- terrain -----------------------------------------------------------------

TERRAIN_COLORS = {SAND: (220, 186, 124), DUNE: (204, 166, 106), ROCK: (170, 146, 110), CLIFF: (130, 80, 50),
                  RAMP: (190, 154, 108)}
HIGH_COLOR = (214, 162, 104)     # plateau tops on the minimap

SAND_C = ((220, 186, 124), (204, 168, 108), (234, 204, 146))
DUNE_C = ((208, 170, 108), (184, 144, 88))
ROCK_C = ((176, 150, 112), (150, 126, 92), (198, 174, 136))
MESA_C = ((212, 162, 104), (192, 142, 88), (230, 186, 128))       # plateau tops
MESA_DUNE = (200, 150, 94)
WALLS = [(156, 98, 60), (138, 84, 50), (120, 72, 43), (104, 62, 37), (92, 54, 32)]   # cliff wall, top to foot
SLOPE_C = ((170, 116, 76), (146, 98, 62), (192, 138, 94))         # faces turned away from the camera
LIP, RIM_LINE, BASE_LINE = (238, 196, 140), (150, 102, 64), (72, 44, 28)


def _speckled(rng, size, base, dark, light, n):
    """A size x size tile of `base` with n random dark/light specks."""
    t = pygame.Surface((size, size))
    t.fill(base)
    for _ in range(n):
        t.set_at((rng.randrange(size), rng.randrange(size)), rng.choice((dark, dark, light)))
    return t


def _grey(values, w, h):
    """A grey surface from w*h byte values."""
    buf = bytearray(w * h * 3)
    buf[0::3] = buf[1::3] = buf[2::3] = values
    return pygame.image.frombuffer(bytes(buf), (w, h), "RGB").copy()


def _contour_mask(world, pick, size, noise, amp, threshold):
    """Mask of the map area where pick(tile index) holds, with rounded, irregular, pixel-fine
    outlines: the 0/255 tile field is blurred up to quarter tiles, wobbled with smooth noise,
    blurred again up to full resolution and thresholded."""
    w, h = world.w, world.h
    tiles = bytes(255 if pick(i) else 0 for i in range(w * h))
    qw, qh = noise.get_size()
    q = pygame.image.tobytes(pygame.transform.smoothscale(_grey(tiles, w, h), (qw, qh)), "RGB")[::3]
    nz = pygame.image.tobytes(noise, "RGB")[::3]
    wobbled = bytes(max(0, min(255, int(a + (b - 128) * amp))) for a, b in zip(q, nz))
    big = pygame.transform.smoothscale(_grey(wobbled, qw, qh), size)
    return pygame.mask.from_threshold(big, (255, 255, 255), (255 - threshold,) * 3 + (255,))


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


def _ramp_outline(group, dx, dy, res):
    """A ramp's outline in screen px: its sides wander like the cliff edge and narrow a little
    towards the top, and it spills out onto the ground at its foot in a rounded apron.
    Returns (polygon, left side, right side) - the sides only along the cut through the cliff."""
    tw = TILE * res
    n = len(group)
    mx = sum(x for x, _ in group) / n * tw + tw / 2
    my = sum(y for _, y in group) / n * tw + tw / 2
    hw = n * tw / 2
    sx, sy = -dy, dx
    half, apron = tw / 2, 9 * res
    left, right, cut_l, cut_r = [], [], [], []
    s = half + 2 * res
    while s >= -half - apron:
        u = s / res   # in game pixels, so the shape is the same at any resolution
        if s >= -half:
            width = hw - 1.5 * res - (s + half) * 0.3
        else:
            f = (-half - s) / apron
            width = (hw + 2 * res) * math.sqrt(max(0.0, 1 - f * f))
        wl = res * (1.8 * math.sin(u * 0.22 + mx * 0.37 / res) + 0.8 * math.sin(u * 0.5 + my * 0.29 / res))
        wr = res * (1.8 * math.sin(u * 0.22 + mx * 0.74 / res + 1.0) + 0.8 * math.sin(u * 0.5 + my * 0.58 / res + 2.0))
        pl = (mx + s * dx - (width + wl) * sx, my + s * dy - (width + wl) * sy)
        pr = (mx + s * dx + (width + wr) * sx, my + s * dy + (width + wr) * sy)
        left.append(pl)
        right.append(pr)
        if s >= -half:
            cut_l.append(pl)
            cut_r.append(pr)
        s -= res
    return left + right[::-1], cut_l, cut_r


def _ramp_art(rng, poly, dx, dy, res):
    """(mask, texture, top-left) for one ramp: a graded slope, lighter towards the top, with
    treads worn across it and a little grit."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    w, h = int(max(xs)) - x0 + 2, int(max(ys)) - y0 + 2
    shape = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(shape, (255, 255, 255), [(x - x0, y - y0) for x, y in poly])
    tex = pygame.Surface((w, h))
    length = h if dy else w
    low, top = (176, 136, 92), MESA_C[0]
    for k in range(length):
        f = k / max(1, length - 1)                     # 0 at the low end, 1 at the top
        if (dy < 0) or (dx < 0):
            f = 1 - f
        col = tuple(int(a + (b - a) * f) for a, b in zip(low, top))
        if (k // res) % 3 == 0:                        # treads across the slope
            col = tuple(int(c * 0.9) for c in col)
        if dy:
            pygame.draw.line(tex, col, (0, k), (w - 1, k))
        else:
            pygame.draw.line(tex, col, (k, 0), (k, h - 1))
    for _ in range(w * h // (14 * res)):
        tex.set_at((rng.randrange(w), rng.randrange(h)), (156, 118, 80))
    return pygame.mask.from_surface(shape), tex, (x0, y0)


def render_terrain(world, seed=1, res=RES):
    """The whole map as one surface at `res` pixels per game pixel."""
    rng = random.Random(seed)
    w, h = world.w, world.h
    tw = TILE * res
    size = (w * tw, h * tw)
    surf = pygame.Surface(size)
    tiles, height = world.tiles, world.height

    # 1. Ground, tile by tile, from speckled variants (desert floor below, warmer mesa rock on
    #    top, which is laid down through the plateau mask later).
    area = res * res
    sand = [_speckled(rng, tw, *SAND_C, 10 * area) for _ in range(6)]
    rock = [_speckled(rng, tw, *ROCK_C, 16 * area) for _ in range(4)]
    mesa = [_speckled(rng, tw, *MESA_C, 14 * area) for _ in range(6)]
    dune = [_speckled(rng, tw, DUNE_C[0], DUNE_C[1], SAND_C[2], 4 * area) for _ in range(4)]
    mesa_tex = pygame.Surface(size)
    dune_tex = pygame.Surface(size)
    rock_tex = pygame.Surface(size)
    mesa_dune = pygame.Surface(size)

    def ripples(target, x, y, line):
        for ry in range(y + rng.randrange(4 * res), y + tw, 5 * res):
            ox = rng.randrange(-3 * res, 3 * res)
            pygame.draw.line(target, line, (x + 2 * res + ox, ry), (x + 9 * res + ox, ry + res))
            pygame.draw.line(target, line, (x + 3 * res + ox, ry + 1), (x + 8 * res + ox, ry + res + 1))

    for ty in range(h):
        for tx in range(w):
            i = ty * w + tx
            t = tiles[i]
            x, y = tx * tw, ty * tw
            mesa_tex.blit(rng.choice(mesa), (x, y))
            mesa_dune.fill(MESA_DUNE, (x, y, tw, tw))
            ripples(mesa_dune, x, y, MESA_C[1])
            if rng.random() < 0.06:                         # loose boulders on the plateaus
                px, py = x + rng.randrange(2, 12) * res, y + rng.randrange(2, 12) * res
                pygame.draw.ellipse(mesa_tex, MESA_C[1], (px, py, 3 * res, 2 * res))
                pygame.draw.rect(mesa_tex, MESA_C[2], (px + res // 2, py, res, max(1, res // 2)))
            dune_tex.blit(rng.choice(dune), (x, y))
            ripples(dune_tex, x, y, DUNE_C[1])
            rock_tex.blit(rng.choice(rock), (x, y))
            if True:
                surf.blit(rng.choice(sand), (x, y))
                r = rng.random()
                if t == SAND and r < 0.04:                  # pebble
                    px, py = x + rng.randrange(2, 12) * res, y + rng.randrange(2, 12) * res
                    pygame.draw.ellipse(surf, (150, 126, 92), (px, py, 3 * res, 2 * res))
                    pygame.draw.rect(surf, (190, 166, 128), (px + res // 2, py, res, max(1, res // 2)))
                elif t == SAND and r < 0.05:                # cactus
                    px, py = x + rng.randrange(4, 11) * res, y + rng.randrange(3, 8) * res
                    green, green_d, green_l = (96, 140, 70), (60, 98, 50), (130, 176, 96)
                    pygame.draw.rect(surf, green_d, (px, py, 2 * res, 7 * res))
                    pygame.draw.rect(surf, green, (px, py, res, 6 * res))
                    pygame.draw.rect(surf, green_l, (px, py + res, max(1, res // 2), 4 * res))
                    pygame.draw.rect(surf, green_d, (px - 2 * res, py + 2 * res, 2 * res, res))
                    pygame.draw.rect(surf, green_d, (px - 2 * res, py, res, 2 * res))

    # 2. Plateau masks with natural outlines; ramps cut out of them.
    noise = pygame.Surface((w // 2 + 1, h // 2 + 1))
    for y in range(noise.get_height()):
        for x in range(noise.get_width()):
            v = rng.randrange(256)
            noise.set_at((x, y), (v, v, v))
    noise = pygame.transform.smoothscale(noise, (w * 4, h * 4))
    dune_m = _contour_mask(world, lambda i: tiles[i] == DUNE, size, noise, 0.5, 128)
    dune_m.to_surface(surf, setsurface=dune_tex, unsetcolor=None)                 # soft-edged patches
    _contour_mask(world, lambda i: tiles[i] == ROCK, size, noise, 0.3, 128).to_surface(
        surf, setsurface=rock_tex, unsetcolor=None)
    dune_m.to_surface(mesa_tex, setsurface=mesa_dune, unsetcolor=None)            # dunes up top too
    del dune_tex, rock_tex, mesa_dune
    high_m = _contour_mask(world, lambda i: height[i] == HIGH, size, noise, 0.36, 120)
    top_m = _contour_mask(world, lambda i: height[i] == HIGH and tiles[i] != CLIFF, size, noise, 0.45, 128)
    top_m = top_m.overlap_mask(high_m, (0, 0))
    ramps = []
    ramp_m = pygame.mask.Mask(size)
    for group, (dx, dy) in _ramp_groups(world):
        poly, cut_l, cut_r = _ramp_outline(group, dx, dy, res)
        rm, tex, pos = _ramp_art(rng, poly, dx, dy, res)
        ramp_m.draw(rm, pos)
        ramps.append((rm, tex, pos, cut_l, cut_r))
    high_m.erase(ramp_m, (0, 0))
    top_m.erase(ramp_m, (0, 0))
    face_m = high_m.copy()
    face_m.erase(top_m, (0, 0))
    low_m = high_m.copy()
    low_m.invert()
    low_m.erase(ramp_m, (0, 0))

    # 3. Shadows cast down and to the right onto the ground (light from the upper left).
    scratch = pygame.Surface(size, pygame.SRCALPHA)
    shadow = pygame.mask.Mask(size)
    for k in range(res, 4 * res + 1, res):
        for off in ((k, k), (0, k), (k, 0)):
            shadow.draw(low_m.overlap_mask(high_m, off), (0, 0))
    shadow.to_surface(scratch, setcolor=(70, 34, 10, 66), unsetcolor=(0, 0, 0, 0))
    surf.blit(scratch, (0, 0))

    # 4. Plateau tops.
    top_m.to_surface(surf, setsurface=mesa_tex, unsetcolor=None)
    del mesa_tex

    # 5. Cliff faces. South faces are walls seen from the camera, darker the further down they
    #    are from the top edge, with striations and a stratum line; the rest is sunlit rubble.
    depth = 20 * res
    walls = pygame.mask.Mask(size)
    bands = [pygame.mask.Mask(size) for _ in WALLS]
    stratum = None
    for k in range(1, depth + 1):
        band = face_m.overlap_mask(top_m, (0, k))       # face pixels with the top edge k px above
        band.erase(walls, (0, 0))
        walls.draw(band, (0, 0))
        bands[min(len(WALLS) - 1, (k - 1) * len(WALLS) // depth)].draw(band, (0, 0))
        if k == int(depth * 0.4):
            stratum = band
    for band, col in zip(bands, WALLS):
        band.to_surface(surf, setcolor=col, unsetcolor=None)
    stripes = pygame.Surface(size, pygame.SRCALPHA)
    x = 0
    while x < size[0]:
        pygame.draw.line(stripes, (40, 20, 10, 70), (x, 0), (x, size[1] - 1))
        x += 3 * res + rng.randrange(-1, 2)
    walls.to_surface(scratch, setsurface=stripes, unsetcolor=(0, 0, 0, 0))
    surf.blit(scratch, (0, 0))
    del stripes
    if stratum is not None:
        stratum.to_surface(surf, setcolor=WALLS[0], unsetcolor=None)
    slope = face_m.copy()
    slope.erase(walls, (0, 0))
    rubble = _speckled(rng, 32 * res, *SLOPE_C, 90 * area)
    rubble_tex = pygame.Surface(size)
    for y in range(0, size[1], rubble.get_height()):
        for x in range(0, size[0], rubble.get_width()):
            rubble_tex.blit(rubble, (x, y))
    slope.to_surface(surf, setsurface=rubble_tex, unsetcolor=None)
    del rubble_tex

    # 6. Contour lines: a bright lip where the top drops away, a darker rim round the rest of the
    #    plateau edge, and a dark line where the walls meet the ground.
    lip = top_m.overlap_mask(face_m, (0, -1))
    inner = top_m.overlap_mask(top_m, (0, 1))
    inner = inner.overlap_mask(top_m, (1, 0))
    inner = inner.overlap_mask(top_m, (-1, 0))
    rim = top_m.copy()
    rim.erase(inner, (0, 0))
    rim.erase(lip, (0, 0))
    for off in ((0, 0), (res, 0), (-res, 0), (0, res), (0, -res), (2 * res, 0), (-2 * res, 0), (0, 2 * res), (0, -2 * res)):
        rim.erase(ramp_m, off)
    rim.to_surface(surf, setcolor=RIM_LINE, unsetcolor=None)
    lip.to_surface(surf, setcolor=LIP, unsetcolor=None)
    face_m.overlap_mask(low_m, (0, -1)).to_surface(surf, setcolor=BASE_LINE, unsetcolor=None)

    # 7. Ramps, with dark cut lines where they pass through the cliff.
    for rm, tex, pos, cut_l, cut_r in ramps:
        rm.to_surface(surf, setsurface=tex, unsetcolor=None, dest=pos)
        for side in (cut_l, cut_r):
            if len(side) > 1:
                pygame.draw.lines(surf, BASE_LINE, False, side)
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
        self.derrick_frames = [m3.render(b, m3.BUILD_FACING, ss=2, texture=0.06, bounds=bounds, scale=RES,
                                         edges=BLD_EDGES) for b in models]
        self.icons = {"move": icon_move(), "stop": icon_stop(), "attack": icon_attack(),
                      "repair": icon_repair(), "design": icon_design(), "cancel": icon_cancel()}
        self.cursor = art_surface(CURSOR_ART, BASE_PAL)
        self._portraits = {}
        self._icons_hi = {}

    def icon_hi(self, name, size, team=PLAYER, loadout=None):
        """A detailed icon at full resolution fitting a size x size UI box: "bld:<kind>" or
        "unit:<kind>" (with that loadout)."""
        key = (name, size, team, tuple(sorted(loadout.items())) if loadout else None)
        got = self._icons_hi.get(key)
        if got is None:
            what, kind = name.split(":")
            img = self.building(kind, team)[0] if what == "bld" else self.unit(kind, team, loadout).image
            got = self._icons_hi[key] = fit(img, size * RES)
        return got

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
            foot = size * TILE * RES
            rise = max(4 * RES, img.get_height() - foot)      # how tall the building stands on screen
            sw = int(rise * 0.45)
            surf = pygame.Surface((foot + sw, foot + sw // 2), pygame.SRCALPHA)
            col = (40, 24, 10, 100)
            # East band (the building's right side) and south band (in front), sheared down-right.
            k = RES
            pygame.draw.polygon(surf, col, [(foot, 2 * k), (foot + sw, 2 * k + sw // 2), (foot + sw, foot + sw // 2),
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
        """A building re-rendered at a larger scale (real detail, not an upscale) to fit `width`
        screen pixels."""
        key = ("hq", kind, team, width)
        p = self._portraits.get(key)
        if p is None:
            base = self.building(kind, team)[0].get_width() / RES   # its width at one pixel per unit
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
        """Full-resolution portrait fitting a 36x36 UI box (infantry blown up 2x first)."""
        key = (e.kind, e.team, tuple(sorted(e.loadout.items())) if e.is_unit else None)
        p = self._portraits.get(key)
        if p is None:
            img = self.entity_image(e)
            if e.is_unit and e.is_infantry:
                img = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
            p = fit(img, 36 * RES)
            self._portraits[key] = p
        return p

    def window_icon(self):
        return fit(self.unit("tank", PLAYER).image, 48)
