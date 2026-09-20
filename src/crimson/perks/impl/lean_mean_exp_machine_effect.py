from __future__ import annotations

from ...math_parity import f32, x87_pc24_sub
from ..helpers import perk_count_get
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def update_lean_mean_exp_machine(ctx: PerksUpdateEffectsCtx) -> None:
    ctx.state.lean_mean_exp_timer = x87_pc24_sub(
        f32(float(ctx.state.lean_mean_exp_timer)),
        f32(float(ctx.dt)),
    )
    if ctx.state.lean_mean_exp_timer < 0.0:
        ctx.state.lean_mean_exp_timer = f32(0.25)
        if not ctx.players:
            return

        # Native `perks_update_effects` uses global `perk_count_get` and awards the
        # periodic XP tick only to player 0 (`player_experience[0]`).
        player0 = ctx.players[0]
        # Rewrite-only: floor each tier at a flat minimum so a single copy is
        # worth taking on its own, not just a per-copy trickle that only adds
        # up once you're stacking several - scaling past the floor still
        # works normally once the linear term overtakes it.
        perk_count = perk_count_get(player0, PerkId.LEAN_MEAN_EXP_MACHINE)
        if perk_count > 0:
            player0.experience += max(20, perk_count * 10)

        # Rewrite-only: Lean Mean Exp Machine++ adds a second, larger trickle on
        # the same timer rather than replacing the base rate.
        plus_count = perk_count_get(player0, PerkId.LEAN_MEAN_EXP_MACHINE_PLUS)
        if plus_count > 0:
            player0.experience += max(40, plus_count * 20)


HOOKS = PerkHooks(
    perk_id=PerkId.LEAN_MEAN_EXP_MACHINE,
    effects_steps=(update_lean_mean_exp_machine,),
)
