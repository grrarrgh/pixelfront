"""All unit types, keyed by kind. Each lives in its own module in this package.

A unit definition (UNIT in units/<kind>.py) holds its base stats and:
- weapons:  three weapon tiers (Light, Medium = default, Heavy), each a weapon id from
            weapons.py plus optional mul/add/cost/time for carrying it; or
- weapon:   a single fixed weapon id (None = unarmed);
- tiers:    unit-specific tiers for any slot (e.g. the medic's medkit, heavy infantry armour);
- slot_labels: renamed slots (the engineer's weapon slot is "Tools").

To add a unit: write units/<kind>.py with a UNIT dict, add it below, and give it a model.
"""
from . import engineer, rifleman, medic, heavy, jeep, tank

# Order matters: it's the order units appear in lists, the motion test and the title screen.
UNITS = {
    "engineer": engineer.UNIT,
    "rifleman": rifleman.UNIT,
    "medic": medic.UNIT,
    "heavy": heavy.UNIT,
    "jeep": jeep.UNIT,
    "tank": tank.UNIT,
}

for _def in UNITS.values():
    # The default weapon: the Medium weapon tier, or the fixed weapon.
    if "weapons" in _def:
        _def["weapon"] = _def["weapons"][1]["weapon"]
    _def.setdefault("weapon", None)
