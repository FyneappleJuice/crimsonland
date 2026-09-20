from __future__ import annotations

"""Not native: Bane of Legends.

A flat -10% damage penalty at all times, offset by +30% for 5 seconds after
any kill. The kill-side timer is set in creatures/runtime.py's death handler
(same hook Momentum uses); this file only decays it.
"""

from ...math_parity import f32, x87_pc24_sub
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

BANE_OF_LEGENDS_PENALTY = 0.10
BANE_OF_LEGENDS_KILL_BONUS = 0.30
BANE_OF_LEGENDS_WINDOW_DURATION = 5.0


def update_bane_of_legends_window(ctx: PerksUpdateEffectsCtx) -> None:
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if not perk_active(player, PerkId.BANE_OF_LEGENDS):
            player.bane_of_legends_timer = 0.0
            continue
        if player.bane_of_legends_timer > 0.0:
            player.bane_of_legends_timer = max(
                0.0,
                float(x87_pc24_sub(f32(player.bane_of_legends_timer), dt)),
            )


HOOKS = PerkHooks(
    perk_id=PerkId.BANE_OF_LEGENDS,
    effects_steps=(update_bane_of_legends_window,),
)
