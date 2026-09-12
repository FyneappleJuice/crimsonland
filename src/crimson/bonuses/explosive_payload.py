from __future__ import annotations

"""Explosive Payload bonus - an original addition, not present in the native game.

For a limited time, every bullet you fire becomes a rocket: on top of its own
regular damage, it detonates on impact for a small area-of-effect burst.
Shotgun-style multi-pellet weapons only convert their single centre-most
pellet - the rest of the spread stays as normal pellets.

The pick-up only starts the timer (`player.explosive_payload_timer`); which
pellet gets marked `Projectile.is_rocket` happens at fire time in
`weapon_runtime/fire.py::PrimaryPelletsMode`, and the actual detonation-on-hit
happens in `projectiles/runtime/projectile_pool.py` by spawning a real
secondary-projectile `DETONATION` burst - the exact same expanding-radius,
damage-per-tick AoE that the Rocket Launcher's own detonation uses (see
`projectiles/runtime/secondary_pool.py`), just at a modest fixed scale so it
stays reasonable on any weapon's fire rate.
"""

from ..math_parity import f32
from .apply_context import BonusApplyCtx, bonus_apply_seconds

# The detonation-on-hit "scale" constant lives in
# projectiles/runtime/projectile_pool.py (_EXPLOSIVE_PAYLOAD_DETONATION_SCALE),
# next to the code that actually spawns the blast - kept out of this module to
# avoid a projectiles -> bonuses import (see _FORK_SHOT_ANGLE_RAD for the same
# convention with Fork Shot).


def apply_explosive_payload(ctx: BonusApplyCtx) -> None:
    should_register = float(ctx.player.explosive_payload_timer) <= 0.0
    if len(ctx.players) > 1:
        should_register = (
            float(ctx.players[0].explosive_payload_timer) <= 0.0
            and float(ctx.players[1].explosive_payload_timer) <= 0.0
        )
    if should_register:
        ctx.register_player("explosive_payload_timer")
    ctx.player.explosive_payload_timer = float(
        f32(
            float(ctx.player.explosive_payload_timer)
            + bonus_apply_seconds(ctx) * float(ctx.economist_multiplier),
        ),
    )
