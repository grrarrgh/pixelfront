"""Draws the map view: terrain, entities, effects, fog and selection overlays."""
import math

import pygame

from .config import TILE, VIEW_W, VIEW_H, PLAYER, NEUTRAL, BUILDINGS, TEAM_COLORS, TRACER_LIFE
from . import model3d as m3
from .units import UNITS
from .game import BOOM_TIME as SHOT_BOOM_TIME
from .sprites import K, render_terrain, unit_anim, death_frame, DEATH_STEPS

SEL_COLORS = {PLAYER: (90, 230, 90), NEUTRAL: (240, 220, 90)}
ENEMY_SEL = (235, 70, 60)
NEUTRAL_FLAG = (230, 230, 230)

FADE_TIME = 3.0   # corpses and wrecks fade out over their last seconds
BOOM_TIME = 0.45


def draw_shadow(surf, x, y, r, prone=False):
    w = r * 2 + (8 if prone else 2)
    sh = pygame.Surface((w, 5), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (60, 30, 10, 80), sh.get_rect())
    surf.blit(sh, (x - w // 2, y))


TRACER_DASH, TRACER_GAP = 3, 3   # px: bullet trails read as "- - - -", not a solid beam


TRACER_DRIFT = 1.5   # px: dashes wander up to this far off the line, more towards the far end


def draw_tracer(surf, x1, y1, x2, y2, age=0.0, seed=0.0, color=(255, 240, 170)):
    """A dashed bullet trail from (x1, y1) to (x2, y2). The dashes slide towards the target as
    the tracer ages, so a burst reads as rounds in flight, and drift a little to either side
    (more the further they get) so rounds look like they spread rather than run on rails.
    `seed` keeps one tracer's drift steady from frame to frame."""
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux   # sideways
    period = TRACER_DASH + TRACER_GAP
    d = (age / TRACER_LIFE) * period % period
    i = 0
    while d < length:
        e = min(length, d + TRACER_DASH)
        side = math.sin(seed * 997.0 + i * 2.3) * TRACER_DRIFT * (d / length)
        ox, oy = nx * side, ny * side
        pygame.draw.line(surf, color, (round(x1 + ux * d + ox), round(y1 + uy * d + oy)),
                         (round(x1 + ux * (e - 1) + ox), round(y1 + uy * (e - 1) + oy)))
        d += period
        i += 1


FLAG_W, FLAG_H, POLE_H = 8, 5, 11
# Where each building's flag pole stands: px down from the top of its sprite (on the roof).
FLAG_ROOF = {"command": 14, "barracks": 12, "yard": 12, "bunker": 10, "tower": 5}


def draw_flag(surf, x, base, color, t, phase=0.0):
    """A team flag on a pole standing at (x, base), rippling in the wind: each column of cloth
    rides a travelling wave that grows towards the free end."""
    top = base - POLE_H
    pygame.draw.line(surf, K, (x - 1, top), (x - 1, base))
    pygame.draw.line(surf, (190, 196, 206), (x, top), (x, base))
    dark = tuple(int(c * 0.7) for c in color)
    for i in range(FLAG_W):
        lift = math.sin(t * 6.0 + phase - i * 0.8) * (i / FLAG_W) * 1.6
        y0 = top + round(lift)
        shade = dark if math.cos(t * 6.0 + phase - i * 0.8) > 0.55 else color   # folds catch shadow
        pygame.draw.line(surf, shade, (x + 1 + i, y0 + 1), (x + 1 + i, y0 + FLAG_H - 1))
        surf.set_at((x + 1 + i, y0), K)
        surf.set_at((x + 1 + i, y0 + FLAG_H), K)
    end = top + round(math.sin(t * 6.0 + phase - FLAG_W * 0.8) * 1.6)
    pygame.draw.line(surf, K, (x + 1 + FLAG_W, end), (x + 1 + FLAG_W, end + FLAG_H))


def draw_garrison(surf, kind, occupants, gx, gy, t, color):
    """One head per garrisoned soldier in the structure's front window, each scanning the
    surroundings: turning slowly from side to side, pausing, with the rifle muzzle following."""
    seats = m3.GARRISON_SEATS.get(kind, [])
    n = len(occupants)
    # Spread whoever is inside across the seats (2 in a 4-seat bunker sit in the middle two).
    first = (len(seats) - n) // 2
    for i, u in enumerate(occupants[:len(seats)]):
        dx, dy = m3.footprint_to_screen(*seats[first + i])
        x, y = round(gx + dx), round(gy + dy)
        # Slow sweep with a hold at each end (clamped sine), each soldier on their own rhythm.
        look = max(-1.0, min(1.0, 1.6 * math.sin(t * (0.7 + 0.13 * (u.id % 5)) + u.id * 1.9)))
        off = round(look)
        pygame.draw.rect(surf, K, (x - 2 + off, y - 2, 4, 3))             # helmet outline
        pygame.draw.rect(surf, color, (x - 1 + off, y - 2, 2, 2))         # helmet
        face = x + off + (1 if look > 0.3 else -2 if look < -0.3 else 0)
        surf.set_at((face, y), (222, 172, 132))                           # face turned to look
        tip = x + off + round(look * 3)
        pygame.draw.line(surf, (46, 48, 54), (x + off, y + 1), (tip, y + 1))   # muzzle following


def draw_projectile(surf, p, cx, cy):
    """Draw one projectile; lobbed rounds get a ground shadow, wire-guided missiles their wire."""
    x, y = int(p.x) - cx, int(p.y) - cy
    if p.arc:   # ground shadow under a lobbed round
        pygame.draw.rect(surf, (110, 86, 60), (int(p.gx) - cx, int(p.gy) - cy, 2, 1))
    if p.trail == "wire" and p.source.alive:
        sx, sy = p.source.muzzle_pos()
        pygame.draw.line(surf, (200, 200, 190), (int(sx) - cx, int(sy) - cy), (x, y))
    tail = (int(x - p.dx * 3), int(y - p.dy * 3))
    if p.style in ("rocket", "atgm"):
        pygame.draw.line(surf, (220, 220, 220), (x, y), tail)
        pygame.draw.rect(surf, (255, 160, 60), (x, y, 1, 1))
    elif p.style == "autocannon":
        pygame.draw.line(surf, (255, 230, 140), (x, y), tail)
    elif p.style == "grenade":
        pygame.draw.rect(surf, (60, 66, 50), (x - 1, y - 1, 2, 2))
    elif p.style == "artillery":
        pygame.draw.rect(surf, (255, 230, 160), (x - 1, y - 1, 3, 3))
        pygame.draw.rect(surf, (255, 255, 230), (x, y, 1, 1))
    else:
        pygame.draw.rect(surf, (255, 230, 140), (x - 1, y - 1, 2, 2))


def draw_explosion(surf, x, y, k, r):
    """Expanding fireball; k runs 0..1 over BOOM_TIME."""
    rad = int(4 + r * 2 * k)
    pygame.draw.circle(surf, (250, 140, 40), (x, y), rad)
    pygame.draw.circle(surf, (255, 220, 120), (x, y), max(1, int(rad * (1 - k))))
    if k < 0.3:
        pygame.draw.circle(surf, (255, 255, 240), (x, y), max(1, int(rad * 0.4)))


def draw_death(surf, sprites, d, age, x, y):
    """Draw a death decal (infantry topple / vehicle wreck) `age` seconds after the kill."""
    spr = sprites.unit(d["unit"], d["team"], d["loadout"])
    fade = min(1.0, (d["life"] - age) / FADE_TIME)
    if d["kind"] == "fall":
        if d.get("prone"):
            img, (ox, oy) = spr.frame("prone", 0, d["facing"])
        else:
            img, (ox, oy) = spr.frame("die", death_frame(age), d["facing"])
        if fade < 1 or age >= DEATH_STEPS[-1]:
            img = img.copy()
            img.fill((150, 140, 130, 255), special_flags=pygame.BLEND_RGBA_MULT)
            img.set_alpha(int(255 * max(0.0, fade)))
        surf.blit(img, (x - ox, y - oy))
        return
    img, (ox, oy) = spr.frame("die", 0, d["facing"], d.get("turret", 0.0))
    if fade < 1:
        img = img.copy()
        img.set_alpha(int(255 * max(0.0, fade)))
    surf.blit(img, (x - ox, y - oy))
    if age < BOOM_TIME:
        draw_explosion(surf, x, y - 6, age / BOOM_TIME, d["r"])


def hp_bar(surf, x, y, w, frac, color=None):
    pygame.draw.rect(surf, K, (x - 1, y - 1, w + 2, 4))
    if color is None:
        color = (80, 220, 80) if frac > 0.5 else (230, 200, 60) if frac > 0.25 else (220, 60, 50)
    pygame.draw.rect(surf, color, (x, y, max(1, int(w * frac)), 2))


def team_color(team):
    return TEAM_COLORS[team][0] if team in TEAM_COLORS else NEUTRAL_FLAG


class Renderer:
    def __init__(self, game, sprites):
        self.game = game
        self.sp = sprites
        self.terrain = render_terrain(game.world, game.seed)

    def draw(self, surf, ctrl):
        g = self.game
        cx, cy = int(ctrl.cam_x), int(ctrl.cam_y)
        view = surf.subsurface((0, 0, VIEW_W, VIEW_H))
        view.blit(self.terrain, (0, 0), (cx, cy, VIEW_W, VIEW_H))

        for d in g.decals:
            self.draw_decal(view, d, cx, cy)

        selected = set(ctrl.selection)
        vis = []
        for e in g.entities:
            if e.is_unit:
                if not (-24 < e.x - cx < VIEW_W + 24 and -24 < e.y - cy < VIEW_H + 24):
                    continue
            else:
                l, t, r, b = e.rect()
                if r + 16 < cx or l - 16 > cx + VIEW_W or b + 16 < cy or t - 16 > cy + VIEW_H:
                    continue
            if g.seen(e):
                vis.append(e)
        vis.sort(key=lambda e: e.y if e.is_unit else e.rect()[3] - 8)

        for e in vis:   # building shadows go down first, on the ground under everything
            if e.is_building and e.complete:
                view.blit(self.sp.building_shadow(e.kind, e.size), (e.tx * TILE - cx, e.ty * TILE - cy))

        for e in vis:
            if e in selected:
                col = SEL_COLORS.get(e.team, ENEMY_SEL)
                if e.is_unit:
                    r = e.radius
                    pygame.draw.ellipse(view, col, (int(e.x) - cx - r - 2, int(e.y) - cy - 1, r * 2 + 4, 7), 1)
                else:
                    l, t, r, b = e.rect()
                    pygame.draw.rect(view, col, (l - cx - 1, t - cy - 1, r - l + 2, b - t + 2), 1)
            if e.is_unit:
                self.draw_unit(view, e, cx, cy)
            elif e.is_point:
                self.draw_point(view, e, cx, cy)
            else:
                self.draw_building(view, e, cx, cy)

        for tr in g.tracers:
            draw_tracer(view, tr[0] - cx, tr[1] - cy, tr[2] - cx, tr[3] - cy, tr[4], tr[5])
        for p in g.projectiles:
            draw_projectile(view, p, cx, cy)
        for b in g.booms:
            draw_explosion(view, int(b[0]) - cx, int(b[1]) - cy, (g.time - b[2]) / SHOT_BOOM_TIME, b[3])
        for p in g.particles:
            pygame.draw.rect(view, p[5], (int(p[0]) - cx, int(p[1]) - cy, 1, 1))

        for e in vis:
            if e.is_point or not (e in selected or e.hp < e.max_hp):
                continue
            if e.is_unit:
                w = max(12, e.radius * 2)
                top = int(e.y) - cy - UNITS[e.kind]["height"] - (-6 if e.suppressed else 3)
                hp_bar(view, int(e.x) - cx - w // 2, top, w, e.hp / e.max_hp)
            else:
                l, t, r, b = e.rect()
                hp_bar(view, l - cx + 4, t - cy - 4, r - l - 8, e.hp / e.max_hp)

        view.blit(g.fog.surface, (0, 0), (cx, cy, VIEW_W, VIEW_H))

        for e in ctrl.selection:
            if e.is_building and e.team == PLAYER and e.rally is not None:
                r = e.rally
                if hasattr(r, "is_point"):
                    rx, ry = int(r.x), int(r.y)
                else:
                    rx, ry = r[0] * TILE + TILE // 2, r[1] * TILE + TILE // 2
                rx, ry = rx - cx, ry - cy
                pygame.draw.line(view, K, (rx, ry), (rx, ry - 10))
                pygame.draw.rect(view, (90, 230, 90), (rx + 1, ry - 10, 5, 4))

        for m in ctrl.markers:
            k = 1 - m[2] / 0.5
            r = int(2 + 6 * k)
            x, y = int(m[0]) - cx, int(m[1]) - cy
            pygame.draw.rect(view, m[3], (x - r, y - r // 2, r * 2, r), 1)

        if ctrl.mode == "place":
            self.draw_ghost(view, ctrl, cx, cy)
        if ctrl.dragging and ctrl.drag_start:
            mx, my = ctrl.mouse
            sx, sy = ctrl.drag_start[0] - cx, ctrl.drag_start[1] - cy
            rect = pygame.Rect(min(sx, mx), min(sy, my), abs(mx - sx), abs(my - sy))
            pygame.draw.rect(view, (90, 230, 90), rect, 1)

    def draw_unit(self, view, u, cx, cy):
        spr = self.sp.unit(u.kind, u.team, u.loadout)
        anim, i = unit_anim(u)
        turret = u.turret - u.facing if u.has_turret else 0.0
        x, y = int(u.x) - cx, int(u.y) - cy
        draw_shadow(view, x, y, u.radius, u.is_infantry and u.suppressed)
        img, (ox, oy) = spr.frame(anim, i, u.facing, turret, u.steer)
        view.blit(img, (x - ox, y - oy))
        if u.flash > 0:
            fl, _ = spr.flash(anim, i, u.facing, turret, u.steer)
            view.blit(fl, (x - ox, y - oy))

    def draw_decal(self, view, d, cx, cy):
        age = self.game.time - d["t"]
        if d["kind"] == "rubble":
            x, y = d["x"] - cx, d["y"] - cy
            size = d["size"] * TILE
            pygame.draw.rect(view, (96, 84, 72), (x + 2, y + 4, size - 4, size - 6))
            for sx, sy, col in d["stones"]:
                pygame.draw.rect(view, col, (x + sx, y + sy, 4, 3))
            return
        x, y = int(d["x"]) - cx, int(d["y"]) - cy
        if -40 < x < VIEW_W + 40 and -40 < y < VIEW_H + 40:
            draw_death(view, self.sp, d, age, x, y)

    def draw_point(self, view, p, cx, cy):
        x, y = int(p.x) - cx, int(p.y) - cy
        img, (ox, oy) = self.sp.derrick(self.game.time)
        view.blit(img, (x - ox, y - oy))
        # Owner's flag on a pole in the middle of the pad, flying clear above the pump.
        draw_flag(view, x, y - 2, team_color(p.team), self.game.time, p.id)
        capturing = p.progress < 1 and p.progress > 0
        if capturing or p.contested:
            team = p.capturer if p.team == NEUTRAL else p.team
            bar = (240, 220, 90) if p.contested else team_color(team)
            hp_bar(view, x - 12, y - oy - 11, 24, p.progress, bar)

    def draw_building(self, view, e, cx, cy):
        l, t = e.tx * TILE - cx, e.ty * TILE - cy
        w = e.size * TILE
        img, (ox, oy) = self.sp.building(e.kind, e.team, e.progress, bool(e.occupants))
        bx, by = int(e.x) - cx - ox, int(e.y) - cy - oy
        view.blit(img, (bx, by))
        if not e.complete:
            return
        # Team flag on the roof at the back-right corner, waving.
        draw_flag(view, bx + img.get_width() - 12, by + FLAG_ROOF.get(e.kind, 10), team_color(e.team),
                  self.game.time, e.id * 1.7)
        if e.occupants:
            draw_garrison(view, e.kind, e.occupants, int(e.x) - cx, int(e.y) - cy, self.game.time,
                          team_color(e.team))
        if e.flash > 0:
            view.blit(self.sp.building_flash(e.kind, e.team), (bx, by))
        frac = e.hp / e.max_hp
        if frac < 0.5:
            tm = self.game.time
            for i in range(1 if frac > 0.25 else 3):
                fx = l + 4 + (e.id * 7 + i * 17) % (w - 10)
                fy = t + 12 + (e.id * 3 + i * 11) % 12
                flick = int(tm * 10 + i * 3) % 3
                pygame.draw.rect(view, (236, 110, 40), (fx, fy - flick, 4, 4 + flick))
                pygame.draw.rect(view, (255, 220, 90), (fx + 1, fy + 1, 2, 2))

    def draw_ghost(self, view, ctrl, cx, cy):
        g = self.game
        kind = ctrl.place_kind
        s = BUILDINGS[kind]["size"]
        tx, ty = ctrl.place_origin(*ctrl.to_world(ctrl.mouse))
        img, (ox, oy) = self.sp.building(kind, PLAYER)
        img = img.copy()
        img.set_alpha(150)
        view.blit(img, (int((tx + s / 2) * TILE) - cx - ox, int((ty + s / 2) * TILE) - cy - oy))
        # Green only if the whole site is legal: clear ground AND a tile's clearance from every
        # other building. Too close (or any bad tile) and the whole footprint shows red.
        ok = g.can_place(kind, tx, ty, PLAYER)
        tint = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        tint.fill((60, 220, 60, 70) if ok else (230, 40, 40, 110))
        for y in range(ty, ty + s):
            for x in range(tx, tx + s):
                view.blit(tint, (x * TILE - cx, y * TILE - cy))
