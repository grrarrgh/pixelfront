"""Draws the map view at full screen resolution (RES screen pixels per game pixel): terrain,
entities, effects, fog and selection overlays. Positions in the world are in game pixels; the
drawing helpers here take screen pixels and a scale k (screen pixels per game pixel)."""
import math

import pygame

from .config import TILE, VIEW_W, VIEW_H, PLAYER, NEUTRAL, BUILDINGS, TEAM_COLORS, TRACER_LIFE, RES
from . import model3d as m3
from .units import UNITS
from .game import BOOM_TIME as SHOT_BOOM_TIME
from .sprites import K, render_terrain, unit_anim, death_frame, DEATH_STEPS, silhouette, shade
from .entities import PING_TIME
from .controller import MARKER_TIME

PING_ALPHA = 80      # peak opacity of a structure's acknowledgement flash (a damage flash is 255)

SEL_COLORS = {PLAYER: (90, 230, 90), NEUTRAL: (240, 220, 90)}
ENEMY_SEL = (235, 70, 60)
NEUTRAL_FLAG = (230, 230, 230)

FADE_TIME = 3.0   # corpses and wrecks fade out over their last seconds
BOOM_TIME = 0.45

_shadows = {}


def draw_shadow(surf, x, y, r, prone=False, k=RES):
    """Soft ellipse on the ground under a unit standing at screen (x, y); r in game pixels."""
    w = (r * 2 + (8 if prone else 2)) * k
    sh = _shadows.get((w, k))
    if sh is None:
        sh = _shadows[(w, k)] = pygame.Surface((w, 5 * k), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (60, 30, 10, 80), sh.get_rect())
    surf.blit(sh, (x - w // 2, y))


TRACER_STREAK = 5    # game px: the bright head of a round in flight
TRACER_TAIL = 7      # game px: the faint trail behind it


def draw_tracer(surf, x1, y1, x2, y2, age=0.0, seed=0.0, color=(255, 240, 170), k=RES):
    """One round in flight from (x1, y1) to (x2, y2) (screen px): a short bright streak with a
    fading tail, travelling the whole way over the tracer's life. Rounds in a burst each take
    their own line (see weapons.SPRAY_CONE), so they read as a spray rather than one beam.
    `seed` is unused; it keeps the tracer record format."""
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    head = min(length, (age / TRACER_LIFE + 0.15) * length)
    at = lambda d: (round(x1 + ux * d), round(y1 + uy * d))
    tail = max(0.0, head - TRACER_STREAK * k)
    pygame.draw.line(surf, shade(color, 0.62), at(max(0.0, tail - TRACER_TAIL * k)), at(tail))
    pygame.draw.line(surf, color, at(tail), at(head))


FLAG_W, FLAG_H, POLE_H = 8, 5, 11      # game px
# Where each building's flag pole stands: game px down from the top of its sprite (on the roof).
FLAG_ROOF = {"command": 14, "barracks": 12, "yard": 12, "bunker": 10, "tower": 5}


def draw_flag(surf, x, base, color, t, phase=0.0, k=RES):
    """A team flag on a pole standing at screen (x, base), rippling in the wind: each column of
    cloth rides a travelling wave that grows towards the free end."""
    top = base - POLE_H * k
    pygame.draw.line(surf, K, (x - 1, top), (x - 1, base))
    pygame.draw.line(surf, (190, 196, 206), (x, top), (x, base))
    surf.set_at((x, top - 1), (230, 236, 240))                        # finial
    dark = tuple(int(c * 0.7) for c in color)
    light = tuple(min(255, int(c * 1.18)) for c in color)
    cols, fh = FLAG_W * k, FLAG_H * k
    for i in range(cols):
        wave = t * 6.0 + phase - i / k * 0.8
        y0 = top + round(math.sin(wave) * (i / cols) * 1.6 * k)
        c = math.cos(wave)
        shade = dark if c > 0.55 else light if c < -0.75 else color   # folds catch shadow and light
        pygame.draw.line(surf, shade, (x + 1 + i, y0 + 1), (x + 1 + i, y0 + fh - 1))
        surf.set_at((x + 1 + i, y0), K)
        surf.set_at((x + 1 + i, y0 + fh), K)
    end = top + round(math.sin(t * 6.0 + phase - FLAG_W * 0.8) * 1.6 * k)
    pygame.draw.line(surf, K, (x + 1 + cols, end), (x + 1 + cols, end + fh))


def draw_garrison(surf, kind, occupants, gx, gy, t, color, k=RES):
    """One head per garrisoned soldier in the structure's front window, each scanning the
    surroundings: turning slowly from side to side, pausing, with the rifle muzzle following."""
    seats = m3.GARRISON_SEATS.get(kind, [])
    n = len(occupants)
    # Spread whoever is inside across the seats (2 in a 4-seat bunker sit in the middle two).
    first = (len(seats) - n) // 2
    dark = tuple(int(c * 0.7) for c in color)
    for i, u in enumerate(occupants[:len(seats)]):
        dx, dy = m3.footprint_to_screen(*seats[first + i])
        x, y = round(gx + dx * k), round(gy + dy * k)
        # Slow sweep with a hold at each end (clamped sine), each soldier on their own rhythm.
        look = max(-1.0, min(1.0, 1.6 * math.sin(t * (0.7 + 0.13 * (u.id % 5)) + u.id * 1.9)))
        off = round(look * k)
        pygame.draw.rect(surf, K, (x - 2 * k + off, y - 2 * k, 4 * k, 3 * k))      # helmet outline
        pygame.draw.rect(surf, color, (x - k + off, y - 2 * k + 1, 2 * k, 2 * k - 1))   # helmet
        pygame.draw.rect(surf, dark, (x - k + off, y - 1, 2 * k, 1))                # its rim
        face = x + off + (k if look > 0.3 else -2 * k if look < -0.3 else -k // 2)
        pygame.draw.rect(surf, (222, 172, 132), (face, y, k, k))                    # face turned to look
        tip = x + off + round(look * 3 * k)
        pygame.draw.line(surf, (46, 48, 54), (x + off, y + k), (tip, y + k))        # muzzle following


def draw_projectile(surf, p, to_screen, k=RES):
    """Draw one projectile; lobbed rounds get a ground shadow, wire-guided missiles their wire.
    to_screen maps game pixels to screen pixels."""
    x, y = to_screen(p.x, p.y)
    if p.arc:   # ground shadow under a lobbed round
        gx, gy = to_screen(p.gx, p.gy)
        pygame.draw.rect(surf, (110, 86, 60), (gx, gy, 2 * k, k))
    if p.trail == "wire" and p.source.alive:
        pygame.draw.line(surf, (200, 200, 190), to_screen(*p.source.muzzle_pos()), (x, y))
    tail = (int(x - p.dx * 3 * k), int(y - p.dy * 3 * k))
    if p.style in ("rocket", "atgm"):
        pygame.draw.line(surf, (220, 220, 220), (x, y), tail, max(1, k // 2))
        pygame.draw.rect(surf, (255, 160, 60), (x - k // 2, y - k // 2, k, k))
    elif p.style == "autocannon":
        pygame.draw.line(surf, (255, 230, 140), (x, y), tail)
    elif p.style == "grenade":
        pygame.draw.circle(surf, (60, 66, 50), (x, y), k)
    elif p.style == "artillery":
        pygame.draw.circle(surf, (255, 230, 160), (x, y), int(1.5 * k))
        pygame.draw.rect(surf, (255, 255, 230), (x - k // 2, y - k // 2, k, k))
    else:
        pygame.draw.rect(surf, (255, 230, 140), (x - k, y - k, 2 * k, 2 * k))


def draw_explosion(surf, x, y, frac, r, k=RES):
    """Expanding fireball at screen (x, y); frac runs 0..1 over BOOM_TIME, r in game pixels."""
    rad = int((4 + r * 2 * frac) * k)
    pygame.draw.circle(surf, (250, 140, 40), (x, y), rad)
    pygame.draw.circle(surf, (255, 220, 120), (x, y), max(1, int(rad * (1 - frac))))
    if frac < 0.3:
        pygame.draw.circle(surf, (255, 255, 240), (x, y), max(1, int(rad * 0.4)))


def draw_marker(surf, x, y, frac, color, k=RES):
    """A click on the ground: a ring that snaps in onto the spot while a fainter ripple spreads
    out and fades. `frac` runs 0..1 over the marker's life. Rings are flattened to lie on the ground."""
    ease = 1 - (1 - frac) ** 2
    size = 20 * k
    ring = pygame.Surface((size * 2, size), pygame.SRCALPHA)
    cx, cy = size, size // 2

    def oval(r, alpha, width):
        if r >= 1:
            rect = pygame.Rect(0, 0, int(r * 2), max(2, int(r * 1.2)))
            rect.center = (cx, cy)
            pygame.draw.ellipse(ring, color + (alpha,), rect, width)

    oval((12 - 9 * ease) * k, 255, k)                    # snaps in
    oval((5 + 13 * ease) * k, int(200 * (1 - frac)), k)   # ripples out
    if frac < 0.6:
        pygame.draw.circle(ring, color + (255,), (cx, cy), k)   # the spot itself
    surf.blit(ring, (x - cx, y - cy))


def draw_ping(surf, sil, pos, left):
    """A structure's soft acknowledgement flash: its silhouette fades in and out once, at low
    opacity so it reads as a glint rather than the white of a hit."""
    f = 1 - left / PING_TIME
    img = sil.copy()
    img.set_alpha(int(PING_ALPHA * math.sin(math.pi * f)))
    surf.blit(img, pos)


def draw_death(surf, sprites, d, age, x, y, k=RES):
    """Draw a death decal (infantry topple / vehicle wreck) at screen (x, y) `age` seconds
    after the kill."""
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
        draw_explosion(surf, x, y - 6 * k, age / BOOM_TIME, d["r"], k)


def hp_bar(surf, x, y, w, frac, color=None, k=1, thick=None):
    """A health/progress bar w (UI or game) pixels long at surface position (x, y), k times finer;
    `thick` = height of the coloured bar in surface pixels (default 2k)."""
    thick = thick or 2 * k
    edge = max(1, k // 2) if thick < 2 * k else k
    pygame.draw.rect(surf, K, (x - edge, y - edge, w * k + 2 * edge, thick + 2 * edge))
    if color is None:
        color = (80, 220, 80) if frac > 0.5 else (230, 200, 60) if frac > 0.25 else (220, 60, 50)
    pygame.draw.rect(surf, color, (x, y, max(1, int(w * k * frac)), thick))


def team_color(team):
    return TEAM_COLORS[team][0] if team in TEAM_COLORS else NEUTRAL_FLAG


class Renderer:
    def __init__(self, game, sprites):
        self.game = game
        self.sp = sprites
        self.terrain = render_terrain(game.world, game.seed)
        self._fog_key = None
        self._fog_img = None
        self._fog_cell = (0, 0)

    def draw(self, screen, ctrl):
        g = self.game
        k = RES
        cx, cy = int(ctrl.cam_x * k), int(ctrl.cam_y * k)    # camera, in screen pixels
        view = screen.subsurface((0, 0, VIEW_W * k, VIEW_H * k))
        view.blit(self.terrain, (0, 0), (cx, cy, VIEW_W * k, VIEW_H * k))

        def at(x, y):
            return int(x * k) - cx, int(y * k) - cy

        for d in g.decals:
            self.draw_decal(view, d, at)

        wx, wy = ctrl.cam_x, ctrl.cam_y
        selected = set(ctrl.selection)
        vis = []
        for e in g.entities:
            if e.is_unit:
                if not (-24 < e.x - wx < VIEW_W + 24 and -24 < e.y - wy < VIEW_H + 24):
                    continue
            else:
                l, t, r, b = e.rect()
                if r + 16 < wx or l - 16 > wx + VIEW_W or b + 16 < wy or t - 16 > wy + VIEW_H:
                    continue
            if g.seen(e):
                vis.append(e)
        vis.sort(key=lambda e: e.y if e.is_unit else e.rect()[3] - 8)

        for e in vis:   # building shadows go down first, on the ground under everything
            if e.is_building and e.complete:
                view.blit(self.sp.building_shadow(e.kind, e.size), at(e.tx * TILE, e.ty * TILE))

        for e in vis:
            if e in selected:
                col = SEL_COLORS.get(e.team, ENEMY_SEL)
                if e.is_unit:
                    r = e.radius
                    x, y = at(e.x, e.y)
                    pygame.draw.ellipse(view, col, (x - (r + 2) * k, y - k, (r * 2 + 4) * k, 7 * k), 1)
                else:
                    l, t, r, b = e.rect()
                    x, y = at(l, t)
                    pygame.draw.rect(view, col, (x - k, y - k, (r - l + 2) * k, (b - t + 2) * k), 1)
            if e.is_unit:
                self.draw_unit(view, e, at)
            elif e.is_point:
                self.draw_point(view, e, at)
            else:
                self.draw_building(view, e, at)

        for tr in g.tracers:
            draw_tracer(view, *at(tr[0], tr[1]), *at(tr[2], tr[3]), tr[4], tr[5], k=k)
        for p in g.projectiles:
            draw_projectile(view, p, at, k)
        for b in g.booms:
            draw_explosion(view, *at(b[0], b[1]), (g.time - b[2]) / SHOT_BOOM_TIME, b[3], k)
        for p in g.particles:
            pygame.draw.rect(view, p[5], (*at(p[0], p[1]), k, k))

        for e in vis:
            if e.is_point or not (e in selected or e.hp < e.max_hp):
                continue
            if e.is_unit:
                w = max(12, e.radius * 2)
                x, y = at(e.x, e.y)
                top = y - (UNITS[e.kind]["height"] + (-6 if e.suppressed else 3)) * k
                hp_bar(view, x - w * k // 2, top, w, e.hp / e.max_hp, k=k, thick=3)
            else:
                l, t, r, b = e.rect()
                x, y = at(l, t)
                hp_bar(view, x + 4 * k, y - 4 * k, r - l - 8, e.hp / e.max_hp, k=k, thick=3)

        self.draw_fog(view, ctrl, cx, cy)

        for e in ctrl.selection:
            if e.is_building and e.team == PLAYER and e.rally is not None:
                r = e.rally
                if hasattr(r, "is_point"):
                    rx, ry = at(r.x, r.y)
                else:
                    rx, ry = at(r[0] * TILE + TILE // 2, r[1] * TILE + TILE // 2)
                pygame.draw.line(view, K, (rx, ry), (rx, ry - 10 * k))
                pygame.draw.rect(view, (90, 230, 90), (rx + 1, ry - 10 * k, 5 * k, 4 * k))

        for m in ctrl.markers:
            draw_marker(view, *at(m[0], m[1]), m[2] / MARKER_TIME, m[3], k)

        if ctrl.mode == "place":
            self.draw_ghost(view, ctrl, at)
        if ctrl.dragging and ctrl.drag_start:
            mx, my = ctrl.mouse[0] * k, ctrl.mouse[1] * k
            sx, sy = at(*ctrl.drag_start)
            rect = pygame.Rect(min(sx, mx), min(sy, my), abs(mx - sx), abs(my - sy))
            pygame.draw.rect(view, (90, 230, 90), rect, 1)

    def draw_fog(self, view, ctrl, cx, cy):
        """The fog over the view: the quarter-tile fog map, the part on screen blown up with hard
        pixels (re-done only when the fog changes or the view crosses into new cells)."""
        fog = self.game.fog
        if fog.reveal_all:
            return
        q = TILE // 4                      # game pixels per fog cell
        x0, y0 = int(ctrl.cam_x // q), int(ctrl.cam_y // q)
        key = (fog.version, x0, y0)
        if key != self._fog_key:
            area = pygame.Rect(x0, y0, VIEW_W // q + 2, VIEW_H // q + 2).clip(fog.mid.get_rect())
            self._fog_img = pygame.transform.scale(fog.mid.subsurface(area),
                                                   (area.w * q * RES, area.h * q * RES))
            self._fog_cell = area.topleft
            self._fog_key = key
        view.blit(self._fog_img, (self._fog_cell[0] * q * RES - cx, self._fog_cell[1] * q * RES - cy))

    def draw_unit(self, view, u, at):
        spr = self.sp.unit(u.kind, u.team, u.loadout)
        anim, i = unit_anim(u)
        turret = u.turret - u.facing if u.has_turret else 0.0
        x, y = at(u.x, u.y)
        draw_shadow(view, x, y, u.radius, u.is_infantry and u.suppressed)
        img, (ox, oy) = spr.frame(anim, i, u.facing, turret, u.steer)
        view.blit(img, (x - ox, y - oy))
        if u.flash > 0:
            fl, _ = spr.flash(anim, i, u.facing, turret, u.steer)
            view.blit(fl, (x - ox, y - oy))

    def draw_decal(self, view, d, at):
        k = RES
        age = self.game.time - d["t"]
        if d["kind"] == "rubble":
            x, y = at(d["x"], d["y"])
            size = d["size"] * TILE
            pygame.draw.rect(view, (96, 84, 72), (x + 2 * k, y + 4 * k, (size - 4) * k, (size - 6) * k))
            for sx, sy, col in d["stones"]:
                pygame.draw.rect(view, col, (x + sx * k, y + sy * k, 4 * k, 3 * k))
                pygame.draw.rect(view, tuple(min(255, c + 24) for c in col), (x + sx * k, y + sy * k, 3 * k, k))
            return
        x, y = at(d["x"], d["y"])
        if -40 * k < x < (VIEW_W + 40) * k and -40 * k < y < (VIEW_H + 40) * k:
            draw_death(view, self.sp, d, age, x, y)

    def draw_point(self, view, p, at):
        k = RES
        x, y = at(p.x, p.y)
        img, (ox, oy) = self.sp.derrick(self.game.time)
        view.blit(img, (x - ox, y - oy))
        if p.ping > 0:
            draw_ping(view, silhouette(img), (x - ox, y - oy), p.ping)
        # Owner's flag on a pole in the middle of the pad, flying clear above the pump.
        draw_flag(view, x, y - 2 * k, team_color(p.team), self.game.time, p.id)
        capturing = p.progress < 1 and p.progress > 0
        if capturing or p.contested:
            team = p.capturer if p.team == NEUTRAL else p.team
            bar = (240, 220, 90) if p.contested else team_color(team)
            hp_bar(view, x - 12 * k, y - oy - 11 * k, 24, p.progress, bar, k=k, thick=3)

    def draw_building(self, view, e, at):
        k = RES
        l, t = at(e.tx * TILE, e.ty * TILE)
        img, (ox, oy) = self.sp.building(e.kind, e.team, e.progress, bool(e.occupants))
        x, y = at(e.x, e.y)
        bx, by = x - ox, y - oy
        view.blit(img, (bx, by))
        if not e.complete:
            if e.ping > 0:
                draw_ping(view, silhouette(img), (bx, by), e.ping)
            return
        # Team flag on the roof at the back-right corner, waving.
        draw_flag(view, bx + img.get_width() - 12 * k, by + FLAG_ROOF.get(e.kind, 10) * k, team_color(e.team),
                  self.game.time, e.id * 1.7)
        if e.occupants:
            draw_garrison(view, e.kind, e.occupants, x, y, self.game.time, team_color(e.team))
        if e.flash > 0:
            view.blit(self.sp.building_flash(e.kind, e.team), (bx, by))
        elif e.ping > 0:
            draw_ping(view, self.sp.building_flash(e.kind, e.team), (bx, by), e.ping)
        frac = e.hp / e.max_hp
        if frac < 0.5:
            tm = self.game.time
            w = e.size * TILE
            for i in range(1 if frac > 0.25 else 3):
                fx = l + (4 + (e.id * 7 + i * 17) % (w - 10)) * k
                fy = t + (12 + (e.id * 3 + i * 11) % 12) * k
                flick = int(tm * 10 + i * 3) % 3 * k
                pygame.draw.rect(view, (236, 110, 40), (fx, fy - flick, 4 * k, 4 * k + flick))
                pygame.draw.rect(view, (255, 220, 90), (fx + k, fy + k, 2 * k, 2 * k))
                pygame.draw.rect(view, (255, 250, 200), (fx + k, fy + k + k // 2, k, k))

    def draw_ghost(self, view, ctrl, at):
        g = self.game
        k = RES
        kind = ctrl.place_kind
        s = BUILDINGS[kind]["size"]
        tx, ty = ctrl.place_origin(*ctrl.to_world(ctrl.mouse))
        img, (ox, oy) = self.sp.building(kind, PLAYER)
        img = img.copy()
        img.set_alpha(150)
        x, y = at((tx + s / 2) * TILE, (ty + s / 2) * TILE)
        view.blit(img, (x - ox, y - oy))
        # Green only if the whole site is legal: clear ground AND a tile's clearance from every
        # other building. Too close (or any bad tile) and the whole footprint shows red.
        ok = g.can_place(kind, tx, ty, PLAYER)
        tint = pygame.Surface((TILE * k, TILE * k), pygame.SRCALPHA)
        tint.fill((60, 220, 60, 70) if ok else (230, 40, 40, 110))
        for yy in range(ty, ty + s):
            for xx in range(tx, tx + s):
                view.blit(tint, at(xx * TILE, yy * TILE))
