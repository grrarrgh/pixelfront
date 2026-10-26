# Changes

All notable changes to Pixelfront are listed here, newest first. Each entry has a version number and a name.

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
