# Pixelfront

A small old-school pixel-art real-time strategy game for Windows, written in Python with
[pygame-ce](https://pyga.me/). Futuristic desert warfare: soldiers, jeeps and tanks fight over
oil derricks. All art is drawn procedurally, so there are no asset files.

## Run from source

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Build the Windows executable

```powershell
.\build.ps1
```

This produces a single self-contained `dist\Pixelfront.exe`.

## Tests

```powershell
python -m unittest discover tests
```

`tests/test_mapgen.py` generates 60 maps and checks each one:

- Every open tile is reachable, and nothing but cliff blocks movement.
- No cliff stands on its own.
- Every plateau has a ramp, and every ramp is a 3-wide cut square into a straight cliff wall.
- Both halves of the map are the same.

## Logs

Every run writes a log to `logs\YYYYMMDD_HHMMSS.log` (next to `Pixelfront.exe`, or in the project
folder when running from source); the newest 50 are kept. Set `PIXELFRONT_DEBUG=1` before
launching for extra detail such as individual orders.

## How to play

Destroy every enemy building to win. Lose all of yours and it's over.

- **Income** comes from **oil derricks** scattered across the desert. Park units next to one
  to capture it (more units capture faster, up to 3). An enemy-owned derrick has to be
  neutralized before you can take it. Each derrick pays +2 credits/s; each Command Center +1/s.
- **Build menu** (right-hand side): by default it lists everything the Command Center offers:
  every building, and Engineers. Select a Barracks or Vehicle Yard and it lists what that
  factory trains instead. Click an entry or press its number (**1-9**). Click the Command Center
  picture at the top to jump to your base.
- **Placing a building** lays its foundation straight away (and pays for it). The closest idle
  engineer walks over and builds it. If none is idle, the next engineer to finish their job
  picks it up. Right-click a foundation with more engineers to speed it up. A site shows red if
  it's within a tile of another building.
- **Command Center** trains **Engineers**, who build, repair buildings and vehicles, and capture.
- **Barracks** trains **Riflemen**, **Medics** (heal infantry they touch) and **Heavy Infantry** (armoured heavy weapons team).
- **Vehicle Yard** builds **Jeeps** (fast, mounted weapon) and **Tanks** (armoured, big gun). Their weapons sit in turrets that traverse independently of the hull.

### Unit design

Select a production building and press **E** to open the design popup. Each unit type has
three module slots, and every choice has a trade-off:

| Slot | Light / Slow | Medium / Normal (default) | Heavy / Fast |
| --- | --- | --- | --- |
| Armor | Less HP, faster, cheaper | Standard | More HP and armor, slower, pricier |
| Weapon | Weaker, faster firing, cheaper | Standard | Hits harder, reaches further, slow to reload and carry |
| Speed | Slower but tougher, cheaper | Standard | Much faster but fragile, pricier |

Some units' weapon tiers are real, distinct weapons:

| Unit | Light | Medium (default) | Heavy |
| --- | --- | --- | --- |
| Rifleman | Pistol | Rifle | Machine gun |
| Heavy Infantry | M60 | Grenade launcher | Shoulder rocket launcher |
| Jeep | M2 Browning | UAG-40 automatic grenade launcher | Twin wire-guided missiles |
| Tank | Bushmaster II 30mm autocannon | 120mm cannon | 155mm artillery (fixed gun: the tank turns to aim) |

For medics and engineers the weapon slot is the bag they carry: satchel, kit case or backpack.
Heavy infantry armour runs from helmet and body armour (Light) to full body armour (Medium) to
full body armour plus a ballistic shield (Heavy). Heavy infantry kneel before they fire.

Units are trained with the design that was current when you queued them, and look the part:

- **Infantry armour:** Light = no helmet or body armour (a team bandana on the arm), Medium =
  helmet and body armour, Heavy = adds shoulder, elbow and knee plates.
- **Vehicle armour:** more plating, same size.
- **Vehicle speed:** Fast = wheels, Normal = half-tracks, Slow = full tracks. Front wheels steer into turns.
- **Markings:** medics carry red crosses on white patches, engineers yellow and grey shoulder patches.

### High ground

The desert has two levels. Plateaus rise out of the rocky rim around the map, edged by cliffs
you can't climb. Each one is reached by one or two ramps. Units below can't see up onto a
plateau, so they can't shoot anything up there unless a friendly unit on top spots it. Units on
top see and shoot down as normal. Some derricks sit on high ground.

### Weapons and armour

Every weapon is one of three types:

| Type | Weapons | Behaviour |
| --- | --- | --- |
| Bullets | Pistol, rifle, M60, M2 | Instant hits. Every round pins down the soldier it's aimed at. Moderate damage to jeeps, weak against tanks and buildings. |
| Explosives | Grenade launcher, UAG-40, Bushmaster, 155mm | Splash damage. Pins down all infantry near the blast. Heavy damage to tanks and buildings. |
| Anti-armour | Rocket launcher, TOW, 120mm | Big hits with a bonus against vehicles, and a small blast. |

Armour ranks cut the damage each type does. Infantry go from unarmoured, to helmet and vest, to
full body armour, to full body armour plus a ballistic shield. The shield stops about half of
all bullets and explosive damage. Heavy infantry always wear one rank more than their tier
name. Armoured infantry lying prone also shrug off a good part of any explosion. Vehicles have
light, medium or heavy plating. The design screen lists each armour tier's damage cuts.

Tank guns reload slowest of all. The Bushmaster fires fast 10-round bursts that wear a tank
down slowly, but several of them together take one apart.

### Bunkers and Towers

Right-click either with infantry to man it. Soldiers inside fire out with the structure's bonuses
while it takes the hits. You can see them in the windows, scanning the area. If it falls, the
garrison is thrown clear.

| | Holds | Garrison bonus |
| --- | --- | --- |
| Bunker (2x2) | 4 | 25% faster reloads, +10% damage and range, slow healing |
| Tower (1x1) | 2 | +35% range, and the tower sees much further while manned. No healing. |

### Suppression

Infantry under heavy fire, especially machine guns or nearby explosions, get pinned down. They
go prone and crawl at 60% speed, shooting less accurately and at 60% range, but they are only
half as likely to be hit. Pinned soldiers automatically crawl a few tiles directly away from
whatever is pinning them, then carry on with their orders. A direct move order overrides this.
While pinned they won't crawl towards enemies who are out of reach.

Medics and engineers have to be touching whoever or whatever they heal, repair or build.

### Test range and motion test

- **T** on the title screen: a sandbox with no AI, no fog, plenty of credits, a starter army, a
  Command Center, Barracks, Vehicle Yard, Bunker and Tower (building and training are 10x faster than normal),
  and passive enemy targets of every type and loadout. **F5** respawns the targets.
- **M** on the title screen: the sprite motion test. Every unit loops through turning, moving,
  attacking, pinned-down and dying animations. **1/2/3** cycle the Armor, Weapon and Speed tiers,
  **Tab** switches team, **Space** pauses.

### Controls

| Input | Action |
| --- | --- |
| Left click / drag | Select units (drag for a box) |
| Shift + click | Add/remove from selection |
| Double click, Ctrl + click | Select all units of that type on screen |
| Right click | Smart command: move, attack, capture a derrick, heal (medic), build/repair (engineer). With a building selected: set rally point |
| `1`-`9` | Build menu: place a building or train a unit (Shift+click places several) |
| `Q` then click | Attack (click an enemy) or attack-move (click ground) |
| `M` / `X` | Move / Stop |
| Engineer: `R` | Repair |
| Bunker / Tower: `U` | Unload the garrison (right-click one with infantry to man it) |
| Factory: `E` | Unit design popup |
| Building under construction: `X` | Cancel (refunds) |
| Click a queue slot | Cancel training (refunds). Factories queue up to 15. |
| Ctrl + 1-9, Shift + 1-9 | Assign / recall control group (recall twice to jump the camera) |
| `W` `A` `S` `D`, arrow keys, screen edges, middle-drag, minimap | Move camera |
| Command Center picture (top of the build menu) | Jump to your Command Center |
| Space | Jump to your base |
| F1 | Controls overlay |
| F11 | Toggle fullscreen |
| Esc | Cancel current command / pause menu |

## Code layout

| File | Purpose |
| --- | --- |
| `pixelfront/config.py` | Resolution, economy, suppression, building stats |
| `pixelfront/units/` | One file per unit type (`rifleman.py`, `tank.py`, ...) with its stats, weapon tiers and special tiers. `registry.py` lists them; `unit.py` is the shared `Unit` behaviour (orders, movement, combat, suppression and retreating) |
| `pixelfront/weapons.py` | Every weapon, the three weapon types, armour ranks, projectiles, and how firing, splash and suppression work |
| `pixelfront/modules.py` | Loadout slots and tiers, and the stats/cost they produce |
| `pixelfront/world.py` | Tile map (with ground levels) and the symmetric desert map generator: plateaus, cliffs, ramps |
| `pixelfront/fog.py` | Vision (including high ground) and the player's fog of war |
| `tests/` | Map generator tests |
| `pixelfront/pathfinding.py` | A* on the tile grid |
| `pixelfront/entities.py` | Entity base class, buildings (incl. bunker garrison fire), capture points |
| `pixelfront/game.py` | Simulation: economy, capturing, combat, construction, win check, test range |
| `pixelfront/ai.py` | Computer opponent |
| `pixelfront/model3d.py` | Units and buildings as small 3D models (per loadout and pose) and the renderer that turns them into pixel art |
| `pixelfront/sprites.py` | Unit frames per facing and animation, building images per construction stage (rendered on demand, cached), icons, terrain |
| `pixelfront/render.py`, `hud.py`, `design.py` | Map view (incl. flags and garrison animations), control panel and build sidebar, design popup |
| `pixelfront/motiontest.py` | Sprite motion test scene |
| `pixelfront/controller.py` | Mouse/keyboard to orders |
| `pixelfront/app.py` | Window, main loop, title/pause/design/game-over screens |
| `pixelfront/log.py` | Per-run log files and crash logging |

### Adding a weapon

1. Add it to `WEAPONS` in `weapons.py` with a `type` (`bullet`, `explosive` or `anti_armor`) and
   its numbers. Anything you leave out comes from the type's defaults.
2. Put its id in a unit's `weapons` list (`units/<kind>.py`).
3. Give it a look in `model3d.py`: models pick their gun by weapon id.

### Adding a unit

1. Write `units/<kind>.py` with a `UNIT` dict. Copy the closest existing unit.
2. Add it to `UNITS` in `units/registry.py` and to a building's `trains` list in `config.py`.
3. Give it a model in `model3d.py`.

### Adding a new module slot

1. Add the slot and its tiers to `SLOTS` in `modules.py` (stats it changes must be in `STAT_NAMES`).
2. Optionally give some units their own tiers via `tiers` in their unit file.
3. Optionally give it a look: read the slot's tier from the loadout in `soldier()`, `jeep()` or
   `tank()` in `model3d.py` and add boxes for it. Check it in the motion test (M).

The design screen, costs, AI and stats pick it up automatically.
