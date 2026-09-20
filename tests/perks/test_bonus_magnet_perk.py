from __future__ import annotations

from crimson.bonuses.pool import BonusPool
from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand


def test_bonus_magnet_allows_bonus_spawn_on_secondary_roll() -> None:
    base_state = GameplayState()
    base_state.rng = ScriptedCrand([0], fallback=ScriptedCrand.Fallback.ZERO)
    base_state.bonus_pool = BonusPool()
    base_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.ASSAULT_RIFLE))

    assert (
        base_state.bonus_pool.try_spawn_on_kill(pos=Vec2(100.0, 100.0), state=base_state, players=[base_player]) is None
    )

    perk_state = GameplayState()
    perk_state.rng = ScriptedCrand([0, 2, 0, 0], fallback=ScriptedCrand.Fallback.ZERO)
    perk_state.bonus_pool = BonusPool()
    perk_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.ASSAULT_RIFLE))
    perk_player.perk_counts[int(PerkId.BONUS_MAGNET)] = 1

    assert (
        perk_state.bonus_pool.try_spawn_on_kill(pos=Vec2(100.0, 100.0), state=perk_state, players=[perk_player])
        is not None
    )


def test_bonus_magnet_plus_widens_the_gated_odds_from_1_in_10_to_1_in_5() -> None:
    # roll=7: 7 % 10 == 7 (base Bonus Magnet alone would miss this roll),
    # but 7 % 5 == 2 (Bonus Magnet++ hits it).
    base_state = GameplayState()
    base_state.rng = ScriptedCrand([0, 7, 0, 0], fallback=ScriptedCrand.Fallback.ZERO)
    base_state.bonus_pool = BonusPool()
    base_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.ASSAULT_RIFLE))
    base_player.perk_counts[int(PerkId.BONUS_MAGNET)] = 1

    assert (
        base_state.bonus_pool.try_spawn_on_kill(pos=Vec2(100.0, 100.0), state=base_state, players=[base_player])
        is None
    )

    plus_state = GameplayState()
    plus_state.rng = ScriptedCrand([0, 7, 0, 0], fallback=ScriptedCrand.Fallback.ZERO)
    plus_state.bonus_pool = BonusPool()
    plus_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.ASSAULT_RIFLE))
    plus_player.perk_counts[int(PerkId.BONUS_MAGNET)] = 1
    plus_player.perk_counts[int(PerkId.BONUS_MAGNET_PLUS)] = 1

    assert (
        plus_state.bonus_pool.try_spawn_on_kill(pos=Vec2(100.0, 100.0), state=plus_state, players=[plus_player])
        is not None
    )
