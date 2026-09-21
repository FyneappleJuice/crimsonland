from __future__ import annotations

from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def update_evil_eyes_target(ctx: PerksUpdateEffectsCtx) -> None:
    if not ctx.players:
        return

    for player in ctx.players:
        if float(player.health) <= 0.0:
            player.evil_eyes_target_creature = -1
            continue
        if not perk_active(player, PerkId.EVIL_EYES):
            player.evil_eyes_target_creature = -1
            continue
        player.evil_eyes_target_creature = ctx.aim_target_for_player(player.index)


HOOKS = PerkHooks(
    perk_id=PerkId.EVIL_EYES,
    effects_steps=(update_evil_eyes_target,),
)
