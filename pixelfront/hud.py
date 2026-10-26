"""Bottom control panel, top resource bar, minimap, radar and tooltips."""
import math

import pygame

from .config import (SCREEN_W, SCREEN_H, VIEW_H, HUD_H, TOPBAR_H, TILE, PLAYER, ENEMY, NEUTRAL, UNITS,
                     MAX_CAPTURERS, POINT_INCOME)
from .font import draw_text, text_width
from .modules import loadout_summary, format_stat
from .render import hp_bar, team_color
from .sprites import K, GOLD, render_minimap, fit

PANEL = (46, 42, 50)
PANEL_L = (112, 104, 120)
PANEL_D = (24, 22, 28)
WELL = (30, 28, 36)
YELLOW = (250, 220, 110)
GREY = (170, 166, 180)

CARD_X, CARD_Y = 498, VIEW_H + 7
INFO_X = 80
TEXT_X = 128


def bevel(surf, rect, raised=True, fill=None):
    rect = pygame.Rect(rect)
    if fill:
        pygame.draw.rect(surf, fill, rect)
    hi, lo = (PANEL_L, PANEL_D) if raised else (PANEL_D, PANEL_L)
    pygame.draw.line(surf, hi, rect.topleft, (rect.right - 1, rect.top))
    pygame.draw.line(surf, hi, rect.topleft, (rect.left, rect.bottom - 1))
    pygame.draw.line(surf, lo, (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1))
    pygame.draw.line(surf, lo, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1))


class HUD:
    def __init__(self, game, sprites):
        self.game = game
        self.sp = sprites
        w = game.world
        self.minimap_rect = pygame.Rect(8, VIEW_H + 8, w.w, w.h)
        self.mm_base = render_minimap(w)
        # Radar in the top-right corner: the same map in radar green.
        self.radar_rect = pygame.Rect(SCREEN_W - w.w - 5, TOPBAR_H + 4, w.w, w.h)
        self.radar_base = self.mm_base.copy()
        for y in range(w.h):
            for x in range(w.w):
                r, g, b, _ = self.radar_base.get_at((x, y))
                lum = (r * 3 + g * 4 + b) // 8
                self.radar_base.set_at((x, y), (lum // 7, 30 + lum // 3, 14 + lum // 6))
        for k in range(0, w.w, 8):
            pygame.draw.line(self.radar_base, (24, 70, 36), (k, 0), (k, w.h - 1))
            pygame.draw.line(self.radar_base, (24, 70, 36), (0, k), (w.w - 1, k))
        self.topbar = pygame.Surface((SCREEN_W, TOPBAR_H), pygame.SRCALPHA)
        self.topbar.fill((10, 8, 14, 180))
        self.panel = pygame.Surface((SCREEN_W, HUD_H))
        self.panel.fill(PANEL)
        pygame.draw.line(self.panel, K, (0, 0), (SCREEN_W, 0))
        pygame.draw.line(self.panel, PANEL_L, (0, 1), (SCREEN_W, 1))
        bevel(self.panel, (6, 6, w.w + 4, w.h + 4), raised=False, fill=WELL)
        bevel(self.panel, (INFO_X - 2, 4, CARD_X - INFO_X - 4, HUD_H - 8), raised=False, fill=WELL)
        bevel(self.panel, (CARD_X - 3, 4, SCREEN_W - CARD_X + 1, HUD_H - 8), raised=False, fill=WELL)

    # ---- hit testing --------------------------------------------------------

    def button_rects(self, n):
        return [pygame.Rect(CARD_X + (i % 4) * 34, CARD_Y + (i // 4) * 34, 32, 32) for i in range(n)]

    def button_at(self, pos, n):
        for i, r in enumerate(self.button_rects(n)):
            if r.collidepoint(pos):
                return i
        return None

    def multi_rects(self, n):
        return [pygame.Rect(INFO_X + 4 + (i % 16) * 25, VIEW_H + 9 + (i // 16) * 30, 22, 22)
                for i in range(min(n, 32))]

    def selection_icon_at(self, pos, ctrl):
        if len(ctrl.selection) < 2:
            return None
        for i, r in enumerate(self.multi_rects(len(ctrl.selection))):
            if r.collidepoint(pos):
                return i
        return None

    def queue_rects(self, b):
        return [pygame.Rect(TEXT_X + i * 25, VIEW_H + 46, 22, 22) for i in range(len(b.queue))]

    def queue_slot_at(self, pos, ctrl):
        sel = ctrl.selection
        if len(sel) != 1 or not sel[0].is_building or sel[0].team != PLAYER:
            return None
        for i, r in enumerate(self.queue_rects(sel[0])):
            if r.collidepoint(pos):
                return i
        return None

    def radar_to_world(self, pos):
        return self.minimap_to_world(pos, self.radar_rect)

    def minimap_to_world(self, pos, rect=None):
        r = rect or self.minimap_rect
        x = min(max(pos[0], r.left), r.right - 1) - r.left
        y = min(max(pos[1], r.top), r.bottom - 1) - r.top
        return x * TILE + TILE / 2, y * TILE + TILE / 2

    # ---- drawing ------------------------------------------------------------

    def draw(self, surf, ctrl):
        self.draw_topbar(surf)
        self.draw_radar(surf, ctrl)
        surf.blit(self.panel, (0, VIEW_H))
        self.draw_minimap(surf, ctrl)
        self.draw_info(surf, ctrl)
        cmds = ctrl.commands()
        self.draw_card(surf, ctrl, cmds)
        self.draw_tooltip(surf, ctrl, cmds)

    def draw_topbar(self, surf):
        g = self.game
        surf.blit(self.topbar, (0, 0))
        t = int(g.time)
        clock = f"{t // 60:02d}:{t % 60:02d}"
        if g.sandbox:
            clock += "   Test range - F5 respawns targets"
        draw_text(surf, clock, 4, 3, GREY)
        team = g.teams[PLAYER]
        supply = f"{team.supply_used}/{team.supply_cap}"
        full = team.supply_used >= team.supply_cap
        x = SCREEN_W - 6 - text_width(supply)
        draw_text(surf, supply, x, 3, (240, 90, 80) if full else (230, 230, 230))
        x -= 9
        pygame.draw.rect(surf, (200, 200, 210), (x, 3, 3, 3))
        pygame.draw.rect(surf, (200, 200, 210), (x - 1, 6, 5, 2))
        income = f"+{team.income:g}/s"
        x -= 8 + text_width(income)
        draw_text(surf, income, x, 3, (150, 220, 150))
        credits = str(int(team.credits))
        x -= 5 + text_width(credits)
        draw_text(surf, credits, x, 3, YELLOW)
        pygame.draw.rect(surf, K, (x - 8, 2, 6, 6))
        pygame.draw.rect(surf, GOLD, (x - 7, 3, 4, 4))
        pygame.draw.rect(surf, K, (x - 6, 4, 2, 2))

        for i, (text, when) in enumerate(g.messages):
            age = g.time - when
            c = 255 if age < 4 else int(255 * max(0.2, 1 - (age - 4) / 2))
            draw_text(surf, text, 4, TOPBAR_H + 4 + i * 8, (c, c, c))

    def draw_radar(self, surf, ctrl):
        """Top-right radar: fog of war, a rotating sweep and blips for everything on the map."""
        g = self.game
        r = self.radar_rect
        pygame.draw.rect(surf, (8, 14, 10), r.inflate(6, 6))
        pygame.draw.rect(surf, (70, 130, 84), r.inflate(6, 6), 1)
        surf.blit(self.radar_base, r)
        blink = int(g.time * 3) % 2
        for e in g.entities:
            if not g.seen(e):
                continue
            if e.is_unit:
                tx, ty = e.tile()
                if e.team == PLAYER:
                    surf.set_at((r.x + tx, r.y + ty), (150, 255, 160))
                else:
                    size = 2 if blink else 1
                    surf.fill((255, 70, 60), (r.x + tx, r.y + ty, size, size))
            elif e.is_point:
                surf.fill(team_color(e.team), (r.x + e.tx, r.y + e.ty, 2, 2))
            else:
                col = (110, 230, 130) if e.team == PLAYER else (230, 70, 60)
                pygame.draw.rect(surf, col, (r.x + e.tx, r.y + e.ty, e.size, e.size), 1)
        surf.blit(g.fog.small, r)
        # Sweep line with a short fading trail.
        cx, cy = r.center
        clip = surf.get_clip()
        surf.set_clip(r)
        for k in range(6):
            a = g.time * 2.0 - k * 0.07
            ex = cx + math.cos(a) * r.w * 0.75
            ey = cy + math.sin(a) * r.h * 0.75
            pygame.draw.line(surf, (40, max(0, 200 - k * 35), 70), (cx, cy), (int(ex), int(ey)))
        surf.set_clip(clip)
        cam = pygame.Rect(r.x + int(ctrl.cam_x / TILE), r.y + int(ctrl.cam_y / TILE),
                          SCREEN_W // TILE, VIEW_H // TILE)
        pygame.draw.rect(surf, (230, 240, 230), cam.clip(r), 1)
        draw_text(surf, "RADAR", r.x, r.bottom + 4, (110, 200, 120))

    def draw_minimap(self, surf, ctrl):
        g = self.game
        r = self.minimap_rect
        surf.blit(self.mm_base, r)
        for e in g.entities:
            if not g.seen(e):
                continue
            if e.is_unit:
                col = (130, 180, 255) if e.team == PLAYER else (255, 90, 80)
                tx, ty = e.tile()
                surf.set_at((r.x + tx, r.y + ty), col)
            elif e.is_point:
                pygame.draw.rect(surf, K, (r.x + e.tx - 1, r.y + e.ty - 1, 3, 3))
                surf.set_at((r.x + e.tx, r.y + e.ty), team_color(e.team))
            else:
                col = (80, 130, 240) if e.team == PLAYER else (220, 60, 50)
                pygame.draw.rect(surf, col, (r.x + e.tx, r.y + e.ty, e.size, e.size))
        surf.blit(g.fog.small, r)
        cam = pygame.Rect(r.x + int(ctrl.cam_x / TILE), r.y + int(ctrl.cam_y / TILE),
                          SCREEN_W // TILE, VIEW_H // TILE)
        pygame.draw.rect(surf, (240, 240, 240), cam.clip(r.inflate(2, 2)), 1)
        if g.alert_pos and g.time - g.last_alert < 3 and int(g.time * 4) % 2:
            ax, ay = int(g.alert_pos[0] / TILE) + r.x, int(g.alert_pos[1] / TILE) + r.y
            pygame.draw.rect(surf, (255, 60, 50), (ax - 3, ay - 3, 7, 7), 1)

    def draw_info(self, surf, ctrl):
        sel = ctrl.selection
        if not sel:
            return
        if len(sel) > 1:
            for e, r in zip(sel, self.multi_rects(len(sel))):
                bevel(surf, r, fill=(58, 54, 66))
                img = fit(self.sp.entity_image(e), 18)
                surf.blit(img, img.get_rect(center=r.center))
                hp_bar(surf, r.x + 2, r.bottom + 2, r.w - 4, e.hp / e.max_hp)
            if len(sel) > 32:
                draw_text(surf, f"+{len(sel) - 32}", CARD_X - 10, SCREEN_H - 10, GREY, align="right")
            return

        e = sel[0]
        bevel(surf, (INFO_X + 2, VIEW_H + 6, 40, 40), fill=(58, 54, 66))
        p = self.sp.portrait(e)
        surf.blit(p, p.get_rect(center=(INFO_X + 22, VIEW_H + 26)))
        x, y = TEXT_X, VIEW_H + 8
        w = draw_text(surf, e.name, x, y, YELLOW)
        if e.team == ENEMY:
            draw_text(surf, "(enemy)", x + w + 6, y, (240, 90, 80))
        if e.is_point:
            self.draw_point_info(surf, e, x, y)
            return
        hp_bar(surf, x, y + 10, 80, e.hp / e.max_hp)
        draw_text(surf, f"HP {int(max(1, e.hp))}/{e.max_hp}", x + 86, y + 9, (230, 230, 230))
        y += 20
        if e.is_unit:
            parts = []
            if e.armed:
                parts.append(f"Dmg {format_stat('damage', e.damage)}")
                parts.append(f"Rng {format_stat('range', e.range)}")
                parts.append(f"Acc {format_stat('accuracy', e.accuracy)}")
            if e.heal:
                parts.append(f"Heal {e.heal:.1f}")
            parts.append(f"Armor {e.armor}")
            parts.append(f"Spd {e.speed:.0f}")
            draw_text(surf, "  ".join(parts), x, y, GREY)
            draw_text(surf, loadout_summary(e.kind, e.loadout), x, y + 9, (200, 200, 220))
            if e.team == PLAYER:
                draw_text(surf, e.status, x, y + 18, (230, 230, 230))
            return
        if not e.complete:
            draw_text(surf, "Under construction", x, y, (230, 230, 230))
            hp_bar(surf, x, y + 9, 120, e.progress)
            return
        draw_text(surf, f"Armor {e.armor}", x, y, GREY)
        if e.team != PLAYER:
            return
        if e.capacity:   # bunker: who's manning it
            draw_text(surf, f"Garrison {len(e.occupants)}/{e.capacity}", x, y + 9, (230, 230, 230))
            for i, u in enumerate(e.occupants):
                r = pygame.Rect(TEXT_X + i * 25, VIEW_H + 46, 22, 22)
                bevel(surf, r, fill=(58, 54, 66))
                img = fit(self.sp.unit(u.kind, PLAYER, u.loadout).image, 18)
                surf.blit(img, img.get_rect(center=r.center))
                hp_bar(surf, r.x + 2, r.bottom + 2, r.w - 4, u.hp / u.max_hp)
            if not e.occupants:
                draw_text(surf, "Right-click it with infantry to man it.", x, y + 18, GREY)
            return
        if e.queue:
            item = e.queue[0]
            draw_text(surf, "Training " + UNITS[item["kind"]]["name"], x, y + 9, (230, 230, 230))
            for i, (it, r) in enumerate(zip(e.queue, self.queue_rects(e))):
                bevel(surf, r, fill=(58, 54, 66))
                img = fit(self.sp.unit(it["kind"], PLAYER, it["loadout"]).image, 18)
                surf.blit(img, img.get_rect(center=r.center))
                if i == 0:
                    hp_bar(surf, r.x + 2, r.bottom + 2, r.w - 4, e.prod_timer / it["time"])
        else:
            draw_text(surf, e.stats["desc"], x, y + 9, (230, 230, 230))

    def draw_point_info(self, surf, p, x, y):
        owner = {PLAYER: "Yours", ENEMY: "Enemy", NEUTRAL: "Neutral"}[p.team]
        draw_text(surf, f"Owner: {owner}", x, y + 11, team_color(p.team))
        draw_text(surf, f"+{POINT_INCOME:g} credits/s to its owner", x, y + 20, GREY)
        if p.contested:
            draw_text(surf, "Contested!", x, y + 31, (240, 220, 90))
        elif 0 < p.progress < 1:
            hp_bar(surf, x, y + 32, 100, p.progress, team_color(p.capturer if p.team == NEUTRAL else p.team))
        draw_text(surf, f"Park units next to it to capture (up to {MAX_CAPTURERS} speed it up).",
                  x, y + 42, GREY)

    def draw_card(self, surf, ctrl, cmds):
        credits = self.game.teams[PLAYER].credits
        mouse = ctrl.mouse
        for cmd, r in zip(cmds, self.button_rects(len(cmds))):
            hover = r.collidepoint(mouse)
            active = ctrl.mode == cmd["id"] or (ctrl.mode == "place" and cmd["id"] == "build:" + str(ctrl.place_kind))
            bevel(surf, r, raised=not active, fill=(84, 78, 96) if hover else (66, 62, 76))
            if cmd.get("unit"):
                kind = cmd["unit"]
                icon = fit(self.sp.unit(kind, PLAYER, self.game.teams[PLAYER].designs[kind]).image, 26)
            else:
                icon = self.sp.icons[cmd["icon"]]
            surf.blit(icon, icon.get_rect(center=r.center))
            if cmd.get("cost", 0) > credits:
                dim = pygame.Surface((r.w - 2, r.h - 2), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 130))
                surf.blit(dim, (r.x + 1, r.y + 1))
            draw_text(surf, cmd["key"], r.x + 2, r.y + 2, YELLOW)

    def draw_tooltip(self, surf, ctrl, cmds):
        i = self.button_at(ctrl.mouse, len(cmds))
        if i is None:
            return
        cmd = cmds[i]
        team = self.game.teams[PLAYER]
        lines = [(f"{cmd['title']} [{cmd['key'].upper()}]", YELLOW)]
        if cmd.get("desc"):
            lines.append((cmd["desc"], (230, 230, 230)))
        if cmd.get("loadout"):
            lines.append((cmd["loadout"], (200, 200, 220)))
        if cmd.get("cost"):
            ok = cmd["cost"] <= team.credits
            lines.append((f"Cost: {cmd['cost']} credits", (230, 230, 230) if ok else (240, 90, 80)))
        if cmd.get("supply"):
            ok = team.supply_used + cmd["supply"] <= team.supply_cap
            lines.append((f"Supply: {cmd['supply']}", (230, 230, 230) if ok else (240, 90, 80)))
        if cmd.get("time"):
            note = f" ({cmd['time_note']})" if cmd.get("time_note") else ""
            lines.append((f"Build time: {cmd['time']:.0f}s{note}", (230, 230, 230)))
        w = max(text_width(t) for t, _ in lines) + 8
        h = len(lines) * 8 + 5
        x, y = SCREEN_W - w - 4, VIEW_H - h - 2
        pygame.draw.rect(surf, (20, 16, 24), (x, y, w, h))
        pygame.draw.rect(surf, PANEL_L, (x, y, w, h), 1)
        for j, (text, col) in enumerate(lines):
            draw_text(surf, text, x + 4, y + 3 + j * 8, col)
