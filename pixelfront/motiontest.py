"""Sprite motion test: every unit type running every animation on a loop, for reviewing art.

Each cell is staged at game resolution (RES screen pixels per game pixel, like the map view)
and blown up (infantry 4x, vehicles 2x) so it looks exactly like the game, only bigger.
"""
import math
import random

import pygame

from .config import SCREEN_W, PLAYER, ENEMY, KNEEL_TIME, STEER_MAX, RES
from .units import UNITS
from .font import draw_text
from .modules import SLOTS, TIER_NAMES, weapon_of, slots_for, tiers, tier, slot_label, default_loadout, compute_stats
from .render import draw_shadow, draw_death, draw_explosion, draw_tracer, TRACER_LIFE
from .sprites import muzzle_offset, WALK_RATE, K
from .weapons import weapon as weapon_def, PROJECTILE_STYLES

KINDS = list(UNITS)
COLUMNS = ("Turning", "Moving", "Attacking", "Pinned / Turret", "Dying")
KNEEL_CYCLE = 4.0            # heavy infantry: kneel, fire for a while, stand up, repeat
LABEL_W = 80
CELL_W, CELL_H = 112, 56     # on-screen cell size
TOP = 24
DIE_CYCLE = 3.2              # seconds: stand, die, lie there, repeat
SLOT_KEYS = {pygame.K_1: "armor", pygame.K_2: "weapon", pygame.K_3: "engine"}
SAND, SAND_D = (220, 186, 124), (204, 168, 108)


class Stage:
    """Staging area for one row, in game pixels: infantry get a smaller stage shown at 4x."""

    def __init__(self, kind):
        self.zoom = 4 if UNITS[kind]["cls"] == "infantry" else 2
        self.w, self.h = CELL_W // self.zoom, CELL_H // self.zoom
        self.ground = self.h - 3
        self.speed = 1.0 / self.zoom * 2   # world px per stage px, so units cross cells at a similar pace


class MotionTest:
    def __init__(self, sprites):
        self.sp = sprites
        self.t = 0.0
        self.team = PLAYER
        self.paused = False
        self.levels = {slot: SLOTS[slot]["default"] for slot in SLOTS}
        self.rng = random.Random(7)
        self.stages = {kind: Stage(kind) for kind in KINDS}
        self.cells = {}
        self.reset()

    def reset(self):
        # Per-unit loop state for the walking, attacking and pinned columns.
        for kind in KINDS:
            st = self.stages[kind]
            self.cells[kind] = dict(walk_x=st.w * 0.3, walk_dir=1, walk_anim=0.0,
                                    crawl_x=st.w * 0.3, crawl_dir=1, crawl_anim=0.0,
                                    cooldown=0.4, lunge=0.0, pcool=0.8, plunge=0.0,
                                    shots=[], projectiles=[], particles=[], booms=[])

    def loadout(self, kind):
        lo = default_loadout(kind)
        for slot in slots_for(kind):
            lo[slot] = min(self.levels[slot], len(tiers(kind, slot)) - 1)
        return lo

    def handle(self, ev):
        """Returns "close" to leave the scene."""
        if ev.type != pygame.KEYDOWN:
            return None
        if ev.key in (pygame.K_ESCAPE, pygame.K_m):
            return "close"
        if ev.key in SLOT_KEYS:
            slot = SLOT_KEYS[ev.key]
            self.levels[slot] = (self.levels[slot] + 1) % len(TIER_NAMES)
        elif ev.key == pygame.K_TAB:
            self.team = ENEMY if self.team == PLAYER else PLAYER
        elif ev.key == pygame.K_SPACE:
            self.paused = not self.paused
        elif ev.key == pygame.K_r:
            self.levels = {slot: SLOTS[slot]["default"] for slot in SLOTS}
        return None

    # ---- simulation -------------------------------------------------------------

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        for kind in KINDS:
            c = self.cells[kind]
            S = self.stages[kind]
            st = compute_stats(kind, self.loadout(kind))
            infantry = UNITS[kind]["cls"] == "infantry"
            margin = 4 if infantry else UNITS[kind]["radius"] + 8

            # Moving: pace back and forth across the cell at the unit's real speed (scaled to fit).
            c["walk_x"] += c["walk_dir"] * st["speed"] * 0.5 * S.speed * dt
            if not margin <= c["walk_x"] <= S.w - margin:
                c["walk_dir"] *= -1
                c["walk_x"] = min(max(c["walk_x"], margin), S.w - margin)
            c["walk_anim"] += dt

            # Attacking: fire on the unit's real reload time at the dummy on the right
            # (heavy infantry only once they've knelt).
            c["lunge"] = max(0.0, c["lunge"] - dt)
            c["cooldown"] -= dt
            if c["cooldown"] <= 0 and self.ready_to_fire(kind):
                c["cooldown"] = max(0.15, st["cooldown"])
                c["lunge"] = 0.12
                self.fire(kind, c, st, self.shooter_x(kind), 0.0, prone=False)

            # Pinned down: crawl a little, then fire from the ground.
            if infantry:
                phase = self.t % 4.0
                c["plunge"] = max(0.0, c["plunge"] - dt)
                if phase < 2.5:
                    c["crawl_x"] += c["crawl_dir"] * st["speed"] * 0.35 * 0.5 * S.speed * dt
                    c["crawl_anim"] += dt
                    if not 5 <= c["crawl_x"] <= S.w - 9:
                        c["crawl_dir"] *= -1
                        c["crawl_x"] = min(max(c["crawl_x"], 5), S.w - 9)
                else:
                    c["pcool"] -= dt
                    if c["pcool"] <= 0 and UNITS[kind]["weapon"]:
                        c["pcool"] = max(0.15, st["cooldown"])
                        c["plunge"] = 0.12

            for tr in c["shots"]:
                tr[4] += dt
            c["shots"] = [tr for tr in c["shots"] if tr[4] < TRACER_LIFE]
            for p in c["projectiles"]:
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                prog = min(1.0, max(0.0, (p["x"] - p["sx"]) / max(1.0, p["tx"] - p["sx"])))
                p["h"] = p["arc"] * 4 * prog * (1 - prog)
                if p["x"] >= p["tx"]:
                    p["done"] = True
                    c["booms"].append([p["tx"], p["ty"], 0.0])
                    self.burst(c, p["tx"], p["ty"], (250, 170, 60), 6, 30 / S.zoom * 2)
            c["projectiles"] = [p for p in c["projectiles"] if not p.get("done")]
            for b in c["booms"]:
                b[2] += dt
            c["booms"] = [b for b in c["booms"] if b[2] < 0.25]
            for p in c["particles"]:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[3] += 60 * p[6] * dt
                p[4] -= dt
            c["particles"] = [p for p in c["particles"] if p[4] > 0]

            # Smoke from a burning wreck in the dying column.
            age = (self.t % DIE_CYCLE) - 0.7
            if not infantry and 0 < age < DIE_CYCLE - 1.2 and self.rng.random() < dt * 8:
                c["particles"].append([S.w / 2 + self.rng.uniform(-3, 3), S.ground - 8, self.rng.uniform(-2, 2),
                                       -10, 0.9, (70, 66, 64), 0.0, "die"])

    def shooter_x(self, kind):
        return 5 if UNITS[kind]["cls"] == "infantry" else 12

    def kneel_state(self):
        """(anim, frame) for heavy infantry in the attack column: kneel, fire, stand, repeat."""
        p = self.t % KNEEL_CYCLE
        if p < KNEEL_TIME / 2:
            return "kneel", 0
        if p < KNEEL_TIME:
            return "kneel", 1
        if p > KNEEL_CYCLE - 0.4:
            return "idle", 0
        return "kfire", None

    def ready_to_fire(self, kind):
        return not UNITS[kind].get("kneels") or self.kneel_state()[0] == "kfire"

    def target_pos(self, kind):
        S = self.stages[kind]
        return S.w - 4, S.ground - (3 if UNITS[kind]["cls"] == "infantry" else 6)

    def fire(self, kind, c, st, x, facing, prone):
        S = self.stages[kind]
        if UNITS[kind]["weapon"] is None:          # medic: heal pulse on the patient instead
            self.burst(c, x + 6, S.ground - 3, (130, 240, 130), 3, 6)
            return
        kneel = UNITS[kind].get("kneels") and not prone
        dx, dy = muzzle_offset(kind, self.loadout(kind), facing, prone, 0.0, kneel)
        sx, sy = x + dx, S.ground + dy
        hit = self.rng.random() < st["accuracy"]
        tx, ty = self.target_pos(kind)
        if not hit:
            tx += self.rng.uniform(-2, 3)
            ty += self.rng.uniform(-4, 3)
        style = weapon_def(st["weapon"])["projectile"]
        if style is None:   # bullets: instant tracer
            c["shots"].append([sx, sy, tx, ty, 0.0, self.rng.random()])
            self.burst(c, tx, ty, (255, 230, 160) if hit else (200, 176, 130), 2, 12)
        else:
            spec = PROJECTILE_STYLES[style]
            speed = spec["speed"] * 0.5 * S.speed
            d = max(1.0, math.hypot(tx - sx, ty - sy))
            c["projectiles"].append(dict(x=sx, y=sy, sx=sx, tx=tx, ty=ty, vx=(tx - sx) / d * speed,
                                         vy=(ty - sy) / d * speed, style=style, h=0.0,
                                         arc=spec["arc"] * 0.25 / S.zoom * 2))

    def burst(self, c, x, y, color, n, speed):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(0.3, 1.0) * speed
            c["particles"].append([x, y, math.cos(a) * s, math.sin(a) * s - speed * 0.4,
                                   self.rng.uniform(0.2, 0.4), color, 1.0, "fire"])

    # ---- drawing ----------------------------------------------------------------

    def draw(self, screen, layer):
        k = RES
        screen.fill((34, 30, 38))
        surf = layer.touch()
        draw_text(surf, "Sprite motion test", 6, 4, (250, 220, 110))
        tiers_txt = "   ".join(f"[{i}] {SLOTS[s]['label']}: {TIER_NAMES[self.levels[s]]}"
                               for i, s in enumerate(SLOTS, 1))
        draw_text(surf, tiers_txt, 120, 4, (230, 230, 230))
        draw_text(surf, "[Tab] team  [Space] pause  [R] reset  [Esc] back", SCREEN_W - 6, 4,
                  (170, 166, 180), align="right")
        for i, name in enumerate(COLUMNS):
            draw_text(surf, name, LABEL_W + i * CELL_W + CELL_W // 2, 15, (250, 220, 110), align="center")
        for r, kind in enumerate(KINDS):
            S = self.stages[kind]
            y = TOP + r * CELL_H
            lo = self.loadout(kind)
            draw_text(surf, UNITS[kind]["name"], 4, y + 14, (240, 240, 240))
            for j, slot in enumerate(slots_for(kind)):
                draw_text(surf, f"{slot_label(kind, slot)[:6]} {tier(kind, slot, lo[slot])['name']}",
                          4, y + 24 + j * 8, (160, 156, 170))
            for col in range(len(COLUMNS)):
                cell = pygame.Surface((S.w * k, S.h * k))
                cell.fill(SAND)
                pygame.draw.line(cell, SAND_D, (0, (S.ground + 2) * k), (S.w * k, (S.ground + 2) * k), k)
                self.draw_cell(cell, kind, lo, col)
                screen.blit(pygame.transform.scale(cell, (CELL_W * k, CELL_H * k)),
                            ((LABEL_W + col * CELL_W) * k, y * k))
                pygame.draw.rect(screen, (34, 30, 38), ((LABEL_W + col * CELL_W) * k, y * k, CELL_W * k, CELL_H * k), k)

    def blit_unit(self, cell, kind, lo, anim, i, facing, x, prone=False, unit_kind=None):
        S = self.stages[kind]
        k = RES
        uk = unit_kind or kind
        spr = self.sp.unit(uk, self.team, lo)
        draw_shadow(cell, int(x * k), S.ground * k, UNITS[uk]["radius"], prone)
        img, (ox, oy) = spr.frame(anim, i, facing)
        cell.blit(img, (int(x * k) - ox, S.ground * k - oy))

    def draw_cell(self, cell, kind, lo, col):
        c = self.cells[kind]
        S = self.stages[kind]
        k = RES
        infantry = UNITS[kind]["cls"] == "infantry"
        rate = WALK_RATE[UNITS[kind]["cls"]]
        mid = S.w // 2
        sx = self.shooter_x(kind)
        if col == 0:                                  # turning through every facing
            if infantry:   # idle breathing while turning
                self.blit_unit(cell, kind, lo, "idle", int(self.t * 2.5), (self.t * 45) % 360, mid)
            else:                                     # vehicles drive round with the wheels steered in
                spr = self.sp.unit(kind, self.team, lo)
                draw_shadow(cell, mid * k, S.ground * k, UNITS[kind]["radius"])
                img, (ox, oy) = spr.frame("walk", int(self.t * rate), (self.t * 45) % 360, 0, -STEER_MAX)
                cell.blit(img, (mid * k - ox, S.ground * k - oy))
        elif col == 1:                                # walking / driving
            facing = 0 if c["walk_dir"] > 0 else 180
            self.blit_unit(cell, kind, lo, "walk", int(c["walk_anim"] * rate), facing, c["walk_x"])
        elif col == 2:                                # attacking (medic: healing, engineer alternates)
            working = kind == "medic" or (kind == "engineer" and (self.t % 6) >= 3)
            if working:
                if kind == "medic":
                    self.blit_unit(cell, kind, default_loadout("rifleman"), "prone", 0, 180, sx + 9,
                                   prone=True, unit_kind="rifleman")
                else:
                    pygame.draw.rect(cell, (120, 96, 60), ((sx + 4) * k, (S.ground - 5) * k, 6 * k, 6 * k))
                    pygame.draw.rect(cell, K, ((sx + 4) * k, (S.ground - 5) * k, 6 * k, 6 * k), 1)
                self.blit_unit(cell, kind, lo, "work", int(c["lunge"] > 0.05), 0, sx)
            else:
                self.draw_dummy(cell, kind)
                anim, i = ("fire", None) if not UNITS[kind].get("kneels") else self.kneel_state()
                if i is None:
                    i = int(c["lunge"] > 0.05)
                self.blit_unit(cell, kind, lo, anim, i, 0, sx)
            self.draw_effects(cell, c, "fire")
        elif col == 3:                                # pinned: crawl, then shoot from the dirt
            if not infantry:                          # vehicles: the turret traverses instead
                if weapon_def(weapon_of(kind, lo))["fixed"]:
                    self.blit_unit(cell, kind, lo, "idlegun", int(self.t * 2.0), 0, mid)
                    draw_text(cell, "fixed gun", mid * k, 2 * k, (120, 80, 50), shadow=None, scale=k,
                              align="center")
                else:
                    spr = self.sp.unit(kind, self.team, lo)
                    draw_shadow(cell, mid * k, S.ground * k, UNITS[kind]["radius"])
                    img, (ox, oy) = spr.frame("idle", 0, 0, (self.t * 60) % 360)
                    cell.blit(img, (mid * k - ox, S.ground * k - oy))
                return
            if (self.t % 4.0) < 2.5:
                facing = 0 if c["crawl_dir"] > 0 else 180
                self.blit_unit(cell, kind, lo, "prone", int(c["crawl_anim"] * 4), facing, c["crawl_x"], True)
            else:
                self.draw_dummy(cell, kind)
                self.blit_unit(cell, kind, lo, "pfire", int(c["plunge"] > 0.05), 0, c["crawl_x"], True)
        else:                                         # dying
            age = (self.t % DIE_CYCLE) - 0.7
            if age < 0:
                self.blit_unit(cell, kind, lo, "idle", int(self.t * (2.5 if infantry else 10)), 0, mid)
            else:
                d = dict(kind="wreck" if not infantry else "fall", unit=kind, team=self.team, loadout=lo,
                         facing=0, r=UNITS[kind]["radius"], life=DIE_CYCLE + 1.5)
                if infantry:
                    draw_shadow(cell, mid * k, S.ground * k, UNITS[kind]["radius"], age > 0.3)
                draw_death(cell, self.sp, d, age, mid * k, S.ground * k)
            self.draw_effects(cell, c, "die")

    def draw_dummy(self, cell, kind):
        x, y = self.target_pos(kind)
        S = self.stages[kind]
        k = RES
        r = (2 if UNITS[kind]["cls"] == "infantry" else 4) * k
        pygame.draw.rect(cell, (110, 80, 50), (x * k, y * k, k, (S.ground - y + 2) * k))
        pygame.draw.circle(cell, K, (x * k, y * k), r)
        pygame.draw.circle(cell, (236, 236, 236), (x * k, y * k), r - 1)
        pygame.draw.circle(cell, (210, 50, 40), (x * k, y * k), max(1, r // 3))

    def draw_effects(self, cell, c, which):
        k = RES
        w, h = cell.get_size()
        if which == "fire":
            for tr in c["shots"]:
                draw_tracer(cell, tr[0] * k, tr[1] * k, tr[2] * k, tr[3] * k, tr[4], tr[5])
            for p in c["projectiles"]:
                x, y = int(p["x"] * k), int((p["y"] - p["h"]) * k)
                style = p["style"]
                if p["arc"]:
                    cell.fill((150, 120, 90), (int(p["x"] * k), int(p["y"] * k), k, k))
                if style in ("rocket", "atgm"):
                    pygame.draw.line(cell, (220, 220, 220), (x, y), (x - 2 * k, y))
                    cell.fill((255, 160, 60), (x, y, k, k))
                elif style == "grenade":
                    cell.fill((50, 56, 40), (x, y, k, k))
                elif style == "autocannon":
                    pygame.draw.line(cell, (255, 230, 140), (x, y), (x - 2 * k, y))
                else:
                    pygame.draw.rect(cell, (255, 230, 140), (x - k, y - k, 2 * k, 2 * k))
            for b in c["booms"]:
                draw_explosion(cell, int(b[0] * k), int(b[1] * k), b[2] / 0.25, 2)
        for p in c["particles"]:
            if p[7] == which and 0 <= p[0] * k < w and 0 <= p[1] * k < h:
                cell.fill(p[5], (int(p[0] * k), int(p[1] * k), k, k))
