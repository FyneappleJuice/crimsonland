from __future__ import annotations

"""Fork Shot bonus - an original addition, not present in the native game.

Generalizes Splitter Gun's on-hit fork behavior (see
`projectiles/runtime/behaviors.py::_pre_hit_splitter`) to every non-piercing
weapon for a limited time. The actual fork-on-hit logic lives in
`projectiles/runtime/projectile_pool.py`, gated on `player.projectile_fork_timer`;
this module only handles picking up the timed bonus.
"""

from ..math_parity import f32
from .apply_context import BonusApplyCtx, bonus_apply_seconds


def apply_projectile_fork(ctx: BonusApplyCtx) -> None:
    should_register = float(ctx.player.projectile_fork_timer) <= 0.0
    if len(ctx.players) > 1:
        should_register = (
            float(ctx.players[0].projectile_fork_timer) <= 0.0
            and float(ctx.players[1].projectile_fork_timer) <= 0.0
        )
    if should_register:
        ctx.register_player("projectile_fork_timer")
    ctx.player.projectile_fork_timer = float(
        f32(float(ctx.player.projectile_fork_timer) + bonus_apply_seconds(ctx) * float(ctx.economist_multiplier)),
    )
