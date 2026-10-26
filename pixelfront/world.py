"""Tile map storage and procedural desert map generation."""
from collections import deque

from .config import MAP_W, MAP_H, TILE

SAND, DUNE, ROCK, CLIFF = range(4)
PASSABLE = (SAND, DUNE, ROCK)


class World:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.tiles = [SAND] * (w * h)
        self.blocked = bytearray(w * h)   # 1 = impassable (terrain or structure)
        self.occupant = [None] * (w * h)  # structure standing on the tile

    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def tile(self, x, y):
        return self.tiles[y * self.w + x]

    def set_tile(self, x, y, t):
        i = y * self.w + x
        self.tiles[i] = t
        self.blocked[i] = 1 if (t not in PASSABLE or self.occupant[i]) else 0

    def walkable(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and not self.blocked[y * self.w + x]

    def walkable_px(self, px, py):
        return self.walkable(int(px // TILE), int(py // TILE))

    def buildable(self, x, y):
        return self.walkable(x, y) and self.tiles[y * self.w + x] in PASSABLE

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
        world = World(w, h)
        protect = set()

        def protect_rect(x, y, s, m):
            for yy in range(y - m, y + s + m):
                for xx in range(x - m, x + s + m):
                    protect.add((xx, yy))

        for x, y in bases:
            protect_rect(x, y, 3, 6)
        for x, y in points:
            protect_rect(x, y, 1, 2)

        def paint(x, y, t):
            for px, py in ((x, y), mirror(x, y)):
                if world.in_bounds(px, py) and (px, py) not in protect:
                    world.set_tile(px, py, t)

        def blob(t, count, rmin, rmax, jitter):
            for _ in range(count):
                cx, cy = rng.randrange(w), rng.randrange(h)
                r = rng.uniform(rmin, rmax)
                for y in range(int(cy - r) - 1, int(cy + r) + 2):
                    for x in range(int(cx - r) - 1, int(cx + r) + 2):
                        if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + rng.uniform(-jitter, jitter):
                            paint(x, y, t)

        blob(DUNE, 18, 2.0, 5.0, 3.0)

        # Cliff wall around the edge.
        for i in range(w):
            for d in range(2):
                if d == 0 or rng.random() < 0.6:
                    paint(i, d, CLIFF)
                    paint(d, i, CLIFF)

        # Mesas.
        blob(CLIFF, 12, 1.5, 3.5, 1.5)
        # Ridges: wandering walls one or two tiles thick.
        for _ in range(9):
            x, y = rng.randrange(w), rng.randrange(h)
            dx, dy = rng.choice(((1, 0), (0, 1), (1, 1), (1, -1)))
            for _ in range(rng.randrange(5, 13)):
                paint(x, y, CLIFF)
                if rng.random() < 0.5:
                    paint(x + dy, y + dx, CLIFF)
                x += dx
                y += dy
                if rng.random() < 0.3:
                    dx, dy = rng.choice(((1, 0), (0, 1), (1, 1), (1, -1)))

        for bx, by in bases:
            cx, cy = bx + 1, by + 1
            for y in range(cy - 6, cy + 7):
                for x in range(cx - 6, cx + 7):
                    if world.in_bounds(x, y) and world.tile(x, y) != CLIFF:
                        if (x - cx) ** 2 + (y - cy) ** 2 <= 16 + rng.uniform(-4, 6):
                            world.set_tile(x, y, ROCK)

        if _connected(world, bases, points):
            return world, bases, points
    raise RuntimeError("could not generate a connected map")


def _connected(world, bases, points):
    sx, sy = bases[0][0] + 1, bases[0][1] + 1
    seen = {(sx, sy)}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            p = (x + dx, y + dy)
            if p not in seen and world.walkable(*p):
                seen.add(p)
                q.append(p)
    return (all((x + 1, y + 1) in seen for x, y in bases)
            and all(p in seen for p in points)
            and len(seen) > world.w * world.h * 0.55)
