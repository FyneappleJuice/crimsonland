from __future__ import annotations

"""Not native: Adrenaline Rush's bonus-damage window.

Taking damage (see player_damage.player_take_damage) opens/refreshes a timed
window; the damage bonus itself is applied in creatures/damage.py's
shooter-perk block while the window is open. This file just decays the timer.
"""

from ...math_parity import f32, x87_pc24_sub
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def update_adrenaline_rush_window(ctx: PerksUpdateEffectsCtx) -> None:
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if not perk_active(player, PerkId.ADRENALINE_RUSH):
            player.adrenaline_rush_window_timer = 0.0
            continue
        if player.adrenaline_rush_window_timer > 0.0:
            player.adrenaline_rush_window_timer = max(
                0.0,
                float(x87_pc24_sub(f32(player.adrenaline_rush_window_timer), dt)),
            )


HOOKS = PerkHooks(
    perk_id=PerkId.ADRENALINE_RUSH,
    effects_steps=(update_adrenaline_rush_window,),
)
