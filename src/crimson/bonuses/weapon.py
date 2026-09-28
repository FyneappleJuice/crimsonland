from __future__ import annotations

from ..meta.relics_impl import giant_pact as relic_giant_pact
from ..weapon_runtime.assign import weapon_assign_player, weapon_slot_active
from ..weapons import WeaponId
from .apply_context import BonusApplyCtx


def apply_weapon(ctx: BonusApplyCtx) -> None:
    # Native weapon pickup is just weapon_assign_player: the old weapon is
    # never stashed anywhere (the alt slot is preloaded with a pistol at
    # player reset, so an empty alt slot cannot occur in native flow).
    weapon_id = WeaponId(ctx.amount)
    if relic_giant_pact.dual_wielding(ctx.player):
        # Not native: Pact of the Giant relic - a pickup replaces whichever
        # slot is currently "active" (giant_pact_active_slot), not always
        # the primary - except a leftover starter Pistol is filled first.
        target = relic_giant_pact.pickup_target_slot(ctx.player)
        with weapon_slot_active(ctx.player, target):
            weapon_assign_player(ctx.player, weapon_id, state=ctx.state)
        return
    weapon_assign_player(ctx.player, weapon_id, state=ctx.state)
