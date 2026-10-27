"""Bottom control panel, sidebar build menu, top resource bar, minimap and tooltips.

Drawn on the 640x360 UI layer (see layer.py); unit and building pictures inside it are queued
as full-resolution images so they keep their detail."""
import pygame

from .config import (SCREEN_W, SCREEN_H, VIEW_W, VIEW_H, HUD_H, TOPBAR_H, TILE, PLAYER, ENEMY, NEUTRAL,
                     MAX_CAPTURERS, POINT_INCOME, SIDEBAR_W, QUEUE_MAX, RES)
from .units import UNITS
from .font import draw_text, text_width
from .modules import loadout_summary, format_stat, armor_rank_info
from .render import hp_bar, team_color
from .sprites import K, GOLD, render_minimap

PANEL = (46, 42, 50)
PANEL_L = (112, 104, 120)
PANEL_D = (24, 22, 28)
WELL = (30, 28, 36)
YELLOW = (250, 220, 110)
GREY = (170, 166, 180)

CARD_X, CARD_Y = 498, VIEW_H + 7
INFO_X = 80
TEXT_X = 128
SLOT, SLOT_STEP = 18, 20       # training-queue slots (room for 15 in a row)

# Sidebar: a big Command Center portrait (click to jump there), then the numbered build menu.
SB_X = VIEW_W
PORTRAIT = pygame.Rect(SB_X + 4, TOPBAR_H + 4, SIDEBAR_W - 8, 52)
MENU_Y = PORTRAIT.bottom + 14
ROW_H = 26


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
        self.portrait_rect = PORTRAIT
        self.sidebar = pygame.Surface((SIDEBAR_W, VIEW_H))
        self.sidebar.fill(PANEL)
        pygame.draw.line(self.sidebar, K, (0, 0), (0, VIEW_H))
        pygame.draw.line(self.sidebar, PANEL_L, (1, 0), (1, VIEW_H))
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
        return [pygame.Rect(TEXT_X + i * SLOT_STEP, VIEW_H + 48, SLOT, SLOT) for i in range(len(b.queue))]

    def menu_rects(self, n):
        return [pygame.Rect(SB_X + 4, MENU_Y + i * ROW_H, SIDEBAR_W - 8, ROW_H - 2) for i in range(n)]

    def menu_item_at(self, pos, n):
        for i, r in enumerate(self.menu_rects(n)):
            if r.collidepoint(pos):
                return i
        return None

    def queue_slot_at(self, pos, ctrl):
        sel = ctrl.selection
        if len(sel) != 1 or not sel[0].is_building or sel[0].team != PLAYER:
            return None
        for i, r in enumerate(self.queue_rects(sel[0])):
            if r.collidepoint(pos):
                return i
        return None

    def minimap_to_world(self, pos):
        r = self.minimap_rect
        x = min(max(pos[0], r.left), r.right - 1) - r.left
        y = min(max(pos[1], r.top), r.bottom - 1) - r.top
        return x * TILE + TILE / 2, y * TILE + TILE / 2

    # ---- drawing ------------------------------------------------------------

    def draw(self, layer, ctrl):
        self.layer = layer
        surf = layer.touch()
        items = ctrl.build_menu()
        self.draw_sidebar(surf, ctrl, items)
        self.draw_topbar(surf)
        surf.blit(self.panel, (0, VIEW_H))
        self.draw_minimap(surf, ctrl)
        self.draw_info(surf, ctrl)
        self.draw_card(surf, ctrl, ctrl.commands())

    def draw_overlays(self, layer, ctrl):
        """Tooltips, on the layer above the HUD's detailed pictures."""
        cmds = ctrl.commands()
        i = self.button_at(ctrl.mouse, len(cmds))
        if i is not None:
            self.draw_tooltip(layer.touch(), cmds[i], (SCREEN_W - 4, VIEW_H - 2), above=True)
        items = ctrl.build_menu()
        i = self.menu_item_at(ctrl.mouse, len(items))
        if i is not None:
            r = self.menu_rects(len(items))[i]
            self.draw_tooltip(layer.touch(), items[i], (SB_X - 3, r.y), above=False)

    def picture(self, img, cx, cy, clip=None):
        """A full-resolution picture centred on UI point (cx, cy)."""
        self.layer.image_center(img, cx, cy, clip)

    @staticmethod
    def portrait_building(ctrl):
        """The building the sidebar portrait shows: the one selected, if a single building is."""
        sel = ctrl.selection
        return sel[0] if len(sel) == 1 and sel[0].is_building else None

    def draw_sidebar(self, surf, ctrl, items):
        g = self.game
        surf.blit(self.sidebar, (SB_X, 0))
        mouse = ctrl.mouse
        # Portrait: a detailed picture of the selected building, or the Command Center when no
        # building is selected. Click to jump there.
        r = self.portrait_rect
        shown = self.portrait_building(ctrl)
        bevel(surf, r, raised=not r.collidepoint(mouse), fill=(176, 146, 98))
        if shown is not None:
            img = self.sp.building_portrait(shown.kind, shown.team, (r.w - 10) * RES, (r.h - 6) * RES)
        else:
            img = self.sp.building_portrait("command", PLAYER, (r.w - 10) * RES)
        self.picture(img, r.centerx, r.centery + 2, clip=r.inflate(-2, -2))
        if shown is None and not any(b.team == PLAYER and b.kind == "command" for b in g.buildings):
            self.layer.fill(r.inflate(-2, -2), (0, 0, 0, 150))
        elif shown is not None and not shown.complete:
            hp_bar(surf, r.x + 3, r.bottom - 5, r.w - 6, shown.progress)
        # Menu title: the selected factory, or the Command Center by default.
        title = ctrl.menu_title()
        draw_text(surf, self.clip_text(title, SIDEBAR_W - 8), SB_X + 4, r.bottom + 4, YELLOW)
        credits = g.teams[PLAYER].credits
        for it, rr in zip(items, self.menu_rects(len(items))):
            hover = rr.collidepoint(mouse)
            active = ctrl.mode == "place" and it["id"] == "build:" + str(ctrl.place_kind)
            bevel(surf, rr, raised=not active, fill=(84, 78, 96) if hover else (66, 62, 76))
            if it.get("unit"):
                kind = it["unit"]
                icon = self.sp.icon_hi("unit:" + kind, 20, PLAYER, it["design"])
            else:
                icon = self.sp.icon_hi(it["icon"], 20)
            self.picture(icon, rr.x + 12, rr.centery)
            draw_text(surf, it["key"], rr.x + 2, rr.y + 1, YELLOW)
            tx = rr.x + 25
            draw_text(surf, self.clip_text(it["name"], rr.right - tx - 2), tx, rr.y + 3, (230, 230, 230))
            ok = it["cost"] <= credits
            draw_text(surf, str(it["cost"]), tx, rr.y + 13, YELLOW if ok else (240, 90, 80))
            if it.get("unit"):
                self.draw_training(surf, ctrl, it["unit"], rr)
            if not ok:
                dim = pygame.Surface((rr.w - 2, rr.h - 2), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 90))
                surf.blit(dim, (rr.x + 1, rr.y + 1))
                self.layer.fill((rr.x + 1, rr.y + 1, 22, rr.h - 2), (0, 0, 0, 90))   # the picture too

    def draw_training(self, surf, ctrl, kind, rr):
        """How many of this unit are queued, and the progress of the one in training."""
        halls = ctrl.factories_for(kind)
        queued = sum(1 for b in halls for it in b.queue if it["kind"] == kind)
        if queued:
            draw_text(surf, f"x{queued}", rr.right - 3, rr.y + 13, (150, 220, 150), align="right")
        active = [b for b in halls if b.queue and b.queue[0]["kind"] == kind]
        if active:
            b = max(active, key=lambda b: b.prod_timer / b.queue[0]["time"])
            hp_bar(surf, rr.x + 25, rr.bottom - 3, rr.w - 28, b.prod_timer / b.queue[0]["time"])

    @staticmethod
    def clip_text(text, width):
        while text and text_width(text) > width:
            text = text[:-1]
        return text

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
                          VIEW_W // TILE, VIEW_H // TILE)
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
                if e.is_unit:
                    img = self.sp.icon_hi("unit:" + e.kind, 18, e.team, e.loadout)
                else:
                    img = self.sp.icon_hi("bld:" + e.kind, 18, e.team)
                self.picture(img, *r.center)
                hp_bar(surf, r.x + 2, r.bottom + 2, r.w - 4, e.hp / e.max_hp)
            if len(sel) > 32:
                draw_text(surf, f"+{len(sel) - 32}", CARD_X - 10, SCREEN_H - 10, GREY, align="right")
            return

        e = sel[0]
        bevel(surf, (INFO_X + 2, VIEW_H + 6, 40, 40), fill=(58, 54, 66))
        self.picture(self.sp.portrait(e), INFO_X + 22, VIEW_H + 26)
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
            draw_text(surf, f"{loadout_summary(e.kind, e.loadout)}  ({armor_rank_info(e.kind, e.loadout)[0]})",
                      x, y + 9, (200, 200, 220))
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
                self.picture(self.sp.icon_hi("unit:" + u.kind, 18, PLAYER, u.loadout), *r.center)
                hp_bar(surf, r.x + 2, r.bottom + 2, r.w - 4, u.hp / u.max_hp)
            if not e.occupants:
                draw_text(surf, "Right-click it with infantry to man it.", x, y + 18, GREY)
            return
        if e.queue:
            item = e.queue[0]
            draw_text(surf, "Training " + UNITS[item["kind"]]["name"], x, y + 9, (230, 230, 230))
            draw_text(surf, f"{len(e.queue)}/{QUEUE_MAX}", CARD_X - 8, y + 9, GREY, align="right")
            for i, (it, r) in enumerate(zip(e.queue, self.queue_rects(e))):
                bevel(surf, r, fill=(58, 54, 66))
                self.picture(self.sp.icon_hi("unit:" + it["kind"], 14, PLAYER, it["loadout"]), *r.center)
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
            active = ctrl.mode == cmd["id"]
            bevel(surf, r, raised=not active, fill=(84, 78, 96) if hover else (66, 62, 76))
            if cmd.get("unit"):
                kind = cmd["unit"]
                self.picture(self.sp.icon_hi("unit:" + kind, 26, PLAYER, cmd.get("design")),
                             *r.center)
            else:
                icon = self.sp.icons[cmd["icon"]]
                surf.blit(icon, icon.get_rect(center=r.center))
            if cmd.get("cost", 0) > credits:
                dim = pygame.Surface((r.w - 2, r.h - 2), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 130))
                surf.blit(dim, (r.x + 1, r.y + 1))
            draw_text(surf, cmd["key"], r.x + 2, r.y + 2, YELLOW)

    def draw_tooltip(self, surf, cmd, anchor, above):
        """A tooltip whose right edge sits at anchor[0]; above=True puts its bottom at anchor[1],
        otherwise its top."""
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
        x = anchor[0] - w
        y = anchor[1] - h if above else min(anchor[1], VIEW_H - h - 2)
        pygame.draw.rect(surf, (20, 16, 24), (x, y, w, h))
        pygame.draw.rect(surf, PANEL_L, (x, y, w, h), 1)
        for j, (text, col) in enumerate(lines):
            draw_text(surf, text, x + 4, y + 3 + j * 8, col)
