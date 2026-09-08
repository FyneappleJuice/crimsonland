from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.progression import refresh_player_stats
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon
from crimson.weapon_runtime.plasma_heat import (
    PLASMA_HEAT_H,
    plasma_energy_heat_mult,
    plasma_heat_fraction,
)
from crimson.weapons import WEAPON_BY_ID, WeaponId
from grim.geom import Vec2

_PLASMA_CANNON_CLIP = WEAPON_BY_ID[WeaponId.PLASMA_CANNON].clip_size  # 3
_PLASMA_MINIGUN_CLIP = WEAPON_BY_ID[WeaponId.PLASMA_MINIGUN].clip_size  # 30


# --- the formula --------------------------------------------------------


def test_ramps_zero_to_H_across_a_stock_clip_regardless_of_clip_size() -> None:
    for weapon, clip in (
        (WeaponId.PLASMA_CANNON, _PLASMA_CANNON_CLIP),
        (WeaponId.PLASMA_MINIGUN, _PLASMA_MINIGUN_CLIP),
    ):
        fresh = plasma_heat_fraction(int(weapon), clip_size=clip, ammo_after_shot=clip)
        last = plasma_heat_fraction(int(weapon), clip_size=clip, ammo_after_shot=0.0)
        assert fresh == pytest.approx(0.0)
        assert last == pytest.approx(PLASMA_HEAT_H)


def test_extra_clip_size_pushes_the_ramp_past_H() -> None:
    # +20% clip on the minigun -> the last round sits at 1.2 * H.
    wide = round(_PLASMA_MINIGUN_CLIP * 1.2)
    last = plasma_heat_fraction(int(WeaponId.PLASMA_MINIGUN), clip_size=wide, ammo_after_shot=0.0)
    assert last == pytest.approx(PLASMA_HEAT_H * wide / _PLASMA_MINIGUN_CLIP)
    assert last > PLASMA_HEAT_H


def test_the_heat_ramp_is_always_on_and_unaffected_by_wpu() -> None:
    # WPU no longer touches the clip-heat ramp - plasma's WPU is just fire rate.
    m = plasma_energy_heat_mult(int(WeaponId.PLASMA_MINIGUN), clip_size=_PLASMA_MINIGUN_CLIP, ammo_after_shot=0.0)
    assert m == pytest.approx(1.0 + PLASMA_HEAT_H)


def test_non_plasma_weapons_get_no_heat() -> None:
    assert plasma_heat_fraction(int(WeaponId.PISTOL), clip_size=12, ammo_after_shot=0.0) == 0.0
    assert plasma_heat_fraction(int(WeaponId.ION_CANNON), clip_size=3, ammo_after_shot=0.0) == 0.0


# --- stamped onto the bolt at fire time --------------------------------


def _fire_plasma(*, ammo: float, clip_size: int) -> float:
    state = GameplayState()
    player = PlayerState(
        index=0,
        pos=Vec2(),
        weapon=WeaponSlot(weapon_id=WeaponId.PLASMA_RIFLE, clip_size=clip_size, ammo=ammo),
    )
    refresh_player_stats([player])
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(1.0, 0.0)), dt=0.1, state=state),
    )
    live = [e for e in state.projectiles.entries if e.active]
    assert live, "plasma rifle should have spawned a bolt"
    return float(live[0].energy_heat_mult)


def test_bolt_carries_the_clip_heat_from_the_moment_it_was_fired() -> None:
    stock = WEAPON_BY_ID[WeaponId.PLASMA_RIFLE].clip_size  # 20
    # first round of a full clip: ammo 20 -> 19, almost cold
    first = _fire_plasma(ammo=stock, clip_size=stock)
    assert first == pytest.approx(1.0 + PLASMA_HEAT_H * 1 / stock, rel=1e-4)
    # last round: ammo 1 -> 0, full H
    last = _fire_plasma(ammo=1.0, clip_size=stock)
    assert last == pytest.approx(1.0 + PLASMA_HEAT_H, rel=1e-4)
