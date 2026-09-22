from __future__ import annotations

from ...math_parity import f32, x87_pc24_add
from ...rng_caller_static import RngCallerStatic
from ..ids import PerkId
from ..impl.soul_tether import soul_tether_clamp_and_gain
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_bandage(ctx: PerkApplyCtx) -> None:
    for player in ctx.players:
        # Heal only alive players (original-bugs.md item 3).
        if player.health <= 0.0:
            continue
        # Not native: Perk Efficacy scales the heal roll.
        amount = float(
            ctx.state.rng.rand_tagged(RngCallerStatic.PERK_APPLY_BANDAGE_HEAL)
            % 50
            + 1,
        ) * float(player.stats.perk_efficacy)
        health = f32(player.health)
        # Intended behavior from in-game text: restore up to 50% HP.
        player.health = soul_tether_clamp_and_gain(player, float(x87_pc24_add(health, amount)))
        ctx.state.effects.spawn_burst(
            pos=player.pos,
            count=8,
            rng=ctx.state.rng,
            detail_preset=5,
        )


HOOKS = PerkHooks(
    perk_id=PerkId.BANDAGE,
    apply_handler=apply_bandage,
)
