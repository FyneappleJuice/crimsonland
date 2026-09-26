from __future__ import annotations

from ...math_parity import f32, x87_pc24_mul, x87_pc24_sub
from ...sim.state_types import PlayerState
from ..helpers import perk_active, perk_count_get
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.counts import adjust_perk_count
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def apply_death_clock(ctx: PerkApplyCtx) -> None:
    adjust_perk_count(
        ctx.owner,
        PerkId.REGENERATION,
        amount=-perk_count_get(ctx.owner, PerkId.REGENERATION),
    )
    adjust_perk_count(
        ctx.owner,
        PerkId.GREATER_REGENERATION,
        amount=-perk_count_get(ctx.owner, PerkId.GREATER_REGENERATION),
    )
    for player in ctx.players:
        if player.health > 0.0:
            player.health = 100.0
        # Not native: strip any banked Rainy Day Fund shield outright - the
        # 30s clock is meant to be an unavoidable, ticking floor. See
        # blocks_health_change below for why nothing can rebuild it either.
        player.soul_tether_shield = 0.0


def update_death_clock(ctx: PerksUpdateEffectsCtx) -> None:
    if not ctx.players:
        return
    if not perk_active(ctx.players[0], PerkId.DEATH_CLOCK):
        return

    # Native gates this effect on shared/player-0 perk state, then applies health
    # drain to every active local player.
    # Not native: Perk Efficacy stretches the 30s countdown by slowing the
    # drain rate (health resets to 100 on pickup, so a slower drain is more
    # seconds before it reaches 0).
    efficacy = float(ctx.players[0].stats.perk_efficacy)
    drain = x87_pc24_mul(f32(float(ctx.dt)), f32(3.33333325 / efficacy))
    for player in ctx.players:
        if float(player.health) <= 0.0:
            player.health = 0.0
        else:
            player.health = x87_pc24_sub(f32(float(player.health)), drain)


def blocks_health_change(player: PlayerState) -> bool:
    """True while Death Clock is active - every OTHER system that would move
    player.health (heals, shield gain/absorb, external hits on the thinner
    projectile-damage path) has to no-op instead, so the perk's own drain
    (update_death_clock, above) is the only thing that can ever move it.
    Without this, Leech/Harvester's Scythe healing faster than the fixed
    drain rate turns "guaranteed death in 30s" into free permanent
    invincibility - the exact opposite of what picking this perk means."""
    return perk_active(player, PerkId.DEATH_CLOCK)


HOOKS = PerkHooks(
    perk_id=PerkId.DEATH_CLOCK,
    apply_handler=apply_death_clock,
    effects_steps=(update_death_clock,),
)
