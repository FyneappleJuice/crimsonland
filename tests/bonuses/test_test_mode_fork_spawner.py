from __future__ import annotations

from crimson.bonuses.ids import BonusId
from crimson.bonuses.update import (
    _TEST_MODE_BONUS_CYCLE,
    _TEST_MODE_WEAPON_DROPS,
    update_test_mode_fork_spawner,
)
from crimson.gameplay import GameplayState
from crimson.test_mode import set_test_mode_enabled
from crimson.weapons import WeaponId


def _weapon_drops(state: GameplayState) -> list:
    return [e for e in state.bonus_pool.entries if e.bonus_id == BonusId.WEAPON and not e.picked]


def test_spawner_does_nothing_when_test_mode_disabled() -> None:
    set_test_mode_enabled(False)
    try:
        state = GameplayState()
        update_test_mode_fork_spawner(state, 10.0)
        assert _weapon_drops(state) == []
    finally:
        set_test_mode_enabled(False)


def test_drops_only_the_arc_gun_once_at_spawn() -> None:
    set_test_mode_enabled(True)
    try:
        state = GameplayState()
        update_test_mode_fork_spawner(state, 0.016)

        drops = _weapon_drops(state)
        assert [WeaponId(d.amount) for d in drops] == [WeaponId.RAYGUN]
        assert _TEST_MODE_WEAPON_DROPS == ((64.0, WeaponId.RAYGUN),)

        # subsequent ticks do not re-drop
        for _ in range(20):
            update_test_mode_fork_spawner(state, 5.0)
        assert len(_weapon_drops(state)) == 1
    finally:
        set_test_mode_enabled(False)


def test_no_bonuses_are_auto_spawned() -> None:
    set_test_mode_enabled(True)
    try:
        assert _TEST_MODE_BONUS_CYCLE == ()
        state = GameplayState()
        for _ in range(30):
            update_test_mode_fork_spawner(state, 5.0)
        non_weapon = [
            e
            for e in state.bonus_pool.entries
            if e.bonus_id not in (BonusId.UNUSED, BonusId.WEAPON) and not e.picked
        ]
        assert non_weapon == []
    finally:
        set_test_mode_enabled(False)
