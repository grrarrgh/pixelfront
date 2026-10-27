"""Turns mouse and keyboard input into selections, camera movement and unit orders."""
import logging

import pygame

from .config import (SCREEN_W, SCREEN_H, VIEW_W, VIEW_H, TILE, MAP_W, MAP_H, PLAYER, NEUTRAL, BUILDINGS,
                     CAMERA_SPEED, EDGE_SCROLL)
from .layer import ui_mouse
from .modules import default_loadout, loadout_cost, loadout_summary, loadout_time
from .units import UNITS

TARGET_MODES = ("move", "attack", "repair")
MARKER_TIME = 0.5   # seconds a click marker stays up (render.py animates it over this time)
BUILDABLE = ("command", "barracks", "yard", "bunker", "tower")   # what the Command Center's menu lays down

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, game, hud):
        self.game = game
        self.hud = hud
        self.selection = []
        self.mode = None          # None, "place" or one of TARGET_MODES
        self.place_kind = None
        self.drag_start = None    # world coords
        self.dragging = False
        self.minimap_drag = None   # True while dragging across the minimap
        self.pan = None
        self.groups = {}
        self.last_click = (0, None)
        self.last_group = (None, 0)
        self.markers = []         # [x, y, age, colour]
        self.mouse = (0, 0)
        self.show_help = False
        self.cam_x = self.cam_y = 0.0
        hall = next(b for b in game.buildings if b.team == PLAYER)
        self.center_on(hall.x, hall.y)

    # ---- camera -----------------------------------------------------------

    def center_on(self, x, y):
        self.cam_x = x - VIEW_W / 2
        self.cam_y = y - VIEW_H / 2
        self.clamp()

    def clamp(self):
        self.cam_x = max(0.0, min(self.cam_x, MAP_W * TILE - VIEW_W))
        self.cam_y = max(0.0, min(self.cam_y, MAP_H * TILE - VIEW_H))

    def to_world(self, pos):
        return pos[0] + int(self.cam_x), pos[1] + int(self.cam_y)

    def place_origin(self, wx, wy):
        s = BUILDINGS[self.place_kind]["size"]
        return self.game.snap_to_grid(wx / TILE - s / 2, wy / TILE - s / 2)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        if pygame.mouse.get_focused() and not self.pan and not self.minimap_drag and not self.dragging:
            mx, my = ui_mouse()
            if mx <= EDGE_SCROLL:
                dx -= 1
            elif mx >= SCREEN_W - 1 - EDGE_SCROLL:
                dx += 1
            if my <= EDGE_SCROLL:
                dy -= 1
            elif my >= SCREEN_H - 1 - EDGE_SCROLL:
                dy += 1
        self.cam_x += max(-1, min(1, dx)) * CAMERA_SPEED * dt
        self.cam_y += max(-1, min(1, dy)) * CAMERA_SPEED * dt
        self.clamp()

        self.selection = [e for e in self.selection if e.alive and not getattr(e, "inside", None)]
        for m in self.markers:
            m[2] += dt
        self.markers = [m for m in self.markers if m[2] < MARKER_TIME]
        if self.mode in TARGET_MODES and not self.own_units():
            self.mode = None

    # ---- selection helpers ----------------------------------------------------

    def own(self):
        return [e for e in self.selection if e.team == PLAYER]

    def own_units(self):
        return [e for e in self.selection if e.team == PLAYER and e.is_unit]

    def pick(self, wx, wy):
        best, best_key = None, None
        for e in self.game.entities:
            if e.is_unit:
                rad = e.radius
                l, t, r, b = e.x - rad - 2, e.y - UNITS[e.kind]["height"], e.x + rad + 2, e.y + 4
            else:
                l, t, r, b = e.rect()
            if l <= wx < r and t <= wy < b and self.game.seen(e):
                key = (0 if e.is_unit else 1, (e.x - wx) ** 2 + (e.y - wy) ** 2)
                if best is None or key < best_key:
                    best, best_key = e, key
        return best

    def marker(self, x, y, color):
        self.markers.append([x, y, 0.0, color])

    @staticmethod
    def ack(target):
        """Units were sent at a building or derrick: it flashes softly to show the click landed."""
        if target is not None and not target.is_unit:
            target.ping_it()

    # ---- command card -----------------------------------------------------------

    def commands(self):
        sel = self.own()
        if not sel:
            return []
        units = [e for e in sel if e.is_unit]
        if units:
            # Q, E and R are kept for unit abilities (the 155mm's Deploy / Pack up).
            cmds = [dict(id="move", key="m", icon="move", title="Move",
                         desc="Park next to a derrick to capture it."),
                    dict(id="stop", key="x", icon="stop", title="Stop")]
            if any(u.armed for u in units):
                cmds.append(dict(id="attack", key="t", icon="attack", title="Attack",
                                 desc="Click an enemy, or ground to attack-move."))
            if any(u.deploy_time for u in units):
                cmds.append(dict(id="deploy", key="q", icon="deploy", title="Deploy",
                                 desc="Dig in here: the gun turns to fire on anything in range."))
                cmds.append(dict(id="pack", key="e", icon="pack", title="Pack up",
                                 desc="Spades up and barrel down, ready to drive."))
            if all(u.kind == "engineer" for u in units):
                cmds.append(dict(id="repair", key="f", icon="repair", title="Repair",
                                 desc="Fix a building or vehicle."))
            return cmds
        b = sel[0]
        if b.is_building:
            if not b.complete:
                return [dict(id="cancel", key="x", icon="cancel", title="Cancel", desc="Refunds the full cost.")]
            cmds = []
            if b.stats["trains"]:
                cmds.append(dict(id="design", key="e", icon="design", title="Design units",
                                 desc="Choose the armor, weapons and speed of what this trains."))
            if b.capacity and b.occupants:
                cmds.append(dict(id="unload", key="u", icon="move", title="Unload",
                                 desc=f"Everyone out ({len(b.occupants)}/{b.capacity} inside)."))
            return cmds
        return []

    # ---- sidebar build menu ------------------------------------------------------

    def menu_source(self):
        """The selected factory whose options the sidebar lists, or None for the Command
        Center's default menu."""
        return next((b for b in self.own() if b.is_building and b.complete and b.stats["trains"]), None)

    def menu_title(self):
        src = self.menu_source()
        return src.name if src else BUILDINGS["command"]["name"]

    def build_menu(self):
        """Sidebar entries, numbered 1-9. The Command Center (also the default when no factory
        is selected) lays down buildings and trains engineers; other factories train their units."""
        g = self.game
        src = self.menu_source()
        speed = g.build_speed
        items = []
        if src is None or src.kind == "command":
            for kind in BUILDABLE:
                st = BUILDINGS[kind]
                items.append(dict(id="build:" + kind, icon="bld:" + kind, name=st["name"],
                                  title="Build " + st["name"], cost=st["cost"], desc=st["desc"],
                                  time=st["time"] / speed, time_note="with one engineer"))
            trains = BUILDINGS["command"]["trains"]
        else:
            trains = src.stats["trains"]
        for k in trains:
            hall = self.trainer_for(k)
            lo = hall.designs[k] if hall else default_loadout(k)
            items.append(dict(id="train:" + k, unit=k, name=UNITS[k]["name"], title="Train " + UNITS[k]["name"],
                              cost=loadout_cost(k, lo), supply=UNITS[k]["supply"], desc=UNITS[k]["desc"],
                              design=lo, loadout=loadout_summary(k, lo), time=loadout_time(k, lo) / speed))
        items = items[:9]
        for i, it in enumerate(items):
            it["key"] = str(i + 1)
        return items

    def factories_for(self, kind):
        """Where a unit can be trained: the selected factories if any can, else all of them."""
        own = [b for b in self.game.buildings if b.team == PLAYER and b.complete and kind in b.stats["trains"]]
        picked = [b for b in own if b in self.selection]
        return picked or own

    def trainer_for(self, kind):
        """The factory a train order for `kind` goes to (the least busy one), or None. Each factory
        has its own unit designs, so the menu shows this one's."""
        halls = self.factories_for(kind)
        return min(halls, key=lambda b: len(b.queue)) if halls else None

    def jump_to_command_center(self):
        g = self.game
        halls = [b for b in g.buildings if b.team == PLAYER and b.kind == "command"]
        if not halls:
            g.notify(PLAYER, "No Command Center")
            return
        # Cycle through them if there are several.
        i = (halls.index(self.selection[0]) + 1) % len(halls) if self.selection and self.selection[0] in halls else 0
        self.center_on(halls[i].x, halls[i].y)
        self.selection = [halls[i]]

    def execute(self, cmd):
        """Run a command-card command. Returns "design" when the design screen should open."""
        g = self.game
        cid = cmd["id"]
        if cid in TARGET_MODES:
            self.mode = cid
        elif cid == "stop":
            for u in self.own_units():
                u.stop(g)
        elif cid == "deploy":
            for u in self.own_units():
                u.order_deploy(g)
        elif cid == "pack":
            for u in self.own_units():
                u.order_pack(g)
        elif cid == "design":
            return "design"
        elif cid.startswith("build:"):
            kind = cid[6:]
            if g.teams[PLAYER].credits < BUILDINGS[kind]["cost"]:
                g.notify(PLAYER, "Not enough credits")
            else:
                self.mode = "place"
                self.place_kind = kind
        elif cid.startswith("train:"):
            kind = cid[6:]
            hall = self.trainer_for(kind)
            if hall:
                g.train(hall, kind)
            else:
                trainer = next(BUILDINGS[k]["name"] for k in BUILDINGS if kind in BUILDINGS[k]["trains"])
                g.notify(PLAYER, f"Needs a {trainer}")
        elif cid == "cancel":
            for b in self.own():
                if b.is_building:
                    g.cancel_construction(b)
        elif cid == "unload":
            for b in self.own():
                if b.is_building and b.occupants:
                    g.unload(b)
        return None

    # ---- events -----------------------------------------------------------------

    def handle(self, ev):
        """Process one event. Returns "pause" when the player asks for the menu."""
        if ev.type == pygame.MOUSEMOTION:
            self.mouse = ev.pos
            if self.minimap_drag:
                self.center_on(*self.hud.minimap_to_world(ev.pos))
            if self.pan:
                self.cam_x -= ev.pos[0] - self.pan[0]
                self.cam_y -= ev.pos[1] - self.pan[1]
                self.pan = ev.pos
                self.clamp()
            if self.drag_start and not self.dragging:
                wx, wy = self.to_world(ev.pos)
                if abs(wx - self.drag_start[0]) + abs(wy - self.drag_start[1]) > 4:
                    self.dragging = True
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = ev.pos
            shift = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
            if ev.button == 1:
                return self.left_down(ev.pos, shift)
            elif ev.button == 3:
                self.right_down(ev.pos)
            elif ev.button == 2:
                self.pan = ev.pos
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1:
                self.minimap_drag = None
                if self.drag_start:
                    self.finish_drag(ev.pos)
            elif ev.button == 2:
                self.pan = None
        elif ev.type == pygame.KEYDOWN:
            return self.key_down(ev)
        return None

    def map_at(self, pos):
        """True when the cursor is over the minimap."""
        return self.hud.minimap_rect.collidepoint(pos)

    def in_sidebar(self, pos):
        return pos[0] >= VIEW_W and pos[1] < VIEW_H

    def left_down(self, pos, shift):
        g = self.game
        if self.map_at(pos):
            if self.mode in TARGET_MODES:
                self.target_command(*self.hud.minimap_to_world(pos), None, shift)
            else:
                self.minimap_drag = True
                self.center_on(*self.hud.minimap_to_world(pos))
            return None
        if self.in_sidebar(pos):
            if self.hud.portrait_rect.collidepoint(pos):
                shown = self.hud.portrait_building(self)
                if shown is not None:
                    self.center_on(shown.x, shown.y)
                else:
                    self.jump_to_command_center()
                return None
            items = self.build_menu()
            i = self.hud.menu_item_at(pos, len(items))
            if i is not None:
                return self.execute(items[i])
            return None
        if pos[1] >= VIEW_H:
            cmds = self.commands()
            i = self.hud.button_at(pos, len(cmds))
            if i is not None:
                return self.execute(cmds[i])
            j = self.hud.selection_icon_at(pos, self)
            if j is not None:
                e = self.selection[j]
                if shift and e.is_unit:
                    self.shift_pick(e)
                elif shift:
                    self.selection.remove(e)
                else:
                    self.selection = [e]
                return
            q = self.hud.queue_slot_at(pos, self)
            if q is not None:
                g.cancel_train(self.selection[0], q)
            return
        wx, wy = self.to_world(pos)
        if self.mode == "place":
            self.place(wx, wy, shift)
        elif self.mode in TARGET_MODES:
            self.target_command(wx, wy, self.pick(wx, wy), shift)
        else:
            self.drag_start = (wx, wy)
            self.dragging = False

    def right_down(self, pos):
        if self.mode:
            self.mode = None
            return
        if self.map_at(pos):
            self.smart_command(*self.hud.minimap_to_world(pos), None)
            return
        if pos[1] >= VIEW_H or self.in_sidebar(pos):
            return
        wx, wy = self.to_world(pos)
        self.smart_command(wx, wy, self.pick(wx, wy))

    def finish_drag(self, pos):
        g = self.game
        wx, wy = self.to_world(pos)
        sx, sy = self.drag_start
        self.drag_start = None
        mods = pygame.key.get_mods()
        shift = bool(mods & pygame.KMOD_SHIFT)
        if self.dragging:
            self.dragging = False
            l, r = sorted((sx, wx))
            t, b = sorted((sy, wy))
            found = [u for u in g.units if u.team == PLAYER and l <= u.x <= r and t - 4 <= u.y <= b + 6]
            if shift:
                base = self.own_units()
                self.selection = base + [u for u in found if u not in base]
            elif found:
                self.selection = found
            return
        self.click_select(wx, wy, shift, bool(mods & pygame.KMOD_CTRL))

    def click_select(self, wx, wy, shift, ctrl):
        g = self.game
        e = self.pick(wx, wy)
        now = pygame.time.get_ticks()
        double = e is not None and self.last_click[1] is e and now - self.last_click[0] < 350
        self.last_click = (now, e)
        if e is None:
            if not shift:
                self.selection = []
            return
        if e.is_unit and e.team == PLAYER:
            if double or ctrl:
                l, t = self.cam_x, self.cam_y
                self.selection = [u for u in g.units if u.team == PLAYER and u.kind == e.kind
                                  and l <= u.x <= l + VIEW_W and t <= u.y <= t + VIEW_H]
                return
            if shift:
                self.shift_pick(e)
                return
        self.selection = [e]

    def shift_pick(self, e):
        """Shift-click on one of your units. In a mixed selection, clicking a selected unit keeps
        just the units of its type; otherwise it toggles that unit in or out of the selection."""
        base = self.own_units()
        if e in base and any(u.kind != e.kind for u in base):
            self.selection = [u for u in base if u.kind == e.kind]
            log.debug("Selection narrowed to %d %s (from %d units)", len(self.selection), e.kind, len(base))
        elif e in base:
            base.remove(e)
            self.selection = base
        else:
            self.selection = base + [e]

    def key_down(self, ev):
        g = self.game
        k = ev.key
        if k == pygame.K_ESCAPE:
            if self.mode:
                self.mode = None
                return None
            if self.show_help:
                self.show_help = False
                return None
            return "pause"
        if k == pygame.K_F10:
            return "pause"
        if k == pygame.K_F1:
            self.show_help = not self.show_help
            return None
        if pygame.K_0 <= k <= pygame.K_9:
            n = k - pygame.K_0
            if ev.mod & pygame.KMOD_CTRL:
                if self.own():
                    self.groups[n] = list(self.own())
                    g.notify(PLAYER, f"Group {n} assigned")
                    log.debug("Control group %d = %d selected", n, len(self.groups[n]))
                return None
            if not ev.mod & pygame.KMOD_SHIFT:   # the number row picks from the build menu
                items = self.build_menu()
                if 1 <= n <= len(items):
                    return self.execute(items[n - 1])
                return None
            group = [e for e in self.groups.get(n, []) if e.alive and not getattr(e, "inside", None)]
            if group:
                now = pygame.time.get_ticks()
                if self.last_group[0] == n and now - self.last_group[1] < 400:
                    self.center_on(sum(e.x for e in group) / len(group), sum(e.y for e in group) / len(group))
                self.selection = list(group)
                self.last_group = (n, now)
            return None
        if k == pygame.K_SPACE:
            halls = [b for b in g.buildings if b.team == PLAYER]
            if halls:
                halls.sort(key=lambda b: b.kind != "command")
                self.center_on(halls[0].x, halls[0].y)
            return None
        if k == pygame.K_F5 and g.sandbox:
            g.spawn_test_targets()
            return None
        name = pygame.key.name(k)
        for cmd in self.commands():
            if cmd["key"] == name:
                return self.execute(cmd)
        return None

    # ---- orders -------------------------------------------------------------------

    def smart_command(self, wx, wy, target):
        g = self.game
        units = self.own_units()
        tx, ty = int(wx // TILE), int(wy // TILE)
        if not units:
            halls = [b for b in self.own() if b.is_building and b.complete and b.stats["trains"]]
            for b in halls:
                b.rally = target if (target is not None and target.is_point) else (tx, ty)
            if halls:
                self.marker(wx, wy, (90, 230, 90))
            return
        if target is not None and target.is_point:
            g.command_move(units, *target.center_tile())
            self.ack(target)
            self.marker(target.x, target.y, (240, 220, 90))
            return
        if target is not None and target.team not in (PLAYER, NEUTRAL):
            log.debug("%s: %d units ordered to attack %s #%d", g.clock(), len(units), target.name, target.id)
            for u in units:
                u.order_attack(g, target)
            if not g.send_escorts(units):
                g.command_move([u for u in units if not u.armed], tx, ty)
            self.ack(target)
            self.marker(target.x, target.y, (235, 70, 60))
            return
        movers = []
        for u in units:
            friendly = target is not None and target.team == PLAYER and target is not u
            if friendly and u.kind == "engineer" and target.is_building and not target.complete:
                u.order_construct(g, target)
            elif friendly and u.kind == "engineer" and not target.is_infantry and target.hp < target.max_hp:
                u.order_repair(g, target)
            elif friendly and u.heal and target.is_infantry and target.hp < target.max_hp:
                u.order_heal(g, target)
            elif (friendly and u.is_infantry and target.is_building and target.complete
                  and target.capacity):
                u.order_garrison(g, target)   # man the bunker
            else:
                movers.append(u)
        if movers:
            g.command_move(movers, tx, ty)
        others = len(units) - len(movers)
        self.ack(target)
        log.debug("%s: right-click at %s: %d moving, %d given a task", g.clock(), (tx, ty), len(movers), others)
        self.marker(wx, wy, (90, 230, 90))

    def target_command(self, wx, wy, target, shift):
        g = self.game
        units = self.own_units()
        tx, ty = int(wx // TILE), int(wy // TILE)
        if self.mode == "move":
            g.command_move(units, tx, ty)
            self.marker(wx, wy, (90, 230, 90))
        elif self.mode == "attack":
            if target is not None and target.team not in (PLAYER, NEUTRAL):
                for u in units:
                    u.order_attack(g, target)
                g.send_escorts(units)
                self.ack(target)
            else:
                g.command_move(units, tx, ty, attack=True)
            self.marker(wx, wy, (235, 70, 60))
        elif self.mode == "repair":
            if (target is None or target.team != PLAYER or target.is_infantry or target.is_point
                    or target.hp >= target.max_hp):
                g.notify(PLAYER, "Click a damaged building or vehicle")
                return
            for u in units:
                if u.kind == "engineer":
                    if target.is_building and not target.complete:
                        u.order_construct(g, target)
                    else:
                        u.order_repair(g, target)
            self.ack(target)
            self.marker(wx, wy, (240, 220, 90))
        if not shift:
            self.mode = None

    def place(self, wx, wy, shift):
        """Lay the foundation where the player clicked; the closest idle engineer goes to build it."""
        g = self.game
        kind = self.place_kind
        tx, ty = self.place_origin(wx, wy)
        if g.teams[PLAYER].credits < BUILDINGS[kind]["cost"]:
            g.notify(PLAYER, "Not enough credits")
            self.mode = None
            return
        b = g.place_foundation(kind, tx, ty, PLAYER)
        if b is None:
            return
        self.marker(b.x, b.y, (90, 230, 90))
        if not shift:
            self.mode = None
