from __future__ import annotations

from ...rng_caller_static import RngCallerStatic
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_fatal_lottery(ctx: PerkApplyCtx) -> None:
    # Not native: Perk Efficacy skews the coin flip slightly toward the good
    # outcome instead of a flat 50/50 - capped well short of a sure thing, it
    # stays a lottery. The exact native `roll & 1` shape is kept bit-for-bit
    # at efficacy==1.0.
    efficacy = float(ctx.owner.stats.perk_efficacy)
    roll = ctx.state.rng.rand_tagged(RngCallerStatic.PERK_APPLY_FATAL_LOTTERY)
    if efficacy == 1.0:
        died = bool(roll & 1)
    else:
        good_chance = min(0.95, 0.5 * efficacy)
        died = (roll % 100) >= round(good_chance * 100)
    if died:
        ctx.owner.health = -1.0
    else:
        ctx.owner.experience += 10000


HOOKS = PerkHooks(
    perk_id=PerkId.FATAL_LOTTERY,
    apply_handler=apply_fatal_lottery,
)
