from __future__ import annotations

"""Ion Payload bonus - an original addition, not present in the native game.

For a limited time, every bullet leaves a brief ion cloud where it lands: on
top of its own regular damage, it spawns a stationary, short-lived ION_MINIGUN
projectile at the impact point purely to ride the native Ion weapons' own
lingering-AoE behavior (`projectiles/runtime/behaviors.py::_linger_ion_aoe`) -
the same cloud a real Ion Minigun bolt blooms into as it expires. Shotgun-style
multi-pellet weapons only flag their single centre-most pellet, mirroring
Explosive Payload.

The pick-up only starts the timer (`player.ion_payload_timer`); which pellet
gets marked `Projectile.is_ion_payload` happens at fire time in
`weapon_runtime/fire.py::PrimaryPelletsMode`, and the actual cloud spawn
happens in `projectiles/runtime/projectile_pool.py`.
"""

from ..math_parity import f32
from .apply_context import BonusApplyCtx, bonus_apply_seconds


def apply_ion_payload(ctx: BonusApplyCtx) -> None:
    should_register = float(ctx.player.ion_payload_timer) <= 0.0
    if len(ctx.players) > 1:
        should_register = (
            float(ctx.players[0].ion_payload_timer) <= 0.0
            and float(ctx.players[1].ion_payload_timer) <= 0.0
        )
    if should_register:
        ctx.register_player("ion_payload_timer")
    ctx.player.ion_payload_timer = float(
        f32(
            float(ctx.player.ion_payload_timer)
            + bonus_apply_seconds(ctx) * float(ctx.economist_multiplier),
        ),
    )
