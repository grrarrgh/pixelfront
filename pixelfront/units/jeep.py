"""Jeep: fast scout with a weapon station that swivels on a pintle."""

UNIT = dict(
    name="Jeep", cls="vehicle", target_class="light_vehicle", hotkey="j", desc="Fast scout with a mounted weapon.",
    hp=110, armor=1, speed=72, sight=8, hull_turn=300,   # degrees per second the hull turns
    cost=120, time=12, supply=2, radius=9, height=19,
    weapons=[
        dict(weapon="m2", cost=-0.1, time=-0.1),
        dict(weapon="uag40"),
        dict(weapon="tow", cost=0.5, time=0.3),
    ],
)
