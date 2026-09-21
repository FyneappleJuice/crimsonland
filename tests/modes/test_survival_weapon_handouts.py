from __future__ import annotations

import pytest

from crimson.creatures.runtime import CreaturePool
from crimson.gameplay import (
    GameplayState,
    gameplay_enforce_weapon_guards,
    survival_enforce_reward_weapon_guard,
    survival_update_weapon_handouts,
)
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import INACTIVE_WEAPON_IDS, prepare_weapon_availability, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2


def test_survival_handout_time_gate_skips_shrinkifier_while_shelved() -> None:
    # Shrinkifier 5K is in weapon_runtime.availability.INACTIVE_WEAPON_IDS -
    # the one-time handout window still closes (bookkeeping below still
    # fires, matching native), it just never actually hands out the weapon.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(512.0, 512.0))
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    survival_update_weapon_handouts(
        state,
        [player],
        survival_elapsed_ms=64001.0,
    )

    assert player.weapon.weapon_id == WeaponId.PISTOL
    assert state.survival_reward_weapon_guard_id != WeaponId.SHRINKIFIER_5K
    assert state.survival_reward_handout_enabled is False
    assert state.survival_reward_damage_seen is True
    assert state.survival_reward_fire_seen is True


def test_survival_handout_time_gate_assigns_shrinkifier_when_reactivated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same scenario with Shrinkifier 5K pulled back out of the inactive pool -
    # the underlying native handout mechanic itself is untouched.
    monkeypatch.setattr(
        "crimson.gameplay.INACTIVE_WEAPON_IDS",
        tuple(w for w in INACTIVE_WEAPON_IDS if w != WeaponId.SHRINKIFIER_5K),
    )
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(512.0, 512.0))
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    survival_update_weapon_handouts(
        state,
        [player],
        survival_elapsed_ms=64001.0,
    )

    assert player.weapon.weapon_id == WeaponId.SHRINKIFIER_5K
    assert state.survival_reward_weapon_guard_id == WeaponId.SHRINKIFIER_5K
    assert state.survival_reward_handout_enabled is False
    assert state.survival_reward_damage_seen is True
    assert state.survival_reward_fire_seen is True


def test_survival_handout_time_gate_consumes_gate_even_without_pistol() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(512.0, 512.0))
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=state)

    survival_update_weapon_handouts(
        state,
        [player],
        survival_elapsed_ms=64001.0,
    )

    assert player.weapon.weapon_id == WeaponId.ASSAULT_RIFLE
    assert state.survival_reward_weapon_guard_id == WeaponId.PISTOL
    assert state.survival_reward_handout_enabled is False
    assert state.survival_reward_damage_seen is True
    assert state.survival_reward_fire_seen is True


def test_survival_handouts_are_single_player_only() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(512.0, 512.0))
    player1 = PlayerState(index=1, pos=Vec2(512.0, 512.0))
    weapon_assign_player(player0, WeaponId.PISTOL, state=state)
    weapon_assign_player(player1, WeaponId.PISTOL, state=state)

    survival_update_weapon_handouts(
        state,
        [player0, player1],
        survival_elapsed_ms=64001.0,
    )

    assert player0.weapon.weapon_id == WeaponId.PISTOL
    assert player1.weapon.weapon_id == WeaponId.PISTOL
    assert state.survival_reward_handout_enabled is True
    assert state.survival_reward_damage_seen is False
    assert state.survival_reward_fire_seen is False


def test_survival_handout_centroid_gate_assigns_blade_gun() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0), health=14.0)
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    state.survival_reward_handout_enabled = False
    state.survival_reward_damage_seen = True
    state.survival_reward_fire_seen = False
    state.survival_recent_death_count = 3
    state.survival_recent_death_pos = [
        Vec2(90.0, 100.0),
        Vec2(100.0, 90.0),
        Vec2(110.0, 110.0),
    ]

    survival_update_weapon_handouts(
        state,
        [player],
        survival_elapsed_ms=0.0,
    )

    assert player.weapon.weapon_id == WeaponId.BLADE_GUN
    assert state.survival_reward_weapon_guard_id == WeaponId.BLADE_GUN
    assert state.survival_reward_fire_seen is True
    assert state.survival_reward_handout_enabled is False


def test_survival_handout_centroid_keeps_native_pc24_radius_boundary() -> None:
    state = GameplayState()
    player = PlayerState(
        index=0,
        pos=Vec2(-97.64498138427734, 544.9747924804688),
        health=14.0,
    )
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    state.survival_reward_handout_enabled = False
    state.survival_reward_damage_seen = True
    state.survival_reward_fire_seen = False
    state.survival_recent_death_count = 3
    state.survival_recent_death_pos = [
        Vec2(315.8760681152344, 836.8428344726562),
        Vec2(1131.1593017578125, 1372.648681640625),
        Vec2(-1691.9703369140625, -574.5670776367188),
    ]

    survival_update_weapon_handouts(
        state,
        [player],
        survival_elapsed_ms=0.0,
    )

    assert player.weapon.weapon_id == WeaponId.PISTOL
    assert state.survival_reward_fire_seen is False


def test_creature_handle_death_tracks_survival_recent_death_samples() -> None:
    state = GameplayState()
    prepare_weapon_availability(state)
    player = PlayerState(index=0, pos=Vec2(512.0, 512.0))
    pool = CreaturePool()
    state.survival_reward_fire_seen = True
    state.survival_reward_handout_enabled = True

    for idx, pos in enumerate((Vec2(10.0, 20.0), Vec2(30.0, 40.0), Vec2(50.0, 60.0))):
        creature = pool.entries[idx]
        creature.active = True
        creature.hp = 0.0
        creature.reward_value = 0.0
        creature.pos = pos
        pool.handle_death(
            idx,
            state=state,
            players=[player],
            rng=state.rng,
            world_width=1024.0,
            world_height=1024.0,
            fx_queue=None,
        )

    assert int(state.survival_recent_death_count) == 3
    assert state.survival_recent_death_pos == [Vec2(10.0, 20.0), Vec2(30.0, 40.0), Vec2(50.0, 60.0)]
    assert state.survival_reward_fire_seen is False
    assert state.survival_reward_handout_enabled is False


def test_survival_weapon_guard_reverts_mismatched_temporary_weapons() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2())
    player1 = PlayerState(index=1, pos=Vec2())
    weapon_assign_player(player0, WeaponId.SHRINKIFIER_5K, state=state)
    weapon_assign_player(player1, WeaponId.BLADE_GUN, state=state)
    state.survival_reward_weapon_guard_id = WeaponId.SHRINKIFIER_5K

    survival_enforce_reward_weapon_guard(state, [player0, player1])

    assert player0.weapon.weapon_id == WeaponId.SHRINKIFIER_5K
    assert player1.weapon.weapon_id == WeaponId.PISTOL


def test_gameplay_weapon_guard_never_revokes_splitter_gun() -> None:
    # Not native: Splitter Gun is unconditionally unlocked (weapon_runtime/
    # availability.py), so the native full-game-unlock revocation gate is gone.
    state = GameplayState()
    players = [PlayerState(index=index, pos=Vec2()) for index in range(3)]
    for player in players:
        weapon_assign_player(player, WeaponId.SPLITTER_GUN, state=state)

    gameplay_enforce_weapon_guards(state, players)

    assert all(player.weapon.weapon_id == WeaponId.SPLITTER_GUN for player in players)
