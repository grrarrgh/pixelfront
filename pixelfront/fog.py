"""Vision and the player's fog of war (black where unexplored, dimmed where explored but not
currently seen).

High ground: nobody can see up onto a plateau from below, but from on top you see down as
normal. Cliff faces themselves are visible from below.
"""
import pygame

from .config import PLAYER
from .world import CLIFF, HIGH

_circles = {}


def _circle(r):
    pts = _circles.get(r)
    if pts is None:
        pts = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if dx * dx + dy * dy <= r * r + r]
        _circles[r] = pts
    return pts


def vision(game, team):
    """Tiles `team` can currently see, as a bytearray (1 = visible)."""
    world = game.world
    w, h = world.w, world.h
    height, tiles = world.height, world.tiles
    vis = bytearray(w * h)
    for e in game.entities:
        if e.team != team:
            continue
        if e.is_unit:
            cx, cy = e.tile()
            r = e.sight
        else:
            cx, cy = e.center_tile()
            r = e.sight + e.size // 2
        up_high = world.level(cx, cy) == HIGH
        for dx, dy in _circle(r):
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h:
                i = y * w + x
                if up_high or height[i] != HIGH or tiles[i] == CLIFF:
                    vis[i] = 1
    return vis


class Fog:
    def __init__(self, world):
        self.w, self.h = world.w, world.h
        self.visible = bytearray(self.w * self.h)
        self.explored = bytearray(self.w * self.h)
        self.small = None    # one pixel per tile, used by the minimap
        self.mid = None      # one pixel per quarter tile; the view enlarges the part on screen
        self.version = 0     # bumped on every redraw, so the view knows when to re-enlarge
        self.reveal_all = False

    def update(self, game):
        w, h = self.w, self.h
        if self.reveal_all:
            self.visible = bytearray(b"\x01" * (w * h))
            self.explored = bytearray(b"\x01" * (w * h))
            if self.mid is None:
                self._redraw()
            return
        vis = vision(game, PLAYER)
        self.explored = bytearray(a | b for a, b in zip(self.explored, vis))
        self.visible = vis
        self._redraw()

    def _redraw(self):
        w, h = self.w, self.h
        buf = bytearray(w * h * 4)
        buf[3::4] = bytes(0 if v else (120 if e else 255) for v, e in zip(self.visible, self.explored))
        self.small = pygame.image.frombuffer(bytes(buf), (w, h), "RGBA").copy()
        # Soften to quarter-tile steps; the view blows these up with hard pixels for a chunky edge.
        self.mid = pygame.transform.smoothscale(self.small, (w * 4, h * 4))
        self.version += 1
