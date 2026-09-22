from __future__ import annotations

from ...math_parity import f32
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_infernal_contract(ctx: PerkApplyCtx) -> None:
    ctx.owner.level += 3
    if ctx.perk_state is not None:
        ctx.perk_state.pending_count += 3
        ctx.perk_state.choices_dirty = True
    ctx.state.run_mod_selection.pending_count += 3
    ctx.state.run_mod_selection.choices_dirty = True
    for player in ctx.players:
        if player.health > 0.0:
            # Rewrite-only: floored at 1.0 (was a flat 0.1) so this
            # self-inflicted, non-enemy cost is never itself lethal. Perk
            # Efficacy raises how much health survives the cut.
            player.health = f32(1.0 * float(player.stats.perk_efficacy))


HOOKS = PerkHooks(
    perk_id=PerkId.INFERNAL_CONTRACT,
    apply_handler=apply_infernal_contract,
)
