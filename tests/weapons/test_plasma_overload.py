from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime.plasma_heat import PLASMA_HEAT_H
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


def test_pistol_fires_the_multiplasma_fan_when_active() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 5  # Multi-Plasma's fixed fan size
    assert {p.type_id for p in live} == {ProjectileTemplateId.PLASMA_RIFLE, ProjectileTemplateId.PLASMA_MINIGUN}


def test_pistol_fires_normally_when_inactive() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=0.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].type_id == ProjectileTemplateId.PISTOL


def test_every_fan_bolt_carries_a_flat_plus_h_heat_bonus() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 5
    for p in live:
        assert p.energy_heat_mult == pytest.approx(1.0 + PLASMA_HEAT_H)


def test_fire_bullets_takes_priority_over_plasma_overload() -> None:
    state, _ = _fire(WeaponId.PISTOL, plasma_overload_timer=5.0, fire_bullets_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].type_id == ProjectileTemplateId.FIRE_BULLETS
