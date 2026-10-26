"""Game-wide constants and unit/building definitions."""

# Logical resolution; the window scales this up with nearest-neighbour filtering.
SCREEN_W, SCREEN_H = 640, 360
TILE = 16
MAP_W, MAP_H = 64, 64
HUD_H = 80
VIEW_H = SCREEN_H - HUD_H
TOPBAR_H = 11
FPS = 60

CAMERA_SPEED = 380
EDGE_SCROLL = 3

PLAYER, ENEMY, NEUTRAL = 0, 1, -1

TEAM_COLORS = {
    PLAYER: ((72, 132, 232), (34, 64, 150)),
    ENEMY: ((222, 64, 52), (124, 30, 26)),
}

START_CREDITS = 400
SUPPLY_CAP = 50
BASE_INCOME = 1.0       # credits per second from each Command Center
POINT_INCOME = 2.0      # credits per second from each captured derrick
CAPTURE_TIME = 12.0     # seconds for one unit to capture a neutral point
CAPTURE_RADIUS = 36     # px from the point's centre
MAX_CAPTURERS = 3       # units beyond this don't speed up capturing
POINT_SIGHT = 3

INTERACT = 2  # px between edges that counts as touching (medics and engineers must touch to work)
REPAIR_RATE = 15  # hp per second at work = 1

# Suppression: infantry under heavy fire go prone and crawl.
SUPPRESS_PER_SHOT = 4      # plus the shot's damage, for every bullet aimed at a soldier
SUPPRESS_EXPLOSIVE = 30    # rockets and shells landing nearby
SUPPRESS_RADIUS = 20       # px around an explosion
SUPPRESS_ON, SUPPRESS_OFF = 60, 20   # go prone at/above ON, get up below OFF
SUPPRESS_DECAY = 20        # per second, once not shot at for SUPPRESS_CALM seconds
SUPPRESS_CALM = 1.0
PRONE_SPEED = 0.6          # speed multiplier while crawling (40% slower)
PRONE_TARGET_HIT = 0.5     # chance-to-hit multiplier for shots aimed at a prone soldier
PRONE_ACCURACY = 0.75      # accuracy multiplier while pinned
PRONE_RANGE = 0.6          # weapon range multiplier while firing prone

BURST_GAP = 0.09           # seconds between rounds of a burst (machine guns)

# Infantry manning a bunker: reload time x0.75, damage and range x1.1.
GARRISON_RELOAD = 0.75
GARRISON_DAMAGE = 1.1
GARRISON_RANGE = 1.1
GARRISON_HEAL = 1.0        # hp per second the bunker slowly restores to each soldier inside
                           # (always well below a medic's rate)

TURRET_SPEED = 160         # degrees per second a turret (or mounted gun) traverses
HULL_TURN = {"jeep": 300, "tank": 140}   # degrees per second a vehicle hull turns
STEER_MAX = 28             # how far front wheels turn into a bend, degrees

# Buildings snap to an invisible grid and keep a tile of clearance, leaving lanes to move through.
BUILD_GRID = 4
GRID_OFFSET = 2            # grid lines fall on tiles where (tile - GRID_OFFSET) % BUILD_GRID == 0
SANDBOX_BUILD_SPEED = 10   # the test range builds and trains this many times faster
KNEEL_TIME = 0.5           # seconds heavy infantry take to kneel before they can fire

# Base stats, before loadout modules (see modules.py). "cls" is infantry or vehicle.
# weapon: "bullet" hits instantly; "rocket", "atgm", "shell", "autocannon", "grenade" and
# "artillery" fire projectiles (see entities.PROJECTILES); None = unarmed.
UNITS = {
    "engineer": dict(name="Engineer", cls="infantry", hp=40, armor=0, damage=3, range=40, cooldown=1.0,
                     weapon="bullet", speed=38, sight=5, work=1.0, cost=75, time=9, supply=1,
                     radius=4, height=13, hotkey="e", desc="Builds, repairs and captures.",
                     slot_labels={"weapon": "Tools"}),
    "rifleman": dict(name="Rifleman", cls="infantry", hp=55, armor=0, damage=6, range=64, cooldown=0.9,
                     weapon="bullet", speed=40, sight=6, cost=60, time=8, supply=1,
                     radius=4, height=13, hotkey="r", desc="All-round infantry."),
    "medic": dict(name="Medic", cls="infantry", hp=45, armor=0, damage=0, heal=6, range=0, cooldown=1.0,
                  weapon=None, speed=42, sight=6, cost=70, time=9, supply=1,
                  radius=4, height=13, hotkey="m", desc="Heals nearby infantry.",
                  slot_labels={"weapon": "Medkit"}),
    "heavy": dict(name="Heavy Infantry", cls="infantry", hp=80, armor=1, damage=14, range=80, cooldown=1.6,
                  weapon="grenade", accuracy=0.8, speed=32, sight=6, cost=110, time=12, supply=1,
                  radius=4, height=13, hotkey="h", desc="Armoured heavy weapons team."),
    "jeep": dict(name="Jeep", cls="vehicle", hp=110, armor=1, damage=10, range=84, cooldown=0.6,
                 weapon="grenade", accuracy=0.75, speed=72, sight=8, cost=120, time=12, supply=2,
                 radius=9, height=19, hotkey="j", desc="Fast scout with a mounted weapon."),
    "tank": dict(name="Tank", cls="vehicle", hp=300, armor=4, damage=30, range=88, cooldown=2.0,
                 weapon="shell", speed=30, sight=7, cost=250, time=20, supply=3,
                 radius=11, height=21, hotkey="t", desc="Heavy armor and a big gun."),
}

BUILDINGS = {
    "command": dict(name="Command Center", size=3, hp=1500, armor=4, cost=500, time=60,
                    sight=8, trains=["engineer"], hotkey="c",
                    desc="Trains engineers. +1 credit/s."),
    "barracks": dict(name="Barracks", size=2, hp=800, armor=3, cost=200, time=30,
                     sight=6, trains=["rifleman", "medic", "heavy"], hotkey="b",
                     desc="Trains infantry."),
    "bunker": dict(name="Bunker", size=2, hp=900, armor=5, cost=150, time=20,
                   sight=7, trains=[], capacity=4, hotkey="k",
                   desc="Man it with infantry: faster reloads, +10% damage and range."),
    "yard": dict(name="Vehicle Yard", size=3, hp=1000, armor=4, cost=300, time=40,
                 sight=6, trains=["jeep", "tank"], hotkey="y",
                 desc="Builds jeeps and tanks."),
}
