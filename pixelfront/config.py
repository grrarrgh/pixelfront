"""Game-wide constants and unit/building definitions."""

# The UI (panels, sidebar, pixel font) lives on a 640x360 grid; the game world and its art are
# drawn RES times finer, so the window shows SCREEN_W*RES x SCREEN_H*RES pixels, scaled up with
# nearest-neighbour filtering. World coordinates stay in game pixels (16 per tile).
SCREEN_W, SCREEN_H = 640, 360
RES = 2
DISPLAY_W, DISPLAY_H = SCREEN_W * RES, SCREEN_H * RES
TILE = 16
MAP_W, MAP_H = 64, 64
HUD_H = 80
VIEW_H = SCREEN_H - HUD_H
SIDEBAR_W = 80             # build menu down the right-hand side of the map view
VIEW_W = SCREEN_W - SIDEBAR_W
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
RETREAT_DISTANCE = 3       # tiles a pinned soldier crawls away from whatever is suppressing them
RETREAT_COOLDOWN = 4.0     # seconds before a pinned soldier will crawl back again
RETREAT_TIMEOUT = 6.0      # give up on a retreat that's taking too long

BURST_GAP = 0.09           # seconds between rounds of a burst (machine guns)
TRACER_LIFE = 0.07         # seconds a dashed bullet trail stays on screen

# Infantry manning a bunker: reload time x0.75, damage and range x1.1.
GARRISON_RELOAD = 0.75
GARRISON_DAMAGE = 1.1
GARRISON_RANGE = 1.1
GARRISON_HEAL = 1.0        # hp per second the bunker slowly restores to each soldier inside
                           # (always well below a medic's rate)

TURRET_SPEED = 160         # degrees per second a turret (or mounted gun) traverses
STEER_MAX = 28             # how far front wheels turn into a bend, degrees

# Buildings snap to the tile grid and must keep a tile of clearance from other buildings, leaving
# lanes to move through. (A coarser grid, e.g. 4 with offset 2, lines bases up in blocks.)
BUILD_GRID = 1
GRID_OFFSET = 0            # grid lines fall on tiles where (tile - GRID_OFFSET) % BUILD_GRID == 0
QUEUE_MAX = 15             # units a factory can have queued
BUILD_SPEED = 0.5         # global construction and training speed (0.5 = everything takes twice as long)
SANDBOX_BUILD_SPEED = 10   # the test range builds and trains this many times faster than that
KNEEL_TIME = 0.5           # seconds heavy infantry take to kneel before they can fire

# Units live in pixelfront/units/ (one file per type) and weapons in pixelfront/weapons.py.

BUILDINGS = {
    "command": dict(name="Command Center", size=3, hp=1500, armor=4, cost=500, time=60,
                    sight=8, trains=["engineer"],
                    desc="Trains engineers. +1 credit/s."),
    "barracks": dict(name="Barracks", size=2, hp=800, armor=3, cost=200, time=30,
                     sight=6, trains=["rifleman", "medic", "heavy"],
                     desc="Trains infantry."),
    # garrison = what manning it does for the soldiers inside: reload (time x), damage x,
    # range x, heal (hp/s), sight (+tiles for the building while manned).
    "bunker": dict(name="Bunker", size=2, hp=900, armor=5, cost=150, time=20,
                   sight=7, trains=[], capacity=4,
                   garrison=dict(reload=GARRISON_RELOAD, damage=GARRISON_DAMAGE, range=GARRISON_RANGE,
                                 heal=GARRISON_HEAL),
                   desc="Man it with infantry: faster reloads, +10% damage and range."),
    "tower": dict(name="Tower", size=1, hp=450, armor=4, cost=120, time=15,
                  sight=5, trains=[], capacity=2,
                  garrison=dict(range=1.35, sight=6),
                  desc="Lookout for 2 infantry: they see and shoot much further. No healing."),
    "yard": dict(name="Vehicle Yard", size=3, hp=1000, armor=4, cost=300, time=40,
                 sight=6, trains=["jeep", "tank"],
                 desc="Builds jeeps and tanks."),
}
