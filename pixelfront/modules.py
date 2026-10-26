"""Unit loadouts: the core customisation mechanic.

Every unit is trained with one tier chosen per module slot (Armor, Weapon, Speed). The middle
tier is the unit's baseline; tiers either side trade one strength for another. A tier changes
stats with multipliers (`mul`) and flat additions (`add`), and changes price and build time by
a fraction of the unit's base values.

Where things live:
- Generic Armor and Speed tiers: SLOTS below.
- Weapon tiers: each unit's `weapons` list (units/<kind>.py) names a weapon per tier; the
  weapon's numbers come from weapons.py.
- Unit-specific tiers for any slot (the medic's medkit, heavy infantry armour): the unit's
  `tiers` in units/<kind>.py.

Extending: a new slot is an entry in SLOTS (plus STAT_NAMES if it touches a new stat) and a
look in model3d if it should be visible.
"""
from . import weapons as W
from .units import UNITS

SLOTS = {
    "armor": dict(label="Armor", default=1, tiers=[
        dict(name="Light", desc="Less protection, quicker on its feet.",
             mul={"hp": 0.7, "speed": 1.15}, cost=-0.15, time=-0.1),
        dict(name="Medium", desc="Standard protection."),
        dict(name="Heavy", desc="Thick plating. Slow and expensive.",
             mul={"hp": 1.6, "speed": 0.8}, add={"armor": 1}, cost=0.5, time=0.3),
    ]),
    # Weapon tiers come from each unit's `weapons` (or `tiers["weapon"]`); see tiers().
    "weapon": dict(label="Weapon", default=1, tiers=None),
    "engine": dict(label="Speed", default=1, tiers=[
        dict(name="Slow", desc="Extra kit: tougher but sluggish.",
             mul={"speed": 0.75, "hp": 1.2}, cost=-0.15, time=-0.1),
        dict(name="Normal", desc="Standard pace."),
        dict(name="Fast", desc="Stripped down for speed. More fragile.",
             mul={"speed": 1.4, "hp": 0.8}, cost=0.35, time=0.2),
    ]),
}
TIER_NAMES = ("Light", "Medium", "Heavy")

# Stat key -> display name. Stats a unit doesn't have (base value 0) are hidden for it.
STAT_NAMES = {
    "hp": "HP", "armor": "Armor", "damage": "Damage", "heal": "Heal", "work": "Work rate",
    "range": "Range", "cooldown": "Reload", "burst": "Burst", "accuracy": "Accuracy", "speed": "Speed",
    "sight": "Sight", "vs_vehicle": "Vs vehicles",
}
UNIT_STAT_DEFAULTS = {"heal": 0, "work": 0, "cooldown": 1.0}
LOWER_IS_BETTER = {"cooldown"}


def slots_for(kind):
    return UNITS[kind].get("slots", list(SLOTS))


def slot_label(kind, slot):
    return UNITS[kind].get("slot_labels", {}).get(slot, SLOTS[slot]["label"])


_weapon_tiers = {}


def tiers(kind, slot):
    d = UNITS[kind]
    if slot in d.get("tiers", {}):
        return d["tiers"][slot]
    if slot == "weapon" and "weapons" in d:
        got = _weapon_tiers.get(kind)
        if got is None:   # build Light/Medium/Heavy tiers from the unit's weapon list
            got = _weapon_tiers[kind] = []
            for name, entry in zip(TIER_NAMES, d["weapons"]):
                w = W.weapon(entry["weapon"])
                got.append(dict(entry, name=name, desc=f"{w['name']}: {w['desc']}"))
        return got
    if SLOTS[slot]["tiers"] is None:   # a fixed weapon (or none): nothing to choose
        return [dict(name=n) for n in TIER_NAMES]
    return SLOTS[slot]["tiers"]


def tier(kind, slot, level):
    return tiers(kind, slot)[level]


def default_loadout(kind):
    return {slot: SLOTS[slot]["default"] for slot in slots_for(kind)}


def base_stats(kind):
    """The unit's own stats plus those of its default weapon, plus "weapon" (its id)."""
    d = UNITS[kind]
    st = {k: d.get(k, UNIT_STAT_DEFAULTS.get(k, 0)) for k in STAT_NAMES}
    st.update(W.stats(d["weapon"]))
    if d["weapon"] is None:
        st["cooldown"] = d.get("cooldown", 1.0)   # unarmed units: their work cadence
    st["weapon"] = d["weapon"]
    return st


def compute_stats(kind, loadout):
    """Stats for a unit with this loadout, including "weapon": the id of the weapon it carries."""
    st = base_stats(kind)
    for slot, level in loadout.items():
        wid = tier(kind, slot, level).get("weapon")
        if wid:
            st.update(W.stats(wid))
            st["weapon"] = wid
    for slot, level in loadout.items():
        t = tier(kind, slot, level)
        for k, v in t.get("mul", {}).items():
            st[k] *= v
        for k, v in t.get("add", {}).items():
            st[k] += v
    if st["accuracy"]:
        st["accuracy"] = min(1.0, max(0.05, st["accuracy"]))
    st["armor_rank"] = armor_rank(kind, loadout)
    return st


def armor_rank(kind, loadout):
    """Armour rank (index into weapons.ARMOR_RANKS): the Armor tier plus the unit's extra ranks."""
    return loadout.get("armor", SLOTS["armor"]["default"]) + UNITS[kind].get("armor_rank", 0)


def armor_rank_info(kind, loadout):
    """(rank name, 'Bullets -15%  Explosives -15%'-style summary) for the HUD and design screen."""
    d = W.armor_rank(UNITS[kind]["cls"], armor_rank(kind, loadout))
    cuts = [f"{label} -{(1 - d[t]) * 100:.0f}%" for t, label in
            (("bullet", "Bullets"), ("explosive", "Explosives"), ("anti_armor", "AT"))]
    return d["name"], "  ".join(c for c in cuts if not c.endswith("-0%"))


def weapon_of(kind, loadout):
    """The weapon id a unit with this loadout carries (None if unarmed)."""
    return compute_stats(kind, loadout)["weapon"]


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
    """Human-readable effects of a tier on this unit, e.g. ['+60% HP', 'Damage 14']."""
    t = tier(kind, slot, level)
    base = base_stats(kind)
    out = []
    if slot == "armor":
        name, cuts = armor_rank_info(kind, {"armor": level})
        out.append(name)
        if cuts:
            out.append(cuts)
    wid = t.get("weapon")
    if wid and wid != base["weapon"]:
        w = W.weapon(wid)
        out.append(f"{w['type'].replace('_', '-')}")
        for k, v in W.stats(wid).items():
            if v != base[k] and not (k == "burst" and v == 1):
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
