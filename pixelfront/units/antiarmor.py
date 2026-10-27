"""Anti-armour infantry: grenadiers and missile teams who kneel to fire."""

UNIT = dict(
    name="Anti-Armor", cls="infantry", desc="Grenades and missiles to crack armour.",
    hp=50, armor=0, speed=36, sight=6,
    cost=100, time=11, supply=1, radius=4, height=13,
    kneels=True,   # must kneel before firing
    weapons=[
        dict(weapon="rifle_ugl", mul={"speed": 1.05}, cost=-0.2, time=-0.1),
        dict(weapon="agl6"),
        dict(weapon="javelin", mul={"speed": 0.88}, cost=0.5, time=0.3),
    ],
)
