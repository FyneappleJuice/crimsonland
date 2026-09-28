from __future__ import annotations

from ...meta.relics_impl import giant_pact as relic_giant_pact
from ...weapon_runtime.assign import weapon_assign_player, weapon_slot_active
from ...weapon_runtime.availability import weapon_pick_random_available
from ...weapons import WeaponId
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_random_weapon(ctx: PerkApplyCtx) -> None:
    # With Pact of the Giant, replace the slot a weapon pickup would (the
    # active slot, a leftover starter Pistol first), not always the primary.
    target = (
        relic_giant_pact.pickup_target_slot(ctx.owner)
        if relic_giant_pact.dual_wielding(ctx.owner)
        else ctx.owner.weapon
    )
    current = target.weapon_id
    weapon_id = current
    for _ in range(100):
        candidate = weapon_pick_random_available(ctx.state)
        weapon_id = candidate
        if candidate != WeaponId.PISTOL and candidate != current:
            break
    with weapon_slot_active(ctx.owner, target):
        weapon_assign_player(ctx.owner, weapon_id, state=ctx.state)


HOOKS = PerkHooks(
    perk_id=PerkId.RANDOM_WEAPON,
    apply_handler=apply_random_weapon,
)
