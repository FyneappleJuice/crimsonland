from __future__ import annotations

from crimson.bonuses import BonusId
from crimson.bonuses.selection import bonus_pick_random_type
from crimson.game_modes import GameMode
from crimson.gameplay import GameplayState
from crimson.rng_caller_static import RngCallerStatic
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand

# roll = rand() % 162 + 1 -> 162 lands in the tail of the 162-entry table that
# was dead space in the original game (bucket walk pushes bonus_value to 15).
_DEAD_SPACE_ROLL = 161


def _state(*, rng_values: list[int]) -> GameplayState:
    return GameplayState(
        rng=ScriptedCrand(rng_values, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )


def test_native_modes_reroll_the_dead_space_slot() -> None:
    # fork_bonus_in_pool defaults off: the dead-space slot rerolls forever,
    # exactly like the original, and the 101-try loop falls back to POINTS.
    state = _state(rng_values=[_DEAD_SPACE_ROLL])
    state.game_mode = GameMode.SURVIVAL
    players = [PlayerState(index=0, pos=Vec2())]

    assert bonus_pick_random_type(state.bonus_pool, state, players) == BonusId.POINTS


def test_maps_dead_space_slot_sub_rolls_a_rewrite_only_bonus() -> None:
    players = [PlayerState(index=0, pos=Vec2())]

    # sub-roll 0 -> first entry of the rewrite pool (Fork Shot)
    fork_state = _state(rng_values=[_DEAD_SPACE_ROLL, 0])
    fork_state.fork_bonus_in_pool = True
    assert bonus_pick_random_type(fork_state.bonus_pool, fork_state, players) == BonusId.PROJECTILE_FORK

    # sub-roll 1 -> second entry (Blade)
    blade_state = _state(rng_values=[_DEAD_SPACE_ROLL, 1])
    blade_state.fork_bonus_in_pool = True
    assert bonus_pick_random_type(blade_state.bonus_pool, blade_state, players) == BonusId.BLADE


def test_maps_dead_space_roll_consumes_the_table_roll_plus_one_sub_roll() -> None:
    rng = ScriptedCrand([_DEAD_SPACE_ROLL, 0], fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    state = GameplayState(rng=rng)
    state.fork_bonus_in_pool = True
    players = [PlayerState(index=0, pos=Vec2())]

    bonus_pick_random_type(state.bonus_pool, state, players)

    assert [record.caller for record in rng.records_since()] == [
        RngCallerStatic.BONUS_PICK_RANDOM_TYPE_ROLL,
        RngCallerStatic.REWRITE_MAPS_NONNATIVE_BONUS_PICK,
    ]


def test_rewrite_bonuses_still_drop_while_already_active() -> None:
    state = _state(rng_values=[_DEAD_SPACE_ROLL, 0])
    state.fork_bonus_in_pool = True
    player = PlayerState(index=0, pos=Vec2())
    player.projectile_fork_timer = 3.0

    assert bonus_pick_random_type(state.bonus_pool, state, [player]) == BonusId.PROJECTILE_FORK
