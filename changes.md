# Changes

All notable changes to Pixelfront are listed here, newest first. Each entry has a version number and a name.

## 0.14.0 "Dig In" (2026-10-27)

A new anti-armour soldier, a tank gun that has to dig in before it fires, bullets that spray,
and infantry that step around each other.

### Added

- **Anti-Armor infantry**, trained at the Barracks. They kneel to fire. Weapon tiers:
  - Light: a rifle with an underbarrel grenade launcher. It fires the rifle, and lobs a
    grenade whenever the launcher's 9-second reload allows.
  - Medium: a 6-round automatic grenade launcher. Bursts of 6 grenades, then a long reload.
  - Heavy: the Javelin. The missile arcs up and dives onto its target, steering after it as it
    moves. It wrecks vehicles but is weak against soldiers, and Javelin teams pick vehicles
    first.
  - The soldiers wear orange shoulder patches with a black bar and carry spare rounds on their
    back. They also appear on the test range, the title screen and the motion test, and the
    computer opponent trains them.
- **Firing a second weapon:** a weapon can carry a second one (the underbarrel launcher) with
  its own damage, range and reload.

### Changed

- **The tank's 155mm is now a self-propelled gun that must deploy:**
  - It has an open-topped gun house with a sloped front shield, a long barrel with a muzzle
    brake and recuperators, a rack of ready rounds and a gunner's seat, instead of a turret.
  - While travelling, the barrel rests on a travel lock on the front deck and the spades are
    folded against the back.
  - To fire, it turns to face the target, then spends 2 seconds deploying: spades drop and dig
    in at the rear, jacks push pads down at the sides, the travel lock folds flat and the barrel
    rises to firing angle.
  - Dug in, it can only fire within 10° of where it points. It packs up (2 seconds) before it
    can turn further or drive off, and does so on its own when ordered to move.
  - Its status reads Deploying, Deployed, Firing (deployed) or Packing up. Dug in and idle, it
    slowly raises and lowers its barrel.
- **Bullets spray instead of streaming.** Each round is now a short streak with a fading tail
  that flies along its own line. Misses scatter in a cone that widens with range and
  inaccuracy, and carry on past the target. Machine-gun bursts fan out.
- **Infantry walk around soldiers who are standing still.** Instead of pushing through, a
  soldier on the move steers round anyone in the way. On contact, the walker takes all of the
  push, so standing soldiers stay put.
- The motion test fits seven rows: infantry are shown at 3× instead of 4×.

## 0.13.0 "Close Order" (2026-10-27)

Groups that move as one, with vehicles in front, plus clearer click feedback and per-factory designs.

### Changed

- **Each factory has its own unit designs.** Changing a unit's loadout in one Barracks or Vehicle
  Yard no longer changes it in the others; new factories start on the defaults.
  - The build menu shows the design of the factory the order will go to. That's the selected
    one, or the least busy one if none is selected.
  - The computer opponent varies its designs per factory too.
- **Groups move at the pace of the slowest unit**, so they stay together. Units with further to
  go speed up just enough to arrive with the rest.
- **Vehicles lead the group.** Soldiers wait for any vehicle behind them to roll past (for up to
  6 seconds), and vehicles take the front spots where the group stops.
- **Medics and engineers hang back.** They take the back of the formation. On an attack or
  attack-move they follow the nearest fighter instead of running ahead to the target. Medics
  stop to heal the wounded along the way.
- **Shift-click in a mixed selection** on one of the selected units keeps only units of that
  type. This works on the map and on the selection icons. In a selection of one type,
  shift-click still removes the unit.

### Added

- **Click ring:** move and attack clicks show a ring that snaps in on the spot while a fainter
  ripple spreads out and fades, instead of the old shrinking box.
- **Building acknowledgement:** right-clicking a building or derrick with units selected (to
  attack, repair, build, man or capture it) makes it flash once, softly.

### Fixed

- Units in a tight crowd could stall on their path, each blocking the others from reaching
  the same tile. A unit already on a waypoint's tile now heads straight for the next one.

## 0.12.0 "Fine Grain" (2026-10-27)

Twice the pixel detail, and redesigned units and buildings to make use of it.

### Changed

- **Double pixel density.** The game world is now drawn at 1280×720 instead of 640×360: an exact 2× on a 2560×1440 screen.
  - Units, buildings, terrain, cliffs, flags, garrison heads and effects all use the finer pixels.
  - The HUD, sidebar and text keep their size and chunky look. The unit and building pictures inside them (sidebar icons, portraits, design previews) use the new detail.
  - On a 1920×1080 screen the window scales by 1.5×, so pixels come out slightly uneven.
- **Slimmer health bars** over units and buildings, to suit the finer art.

### Added

- **Round wheels and tracks:**
  - Wheels are round tyres with a rim, hub, wheel nuts and tread grooves that turn as they roll.
  - Track runs have rounded ends, with links that crawl around them, round road wheels, a drive sprocket and an idler.
  - Barrels, launch tubes and the jeep's spare wheel are round too, and half-tracks have curved mudguards.
- **More detailed infantry:**
  - Rounded limbs and heads, with faces (eyes, brows, nose, mouth, ears).
  - Domed helmets with goggles and chin straps.
  - Plate carriers with magazine pouches, a radio and straps; webbing for unarmoured soldiers; belts, buckles and canteens.
  - Boots with soles and laces, cargo pockets, knee and elbow pads, and gloves.
  - Weapons rebuilt with stocks, grips, magazines, optics and round barrels. The M60 gets an ammo belt and bipod, and the rocket launcher is a proper tube.
- **Detail lines on buildings:** every building and vehicle has fine dark edge lines.
  - The Vehicle Yard has an arched, corrugated roof with seams and team trim, grooved wall cladding, a framed roller door and a lattice crane.
  - The Command Center has panel seams and window and door frames; the barracks have pour lines.
- **Smoother terrain:** cliff edges, dune patches and the rocky base pads have smooth, pixel-fine outlines instead of following the tiles. Ramps are single contoured shapes with a slope, treads and a spill of sand at the foot.

### Fixed

- The title screen's list of controls no longer runs off the right edge.

## 0.11.0 "High Ground" (2026-10-26)

Cliffs that matter: plateaus with ramps, contoured rock, height-based vision and livelier idle units.

### Added

- **High ground**:
  - The map now has two levels.
  - Plateaus always grow out of the rocky rim around the map, so no cliff stands on its own.
  - Each plateau is edged by impassable cliff and reached by one or two ramps.
- **Ramps** are 3 tiles wide and cut square into a straight stretch of cliff wall. They're drawn as a slope with treads, wandering sides and a spill of sand at the foot.
- **Height-based vision**:
  - Units on low ground can't see onto a plateau, and can't target anything up there unless a friendly unit on top spots it.
  - Units on high ground see and shoot down as normal.
  - This applies to both sides.
- **Contoured cliffs**:
  - Cliff edges are drawn at quarter-tile detail with rounded, irregular outlines.
  - South faces show rock strata and striations; other faces show sunlit rubble.
  - Plateau tops have their own rock texture with a highlight lip, and cliffs cast shadows.
  - High ground shows up on the minimap.
- **Map generator tests** (`python -m unittest discover tests`) check 60 maps each for reachability, blocking terrain, lone cliffs, ramp alignment, ramps onto every plateau and symmetry.
- **Idle animations**:
  - Idle tanks and jeeps sweep their turrets to random bearings and pause.
  - The fixed 155mm raises and lowers its barrel instead.
  - Idle soldiers turn to look around every few seconds, and now and then check their weapon (medics and engineers go through their kit).

### Changed

- The generator rejects any map where some open ground can't be reached (it used to allow 2%). Low-ground pockets walled in by plateaus are filled in.

## 0.10.0 "Watchtower" (2026-10-26)

A C&C-style build sidebar, a new Tower, instant foundations and a smaller designer.

### Added

- **Build sidebar** on the right of the map:
  - A detailed picture of the Command Center sits at the top. Click it to jump to your Command Center.
  - Below it is a numbered list. By default it shows everything the Command Center offers: every building, and Engineers.
  - Select a Barracks or Vehicle Yard and the list shows what that factory trains, with queue counts and training progress.
  - Press **1-9** to pick an entry.
- **Instant foundations.** Placing a building lays its foundation (and pays for it) right away. The closest idle engineer then goes to build it. Unattended foundations are picked up by the next engineer to go idle.
- **Tower**, a tall concrete guard tower on a single tile:
  - Holds 2 infantry.
  - The garrison fires at +35% range, and the tower's sight rises from 5 to 11 tiles while manned.
  - Soldiers inside don't heal.
  - It's in the build menu, and the test range has one.
- **Garrison animations.** Bunkers and Towers show one head per soldier inside, each scanning the surroundings.
- **Waving flags** on every building, and on derricks.
- **Bullet spread.** Rounds fan out a little, and their dashed trails drift slightly instead of running dead straight.

### Changed

- **Controls**:
  - **WASD** scrolls the camera (as well as the arrow keys).
  - Attack is now **Q**, Stop **X**, and Design **E**.
  - Control groups are assigned with **Ctrl + 1-9** (unchanged) and recalled with **Shift + 1-9**.
  - The old letter hotkeys for building and training are gone; use the numbered sidebar instead.
- The radar in the top-right corner is gone. The minimap stays at the bottom left.
- The unit designer is now a popup about half the size of the old full-screen panel. Every number is still shown at the same size.
- Factories can queue up to 15 units (was 5).

### Fixed

- Units inside a Bunker or Tower can no longer be targeted. Medics used to keep "healing" a soldier who had gone inside, and enemies could keep shooting at them.

## 0.9.0 "Hit the Dirt" (2026-10-26)

A large refactor, plus weapon types, armour ranks and smarter suppression. Also a gentler AI and freer building placement.

### Changed: code layout

- Each unit type now has its own file in `pixelfront/units/` (stats, weapon tiers, special tiers). `units/unit.py` holds the shared behaviour.
- Every weapon lives in `pixelfront/weapons.py`. That file also holds the three weapon types, armour ranks, projectiles, and how firing, splash and suppression work. See the README for how to add a weapon or a unit.
- Models choose their guns by weapon id, so a new weapon only needs a model, not new tier logic.

### Added

- **Weapon types**:
  - Bullets: moderate damage against jeeps, weak against tanks and buildings.
  - Explosives: heavy damage against tanks and buildings.
  - Anti-armour: big hits, with a bonus against vehicles.
- **Explosives cause suppression.** Every blast pins down nearby infantry on both sides.
- **Pinned soldiers retreat.** Suppressed infantry crawl a few tiles directly away from whatever is pinning them, then carry on with their orders. A direct move order overrides this.
- **Pinned soldiers hold position.** They no longer crawl towards enemies out of reach. They shoot anyone in range or keep their heads down.
- **Armour ranks**:
  - Infantry: unarmoured, helmet + vest, full body, and full body + shield. Heavier armour stops more bullets and explosive damage.
  - The ballistic shield stops about half of all bullets and explosive damage.
  - Heavy infantry always wear one rank more than their tier name.
  - Armoured infantry lying prone take much less from explosions.
  - Vehicles have light, medium or heavy plating.
  - The rank is shown on the selected unit, and the design screen lists each armour tier's damage cuts.
- Bullet trails are now dashed (`- - - -`) instead of solid lines.

### Balance

- The Bushmaster fires fast 10-round bursts of light rounds, then reloads. One wears a tank down slowly, and several take it apart quickly. Measured time to kill a tank: 1 Bushmaster ~34 s, 2 ~16 s, 3 ~10 s.
- Tanks now have the slowest reloads of any unit: Bushmaster 3.0 s, 120mm 3.5 s, 155mm 5.0 s. To make up for this, the 120mm now does 50 damage and the 155mm 55.
- Building and training take twice as long. The test range is still 10x faster than normal.
- The AI is easier and a bit dimmer:
  - It thinks every 2.5 s instead of every second.
  - Its first attack comes at 5:00, with smaller waves that grow more slowly.
  - Its factories dawdle, and it keeps 2 engineers instead of 3.
  - Only nearby units notice an attack on its base, and only some of them react.
  - Some attack waves wander off to a random target.

### Fixed / improved

- Buildings snap to single tiles instead of a coarse 4-tile grid. The placement preview turns red when the site is too close to another building.

## 0.8.0 "Paper Trail" (2026-10-26)

Every run now writes a log file.

### Added

- Logging. Each run writes `logs/YYYYMMDD_HHMMSS.log`, named year first so the files sort in order. The folder sits next to `Pixelfront.exe`, or in the project folder when running from source. The newest 50 logs are kept.
- What gets logged:
  - Startup: version, Python, pygame and display details.
  - Screen changes and fullscreen toggles.
  - Each match's seed and mode, and the result with the player's remaining forces.
  - Units queued and ready, with their loadouts.
  - Buildings placed, started, completed, cancelled and destroyed.
  - Units killed, and by whom.
  - Derricks captured and neutralised.
  - Bunkers manned and emptied.
  - Unit design changes.
  - AI decisions: what it builds, attack waves with their makeup, base defence starting and ending.
  - Slow frames, and any crash with its full traceback.
- Set the environment variable `PIXELFRONT_DEBUG=1` for extra detail: player orders, control groups, AI capture assignments and redesigns, soldiers getting pinned down.
- The game now reports its version (0.8.0).

## 0.7.0 "Hold the Line" (2026-10-26)

Bunkers to man, engineers who work together, idle animations and a set of fixes.

### Added

- Bunker: a 2×2 concrete pillbox that engineers can build (K). Right-click it with infantry to man it, up to 4 soldiers. While inside, each soldier fires from the bunker with 25% faster reloads and +10% damage and range, and slowly heals (1 HP per second, always slower than a medic). Helmets show in the firing slits when it's manned. The bunker takes the hits; if it's destroyed, the garrison scrambles out. Select it and press U to unload. The test range now starts with one.
- Several engineers can build together: place a building with more than one engineer selected and the nearest one lays the foundation while the rest go and help. Several engineers can also repair or construct the same building.
- Tooltips on build and train buttons show the build time.
- Idle animations: soldiers breathe (a slight rise and fall of the upper body, out of step with each other), and vehicles shake gently with the engine running.

### Changed

- Heavier weapon tiers never reload faster than lighter ones. The rifleman's machine gun, which had been reloading faster than the rifle, now fires bursts of 4 rounds per reload instead. The heavy infantry's M60 works the same way. A check flags any unit whose weapon tiers break this rule.
- Design screen stats include Burst for machine guns.
- Test range targets now stand well away from your base (about 12–15 tiles), so nothing fires until you send units in. The riflemen are packed together as a squad, for testing splash weapons and suppression; the other targets are spread two tiles apart.

### Fixed

- Oil derricks no longer jitter: every pump frame is drawn on the same canvas, so only the beam and horse head move.

## 0.6.0 "Radar & Rumble" (2026-10-26)

A radar, base layout on a grid, steering vehicles that infantry make way for, and clearer unit markings.

### Added

- Radar in the top-right corner: the map in radar green with a grid and a rotating sweep. It shows fog of war, your units as green blips and visible enemies as pulsing red blips, plus buildings and derricks. Click or drag on it to move the camera; right-click to issue orders there.
- Buildings snap to an invisible 4-tile grid and must keep a tile of clearance from other structures, leaving lanes for infantry and vehicles. The AI follows the same rules.
- Vehicles turn their hull at a realistic rate instead of snapping round, and front wheels steer into the turn. On half-tracks the steering wheels are bigger, with a light rim and a mudguard. The 155mm artillery tank now has to swing round before it can fire.
- Infantry get out of the way of moving vehicles: they step aside before the vehicle reaches them and are pushed clear rather than blocking it.
- Oil derricks pump continuously, and the owner's flag flies on a pole centred above the pump.
- Buildings cast a ground shadow and have a weathered surface texture.
- The sprite motion test shows vehicles driving in a circle with their wheels steered.

### Changed

- Light-armour infantry wear team bandanas on both arms.
- Medics: the red crosses sit on white patches, and both shoulders carry a white patch with a red centre.
- Engineers always have yellow and light-grey patches on top of both shoulders.
- The Barracks is smaller: a 2×2 building.
- The test range builds and trains 10 times faster.
- Prone soldiers are harder to hit (half the chance) instead of taking reduced bullet damage.
- Prone soldiers crawl at 60% speed (40% slower), up from 35%.

## 0.5.0 "Heavy Metal" (2026-10-26)

Real weapons for heavy infantry, jeeps and tanks, turrets that traverse, and new firing stances.

### Added

- Heavy infantry weapon tiers: Light = M60 machine gun, Medium = M32-style grenade launcher, Heavy = shoulder rocket launcher.
- Jeep weapon tiers: Light = M2 Browning heavy machine gun, Medium = UAG-40 automatic grenade launcher, Heavy = twin wire-guided missile launchers.
- Tank weapon tiers: Light = Bushmaster II 30mm autocannon, Medium = 120mm cannon, Heavy = 155mm artillery.
- Each weapon has its own model, matched to the real weapon as closely as the pixel size allows:
  - M2: perforated barrel jacket and spade grips.
  - UAG-40: chunky receiver, short fat barrel, linked grenades feeding in.
  - Missile launchers: twin tubes on a guidance sight.
  - Bushmaster: slim barrel with muzzle brake and ammo feed.
  - 120mm: fume extractor and thermal sleeve.
  - 155mm: long raised barrel, double-baffle muzzle brake, recuperators, turret bustle.
- New projectile types:
  - Lobbed grenades and artillery shells that arc, cast a ground shadow and burst over an area.
  - Fast autocannon rounds.
  - Wire-guided missiles that trail their guidance wire back to the launcher.
- Turrets: tank turrets and the jeep's rear weapon station (gunner included) traverse to aim independently of the hull. The 155mm artillery is a fixed gun, so the whole tank turns to aim.
- Heavy infantry must kneel before firing; they stand up again to move.
- Infantry fire while pinned down, prone, at 60% range.
- Light-armour infantry wear a team-coloured bandana knotted round the left arm, so they still show their side.
- Sprite motion test: vehicle rows show the turret traversing (the 155mm is labelled as a fixed gun), and heavy infantry kneel before firing.

### Changed

- Heavy infantry armour tiers all carry more plating: Light = helmet and body armour, Medium = full body armour, Heavy = full body armour plus a ballistic shield.
- The design screen shows units smaller, standing on a patch of the actual map near the building.
- Heavy infantry, jeeps and tanks now default to the grenade launcher, UAG-40 and 120mm respectively.

## 0.4.0 "Joints & Foundations" (2026-10-26)

Buildings join units in the pre-rendered 3D style, infantry shrink to C&C proportions, and soldiers move with real joints.

### Added

- 3D-modelled buildings: Command Center (radar dome, dish, beacon mast, lit windows), Barracks (bunker with firing slits, sandbags, flag), Vehicle Yard (arched hangar, hazard-striped door, crane) and oil derricks (pump jack). Each covers exactly its tiles, and buildings under construction rise in stages inside yellow scaffolding.
- Elbows and knees: infantry arms and legs bend at the joints when walking, aiming, firing, working and dying.
- Pinned-down crab crawl: suppressed soldiers splay their arms and legs out to the sides, bent at the elbows and knees, and alternate them as they crawl.
- More vehicle detail:
  - Tanks: road wheels, sprockets and idlers on the tracks, engine-deck grille, stowage bins, tow cable, commander's cupola with periscopes, gunner's sight, smoke launchers, antenna, rear basket, team band.
  - Jeeps: grille slats, door seams and handles, mirrors, steering wheel, seat backs, spare wheel, radio antenna.
- The test range now starts with a Barracks and a Vehicle Yard next to the Command Center, so every unit type can be trained there.

### Changed

- Infantry are about half their previous size (around 8×13px). They're rendered supersampled for rounder silhouettes and softer shading.
- The sprite motion test shows infantry rows at 4x zoom and vehicle rows at 2x.

## 0.3.0 "Iron & Plate" (2026-10-26)

Units now have a pre-rendered 3D look in the style of Command & Conquer, and infantry can be pinned down.

### Added

- 3D-style unit sprites: every unit is a small 3D model rendered to pixel art with shading, light from the top-left and a dark outline. Nothing floats around the units; all gear is attached to the body.
- Real facing directions: 8 for infantry, 16 for vehicles. Units turn to face where they move and what they shoot.
- Frame animations:
  - Infantry: 4-frame walk, aim and recoil with muzzle flash, heal and repair poses, and a 4-frame fall backwards when killed.
  - Vehicles: rolling wheels and tracks, gun recoil with muzzle flash, exhaust flames when moving, and a wreck with the turret knocked askew.
- Suppression: infantry under heavy fire (machine guns especially, and nearby explosions) go prone and crawl on their bellies. While pinned they move at 35% speed, take half damage from bullets and shoot less accurately. They get up once the fire lets up.
- Sprite motion test (M on the title screen): every unit type loops through turning, moving, attacking, pinned-down and dying animations. Keys 1/2/3 cycle the Armor, Weapon and Speed tiers, Tab switches team, Space pauses.

### Changed

- Infantry armour adds plating without changing a soldier's size. Light: no helmet, no body armour. Medium: helmet and body armour. Heavy: helmet, body armour, plus shoulder, elbow and knee plates.
- Vehicle armour adds plating within the same footprint. Light shows a bare frame; Heavy adds skirts, bolt-on plates and a gun shield (jeep).
- Vehicle Speed slot sets the running gear: Fast = wheels, Normal = half-tracks, Slow = full tracks.
- Medics and engineers wear the same kit as other infantry, with a small red cross or yellow band. Their weapon slot is the bag they carry: Light = satchel, Medium = kit case in hand, Heavy = backpack. Medic kits are white with a red cross; engineer kits are yellow.
- Medics and engineers must be touching their patient or building to heal, repair or build.

## 0.2.0 "Desert Front" (2026-10-26)

The game is now futuristic desert warfare built around designing your own units.

### Added

- Unit design: every unit type has Armor, Weapon and Speed slots, each with three tiers (Light/Medium/Heavy or Slow/Normal/Fast). The middle tier is the default; the others trade one strength for another and change cost and build time. Select a production building and press D to open the design screen, which shows the resulting stats and cost.
- Rifleman weapons work like real guns: Light is a pistol (accurate, short range), Medium a rifle, Heavy a machine gun (lots of firepower, inaccurate, slows the gunner).
- Accuracy stat: shots can miss, and misses land near the target.
- Units look like their loadout: armour plating or lighter gear, pistols and machine guns, bigger medkits and tool packs, jetpacks, cargo, exhaust flames.
- Capture points: oil derricks across the map pay credits to whoever holds them. Units standing next to one capture it over time; enemy-held points must be neutralized first.
- Units: Engineer (builds, repairs, captures), Rifleman, Medic (heals infantry), Heavy Infantry (rockets, strong vs vehicles), Jeep, Tank.
- Buildings: Command Center, Barracks, Vehicle Yard.
- Desert map with dunes, rocky ground and impassable cliff mesas and ridges.
- Combat effects: bullet tracers, muzzle flashes, vehicle recoil, rockets with smoke trails, tank shells and explosions.
- Death animations: soldiers topple and fade; vehicles explode and leave smoking wrecks.
- Test range (T on the title screen): no AI, no fog, 5000 credits, a starter army and passive enemy targets of every unit and loadout. F5 respawns the targets.
- The enemy AI captures derricks, builds barracks and yards, varies its unit designs and attacks in growing waves.

### Changed

- Income now comes from derricks and Command Centers instead of mining gold.
- Supply is a flat cap of 50; vehicles use more supply than infantry.
- Rifleman machine gun accuracy raised from 50% to 65%.

### Removed

- Fantasy theme: workers, footmen, archers, town halls, farms and gold mines.

## 0.1.0 "First Light" (2026-10-26)

First playable version (MVP).

### Added

- Standalone Windows build: `build.ps1` packages the game into a single `dist\Pixelfront.exe` with PyInstaller.
- Pixel-art look with all art drawn in code (no asset files). The game renders at 640×360 and scales up with crisp pixels. F11 toggles fullscreen.
- Randomly generated two-player map that is the same from both sides, with forests, lakes and 8 gold mines.
- Economy: workers mine gold and return it to the Town Hall. Farms raise the supply cap (max 60).
- Buildings: Town Hall, Barracks, Farm. Buildings show construction progress, can be cancelled for a full refund, and catch fire when badly damaged.
- Units: Worker, Footman (melee) and Archer (ranged). Training queues hold up to 5 units, and rally points can be set on the ground or on a gold mine.
- A* pathfinding, group movement in formation, attack-move, and units that automatically fight back or engage enemies in range.
- Fog of war on the main view and the minimap.
- Computer opponent that grows its economy, builds farms and barracks, defends its base and attacks in growing waves.
- Controls:
  - Mouse: click, drag and Shift selection; double-click or Ctrl+click to select all of a type; context-sensitive right-click.
  - Keyboard: command hotkeys and control groups.
  - Camera: arrow keys, screen-edge scrolling, middle-mouse drag and minimap clicks.
- HUD with resource bar, messages, minimap, selection details, command buttons and tooltips.
- Title, pause, help (F1) and victory/defeat screens.
