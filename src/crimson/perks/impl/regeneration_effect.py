from __future__ import annotations

from ...math_parity import f32, x87_pc24_add, x87_pc24_mul
from ...rng_caller_static import RngCallerStatic
from ..helpers import perk_active
from ..ids import PerkId
from ..impl.soul_tether import soul_tether_clamp_and_gain
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def update_regeneration(ctx: PerksUpdateEffectsCtx) -> None:
    if not ctx.players:
        return
    if not perk_active(ctx.players[0], PerkId.REGENERATION):
        return
    if (
        ctx.state.rng.rand_tagged(RngCallerStatic.PERKS_UPDATE_EFFECTS_REGENERATION_GATE)
        & 1
    ) == 0:
        return
    dt = f32(float(ctx.dt))

    heal_amount = dt
    if perk_active(ctx.players[0], PerkId.GREATER_REGENERATION):
        heal_amount = x87_pc24_mul(dt, f32(2.0))

    for player in ctx.players:
        if float(player.health) <= 0.0:
            continue
        # Rewrite-only: Soul Tether wants the tick even at full health, so it
        # can redirect it into shield instead of it being skipped outright.
        if float(player.health) >= 100.0 and not perk_active(player, PerkId.SOUL_TETHER):
            continue
        player.health = soul_tether_clamp_and_gain(
            player,
            float(x87_pc24_add(f32(float(player.health)), heal_amount)),
        )


HOOKS = PerkHooks(
    perk_id=PerkId.REGENERATION,
    effects_steps=(update_regeneration,),
)
