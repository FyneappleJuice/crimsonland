from __future__ import annotations

"""Plasma Overload bonus - an original addition, not present in the native game.

For a limited time, every weapon's fire recipe is overridden: it fires two
Plasma Rifle bolts side-by-side on the same heading (not a fan - no angle
spread) instead of its own projectile, at a fixed Assault Rifle cooldown, for
no ammo cost (so it can never trigger a reload either).

The pick-up only starts the timer (`player.plasma_overload_timer`); the
actual fire-mode override happens in `weapon_runtime/fire_recipes.py`
(`resolve_fire_recipe`'s `plasma_overload_active` branch, returning
`PlasmaOverloadMode`) and is resolved in `weapon_runtime/fire.py`'s dedicated
`PlasmaOverloadMode` case, which also carries the fixed cooldown and skips
the ammo decrement.
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
    # Same "clear the slate" treatment Fire Bullets gives on pickup - clip
    # tops off immediately instead of waiting out whatever reload was mid-flight.
    ctx.player.weapon_reset_latch = 0
    ctx.player.weapon.shot_cooldown = 0.0
    ctx.player.weapon.reload_timer = 0.0
    ctx.player.weapon.ammo = float(ctx.player.weapon.clip_size)
