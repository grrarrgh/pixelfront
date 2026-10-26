"""Computer opponent: grabs derricks, builds an army with varied loadouts and attacks in waves."""
import logging
import math
import random

from .config import TILE, BUILDINGS, CAPTURE_RADIUS
from .modules import slots_for, tiers, default_loadout, loadout_summary

log = logging.getLogger(__name__)

ARMY_MIX = {"barracks": [("rifleman", 5), ("heavy", 2), ("medic", 1)],
            "yard": [("jeep", 2), ("tank", 3)]}

# Difficulty. The AI is deliberately a bit slow and a bit dim:
THINK_INTERVAL = 2.5      # seconds between decisions (slow to react)
FIRST_WAVE_AT = 300.0     # seconds before the first attack wave
FIRST_WAVE, WAVE_GROWTH, MAX_WAVE = 4, 1, 10   # attack wave sizes
TRAIN_CHANCE = 0.6        # chance an idle factory gets a new order on each think (it dawdles)
MAX_ENGINEERS = 2
DEFEND_RADIUS = 9         # tiles from the threat: only units this close notice their base is under attack
DEFEND_CHANCE = 0.5       # and each of those only reacts half the time per think
DUMB_TARGET = 0.4         # chance an attack wave heads for a random building, not the nearest


class AI:
    def __init__(self, game, team, first_wave_at=FIRST_WAVE_AT):
        self.game = game
        self.team = team
        self.timer = 2.0
        self.wave = FIRST_WAVE
        self.first_wave_at = first_wave_at
        self.rng = random.Random(game.rng.random())
        self.claims = {}  # unit id -> capture point it was sent to
        self.defending = False   # remembered so the log only notes when a defence starts/ends

    def update(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = THINK_INTERVAL
            self.think()

    def think(self):
        g = self.game
        me = g.teams[self.team]
        units = [u for u in g.units if u.team == self.team]
        engineers = [u for u in units if u.kind == "engineer"]
        army = [u for u in units if u.kind != "engineer"]
        mine = [b for b in g.buildings if b.team == self.team]
        if not mine:
            return
        ccs = [b for b in mine if b.kind == "command" and b.complete]
        base = ccs[0] if ccs else mine[0]
        pending = {b.kind for b in mine if not b.complete}
        pending |= {u.build_plan[0] for u in engineers if u.build_plan}
        count = lambda kind: sum(1 for b in mine if b.kind == kind)

        # Buildings: barracks first, then a yard, then more of each when rich.
        if "barracks" not in pending and (count("barracks") == 0 or (count("barracks") < 2 and me.credits > 700)):
            if me.credits >= BUILDINGS["barracks"]["cost"]:
                self.build("barracks", engineers, base)
        elif ("yard" not in pending and count("barracks") and
              (count("yard") == 0 or (count("yard") < 2 and me.credits > 900))):
            if me.credits >= BUILDINGS["yard"]["cost"]:
                self.build("yard", engineers, base)

        for b in mine:
            if not b.complete or b.queue or self.rng.random() > TRAIN_CHANCE:
                continue
            if b.kind == "command" and len(engineers) < MAX_ENGINEERS:
                g.train(b, "engineer")
            elif b.kind in ARMY_MIX:
                kind = self.rng.choices(*zip(*ARMY_MIX[b.kind]))[0]
                self.redesign(kind)
                g.train(b, kind)

        # Engineers: repair damaged buildings, otherwise grab nearby derricks.
        for e in engineers:
            if e.order != "idle":
                continue
            hurt = next((b for b in mine if b.complete and b.hp < b.max_hp * 0.7), None)
            if hurt:
                e.order_repair(g, hurt)

        threat = next((u for u in g.units if u.team != self.team
                       and math.hypot(u.x - base.x, u.y - base.y) < 14 * TILE), None)
        if bool(threat) != self.defending:
            self.defending = bool(threat)
            if threat:
                log.info("%s: AI defending its base against %s #%d", g.clock(), threat.name, threat.id)
            else:
                log.info("%s: AI base threat cleared", g.clock())
        if threat:
            for s in army:
                if (s.order in ("idle", "move") and s.armed and self.rng.random() < DEFEND_CHANCE
                        and math.hypot(s.x - threat.x, s.y - threat.y) < DEFEND_RADIUS * TILE):
                    s.order_attack(g, threat)
            return

        idle = [u for u in units if u.order == "idle" and not self.capturing(u)]
        idle_army = [u for u in idle if u.kind != "engineer"]
        if g.time >= self.first_wave_at and len(idle_army) >= self.wave:
            target = self.pick_target(base)
            if target:
                g.command_move(idle_army, *target.center_tile(), attack=True)
                mix = {}
                for u in idle_army:
                    mix[u.kind] = mix.get(u.kind, 0) + 1
                log.info("%s: AI attack wave of %d (%s) sent at %s %s; next wave size %d", g.clock(),
                         len(idle_army), ", ".join(f"{n} {k}" for k, n in sorted(mix.items())),
                         target.name, (target.tx, target.ty), min(MAX_WAVE, self.wave + WAVE_GROWTH))
                self.wave = min(MAX_WAVE, self.wave + WAVE_GROWTH)
                idle = [u for u in idle if u.kind == "engineer"]
        self.send_capturers(idle, base)

    def capturing(self, u):
        """True while the unit is parked on a point this team doesn't fully own yet."""
        for p in self.game.points:
            if (p.team != self.team or p.progress < 1) and math.hypot(u.x - p.x, u.y - p.y) <= CAPTURE_RADIUS:
                return True
        return False

    def send_capturers(self, idle, base):
        g = self.game
        alive = {u.id for u in g.units}
        self.claims = {uid: p for uid, p in self.claims.items() if uid in alive and p.team != self.team}
        targets = [p for p in g.points if p.team != self.team]
        if not targets:
            return
        heading = {}
        for p in self.claims.values():
            heading[p.id] = heading.get(p.id, 0) + 1
        for u in idle:
            cands = [p for p in targets if heading.get(p.id, 0) < 2]
            if not u.armed or u.kind == "engineer":
                # Builders are precious: only send them to points close to home.
                cands = [p for p in cands if math.hypot(p.x - base.x, p.y - base.y) < 20 * TILE]
            if not cands:
                return
            # Prefer points near this unit and near home.
            p = min(cands, key=lambda p: math.hypot(p.x - u.x, p.y - u.y) + 0.5 * math.hypot(p.x - base.x, p.y - base.y))
            heading[p.id] = heading.get(p.id, 0) + 1
            self.claims[u.id] = p
            log.debug("%s: AI sends %s #%d to capture the derrick at %s", g.clock(), u.name, u.id, p.center_tile())
            g.command_move([u], *p.center_tile(), attack=u.armed)

    def redesign(self, kind):
        """Occasionally try a different loadout so the enemy army isn't uniform."""
        designs = self.game.teams[self.team].designs
        if self.rng.random() < 0.5:
            designs[kind] = default_loadout(kind)
            for slot in slots_for(kind):
                if self.rng.random() < 0.5:
                    designs[kind][slot] = self.rng.randrange(len(tiers(kind, slot)))
            log.debug("AI redesigned %s: %s", kind, loadout_summary(kind, designs[kind]))

    def pick_target(self, base):
        enemies = [b for b in self.game.buildings if b.team != self.team]
        if not enemies:
            return None
        if self.rng.random() < DUMB_TARGET:   # not the sharpest general
            return self.rng.choice(enemies)
        return min(enemies, key=lambda b: (b.x - base.x) ** 2 + (b.y - base.y) ** 2)

    def build(self, kind, engineers, base):
        g = self.game
        cands = [e for e in engineers if e.order in ("idle", "move", "amove")] or engineers
        if not cands:
            return
        spot = self.find_spot(kind, base)
        if spot is None:
            log.warning("%s: AI found nowhere to build a %s near %s", g.clock(), kind, (base.tx, base.ty))
            return
        g.teams[self.team].credits -= BUILDINGS[kind]["cost"]
        sx, sy = spot[0] * TILE, spot[1] * TILE
        worker = min(cands, key=lambda w: (w.x - sx) ** 2 + (w.y - sy) ** 2)
        self.claims.pop(worker.id, None)
        log.info("%s: AI orders a %s at %s (engineer #%d)", g.clock(), kind, spot, worker.id)
        worker.order_build(g, kind, *spot)

    def find_spot(self, kind, base):
        """A legal build-grid site near the base whose surroundings are open ground."""
        g = self.game
        s = BUILDINGS[kind]["size"]
        cx, cy = base.center_tile()
        for r in range(2, 16):
            ring = [(x, y) for y in range(cy - r, cy + r + 1) for x in range(cx - r, cx + r + 1)
                    if max(abs(x - cx), abs(y - cy)) == r]
            self.rng.shuffle(ring)
            for x, y in ring:
                tx, ty = g.snap_to_grid(x - s / 2, y - s / 2)
                if g.can_place(kind, tx, ty) and all(
                        g.world.buildable(xx, yy) or g.world.occupant[yy * g.world.w + xx] is not None
                        for yy in range(ty - 1, ty + s + 1) for xx in range(tx - 1, tx + s + 1)
                        if g.world.in_bounds(xx, yy)):
                    return tx, ty
        return None
