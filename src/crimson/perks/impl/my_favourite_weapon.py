from __future__ import annotations

from ...meta.relics_impl.giant_pact import wielded_slots
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_my_favourite_weapon(ctx: PerkApplyCtx) -> None:
    for player in ctx.players:
        # Every wielded weapon - both slots with Pact of the Giant.
        for slot in wielded_slots(player):
            slot.clip_size += 2


HOOKS = PerkHooks(
    perk_id=PerkId.MY_FAVOURITE_WEAPON,
    apply_handler=apply_my_favourite_weapon,
)
