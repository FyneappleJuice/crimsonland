from __future__ import annotations

"""Not native: Overdue's bonus-damage window.

weapon_runtime/fire.py tracks the consecutive-non-crit streak and opens the
window (sets `overdue_window_timer`) once it hits threshold; this counts both
that window and the streak's own internal-cooldown timer
(overdue_tick_cooldown_timer - see projectiles/runtime/projectile_pool.py's
OVERDUE_TICK_COOLDOWN) back down every frame, independent of whether the
player is currently firing.
"""

from ...math_parity import f32, x87_pc24_sub
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def update_overdue_window(ctx: PerksUpdateEffectsCtx) -> None:
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if not perk_active(player, PerkId.OVERDUE):
            player.overdue_window_timer = 0.0
            player.overdue_tick_cooldown_timer = 0.0
            continue
        if player.overdue_window_timer > 0.0:
            player.overdue_window_timer = max(0.0, float(x87_pc24_sub(f32(player.overdue_window_timer), dt)))
        if player.overdue_tick_cooldown_timer > 0.0:
            player.overdue_tick_cooldown_timer = max(
                0.0, float(x87_pc24_sub(f32(player.overdue_tick_cooldown_timer), dt)),
            )


HOOKS = PerkHooks(
    perk_id=PerkId.OVERDUE,
    effects_steps=(update_overdue_window,),
)
