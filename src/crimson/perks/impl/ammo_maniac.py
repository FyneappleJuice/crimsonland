from __future__ import annotations

from ...meta.relics_impl.giant_pact import wielded_slots
from ...weapon_runtime.assign import weapon_assign_player, weapon_slot_active
from ...weapons import WeaponId
from ..ids import PerkId
from ..runtime.apply_context import PerkApplyCtx
from ..runtime.hook_types import PerkHooks


def apply_ammo_maniac(ctx: PerkApplyCtx) -> None:
    if len(ctx.players) > 1:
        for player in ctx.players[1:]:
            player.perk_counts[:] = ctx.owner.perk_counts
    for player in ctx.players:
        # Re-assign every wielded weapon (both slots with Pact of the Giant)
        # so the bigger clip applies right away, not just to the primary.
        for slot in wielded_slots(player):
            with weapon_slot_active(player, slot):
                weapon_assign_player(player, WeaponId(slot.weapon_id), state=ctx.state)


HOOKS = PerkHooks(
    perk_id=PerkId.AMMO_MANIAC,
    apply_handler=apply_ammo_maniac,
)

# Not native: Ammo Maniac+ had no apply handler, so its bigger clip only
# showed up on the next weapon picked up - apply it immediately too.
PLUS_HOOKS = PerkHooks(
    perk_id=PerkId.AMMO_MANIAC_PLUS,
    apply_handler=apply_ammo_maniac,
)
