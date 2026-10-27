"""Unit design popup: pick each unit type's loadout before training it."""
import logging

import pygame

from .config import VIEW_W, VIEW_H, TOPBAR_H, PLAYER, TEAM_COLORS, RES
from .units import UNITS
from .font import draw_text, text_width
from .modules import (slots_for, slot_label, tiers, compute_stats, base_stats, loadout_cost,
                      loadout_time, tier, tier_effects, format_stat, STAT_NAMES, LOWER_IS_BETTER,
                      loadout_summary)

log = logging.getLogger(__name__)
from .sprites import K

# A compact popup centred over the map view (about half the old full-screen panel).
PANEL = pygame.Rect(0, 0, 386, 220)
PANEL.center = (VIEW_W // 2, (TOPBAR_H + VIEW_H) // 2)
HEADER_H = 16
ROW_H = 58
FOOTER_H = 30
YELLOW = (250, 220, 110)
GREY = (170, 166, 180)
GOOD, BAD = (110, 230, 110), (240, 100, 90)

PREVIEW_W, PREVIEW_H = 46, 52   # unit preview frame, drawn over a patch of the real map
COLS_X = PANEL.x + 6 + PREVIEW_W + 6   # module columns start here
COL_W, COL_GAP = 54, 3
STAT_COL = 68                          # width of each of the two stat columns
# The unit rows scroll inside this area when there are more than fit (the Barracks has four).
LIST = pygame.Rect(PANEL.x, PANEL.y + HEADER_H, PANEL.w, PANEL.h - HEADER_H - FOOTER_H - 4)
TRACK = pygame.Rect(PANEL.right - 7, LIST.y + 2, 4, LIST.h - 4)   # the scroll bar's track
WHEEL_STEP = ROW_H // 2


class DesignScreen:
    def __init__(self, game, sprites, building, terrain):
        self.game = game
        self.sp = sprites
        self.building = building
        self.kinds = list(building.stats["trains"])
        self.hover = None  # (kind, slot, level)
        self.scroll = 0    # px the unit rows are scrolled up by
        self.drag = None   # (mouse y, scroll) when the scroll bar's thumb was grabbed
        self.backdrops = {}
        pw, ph = PREVIEW_W * RES, PREVIEW_H * RES       # the preview, in screen pixels
        for scale in (1, 2):
            # Sample the map just below the building (terrain is at screen resolution), at the
            # same zoom as the unit preview.
            w, h = pw // scale, ph // scale
            x = min(max(0, int(building.x * RES) - w // 2), terrain.get_width() - w)
            y = min(max(0, int((building.rect()[3] + 4) * RES)), terrain.get_height() - h)
            patch = terrain.subsurface((x, y, w, h))
            self.backdrops[scale] = pygame.transform.scale(patch, (pw, ph))

    def draw_preview(self, surf, kind, lo, y):
        """The unit at a modest zoom, standing on the actual map terrain (at full resolution)."""
        infantry = UNITS[kind]["cls"] == "infantry"
        scale = 2 if infantry else 1
        box = pygame.Rect(PANEL.x + 6, y, PREVIEW_W, PREVIEW_H)
        if not box.colliderect(LIST):
            return
        pv = self.backdrops[scale].copy()
        img, (ox, oy) = self.sp.unit(kind, PLAYER, lo).frame("idle", 0, 30)
        img = pygame.transform.scale(img, (img.get_width() * scale, img.get_height() * scale))
        gx, gy = pv.get_width() // 2, pv.get_height() - 10 * RES
        k = scale * RES
        shadow = pygame.Surface((UNITS[kind]["radius"] * 2 * k + 4 * RES, 5 * k), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (60, 30, 10, 80), shadow.get_rect())
        pv.blit(shadow, shadow.get_rect(center=(gx, gy + k)))
        pv.blit(img, (gx - ox * scale, gy - oy * scale))
        self.layer.image_center(pv, box.centerx, box.centery, clip=box.clip(LIST))
        pygame.draw.rect(surf, (110, 100, 122), box, 1)

    @property
    def designs(self):
        return self.building.designs

    def rows(self):
        return [(kind, LIST.y + 2 + i * ROW_H - self.scroll) for i, kind in enumerate(self.kinds)]

    @property
    def max_scroll(self):
        return max(0, len(self.kinds) * ROW_H - LIST.h)

    def scroll_to(self, px):
        self.scroll = int(min(self.max_scroll, max(0, px)))

    def thumb(self):
        """The scroll bar's thumb, or None when everything fits."""
        if not self.max_scroll:
            return None
        h = max(12, TRACK.h * LIST.h // (LIST.h + self.max_scroll))
        y = TRACK.y + (TRACK.h - h) * self.scroll // self.max_scroll
        return pygame.Rect(TRACK.x, y, TRACK.w, h)

    def buttons(self):
        """(kind, slot, level, rect) for every tier button."""
        out = []
        for kind, y in self.rows():
            for i, slot in enumerate(slots_for(kind)):
                x = COLS_X + i * (COL_W + COL_GAP)
                for lv in range(len(tiers(kind, slot))):
                    out.append((kind, slot, lv, pygame.Rect(x, y + 10 + lv * 13, COL_W, 12)))
        return out

    def close_rect(self):
        return pygame.Rect(PANEL.right - 50, PANEL.y + 3, 46, 11)

    def handle(self, ev):
        """Returns "close" when the screen should be dismissed."""
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN):
            return "close"
        if ev.type == pygame.MOUSEWHEEL and self.max_scroll:
            self.scroll_to(self.scroll - ev.y * WHEEL_STEP)
            self.hover = None
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.drag = None
        if ev.type == pygame.MOUSEMOTION:
            if self.drag:
                y0, s0 = self.drag
                th = self.thumb()
                room = TRACK.h - th.h
                self.scroll_to(s0 + (ev.pos[1] - y0) * self.max_scroll / max(1, room))
            inside = LIST.collidepoint(ev.pos)
            self.hover = next(((k, s, lv) for k, s, lv, r in self.buttons()
                               if inside and r.collidepoint(ev.pos)), None)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.close_rect().collidepoint(ev.pos):
                return "close"
            th = self.thumb()
            if th and TRACK.inflate(4, 0).collidepoint(ev.pos):
                if not th.collidepoint(ev.pos):   # click the track: jump a page that way
                    self.scroll_to(self.scroll + (LIST.h if ev.pos[1] > th.centery else -LIST.h))
                self.drag = (ev.pos[1], self.scroll)
                return None
            if not LIST.collidepoint(ev.pos):
                return None
            for kind, slot, lv, r in self.buttons():
                if r.collidepoint(ev.pos) and self.designs[kind][slot] != lv:
                    self.designs[kind][slot] = lv
                    log.info("Design at %s %s: %s %s -> %s (now %s, %d credits)", self.building.name,
                             (self.building.tx, self.building.ty), kind, slot_label(kind, slot),
                             tier(kind, slot, lv)["name"], loadout_summary(kind, self.designs[kind]),
                             loadout_cost(kind, self.designs[kind]))
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            return "close"
        return None

    def draw(self, layer):
        self.layer = layer
        surf = layer.touch()
        light, dark = TEAM_COLORS[PLAYER]
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        surf.blit(shade, (0, 0))
        pygame.draw.rect(surf, (10, 8, 14), PANEL.move(3, 3))          # drop shadow
        pygame.draw.rect(surf, (24, 22, 30), PANEL)
        pygame.draw.rect(surf, (110, 100, 122), PANEL, 1)
        draw_text(surf, f"Unit design - {self.building.name}", PANEL.x + 6, PANEL.y + 5, YELLOW)

        surf.set_clip(LIST)
        for kind, y in self.rows():
            if y + ROW_H < LIST.y or y > LIST.bottom:
                continue
            if y > LIST.y + 2:
                pygame.draw.line(surf, (60, 56, 70), (PANEL.x + 6, y - 4), (PANEL.right - 6, y - 4))
            lo = self.designs[kind]
            self.draw_preview(surf, kind, lo, y)

            slots = slots_for(kind)
            for (k, slot, lv, r) in (b for b in self.buttons() if b[0] == kind):
                if lv == 0:
                    draw_text(surf, slot_label(kind, slot), r.x, y + 2, GREY)
                chosen = lo[slot] == lv
                hovered = self.hover == (kind, slot, lv)
                pygame.draw.rect(surf, light if chosen else (70, 66, 82) if hovered else (46, 42, 56), r)
                pygame.draw.rect(surf, K if chosen else (90, 84, 104), r, 1)
                draw_text(surf, tier(kind, slot, lv)["name"], r.centerx, r.y + 4,
                          (255, 255, 255) if chosen else (210, 210, 220), shadow=dark if chosen else None,
                          align="center")
            self.draw_stats(surf, kind, lo, COLS_X + len(slots) * (COL_W + COL_GAP) + 4, y)
        surf.set_clip(None)
        th = self.thumb()
        if th:
            pygame.draw.rect(surf, (36, 33, 44), TRACK)
            grabbed = self.drag is not None
            pygame.draw.rect(surf, (150, 140, 166) if grabbed else (110, 100, 122), th)

        fy = PANEL.bottom - FOOTER_H
        pygame.draw.line(surf, (60, 56, 70), (PANEL.x + 6, fy - 2), (PANEL.right - 6, fy - 2))
        width = PANEL.w - 12
        if self.hover:
            kind, slot, lv = self.hover
            t = tier(kind, slot, lv)
            lines = [(l, YELLOW) for l in wrap(f"{t['name']}: {t.get('desc', '')}", width)]
            lines += [(l, (220, 220, 230)) for l in wrap(", ".join(tier_effects(kind, slot, lv)) or "Baseline", width)]
        else:
            lines = [(l, GREY) for l in wrap("Click a module to fit it; hover for details. Choices apply to "
                                             "units trained from now on.", width)]
        for i, (text, col) in enumerate(lines[:3]):
            draw_text(surf, text, PANEL.x + 6, fy + 1 + i * 9, col)
        cr = self.close_rect()
        pygame.draw.rect(surf, (70, 66, 82), cr)
        pygame.draw.rect(surf, (110, 100, 122), cr, 1)
        draw_text(surf, "Done [E]", cr.centerx, cr.y + 3, (230, 230, 230), align="center")

    def draw_stats(self, surf, kind, loadout, x, y):
        base = base_stats(kind)
        st = compute_stats(kind, loadout)
        keys = [k for k in ("hp", "armor", "speed", "damage", "heal", "work", "range", "cooldown", "accuracy")
                if base[k] or st[k]]
        draw_text(surf, UNITS[kind]["name"], x, y + 1, (240, 240, 240))
        for i, key in enumerate(keys):
            cx = x + (i % 2) * STAT_COL
            cy = y + 10 + (i // 2) * 8
            draw_text(surf, STAT_NAMES[key], cx, cy, GREY)
            val = format_stat(key, st[key])
            diff = st[key] - base[key]
            if abs(diff) < 1e-6:
                col = (230, 230, 230)
            else:
                better = (diff < 0) if key in LOWER_IS_BETTER else (diff > 0)
                col = GOOD if better else BAD
            draw_text(surf, val, cx + STAT_COL - 6, cy, col, align="right")
        cost = loadout_cost(kind, loadout)
        secs = loadout_time(kind, loadout)
        cy = y + 10 + ((len(keys) + 1) // 2) * 8 + 1
        draw_text(surf, f"Cost {cost}", x, cy, YELLOW)
        draw_text(surf, f"Time {secs:.0f}s", x + STAT_COL, cy, YELLOW)
        if cost != UNITS[kind]["cost"]:
            w = text_width(f"Cost {cost}")
            draw_text(surf, f"({UNITS[kind]['cost']})", x + w + 4, cy, GREY)


def wrap(text, width):
    """Split text into lines no wider than `width` px, breaking at spaces."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if text_width(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
