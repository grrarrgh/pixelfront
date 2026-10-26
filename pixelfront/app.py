"""Window, main loop and screen states (title, playing, paused, game over)."""
import logging
import random
import time

import pygame

from .config import SCREEN_W, SCREEN_H, VIEW_H, FPS, PLAYER, TILE, MAP_W, MAP_H
from .controller import Controller, TARGET_MODES
from .design import DesignScreen
from .font import draw_text
from .game import Game
from .hud import HUD
from .motiontest import MotionTest
from .render import Renderer
from .sprites import Sprites, render_terrain, fit
from .world import generate

CONTROLS = [
    ("Left click / drag", "Select units"),
    ("Shift + click", "Add to selection"),
    ("Double click", "Select all of a type"),
    ("Right click", "Move / attack / capture / rally"),
    ("A then click", "Attack-move"),
    ("S", "Stop"),
    ("D (on a factory)", "Design unit loadouts"),
    ("Ctrl + 1-9", "Assign control group"),
    ("1-9", "Recall group (twice: jump)"),
    ("Arrows / screen edge", "Scroll"),
    ("Middle drag / minimap", "Move camera"),
    ("Space", "Jump to base"),
    ("F1 / F11", "Help / fullscreen"),
    ("Esc", "Cancel / menu"),
]

log = logging.getLogger(__name__)
SLOW_FRAME = 0.1   # seconds; frames slower than this are logged (at most every few seconds)


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pixelfront")
        try:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED, vsync=1)
        except pygame.error:
            log.warning("vsync unavailable, running without it")
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED)
        log.info("Display: logical %dx%d, window %s, driver %s", SCREEN_W, SCREEN_H,
                 pygame.display.get_window_size(), pygame.display.get_driver())
        t0 = time.perf_counter()
        self.sprites = Sprites()
        log.info("Sprites ready in %.0f ms", (time.perf_counter() - t0) * 1000)
        pygame.display.set_icon(self.sprites.window_icon())
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = "title"
        self.title_time = 0.0
        world, _, _ = generate(random.Random())
        self.title_bg = render_terrain(world, 3)
        self.game = None
        self.design = None
        self._last_slow_log = -99.0

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value != getattr(self, "_state", None):
            log.info("Screen: %s -> %s", getattr(self, "_state", None), value)
        self._state = value

    def start_game(self, sandbox=False):
        t0 = time.perf_counter()
        self.game = Game(sandbox=sandbox)
        self.renderer = Renderer(self.game, self.sprites)
        self.hud = HUD(self.game, self.sprites)
        self.ctrl = Controller(self.game, self.hud)
        log.info("%s started (seed %d) in %.0f ms", "Test range" if sandbox else "Match",
                 self.game.seed, (time.perf_counter() - t0) * 1000)
        self.state = "play"

    def open_design(self):
        b = next((e for e in self.ctrl.own() if e.is_building and e.complete), None)
        if b is not None:
            self.design = DesignScreen(self.game, self.sprites, b, self.renderer.terrain)
            self.state = "design"

    def run(self):
        while self.running:
            raw = self.clock.tick(FPS) / 1000.0
            if raw > SLOW_FRAME and time.monotonic() - self._last_slow_log > 5:
                self._last_slow_log = time.monotonic()
                log.warning("Slow frame: %.0f ms on the %s screen", raw * 1000, self.state)
            dt = min(raw, 0.05)
            for ev in pygame.event.get():
                self.handle(ev)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        log.info("Window closed")
        pygame.quit()

    # ---- input ------------------------------------------------------------

    def handle(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
            log.info("Fullscreen toggled (window now %s)", pygame.display.get_window_size())
            return
        key = ev.key if ev.type == pygame.KEYDOWN else None
        if self.state == "title":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) or (
                    ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1):
                self.start_game()
            elif key == pygame.K_t:
                self.start_game(sandbox=True)
            elif key == pygame.K_m:
                self.motion = MotionTest(self.sprites)
                self.state = "motion"
            elif key == pygame.K_ESCAPE:
                self.running = False
        elif self.state == "motion":
            if self.motion.handle(ev) == "close":
                self.state = "title"
        elif self.state == "play":
            action = self.ctrl.handle(ev)
            if action == "pause":
                self.state = "paused"
            elif action == "design":
                self.open_design()
        elif self.state == "design":
            if ev.type == pygame.MOUSEMOTION:
                self.ctrl.mouse = ev.pos
            if self.design.handle(ev) == "close":
                self.design = None
                self.state = "play"
        elif self.state == "paused":
            if key in (pygame.K_ESCAPE, pygame.K_F10, pygame.K_RETURN):
                self.state = "play"
            elif key == pygame.K_r:
                self.start_game(self.game.sandbox)
            elif key == pygame.K_q:
                self.state = "title"
        elif self.state == "over":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start_game(self.game.sandbox)
            elif key == pygame.K_ESCAPE:
                self.state = "title"

    def update(self, dt):
        if self.state == "title":
            self.title_time += dt
        elif self.state == "motion":
            self.motion.update(dt)
        elif self.state == "play":
            self.ctrl.update(dt)
            self.game.update(dt)
            if self.game.winner is not None:
                g = self.game
                log.info("Match over after %d:%02d: %s. Player has %d units, %d buildings, %d credits",
                         int(g.time) // 60, int(g.time) % 60,
                         "VICTORY" if g.winner == PLAYER else "DEFEAT",
                         sum(1 for u in g.units if u.team == PLAYER),
                         sum(1 for b in g.buildings if b.team == PLAYER), int(g.teams[PLAYER].credits))
                self.state = "over"

    # ---- drawing ----------------------------------------------------------

    def draw(self):
        s = self.screen
        if self.state == "title":
            self.draw_title(s)
        elif self.state == "motion":
            self.motion.draw(s)
        else:
            self.renderer.draw(s, self.ctrl)
            self.hud.draw(s, self.ctrl)
            if self.ctrl.show_help:
                self.draw_help(s)
            if self.state == "design":
                self.design.draw(s)
            elif self.state == "paused":
                self.overlay(s, "Paused", ["Esc - Resume", "R - Restart", "Q - Quit to title"])
            elif self.state == "over":
                won = self.game.winner == PLAYER
                self.overlay(s, "Victory!" if won else "Defeat",
                             ["All enemy buildings destroyed." if won else "Your base has fallen.",
                              "Enter - Play again", "Esc - Title screen"],
                             (250, 220, 110) if won else (240, 90, 80))
        self.draw_cursor(s)

    def shade(self, s, alpha=150):
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, alpha))
        s.blit(dim, (0, 0))

    def overlay(self, s, title, lines, color=(250, 220, 110)):
        self.shade(s)
        draw_text(s, title, SCREEN_W // 2, 110, color, scale=5, align="center")
        for i, line in enumerate(lines):
            draw_text(s, line, SCREEN_W // 2, 160 + i * 14, (230, 230, 230), scale=2, align="center")

    def draw_title(self, s):
        span_x = MAP_W * TILE - SCREEN_W
        span_y = MAP_H * TILE - SCREEN_H
        t = self.title_time * 12
        x = int(t) % (2 * span_x)
        x = x if x < span_x else 2 * span_x - x
        s.blit(self.title_bg, (0, 0), (x, span_y // 2, SCREEN_W, SCREEN_H))
        self.shade(s, 120)
        draw_text(s, "Pixelfront", SCREEN_W // 2 + 2, 52, (40, 30, 20), shadow=None, scale=8, align="center")
        draw_text(s, "Pixelfront", SCREEN_W // 2, 50, (250, 220, 110), shadow=(120, 70, 30), scale=8, align="center")
        draw_text(s, "Desert warfare. Design your units. Hold the derricks.", SCREEN_W // 2, 100,
                  (230, 230, 230), align="center")

        lineup = (("engineer", -170), ("rifleman", -125), ("medic", -80), ("heavy", -35),
                  ("jeep", 35), ("tank", 125))
        for kind, dx in lineup:
            spr = self.sprites.unit(kind, PLAYER)
            img, (ox, oy) = spr.frame("walk", int(self.title_time * 8), 20)
            img = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
            s.blit(img, (SCREEN_W // 2 + dx - ox * 2, 150 - oy * 2))

        if int(self.title_time * 2) % 2 == 0:
            draw_text(s, "Enter - Start game", SCREEN_W // 2, 162, (255, 255, 255), scale=2, align="center")
        draw_text(s, "T - Test range (practice targets, no AI)     M - Sprite motion test", SCREEN_W // 2, 180,
                  (220, 220, 230), align="center")
        self.draw_controls(s, 90, 196)
        draw_text(s, "Capture derricks for income. Destroy every enemy building to win.", SCREEN_W // 2,
                  SCREEN_H - 14, (200, 200, 210), align="center")

    def draw_controls(self, s, x, y):
        for i, (key, what) in enumerate(CONTROLS):
            col = i // 7
            row = i % 7
            cx = x + col * 240
            draw_text(s, key, cx, y + row * 11, (250, 220, 110))
            draw_text(s, what, cx + 92, y + row * 11, (220, 220, 230))

    def draw_help(self, s):
        box = pygame.Rect(76, 70, 488, 100)
        pygame.draw.rect(s, (20, 16, 24), box)
        pygame.draw.rect(s, (110, 100, 122), box, 1)
        draw_text(s, "Controls", box.centerx, box.y + 6, (250, 220, 110), align="center")
        self.draw_controls(s, box.x + 14, box.y + 20)

    def draw_cursor(self, s):
        mx, my = pygame.mouse.get_pos()
        mode = self.ctrl.mode if self.state == "play" else None
        if mode in TARGET_MODES:
            col = {"move": (90, 230, 90), "attack": (235, 70, 60), "repair": (250, 220, 90)}[mode]
            for dx, dy, w, h in ((-6, 0, 4, 1), (3, 0, 4, 1), (0, -6, 1, 4), (0, 3, 1, 4)):
                pygame.draw.rect(s, (20, 20, 26), (mx + dx - 1, my + dy - 1, w + 2, h + 2))
                pygame.draw.rect(s, col, (mx + dx, my + dy, w, h))
        else:
            s.blit(self.sprites.cursor, (mx, my))
