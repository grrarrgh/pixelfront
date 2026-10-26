"""Engineer: builds, repairs and captures. Carries a pistol; the weapon slot is the tool kit."""

UNIT = dict(
    name="Engineer", cls="infantry", desc="Builds, repairs and captures.",
    hp=40, armor=0, speed=38, sight=5, work=1.0,
    cost=75, time=9, supply=1, radius=4, height=13,
    weapon="pistol",
    slot_labels={"weapon": "Tools"},
    # The tools slot changes how fast the engineer builds and repairs, not the pistol.
    tiers={"weapon": [
        dict(name="Light", desc="Satchel of basic tools: slower work, lighter load.",
             mul={"work": 0.7, "speed": 1.05}, cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Tool case: standard work rate."),
        dict(name="Heavy", desc="Full tool backpack: much faster work, heavy to carry.",
             mul={"work": 1.7, "speed": 0.85}, cost=0.5, time=0.3),
    ]},
)
