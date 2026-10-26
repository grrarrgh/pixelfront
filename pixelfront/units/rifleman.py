"""Rifleman: the all-round infantryman."""

UNIT = dict(
    name="Rifleman", cls="infantry", hotkey="r", desc="All-round infantry.",
    hp=55, armor=0, speed=40, sight=6,
    cost=60, time=8, supply=1, radius=4, height=13,
    # Weapon tiers: Light, Medium (default), Heavy. Each entry is a weapon id (weapons.py) plus
    # what carrying it does to the soldier and the price.
    weapons=[
        dict(weapon="pistol", mul={"speed": 1.08}, cost=-0.2, time=-0.1),
        dict(weapon="rifle"),
        dict(weapon="m60", mul={"speed": 0.72}, cost=0.5, time=0.3),
    ],
)
