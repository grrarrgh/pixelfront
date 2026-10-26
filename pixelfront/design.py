"""Unit design screen: pick each unit type's loadout before training it."""
import logging

import pygame

from .config import SCREEN_W, VIEW_H, PLAYER, UNITS, TEAM_COLORS
from .font import draw_text, text_width
from .modules import (slots_for, slot_label, tiers, compute_stats, base_stats, loadout_cost,
                      loadout_time, tier, tier_effects, format_stat, STAT_NAMES, LOWER_IS_BETTER,
                      loadout_summary)

log = logging.getLogger(__name__)
from .sprites import K

PANEL = pygame.Rect(12, 14, SCREEN_W - 24, VIEW_H - 18)
ROW_H = 72
YELLOW = (250, 220, 110)
GREY = (170, 166, 180)
GOOD, BAD = (110, 230, 110), (240, 100, 90)


PREVIEW_W, PREVIEW_H = 78, 62   # unit preview frame, drawn over a patch of the real map


class DesignScreen:
    def __init__(self, game, sprites, building, terrain):
        self.game = game
        self.sp = sprites
        self.building = building
        self.kinds = list(building.stats["trains"])
        self.hover = None  # (kind, slot, level)
        self.backdrops = {}
        for scale in (1, 2):
            # Sample the map just below the building, at the same zoom as the unit preview.
            w, h = PREVIEW_W // scale, PREVIEW_H // scale
            x = min(max(0, int(building.x) - w // 2), terrain.get_width() - w)
            y = min(max(0, int(building.rect()[3]) + 4), terrain.get_height() - h)
            patch = terrain.subsurface((x, y, w, h))
            self.backdrops[scale] = pygame.transform.scale(patch, (PREVIEW_W, PREVIEW_H))

    def draw_preview(self, surf, kind, lo, y):
        """The unit at a modest zoom, standing on the actual map terrain."""
        infantry = UNITS[kind]["cls"] == "infantry"
        scale = 2 if infantry else 1
        box = pygame.Rect(PANEL.x + 6, y, PREVIEW_W, PREVIEW_H)
        surf.blit(self.backdrops[scale], box)
        img, (ox, oy) = self.sp.unit(kind, PLAYER, lo).frame("idle", 0, 30)
        img = pygame.transform.scale(img, (img.get_width() * scale, img.get_height() * scale))
        gx, gy = box.centerx, box.bottom - 16
        shadow = pygame.Surface((UNITS[kind]["radius"] * 2 * scale + 4, 5 * scale), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (60, 30, 10, 80), shadow.get_rect())
        surf.blit(shadow, shadow.get_rect(center=(gx, gy + scale)))
        surf.blit(img, (gx - ox * scale, gy - oy * scale))
        pygame.draw.rect(surf, (110, 100, 122), box, 1)
        draw_text(surf, UNITS[kind]["name"], box.centerx, box.y + 3, (240, 240, 240), align="center")

    @property
    def designs(self):
        return self.game.teams[PLAYER].designs

    def rows(self):
        return [(kind, PANEL.y + 20 + i * ROW_H) for i, kind in enumerate(self.kinds)]

    def buttons(self):
        """(kind, slot, level, rect) for every tier button."""
        out = []
        for kind, y in self.rows():
            slots = slots_for(kind)
            col_w = min(100, 300 // len(slots))
            for i, slot in enumerate(slots):
                x = PANEL.x + 92 + i * (col_w + 4)
                for lv in range(len(tiers(kind, slot))):
                    out.append((kind, slot, lv, pygame.Rect(x, y + 10 + lv * 13, col_w, 12)))
        return out

    def close_rect(self):
        return pygame.Rect(PANEL.right - 52, PANEL.bottom - 16, 46, 12)

    def handle(self, ev):
        """Returns "close" when the screen should be dismissed."""
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_d, pygame.K_RETURN):
            return "close"
        if ev.type == pygame.MOUSEMOTION:
            self.hover = next(((k, s, lv) for k, s, lv, r in self.buttons() if r.collidepoint(ev.pos)), None)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.close_rect().collidepoint(ev.pos):
                return "close"
            for kind, slot, lv, r in self.buttons():
                if r.collidepoint(ev.pos) and self.designs[kind][slot] != lv:
                    self.designs[kind][slot] = lv
                    log.info("Design: %s %s -> %s (now %s, %d credits)", kind, slot_label(kind, slot),
                             tier(kind, slot, lv)["name"], loadout_summary(kind, self.designs[kind]),
                             loadout_cost(kind, self.designs[kind]))
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
            return "close"
        return None

    def draw(self, surf):
        light, dark = TEAM_COLORS[PLAYER]
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        surf.blit(shade, (0, 0))
        pygame.draw.rect(surf, (24, 22, 30), PANEL)
        pygame.draw.rect(surf, (110, 100, 122), PANEL, 1)
        draw_text(surf, f"Unit design - {self.building.name}", PANEL.x + 8, PANEL.y + 6, YELLOW)
        draw_text(surf, "Choices apply to units trained from now on.", PANEL.right - 8, PANEL.y + 6,
                  GREY, align="right")

        for kind, y in self.rows():
            if y > PANEL.y + 20:
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
            self.draw_stats(surf, kind, lo, PANEL.x + 92 + len(slots) * (min(100, 300 // len(slots)) + 4) + 6, y)

        if self.hover:
            kind, slot, lv = self.hover
            t = tier(kind, slot, lv)
            line = t.get("desc", "")
            effects = ", ".join(tier_effects(kind, slot, lv)) or "Baseline"
            draw_text(surf, f"{t['name']}: {line}", PANEL.x + 8, PANEL.bottom - 24, YELLOW)
            draw_text(surf, effects, PANEL.x + 8, PANEL.bottom - 14, (220, 220, 230))
        else:
            draw_text(surf, "Click a module to fit it. Hover for details.", PANEL.x + 8, PANEL.bottom - 14, GREY)
        cr = self.close_rect()
        pygame.draw.rect(surf, (70, 66, 82), cr)
        pygame.draw.rect(surf, (110, 100, 122), cr, 1)
        draw_text(surf, "Done [D]", cr.centerx, cr.y + 4, (230, 230, 230), align="center")

    def draw_stats(self, surf, kind, loadout, x, y):
        base = base_stats(kind)
        st = compute_stats(kind, loadout)
        keys = [k for k in ("hp", "armor", "speed", "damage", "heal", "work", "range", "cooldown", "accuracy")
                if base[k] or st[k]]
        for i, key in enumerate(keys):
            cx = x + (i % 2) * 86
            cy = y + 4 + (i // 2) * 9
            draw_text(surf, STAT_NAMES[key], cx, cy, GREY)
            val = format_stat(key, st[key])
            diff = st[key] - base[key]
            if abs(diff) < 1e-6:
                col = (230, 230, 230)
            else:
                better = (diff < 0) if key in LOWER_IS_BETTER else (diff > 0)
                col = GOOD if better else BAD
            draw_text(surf, val, cx + 80, cy, col, align="right")
        cost = loadout_cost(kind, loadout)
        secs = loadout_time(kind, loadout)
        cy = y + 4 + ((len(keys) + 1) // 2) * 9 + 3
        draw_text(surf, f"Cost {cost}", x, cy, YELLOW)
        draw_text(surf, f"Time {secs:.0f}s", x + 86, cy, YELLOW)
        if cost != UNITS[kind]["cost"]:
            w = text_width(f"Cost {cost}")
            draw_text(surf, f"({UNITS[kind]['cost']})", x + w + 4, cy, GREY)
