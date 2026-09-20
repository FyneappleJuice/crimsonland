from __future__ import annotations

from ..math_parity import f32
from ..perks.impl.pendulum import pendulum_snapshot_on_bonus_pickup
from .apply_context import BonusApplyCtx


def apply_weapon_power_up(ctx: BonusApplyCtx) -> None:
    # Rewrite-only: Pendulum snapshots whichever phase is active right now, so
    # a reload mid-buff can't change what this pickup is worth.
    pendulum_snapshot_on_bonus_pickup(ctx.player)

    old = float(ctx.state.bonuses.weapon_power_up)
    if old <= 0.0:
        ctx.register_global("weapon_power_up")
    ctx.state.bonuses.weapon_power_up = float(
        f32(float(old) + float(ctx.amount) * float(ctx.economist_multiplier)),
    )
    ctx.player.weapon_reset_latch = 0
    ctx.player.weapon.shot_cooldown = 0.0
    ctx.player.weapon.reload_timer = 0.0
    ctx.player.weapon.ammo = float(ctx.player.weapon.clip_size)
