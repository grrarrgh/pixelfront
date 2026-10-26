"""Player fog of war: black where unexplored, dimmed where explored but not currently seen."""
import pygame

from .config import TILE, PLAYER

_circles = {}


def _circle(r):
    pts = _circles.get(r)
    if pts is None:
        pts = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1) if dx * dx + dy * dy <= r * r + r]
        _circles[r] = pts
    return pts


class Fog:
    def __init__(self, world):
        self.w, self.h = world.w, world.h
        self.visible = bytearray(self.w * self.h)
        self.explored = bytearray(self.w * self.h)
        self.small = None    # one pixel per tile, used by the minimap
        self.surface = None  # full map size, used by the main view
        self.reveal_all = False

    def update(self, game):
        w, h = self.w, self.h
        if self.reveal_all:
            self.visible = bytearray(b"\x01" * (w * h))
            self.explored = bytearray(b"\x01" * (w * h))
            if self.surface is None:
                self._redraw()
            return
        vis = bytearray(w * h)
        exp = self.explored
        for e in game.entities:
            if e.team != PLAYER:
                continue
            if e.is_unit:
                cx, cy = e.tile()
                r = e.sight
            else:
                cx, cy = e.center_tile()
                r = e.sight + e.size // 2
            for dx, dy in _circle(r):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    i = y * w + x
                    vis[i] = 1
                    exp[i] = 1
        self.visible = vis
        self._redraw()

    def _redraw(self):
        w, h = self.w, self.h
        buf = bytearray(w * h * 4)
        buf[3::4] = bytes(0 if v else (120 if e else 255) for v, e in zip(self.visible, self.explored))
        self.small = pygame.image.frombuffer(bytes(buf), (w, h), "RGBA").copy()
        # Soften to quarter-tile steps, then blow up with hard pixels for a chunky edge.
        mid = pygame.transform.smoothscale(self.small, (w * 4, h * 4))
        self.surface = pygame.transform.scale(mid, (w * TILE, h * TILE))
