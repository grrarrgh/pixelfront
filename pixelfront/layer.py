"""Screen composition.

The world and every piece of detailed art (units, buildings, portraits) is drawn straight onto
the screen at full resolution (RES screen pixels per game pixel). The UI - panels, sidebar,
pixel-font text - is drawn on a 640x360 Layer and scaled up RES times on top, so it keeps its
chunky look. Detailed images that sit inside the UI (sidebar icons, portraits) are queued on the
layer with image() and composited at full resolution over it.
"""
import pygame

from .config import SCREEN_W, SCREEN_H, RES

CLEAR = (0, 0, 0, 0)


class Layer:
    def __init__(self):
        self.surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.hires = []      # ("img", surface, screen pos) / ("fill", screen rect, rgba), in order
        self.used = False

    def begin(self):
        """Start a new frame: an empty layer."""
        if self.used:
            self.surf.fill(CLEAR)
        self.hires = []
        self.used = False
        return self.surf

    def touch(self):
        """Note that something was drawn on the layer this frame (so it gets composited)."""
        self.used = True
        return self.surf

    def image(self, img, x, y):
        """A full-resolution image with its top-left at UI position (x, y)."""
        self.used = True
        self.hires.append(("img", img, (round(x * RES), round(y * RES))))

    def image_center(self, img, cx, cy, clip=None):
        """A full-resolution image centred on UI point (cx, cy), optionally clipped to a UI rect."""
        w, h = img.get_size()
        pos = (round(cx * RES - w / 2), round(cy * RES - h / 2))
        self.used = True
        if clip is None:
            self.hires.append(("img", img, pos))
        else:
            r = pygame.Rect(clip)
            self.hires.append(("clip", img, pos, pygame.Rect(r.x * RES, r.y * RES, r.w * RES, r.h * RES)))

    def fill(self, rect, rgba):
        """A translucent fill over a UI rect, at full resolution (e.g. dimming a hi-res icon)."""
        r = pygame.Rect(rect)
        self.used = True
        self.hires.append(("fill", pygame.Rect(r.x * RES, r.y * RES, r.w * RES, r.h * RES), rgba))

    def composite(self, screen):
        if not self.used:
            return
        screen.blit(pygame.transform.scale(self.surf, (SCREEN_W * RES, SCREEN_H * RES)), (0, 0))
        for item in self.hires:
            kind = item[0]
            if kind == "img":
                screen.blit(item[1], item[2])
            elif kind == "clip":
                clip = screen.get_clip()
                screen.set_clip(item[3])
                screen.blit(item[1], item[2])
                screen.set_clip(clip)
            else:
                dim = pygame.Surface(item[1].size, pygame.SRCALPHA)
                dim.fill(item[2])
                screen.blit(dim, item[1].topleft)


def ui_mouse():
    """The mouse position on the 640x360 UI grid (what all input handling works in)."""
    x, y = pygame.mouse.get_pos()
    return x // RES, y // RES


def to_ui(ev):
    """A mouse event with its position converted from screen pixels to the UI grid."""
    if ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        d = dict(ev.dict)
        d["pos"] = (ev.pos[0] // RES, ev.pos[1] // RES)
        if "rel" in d:
            d["rel"] = (ev.rel[0] / RES, ev.rel[1] / RES)
        return pygame.event.Event(ev.type, d)
    return ev
