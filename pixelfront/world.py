"""Tile map storage and procedural desert map generation.

The desert has two levels: low ground and high plateaus. A plateau's outer ring of tiles is a
cliff face (impassable); its inside is walkable high ground, reached by ramps. Plateaus always
grow out of the rocky rim around the map, so no cliff stands on its own. Units on low ground
can't see up onto a plateau; units on top can see down (see fog.vision).
"""
import math
from collections import deque

from .config import MAP_W, MAP_H, TILE

SAND, DUNE, ROCK, CLIFF, RAMP = range(5)
PASSABLE = (SAND, DUNE, ROCK, RAMP)
LOW, HIGH = 0, 1

RIM = 2                 # tiles of impassable rock around the map edge
MIN_PLATEAU = 10        # high-ground tiles a plateau needs to be worth climbing (else solid rock)
RAMP_W = 3              # ramps are this many tiles wide, cut square into a straight stretch of cliff
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


class World:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.tiles = [SAND] * (w * h)
        self.height = bytearray(w * h)    # LOW / HIGH (cliff faces count as HIGH; ramps as LOW)
        self.blocked = bytearray(w * h)   # 1 = impassable (terrain or structure)
        self.occupant = [None] * (w * h)  # structure standing on the tile

    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y * self.w + x]

    def level(self, x, y):
        """Ground level of a tile (LOW outside the map)."""
        return self.height[y * self.w + x] if self.in_bounds(x, y) else LOW

    def set_tile(self, x, y, t):
        i = y * self.w + x
        self.tiles[i] = t
        self.blocked[i] = 1 if (t not in PASSABLE or self.occupant[i]) else 0

    def walkable(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and not self.blocked[y * self.w + x]

    def walkable_px(self, px, py):
        return self.walkable(int(px // TILE), int(py // TILE))

    def buildable(self, x, y):
        return self.walkable(x, y) and self.tiles[y * self.w + x] in (SAND, DUNE, ROCK)   # not on ramps

    def occupy(self, s):
        for y in range(s.ty, s.ty + s.size):
            for x in range(s.tx, s.tx + s.size):
                i = y * self.w + x
                self.occupant[i] = s
                self.blocked[i] = 1

    def vacate(self, s):
        for y in range(s.ty, s.ty + s.size):
            for x in range(s.tx, s.tx + s.size):
                i = y * self.w + x
                if self.occupant[i] is s:
                    self.occupant[i] = None
                    self.blocked[i] = 0 if self.tiles[i] in PASSABLE else 1

    def ramp_dir(self, x, y):
        """For a ramp tile, the (dx, dy) step that leads up onto the plateau."""
        for dx, dy in N4:
            if self.in_bounds(x + dx, y + dy) and self.level(x + dx, y + dy) == HIGH \
                    and self.tile(x + dx, y + dy) != CLIFF:
                return dx, dy
        return 0, -1


def generate(rng):
    """Build a point-symmetric desert map.

    Returns (world, [player_cc, enemy_cc], points) as tile coords; command centers are 3x3,
    capture points 1x1.
    """
    w, h = MAP_W, MAP_H

    def mirror(x, y, s=1):
        return w - s - x, h - s - y

    bases = [(6, 6), mirror(6, 6, 3)]
    points = []
    for pos in [(15, 9), (8, 25), (25, 8), (22, 22), (27, 36)]:
        points.append(pos)
        points.append(mirror(*pos))

    for _ in range(200):
        protect = set()

        def protect_rect(x, y, s, m):
            for yy in range(y - m, y + s + m):
                for xx in range(x - m, x + s + m):
                    protect.add((xx, yy))

        for x, y in bases:
            protect_rect(x, y, 3, 6)
        for x, y in points:
            protect_rect(x, y, 1, 3)

        high = _plateaus(rng, w, h, protect, mirror, bases)
        world = World(w, h)
        _carve(world, high, rng, mirror)
        _decorate(world, rng, bases, mirror, protect)
        if _connected(world, bases, points):
            return world, bases, points
    raise RuntimeError("could not generate a connected map")


def _plateaus(rng, w, h, protect, mirror, bases):
    """High-ground mask: the rim, plus plateaus that grow inward from it as chains of
    overlapping blobs, smoothed into natural shapes. Anything not joined to the rim is dropped."""
    high = bytearray(w * h)

    def rim(x, y):
        return x < RIM or y < RIM or x >= w - RIM or y >= h - RIM

    def mark(x, y):
        for px, py in ((x, y), mirror(x, y)):
            if 0 <= px < w and 0 <= py < h and (rim(px, py) or (px, py) not in protect):
                high[py * w + px] = 1

    for y in range(h):
        for x in range(w):
            if rim(x, y):
                high[y * w + x] = 1

    # Plateaus: wander inward from a point on the rim, dropping overlapping blobs as they go.
    for _ in range(rng.randint(5, 7)):
        side = rng.randrange(4)
        t = rng.uniform(0.15, 0.85)
        x, y, ang = {0: (t * w, 1, math.pi / 2), 1: (t * w, h - 2, -math.pi / 2),
                     2: (1, t * h, 0.0), 3: (w - 2, t * h, math.pi)}[side]
        ang += rng.uniform(-0.6, 0.6)
        r = rng.uniform(3.0, 4.8)
        for _ in range(rng.randint(4, 8)):
            for yy in range(int(y - r) - 1, int(y + r) + 2):
                for xx in range(int(x - r) - 1, int(x + r) + 2):
                    if (xx - x) ** 2 + (yy - y) ** 2 <= r * r + rng.uniform(-2.0, 2.0):
                        mark(xx, yy)
            x += math.cos(ang) * r * 0.9
            y += math.sin(ang) * r * 0.9
            ang += rng.uniform(-0.7, 0.7)
            r = max(2.2, min(5.5, r * rng.uniform(0.8, 1.15)))

    # Smooth twice (majority of the 3x3 block), keeping the rim solid and protected areas clear.
    for _ in range(2):
        nxt = bytearray(high)
        for y in range(RIM, h - RIM):
            for x in range(RIM, w - RIM):
                if (x, y) in protect:
                    nxt[y * w + x] = 0
                    continue
                n = sum(high[(y + dy) * w + x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                nxt[y * w + x] = 1 if n >= 5 else 0
        high = nxt

    # Keep only high ground joined to the rim: no free-standing cliffs.
    seen = bytearray(w * h)
    q = deque((x, y) for y in range(h) for x in range(w) if rim(x, y))
    for x, y in q:
        seen[y * w + x] = 1
    while q:
        x, y = q.popleft()
        for dx, dy in N4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and high[ny * w + nx] and not seen[ny * w + nx]:
                seen[ny * w + nx] = 1
                q.append((nx, ny))
    high = bytearray(1 if high[i] and seen[i] else 0 for i in range(w * h))

    # Fill pockets of low ground walled in by plateaus: they could never be reached.
    starts = [(y + 1) * w + x + 1 for x, y in bases]   # flood from both bases' centres
    low = bytearray(w * h)
    for i in starts:
        low[i] = 1
    q = deque(starts)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for dx, dy in N4:
            nx, ny = x + dx, y + dy
            j = ny * w + nx
            if 0 <= nx < w and 0 <= ny < h and not high[j] and not low[j]:
                low[j] = 1
                q.append(j)
    return bytearray(0 if low[i] else 1 for i in range(w * h))


def _carve(world, high, rng, mirror):
    """Turn the high-ground mask into tiles: cliff faces around each plateau, walkable tops, and
    ramps up onto every plateau big enough to stand on."""
    w, h = world.w, world.h

    def is_high(x, y):
        return not (0 <= x < w and 0 <= y < h) or high[y * w + x]

    face = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if high[i]:
                world.height[i] = HIGH
                rim = x < RIM or y < RIM or x >= w - RIM or y >= h - RIM
                if rim or any(not is_high(x + dx, y + dy) for dx, dy in N8):
                    face[i] = 1
                    world.set_tile(x, y, CLIFF)

    # Plateau tops (4-connected runs of non-face high ground).
    comp = [-1] * (w * h)
    comps = []
    for i in range(w * h):
        if high[i] and not face[i] and comp[i] < 0:
            cells, q = [], deque([i])
            comp[i] = len(comps)
            while q:
                j = q.popleft()
                cells.append(j)
                x, y = j % w, j // w
                for dx, dy in N4:
                    nx, ny = x + dx, y + dy
                    k = ny * w + nx
                    if 0 <= nx < w and 0 <= ny < h and high[k] and not face[k] and comp[k] < 0:
                        comp[k] = len(comps)
                        q.append(k)
            comps.append(cells)

    for cid, cells in enumerate(comps):
        if len(cells) < MIN_PLATEAU:   # too small to stand on: solid rock
            for j in cells:
                world.set_tile(j % w, j // w, CLIFF)
            continue
        if any(world.tile(*_xy(j, w)) == RAMP for j in _ring(cells, w, h)):
            continue                   # its mirror twin already carved our ramp
        spots = _ramp_spots(world, comp, cid, cells)
        if not spots:                  # no straight wall to cut a ramp into: solid rock instead
            for j in cells:
                for px, py in (_xy(j, w), mirror(*_xy(j, w))):
                    world.set_tile(px, py, CLIFF)
            continue
        rng.shuffle(spots)
        chosen = []
        want = 1 if len(cells) < 60 else 2
        for s in spots:
            if all(abs(s[0][0] - c[0][0]) + abs(s[0][1] - c[0][1]) > 10 for c in chosen):
                chosen.append(s)
            if len(chosen) == want:
                break
        for tiles in chosen:
            # Re-check against ramps already cut (a self-symmetric plateau's mirrored ramps can
            # land next to its others): the ramp, its mirror twin and both flanking tiles of
            # each must all still be solid cliff.
            (x0, y0), (x1, y1) = tiles[0], tiles[-1]
            sx, sy = x1 - x0, y1 - y0
            sx, sy = (sx > 0) - (sx < 0), (sy > 0) - (sy < 0)
            span = [(x0 - sx, y0 - sy), *tiles, (x1 + sx, y1 + sy)]
            if not all(world.in_bounds(*q) and world.tile(*q) == CLIFF and world.tile(*mirror(*q)) == CLIFF
                       for q in span):
                continue
            for x, y in tiles:
                for px, py in ((x, y), mirror(x, y)):
                    world.set_tile(px, py, RAMP)
                    world.height[py * w + px] = LOW


def _xy(i, w):
    return i % w, i // w


def _ring(cells, w, h):
    """Tiles bordering a set of cells (where its cliff face and ramps are), as sorted tile
    indices: a fixed order, so other ports of the generator (the C# one) can match it."""
    out = set()
    for j in cells:
        x, y = j % w, j // w
        for dx, dy in N8:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                out.add(ny * w + nx)
    return sorted(out)


def _ramp_spots(world, comp, cid, cells):
    """Places to cut a RAMP_W-wide ramp onto this plateau: a straight run of cliff face with the
    plateau top directly behind every tile, open low ground directly in front, and solid cliff
    either side, so the ramp sits square in the wall. Each spot is a tuple of tiles."""
    w, h = world.w, world.h
    half = RAMP_W // 2
    spots = []

    def fits(x, y, dx, dy):
        """Cliff tile with this plateau behind it (-dx, -dy) and walkable low ground in front."""
        up, down = (x - dx, y - dy), (x + dx, y + dy)
        return (world.in_bounds(*up) and world.in_bounds(*down) and world.tile(x, y) == CLIFF
                and comp[up[1] * w + up[0]] == cid
                and world.level(*down) == LOW and world.walkable(*down))

    for j in _ring(cells, w, h):
        x, y = j % w, j // w
        if x < RIM + half or y < RIM + half or x >= w - RIM - half or y >= h - RIM - half:
            continue
        for dx, dy in N4:
            px, py = dy, dx   # sideways along the wall
            tiles = [(x + px * k, y + py * k) for k in range(-half, RAMP_W - half)]
            if not all(fits(tx, ty, dx, dy) for tx, ty in tiles):
                continue
            ends = [(tiles[0][0] - px, tiles[0][1] - py), (tiles[-1][0] + px, tiles[-1][1] + py)]
            if all(world.in_bounds(*e) and world.tile(*e) == CLIFF for e in ends):
                spots.append(tuple(tiles))
    return spots


def _decorate(world, rng, bases, mirror, protect):
    """Dunes on open ground and a rocky pad around each base."""
    w, h = world.w, world.h

    def paint(x, y, t):
        for px, py in ((x, y), mirror(x, y)):
            if world.in_bounds(px, py) and world.tile(px, py) in (SAND, DUNE):
                world.set_tile(px, py, t)

    for _ in range(18):
        cx, cy = rng.randrange(w), rng.randrange(h)
        r = rng.uniform(2.0, 5.0)
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r) - 1, int(cx + r) + 2):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + rng.uniform(-3.0, 3.0) and (x, y) not in protect:
                    paint(x, y, DUNE)
    for bx, by in bases:
        cx, cy = bx + 1, by + 1
        for y in range(cy - 6, cy + 7):
            for x in range(cx - 6, cx + 7):
                if world.in_bounds(x, y) and world.tile(x, y) in (SAND, DUNE):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= 16 + rng.uniform(-4, 6):
                        world.set_tile(x, y, ROCK)


def _connected(world, bases, points):
    """Both bases, every derrick and every open tile, high ground included, must be reachable
    from the first base: nothing walkable may be cut off."""
    sx, sy = bases[0][0] + 1, bases[0][1] + 1
    seen = {(sx, sy)}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in N4:
            p = (x + dx, y + dy)
            if p not in seen and world.walkable(*p):
                seen.add(p)
                q.append(p)
    open_tiles = sum(1 for i in range(world.w * world.h) if not world.blocked[i])
    return (all((x + 1, y + 1) in seen for x, y in bases)
            and all(p in seen for p in points)
            and len(seen) == open_tiles
            and len(seen) > world.w * world.h * 0.55)
