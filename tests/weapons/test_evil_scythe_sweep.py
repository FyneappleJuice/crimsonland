from __future__ import annotations

import math

import pytest

from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime
from crimson.gameplay import GameplayState
from crimson.progression import refresh_player_stats
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime.scythe_sweep import (
    SCYTHE_ARC,
    SCYTHE_DAMAGE,
    SCYTHE_REACH,
    SCYTHE_SWING_DURATION_S,
    SCYTHE_WPU_ARC_MULT,
    SCYTHE_WPU_DAMAGE_MULT,
    SCYTHE_WPU_REACH_MULT,
    start_scythe_swing,
    update_scythe_swings,
)
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state


def _player_with_scythe(state: GameplayState) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.EVIL_SCYTHE, state=state)
    refresh_player_stats([player])
    return player


def _swing_to_completion(player: PlayerState, creatures, runtime) -> None:
    steps = int(SCYTHE_SWING_DURATION_S / 0.016) + 2
    for _ in range(steps):
        update_scythe_swings([player], creatures, 0.016, creature_damage_runtime=runtime)


def test_firing_starts_a_swing_and_alternates_direction() -> None:
    state = GameplayState()
    player = _player_with_scythe(state)
    assert player.weapon.clip_size == 2

    fire_weapon(WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state))
    assert player.scythe_swing.active
    first_dir = player.scythe_swing.direction

    player.weapon.shot_cooldown = 0.0
    _swing_to_completion(player, [], None)
    refresh_player_stats([player])
    fire_weapon(WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state))
    assert player.scythe_swing.direction == -first_dir  # left->right, then right->left


def test_a_creature_in_the_cone_takes_scythe_damage_once() -> None:
    state = GameplayState()
    player = _player_with_scythe(state)
    # dead ahead of the aim (+x), well inside reach
    creature = make_creature_state(pos=Vec2(SCYTHE_REACH * 0.6, 0.0), hp=100000.0, size=30.0)
    runtime = DirectCreatureDamageRuntime(creatures=[creature])

    start_scythe_swing(player, Vec2(200.0, 0.0), shots_fired_this_clip=0)
    _swing_to_completion(player, [creature], runtime)

    assert (100000.0 - creature.hp) == pytest.approx(SCYTHE_DAMAGE)
    assert not player.scythe_swing.active


def test_a_creature_behind_the_player_is_not_touched() -> None:
    state = GameplayState()
    player = _player_with_scythe(state)
    behind = make_creature_state(pos=Vec2(-SCYTHE_REACH * 0.6, 0.0), hp=1e9, size=30.0)
    runtime = DirectCreatureDamageRuntime(creatures=[behind])

    start_scythe_swing(player, Vec2(200.0, 0.0), shots_fired_this_clip=0)  # aiming +x
    _swing_to_completion(player, [behind], runtime)

    assert behind.hp == 1e9


def test_a_creature_beyond_reach_is_not_touched() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    far = make_creature_state(pos=Vec2(SCYTHE_REACH + 40.0, 0.0), hp=1e9, size=10.0)
    runtime = DirectCreatureDamageRuntime(creatures=[far])

    start_scythe_swing(player, Vec2(200.0, 0.0), shots_fired_this_clip=0)
    _swing_to_completion(player, [far], runtime)

    assert far.hp == 1e9


def test_the_full_cone_is_covered_edge_to_edge() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    # ring of creatures around the aim, from one arc edge to the other
    r = SCYTHE_REACH * 0.7
    creatures = []
    for k in range(9):
        rel = -SCYTHE_ARC * 0.5 + SCYTHE_ARC * (k / 8.0)
        creatures.append(make_creature_state(pos=Vec2(r * math.cos(rel), r * math.sin(rel)), hp=1e9, size=8.0))
    runtime = DirectCreatureDamageRuntime(creatures=creatures)

    start_scythe_swing(player, Vec2(200.0, 0.0), shots_fired_this_clip=0)
    _swing_to_completion(player, creatures, runtime)

    for c in creatures:
        assert c.hp == pytest.approx(1e9 - SCYTHE_DAMAGE)


def test_swing_ends_after_its_duration() -> None:
    player = PlayerState(index=0, pos=Vec2())
    start_scythe_swing(player, Vec2(1.0, 0.0), shots_fired_this_clip=0)

    update_scythe_swings([player], [], SCYTHE_SWING_DURATION_S - 0.01, creature_damage_runtime=None)
    assert player.scythe_swing.active
    update_scythe_swings([player], [], 0.02, creature_damage_runtime=None)
    assert not player.scythe_swing.active


def test_clip_of_two_then_reload() -> None:
    state = GameplayState()
    player = _player_with_scythe(state)

    fire_weapon(WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state))
    assert player.weapon.ammo == pytest.approx(1.0)
    assert not player.weapon.reload_active

    player.weapon.shot_cooldown = 0.0
    _swing_to_completion(player, [], None)
    refresh_player_stats([player])
    fire_weapon(WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state))
    assert player.weapon.ammo <= 0.0
    assert player.weapon.reload_active
    assert player.weapon.reload_timer == pytest.approx(0.5, abs=1e-3)


# --- Weapon Power Up: ~+30% damage, same cadence --------------------------


def test_wpu_hardens_the_swing_by_about_30_percent() -> None:
    plain = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    start_scythe_swing(plain, Vec2(200.0, 0.0), shots_fired_this_clip=0, weapon_power_up=False)
    powered = PlayerState(index=1, pos=Vec2(0.0, 0.0))
    start_scythe_swing(powered, Vec2(200.0, 0.0), shots_fired_this_clip=0, weapon_power_up=True)

    assert SCYTHE_WPU_DAMAGE_MULT == pytest.approx(1.3)
    assert powered.scythe_swing.damage == pytest.approx(SCYTHE_DAMAGE * SCYTHE_WPU_DAMAGE_MULT)
    assert powered.scythe_swing.arc == pytest.approx(SCYTHE_ARC * SCYTHE_WPU_ARC_MULT)
    assert powered.scythe_swing.reach == pytest.approx(SCYTHE_REACH * SCYTHE_WPU_REACH_MULT)

    c_plain = make_creature_state(pos=Vec2(SCYTHE_REACH * 0.6, 0.0), hp=1e9, size=20.0)
    c_pow = make_creature_state(pos=Vec2(SCYTHE_REACH * 0.6, 0.0), hp=1e9, size=20.0)
    rt_plain = DirectCreatureDamageRuntime(creatures=[c_plain])
    rt_pow = DirectCreatureDamageRuntime(creatures=[c_pow])
    _swing_to_completion(plain, [c_plain], rt_plain)
    _swing_to_completion(powered, [c_pow], rt_pow)

    assert (1e9 - c_plain.hp) == pytest.approx(SCYTHE_DAMAGE)
    assert (1e9 - c_pow.hp) == pytest.approx(SCYTHE_DAMAGE * 1.3)


def test_wpu_does_not_speed_up_the_scythe_cadence() -> None:
    from crimson.weapon_runtime.power_up import wpu_boosts_fire_rate

    assert wpu_boosts_fire_rate(int(WeaponId.EVIL_SCYTHE)) is False
    assert wpu_boosts_fire_rate(int(WeaponId.PISTOL)) is True

    # reload timer under WPU is still the raw 0.5s, unscaled
    state = GameplayState()
    state.bonuses.weapon_power_up = 5.0
    player = _player_with_scythe(state)
    player.weapon.ammo = 0.0
    from crimson.weapon_runtime.assign import player_start_reload

    player_start_reload(player, state, players=[player])
    assert player.weapon.reload_timer == pytest.approx(0.5, abs=1e-3)
