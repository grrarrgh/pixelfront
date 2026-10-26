"""Pre-rendered 3D look, C&C style: units and buildings are small models built from shaded
boxes and rendered to pixel art from a fixed high-angle camera, in any facing and pose.

Model space: x forward, y to the unit's left, z up; one unit is one pixel at scale 1.
Infantry are modelled at full size, then rendered at INF_SCALE with supersampling, which
shrinks them and rounds off their silhouettes and shading.
"""
import math

import pygame

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
    order). glow boxes ignore lighting; fixed boxes ignore the whole-body fall."""
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


def render(boxes, facing, fall=0.0, lift=0.0, outline=True, darken=1.0, scale=1.0, ss=1, texture=0.0,
           bounds=None):
    """Render boxes facing `facing` degrees (0 = east, 90 = south). Returns (surface, origin)
    where origin is the pixel that sits on the model's ground position. texture > 0 adds
    that much pixel grain (used for buildings). Pass the same `bounds` (from measure()) to
    every frame of an animation to keep them on one fixed canvas, so static parts don't jitter."""
    a = math.radians(facing)
    ca, sa = math.cos(a), math.sin(a)
    k = scale * ss
    faces = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for b in boxes:
        pts = b.corners()
        if fall and not b.fixed:
            pts = [_rotate(p, "pitch", fall, (0, 0, 0)) for p in pts]
        up = 0 if b.fixed else lift
        world = [((x * ca + y * sa) * k, (x * sa - y * ca) * k, (z + up) * k) for x, y, z in pts]
        cx = sum(p[0] for p in world) / 8
        cy = sum(p[1] for p in world) / 8
        cz = sum(p[2] for p in world) / 8
        for f in _FACES:
            p0, p1, p3 = world[f[0]], world[f[1]], world[f[3]]
            u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            v = (p3[0] - p0[0], p3[1] - p0[1], p3[2] - p0[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            n = (n[0] / ln, n[1] / ln, n[2] / ln)
            fc = [sum(world[i][j] for i in f) / 4 for j in range(3)]
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
            faces.append((fc[1] * COS_E + fc[2] * SIN_E, pts2, col))
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
    for _, pts, col in faces:
        moved = [(x + ox, y + oy) for x, y in pts]
        pygame.draw.polygon(surf, col, moved)
        pygame.draw.polygon(surf, col, moved, 1)
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


def _hold(kind, weapon, act, shield=False):
    """Arm angles {side: (shoulder, elbow)} for how this soldier holds their kit."""
    if kind == "engineer" and act == "fire":
        kind, weapon = "rifleman", 0
    if kind == "heavy":
        # M60 at the hip, grenade launcher at the shoulder, rocket tube on the shoulder;
        # with a shield the left arm holds the shield instead.
        hold = {0: {-1: (10, 70), 1: (30, 60)}, 1: {-1: (30, 70), 1: (45, 50)},
                2: {-1: (20, 110), 1: (60, 70)}}[weapon]
        if shield:
            hold = {**hold, 1: (35, 55)}
        return hold
    if kind == "rifleman":
        if weapon == 0:
            return {-1: (88, 0) if act == "fire" else (30, 45), 1: (0, 15)}
        if weapon == 2:
            return {-1: (10, 70), 1: (30, 60)}
        return {-1: (30, 70), 1: (45, 50)} if act != "fire" else {-1: (40, 70), 1: (55, 45)}
    if act == "work":
        return {1: (80, 10), -1: (5, 15)}
    return {1: (0, 15), -1: (0, 15)}


def soldier(kind, light, lo, anim="idle", i=0):
    """Boxes for an infantry unit in one animation frame.

    Returns (boxes, muzzle, fall, lift): render with those fall/lift values at INF_SCALE.
    """
    tc = team_set(light)
    armor, weapon, speed = lo.get("armor", 1), lo.get("weapon", 1), lo.get("engine", 1)
    # Heavy infantry always wear more plating than their tier name: Light = helmet + body
    # armour, Medium = full body armour, Heavy = full body armour + a ballistic shield.
    shield = kind == "heavy" and armor == 2
    if kind == "heavy":
        armor = min(2, armor + 1)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))

    firing_anims = ("fire", "pfire", "kfire", "work")
    act = {"fire": "fire", "pfire": "fire", "kfire": "fire", "work": "work"}.get(anim)
    recoil = float(i) if anim in firing_anims else 0.0
    flash = anim in firing_anims and i == 1
    moving = anim in ("walk", "prone")
    prone = anim in ("prone", "pfire")
    fall = lift = 0.0

    # Leg and arm poses for this frame.
    legs = {1: (0, -4, 0, 0), -1: (0, -4, 0, 0)}
    hold = _hold(kind, weapon, act, shield)
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

    _legs(add, tc, armor, speed, legs)
    upper_from = len(B)   # everything after the legs breathes in the idle animation
    _body(add, kind, tc, armor, weapon, speed, moving)
    _arms(add, kind, tc, armor, weapon, arms)
    W = []
    wadd = lambda *a, **k: W.append(Box(*a, **k))
    muzzle = _weapon(wadd, kind, tc, armor, weapon, act, recoil)
    if shield:   # ballistic shield on the left arm, with a vision slit
        wadd((3.6, 3.4, 10.6), (0.8, 5.0, 9.6), tc["plate"])
        wadd((3.65, 3.4, 15.5), (0.9, 5.2, 0.5), GUN)
        wadd((4.05, 3.4, 13.4), (0.2, 1.8, 0.7), CYAN, glow=True)
        for z in (8.0, 11.0):
            wadd((4.05, 3.4, z), (0.15, 4.6, 0.3), shade(tc["plate"], 0.8))
    if prone:
        # Weapons are held up overhead in the standing frame so they lie forward once prone.
        pr = ("pitch", 90, (0, 0, 13))
        W = [Box(b.pos, b.size, b.color, tuple(b.rot) + (pr,), b.glow) for b in W]
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
            big = 2.6 if kind == "heavy" else 2.0
            add(fx((mx + big / 2, my, mz)), (big, big, big), FLASH_Y, glow=True)
            add(fx((mx + 0.4, my, mz)), (big * 0.6,) * 3, FLASH_W, glow=True)
    if anim == "idle" and i:
        B[upper_from:] = _raised(B[upper_from:], IDLE_BREATH[i % len(IDLE_BREATH)])
    if muzzle:
        muzzle = transform(muzzle, fall, lift)
    return B, muzzle, fall, lift


IDLE_BREATH = (0.0, 0.25, 0.45, 0.25)   # upper-body rise per idle frame
IDLE_SHAKE = (0.0, 0.3)                 # vehicle body shake per idle frame, engine running


def _raised(boxes, dz):
    """The same boxes lifted by dz (rotation pivots too, so limbs stay attached)."""
    return [Box((b.pos[0], b.pos[1], b.pos[2] + dz), b.size, b.color,
                tuple((ax, deg, (p[0], p[1], p[2] + dz)) for ax, deg, p in b.rot), b.glow, b.fixed)
            for b in boxes]


def _legs(add, tc, armor, speed, legs):
    pants = KHAKI_D if armor == 0 else tc["pants"]
    boot = BROWN_D if speed == 0 else BOOT
    for s in (1, -1):
        hip, knee, hroll, kroll = legs[s]
        y = s * LEG_Y
        hp, kp = (0, y, HIP_Z), (0, y, KNEE_Z)
        thigh_rot = (("pitch", hip, hp), ("roll", hroll, hp))
        shin_rot = (("pitch", knee, kp), ("roll", kroll, kp)) + thigh_rot
        col = pants if s < 0 else shade(pants, 0.92)
        add((0, y, (HIP_Z + KNEE_Z) / 2), (2.6, 2.4, HIP_Z - KNEE_Z + 0.4), col, thigh_rot)
        add((0, y, 2.9), (2.4, 2.2, 3.2), col, shin_rot)
        add((0.6, y, 0.9), (3.8, 2.6, 1.8), boot, shin_rot)
        if armor == 2:
            add((1.3, y, 4.6), (0.7, 2.4, 1.8), METAL, shin_rot)     # knee plate
        if speed == 2:
            add((-1.2, y, 1.0), (0.5, 2.0, 0.8), CYAN, shin_rot, glow=True)


def _body(add, kind, tc, armor, weapon, speed, moving):
    # Armour never changes a soldier's size, only how much of them is plated:
    # light = fatigues and bare head, medium = helmet + body armour,
    # heavy = helmet + body armour + shoulder, elbow and knee plates.
    vest = tc["T"]
    hat = tc["T"]
    add((0, 0, 11.6), (3.6, 6.0, 7.2), KHAKI)
    add((0, 0, 8.6), (3.9, 6.3, 1.0), BROWN_D)
    if armor >= 1:
        add((0.1, 0, 12.2), (4.2, 6.3, 5.0), vest)
        add((2.25, -1.4, 11.4), (0.3, 1.6, 1.6), shade(vest, 0.8))
        add((2.25, 1.4, 11.4), (0.3, 1.6, 1.6), shade(vest, 0.8))
        add((0.1, 0, 14.6), (4.0, 5.4, 0.4), shade(vest, 1.15))
    fx = 2.3 if armor else 1.85
    if kind == "engineer":
        add((fx, 0, 11.0), (0.3, 6.1, 0.7), YELLOW)
    if kind == "medic":   # red cross on a white patch
        add((fx, 1.2, 13.0), (0.25, 2.6, 2.6), WHITE)
        add((fx + 0.05, 1.2, 13.0), (0.3, 0.6, 1.8), RED)
        add((fx + 0.05, 1.2, 13.0), (0.3, 1.8, 0.6), RED)

    # Head: stacked boxes so heads and helmets read as rounded.
    add((0.2, 0, 17.0), (3.4, 3.4, 3.2), SKIN)
    add((0.2, 0, 18.7), (2.6, 2.6, 0.6), SKIN)
    add((1.95, 0.8, 17.6), (0.2, 0.6, 0.6), (40, 30, 30))
    if armor == 0:
        add((-0.2, 0, 19.2), (3.0, 3.2, 0.6), BROWN_D)
        add((-1.3, 0, 18.0), (0.8, 3.2, 2.4), BROWN_D)
    else:
        add((0, 0, 18.9), (4.0, 4.0, 1.8), hat)
        add((0, 0, 20.1), (3.0, 3.0, 0.8), hat)
        add((2.0, 0, 17.9), (0.4, 3.0, 1.0), CYAN, glow=True)
        if kind == "medic":
            add((0, 0, 20.5), (2.6, 2.6, 0.15), WHITE)
            add((0, 0, 20.6), (1.8, 0.6, 0.2), RED)
            add((0, 0, 20.6), (0.6, 1.8, 0.2), RED)
        elif kind == "engineer":
            add((0, 0, 19.0), (4.1, 4.1, 0.6), YELLOW)

    # Back gear: speed slot (a heavy kit backpack takes the rucksack's place; the bedroll stays).
    backpack = kind in ("medic", "engineer") and weapon == 2
    if speed == 0:
        if not backpack:
            add((-3.7, 0, 12.0), (3.2, 5.2, 6.0), OLIVE)
            add((-3.6, 0, 15.2), (3.4, 5.4, 1.0), OLIVE_D)
        add((-3.4, 0, 16.6), (2.6, 6.4, 2.2), (96, 104, 74))
    elif speed == 2:
        add((-3.0, 0, 12.4), (2.4, 4.4, 5.0), GUN)
        add((-4.25, 0, 13.0), (0.2, 3.6, 0.6), CYAN, glow=True)
        for s in (1, -1):
            add((-3.0, s * 1.2, 9.4), (1.6, 1.4, 1.4), METAL_D)
            if moving:
                add((-3.0, s * 1.2, 8.2), (1.2, 1.0, 1.4), FLAME, glow=True)
    if backpack:
        _kit_backpack(add, kind, -3.6 if speed != 2 else -5.0)
    if kind in ("medic", "engineer") and weapon == 0:
        body, _ = KIT_COLORS[kind]
        add((0.4, -4.0, 9.4), (3.4, 1.8, 3.0), body)
        add((0.4, -4.0, 11.0), (3.6, 2.0, 0.5), shade(body, 0.8))
        _kit_mark(add, kind, 0.4, -4.95, 9.3, "y")
        sx = 2.35 if armor else 1.95
        add((sx, 0, 12.4), (0.25, 0.8, 7.2), BROWN, (("roll", -45, (sx, 0, 12.4)),))


def _arms(add, kind, tc, armor, weapon, arms):
    glove = GUN if armor == 2 else SKIN
    carry = kind if kind in ("medic", "engineer") and weapon == 1 else None
    for s in (1, -1):
        sp, ep, sr, er = arms[s]
        y = s * ARM_Y
        shp, elp = (0, y, SHOULDER_Z), (0, y, ELBOW_Z)
        upper = (("pitch", sp, shp), ("roll", sr, shp))
        lower = (("pitch", ep, elp), ("roll", er, elp)) + upper
        add((0, y, (SHOULDER_Z + ELBOW_Z) / 2), (2.0, 2.0, SHOULDER_Z - ELBOW_Z + 0.4), KHAKI, upper)
        add((0, y, ELBOW_Z - 1.3), (1.9, 1.9, 2.6), KHAKI, lower)
        add((0, y, ELBOW_Z - 3.2), (2.0, 2.0, 1.3), glove, lower)
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
        if armor == 2:
            add((0, y, SHOULDER_Z - 0.4), (2.5, 2.3, 1.6), METAL, upper)   # shoulder plate
            add((0, y, ELBOW_Z), (2.3, 2.2, 1.0), METAL, lower)           # elbow plate
        if carry and s == -1:   # kit case hanging from the right hand by its handle
            body, _ = KIT_COLORS[carry]
            add((0.3, y - 0.3, ELBOW_Z - 5.6), (4.6, 1.8, 3.2), body, lower)
            add((0.3, y - 0.3, ELBOW_Z - 3.9), (1.6, 0.6, 0.4), GUN, lower)
            _kit_mark(add, carry, 0.3, y - 1.3, ELBOW_Z - 5.6, "y", lower)


def _weapon(add, kind, tc, armor, weapon, act, recoil):
    """Weapon / tool boxes; returns the muzzle (or tool tip) point."""
    r = -recoil
    aim = act == "fire"
    if kind == "engineer" and act == "fire":
        kind, weapon = "rifleman", 0
    if kind == "heavy" and weapon == 0:   # the heavy team's light weapon is the M60
        kind, weapon = "rifleman", 2
    if kind == "heavy" and weapon == 1:   # M32-style revolving grenade launcher at the shoulder
        z = 13.6 if aim else 12.8
        add((0.4 + r, -1.6, z - 0.4), (2.6, 1.2, 2.0), GUN)
        add((3.0 + r, -1.6, z), (3.0, 1.4, 1.6), GUN)
        add((4.8 + r, -1.6, z - 0.2), (2.6, 2.8, 2.8), OLIVE_D)          # cylinder
        for dx in (-0.8, 0.8):
            add((4.8 + dx + r, -1.6, z - 0.2), (0.3, 3.0, 3.0), GUN_L)
        add((8.2 + r, -1.6, z + 0.2), (4.0, 1.6, 1.6), GUN)               # fat barrel
        add((10.3 + r, -1.6, z + 0.2), (0.4, 1.9, 1.9), GUN_L)
        add((7.2 + r, -1.6, z - 1.4), (0.8, 0.8, 1.6), GUN)               # foregrip
        add((5.8 + r, -1.6, z + 1.8), (1.0, 0.4, 1.0), GUN_L)             # ladder sight
        return (10.6 + r, -1.6, z + 0.2)
    if kind == "rifleman" and weapon == 1:            # rifle at the ready
        z = 13.4 if aim else 12.6
        add((0.6 + r, -1.6, z - 0.4), (3.0, 1.2, 2.2), BROWN)
        add((4.0 + r, -1.6, z), (5.0, 1.4, 2.0), GUN)
        add((4.0 + r, -1.6, z + 1.4), (2.6, 1.0, 1.0), GUN_L)
        add((4.6 + r, -1.6, z - 1.5), (1.2, 1.0, 2.2), GUN)
        add((9.0 + r, -1.6, z + 0.2), (5.0, 0.8, 0.8), GUN)
        return (11.5 + r, -1.6, z + 0.2)
    if kind == "rifleman" and weapon == 0:             # pistol
        z = 14.6 if aim else 11.6
        x = 7.6 if aim else 4.4
        add((x + r, -3.7, z), (3.0, 1.0, 1.2), GUN)
        add((x - 1.0 + r, -3.7, z - 0.9), (1.0, 1.0, 1.4), GUN)
        return (x + 1.6 + r, -3.7, z)
    if kind == "rifleman":                             # machine gun at the hip
        z = 10.8
        add((4.6 + r, -2.0, z), (7.0, 2.2, 2.6), GUN)
        add((0.4 + r, -2.0, z - 0.4), (3.0, 1.6, 2.0), GUN)
        add((11.6 + r, -2.0, z + 0.2), (7.0, 1.0, 1.0), GUN)
        add((10.0 + r, -2.0, z + 0.3), (4.0, 1.5, 1.5), GUN_L)
        add((4.6 + r, -2.0, z + 1.8), (2.0, 0.6, 1.0), GUN_L)
        for s in (0.5, -0.5):
            add((13.6 + r, -2.0 + s, z - 1.4), (0.6, 0.6, 2.2), GUN)
        add((3.4 + r, -3.9, z - 2.6), (3.0, 2.4, 3.0), OLIVE)
        add((3.6 + r, -3.0, z - 0.8), (1.0, 0.6, 1.8), YELLOW)
        return (15.2 + r, -2.0, z + 0.2)
    if kind == "heavy":                                # rocket launcher on the shoulder
        length, th = 16, 3.0
        z = 16.6
        front = length - 6 + r
        add((length / 2 - 6 + r, -3.4, z), (length, th, th), OLIVE)
        add((-5.6 + r, -3.4, z), (0.8, th + 0.6, th + 0.6), OLIVE_D)     # rear venturi flare
        add((front - 3, -3.4, z), (0.6, th + 0.2, th + 0.2), OLIVE_D)
        add((front + 1.2, -3.4, z), (2.4, th - 0.4, th - 0.4), (170, 70, 40))   # warhead
        add((2.6 + r, -3.4, z - th / 2 - 0.9), (1.0, 1.0, 1.8), GUN)     # grip
        add((1.0 + r, -3.4 + th / 2 + 0.6, z + 0.6), (2.0, 1.2, 1.6), GUN)   # sight unit
        return (front + 2.4, -3.4, z)
    # Medic / engineer: the left hand does the work (injector / wrench).
    if act == "work":
        x, z = 7.4, 14.8
        if kind == "medic":
            add((x, 3.7, z), (2.4, 0.6, 0.6), METAL_L)
        else:
            add((x, 3.7, z), (2.4, 0.8, 0.8), METAL_L)
            add((x + 1.4, 3.7, z), (0.8, 1.6, 1.6), METAL_L)
        return (x + 1.4, 3.7, z)
    if kind == "engineer":
        add((0.4, 3.7, 8.4), (0.8, 0.8, 3.6), METAL_L)
        add((0.4, 3.7, 6.2), (1.6, 0.8, 0.8), METAL_L)
    return (1.0, 3.7, 9.0)


KIT_COLORS = {"medic": (WHITE, RED), "engineer": (YELLOW, GUN)}


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

def _wheel(add, x, y, z, size, side, phase, steer=0.0, front=False):
    """A tyre with a hub and tread blocks; the spokes and treads turn with `phase` so it rolls.
    Steering wheels yaw by `steer` degrees and get a light rim so they stand out."""
    rot = (("yaw", steer, (x, y, z)),) if steer else ()
    w = 3.2 if front else 2.8
    add((x, y, z), (size, w, size), TYRE, rot)
    oy = y + side * (w / 2 + 0.05)
    if front:
        add((x, oy, z), (size * 0.8, 0.2, size * 0.8), METAL_L, rot)       # rim
    add((x, oy + side * 0.05, z), (size * 0.55, 0.2, size * 0.55), METAL_D, rot)
    add((x, oy + side * 0.1, z), (size * 0.3, 0.2, size * 0.3), METAL_L, rot)
    if phase % 2:
        add((x, oy + side * 0.15, z), (size * 0.75, 0.15, 0.5), METAL, rot)
    else:
        add((x, oy + side * 0.15, z), (0.5, 0.15, size * 0.75), METAL, rot)
    for k in range(4):   # tread blocks on the rolling face
        ang = (k * 90 + phase * 30) % 360
        if 200 < ang < 340:
            continue
        rx = math.cos(math.radians(ang)) * size / 2
        rz = math.sin(math.radians(ang)) * size / 2
        add((x + rx, y + side * 1.2, z + rz), (0.7, 0.5, 0.7), (60, 60, 64), rot)


def _track(add, x0, x1, y, z, h, w, side, phase):
    """A track run from x0 to x1: crawling tread bars, road wheels, sprocket and idler."""
    length = x1 - x0
    add(((x0 + x1) / 2, y, z), (length, w, h), TRACK)
    add(((x0 + x1) / 2, y, z + h / 2 - 0.3), (length - 1.0, w + 0.1, 0.4), TRACK_L)
    n = max(3, int(length / 3.0))
    step = length / n
    for k in range(n):
        x = x0 + 0.6 + ((k * step + phase * step / 3) % (length - 1.2))
        add((x, y + side * (w / 2 + 0.05), z - h / 2 + 0.6), (1.0, 0.2, 0.8), TRACK_L)
    wheels = max(2, int((length - 4) / 5.5))
    for k in range(wheels):
        x = x0 + 2.4 + k * (length - 4.8) / max(1, wheels - 1)
        add((x, y + side * (w / 2 + 0.1), z - 0.4), (2.6, 0.2, 2.6), METAL_D)
        add((x, y + side * (w / 2 + 0.2), z - 0.4), (1.0, 0.2, 1.0), METAL)
    for x in (x0 + 1.4, x1 - 1.4):
        add((x, y + side * (w / 2 + 0.15), z + 0.6), (2.2, 0.2, 2.2), GUN_L)


def _running_gear(add, speed, phase, front, rear, y, z, h, wheel, wreck=False, steer=0.0, fender=None):
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
                    _wheel(add, x, yy, wheel / 2, wheel, s, phase, steer if k == 0 else 0.0, k == 0)
        elif speed == 1:                    # half-track: big steering wheels up front, tracks behind
            fw = wheel * 1.15
            fx = front - fw / 2
            if not wreck:
                _wheel(add, fx, yy, fw / 2, fw, s, phase, steer, True)
            if fender:
                add((fx, yy, fw + 0.3), (fw + 1.2, 3.6, 0.5), fender)
                add((fx + fw / 2 + 0.5, yy, fw - 0.6), (0.5, 3.6, 1.6), fender)
            _track(add, rear, front - fw - 1.0, yy, z, h, 2.8, s, phase)
        else:                               # full tracks
            _track(add, rear, front, yy, z, h, 3.2, s, phase)


def tank(light, lo, phase=0, recoil=0.0, flash=False, moving=False, wreck=False, turret=0.0, steer=0.0,
         shake=0.0):
    B, muzzle, gear = _tank(light, lo, phase, recoil, flash, moving, wreck, turret, steer)
    if shake:   # idling engine: the body rocks on its suspension, the running gear stays put
        B[gear:] = _raised(B[gear:], shake)
        muzzle = (muzzle[0], muzzle[1], muzzle[2] + shake)
    return B, muzzle


def _tank(light, lo, phase, recoil, flash, moving, wreck, turret, steer):
    tc = team_set(light)
    armor, weapon, speed = lo.get("armor", 1), lo.get("weapon", 1), lo.get("engine", 1)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    hull = blend(tc["Td"], OLIVE, 0.35)
    hull_l = shade(hull, 1.12)

    _running_gear(add, speed, phase, 15.5, -15.5, 7.2, 3.0, 6.0, 6.4, wreck, steer, shade(hull, 0.9))
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

    # Turret group (can turn independently of the hull).
    if weapon == 2:
        turret = 0.0   # the 155mm can't traverse: the whole tank turns to aim
    tr = [("yaw", turret, TANK_PIVOT)]
    if wreck:
        tr.append(("roll", 8, (-1, 0, 12)))
    tadd = lambda pos, size, col, rot=(), glow=False: B.append(Box(pos, size, col, tuple(rot) + tuple(tr), glow))
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
    # Barrel elevation: the 155mm sits raised like an artillery piece; wrecks droop.
    elev = -10 if wreck else (14 if weapon == 2 else 0)
    bar = [("pitch", elev, pivot)] if elev else []
    if weapon == 0:     # Bushmaster II 30mm: slim barrel, muzzle brake, ammo feed box, coax
        tadd((6.8, 0, gz), (1.6, 2.6, 2.2), GUN_L)
        length, th = 11, 0.9
        tadd((7.4 + length / 2 + r, 0, gz), (length, th, th), GUN, bar)
        tadd((7.4 + length + 0.5 + r, 0, gz), (1.0, 1.4, 1.4), GUN, bar)
        tadd((4.0, -3.7, gz), (2.4, 1.4, 1.8), GUN)
        tadd((8.0, 1.8, gz - 1.0), (4.0, 0.7, 0.7), GUN)
        muzzle_x = 7.4 + length + 1.0
    elif weapon == 1:   # 120mm smoothbore: thick barrel, fume extractor, thermal sleeve bands
        tadd((6.8, 0, gz), (1.8, 4.0, 3.0), GUN_L)
        length, th = 13, 2.0
        tadd((7.4 + length / 2 + r, 0, gz), (length, th, th), GUN, bar)
        tadd((7.4 + length / 2 + r, 0, gz + th / 2), (length - 0.6, th * 0.5, 0.15), GUN_L, bar)
        tadd((7.4 + length * 0.45 + r, 0, gz), (2.6, th + 0.9, th + 0.9), GUN, bar)
        for k in (0.25, 0.7, 0.85):
            tadd((7.4 + length * k + r, 0, gz), (0.4, th + 0.3, th + 0.3), GUN_L, bar)
        muzzle_x = 7.4 + length
    else:               # 155mm artillery: long raised barrel, double-baffle brake, recuperators, bustle
        tadd((6.8, 0, gz), (2.2, 4.8, 3.4), GUN_L)
        length, th = 19, 2.8
        tadd((7.4 + length / 2 + r, 0, gz), (length, th, th), GUN, bar)
        tadd((7.4 + length * 0.35 + r, 0, gz), (3.0, th + 1.0, th + 1.0), GUN, bar)
        for s in (0.9, -0.9):
            tadd((9.6 + r, s, gz + th / 2 + 0.5), (5.0, 0.8, 0.8), GUN_L, bar)
        for dx in (0.6, 2.2):
            tadd((7.4 + length + dx + r, 0, gz), (1.0, th + 2.2, th + 1.0), GUN, bar)
        tadd((-9.4, 0, 13.4), (4.4, 8.6, 3.6), T)                       # turret bustle
        muzzle_x = 7.4 + length + 2.8
    muzzle = (muzzle_x + r, 0, gz)
    if elev:
        muzzle = _rotate(muzzle, "pitch", elev, pivot)
    if flash:
        a = math.radians(elev)
        fx, fz = math.cos(a), math.sin(a)
        size = {0: 2.0, 1: 3.2, 2: 4.0}[weapon]
        tadd((muzzle[0] + fx * size / 2, 0, muzzle[2] + fz * size / 2), (size, size, size), FLASH_Y, glow=True)
        tadd((muzzle[0] + fx * 0.8, 0, muzzle[2] + fz * 0.8), (size * 0.6,) * 3, FLASH_W, glow=True)
    return B, _rotate(muzzle, "yaw", turret, TANK_PIVOT), gear


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
    armor, weapon, speed = lo.get("armor", 1), lo.get("weapon", 1), lo.get("engine", 1)
    B = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    body = tc["T"]
    _running_gear(add, speed, phase, 11.0, -11.0, 6.0, 2.4, 4.6, 5.2, wreck, steer, shade(body, 0.8))
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
        add((-12.2, 0, 7.6), (1.0, 4.4, 4.4), TYRE)                   # spare wheel
        add((-12.75, 0, 7.6), (0.2, 2.0, 2.0), METAL_D)

    # Weapon station: gunner + weapon swivel together on the pintle.
    yaw = ("yaw", turret, JEEP_PIVOT)
    wadd = lambda pos, size, col, glow=False: B.append(Box(pos, size, col, (yaw,), glow))
    wadd((-7.5, 0, 11.6), (2.6, 4.0, 3.6), body)
    wadd((-7.5, 0, 14.6), (2.4, 2.4, 2.4), SKIN)
    wadd((-7.5, 0, 15.9), (2.8, 2.8, 1.4), tc["Td"])
    if armor == 2:
        wadd((-1.6, 0, 15.6), (0.5, 4.8, 3.2), tc["plate"])            # gun shield
    r = -recoil
    z = 14.8
    if weapon == 0:     # M2 Browning: boxy receiver, perforated barrel jacket, spade grips
        wadd((-3.6 + r, 0, z), (3.6, 1.8, 2.0), GUN)
        wadd((0.8 + r, 0, z + 0.2), (5.0, 1.1, 1.1), GUN_L)
        for k in range(4):
            wadd((-0.8 + k * 1.2 + r, 0, z + 0.78), (0.4, 0.6, 0.1), GUN)
        wadd((4.0 + r, 0, z + 0.2), (1.6, 0.7, 0.7), GUN)
        for s in (0.6, -0.6):
            wadd((-5.7 + r, s, z), (0.6, 0.5, 1.2), GUN)
        wadd((-3.6 + r, -1.7, z - 0.4), (1.6, 1.2, 1.4), OLIVE)
        muzzle = (4.8 + r, 0, z + 0.2)
    elif weapon == 1:   # UAG-40 automatic grenade launcher: chunky receiver, short fat barrel, big ammo box
        wadd((-3.4 + r, 0, z), (4.4, 2.4, 2.4), GUN)
        wadd((-3.4 + r, 0, z + 1.3), (3.6, 1.6, 0.3), GUN_L)
        wadd((0.6 + r, 0, z + 0.2), (2.8, 1.5, 1.5), GUN)
        wadd((2.2 + r, 0, z + 0.2), (0.6, 1.8, 1.8), GUN_L)
        wadd((-3.4 + r, -2.6, z - 0.6), (2.6, 2.6, 2.2), OLIVE)
        wadd((-3.4 + r, -1.4, z + 0.2), (1.0, 0.8, 0.6), YELLOW)       # linked grenades feeding in
        muzzle = (2.6 + r, 0, z + 0.2)
    else:               # twin wire-guided missile tubes on a mount with a guidance sight
        wadd((-3.4, 0, z - 0.6), (2.0, 1.8, 1.8), GUN)
        wadd((-2.35, 0, z - 0.4), (0.1, 0.8, 0.6), CYAN, glow=True)
        for s in (1.0, -1.0):
            wadd((-1.0 + r, s, z + 0.9), (8.0, 1.5, 1.5), OLIVE)
            wadd((3.1 + r, s, z + 0.9), (0.4, 1.7, 1.7), GUN)
            wadd((-5.1 + r, s, z + 0.9), (0.4, 1.7, 1.7), GUN)
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
    b(0, 13.0, 2, 12, 0.6, 8, (46, 50, 58))                  # main door
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
    b(17, -16, 14.7, 0.8, 0.8, 12, GUN)                       # flag pole + team flag
    b(19.8, -16, 23.5, 5, 0.4, 3, T)
    return B


def vehicle_yard(light):
    tc = team_set(light)
    T = tc["T"]
    B = []
    b = lambda *a, **k: _bbox(B, *a, **k)
    b(0, 0, 0, 46, 46, 1.2, CONCRETE)
    b(0, 18, 1.2, 40, 8, 0.2, CONCRETE_D)                     # apron
    b(0, -6, 1.2, 44, 30, 12, METAL)                          # hangar walls
    for k, (w, hgt) in enumerate(((44, 3), (40, 3), (32, 2.6), (20, 2))):   # arched roof
        b(0, -6, 13.2 + k * 2.9, w, 30, hgt, shade(METAL_L, 1.0 - 0.04 * k))
    for x in range(-18, 20, 6):
        b(x, -6, 13.2, 0.4, 30.2, 0.4, METAL_D)               # roof ribs
    b(0, 9.1, 9.5, 44, 0.3, 2.2, T)                           # team band
    b(0, 9.0, 1.2, 30, 0.6, 9, (66, 70, 80))                  # big door
    for k in range(4):
        b(0, 9.3, 2.5 + k * 2, 30, 0.2, 0.3, (52, 56, 64))
    for k in range(8):
        b(-14 + k * 4, 9.4, 10.2, 4, 0.3, 1.0, YELLOW if k % 2 == 0 else (30, 30, 34))
    for s in (1, -1):
        b(s * 17, 9.4, 6, 1.2, 0.3, 1.2, (255, 170, 60), glow=True)
    # Crane: mast, jib and hook.
    b(-19, -18, 13.2, 1.4, 1.4, 14, YELLOW)
    b(-12, -18, 26.4, 16, 1.2, 1.2, YELLOW)
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
    if manned:   # helmets of the garrison in the slits, and a barrel poking out
        for e in (-6, 0, 6):
            b(e, 16.4, 7.2, 3, 2, 1.4, T)
        b(3, 19.0, 7.4, 1, 4, 0.8, GUN)
    b(10, -14, 13.8, 0.8, 0.8, 8, GUN)                          # radio mast
    return B


BUILDING_MODELS = {"command": command_center, "barracks": barracks, "yard": vehicle_yard, "bunker": bunker}


def under_construction(boxes, progress):
    """The building cut off at `progress` of its height, wrapped in yellow scaffolding."""
    top = max(b.pos[2] + b.size[2] / 2 for b in boxes)
    cut = max(1.5, top * progress)
    out = []
    for b in boxes:
        z0 = b.pos[2] - b.size[2] / 2
        z1 = b.pos[2] + b.size[2] / 2
        if z0 >= cut:
            continue
        if z1 > cut:
            h = cut - z0
            b = Box((b.pos[0], b.pos[1], z0 + h / 2), (b.size[0], b.size[1], h), b.color, b.rot, b.glow)
        out.append(b)
    hx = max(abs(b.pos[0]) + b.size[0] / 2 for b in boxes if b.pos[2] < 3) - 2
    hy = max(abs(b.pos[1]) + b.size[1] / 2 for b in boxes if b.pos[2] < 3) - 2
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
