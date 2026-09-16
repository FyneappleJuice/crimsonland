from __future__ import annotations

from ...bonuses.ion_overload import fire_ion_overload_bolt
from ...math_parity import f32, x87_pc24_sub
from .effects_context import PerksUpdateEffectsCtx


def update_player_bonus_timers(ctx: PerksUpdateEffectsCtx) -> None:
    # Native `perks_update_effects` decrements per-player shield/fire-bullets/speed
    # timers before `player_update` reads them for this frame.
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if player.shield_timer <= 0.0:
            player.shield_timer = 0.0
        else:
            player.shield_timer = x87_pc24_sub(f32(float(player.shield_timer)), dt)

        if player.fire_bullets_timer <= 0.0:
            player.fire_bullets_timer = 0.0
        else:
            player.fire_bullets_timer = x87_pc24_sub(
                f32(float(player.fire_bullets_timer)),
                dt,
            )

        if player.speed_bonus_timer <= 0.0:
            player.speed_bonus_timer = 0.0
        else:
            player.speed_bonus_timer = x87_pc24_sub(
                f32(float(player.speed_bonus_timer)),
                dt,
            )

        if player.projectile_fork_timer <= 0.0:
            player.projectile_fork_timer = 0.0
        else:
            player.projectile_fork_timer = x87_pc24_sub(
                f32(float(player.projectile_fork_timer)),
                dt,
            )

        if player.explosive_payload_timer <= 0.0:
            player.explosive_payload_timer = 0.0
        else:
            player.explosive_payload_timer = x87_pc24_sub(
                f32(float(player.explosive_payload_timer)),
                dt,
            )

        if player.plasma_overload_timer <= 0.0:
            player.plasma_overload_timer = 0.0
        else:
            player.plasma_overload_timer = x87_pc24_sub(
                f32(float(player.plasma_overload_timer)),
                dt,
            )

        overload = player.ion_overload
        was_charging = overload.charge_timer > 0.0
        if not was_charging:
            overload.charge_timer = 0.0
        else:
            overload.charge_timer = x87_pc24_sub(f32(float(overload.charge_timer)), dt)
            if overload.charge_timer <= 0.0:
                # Not native: Ion Overload bonus - the charge just ran out,
                # fire the payload bolt now (bonuses/ion_overload.py).
                fire_ion_overload_bolt(ctx.state, player)
