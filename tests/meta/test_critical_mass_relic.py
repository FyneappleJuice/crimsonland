from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import critical_mass
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime import crit as crit_module
from crimson.weapon_runtime.crit import CRIT_MULTIPLIER
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature


@pytest.fixture(autouse=True)
def _critical_mass_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.CRITICAL_MASS_LOW),))


def _crowd(count: int, *, distance: float) -> list:
    return [_creature(pos=Vec2(distance, float(i)), hp=100.0) for i in range(count)]


def test_radius_counts_enemies_out_to_400() -> None:
    assert critical_mass.CRITICAL_MASS_RADIUS == 400.0
    assert critical_mass.crit_bonus_chance(Vec2(), _crowd(7, distance=380.0)) == pytest.approx(0.144)
    assert critical_mass.crit_bonus_chance(Vec2(), _crowd(7, distance=420.0)) == 0.0


def _rifle_damage_vs_no_relic(monkeypatch: pytest.MonkeyPatch, relic: RelicId, enemies: int) -> float:
    """Average-damage multiplier of a Rifle (20% base, 2.0x) with the relic,
    relative to no relic - straight from the same inputs fire.py rolls with."""
    from crimson.weapon_runtime.crit import crit_chance_for_weapon

    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(relic),))
    crowd = _crowd(enemies, distance=300.0)
    base = crit_chance_for_weapon(WeaponId.ASSAULT_RIFLE)
    chance = min(1.0, base + critical_mass.crit_bonus_chance(Vec2(), crowd))
    mult = CRIT_MULTIPLIER * critical_mass.crit_mult_penalty_mult(Vec2(), crowd)
    return (1.0 + chance * (mult - 1.0)) / (1.0 + base * (CRIT_MULTIPLIER - 1.0))


@pytest.mark.parametrize(("relic", "gain"), [(RelicId.CRITICAL_MASS_LOW, 0.12)])
def test_rifle_gains_the_tier_value_at_seven_enemies(monkeypatch: pytest.MonkeyPatch, relic: RelicId, gain: float) -> None:
    assert _rifle_damage_vs_no_relic(monkeypatch, relic, 7) == pytest.approx(1.0 + gain)
    # Keeps growing to the 10-enemy cap, then stops.
    at_cap = _rifle_damage_vs_no_relic(monkeypatch, relic, 10)
    assert at_cap == pytest.approx(1.0 + gain * 10.0 / 7.0)
    assert _rifle_damage_vs_no_relic(monkeypatch, relic, 15) == pytest.approx(at_cap)


def test_penalty_applies_below_five_enemies_only(monkeypatch: pytest.MonkeyPatch) -> None:
    crowd4, crowd5 = _crowd(4, distance=300.0), _crowd(5, distance=300.0)
    assert critical_mass.crit_mult_penalty_mult(Vec2(), crowd4) == pytest.approx(0.75)
    assert critical_mass.crit_mult_penalty_mult(Vec2(), crowd5) == 1.0


@pytest.mark.parametrize(
    "weapon_id",
    [WeaponId.ROCKET_LAUNCHER, WeaponId.SEEKER_ROCKETS, WeaponId.MINI_ROCKET_SWARMERS, WeaponId.ROCKET_MINIGUN],
)
@pytest.mark.parametrize(("crowd_size", "expected_mult"), [(0, CRIT_MULTIPLIER * 0.75), (10, CRIT_MULTIPLIER)])
def test_rockets_read_critical_mass(
    monkeypatch: pytest.MonkeyPatch,
    weapon_id: WeaponId,
    crowd_size: int,
    expected_mult: float,
) -> None:
    # Force every roll to crit, so the stamped crit_mult shows the relic's
    # thin-crowd multiplier penalty (or its absence).
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 0.0)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, weapon_id, state=state)
    creatures = _crowd(crowd_size, distance=300.0)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=Vec2(100.0, 0.0)),
            dt=0.016,
            state=state,
            creatures=creatures,
        ),
    )
    rockets = [e for e in state.secondary_projectiles.entries if e.active]
    assert rockets
    for rocket in rockets:
        assert rocket.did_crit is True
        # Swarmers fold their own +damage into crit_mult; divide it back out.
        base = float(rocket.crit_mult)
        if weapon_id == WeaponId.MINI_ROCKET_SWARMERS:
            from crimson.weapon_runtime.fire import _MINI_ROCKET_SWARMERS_DAMAGE_MULT

            base /= _MINI_ROCKET_SWARMERS_DAMAGE_MULT
        assert base == pytest.approx(expected_mult)
