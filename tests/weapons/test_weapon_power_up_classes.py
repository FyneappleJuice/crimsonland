from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import weapon_assign_player
from crimson.weapon_runtime.power_up import WPU_FLAME_DAMAGE_MULT, wpu_boosts_fire_rate
from crimson.weapons import WEAPON_BY_ID, WeaponId
from grim.geom import Vec2

# The normalized WPU levers (gameplay.py / assign.py).
_WPU_FIRE_RATE = 1.30   # cooldown decays this much faster -> fire interval / this
_WPU_RELOAD = 0.80


def _sustained_dps_gain(weapon: WeaponId) -> float:
    """Analytic sustained-DPS ratio: N*D / (N*C + R), WPU vs base."""
    w = WEAPON_BY_ID[weapon]
    n, c, r = w.clip_size, w.shot_cooldown, w.reload_time
    base = n / (n * c + r)
    hot = n / (n * c / _WPU_FIRE_RATE + r * _WPU_RELOAD)
    return hot / base - 1.0


# --- the normalized target: ~+30% DPS for everyone -------------------------


@pytest.mark.parametrize(
    "weapon",
    [WeaponId.PISTOL, WeaponId.ASSAULT_RIFLE, WeaponId.GAUSS_GUN, WeaponId.PLASMA_MINIGUN, WeaponId.ION_MINIGUN, WeaponId.RAYGUN],
)
def test_wpu_fire_rate_lever_lands_near_plus_30_percent(weapon: WeaponId) -> None:
    gain = _sustained_dps_gain(weapon)
    assert 0.24 <= gain <= 0.36, f"{weapon.name}: {gain:.1%}"


def test_scythe_and_stream_weapons_do_not_get_the_fire_rate_lever() -> None:
    assert wpu_boosts_fire_rate(int(WeaponId.EVIL_SCYTHE)) is False
    assert wpu_boosts_fire_rate(int(WeaponId.PISTOL)) is True
    assert wpu_boosts_fire_rate(int(WeaponId.FLAMETHROWER)) is True  # moot - fire rate is a no-op for a stream


def test_wpu_flame_lever_is_plus_30_percent_particle_damage() -> None:
    assert WPU_FLAME_DAMAGE_MULT == pytest.approx(1.30)


def test_wpu_reload_is_x0_8_for_fire_rate_weapons() -> None:
    from crimson.weapon_runtime.assign import player_start_reload

    state = GameplayState()
    state.bonuses.weapon_power_up = 999.0
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    player.weapon.ammo = 0.0
    player_start_reload(player, state, players=[player])
    base_reload = WEAPON_BY_ID[WeaponId.PISTOL].reload_time
    assert player.weapon.reload_timer == pytest.approx(base_reload * 0.8, abs=1e-3)
