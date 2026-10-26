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

## Logs

Every run writes a log to `logs\YYYYMMDD_HHMMSS.log` (next to `Pixelfront.exe`, or in the project
folder when running from source); the newest 50 are kept. Set `PIXELFRONT_DEBUG=1` before
launching for extra detail such as individual orders.

## How to play

Destroy every enemy building to win. Lose all of yours and it's over.

- **Income** comes from **oil derricks** scattered across the desert. Park units next to one
  to capture it (more units capture faster, up to 3). An enemy-owned derrick has to be
  neutralized before you can take it. Each derrick pays +2 credits/s; each Command Center +1/s.
- **Command Center** trains **Engineers**, who build, repair buildings and vehicles, and capture.
- **Barracks** trains **Riflemen**, **Medics** (heal infantry they touch) and **Heavy Infantry** (armoured heavy weapons team).
- **Vehicle Yard** builds **Jeeps** (fast, mounted weapon) and **Tanks** (armoured, big gun). Their weapons sit in turrets that traverse independently of the hull.

### Unit design

Select a production building and press **D** to open the design screen. Each unit type has
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

### Bunkers

Engineers can build Bunkers. Right-click one with infantry to man it (up to 4). Soldiers inside
fire from it with 25% faster reloads and +10% damage and range, and slowly heal, while the bunker takes the hits.
If it falls, the garrison is thrown clear.

### Suppression

Infantry under heavy fire, especially machine guns or nearby explosions, get pinned down. They
go prone and crawl at 60% speed, shooting less accurately and at 60% range, but they are only half as likely to be hit. Medics and
engineers have to be touching whoever or whatever they heal, repair or build.

### Test range and motion test

- **T** on the title screen: a sandbox with no AI, no fog, plenty of credits, a starter army, a
  Command Center, Barracks and Vehicle Yard to train from (building and training are 10x faster),
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
| `A` then click | Attack (click an enemy) or attack-move (click ground) |
| `M` / `S` | Move / Stop |
| Engineer: `R`, `C` / `B` / `Y` / `K` | Repair; build Command Center / Barracks / Vehicle Yard / Bunker (Shift+click to place several; other selected engineers help build) |
| Bunker: `U` | Unload the garrison (right-click a bunker with infantry to man it) |
| Command Center: `E` | Train Engineer |
| Barracks: `R` / `M` / `H` | Train Rifleman / Medic / Heavy Infantry |
| Yard: `J` / `T` | Build Jeep / Tank |
| Factory: `D` | Unit design screen |
| Click a queue slot | Cancel training (refunds) |
| Ctrl + 1-9, 1-9 | Assign / recall control group (press twice to jump the camera) |
| Arrow keys, screen edges, middle-drag, minimap | Move camera |
| Space | Jump to your base |
| F1 | Controls overlay |
| F11 | Toggle fullscreen |
| Esc | Cancel current command / pause menu |

## Code layout

| File | Purpose |
| --- | --- |
| `pixelfront/config.py` | Resolution, economy, unit and building base stats |
| `pixelfront/modules.py` | Loadout slots and tiers, and the stats/cost they produce |
| `pixelfront/world.py` | Tile map and symmetric desert map generator |
| `pixelfront/pathfinding.py` | A* on the tile grid |
| `pixelfront/entities.py` | Units (order state machine), buildings, capture points, projectiles |
| `pixelfront/game.py` | Simulation: economy, capturing, combat, construction, win check, test range |
| `pixelfront/ai.py` | Computer opponent |
| `pixelfront/fog.py` | Fog of war |
| `pixelfront/model3d.py` | Units and buildings as small 3D models (per loadout and pose) and the renderer that turns them into pixel art |
| `pixelfront/sprites.py` | Unit frames per facing and animation, building images per construction stage (rendered on demand, cached), icons, terrain |
| `pixelfront/render.py`, `hud.py`, `design.py` | Map view, control panel, design screen |
| `pixelfront/motiontest.py` | Sprite motion test scene |
| `pixelfront/controller.py` | Mouse/keyboard to orders |
| `pixelfront/app.py` | Window, main loop, title/pause/design/game-over screens |
| `pixelfront/log.py` | Per-run log files and crash logging |

### Adding a new module slot

1. Add the slot and its tiers to `SLOTS` in `modules.py` (stats it changes must be in `STAT_NAMES`).
2. Optionally give some units their own tiers via `UNIT_TIERS`.
3. Optionally give it a look: read the slot's tier from the loadout in `soldier()`, `jeep()` or
   `tank()` in `model3d.py` and add boxes for it. Check it in the motion test (M).

The design screen, costs, AI and stats pick it up automatically.
