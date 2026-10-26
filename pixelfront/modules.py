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
        dict(name="Heavy", desc="Machine gun: long bursts of fire, inaccurate, heavy to carry.",
             mul={"damage": 0.8, "cooldown": 1.15, "range": 1.1, "speed": 0.72},
             set={"burst": 4}, add={"accuracy": -0.2}, cost=0.5, time=0.3),
    ],
    # Weapon tiers that swap the weapon itself use `set` (applied before any mul/add).
    ("heavy", "weapon"): [
        dict(name="Light", desc="M60 machine gun: bursts of fire that pin infantry down; weak vs armour.",
             set={"weapon": "bullet", "damage": 5, "cooldown": 1.0, "burst": 4, "range": 70, "accuracy": 0.6,
                  "vs_vehicle": 1.0}, cost=-0.1, time=-0.1),
        dict(name="Medium", desc="Grenade launcher: lobbed grenades that burst over a small area."),
        dict(name="Heavy", desc="Shoulder rocket launcher: slow to reload, devastating vs vehicles.",
             set={"weapon": "rocket", "damage": 24, "cooldown": 2.4, "range": 84, "accuracy": 0.9,
                  "vs_vehicle": 1.75}, mul={"speed": 0.9}, cost=0.4, time=0.3),
    ],
    ("heavy", "armor"): [
        dict(name="Light", desc="Helmet and body armour.", mul={"hp": 0.75, "speed": 1.1},
             cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Helmet and full body armour."),
        dict(name="Heavy", desc="Full body armour plus a ballistic shield.",
             mul={"hp": 1.6, "speed": 0.8}, add={"armor": 2}, cost=0.5, time=0.3),
    ],
    ("jeep", "weapon"): [
        dict(name="Light", desc="M2 Browning: heavy machine gun, fast and accurate.",
             set={"weapon": "bullet", "damage": 7, "cooldown": 0.3, "range": 76, "accuracy": 0.8},
             cost=-0.1, time=-0.1),
        dict(name="Medium", desc="UAG-40 automatic grenade launcher: bursts of splashing grenades."),
        dict(name="Heavy", desc="Twin wire-guided rockets: long range, deadly vs vehicles, slow to reload.",
             set={"weapon": "atgm", "damage": 32, "cooldown": 2.8, "range": 110, "accuracy": 0.95,
                  "vs_vehicle": 1.8}, cost=0.5, time=0.3),
    ],
    ("tank", "weapon"): [
        dict(name="Light", desc="Bushmaster II 30mm autocannon: rapid bursts, good vs infantry and light vehicles.",
             set={"weapon": "autocannon", "damage": 9, "cooldown": 0.35, "range": 84, "accuracy": 0.85,
                  "vs_vehicle": 1.2}, cost=-0.15, time=-0.1),
        dict(name="Medium", desc="120mm cannon: the all-round tank gun."),
        dict(name="Heavy", desc="155mm artillery: huge range and blast, slow and inaccurate.",
             set={"weapon": "artillery", "damage": 45, "cooldown": 4.0, "range": 160, "accuracy": 0.65,
                  "vs_vehicle": 1.0}, mul={"speed": 0.85}, cost=0.6, time=0.4),
    ],
}

# Stat key -> display name. Stats a unit doesn't have (base value 0) are hidden for it.
STAT_NAMES = {
    "hp": "HP", "armor": "Armor", "damage": "Damage", "heal": "Heal", "work": "Work rate",
    "range": "Range", "cooldown": "Reload", "burst": "Burst", "accuracy": "Accuracy", "speed": "Speed",
    "sight": "Sight", "vs_vehicle": "Vs vehicles",
}
STAT_DEFAULTS = {"heal": 0, "work": 0, "vs_vehicle": 1.0, "accuracy": 0.85, "burst": 1}
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
    st["weapon"] = base.get("weapon")
    return st


def compute_stats(kind, loadout):
    """Stats for a unit with this loadout, including "weapon" (the weapon type it fires)."""
    st = base_stats(kind)
    for slot, level in loadout.items():
        st.update(tier(kind, slot, level).get("set", {}))
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


def reload_order_problems():
    """Heavier weapon tiers must never reload faster than lighter ones. Returns a list of
    human-readable violations (empty when every unit's weapon tiers are in order)."""
    problems = []
    for kind in UNITS:
        if "weapon" not in slots_for(kind):
            continue
        prev = None
        for level, t in enumerate(tiers(kind, "weapon")):
            lo = dict(default_loadout(kind), weapon=level)
            reload_time = compute_stats(kind, lo)["cooldown"]
            if prev is not None and reload_time < prev[1] - 1e-9:
                problems.append(f"{kind}: {t['name']} reloads in {reload_time:.2f}s, "
                                f"faster than {prev[0]} ({prev[1]:.2f}s)")
            prev = (t["name"], reload_time)
    return problems


def format_stat(key, value):
    if key == "burst":
        return f"x{int(value)}"
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
    for k, v in t.get("set", {}).items():
        if k in STAT_NAMES and v != base[k]:
            out.append(f"{STAT_NAMES[k]} {format_stat(k, v)}")
    for k, v in t.get("mul", {}).items():
        if base[k]:
            out.append(f"{(v - 1) * 100:+.0f}% {STAT_NAMES[k]}")
    for k, v in t.get("add", {}).items():
        if base[k]:
            out.append(f"{v * 100:+.0f}% {STAT_NAMES[k]}" if k == "accuracy" else f"{v:+g} {STAT_NAMES[k]}")
    if t.get("cost"):
        out.append(f"{t['cost'] * 100:+.0f}% cost")
    return out
