"""Tank: heavy armour and a turret-mounted main gun."""

UNIT = dict(
    name="Tank", cls="vehicle", target_class="heavy_vehicle", desc="Heavy armour and a big gun.",
    hp=300, armor=4, speed=30, sight=7, hull_turn=140,
    cost=250, time=20, supply=3, radius=11, height=21,
    weapons=[
        dict(weapon="bushmaster", cost=-0.15, time=-0.1),
        dict(weapon="cannon_120"),
        dict(weapon="howitzer_155", mul={"speed": 0.85}, cost=0.6, time=0.4),
    ],
)
