"""Unit loadouts: the core customisation mechanic.

Every unit is trained with one tier chosen per module slot. The middle tier is the unit's
baseline; tiers either side trade one strength for another. A tier changes stats with
multipliers (`mul`) and flat additions (`add`), and changes price and build time by a
fraction of the unit's base values.

Extending:
- New slot: add an entry to SLOTS (and to STAT_NAMES if it touches a new stat), plus a
  look in sprites.DECOR if it should be visible.
- Unit-specific behaviour for a slot: add its tier list to UNIT_TIERS (the rifleman's
  weapon tiers are a pistol, a rifle and a machine gun).
- Units get every slot unless their UNITS entry lists "slots"; "slot_labels" renames a
  slot for one unit (the medic's weapon slot is its "Medkit").
"""
from .config import UNITS

SLOTS = {
    "armor": dict(label="Armor", default=1, tiers=[
        dict(name="Light", desc="Less protection, quicker on its feet.",
             mul={"hp": 0.7, "speed": 1.15}, cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Standard protection."),
        dict(name="Heavy", desc="Thick plating. Slow and expensive.",
             mul={"hp": 1.6, "speed": 0.8}, add={"armor": 1}, cost=0.5, time=0.3),
    ]),
    "weapon": dict(label="Weapon", default=1, tiers=[
        dict(name="Light", desc="Lighter, faster-firing, weaker.",
             mul={"damage": 0.7, "heal": 0.7, "work": 0.7, "cooldown": 0.8, "speed": 1.05},
             cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Standard issue."),
        dict(name="Heavy", desc="Hits hard and reaches further. Slow to reload and carry.",
             mul={"damage": 1.7, "heal": 1.7, "work": 1.7, "range": 1.15, "cooldown": 1.3, "speed": 0.85},
             cost=0.5, time=0.3),
    ]),
    "engine": dict(label="Speed", default=1, tiers=[
        dict(name="Slow", desc="Extra kit: tougher but sluggish.",
             mul={"speed": 0.75, "hp": 1.2}, cost=-0.15, time=-0.1),
        dict(name="Normal", desc="Standard pace."),
        dict(name="Fast", desc="Stripped down for speed. More fragile.",
             mul={"speed": 1.4, "hp": 0.8}, cost=0.35, time=0.2),
    ]),
}

# (unit kind, slot) -> tier list replacing the slot's generic tiers for that unit.
UNIT_TIERS = {
    ("rifleman", "weapon"): [
        dict(name="Light", desc="Pistol: light damage, very accurate, short range.",
             mul={"damage": 0.6, "range": 0.6, "cooldown": 0.8, "speed": 1.08},
             add={"accuracy": 0.12}, cost=-0.2, time=-0.1),
        dict(name="Medium", desc="Rifle: all-purpose."),
        dict(name="Heavy", desc="Machine gun: huge firepower, inaccurate, heavy to carry.",
             mul={"damage": 0.8, "cooldown": 0.3, "range": 1.1, "speed": 0.72},
             add={"accuracy": -0.2}, cost=0.5, time=0.3),
    ],
}

# Stat key -> display name. Stats a unit doesn't have (base value 0) are hidden for it.
STAT_NAMES = {
    "hp": "HP", "armor": "Armor", "damage": "Damage", "heal": "Heal", "work": "Work rate",
    "range": "Range", "cooldown": "Reload", "accuracy": "Accuracy", "speed": "Speed",
    "sight": "Sight", "vs_vehicle": "Vs vehicles",
}
STAT_DEFAULTS = {"heal": 0, "work": 0, "vs_vehicle": 1.0, "accuracy": 0.85}
LOWER_IS_BETTER = {"cooldown"}


def slots_for(kind):
    return UNITS[kind].get("slots", list(SLOTS))


def slot_label(kind, slot):
    return UNITS[kind].get("slot_labels", {}).get(slot, SLOTS[slot]["label"])


def tiers(kind, slot):
    return UNIT_TIERS.get((kind, slot)) or SLOTS[slot]["tiers"]


def tier(kind, slot, level):
    return tiers(kind, slot)[level]


def default_loadout(kind):
    return {slot: SLOTS[slot]["default"] for slot in slots_for(kind)}


def base_stats(kind):
    base = UNITS[kind]
    st = {k: base.get(k, STAT_DEFAULTS.get(k, 0)) for k in STAT_NAMES}
    if not base.get("weapon"):
        st["accuracy"] = 0
    return st


def compute_stats(kind, loadout):
    st = base_stats(kind)
    for slot, level in loadout.items():
        t = tier(kind, slot, level)
        for k, v in t.get("mul", {}).items():
            st[k] *= v
        for k, v in t.get("add", {}).items():
            if k != "accuracy" or st[k]:
                st[k] += v
    if st["accuracy"]:
        st["accuracy"] = min(1.0, max(0.05, st["accuracy"]))
    return st


def loadout_cost(kind, loadout):
    extra = sum(tier(kind, s, lv).get("cost", 0) for s, lv in loadout.items())
    return int(round(UNITS[kind]["cost"] * max(0.3, 1 + extra) / 5) * 5)


def loadout_time(kind, loadout):
    extra = sum(tier(kind, s, lv).get("time", 0) for s, lv in loadout.items())
    return UNITS[kind]["time"] * max(0.3, 1 + extra)


def loadout_summary(kind, loadout):
    return "  ".join(f"{slot_label(kind, s)} {tier(kind, s, lv)['name']}" for s, lv in loadout.items())


def format_stat(key, value):
    if key == "accuracy":
        return f"{value * 100:.0f}%"
    if key == "range":
        return f"{value / 16:.1f}"
    if key == "cooldown":
        return f"{value:.2f}s"
    if key == "vs_vehicle":
        return f"x{value:.2f}"
    return f"{value:.0f}" if value >= 10 or key in ("hp", "armor", "speed") else f"{value:.1f}"


def tier_effects(kind, slot, level):
    """Human-readable effects of a tier on this unit, e.g. ['+60% HP', '-20% Speed']."""
    t = tier(kind, slot, level)
    base = base_stats(kind)
    out = []
    for k, v in t.get("mul", {}).items():
        if base[k]:
            out.append(f"{(v - 1) * 100:+.0f}% {STAT_NAMES[k]}")
    for k, v in t.get("add", {}).items():
        if base[k]:
            out.append(f"{v * 100:+.0f}% {STAT_NAMES[k]}" if k == "accuracy" else f"{v:+g} {STAT_NAMES[k]}")
    if t.get("cost"):
        out.append(f"{t['cost'] * 100:+.0f}% cost")
    return out
