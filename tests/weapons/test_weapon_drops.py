from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from crimson.game_modes import GameMode
from crimson.gameplay import GameplayState
from crimson.persistence import save_status
from crimson.rng_caller_static import RngCallerStatic
from crimson.weapon_runtime import (
    prepare_weapon_availability,
    weapon_pick_random_available,
)
from crimson.weapons import WeaponId
from tests.support.helpers import ScriptedCrand


class _SeqRng:
    def __init__(self, values: list[int]) -> None:
        self._values = [int(v) for v in values] or [0]
        self._idx = 0

    def _next(self) -> int:
        if self._idx >= len(self._values):
            return int(self._values[-1])
        value = int(self._values[self._idx])
        self._idx += 1
        return value

    def rand(self) -> int:
        return self._next()

    def rand_tagged(self, caller: int) -> int:
        _ = caller
        return self._next()


def _as_rng(value: object) -> Any:
    return value


def _status_default() -> save_status.GameStatus:
    return save_status.GameStatus.from_data(
        path=Path("game.cfg"),
        data=save_status.default_status_data(),
        dirty=False,
    )


def test_prepare_weapon_availability_includes_survival_defaults() -> None:
    state = GameplayState()
    state.game_mode = GameMode.SURVIVAL

    prepare_weapon_availability(state)

    assert state.weapon_available[WeaponId.PISTOL]
    assert state.weapon_available[WeaponId.ASSAULT_RIFLE]
    assert state.weapon_available[WeaponId.SHOTGUN]
    # Not native: every fireable weapon is unlocked regardless of mode -
    # except the shelved roster in weapon_runtime.availability.INACTIVE_WEAPON_IDS
    # (Submachine Gun among them - see test_prepare_weapon_availability_excludes_inactive_weapons).
    assert state.weapon_available[WeaponId.FLAMETHROWER]


def test_prepare_weapon_availability_ignores_quest_progress() -> None:
    # Not native: the mod drops quest-gated weapon unlocks entirely - even
    # with zero quest progress, everything droppable is already unlocked.
    status = _status_default()
    status.quest_unlock_index = 0

    state = GameplayState()
    state.status = status
    state.game_mode = GameMode.QUESTS

    prepare_weapon_availability(state)

    assert state.weapon_available[WeaponId.PISTOL]
    assert state.weapon_available[WeaponId.ASSAULT_RIFLE]
    assert state.weapon_available[WeaponId.SHOTGUN]


def test_prepare_weapon_availability_excludes_special_handout_weapons() -> None:
    # Shrinkifier 5K and Blade Gun are only ever granted by Survival's own
    # scripted handout triggers (gameplay.py::survival_update_weapon_handouts)
    # and immediately revoked back to Pistol if picked up any other way
    # (survival_enforce_reward_weapon_guard) - rolling them from a normal
    # Weapon bonus would just be an instant, confusing revert.
    state = GameplayState()
    prepare_weapon_availability(state)

    assert not state.weapon_available[WeaponId.SHRINKIFIER_5K]
    assert not state.weapon_available[WeaponId.BLADE_GUN]


def test_prepare_weapon_availability_excludes_spider_plasma() -> None:
    # Enemy-only weapon stat block (Spider Plasma Shooter's own attack) -
    # never meant to be a player pickup.
    state = GameplayState()
    prepare_weapon_availability(state)

    assert not state.weapon_available[WeaponId.SPIDER_PLASMA]


def test_prepare_weapon_availability_excludes_inactive_weapons() -> None:
    # weapon_runtime.availability.INACTIVE_WEAPON_IDS - shelved out of the
    # active roster while the crit/build design settles. Still in
    # WEAPON_TABLE and still fireable via the debug weapon cycle, just not
    # droppable/unlockable.
    from crimson.weapon_runtime.availability import INACTIVE_WEAPON_IDS

    state = GameplayState()
    prepare_weapon_availability(state)

    for weapon_id in INACTIVE_WEAPON_IDS:
        assert not state.weapon_available[weapon_id], weapon_id


def test_prepare_weapon_availability_keeps_full_version_unlocks_in_demo_mode() -> None:
    status = _status_default()
    status.quest_unlock_index_full = 0x28
    state = GameplayState(status=status, demo_mode_active=True)

    prepare_weapon_availability(state)

    assert state.weapon_available[WeaponId.SPLITTER_GUN]


def test_weapon_pick_random_available_enforces_unlocked() -> None:
    state = GameplayState(rng=_as_rng(_SeqRng([1, 0])))
    state.game_mode = GameMode.QUESTS
    prepare_weapon_availability(state)
    # Force everything but Pistol locked, to prove the picker still respects
    # per-weapon availability rather than just always succeeding on the first draw.
    for weapon_id in range(1, len(state.weapon_available)):
        state.weapon_available[weapon_id] = weapon_id == WeaponId.PISTOL

    picked = weapon_pick_random_available(state)

    assert picked == WeaponId.PISTOL
    assert isinstance(picked, WeaponId)


def test_weapon_pick_random_available_rejects_uninitialized_availability() -> None:
    rng = _SeqRng([0])
    state = GameplayState(rng=_as_rng(rng))

    with pytest.raises(RuntimeError, match="call prepare_weapon_availability"):
        weapon_pick_random_available(state)

    assert rng._idx == 0


def test_weapon_pick_random_available_has_no_synthetic_retry_cap() -> None:
    state = GameplayState(rng=_as_rng(_SeqRng([1] * 1001 + [0])))
    state.weapon_available[WeaponId.PISTOL] = True

    assert weapon_pick_random_available(state) == WeaponId.PISTOL


def test_weapon_pick_random_available_rerolls_used_weapons() -> None:
    status = _status_default()
    status.increment_weapon_usage_for_weapon_id(WeaponId.PISTOL)

    state = GameplayState(rng=_as_rng(_SeqRng([0, 0, 1])))
    state.status = status
    state.game_mode = GameMode.SURVIVAL
    prepare_weapon_availability(state)

    assert weapon_pick_random_available(state) == WeaponId.ASSAULT_RIFLE


def test_weapon_pick_random_available_tags_exact_native_callers_on_reroll() -> None:
    status = _status_default()
    status.increment_weapon_usage_for_weapon_id(WeaponId.PISTOL)

    rng = ScriptedCrand([0, 0, 1])
    state = GameplayState(rng=rng)
    state.status = status
    state.game_mode = GameMode.SURVIVAL
    prepare_weapon_availability(state)

    assert weapon_pick_random_available(state) == WeaponId.ASSAULT_RIFLE
    assert [record.caller for record in rng.records_since()] == [
        RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_PICK,
        RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_REROLL_GATE,
        RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_REROLL_PICK,
    ]
