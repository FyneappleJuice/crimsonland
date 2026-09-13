from __future__ import annotations

"""Plasma Overload bonus - an original addition, not present in the native game.

For a limited time, every weapon fires like Multi-Plasma: a fixed 5-bolt fan
(`weapon_runtime/fire_recipes.py::MultiPlasmaFanMode`), at a faster cadence,
with every bolt carrying a flat +H clip-heat bonus (the same H that Reflex
Boost pins plasma weapons to - see `weapon_runtime/plasma_heat.py`) regardless
of the underlying weapon's own clip state.

The pick-up only starts the timer (`player.plasma_overload_timer`); the recipe
override, fire-rate bump, and heat stamping all live in
`weapon_runtime/fire.py` and `weapon_runtime/fire_recipes.py`, gated on it.
"""

from ..math_parity import f32
from .apply_context import BonusApplyCtx, bonus_apply_seconds


def apply_plasma_overload(ctx: BonusApplyCtx) -> None:
    should_register = float(ctx.player.plasma_overload_timer) <= 0.0
    if len(ctx.players) > 1:
        should_register = (
            float(ctx.players[0].plasma_overload_timer) <= 0.0
            and float(ctx.players[1].plasma_overload_timer) <= 0.0
        )
    if should_register:
        ctx.register_player("plasma_overload_timer")
    ctx.player.plasma_overload_timer = float(
        f32(
            float(ctx.player.plasma_overload_timer)
            + bonus_apply_seconds(ctx) * float(ctx.economist_multiplier),
        ),
    )
