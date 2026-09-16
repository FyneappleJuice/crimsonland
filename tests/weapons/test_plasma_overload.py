from __future__ import annotations

import pytest

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.gameplay import GameplayState
from crimson.math_parity import f32
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _fire(weapon_id: WeaponId, *, plasma_overload_timer: float = 0.0, fire_bullets_timer: float = 0.0):
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.plasma_overload_timer = float(plasma_overload_timer)
    player.fire_bullets_timer = float(fire_bullets_timer)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )
    return state, player


def test_pistol_fires_two_parallel_plasma_rifle_bolts_when_active() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 2
    assert all(p.type_id == ProjectileTemplateId.PLASMA_RIFLE for p in live)


def test_the_two_bolts_share_a_heading_but_have_different_positions() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 2
    assert float(f32(live[0].angle)) == pytest.approx(float(f32(live[1].angle)))
    assert live[0].pos != live[1].pos


def test_pistol_fires_normally_when_inactive() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=0.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].type_id == ProjectileTemplateId.PISTOL


def test_fire_bullets_takes_priority_over_plasma_overload() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0, fire_bullets_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].type_id == ProjectileTemplateId.FIRE_BULLETS


def test_cooldown_is_pinned_to_a_fixed_value_regardless_of_equipped_weapon() -> None:
    _, plasma_cannon_player = _fire(WeaponId.PLASMA_CANNON, plasma_overload_timer=5.0)
    _, pistol_player = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0)

    expected_cooldown = float(f32(0.1))
    assert float(plasma_cannon_player.weapon.shot_cooldown) == pytest.approx(expected_cooldown)
    assert float(pistol_player.weapon.shot_cooldown) == pytest.approx(expected_cooldown)


def test_spread_heat_grows_slower_than_any_real_weapons_own_rate() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.SHOTGUN, state=state)
    player.plasma_overload_timer = 5.0

    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )

    # Shotgun's own spread_heat_inc (0.27) would drive this well above the
    # Assault Rifle's 0.09 - Plasma Overload should stay tighter than that.
    assault_rifle_spread_inc = float(f32(0.09 * 1.3))
    assert float(player.spread_heat) < assault_rifle_spread_inc


def test_shotgun_still_only_fires_the_two_bolts_not_its_own_pellet_count() -> None:
    state, _ = _fire(WeaponId.SHOTGUN, plasma_overload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 2


def test_no_ammo_cost_while_active() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    player.plasma_overload_timer = 5.0
    ammo_before = float(player.weapon.ammo)

    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )

    assert float(player.weapon.ammo) == pytest.approx(ammo_before)
    assert player.weapon.reload_timer <= 0.0


def test_pickup_immediately_refills_the_clip_and_clears_reload() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.SHOTGUN, state=state)
    player.weapon.ammo = 0.0
    player.weapon.reload_timer = 1.0
    player.weapon.shot_cooldown = 0.5

    bonus_apply(
        state,
        player,
        BonusId.PLASMA_OVERLOAD,
        origin=Vec2(),
        creatures=(),
        players=[player],
    )

    assert float(player.weapon.ammo) == pytest.approx(float(player.weapon.clip_size))
    assert player.weapon.reload_timer == 0.0
    assert player.weapon.shot_cooldown == 0.0
    assert float(player.plasma_overload_timer) > 0.0
