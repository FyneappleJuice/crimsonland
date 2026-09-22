from __future__ import annotations

from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_instant_winner(ctx: PerkApplyCtx) -> None:
    # Not native: Perk Efficacy scales the flat XP award.
    ctx.owner.experience += round(2500 * float(ctx.owner.stats.perk_efficacy))


HOOKS = PerkHooks(
    perk_id=PerkId.INSTANT_WINNER,
    apply_handler=apply_instant_winner,
)
