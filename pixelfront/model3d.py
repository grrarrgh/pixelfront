"""Pre-rendered 3D look, C&C style: units and buildings are small models built from shaded
boxes and rendered to pixel art from a fixed high-angle camera, in any facing and pose.

Model space: x forward, y to the unit's left, z up; one unit is one pixel at scale 1.
Infantry are modelled at full size, then rendered at INF_SCALE with supersampling, which
shrinks them and rounds off their silhouettes and shading.
"""
import math

import pygame

from .modules import weapon_of
from .weapons import weapon as weapon_def

ELEVATION = math.radians(42)            # camera angle above the horizon
SIN_E, COS_E = math.sin(ELEVATION), math.cos(ELEVATION)
VIEW = (0.0, COS_E, SIN_E)              # towards the camera (south and up)
_L = (-0.55, -0.4, 0.75)                # light from the upper left
_LN = math.sqrt(sum(v * v for v in _L))
LIGHT = tuple(v / _LN for v in _L)
AMBIENT, DIFFUSE = 0.42, 0.72
SHADE_STEP = 0.07                       # posterise shading so faces stay crisp pixel colours
OUTLINE = (22, 20, 26)

INF_SCALE = 0.55                        # infantry render size relative to their model
INF_SS = 3                              # infantry supersampling factor (rounder shapes)

# Corner order: bottom 0-3, top 4-7. Faces as corner indices.
_SIGNS = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
          (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4))


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def blend(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rotate(p, axis, deg, pivot):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]
    if axis == "pitch":    # about y: positive tips the top backwards / swings a hanging limb forward
        x, z = x * c - z * s, x * s + z * c
    elif axis == "yaw":    # about z: positive turns left
        x, y = x * c - y * s, x * s + y * c
    else:                  # "roll", about x: positive swings a hanging left limb outwards
        y, z = y * c - z * s, y * s + z * c
    return (x + pivot[0], y + pivot[1], z + pivot[2])


class Box:
    """A box in model space, optionally rotated (rot = [(axis, degrees, pivot), ...], applied in
    order). glow boxes ignore lighting; fixed boxes ignore the whole-body fall.

    Every shape (Box, Ext, Cyl) offers geometry() -> (points, faces as index lists, an inside
    point), already rotated, which is all render() needs."""
    __slots__ = ("pos", "size", "color", "rot", "glow", "fixed")

    def __init__(self, pos, size, color, rot=(), glow=False, fixed=False):
        self.pos, self.size, self.color, self.rot, self.glow, self.fixed = pos, size, color, rot, glow, fixed

    def corners(self):
        cx, cy, cz = self.pos
        hx, hy, hz = self.size[0] / 2, self.size[1] / 2, self.size[2] / 2
        pts = [(cx + sx * hx, cy + sy * hy, cz + sz * hz) for sx, sy, sz in _SIGNS]
        for axis, deg, pivot in self.rot:
            pts = [_rotate(p, axis, deg, pivot) for p in pts]
        return pts

    def geometry(self):
        pts = self.corners()
        inside = tuple(sum(p[j] for p in pts) / 8 for j in range(3))
        return pts, _FACES, inside

    def moved(self, rot=(), dz=0.0):
        """A copy with extra rotations appended and/or lifted by dz (pivots too)."""
        r = tuple((ax, deg, (q[0], q[1], q[2] + dz)) for ax, deg, q in self.rot) + tuple(rot)
        return Box((self.pos[0], self.pos[1], self.pos[2] + dz), self.size, self.color, r, self.glow, self.fixed)


class Ext:
    """A convex 2D profile extruded along an axis: profile points (u, v) lie across `axis`
    ('x': (y, z), 'y': (x, z), 'z': (x, y)), the solid runs from a0 to a1 along it, and the
    whole thing is offset by `pos`. Used for round wheels, rounded track runs, barrels, domes."""
    __slots__ = ("pos", "profile", "axis", "a0", "a1", "color", "rot", "glow", "fixed")

    def __init__(self, pos, profile, axis, a0, a1, color, rot=(), glow=False, fixed=False):
        self.pos, self.profile, self.axis, self.a0, self.a1 = pos, profile, axis, a0, a1
        self.color, self.rot, self.glow, self.fixed = color, rot, glow, fixed

    def _point(self, u, v, a):
        x, y, z = {"x": (a, u, v), "y": (u, a, v), "z": (u, v, a)}[self.axis]
        return (self.pos[0] + x, self.pos[1] + y, self.pos[2] + z)

    def geometry(self):
        n = len(self.profile)
        pts = [self._point(u, v, self.a0) for u, v in self.profile] + \
              [self._point(u, v, self.a1) for u, v in self.profile]
        for axis, deg, pivot in self.rot:
            pts = [_rotate(p, axis, deg, pivot) for p in pts]
        inside = tuple(sum(p[j] for p in pts) / len(pts) for j in range(3))
        faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
        faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        return pts, faces, inside

    def moved(self, rot=(), dz=0.0):
        r = tuple((ax, deg, (q[0], q[1], q[2] + dz)) for ax, deg, q in self.rot) + tuple(rot)
        return Ext((self.pos[0], self.pos[1], self.pos[2] + dz), self.profile, self.axis, self.a0, self.a1,
                   self.color, r, self.glow, self.fixed)


def circle(r, n=14, ry=None, start=0.0):
    """Profile points of a circle (or ellipse, with ry) of radius r."""
    ry = r if ry is None else ry
    return [(r * math.cos(start + math.tau * i / n), ry * math.sin(start + math.tau * i / n)) for i in range(n)]


def stadium(length, r, n=6):
    """Profile of a rounded-end bar (a track run seen from the side): `length` overall, ends of radius r."""
    half = length / 2 - r
    pts = [(half + r * math.cos(-math.pi / 2 + math.pi * i / n), r * math.sin(-math.pi / 2 + math.pi * i / n))
           for i in range(n + 1)]
    pts += [(-half + r * math.cos(math.pi / 2 + math.pi * i / n), r * math.sin(math.pi / 2 + math.pi * i / n))
            for i in range(n + 1)]
    return pts


def rrect(w, d, r, n=3):
    """Profile of a rectangle w x d with corners rounded to radius r."""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90),
                       (-w / 2 + r, -d / 2 + r, 180), (w / 2 - r, -d / 2 + r, 270)):
        for i in range(n + 1):
            ang = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _adders(B):
    """add(box args), cyl(pos, r, length, axis, colour, rot) and ext(...) appending to list B."""
    def add(*a, **k):
        B.append(Box(*a, **k))

    def cyl(pos, r, length, axis, col, rot=(), n=10, glow=False):
        B.append(Cyl(pos, r, length, axis, col, rot, glow, n=n))

    def ext(pos, profile, axis, a0, a1, col, rot=(), glow=False):
        B.append(Ext(pos, profile, axis, a0, a1, col, rot, glow))
    return add, cyl, ext


def Cyl(pos, r, length, axis, color, rot=(), glow=False, fixed=False, n=14, ry=None):
    """A cylinder of radius r (ellipse with ry) and `length` along `axis`, centred on pos."""
    return Ext(pos, circle(r, n, ry), axis, -length / 2, length / 2, color, rot, glow, fixed)


def render(boxes, facing, fall=0.0, lift=0.0, outline=True, darken=1.0, scale=1.0, ss=1, texture=0.0,
           bounds=None, edges=None):
    """Render shapes facing `facing` degrees (0 = east, 90 = south). Returns (surface, origin)
    where origin is the pixel that sits on the model's ground position. texture > 0 adds
    that much pixel grain (used for buildings). Pass the same `bounds` (from measure()) to
    every frame of an animation to keep them on one fixed canvas, so static parts don't jitter.
    edges = a shade factor (e.g. 0.6) to draw every face's edges darker, as fine detail lines."""
    a = math.radians(facing)
    ca, sa = math.cos(a), math.sin(a)
    k = scale * ss
    faces = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for b in boxes:
        pts, polys, inside = b.geometry()
        if fall and not b.fixed:
            pts = [_rotate(p, "pitch", fall, (0, 0, 0)) for p in pts]
            inside = _rotate(inside, "pitch", fall, (0, 0, 0))
        up = 0 if b.fixed else lift
        world = [((x * ca + y * sa) * k, (x * sa - y * ca) * k, (z + up) * k) for x, y, z in pts]
        ix, iy, iz = inside
        cx, cy, cz = (ix * ca + iy * sa) * k, (ix * sa - iy * ca) * k, (iz + up) * k
        for f in polys:
            # Newell's method: a robust normal for any planar polygon.
            nx = ny = nz = 0.0
            m = len(f)
            for j in range(m):
                p0, p1 = world[f[j]], world[f[(j + 1) % m]]
                nx += (p0[1] - p1[1]) * (p0[2] + p1[2])
                ny += (p0[2] - p1[2]) * (p0[0] + p1[0])
                nz += (p0[0] - p1[0]) * (p0[1] + p1[1])
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            if ln < 1e-9:
                continue
            n = (nx / ln, ny / ln, nz / ln)
            fc = [sum(world[i][j] for i in f) / m for j in range(3)]
            if n[0] * (fc[0] - cx) + n[1] * (fc[1] - cy) + n[2] * (fc[2] - cz) < 0:
                n = (-n[0], -n[1], -n[2])
            if n[0] * VIEW[0] + n[1] * VIEW[1] + n[2] * VIEW[2] <= 0.01:
                continue
            if b.glow:
                col = b.color
            else:
                lum = AMBIENT + DIFFUSE * max(0.0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2])
                lum = round(lum / SHADE_STEP) * SHADE_STEP * darken
                col = shade(b.color, lum)
            pts2 = [(world[i][0], world[i][1] * SIN_E - world[i][2] * COS_E) for i in f]
            for x, y in pts2:
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
            line = shade(col, edges) if edges and not b.glow else col
            faces.append((fc[1] * COS_E + fc[2] * SIN_E, pts2, col, line))
    if bounds == "measure":
        return (minx / k, maxx / k, miny / k, maxy / k)
    if not faces:
        return pygame.Surface((1, 1), pygame.SRCALPHA), (0, 0)
    if bounds is not None:
        minx, maxx, miny, maxy = (v * k for v in bounds)
    faces.sort(key=lambda f: f[0])
    pad = 2 * ss
    ox, oy = math.floor(-minx) + pad, math.floor(-miny) + pad
    w = int(math.ceil(maxx - minx)) + 2 * pad + 1
    h = int(math.ceil(maxy - miny)) + 2 * pad + 1
    w += (-w) % ss
    h += (-h) % ss
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for _, pts, col, line in faces:
        moved = [(x + ox, y + oy) for x, y in pts]
        pygame.draw.polygon(surf, col, moved)
        pygame.draw.polygon(surf, line, moved, 1)
    if ss > 1:
        surf = _downsample(surf, ss)
        ox, oy = ox / ss, oy / ss
    if texture:
        _grain(surf, texture)
    if outline:
        _outline(surf)
    if bounds is not None:   # fixed canvas: no cropping, so every frame lines up
        return surf, (int(round(ox)), int(round(oy)))
    r = surf.get_bounding_rect()
    return surf.subsurface(r).copy(), (int(round(ox)) - r.x, int(round(oy)) - r.y)


def measure(frames, facing, scale=1.0):
    """Union screen bounds of several box lists, for render(..., bounds=...)."""
    found = [render(b, facing, scale=scale, bounds="measure") for b in frames]
    return (min(f[0] for f in found), max(f[1] for f in found),
            min(f[2] for f in found), max(f[3] for f in found))


def _downsample(surf, ss):
    """Average ss x ss blocks, then snap edge pixels back to solid so the art stays pixel-crisp."""
    w, h = surf.get_width() // ss, surf.get_height() // ss
    small = pygame.transform.smoothscale(surf, (w, h))
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            r, g, b, a = small.get_at((x, y))
            if a < 100:
                continue
            if a < 255:  # undo the darkening from averaging with transparent pixels
                f = 255 / a
                r, g, b = min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f))
            out.set_at((x, y), (r, g, b, 255))
    return out


def _grain(surf, amount):
    """Deterministic per-pixel light/dark grain so flat faces read as worn concrete and metal.
    Glowing colours (very bright or saturated) are left clean."""
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w):
            r, g, b, a = surf.get_at((x, y))
            if not a or max(r, g, b) > 235 or max(r, g, b) - min(r, g, b) > 120:
                continue
            n = ((x * 73856093) ^ (y * 19349663)) % 997 / 997.0   # stable noise in 0..1
            f = 1.0 + (n - 0.5) * 2 * amount
            if n > 0.97:
                f -= amount * 2   # occasional dark fleck
            surf.set_at((x, y), (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)), a))


def _outline(surf):
    """Ring the silhouette with a 1px dark outline (mask dilation, so it's fast)."""
    mask = pygame.mask.from_surface(surf)
    grown = pygame.mask.Mask(mask.get_size())
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown.draw(mask, d)
    grown.erase(mask, (0, 0))
    surf.blit(grown.to_surface(setcolor=OUTLINE + (255,), unsetcolor=(0, 0, 0, 0)), (0, 0))


def transform(p, fall=0.0, lift=0.0):
    """A model-space point after the whole-body fall rotation used by render()."""
    if fall:
        p = _rotate(p, "pitch", fall, (0, 0, 0))
    return (p[0], p[1], p[2] + lift)


def project(p, facing, scale=1.0):
    """Screen offset (dx, dy) of a model-space point from the model's ground position."""
    a = math.radians(facing)
    x, y, z = p
    wx = x * math.cos(a) + y * math.sin(a)
    wy = x * math.sin(a) - y * math.cos(a)
    return wx * scale, (wy * SIN_E - z * COS_E) * scale


# ---- palette ------------------------------------------------------------------

SKIN = (222, 172, 132)
KHAKI, KHAKI_D = (190, 170, 116), (140, 124, 82)
OLIVE, OLIVE_D = (104, 116, 72), (74, 84, 52)
METAL, METAL_L, METAL_D = (138, 144, 154), (190, 196, 206), (84, 88, 98)
GUN, GUN_L = (58, 62, 70), (104, 110, 122)
BROWN, BROWN_D = (124, 86, 52), (88, 60, 36)
BOOT = (50, 44, 42)
WHITE = (228, 230, 232)
RED = (204, 36, 36)
YELLOW = (236, 190, 48)
CYAN = (120, 230, 245)
TYRE = (38, 38, 42)
TRACK, TRACK_L = (50, 50, 54), (96, 96, 102)
CONCRETE, CONCRETE_D = (184, 172, 146), (140, 130, 108)
GLASS = (110, 170, 200)
FLASH_Y, FLASH_W, FLAME = (255, 210, 90), (255, 255, 230), (250, 140, 40)


def team_set(light):
    return dict(T=light, Td=shade(light, 0.62), plate=blend(light, METAL, 0.5),
                pants=blend(shade(light, 0.55), (60, 60, 60), 0.3))


# ---- infantry -------------------------------------------------------------------
#
# Limbs have two segments. Each leg: (hip pitch, knee pitch, hip roll, knee roll); each arm:
# (shoulder pitch, elbow pitch, shoulder roll, elbow roll). Positive pitch swings a hanging
# limb forward; a negative knee pitch folds the shin back; positive elbow pitch folds the
# forearm forward/up. Roll swings a hanging limb sideways (positive = outwards for the left).

HIP_Z, KNEE_Z, SHOULDER_Z, ELBOW_Z = 8.0, 4.4, 15.0, 12.4
LEG_Y, ARM_Y = 1.6, 3.7

WALK_LEGS = ((26, -10), (6, -46), (-24, -14), (-4, -4))   # left leg; the right leg is 2 frames behind
DEATH = (                                                  # (fall, hip, knee) per frame
    (12, 8, -20), (40, 26, -70), (70, 14, -40), (90, 4, -10))
PRONE_FALL, PRONE_LIFT = -90.0, 2.4
# Crab crawl, per frame: (left leg splay, left knee fold, left arm splay, left elbow fold);
# the right side mirrors the other frame so the limbs alternate.
CRAWL = ((14, 40, 20, 60), (40, 95, 45, 110))


KNEEL_LEGS = {1: (85, -88), -1: (-12, -98)}   # front (left) leg and back (right) leg, fully knelt
KNEEL_DROP = 3.6                               # how far the body sinks when kneeling


def _hold(gun, act, shield=False):
    """Arm angles {side: (shoulder, elbow)} for how this soldier holds their gun (or kit, when
    gun is None)."""
    if gun == "pistol":
        hold = {-1: (88, 0) if act == "fire" else (30, 45), 1: (0, 15)}
    elif gun in ("rifle", "rifle_ugl", "sniper"):
        hold = {-1: (30, 70), 1: (45, 50)} if act != "fire" else {-1: (40, 70), 1: (55, 45)}
    elif gun == "m60":                    # at the hip
        hold = {-1: (10, 70), 1: (30, 60)}
    elif gun in ("grenade_launcher", "agl6"):   # at the shoulder
        hold = {-1: (30, 70), 1: (45, 50)}
    elif gun in ("rocket_launcher", "javelin"):   # tube on the shoulder
        hold = {-1: (20, 110), 1: (60, 70)}
    elif act == "work":
        hold = {1: (80, 10), -1: (5, 15)}
    else:
        hold = {1: (0, 15), -1: (0, 15)}
    if shield:   # the left arm holds the shield instead
        hold = {**hold, 1: (35, 55)}
    return hold


def soldier(kind, light, lo, anim="idle", i=0):
    """Boxes for an infantry unit in one animation frame.

    Returns (boxes, muzzle, fall, lift): render with those fall/lift values at INF_SCALE.
    """
    tc = team_set(light)
    act = {"fire": "fire", "pfire": "fire", "kfire": "fire", "work": "work"}.get(anim)
    if anim == "check":   # weapon check: rifle raised and looked over; medics/engineers go through their kit
        act = "work" if kind in ("medic", "engineer") else "fire"
    armor, weapon, speed = lo.get("armor", 1), lo.get("weapon", 1), lo.get("engine", 1)
    # The gun in their hands. Medics and engineers carry kit in the weapon slot instead (the
    # tier number picks the kit) and only draw their sidearm to fire.
    gun = weapon_of(kind, lo)
    if kind in ("medic", "engineer") and act != "fire":
        gun = None
    # Heavy infantry always wear more plating than their tier name: Light = helmet + body
    # armour, Medium = full body armour, Heavy = full body armour + a ballistic shield.
    shield = kind == "heavy" and armor == 2
    if kind == "heavy":
        armor = min(2, armor + 1)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))

    firing_anims = ("fire", "pfire", "kfire", "work")
    recoil = float(i) if anim in firing_anims else 0.0
    flash = anim in firing_anims and i == 1
    moving = anim in ("walk", "prone")
    prone = anim in ("prone", "pfire")
    fall = lift = 0.0

    # Leg and arm poses for this frame.
    legs = {1: (0, -4, 0, 0), -1: (0, -4, 0, 0)}
    hold = _hold(gun, act, shield)
    arms = {s: (sp, ep, 0, 0) for s, (sp, ep) in hold.items()}
    free = {s for s, (sp, ep) in hold.items() if sp < 6}   # arms not holding anything up
    if anim == "walk":
        for s, f in ((1, i), (-1, (i + 2) % 4)):
            hip, knee = WALK_LEGS[f % 4]
            legs[s] = (hip, knee, 0, 0)
        for s in free:   # free arms swing opposite their leg, elbows a little bent
            sp, ep, _, _ = arms[s]
            arms[s] = (sp - legs[s][0] * 0.7, 20 + max(0, legs[s][0]) * 0.5, 0, 0)
    elif anim in ("kneel", "kfire"):
        k = 0.5 if anim == "kneel" and i == 0 else 1.0     # kneel frame 0 is halfway down
        legs = {s: (hip * k, knee * k, 0, 0) for s, (hip, knee) in KNEEL_LEGS.items()}
        lift = -KNEEL_DROP * k
    elif act == "fire" and not prone:
        legs = {1: (14, -10, 0, 0), -1: (-10, -18, 0, 0)}   # braced stance
    elif anim == "die":
        fall, hip, knee = DEATH[i]
        lift = 1.6 * fall / 90
        legs = {1: (hip, knee, 0, 0), -1: (hip * 0.6, knee * 0.8, 0, 0)}
        arms = {s: (sp + 20 * i, ep + 10 * i, s * 8 * i, 0) for s, (sp, ep, _, _) in arms.items()}
    if prone:
        fall, lift = PRONE_FALL, PRONE_LIFT
        f = i if anim == "prone" else 0
        for s, cf in ((1, CRAWL[f % 2]), (-1, CRAWL[(f + 1) % 2])):
            splay, knee, asplay, elbow = cf
            legs[s] = (0, 0, s * splay, -s * knee)
            arms[s] = (165, 0, -s * asplay, s * elbow)

    if anim == "check":   # tilt the weapon up and back down to look it over
        arms = {s: (sp + (14 if i else 4) * (1 if s == -1 else 0.6), ep - (16 if i else 0), a, b)
                for s, (sp, ep, a, b) in arms.items()}
    _legs(B, tc, armor, speed, legs)
    upper_from = len(B)   # everything after the legs breathes in the idle animation
    _body(B, kind, tc, armor, weapon, speed, moving)
    _arms(B, kind, tc, armor, weapon, arms)
    W = []
    wadd = lambda *a, **k: W.append(Box(*a, **k))
    muzzle = _weapon(W, kind, gun, act, recoil)
    if anim == "check" and gun:   # weapon tipped up, close to the face
        tilt = ("pitch", -(18 if i else 8), (0, 0, 12))
        W = [b.moved(rot=(tilt,)) for b in W]
        muzzle = _rotate(muzzle, *tilt) if muzzle else muzzle
    if shield:   # ballistic shield on the left arm, with a vision slit
        wadd((3.6, 3.4, 10.6), (0.8, 5.0, 9.6), tc["plate"])
        wadd((3.65, 3.4, 15.5), (0.9, 5.2, 0.5), GUN)
        wadd((4.05, 3.4, 13.4), (0.2, 1.8, 0.7), CYAN, glow=True)
        for z in (8.0, 11.0):
            wadd((4.05, 3.4, z), (0.15, 4.6, 0.3), shade(tc["plate"], 0.8))
    if prone:
        # Weapons are held up overhead in the standing frame so they lie forward once prone.
        pr = ("pitch", 90, (0, 0, 13))
        W = [b.moved(rot=(pr,)) for b in W]
        if muzzle:
            muzzle = _rotate(muzzle, *pr)
    B += W
    if flash and muzzle:
        mx, my, mz = muzzle
        fx = (lambda p: _rotate(p, "pitch", 90, (0, 0, 13))) if prone else (lambda p: p)
        if kind == "medic":
            add(fx((mx + 0.6, my, mz)), (1.4, 1.4, 1.4), (150, 255, 150), glow=True)
        elif act == "work":
            add(fx((mx + 0.6, my, mz)), (1.2, 1.2, 1.2), FLASH_W, glow=True)
            add(fx((mx + 0.8, my + 0.8, mz + 0.8)), (0.8, 0.8, 0.8), FLASH_Y, glow=True)
        else:
            big = 2.6 if kind in ("heavy", "antiarmor") else 2.0
            add(fx((mx + big / 2, my, mz)), (big, big, big), FLASH_Y, glow=True)
            add(fx((mx + 0.4, my, mz)), (big * 0.6,) * 3, FLASH_W, glow=True)
    if anim == "idle" and i:
        B[upper_from:] = _raised(B[upper_from:], IDLE_BREATH[i % len(IDLE_BREATH)])
    if muzzle:
        muzzle = transform(muzzle, fall, lift)
    return B, muzzle, fall, lift


IDLE_BREATH = (0.0, 0.25, 0.45, 0.25)   # upper-body rise per idle frame
IDLE_SHAKE = (0.0, 0.3)                 # vehicle body shake per idle frame, engine running
IDLE_ELEV = (0, 3, 7, 11, 14, 11, 7, 3)  # fixed-gun barrel elevation per "idlegun" frame, degrees


def _raised(boxes, dz):
    """The same shapes lifted by dz (rotation pivots too, so limbs stay attached)."""
    return [b.moved(dz=dz) for b in boxes]


POLY = (72, 76, 84)          # polymer gun furniture
STRAP = (44, 40, 38)


def _legs(B, tc, armor, speed, legs):
    add, cyl, _ = _adders(B)
    pants = KHAKI_D if armor == 0 else tc["pants"]
    boot = BROWN_D if speed == 0 else BOOT
    for s in (1, -1):
        hip, knee, hroll, kroll = legs[s]
        y = s * LEG_Y
        hp, kp = (0, y, HIP_Z), (0, y, KNEE_Z)
        thigh_rot = (("pitch", hip, hp), ("roll", hroll, hp))
        shin_rot = (("pitch", knee, kp), ("roll", kroll, kp)) + thigh_rot
        col = pants if s < 0 else shade(pants, 0.92)
        cyl((0, y, (HIP_Z + KNEE_Z) / 2), 1.32, HIP_Z - KNEE_Z + 0.5, "z", col, thigh_rot, n=8)
        add((0.15, y + s * 1.18, 6.3), (1.5, 0.45, 1.7), shade(col, 0.84), thigh_rot)     # cargo pocket
        add((0.15, y + s * 1.42, 7.05), (1.6, 0.12, 0.3), shade(col, 0.64), thigh_rot)    # its flap
        cyl((0, y, 3.05), 1.18, 3.1, "z", col, shin_rot, n=8)
        add((0, y, 2.2), (2.5, 2.5, 0.35), shade(col, 0.78), shin_rot)                    # trousers bloused into boots
        add((0.45, y, 1.2), (3.1, 2.3, 1.5), boot, shin_rot)                              # boot
        add((1.5, y, 0.7), (1.5, 2.2, 1.1), shade(boot, 1.12), shin_rot)                  # toe cap
        add((0.6, y, 0.15), (4.0, 2.45, 0.3), (26, 22, 22), shin_rot)                     # sole
        add((1.0, y, 1.85), (1.0, 1.0, 0.22), shade(boot, 1.6), shin_rot)                 # laces
        if armor == 2:
            add((1.3, y, 4.6), (0.8, 2.4, 2.0), METAL, shin_rot)                          # knee plate
            add((1.72, y, 4.6), (0.1, 1.6, 0.25), METAL_D, shin_rot)
        elif armor == 1:
            add((1.2, y, 4.5), (0.6, 2.0, 1.5), (54, 54, 60), shin_rot)                   # knee pad
        if speed == 2:
            add((-1.2, y, 1.0), (0.5, 2.0, 0.8), CYAN, shin_rot, glow=True)


def _body(B, kind, tc, armor, weapon, speed, moving):
    # Armour never changes a soldier's size, only how much of them is plated:
    # light = fatigues and bare head, medium = helmet + body armour,
    # heavy = helmet + body armour + shoulder, elbow and knee plates.
    add, cyl, ext = _adders(B)
    vest = tc["T"]
    hat = tc["T"]
    ext((0, 0, 0), rrect(3.6, 6.0, 1.0), "z", 8.0, 15.2, KHAKI)                       # torso
    ext((0, 0, 0), rrect(3.9, 6.3, 1.0), "z", 8.1, 9.1, BROWN_D)                      # belt
    add((1.98, 0, 8.6), (0.25, 1.0, 0.7), METAL_L)                                     # buckle
    ext((0.15, 0, 0), rrect(2.6, 3.6, 0.8), "z", 14.9, 15.5, shade(KHAKI, 0.84))       # collar
    cyl((0.15, 0, 15.75), 0.95, 0.9, "z", shade(SKIN, 0.9))                            # neck
    cyl((-1.3, 3.05, 8.9), 0.75, 1.8, "z", OLIVE_D)                                    # canteen on the hip
    add((-1.3, 3.05, 9.95), (0.6, 0.6, 0.3), GUN)
    if armor >= 1:
        ext((0.1, 0, 0), rrect(4.2, 6.4, 0.9), "z", 9.6, 14.8, vest)                  # plate carrier
        add((2.18, 0, 14.7), (0.2, 4.6, 0.3), shade(vest, 1.2))                       # its top edge
        for y in (-1.55, 0.0, 1.55):                                                   # magazine pouches
            add((2.35, y, 10.7), (0.7, 1.3, 1.9), shade(vest, 0.74))
            add((2.45, y, 11.55), (0.75, 1.35, 0.35), shade(vest, 0.92))
        add((0.3, -3.35, 12.0), (1.8, 0.6, 2.2), shade(vest, 0.7))                   # radio pouch
        add((-0.3, -3.35, 14.4), (0.25, 0.25, 3.0), GUN)                              # whip antenna
        for y in (-2.0, 2.0):
            add((0, y, 15.0), (4.0, 1.3, 0.4), shade(vest, 0.85))                     # shoulder straps
        add((2.35, 1.6, 13.6), (0.15, 1.2, 0.8), shade(vest, 1.35))                  # ID patch
    else:
        for y in (-1.3, 1.3):                                                          # webbing straps
            add((1.85, y, 12.0), (0.2, 0.6, 6.2), STRAP)
            add((-1.85, y, 12.0), (0.2, 0.6, 6.2), STRAP)
        for y in (-2.3, 2.3):
            add((1.95, y, 9.3), (0.8, 1.1, 1.1), OLIVE_D)                             # belt pouches
    fx = 2.35 if armor else 1.9
    if kind == "engineer":                                                             # reflective stripes
        for z in (10.6, 12.8):
            add((fx + 0.1, 0, z), (0.25, 6.2, 0.5), YELLOW)
    if kind == "medic":   # red cross on a white patch
        add((fx + 0.05, 1.2, 13.0), (0.25, 2.6, 2.6), WHITE)
        add((fx + 0.1, 1.2, 13.0), (0.3, 0.6, 1.8), RED)
        add((fx + 0.1, 1.2, 13.0), (0.3, 1.8, 0.6), RED)

    # Head: a rounded column with a face.
    cyl((0.2, 0, 17.1), 1.75, 3.0, "z", SKIN, n=10)
    cyl((0.2, 0, 18.75), 1.4, 0.5, "z", SKIN, n=10)
    for y in (0.7, -0.7):
        add((1.93, y, 17.65), (0.25, 0.55, 0.5), (34, 28, 30))                       # eyes
        add((1.96, y, 18.15), (0.2, 0.75, 0.22), (90, 60, 40))                       # brows
        add((0.2, y * 2.5, 17.3), (0.7, 0.35, 0.9), shade(SKIN, 0.86))               # ears
    add((2.08, 0, 17.15), (0.45, 0.55, 0.75), shade(SKIN, 1.06))                      # nose
    add((1.98, 0, 16.35), (0.15, 0.9, 0.22), (150, 92, 78))                           # mouth
    if armor == 0:
        hair = BROWN_D
        cyl((0.0, 0, 18.95), 1.85, 0.65, "z", hair, n=10)
        add((-1.25, 0, 17.9), (0.9, 3.3, 2.2), hair)
    else:
        cyl((0, 0, 17.95), 2.3, 0.28, "z", shade(hat, 0.72), n=12)                   # helmet rim
        cyl((0, 0, 18.6), 2.15, 1.1, "z", hat, n=12)                                  # shell
        cyl((0, 0, 19.4), 1.9, 0.6, "z", hat, n=12)
        cyl((0, 0, 19.9), 1.45, 0.45, "z", shade(hat, 1.06), n=12)
        cyl((0, 0, 20.2), 0.85, 0.2, "z", shade(hat, 1.1), n=10)
        cyl((0, 0, 18.75), 2.2, 0.32, "z", (38, 38, 42), n=12)                       # goggle strap
        for y in (0.75, -0.75):
            add((1.95, y, 18.75), (0.5, 0.95, 0.55), CYAN, glow=True)                 # goggles, pushed up
        for y in (1.78, -1.78):
            add((0.7, y, 16.8), (0.25, 0.15, 1.9), STRAP)                             # chin straps
        if kind == "medic":
            cyl((0, 0, 20.36), 0.95, 0.12, "z", WHITE)
            add((0, 0, 20.45), (1.5, 0.5, 0.15), RED)
            add((0, 0, 20.45), (0.5, 1.5, 0.15), RED)
        elif kind == "engineer":
            cyl((0, 0, 18.95), 2.18, 0.5, "z", YELLOW, n=12)

    # Back gear: speed slot (a heavy kit backpack takes the rucksack's place; the bedroll stays).
    backpack = kind in ("medic", "engineer") and weapon == 2
    if speed == 0:
        if not backpack:
            ext((-3.7, 0, 0), rrect(3.0, 5.2, 0.8), "z", 9.0, 15.0, OLIVE)            # rucksack
            ext((-3.65, 0, 0), rrect(3.2, 5.4, 0.8), "z", 14.4, 15.4, OLIVE_D)        # its lid
            for y in (-1.6, 1.6):
                add((-5.25, y, 11.4), (0.35, 1.4, 2.4), OLIVE_D)                       # pockets
        cyl((-3.4, 0, 16.6), 1.15, 6.2, "y", (96, 104, 74), n=10)                    # bedroll
        for y in (-1.8, 1.8):
            cyl((-3.4, y, 16.6), 1.22, 0.3, "y", STRAP, n=10)
    elif speed == 2:
        ext((-3.0, 0, 0), rrect(2.4, 4.4, 0.7), "z", 9.9, 14.9, GUN)                  # thruster pack
        add((-4.25, 0, 13.0), (0.2, 3.6, 0.6), CYAN, glow=True)
        for s in (1, -1):
            cyl((-3.0, s * 1.2, 9.4), 0.75, 1.4, "z", METAL_D, n=8)
            if moving:
                cyl((-3.0, s * 1.2, 8.2), 0.55, 1.4, "z", FLAME, glow=True, n=8)
    if backpack:
        _kit_backpack(add, kind, -3.6 if speed != 2 else -5.0)
    if kind == "antiarmor" and speed == 1:   # two spare rounds in a carrier on the back
        add((-2.3, 0, 12.0), (0.6, 4.6, 5.4), STRAP)
        for y in (-1.2, 1.2):
            cyl((-3.3, y, 11.6), 1.0, 5.6, "z", OLIVE_D, n=8)
            cyl((-3.3, y, 15.0), 0.8, 1.2, "z", WARHEAD, n=8)
            cyl((-3.3, y, 15.8), 0.45, 0.6, "z", shade(WARHEAD, 0.85), n=8)
    if kind in ("medic", "engineer") and weapon == 0:
        body, _ = KIT_COLORS[kind]
        add((0.4, -4.0, 9.4), (3.4, 1.8, 3.0), body)
        add((0.4, -4.0, 11.0), (3.6, 2.0, 0.5), shade(body, 0.8))
        _kit_mark(add, kind, 0.4, -4.95, 9.3, "y")
        sx = 2.35 if armor else 1.95
        add((sx, 0, 12.4), (0.25, 0.8, 7.2), BROWN, (("roll", -45, (sx, 0, 12.4)),))


def _arms(B, kind, tc, armor, weapon, arms):
    add, cyl, _ = _adders(B)
    glove = (52, 50, 54) if armor >= 1 else SKIN
    carry = kind if kind in ("medic", "engineer") and weapon == 1 else None
    for s in (1, -1):
        sp, ep, sr, er = arms[s]
        y = s * ARM_Y
        shp, elp = (0, y, SHOULDER_Z), (0, y, ELBOW_Z)
        upper = (("pitch", sp, shp), ("roll", sr, shp))
        lower = (("pitch", ep, elp), ("roll", er, elp)) + upper
        cyl((0, y, (SHOULDER_Z + ELBOW_Z) / 2), 1.02, SHOULDER_Z - ELBOW_Z + 0.6, "z", KHAKI, upper, n=8)
        cyl((0, y, ELBOW_Z - 1.3), 0.94, 2.7, "z", KHAKI, lower, n=8)
        if armor == 0:
            cyl((0, y, ELBOW_Z - 0.9), 1.02, 0.5, "z", shade(KHAKI, 0.84), lower, n=8)   # rolled sleeves
        cyl((0, y, ELBOW_Z - 3.2), 0.92, 1.3, "z", glove, lower, n=8)                  # hand
        add((0.7, y, ELBOW_Z - 3.35), (0.6, 1.1, 0.9), glove, lower)                   # thumb and fingers
        if armor == 1:
            add((0, y, ELBOW_Z), (2.1, 2.1, 0.8), (54, 54, 60), lower)                 # elbow pad
        if armor == 0:
            # No helmet or vest to carry the team colour: bandanas knotted round both arms.
            add((0, y, SHOULDER_Z - 1.2), (2.4, 2.4, 1.0), tc["T"], upper)
            add((-1.3, y + s * 0.5, SHOULDER_Z - 1.6), (0.6, 0.5, 1.4), tc["T"], upper)
        # Trade patches on top of the shoulders, visible from the camera at any armour tier:
        # medics white with a red centre, engineers yellow and light grey.
        top = SHOULDER_Z + (0.55 if armor == 2 else 0.15)
        if kind == "medic":
            add((0, y, top), (2.3, 2.3, 0.5), WHITE, upper)
            add((0, y, top + 0.2), (0.9, 0.9, 0.3), RED, upper)
        elif kind == "engineer":
            add((0.5, y, top), (1.3, 2.3, 0.5), YELLOW, upper)
            add((-0.65, y, top), (1.0, 2.3, 0.5), METAL_L, upper)
        elif kind == "antiarmor":   # warhead orange with a black bar
            add((0, y, top), (2.3, 2.3, 0.5), WARHEAD, upper)
            add((0, y, top + 0.2), (0.6, 2.3, 0.3), (30, 28, 30), upper)
        if armor == 2:
            add((0, y, SHOULDER_Z - 0.4), (2.5, 2.3, 1.6), METAL, upper)   # shoulder plate
            add((0.2, y, SHOULDER_Z + 0.42), (2.0, 1.9, 0.1), METAL_D, upper)
            add((0, y, ELBOW_Z), (2.3, 2.2, 1.0), METAL, lower)           # elbow plate
        if carry and s == -1:   # kit case hanging from the right hand by its handle
            body, _ = KIT_COLORS[carry]
            add((0.3, y - 0.3, ELBOW_Z - 5.6), (4.6, 1.8, 3.2), body, lower)
            add((0.3, y - 0.3, ELBOW_Z - 3.9), (1.6, 0.6, 0.4), GUN, lower)
            _kit_mark(add, carry, 0.3, y - 1.3, ELBOW_Z - 5.6, "y", lower)


def _weapon(W, kind, gun, act, recoil):
    """Weapon / tool shapes; returns the muzzle (or tool tip) point."""
    add, cyl, _ = _adders(W)
    r = -recoil
    aim = act == "fire"

    def tilt(deg, x, y, z):
        return (("pitch", deg, (x, y, z)),)

    if gun == "grenade_launcher":            # M32-style revolving grenade launcher at the shoulder
        z, y = (13.6 if aim else 12.8), -1.6
        add((0.3 + r, y, z - 0.5), (2.4, 1.0, 1.8), POLY)                                  # stock
        add((-0.95 + r, y, z - 0.5), (0.3, 1.1, 2.0), (40, 40, 44))                        # butt pad
        add((2.6 + r, y, z), (2.6, 1.3, 1.5), GUN)                                         # frame
        cyl((4.8 + r, y, z - 0.2), 1.45, 2.6, "x", OLIVE_D, n=8)                          # revolving drum
        for k in range(6):
            ang = math.tau * k / 6
            add((6.12 + r, y + math.cos(ang) * 0.85, z - 0.2 + math.sin(ang) * 0.85), (0.1, 0.42, 0.42), (30, 30, 34))
        cyl((8.3 + r, y, z + 0.25), 0.8, 3.6, "x", GUN, n=10)                              # fat barrel
        cyl((10.2 + r, y, z + 0.25), 0.95, 0.4, "x", GUN_L, n=10)
        add((7.2 + r, y, z - 1.3), (0.8, 0.8, 1.6), GUN)                                   # foregrip
        add((3.4 + r, y, z - 1.3), (0.7, 0.8, 1.4), GUN, tilt(12, 3.4 + r, y, z - 0.6))   # pistol grip
        add((5.8 + r, y, z + 1.65), (1.0, 0.4, 1.0), GUN_L)                                # ladder sight
        return (10.6 + r, y, z + 0.25)
    if gun in ("rifle", "rifle_ugl"):                  # rifle at the ready
        z, y = (13.4 if aim else 12.6), -1.6
        add((0.4 + r, y, z - 0.45), (2.6, 1.0, 1.9), POLY)                                 # stock
        add((-0.95 + r, y, z - 0.45), (0.3, 1.1, 2.1), (36, 36, 40))                       # butt pad
        add((3.4 + r, y, z), (4.2, 1.2, 1.7), GUN)                                         # receiver
        add((3.5 + r, y, z + 0.95), (3.6, 0.9, 0.3), GUN_L)                                # top rail
        cyl((3.5 + r, y, z + 1.55), 0.5, 2.4, "x", (40, 42, 48), n=8)                     # optic
        add((4.75 + r, y, z + 1.55), (0.12, 0.6, 0.6), CYAN, glow=True)                    # its lens
        add((4.4 + r, y, z - 1.35), (0.9, 0.85, 1.7), (46, 48, 54), tilt(-14, 4.4 + r, y, z - 0.5))   # magazine
        add((2.5 + r, y, z - 1.2), (0.7, 0.85, 1.5), GUN, tilt(14, 2.5 + r, y, z - 0.5))  # pistol grip
        cyl((7.0 + r, y, z + 0.15), 0.62, 3.2, "x", POLY, n=8)                            # handguard
        cyl((9.6 + r, y, z + 0.15), 0.3, 2.4, "x", GUN, n=8)                              # barrel
        cyl((10.95 + r, y, z + 0.15), 0.42, 0.5, "x", GUN_L, n=8)                         # flash hider
        add((8.4 + r, y, z + 0.8), (0.3, 0.3, 0.6), GUN)                                   # front sight
        if gun == "rifle_ugl":                         # 40mm launcher under the handguard
            cyl((7.6 + r, y, z - 1.15), 0.85, 3.6, "x", OLIVE_D, n=10)                     # tube
            cyl((9.45 + r, y, z - 1.15), 0.6, 0.15, "x", (30, 30, 34), n=10)               # bore
            add((5.5 + r, y, z - 1.5), (1.2, 0.9, 1.4), GUN)                               # breech / trigger
            add((5.2 + r, y, z - 2.4), (0.6, 0.6, 0.8), GUN_L)                             # trigger guard
        return (11.3 + r, y, z + 0.15)
    if gun == "sniper":                                # bolt-action sniper rifle with a big scope
        z, y = (13.4 if aim else 12.6), -1.6
        add((0.2 + r, y, z - 0.5), (3.0, 1.0, 2.0), BROWN)                                 # stock
        add((-1.35 + r, y, z - 0.5), (0.3, 1.1, 2.2), (36, 36, 40))                        # butt pad
        add((0.8 + r, y, z + 0.75), (1.6, 0.8, 0.5), BROWN_D)                              # cheek rest
        add((3.4 + r, y, z), (3.6, 1.1, 1.4), GUN)                                         # action
        add((4.4 + r, y + 0.75, z + 0.3), (0.3, 0.6, 0.3), GUN_L)                          # bolt handle
        cyl((3.6 + r, y, z + 1.6), 0.6, 4.6, "x", (34, 36, 40), n=8)                      # scope tube
        cyl((6.0 + r, y, z + 1.6), 0.8, 0.8, "x", (34, 36, 40), n=8)                      # objective bell
        add((6.42 + r, y, z + 1.6), (0.12, 0.9, 0.9), CYAN, glow=True)                     # its lens
        add((3.0 + r, y, z - 1.0), (0.7, 0.85, 1.2), BROWN, tilt(14, 3.0 + r, y, z - 0.5))  # grip
        cyl((7.4 + r, y, z + 0.1), 0.55, 3.0, "x", BROWN, n=8)                            # fore-end
        cyl((11.0 + r, y, z + 0.1), 0.28, 5.2, "x", GUN, n=8)                             # long barrel
        cyl((13.75 + r, y, z + 0.1), 0.45, 0.6, "x", GUN_L, n=8)                          # muzzle brake
        for s in (0.45, -0.45):                                                             # folded bipod
            add((8.6 + r, y + s, z - 1.0), (0.3, 0.3, 1.8), GUN, (("roll", s * 30, (8.6 + r, y + s, z - 0.2)),))
        return (14.1 + r, y, z + 0.1)
    if gun == "pistol":
        z, y = (14.6 if aim else 11.6), -3.7
        x = 7.6 if aim else 4.4
        add((x + r, y, z), (3.0, 0.9, 1.0), GUN)                                           # slide
        add((x + 0.2 + r, y, z + 0.55), (2.6, 0.6, 0.15), GUN_L)
        add((x - 1.0 + r, y, z - 0.95), (1.0, 0.9, 1.5), (46, 48, 54), tilt(12, x - 1.0 + r, y, z - 0.3))
        return (x + 1.6 + r, y, z)
    if gun == "m60":                                   # machine gun at the hip
        z, y = 10.8, -2.0
        add((-0.2 + r, y, z - 0.5), (2.8, 1.4, 2.0), POLY)                                 # butt stock
        add((4.4 + r, y, z), (6.0, 2.0, 2.4), GUN)                                         # receiver
        add((4.0 + r, y, z + 1.3), (3.0, 1.8, 0.4), GUN_L)                                 # feed cover
        add((5.6 + r, y, z + 1.9), (1.6, 0.4, 0.6), GUN)                                   # carry handle
        cyl((10.6 + r, y, z + 0.2), 0.95, 4.0, "x", GUN_L, n=8)                           # barrel jacket
        cyl((13.0 + r, y, z + 0.2), 0.42, 3.2, "x", GUN, n=8)                             # barrel
        cyl((14.7 + r, y, z + 0.2), 0.6, 0.6, "x", GUN_L, n=8)                            # flash hider
        for s in (0.5, -0.5):                                                               # folded bipod
            add((12.6 + r, y + s, z - 1.4), (0.4, 0.4, 2.2), GUN, (("roll", s * 30, (12.6 + r, y + s, z - 0.3)),))
        add((3.0 + r, y - 1.9, z - 2.0), (2.8, 2.2, 2.6), OLIVE)                           # ammo box
        for k in range(5):                                                                  # belt feeding in
            add((3.2 + r + k * 0.45, y - 1.0 + k * 0.18, z - 0.6 + k * 0.25), (0.35, 0.6, 0.9),
                YELLOW if k % 2 else (200, 160, 40))
        return (15.1 + r, y, z + 0.2)
    if gun == "rocket_launcher":                       # rocket launcher on the shoulder
        z, y = 16.6, -3.4
        cyl((2.0 + r, y, z), 1.45, 16, "x", OLIVE, n=10)                                  # launch tube
        cyl((-5.6 + r, y, z), 1.85, 1.0, "x", OLIVE_D, n=10)                              # rear venturi flare
        for xx in (-2.0, 6.5):
            cyl((xx + r, y, z), 1.55, 0.5, "x", OLIVE_D, n=10)                            # tube bands
        cyl((10.6 + r, y, z), 1.2, 1.4, "x", WARHEAD, n=10)                               # warhead
        cyl((11.6 + r, y, z), 0.7, 0.8, "x", (150, 60, 34), n=8)                          # its nose
        add((2.6 + r, y, z - 2.3), (1.0, 1.0, 1.8), GUN)                                   # grip
        add((1.0 + r, y + 2.1, z + 0.6), (2.0, 1.2, 1.6), GUN)                             # sight unit
        add((1.6 + r, y + 2.75, z + 0.7), (0.12, 0.5, 0.5), CYAN, glow=True)
        return (12.0 + r, y, z)
    if gun == "agl6":                                  # 6-round automatic grenade launcher
        z, y = (13.6 if aim else 12.8), -1.8
        add((0.0 + r, y, z - 0.4), (2.6, 1.2, 2.0), POLY)                                  # stock
        add((-1.35 + r, y, z - 0.4), (0.3, 1.3, 2.2), (40, 40, 44))                        # butt pad
        add((3.4 + r, y, z), (4.4, 2.0, 2.4), GUN)                                         # receiver
        add((3.4 + r, y, z + 1.35), (3.6, 1.4, 0.3), GUN_L)                                # top rail
        cyl((3.2 + r, y, z + 2.0), 0.6, 2.4, "x", (40, 42, 48), n=8)                       # sight
        add((4.45 + r, y, z + 2.0), (0.12, 0.7, 0.7), CYAN, glow=True)
        cyl((4.0 + r, y - 0.2, z - 2.5), 2.0, 1.8, "y", OLIVE_D, n=12)                     # drum magazine
        cyl((4.0 + r, y - 1.15, z - 2.5), 0.7, 0.1, "y", YELLOW, n=8)                       # its winder
        cyl((8.2 + r, y, z + 0.2), 1.0, 4.2, "x", GUN, n=10)                               # fat barrel
        cyl((10.4 + r, y, z + 0.2), 1.2, 0.5, "x", GUN_L, n=10)                            # muzzle
        add((7.4 + r, y, z - 1.5), (0.8, 0.8, 1.6), GUN)                                   # foregrip
        add((2.0 + r, y, z - 1.4), (0.8, 0.9, 1.5), GUN, tilt(12, 2.0 + r, y, z - 0.6))   # pistol grip
        return (10.8 + r, y, z + 0.2)
    if gun == "javelin":                               # missile tube with the sight unit clamped on
        z, y = 16.8, -3.4
        cyl((2.4 + r, y, z), 1.8, 12.0, "x", (110, 112, 82), n=12)                         # launch tube
        for xx in (-3.4, 8.2):
            cyl((xx + r, y, z), 2.0, 0.9, "x", (78, 80, 60), n=12)                         # end caps
        add((0.6 + r, y + 2.6, z - 0.2), (3.2, 2.0, 2.6), (60, 62, 56))                    # command launch unit
        add((0.6 + r, y + 2.6, z + 1.3), (2.6, 1.6, 0.4), (44, 46, 42))
        add((-1.15 + r, y + 2.6, z + 0.2), (0.4, 1.0, 0.8), (30, 30, 32))                  # eyepiece
        add((2.25 + r, y + 2.6, z), (0.12, 1.2, 1.2), CYAN, glow=True)                     # seeker window
        add((1.0 + r, y + 1.4, z - 1.8), (0.9, 0.9, 1.4), GUN)                             # grips
        add((-0.6 + r, y + 1.4, z - 1.8), (0.9, 0.9, 1.4), GUN)
        _backblast(add, aim and recoil >= 1, -4.0 + r, y, z, 1.4)
        return (8.8 + r, y, z)
    # Medic / engineer: the left hand does the work (injector / wrench).
    if act == "work":
        x, z = 7.4, 14.8
        if kind == "medic":
            cyl((x, 3.7, z), 0.32, 2.4, "x", METAL_L, n=8)
            add((x + 1.3, 3.7, z), (0.3, 0.12, 0.12), METAL_D)
        else:
            add((x, 3.7, z), (2.4, 0.8, 0.8), METAL_L)
            cyl((x + 1.4, 3.7, z), 0.8, 0.8, "y", METAL_L, n=8)
        return (x + 1.4, 3.7, z)
    if kind == "engineer":
        add((0.4, 3.7, 8.4), (0.8, 0.8, 3.6), METAL_L)
        cyl((0.4, 3.7, 6.2), 0.8, 0.8, "y", METAL_L, n=8)
    return (1.0, 3.7, 9.0)


def _backblast(add, on, x, y, z, size):
    """The flash and dust blown out of the back of a launcher as it fires."""
    if not on:
        return
    add((x - size, y, z), (size * 2, size * 2, size * 2), FLASH_Y, glow=True)
    add((x - size * 2.6, y, z - size * 0.2), (size * 2, size * 2.4, size * 2), (210, 196, 170))
    add((x - size * 3.8, y, z - size * 0.4), (size * 1.6, size * 2.8, size * 1.6), (190, 178, 156))


KIT_COLORS = {"medic": (WHITE, RED), "engineer": (YELLOW, GUN)}
WARHEAD = (170, 70, 40)


def _kit_mark(add, kind, x, y, z, face_axis, rot=()):
    """The medic's red cross or the engineer's dark tool band on one face of a kit."""
    body, mark = KIT_COLORS[kind]
    if kind == "medic":
        if face_axis == "x":
            add((x, y, z), (0.2, 0.6, 1.8), mark, rot)
            add((x, y, z), (0.2, 1.8, 0.6), mark, rot)
        else:
            add((x, y, z), (0.6, 0.2, 1.8), mark, rot)
            add((x, y, z), (1.8, 0.2, 0.6), mark, rot)
    elif face_axis == "x":
        add((x, y, z), (0.2, 2.4, 0.6), mark, rot)
    else:
        add((x, y, z), (2.4, 0.2, 0.6), mark, rot)


def _kit_backpack(add, kind, x):
    body, _ = KIT_COLORS[kind]
    add((x, 0, 12.2), (3.2, 5.2, 6.4), body)
    add((x + 0.1, 0, 15.6), (3.4, 5.4, 0.8), shade(body, 0.8))
    for s in (1, -1):
        add((x + 0.4, s * 2.9, 11.2), (1.8, 0.6, 2.6), shade(body, 0.85))
    _kit_mark(add, kind, x - 1.7, 0, 12.6, "x")


# ---- vehicles -------------------------------------------------------------------
# Speed slot sets the running gear (Slow = full tracks, Normal = half-tracks, Fast = wheels).
# Armour slot only adds plating; the footprint stays the same.

def _wheel(B, x, y, z, size, side, phase, steer=0.0, front=False):
    """A round tyre on a rim and hub. The wheel nuts and tread grooves turn with `phase`, so it
    rolls; steering wheels yaw by `steer` degrees and get a bright rim so they stand out."""
    rot = (("yaw", steer, (x, y, z)),) if steer else ()
    w = 3.2 if front else 2.8
    r = size / 2
    oy = y + side * w / 2
    B.append(Cyl((x, y, z), r, w, "y", TYRE, rot, n=16))
    B.append(Cyl((x, oy + side * 0.06, z), r * 0.72, 0.14, "y", (60, 60, 66), rot, n=14))          # sidewall
    B.append(Cyl((x, oy + side * 0.13, z), r * 0.54, 0.14, "y", METAL_L if front else METAL, rot, n=12))   # rim
    B.append(Cyl((x, oy + side * 0.2, z), r * 0.24, 0.14, "y", METAL_D, rot, n=8))                 # hub
    for k in range(5):   # wheel nuts
        ang = math.radians(k * 72 + phase * 24)
        B.append(Box((x + math.cos(ang) * r * 0.38, oy + side * 0.22, z + math.sin(ang) * r * 0.38),
                     (0.4, 0.12, 0.4), GUN, rot))
    for k in range(10):  # tread grooves across the rolling face
        ang = math.radians(k * 36 + phase * 12)
        px, pz = x + math.cos(ang) * (r + 0.03), z + math.sin(ang) * (r + 0.03)
        B.append(Box((px, y, pz), (0.32, w * 0.84, 0.12), (22, 22, 26),
                     (("pitch", math.degrees(ang) + 90, (px, y, pz)),) + rot))


def _stadium_at(dist, half, r):
    """Point (x, z) and tangent angle (degrees) at distance `dist` round a rounded track run:
    forward along the bottom, up round the front, back along the top, down round the rear."""
    straight, arc = 2 * half, math.pi * r
    dist %= 2 * straight + 2 * arc
    if dist < straight:
        return -half + dist, -r, 0.0
    dist -= straight
    if dist < arc:
        ang = -math.pi / 2 + dist / r
        return half + r * math.cos(ang), r * math.sin(ang), math.degrees(ang) + 90
    dist -= arc
    if dist < straight:
        return half - dist, r, 180.0
    dist -= straight
    ang = math.pi / 2 + dist / r
    return -half + r * math.cos(ang), r * math.sin(ang), math.degrees(ang) + 90


def _track(B, x0, x1, y, z, h, w, side, phase):
    """A track run from x0 to x1 with rounded ends: links that crawl round as it moves, round
    road wheels, drive sprocket and idler."""
    length = x1 - x0
    cx = (x0 + x1) / 2
    r = h / 2
    half = length / 2 - r
    B.append(Ext((cx, y, z), stadium(length, r, 6), "y", -w / 2, w / 2, TRACK))
    per = 4 * half + 2 * math.pi * r
    n = max(8, int(per / 1.6))
    step = per / n
    for k in range(n):
        px, pz, ang = _stadium_at(k * step + phase * step / 3, half, r + 0.1)
        B.append(Box((cx + px, y, z + pz), (step * 0.5, w + 0.14, 0.32), TRACK_L, (("pitch", ang, (cx + px, y, z + pz)),)))
    oy = y + side * (w / 2 + 0.1)
    wheels = max(2, int((length - 2 * r) / 4.6) + 1)
    for k in range(wheels):   # road wheels along the bottom run
        x = x0 + r + 0.3 + k * (length - 2 * r - 0.6) / max(1, wheels - 1)
        B.append(Cyl((x, oy, z - r * 0.28), r * 0.62, 0.3, "y", METAL_D, n=12))
        B.append(Cyl((x, oy + side * 0.16, z - r * 0.28), r * 0.26, 0.16, "y", METAL, n=8))
    for x in (x1 - r, x0 + r):   # drive sprocket (front) and idler (rear)
        B.append(Cyl((x, oy, z), r * 0.78, 0.3, "y", GUN_L, n=12))
        B.append(Cyl((x, oy + side * 0.16, z), r * 0.3, 0.16, "y", METAL_D, n=8))


def _running_gear(B, speed, phase, front, rear, y, z, h, wheel, wreck=False, steer=0.0, fender=None):
    """Wheels, half-tracks or full tracks between x=rear and x=front on both sides.
    Front wheels steer by `steer` degrees; `fender` colours the mudguards over them."""
    for s in (1, -1):
        yy = s * y
        if speed == 2:                      # wheels
            span = front - rear
            count = 3 if span > 22 else 2
            for k in range(count):
                x = front - wheel / 2 - k * (span - wheel) / (count - 1)
                if not (wreck and k == 0):
                    _wheel(B, x, yy, wheel / 2, wheel, s, phase, steer if k == 0 else 0.0, k == 0)
        elif speed == 1:                    # half-track: big steering wheels up front, tracks behind
            fw = wheel * 1.15
            fx = front - fw / 2
            if not wreck:
                _wheel(B, fx, yy, fw / 2, fw, s, phase, steer, True)
            if fender:   # a curved mudguard over the front wheel
                arc = [(math.cos(math.pi * i / 6) * (fw / 2 + 0.9), math.sin(math.pi * i / 6) * (fw / 2 + 0.9))
                       for i in range(7)]
                for i in range(6):
                    (u0, v0), (u1, v1) = arc[i], arc[i + 1]
                    mx, mz = fx + (u0 + u1) / 2, fw / 2 + (v0 + v1) / 2
                    seg = math.hypot(u1 - u0, v1 - v0)
                    ang = math.degrees(math.atan2(v1 - v0, u1 - u0))
                    B.append(Box((mx, yy, mz), (seg + 0.2, 3.6, 0.45), fender, (("pitch", ang, (mx, yy, mz)),)))
            _track(B, rear, front - fw - 1.0, yy, z, h, 2.8, s, phase)
        else:                               # full tracks
            _track(B, rear, front, yy, z, h, 3.2, s, phase)


def tank(light, lo, phase=0, recoil=0.0, flash=False, moving=False, wreck=False, turret=0.0, steer=0.0,
         shake=0.0, elev=0.0, deploy=0.0):
    """elev = extra barrel elevation in degrees (the deployed 155mm's idle animation);
    deploy = 0 (travelling) .. 1 (dug in and ready to fire), for the 155mm."""
    B, muzzle, gear = _tank(light, lo, phase, recoil, flash, moving, wreck, turret, steer, elev, deploy)
    if shake:   # idling engine: the body rocks on its suspension, the running gear stays put
        B[gear:] = _raised(B[gear:], shake)
        muzzle = (muzzle[0], muzzle[1], muzzle[2] + shake)
    return B, muzzle


def _tank(light, lo, phase, recoil, flash, moving, wreck, turret, steer, elev_extra=0.0, deploy=0.0):
    tc = team_set(light)
    armor, speed = lo.get("armor", 1), lo.get("engine", 1)
    gun = weapon_of("tank", lo)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    hull = blend(tc["Td"], OLIVE, 0.35)
    hull_l = shade(hull, 1.12)

    _running_gear(B, speed, phase, 15.5, -15.5, 7.2, 3.0, 6.0, 6.4, wreck, steer, shade(hull, 0.9))
    gear = len(B)
    add((0, 0, 7.4), (27, 11, 4), hull)
    add((14.2, 0, 8.4), (4.0, 11, 3.0), hull, (("pitch", -30, (14.2, 0, 8.4)),))
    # Engine deck: grille slats and access hatch.
    for k in range(4):
        add((-11.5 + k * 1.6, 0, 9.65), (0.6, 7.5, 0.3), GUN)
    add((-5.5, 0, 9.65), (3.0, 5.0, 0.3), shade(hull, 0.85))
    # Front: headlights, tow hooks, glacis seam.
    for s in (1, -1):
        add((15.3, s * 4.5, 9.8), (0.6, 1.2, 1.0), FLASH_Y, glow=True)
        add((16.0, s * 3.0, 6.8), (0.8, 0.8, 0.8), GUN)
    add((13.0, 0, 9.65), (0.3, 10, 0.3), GUN)
    if armor == 0:
        # Bare hull: exposed frame ribs, no fenders over the running gear.
        for k in range(6):
            for s in (1, -1):
                add((-12 + k * 5, s * 5.55, 7.4), (0.8, 0.2, 4.0), GUN)
        add((-1, 0, 9.6), (24, 10, 0.4), hull_l)
    else:
        add((-1, 0, 10.1), (26, 17, 1.4), hull_l)                 # fenders over the gear
        for s in (1, -1):
            add((-1, s * 8.4, 10.85), (24, 0.2, 0.2), shade(hull, 0.7))   # fender edge line
            add((-8, s * 7.2, 11.4), (5, 1.6, 1.2), OLIVE_D)               # stowage bins
            add((3, s * 7.4, 11.1), (6, 0.8, 0.6), BROWN)                  # tools / tow cable
    if armor == 2:
        for s in (1, -1):
            add((0, s * 8.65, 7.0), (27, 0.4, 3.6), tc["plate"])  # side skirts
            for k in range(6):
                add((-12 + k * 4.8, s * 8.9, 8.0), (0.6, 0.2, 0.6), METAL_L)
        add((15.3, 0, 9.0), (1.2, 10.5, 2.4), tc["plate"], (("pitch", -30, (14.2, 0, 8.4)),))
    if speed == 2:
        for s in (1, -1):
            add((-13.6, s * 3.2, 9.6), (1.6, 2.2, 1.8), GUN)
            if moving:
                add((-15.0, s * 3.2, 9.6), (1.4, 1.6, 1.2), FLAME, glow=True)

    if gun == "howitzer_155":   # an artillery piece instead of a turret
        muzzle = _artillery(B, tc, hull, recoil, flash, wreck, deploy, elev_extra, turret)
        return B, muzzle, gear

    # Turret group (can turn independently of the hull).
    tr = [("yaw", turret, TANK_PIVOT)]
    if wreck:
        tr.append(("roll", 8, (-1, 0, 12)))
    # The Bushmaster's turret is a smaller one: everything in it shrinks towards the turret ring.
    ts = TANK_LIGHT_TURRET if gun == "bushmaster" else 1.0
    sc = lambda p: (-1 + (p[0] + 1) * ts, p[1] * ts, 11.4 + (p[2] - 11.4) * ts)
    srot = lambda rot: tuple((ax, deg, sc(pv)) for ax, deg, pv in rot) + tuple(tr)
    tadd = lambda pos, size, col, rot=(), glow=False: B.append(
        Box(sc(pos), tuple(v * ts for v in size), col, srot(rot), glow))
    tcyl = lambda pos, r, length, col, rot=(), n=10: B.append(
        Cyl(sc(pos), r * ts, length * ts, "x", col, srot(rot), n=n))
    T = tc["T"]
    tadd((-1, 0, 13.0), (12, 10, 3.6), T)
    tadd((-1.4, 0, 15.2), (9.6, 8, 0.8), T)
    tadd((5.6, 0, 13.0), (2.0, 8, 3.2), T)
    tadd((-1, 0, 11.4), (12.4, 10.4, 0.4), shade(T, 0.6))        # turret ring shadow line
    tadd((-7.2, 0, 13.2), (0.6, 8.4, 2.6), GUN_L)                # rear stowage basket
    tadd((-7.6, 0, 14.6), (0.4, 8.4, 0.4), GUN)
    # Commander's cupola with periscopes, gunner's sight, antenna.
    tadd((-3.4, 2.2, 15.9), (3.2, 3.2, 0.8), METAL_L)
    tadd((-3.4, 2.2, 16.6), (1.0, 1.0, 1.0), GUN)
    tadd((-1.8, 2.2, 16.0), (0.4, 1.6, 0.5), CYAN, glow=True)
    tadd((1.4, -2.6, 15.9), (2.0, 1.4, 1.0), GUN)
    tadd((2.4, -2.6, 15.9), (0.2, 1.0, 0.6), CYAN, glow=True)
    tadd((-5.6, -3.2, 18.0), (0.3, 0.3, 5.0), GUN)
    tadd((-1, 0, 13.0), (12.1, 10.1, 0.6), shade(T, 1.15))        # team stripe band
    for s in (1, -1):
        for k in range(3):                                         # smoke launchers
            tadd((3.4, s * (5.2 + 0.1 * k), 14.2 + k * 0.7), (1.2, 0.8, 0.6), GUN)
    if armor >= 1:
        tadd((6.7, 0, 13.0), (0.3, 7.0, 2.4), shade(T, 0.8))
    if armor == 2:
        for s in (1, -1):
            tadd((1.0, s * 5.15, 13.0), (8, 0.3, 2.8), tc["plate"])   # flush appliqué
            for x in (-2, 1, 4):
                tadd((x, s * 5.35, 13.6), (0.5, 0.1, 0.5), METAL_L)
    r = -recoil
    gz = 13.4
    pivot = (6.6, 0, gz)
    elev = -10 if wreck else 0   # wrecks' barrels droop
    bar = [("pitch", elev, pivot)] if elev else []
    if gun == "bushmaster":     # Bushmaster II 30mm: slim barrel, muzzle brake, ammo feed box, coax
        tadd((6.8, 0, gz), (1.6, 2.6, 2.2), GUN_L)
        length, th = 11, 0.9
        tcyl((7.4 + length / 2 + r, 0, gz), th / 2, length, GUN, bar)
        tcyl((7.4 + length + 0.5 + r, 0, gz), 0.7, 1.0, GUN, bar)
        for k in range(3):   # muzzle brake ports
            tadd((7.4 + length + 0.2 + k * 0.3 + r, 0, gz + 0.72), (0.12, 0.8, 0.1), (24, 24, 28), bar)
        tadd((4.0, -3.7, gz), (2.4, 1.4, 1.8), GUN)
        tadd((8.0, 1.8, gz - 1.0), (4.0, 0.7, 0.7), GUN)
        muzzle_x = 7.4 + length + 1.0
    else:                         # 120mm smoothbore: thick barrel, fume extractor, thermal sleeve bands
        tadd((6.8, 0, gz), (1.8, 4.0, 3.0), GUN_L)
        length, th = 13, 2.0
        tcyl((7.4 + length / 2 + r, 0, gz), th / 2, length, GUN, bar, n=12)
        tadd((7.4 + length / 2 + r, 0, gz + th / 2), (length - 0.6, th * 0.4, 0.15), GUN_L, bar)
        tcyl((7.4 + length * 0.45 + r, 0, gz), (th + 0.9) / 2, 2.6, GUN, bar, n=12)
        for k in (0.25, 0.7, 0.85):
            tcyl((7.4 + length * k + r, 0, gz), (th + 0.3) / 2, 0.4, GUN_L, bar, n=12)
        muzzle_x = 7.4 + length
    muzzle = (muzzle_x + r, 0, gz)
    if elev:
        muzzle = _rotate(muzzle, "pitch", elev, pivot)
    if flash:
        a = math.radians(elev)
        fx, fz = math.cos(a), math.sin(a)
        size = 2.0 if gun == "bushmaster" else 3.2
        tadd((muzzle[0] + fx * size / 2, 0, muzzle[2] + fz * size / 2), (size, size, size), FLASH_Y, glow=True)
        tadd((muzzle[0] + fx * 0.8, 0, muzzle[2] + fz * 0.8), (size * 0.6,) * 3, FLASH_W, glow=True)
    return B, _rotate(sc(muzzle), "yaw", turret, TANK_PIVOT), gear


TANK_LIGHT_TURRET = 0.75   # size of the Bushmaster tank's turret next to the 120mm's


def _phase(d, a, b):
    """How far (0..1, eased) a deployment step running from d=a to d=b has got at d."""
    t = max(0.0, min(1.0, (d - a) / (b - a)))
    return t * t * (3 - 2 * t)


ART_PIVOT = (1.6, 0, 15.4)      # the 155mm's trunnions
ART_ELEV = 42                   # its firing elevation, degrees (0 = lying on the travel lock)
SPADE_HINGE = (-14.2, 6.0)      # rear spades' hinge (x, z), low on the back plate
SPADE_ARM = 7.4                 # hinge to blade
SPADE_DUG, SPADE_UP = -35, -180  # arm angle from hanging straight down: dug in / folded up


ART_HOUSE_PIVOT = (-2.0, 0, 0)   # where the gun house turns on the hull once dug in


def _artillery(B, tc, hull, recoil, flash, wreck, d, elev_extra, turret=0.0):
    """The 155mm self-propelled gun: an open-topped gun house with a front shield, the barrel
    resting on a travel lock. Deploying (d 0..1) lowers the rear spades and side jacks, folds the
    travel lock away and raises the barrel; dug in, the gun house turns `turret` degrees on the
    hull. Returns the muzzle point."""
    add, cyl, _ = _adders(B)
    T, Td = tc["T"], tc["Td"]
    dig, lock, lift = _phase(d, 0.0, 0.5), _phase(d, 0.3, 0.6), _phase(d, 0.5, 1.0)

    # Rear spades: folded up against the back plate when travelling, dug in behind when deployed.
    hx, hz = SPADE_HINGE
    swing = SPADE_UP + (SPADE_DUG - SPADE_UP) * dig
    for s in (1, -1):
        y = s * 4.2
        arm = (("pitch", swing, (hx, y, hz)),)
        add((hx, y, hz - SPADE_ARM / 2), (1.2, 1.2, SPADE_ARM), GUN_L, arm)          # arm
        add((hx - 0.4, y, hz - SPADE_ARM), (1.0, 4.2, 2.4), GUN, arm)               # spade
        add((hx - 0.95, y, hz - SPADE_ARM - 0.3), (0.15, 3.8, 1.6), METAL_L, arm)   # its worn edge
        cyl((hx, y, hz), 0.8, 1.6, "y", METAL_D, n=8)                               # hinge
    # Side jacks: hydraulic legs that push pads down onto the sand either side of the tracks.
    for s in (1, -1):
        y = s * 9.3
        foot = 6.2 - 5.9 * dig
        add((-4.0, y, 10.4), (2.4, 1.4, 1.4), GUN)                                   # housing on the fender
        cyl((-4.0, y, (10.0 + foot) / 2), 0.45, 10.0 - foot, "z", METAL_L, n=8)     # ram
        add((-4.0, y, foot), (2.8, 2.4, 0.5), GUN_L)                                 # pad
    # Travel lock: an A-frame on the front deck the barrel rests in; it folds flat forwards.
    tl = (("pitch", -85 * lock, (12.0, 0, 9.6)),)
    for s in (1, -1):
        add((12.0, s * 1.3, 12.4), (0.6, 0.6, 5.6), GUN_L, (("roll", -s * 12, (12.0, s * 1.3, 9.6)),) + tl)
    add((12.0, 0, 15.0), (1.2, 3.4, 0.7), GUN, tl)                                    # the cradle

    # Gun house: open-topped armoured walls in the team colour, a sloped shield at the front.
    add((-2.0, 0, 10.9), (17.0, 10.6, 0.3), shade(hull, 0.6))                         # turntable well
    house = len(B)
    add((-2.0, 0, 11.0), (17.0, 10.6, 0.5), shade(hull, 0.8))                         # floor
    for s in (1, -1):
        add((-2.0, s * 5.2, 13.4), (17.0, 0.6, 4.4), T)                              # side walls
        add((-2.0, s * 5.55, 15.5), (17.0, 0.15, 0.3), shade(T, 1.2))                 # their top lip
        add((-2.0, s * 5.55, 12.2), (16.6, 0.12, 0.5), Td)                           # team stripe
        for x in (-8.0, -2.0, 4.0):
            add((x, s * 5.55, 13.6), (0.4, 0.1, 0.4), METAL_L)                       # rivets
    add((-10.4, 0, 12.8), (0.6, 10.6, 3.2), T)                                        # low rear wall
    shield = (("pitch", 18, (6.6, 0, 11.0)),)
    add((6.6, 0, 14.4), (0.9, 11.4, 6.6), T, shield)                                 # front gun shield
    add((7.1, 0, 17.4), (0.2, 11.0, 0.4), shade(T, 1.2), shield)
    for s in (1, -1):
        add((7.1, s * 3.6, 13.0), (0.15, 2.2, 3.2), Td, shield)                      # shield panels
    # Inside: ready rounds in a rack on the rear wall, a seat, the gun's pedestal and sight.
    for k in range(6):
        y = -3.75 + k * 1.5
        cyl((-9.4, y, 13.0), 0.6, 3.6, "z", (176, 140, 60), n=8)                      # brass cases
        cyl((-9.4, y, 15.2), 0.5, 0.9, "z", OLIVE_D, n=8)                             # shell noses
    add((-4.6, 3.0, 12.2), (2.0, 2.0, 0.6), BROWN_D)                                  # gunner's seat
    add((-5.4, 3.0, 13.4), (0.5, 2.0, 2.4), BROWN_D)
    add((1.6, 0, 13.2), (1.6, 3.0, 4.2), GUN)                                         # pedestal
    add((-4.0, -3.6, 14.2), (1.6, 1.2, 1.2), GUN_L)                                   # sight box
    add((-3.15, -3.6, 14.3), (0.15, 0.8, 0.5), CYAN, glow=True)

    # The gun: cradle, recuperators, long barrel with a double-baffle brake, breech behind.
    elev = -6 if wreck else (ART_ELEV + elev_extra) * lift
    bar = (("pitch", elev, ART_PIVOT),)
    r = -recoil * 1.6
    px, _, pz = ART_PIVOT
    length, th = 20.0, 2.6
    add((px, 0, pz), (4.0, 3.6, 3.0), GUN_L, bar)                                     # cradle
    for s in (1, -1):
        cyl((px, s * 2.0, pz), 0.9, 0.8, "y", METAL_D, n=8)                          # trunnions
    for zz in (pz + 1.9, pz - 1.6):
        cyl((px + 4.0 + r * 0.3, 0, zz), 0.5, 6.0, "x", METAL_L, bar, n=8)           # recuperators
    add((px - 3.2 + r, 0, pz), (2.8, 2.8, 2.6), GUN, bar)                             # breech block
    add((px - 4.7 + r, 0, pz), (0.3, 1.6, 1.6), METAL_D, bar)
    cyl((px + 2 + length / 2 + r, 0, pz), th / 2, length, "x", GUN, bar, n=12)        # barrel
    cyl((px + 2 + length * 0.55 + r, 0, pz), th / 2 + 0.45, 2.4, "x", GUN, bar, n=12)  # fume extractor
    for dx in (0.6, 2.2):
        add((px + 2 + length + dx + r, 0, pz), (1.0, th + 2.0, th + 0.8), GUN, bar)   # muzzle brake
    muzzle = _rotate((px + 2 + length + 2.8 + r, 0, pz), "pitch", elev, ART_PIVOT)
    if flash:
        a = math.radians(elev)
        fx, fz = math.cos(a), math.sin(a)
        mx, _, mz = muzzle
        add((mx + fx * 2.2, 0, mz + fz * 2.2), (4.4, 4.4, 4.4), FLASH_Y, glow=True)
        add((mx + fx * 0.8, 0, mz + fz * 0.8), (2.6, 2.6, 2.6), FLASH_W, glow=True)
        for s in (1, -1):   # flame jets out of the brake's side ports
            add((mx - fx * 2.0, s * 3.2, mz - fz * 2.0), (2.0, 2.4, 1.6), FLASH_Y, glow=True)
    if turret:
        yaw = (("yaw", turret, ART_HOUSE_PIVOT),)
        for b in B[house:]:
            b.rot = tuple(b.rot) + yaw
        muzzle = _rotate(muzzle, "yaw", turret, ART_HOUSE_PIVOT)
    return muzzle


JEEP_PIVOT = (-4.8, 0, 0)    # the pintle the rear weapon and its gunner swivel on
TANK_PIVOT = (-1, 0, 0)      # turret ring centre


def jeep(light, lo, phase=0, recoil=0.0, flash=False, moving=False, wreck=False, turret=0.0, steer=0.0,
         shake=0.0):
    """turret = the rear weapon's angle relative to the hull, in degrees (positive = left)."""
    B, muzzle, gear = _jeep(light, lo, phase, recoil, flash, moving, wreck, turret, steer)
    if shake:
        B[gear:] = _raised(B[gear:], shake)
        muzzle = (muzzle[0], muzzle[1], muzzle[2] + shake)
    return B, muzzle


def _jeep(light, lo, phase, recoil, flash, moving, wreck, turret, steer):
    tc = team_set(light)
    armor, speed = lo.get("armor", 1), lo.get("engine", 1)
    gun = weapon_of("jeep", lo)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    body = tc["T"]
    _running_gear(B, speed, phase, 11.0, -11.0, 6.0, 2.4, 4.6, 5.2, wreck, steer, shade(body, 0.8))
    gear = len(B)
    add((0, 0, 5.6), (24, 9.4, 3), shade(body, 0.75))
    if armor == 0:
        # Open frame: rails, seats and floor showing.
        for s in (1, -1):
            add((0, s * 4.6, 8.2), (20, 0.6, 0.8), GUN)
            add((-2, s * 2.4, 8.2), (3, 3, 3), BROWN)
            add((-3.4, s * 2.4, 10.2), (0.6, 3, 3), BROWN_D)          # seat backs
        add((8, 0, 8.0), (8, 9.4, 2.0), body)
    else:
        add((-1, 0, 8.4), (22, 9.6, 3.4), body)
        add((8, 0, 10.4), (8, 9.4, 0.6), body)
        for s in (1, -1):
            add((1, s * 4.85, 8.6), (0.3, 0.1, 3.0), tc["Td"])          # door seam
            add((-0.2, s * 4.87, 9.2), (0.8, 0.1, 0.3), METAL_L)        # door handle
            add((-1, s * 4.85, 6.8), (22, 0.1, 0.3), shade(body, 0.7))  # sill line
    # Hood detail, fenders over the front wheels, mirrors, steering wheel.
    add((8, 0, 10.8), (6, 2.0, 0.3), shade(body, 1.15))
    for s in (1, -1):
        add((8.3, s * 5.4, 7.8), (6.4, 1.4, 0.5), shade(body, 0.85))
        add((3.0, s * 5.2, 12.2), (0.4, 0.8, 0.6), GUN)
    add((2.4, 2.4, 11.4), (0.4, 2.0, 2.0), GUN)
    if armor == 2:
        # Bolt-on plates over the same body: hood, sides, wheel arches, grille.
        add((8, 0, 10.85), (8, 9.6, 0.3), tc["plate"])
        for s in (1, -1):
            add((-1, s * 4.95, 8.4), (21, 0.3, 3.0), tc["plate"])
            for x in (-8, -3, 2, 7):
                add((x, s * 5.15, 9.2), (0.5, 0.1, 0.5), METAL_L)
            add((8, s * 6.0, 5.4), (5.6, 2.6, 0.5), tc["plate"])
        add((11.9, 0, 8.0), (0.4, 8, 3.2), GUN)
    # Grille, bumper, headlights.
    add((12.2, 0, 6.8), (0.6, 9.4, 1.6), GUN)
    for k in range(4):
        add((12.0, -2.4 + k * 1.6, 8.6), (0.3, 0.6, 2.0), GUN)
    for s in (1, -1):
        add((12.3, s * 3.8, 8.6), (0.4, 1.4, 1.0), FLASH_Y, glow=True)
    if armor < 2:
        add((3.4, 0, 11.6), (0.6, 9.4, 4.0), GUN)
        add((3.9, 0, 11.6), (0.2, 8.0, 3.0), GLASS)
        add((3.95, -2, 12.4), (0.1, 1.2, 1.2), (190, 230, 245))          # glint
    else:
        add((3.4, 0, 12.0), (0.8, 9.6, 3.6), tc["plate"])
        add((3.9, 0, 12.4), (0.2, 7, 0.8), CYAN, glow=True)
    # Driver and gunner.
    add((0, 2.4, 11.2), (2.6, 3.2, 3.0), body)
    add((0, 2.4, 13.8), (2.4, 2.4, 2.4), SKIN)
    add((0, 2.4, 15.1), (2.8, 2.8, 1.4), tc["Td"])
    add((-4, 0, 13.6), (0.8, 9.6, 0.8), GUN)
    for s in (1, -1):
        add((-4, s * 4.4, 10.6), (0.8, 0.8, 6), GUN)
    add((-4.8, 0, 12.0), (0.8, 0.8, 3.0), GUN)                        # pintle post
    add((-10.6, 3.6, 13.6), (0.3, 0.3, 6.0), GUN)                     # radio antenna
    if speed != 0:
        B.append(Cyl((-12.2, 0, 7.6), 2.2, 1.0, "x", TYRE, n=14))     # spare wheel
        B.append(Cyl((-12.75, 0, 7.6), 1.1, 0.14, "x", METAL, n=12))
        B.append(Cyl((-12.82, 0, 7.6), 0.45, 0.14, "x", METAL_D, n=8))

    # Weapon station: gunner + weapon swivel together on the pintle.
    yaw = ("yaw", turret, JEEP_PIVOT)
    wadd = lambda pos, size, col, glow=False: B.append(Box(pos, size, col, (yaw,), glow))
    wcyl = lambda pos, r, length, col, n=10: B.append(Cyl(pos, r, length, "x", col, (yaw,), n=n))
    wadd((-7.5, 0, 11.6), (2.6, 4.0, 3.6), body)
    wadd((-7.5, 0, 14.6), (2.4, 2.4, 2.4), SKIN)
    wadd((-7.5, 0, 15.9), (2.8, 2.8, 1.4), tc["Td"])
    if armor == 2:
        wadd((-1.6, 0, 15.6), (0.5, 4.8, 3.2), tc["plate"])            # gun shield
    r = -recoil
    z = 14.8
    if gun == "m2":         # M2 Browning: boxy receiver, perforated barrel jacket, spade grips
        wadd((-3.6 + r, 0, z), (3.6, 1.8, 2.0), GUN)
        wcyl((0.8 + r, 0, z + 0.2), 0.58, 5.0, GUN_L)                    # perforated barrel jacket
        for k in range(4):
            wadd((-0.8 + k * 1.2 + r, 0, z + 0.78), (0.4, 0.6, 0.1), GUN)
        wcyl((4.0 + r, 0, z + 0.2), 0.36, 1.6, GUN)
        for s in (0.6, -0.6):
            wadd((-5.7 + r, s, z), (0.6, 0.5, 1.2), GUN)
        wadd((-3.6 + r, -1.7, z - 0.4), (1.6, 1.2, 1.4), OLIVE)
        muzzle = (4.8 + r, 0, z + 0.2)
    elif gun == "uag40":    # UAG-40 automatic grenade launcher: chunky receiver, short fat barrel, big ammo box
        wadd((-3.4 + r, 0, z), (4.4, 2.4, 2.4), GUN)
        wadd((-3.4 + r, 0, z + 1.3), (3.6, 1.6, 0.3), GUN_L)
        wcyl((0.6 + r, 0, z + 0.2), 0.78, 2.8, GUN)
        wcyl((2.2 + r, 0, z + 0.2), 0.92, 0.6, GUN_L)
        wadd((-3.4 + r, -2.6, z - 0.6), (2.6, 2.6, 2.2), OLIVE)
        wadd((-3.4 + r, -1.4, z + 0.2), (1.0, 0.8, 0.6), YELLOW)       # linked grenades feeding in
        muzzle = (2.6 + r, 0, z + 0.2)
    else:               # twin wire-guided missile tubes on a mount with a guidance sight
        wadd((-3.4, 0, z - 0.6), (2.0, 1.8, 1.8), GUN)
        wadd((-2.35, 0, z - 0.4), (0.1, 0.8, 0.6), CYAN, glow=True)
        for s in (1.0, -1.0):
            B.append(Cyl((-1.0 + r, s, z + 0.9), 0.78, 8.0, "x", OLIVE, (yaw,), n=10))
            B.append(Cyl((3.1 + r, s, z + 0.9), 0.88, 0.4, "x", GUN, (yaw,), n=10))
            B.append(Cyl((-5.1 + r, s, z + 0.9), 0.88, 0.4, "x", GUN, (yaw,), n=10))
        muzzle = (3.4 + r, 1.0, z + 0.9)
    muzzle = _rotate(muzzle, *yaw)
    if speed == 0:
        for s in (1, -1):
            add((-10.8, s * 2.6, 9.4), (3.0, 3.6, 3.2), BROWN)
            add((-10.8, s * 2.6, 11.05), (3.1, 3.7, 0.2), BROWN_D)
        add((-12.6, 0, 8.8), (1.0, 2.4, 3.0), OLIVE)
    elif speed == 2:
        add((-11.6, 0, 11.6), (1.2, 11, 0.6), body)
        for s in (1, -1):
            add((-11.6, s * 4.8, 10.4), (0.8, 0.6, 2.0), GUN)
        add((-12.4, -3.6, 4.6), (1.4, 1.2, 1.2), GUN)
        if moving:
            add((-13.6, -3.6, 4.6), (1.2, 1.0, 1.0), FLAME, glow=True)
    if flash:
        a = math.radians(turret)
        fx, fy = math.cos(a), math.sin(a)
        add((muzzle[0] + fx, muzzle[1] + fy, muzzle[2]), (2.0, 2.0, 2.0), FLASH_Y, glow=True)
        add((muzzle[0] + fx * 0.5, muzzle[1] + fy * 0.5, muzzle[2]), (1.2, 1.2, 1.2), FLASH_W, glow=True)
    return B, muzzle, gear


# ---- buildings ------------------------------------------------------------------
# Buildings face the camera (render with facing=BUILD_FACING). Their footprint is stretched
# north-south by 1/SIN_E so that on screen it covers exactly its tiles.

BUILD_FACING = 90
DEPTH = 1 / SIN_E
HEIGHT = 1.7   # buildings are stretched upwards so their fronts read clearly from this camera


def _bbox(B, east, south, up, w, d, h, col, glow=False, rot=()):
    """Add a box by footprint coords: east/south from the centre (tile px), up from the ground.
    Heights are in design units and stretched by HEIGHT; rotation pivots are given unstretched."""
    rot = tuple((ax, deg, (p[0], p[1], p[2] * HEIGHT)) for ax, deg, p in rot)
    B.append(Box((south * DEPTH, east, (up + h / 2) * HEIGHT), (d * DEPTH, w, h * HEIGHT), col, rot, glow))


GROOVE = (40, 42, 50)   # dark detail lines: panel seams, corrugation grooves, joints


def _barch(B, south, depth, half_w, base, rise, col, n=18):
    """An arched (half-ellipse) roof running north-south: `half_w` either side of the centre line,
    springing from height `base` and rising `rise` (design units), `depth` long, centred on `south`.
    Returns the arch's (east, up) outline points for adding trim and grooves."""
    arc = [(half_w * math.cos(math.pi * i / n), base + rise * math.sin(math.pi * i / n)) for i in range(n + 1)]
    profile = [(e, u * HEIGHT) for e, u in arc]
    B.append(Ext((south * DEPTH, 0, 0), profile, "x", -depth / 2 * DEPTH, depth / 2 * DEPTH, col))
    return arc


def _barc_line(B, arc, south, col, thick=0.45, out=0.12):
    """A thin strip following an arch outline across the roof at `south` (a seam or trim)."""
    for (e0, u0), (e1, u1) in zip(arc, arc[1:]):
        y0, z0, y1, z1 = e0, u0 * HEIGHT, e1, u1 * HEIGHT
        my, mz = (y0 + y1) / 2, (z0 + z1) / 2
        ln = math.hypot(y1 - y0, z1 - z0)
        ny, nz = (mz and my / max(1e-6, math.hypot(my, mz))), 0
        ang = math.degrees(math.atan2(z1 - z0, y1 - y0))
        B.append(Box((south * DEPTH, my, mz + out), (thick, ln + 0.1, thick), col,
                     (("roll", ang, (south * DEPTH, my, mz + out)),)))


def command_center(light):
    tc = team_set(light)
    T = tc["T"]
    B = []
    b = lambda *a, **k: _bbox(B, *a, **k)
    b(0, 0, 0, 46, 46, 2, CONCRETE)                         # pad
    b(0, 20, 2, 44, 4, 0.3, YELLOW)                          # hazard edge along the front
    b(0, -2, 2, 38, 30, 14, METAL)                           # main block
    b(0, -2, 16, 36, 28, 1.2, shade(METAL, 1.12))            # roof slab
    b(0, 13.1, 9, 38, 0.3, 2.4, T)                           # team band, front
    for s in (1, -1):
        b(s * 19.1, -2, 9, 0.3, 30, 2.4, T)                  # team band, sides
        b(s * 21, 6, 2, 6, 12, 8, shade(METAL, 0.9))          # side annexes
        b(s * 21, 6, 10, 6.4, 12.4, 0.8, METAL_L)
    for x in (-13, -6, 6, 13):
        b(x, 13.1, 12.4, 4, 0.3, 1.6, CYAN, glow=True)        # windows
        b(x, 13.0, 11.9, 4.8, 0.2, 2.6, GROOVE)               # window frames
    for x in (-16, -9.5, -3, 3, 9.5, 16):
        b(x, 13.05, 2.4, 0.3, 0.2, 6.6, GROOVE)               # wall panel seams (below the band)
    b(0, 13.05, 15.4, 38, 0.2, 0.3, GROOVE)                   # roof line
    b(0, 13.0, 2, 12, 0.6, 8, (46, 50, 58))                  # main door
    b(0, 13.35, 2, 0.3, 0.2, 8, GROOVE)                       # door split
    for k in range(4):
        b(0, 13.35, 3.0 + k * 1.8, 12, 0.2, 0.2, (36, 38, 44))   # door ribs
    for k in range(6):
        b(-5 + k * 2, 13.2, 10, 1, 0.4, 1.2, YELLOW if k % 2 == 0 else (30, 30, 34))
    # Rooftop: command dome (stacked), radar dish, mast with beacon, vents.
    for k, (r, hgt) in enumerate(((16, 3), (13, 3), (9, 2.4), (5, 1.6))):
        b(-4, -6, 17.2 + k * 3, r, r * 0.8, hgt, METAL_L if k % 2 == 0 else shade(METAL_L, 0.92))
    b(10, -10, 17.2, 6, 6, 1.0, GUN)
    b(10, -10, 18.2, 1, 1, 4, GUN)
    b(10, -10, 22, 7, 1.2, 3, METAL_L, rot=(("roll", 25, (0, 10, 23.5)),))
    b(-14, -12, 17.2, 0.8, 0.8, 14, GUN)
    b(-14, -12, 31, 1.6, 1.6, 1.4, (255, 70, 60), glow=True)
    for x in (4, 8):
        b(x, 4, 17.2, 2.4, 3, 1.4, GUN_L)
    return B


def barracks(light):
    """A 2x2 bunker: designed on the 3x3 grid like the others, then shrunk to fit 32px."""
    tc = team_set(light)
    T = tc["T"]
    B = []
    k2 = 2 / 3

    def b(east, south, up, w, d, h, col, glow=False, rot=()):
        _bbox(B, east * k2, south * k2, up * 0.85, w * k2, d * k2, h * 0.85, col, glow, rot)

    b(0, 0, 0, 46, 46, 1.5, CONCRETE_D)
    for x in (-10, 6):                                          # weathering streaks on the walls
        b(x, 12.15, 3, 1.0, 0.3, 6, shade(CONCRETE, 0.85))
    b(0, -4, 1.5, 42, 32, 9, CONCRETE)                       # bunker walls
    for z in (3.6, 5.6, 8.0):
        b(0, 12.08, z, 42, 0.2, 0.25, shade(CONCRETE, 0.7))   # pour lines
    for x in (-21, 21):
        b(x, 12.08, 1.5, 0.35, 0.2, 9, shade(CONCRETE, 0.7))  # corners
    b(0, -4, 10.5, 38, 28, 3, shade(CONCRETE, 0.95))          # stepped roof
    b(0, -4, 13.5, 32, 22, 1.2, shade(CONCRETE, 1.08))
    b(0, 12.1, 6, 42, 0.3, 2.0, T)                            # team stripe
    for x in (-14, 14):
        b(x, 12.1, 9, 8, 0.4, 1.2, (24, 24, 28))              # firing slits
    b(0, 12.0, 1.5, 9, 0.6, 7, (44, 46, 54))                  # door
    b(0, 12.3, 8.6, 10, 0.4, 0.8, GUN)
    b(3, 12.4, 4.6, 0.6, 0.3, 1.2, CYAN, glow=True)
    for k, x in enumerate((-19, -15, -11, 11, 15, 19)):       # sandbags in front
        b(x, 17, 1.5, 4, 3, 2.2, (170, 150, 104) if k % 2 else (160, 140, 96))
        b(x + 2, 17, 3.7, 4, 3, 2.0, (176, 156, 108))
    for x in (-11, -3, 5):                                     # roof vents
        b(x, -9, 14.7, 5, 2, 1.0, GUN_L)
    # (The team flag on a pole is drawn and animated by render.draw_flag.)
    return B


def vehicle_yard(light):
    tc = team_set(light)
    T = tc["T"]
    B = []
    b = lambda *a, **k: _bbox(B, *a, **k)
    b(0, 0, 0, 46, 46, 1.2, CONCRETE)
    b(0, 18, 1.2, 40, 8, 0.2, CONCRETE_D)                     # apron
    for x in range(-18, 19, 6):                                # its expansion joints
        b(x, 18, 1.4, 0.3, 8, 0.05, shade(CONCRETE_D, 0.8))
    b(0, -6, 1.2, 44, 30, 12, METAL)                          # hangar walls
    for x in list(range(-21, -15, 2)) + list(range(17, 22, 2)):
        b(x, 9.05, 1.4, 0.3, 0.2, 7.8, GROOVE)                # corrugated cladding either side of the door
    b(0, 9.1, 9.5, 44, 0.3, 2.2, T)                           # team band
    # Arched roof of corrugated sheet: grooves run front to back, seams across every few metres.
    arc = _barch(B, -6, 30, 22, 13.2, 10.5, METAL_L)
    for i in range(1, 36):
        t = math.pi * i / 36
        e, u = 22.1 * math.cos(t), 13.2 + 10.6 * math.sin(t)
        B.append(Box((-6 * DEPTH, e, u * HEIGHT), (30 * DEPTH, 0.28, 0.28), GROOVE if i % 3 else shade(METAL, 0.8)))
    for south in (-14, -6):
        _barc_line(B, [(e * 1.005, u + 0.05) for e, u in arc], south, GROOVE, 0.3)
    _barc_line(B, [(e * 1.01, u + 0.1) for e, u in arc], 8.85, T, 0.8)          # team trim on the front edge
    b(0, -6, 13.0, 44.6, 30.4, 0.6, shade(METAL, 0.8))                         # eaves
    b(0, 9.0, 1.2, 30, 0.6, 9, (66, 70, 80))                  # big door
    for k in range(9):
        b(0, 9.32, 2.2 + k * 0.95, 30, 0.2, 0.25, (46, 50, 58))   # roller door slats
    for k in range(8):
        b(-14 + k * 4, 9.4, 10.2, 4, 0.3, 1.0, YELLOW if k % 2 == 0 else (30, 30, 34))
    for s in (1, -1):
        b(s * 17, 9.4, 6, 1.2, 0.3, 1.2, (255, 170, 60), glow=True)
        b(s * 15.6, 9.3, 1.2, 0.6, 0.3, 9, GROOVE)            # door frame
    # Crane: lattice mast, jib and hook.
    b(-19, -18, 13.2, 1.4, 1.4, 14, YELLOW)
    for k in range(5):
        b(-19, -17.25, 14.5 + k * 2.6, 1.4, 0.2, 0.25, shade(YELLOW, 0.6))
    b(-12, -18, 26.4, 16, 1.2, 1.2, YELLOW)
    for k in range(6):
        b(-17 + k * 2.6, -17.35, 26.5, 0.25, 0.2, 1.0, shade(YELLOW, 0.6))
    b(-5, -18, 21, 0.3, 0.3, 5, GUN)
    b(-5, -18, 20, 1.2, 1.2, 1.0, GUN)
    return B


def derrick(rock=0.0):
    """Pump jack; `rock` tilts the walking beam (degrees) for the pumping animation."""
    B = []
    b = lambda *a, **k: _bbox(B, *a, **k)
    b(0, 0, 0, 22, 14, 1.4, CONCRETE)
    b(-6, 3, 1.4, 6, 4, 0.2, (40, 34, 30))                    # oil stain
    b(-2, 0, 1.4, 8, 6, 2.4, GUN)                             # motor housing
    b(-2, 0, 3.8, 6, 4, 0.4, GUN_L)
    for s in (1, -1):                                          # A-frame legs
        b(2, s * 2.2, 1.4, 1, 1, 13, METAL, rot=(("pitch", s * 14, (s * 2.2 * DEPTH, 2, 1.4)),))
    beam = (("roll", rock, (0, 2, 14.1)),)                     # beam, horse head and weight rock together
    b(2, 0, 13.4, 16, 1.4, 1.4, (60, 60, 64), rot=beam)        # walking beam
    b(10, 0, 11.2, 2.0, 2.2, 5, (40, 38, 40), rot=beam)        # horse head
    b(-6, 0, 11.6, 3, 2.4, 3, (90, 60, 40), rot=beam)          # counterweight
    rod = -math.sin(math.radians(rock)) * 8                    # the rod rides up and down with the head
    b(10, 0, 1.4, 1.2, 1.2, 9 + rod, GUN)                      # polished rod / wellhead
    b(10, 0, 1.4, 2.4, 2.4, 1.6, METAL_D)
    b(-8, 3, 1.4, 3, 3, 4, (120, 80, 50))                     # oil tank
    b(-8, 3, 5.4, 3.2, 3.2, 0.4, (90, 60, 40))
    return B


DERRICK_FRAMES = 8
DERRICK_PERIOD = 2.4   # seconds per pump stroke


def derrick_rock(i):
    return 12 * math.sin(2 * math.pi * i / DERRICK_FRAMES)


def bunker(light, manned=False):
    """A 2x2 concrete pillbox ringed with sandbags. Manned bunkers show helmets at the slits."""
    tc = team_set(light)
    T = tc["T"]
    B = []
    k2 = 2 / 3

    def b(east, south, up, w, d, h, col, glow=False, rot=()):
        _bbox(B, east * k2, south * k2, up * 0.8, w * k2, d * k2, h * 0.8, col, glow, rot)

    b(0, 0, 0, 46, 46, 1.2, CONCRETE_D)
    for k in range(10):                                         # sandbag ring
        ang = k * math.tau / 10
        ex, sy = math.cos(ang) * 19, math.sin(ang) * 19
        b(ex, sy, 1.2, 7, 6, 3.0, (170, 150, 104) if k % 2 else (158, 138, 94))
    # Octagonal pillbox: stacked, narrowing slabs.
    b(0, -1, 1.2, 30, 30, 9, CONCRETE)
    b(0, -1, 1.2, 36, 22, 9, CONCRETE)
    b(0, -1, 1.2, 22, 36, 9, CONCRETE)
    b(0, -1, 10.2, 28, 28, 2.4, shade(CONCRETE, 1.08))
    b(0, -1, 12.6, 20, 20, 1.2, shade(CONCRETE, 0.95))
    b(0, -1, 13.8, 6, 6, 1.0, GUN_L)                           # roof hatch
    b(0, 17.15, 4.2, 36, 0.3, 1.6, T)                           # team band
    for s in (1, -1):
        b(s * 18.15, -1, 4.2, 0.3, 22, 1.6, T)
    # Firing slits: front and both sides.
    slit = (20, 20, 24)
    b(0, 17.2, 7.0, 20, 0.4, 1.6, slit)
    for s in (1, -1):
        b(s * 18.2, -1, 7.0, 0.4, 14, 1.6, slit)
    if manned:   # a barrel poking out (the garrison's heads are animated by render.draw_garrison)
        b(3, 19.0, 7.4, 1, 4, 0.8, GUN)
    b(10, -14, 13.8, 0.8, 0.8, 8, GUN)                          # radio mast
    return B


def tower(light, manned=False):
    """A tall concrete guard tower on a 1x1 footprint: a tapering shaft with a steel door, a
    wider observation cab with window slits on every side, a flat overhanging roof and a
    searchlight. Manned towers show the garrison's helmets in the windows."""
    tc = team_set(light)
    T = tc["T"]
    B = []
    slit = (20, 20, 24)

    def b(east, south, up, w, d, h, col, glow=False, rot=()):
        _bbox(B, east, south, up * 0.8, w, d, h * 0.8, col, glow, rot)

    b(0, 0, 0, 15, 15, 1.0, CONCRETE_D)                          # footing slab
    # Shaft: stacked, slightly narrowing pours, with a darker seam between each.
    for k, (w, z) in enumerate(((11.0, 1.0), (10.2, 6.0), (9.4, 11.0))):
        b(0, 0, z, w, w, 5.0, CONCRETE if k % 2 == 0 else shade(CONCRETE, 0.96))
        b(0, 0, z + 4.9, w + 0.2, w + 0.2, 0.3, CONCRETE_D)
    b(0, 5.6, 1.0, 3.6, 0.3, 5.4, (70, 74, 82))                   # steel door
    b(0, 5.75, 3.6, 0.5, 0.2, 0.5, GUN_L)                         # handle
    b(0, 4.8, 9.0, 1.4, 0.3, 2.0, slit)                           # stairwell slit
    b(0, 0, 16.0, 13, 13, 1.2, shade(CONCRETE, 1.05))              # cab floor overhang
    # Observation cab: solid corners, window slits between.
    b(0, 0, 17.2, 12.4, 12.4, 6.0, CONCRETE)
    for s in (1, -1):
        b(0, s * 6.25, 19.0, 8, 0.3, 2.2, slit)                   # front/back windows
        b(s * 6.25, 0, 19.0, 0.3, 8, 2.2, slit)                   # side windows
    b(0, 6.4, 17.6, 12, 0.3, 0.9, T)                               # team band under the windows
    b(0, 0, 23.2, 14.4, 14.4, 1.0, shade(CONCRETE, 1.08))          # roof slab, overhanging
    b(0, 0, 24.2, 9, 9, 0.5, CONCRETE_D)
    b(4.4, -4.4, 24.7, 2.0, 2.0, 1.6, GUN)                         # searchlight housing
    b(4.4, -3.3, 25.3, 1.4, 0.3, 0.9, (250, 246, 210), glow=True)  # lamp
    b(-4.8, -4.8, 24.7, 0.6, 0.6, 5.0, GUN)                        # radio aerial
    if manned:   # (heads in the window are animated by render.draw_garrison)
        b(2.4, 7.4, 19.6, 0.7, 2.6, 0.6, GUN)                      # barrel through the slit
    return B

def footprint_to_screen(east, south, up):
    """Screen offset from a building's ground centre of a point given in _bbox coordinates
    (buildings are drawn at BUILD_FACING, scale 1)."""
    return east, south - up * HEIGHT * COS_E


# Where garrisoned soldiers' heads show: (east, south, up) in _bbox coordinates, one per seat,
# along the front window slit. Matches the bunker()/tower() models above.
_K2 = 2 / 3
GARRISON_SEATS = {
    "bunker": [(e * _K2, 17.2 * _K2, 7.0 * 0.8) for e in (-9, -3, 3, 9)],
    "tower": [(e, 6.25, 19.2 * 0.8) for e in (-2.2, 2.2)],
}


BUILDING_MODELS = {"command": command_center, "barracks": barracks, "yard": vehicle_yard, "bunker": bunker,
                   "tower": tower}


def under_construction(boxes, progress):
    """The building cut off at `progress` of its height, wrapped in yellow scaffolding."""
    def zrange(b):
        if isinstance(b, Box):
            return b.pos[2] - b.size[2] / 2, b.pos[2] + b.size[2] / 2
        zs = [p[2] for p in b.geometry()[0]]
        return min(zs), max(zs)

    top = max(zrange(b)[1] for b in boxes)
    cut = max(1.5, top * progress)
    out = []
    for b in boxes:
        z0, z1 = zrange(b)
        if z0 >= cut:
            continue
        if z1 > cut:
            if not isinstance(b, Box):
                continue   # round parts (domes, arches) go on once their level is reached
            h = cut - z0
            b = Box((b.pos[0], b.pos[1], z0 + h / 2), (b.size[0], b.size[1], h), b.color, b.rot, b.glow)
        out.append(b)
    ground = [b for b in boxes if isinstance(b, Box) and b.pos[2] < 3]
    hx = max(abs(b.pos[0]) + b.size[0] / 2 for b in ground) - 2
    hy = max(abs(b.pos[1]) + b.size[1] / 2 for b in ground) - 2
    pole = (176, 140, 60)
    for sx in (1, -1):
        for sy in (1, -1):
            out.append(Box((sx * hx, sy * hy, (cut + 2) / 2), (0.8, 0.8, cut + 2), pole))
    z = 4.0
    while z < cut + 1:
        for sx in (1, -1):
            out.append(Box((sx * hx, 0, z), (0.5, hy * 2, 0.5), pole))
        out.append(Box((0, hy, z), (hx * 2, 0.5, 0.5), pole))
        z += 5.0
    return out
