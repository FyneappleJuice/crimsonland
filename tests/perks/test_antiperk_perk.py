from __future__ import annotations

from crimson.game_modes import GameMode
from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.perks.availability import build_perk_availability, perk_can_offer
from crimson.perks.ids import PERK_BY_ID, PERK_MASTERY_CONCRETE_IDS
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def test_antiperk_is_excluded_by_availability_not_offer_predicate() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    assert perk_can_offer(state, player, PerkId.ANTIPERK, game_mode=GameMode.SURVIVAL, player_count=1)
    assert not build_perk_availability(status=None)[int(PerkId.ANTIPERK)]


def test_every_perk_is_unlocked_regardless_of_quest_progress() -> None:
    # Not native: the mod drops quest-gated perk unlocks entirely.
    available = build_perk_availability(status=None)
    disabled = {PerkId.ANTIPERK, PerkId.ANXIOUS_LOADER, PerkId.FINAL_REVENGE} | PERK_MASTERY_CONCRETE_IDS
    for perk_id in PERK_BY_ID:
        if perk_id in disabled:
            assert not available[int(perk_id)]
        else:
            assert available[int(perk_id)]
