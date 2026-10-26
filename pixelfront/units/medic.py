"""Medic: unarmed; heals infantry it touches. The weapon slot is the medical kit."""

UNIT = dict(
    name="Medic", cls="infantry", hotkey="m", desc="Heals infantry it touches.",
    hp=45, armor=0, speed=42, sight=6, heal=6, cooldown=1.0,   # heals `heal` hp every `cooldown` s
    cost=70, time=9, supply=1, radius=4, height=13,
    weapon=None,
    slot_labels={"weapon": "Medkit"},
    tiers={"weapon": [
        dict(name="Light", desc="Satchel: quick, small doses.",
             mul={"heal": 0.7, "cooldown": 0.8, "speed": 1.05}, cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Medical kit case: standard care."),
        dict(name="Heavy", desc="Medical backpack: big doses, heavy to carry.",
             mul={"heal": 1.7, "cooldown": 1.3, "speed": 0.85}, cost=0.5, time=0.3),
    ]},
)
