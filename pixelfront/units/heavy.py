"""Heavy infantry: an armoured heavy-weapons team that kneels to fire."""

UNIT = dict(
    name="Heavy Infantry", cls="infantry", desc="Armoured heavy weapons team.",
    hp=80, armor=1, speed=32, sight=6,
    cost=110, time=12, supply=1, radius=4, height=13,
    kneels=True,   # must kneel before firing
    armor_rank=1,  # one rank more plating than the tier name: Light = helmet + vest, Heavy = shield
    weapons=[
        dict(weapon="m60", cost=-0.1, time=-0.1),
        dict(weapon="grenade_launcher"),
        dict(weapon="rocket_launcher", mul={"speed": 0.9}, cost=0.4, time=0.3),
    ],
    # Heavy infantry always carry more plating than other soldiers at the same tier.
    tiers={"armor": [
        dict(name="Light", desc="Helmet and body armour.", mul={"hp": 0.75, "speed": 1.1},
             cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Helmet and full body armour."),
        dict(name="Heavy", desc="Full body armour plus a ballistic shield.",
             mul={"hp": 1.6, "speed": 0.8}, add={"armor": 2}, cost=0.5, time=0.3),
    ]},
)
