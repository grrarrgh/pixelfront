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
from .world import SAND, DUNE, ROCK, CLIFF

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
    "infantry": dict(idle=4, walk=4, fire=2, work=2, prone=2, pfire=2, kneel=2, kfire=2, die=4),
    "vehicle": dict(idle=2, walk=3, fire=2, die=1),
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
    # Idle: soldiers breathe slowly, vehicles shake with the engine running. The unit id
    # offsets the cycle so a squad doesn't breathe in unison.
    if u.is_vehicle:
        return "idle", int(u.idle_t * 10) % 2
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


def render_building(kind, team, stage=BUILD_STAGES, manned=False):
    model = m3.BUILDING_MODELS[kind]
    boxes = model(TEAM_COLORS[team][0], manned) if kind == "bunker" else model(TEAM_COLORS[team][0])
    if stage < BUILD_STAGES:
        boxes = m3.under_construction(boxes, (stage + 1) / (BUILD_STAGES + 1))
    return m3.render(boxes, m3.BUILD_FACING, ss=2, texture=0.07)


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

TERRAIN_COLORS = {SAND: (220, 186, 124), DUNE: (204, 166, 106), ROCK: (170, 146, 110), CLIFF: (130, 80, 50)}


def render_terrain(world, seed=1):
    rng = random.Random(seed)
    surf = pygame.Surface((world.w * TILE, world.h * TILE))
    sand, sand_d, sand_l = (220, 186, 124), (204, 168, 108), (234, 204, 146)
    dune, dune_d = (208, 170, 108), (184, 144, 88)
    rock, rock_d, rock_l = (176, 150, 112), (150, 126, 92), (198, 174, 136)
    top, top_d, top_l = (180, 116, 72), (160, 100, 60), (204, 140, 92)
    wall, wall_d = (122, 74, 44), (98, 58, 34)

    def cliff(x, y):
        return world.in_bounds(x, y) and world.tile(x, y) == CLIFF

    def speckle(x, y, base, dark, light, n):
        pygame.draw.rect(surf, base, (x, y, TILE, TILE))
        for _ in range(n):
            surf.set_at((x + rng.randrange(TILE), y + rng.randrange(TILE)), rng.choice((dark, dark, light)))

    for ty in range(world.h):
        for tx in range(world.w):
            t = world.tile(tx, ty)
            x, y = tx * TILE, ty * TILE
            if t == CLIFF:
                speckle(x, y, top, top_d, top_l, 14)
                if not cliff(tx, ty - 1):
                    pygame.draw.line(surf, top_l, (x, y), (x + TILE - 1, y))
                if not cliff(tx - 1, ty):
                    pygame.draw.line(surf, wall, (x, y), (x, y + TILE - 1))
                if not cliff(tx + 1, ty):
                    pygame.draw.line(surf, wall, (x + TILE - 1, y), (x + TILE - 1, y + TILE - 1))
                if not cliff(tx, ty + 1):
                    pygame.draw.rect(surf, wall, (x, y + 9, TILE, 7))
                    for sx in range(x + rng.randrange(3), x + TILE, 3):
                        pygame.draw.line(surf, wall_d, (sx, y + 10), (sx, y + 14))
                    pygame.draw.line(surf, top_d, (x, y + 9), (x + TILE - 1, y + 9))
                    pygame.draw.line(surf, (70, 42, 28), (x, y + 15), (x + TILE - 1, y + 15))
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
                if r < 0.04:
                    px, py = x + rng.randrange(2, 12), y + rng.randrange(2, 12)
                    pygame.draw.rect(surf, (150, 126, 92), (px, py, 3, 2))
                    surf.set_at((px, py), (190, 166, 128))
                elif r < 0.05:
                    px, py = x + rng.randrange(4, 11), y + rng.randrange(3, 8)
                    green, green_d = (96, 140, 70), (60, 98, 50)
                    pygame.draw.rect(surf, green_d, (px, py, 2, 7))
                    pygame.draw.rect(surf, green, (px, py, 1, 6))
                    pygame.draw.rect(surf, green_d, (px - 2, py + 2, 2, 1))
                    pygame.draw.rect(surf, green_d, (px - 2, py, 1, 2))
            if cliff(tx, ty - 1):
                shadow = pygame.Surface((TILE, 4), pygame.SRCALPHA)
                shadow.fill((60, 30, 10, 50))
                surf.blit(shadow, (x, y))
    return surf


def render_minimap(world):
    surf = pygame.Surface((world.w, world.h))
    for ty in range(world.h):
        for tx in range(world.w):
            surf.set_at((tx, ty), TERRAIN_COLORS[world.tile(tx, ty)])
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
