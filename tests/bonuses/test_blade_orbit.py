from __future__ import annotations

import math

import pytest

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.bonuses.blade_orbit import (
    BLADE_COUNT,
    BLADE_CREATURE_RADIUS_FACTOR,
    BLADE_DURATION_S,
    BLADE_HIT_COOLDOWN_S,
    BLADE_HIT_DAMAGE,
    BLADE_HIT_RADIUS,
    BLADE_OMEGA,
    BLADE_RADIUS,
    BLADE_REVOLUTIONS,
    BLADE_SOUND_LOOP_S,
    blade_orbit_offsets,
    blade_sound_loop_index,
    update_blade_orbits,
)
from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime
from crimson.gameplay import GameplayState
from crimson.sim.state_types import BladeOrbitState, PlayerState
from grim.geom import Vec2
from tests.support.factories import make_creature_state


def _active_orbit(theta0: float = 0.0) -> BladeOrbitState:
    return BladeOrbitState(active=True, elapsed=0.0, theta0=theta0)


def test_pickup_activates_a_five_blade_orbit() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(500.0, 500.0))

    bonus_apply(state, player, BonusId.BLADE, amount=8, origin=player.pos, creatures=[], players=[player])

    assert player.blade_orbit.active
    assert player.blade_orbit.elapsed == 0.0
    assert len(blade_orbit_offsets(player.blade_orbit)) == BLADE_COUNT


def test_blades_ride_a_circle_centred_on_the_player_evenly_phased() -> None:
    offsets = blade_orbit_offsets(_active_orbit())
    for k, off in enumerate(offsets):
        theta = k * (math.tau / BLADE_COUNT)
        assert off.x == pytest.approx(BLADE_RADIUS * math.cos(theta))
        assert off.y == pytest.approx(BLADE_RADIUS * math.sin(theta))
        assert math.hypot(off.x, off.y) == pytest.approx(BLADE_RADIUS)  # a circle, not an ellipse
    # centred: the 5 blades sum to ~0
    assert abs(sum(o.x for o in offsets)) < 1e-9
    assert abs(sum(o.y for o in offsets)) < 1e-9


def test_no_precession_the_ring_orientation_never_changes() -> None:
    early = blade_orbit_offsets(BladeOrbitState(active=True, elapsed=0.0))
    # advance a quarter turn: blade 0 should just be where blade ~1.25 was,
    # i.e. every offset still lands exactly on the same circle with no skew
    later = blade_orbit_offsets(BladeOrbitState(active=True, elapsed=BLADE_DURATION_S * 0.25))
    for off in early + later:
        assert math.hypot(off.x, off.y) == pytest.approx(BLADE_RADIUS)


def test_effect_makes_the_configured_revolutions_over_the_duration_then_ends() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.blade_orbit = _active_orbit()

    update_blade_orbits([player], [], BLADE_DURATION_S - 0.01, creature_damage_runtime=None)
    assert player.blade_orbit.active
    assert (BLADE_OMEGA * player.blade_orbit.elapsed) / math.tau < BLADE_REVOLUTIONS

    update_blade_orbits([player], [], 0.02, creature_damage_runtime=None)
    assert not player.blade_orbit.active

    assert round((BLADE_OMEGA * BLADE_DURATION_S) / math.tau, 6) == BLADE_REVOLUTIONS


def test_test_mode_keeps_the_orbit_permanently_on() -> None:
    from crimson.test_mode import set_test_mode_enabled

    set_test_mode_enabled(True)
    try:
        player = PlayerState(index=0, pos=Vec2())
        assert not player.blade_orbit.active

        # first tick activates it; it never deactivates and elapsed wraps
        for _ in range(int(BLADE_DURATION_S * 3 / 0.1) + 5):
            update_blade_orbits([player], [], 0.1, creature_damage_runtime=None)
            assert player.blade_orbit.active
        assert player.blade_orbit.elapsed < BLADE_DURATION_S
    finally:
        set_test_mode_enabled(None)


def test_orbit_is_not_forced_on_outside_test_mode() -> None:
    player = PlayerState(index=0, pos=Vec2())
    update_blade_orbits([player], [], 0.1, creature_damage_runtime=None)
    assert not player.blade_orbit.active


def test_a_blade_sweeping_a_creature_deals_contact_damage_once_per_cooldown() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.blade_orbit = _active_orbit()
    # blade 0 at t=0 sits at (+R, 0); park a creature right on it
    creature = make_creature_state(pos=Vec2(BLADE_RADIUS, 0.0), hp=100000.0, size=10.0)
    runtime = DirectCreatureDamageRuntime(creatures=[creature])

    update_blade_orbits([player], [creature], 0.016, creature_damage_runtime=runtime)
    assert creature.hp == 100000.0 - BLADE_HIT_DAMAGE
    assert 0 in player.blade_orbit.hit_cooldowns

    update_blade_orbits([player], [creature], 0.016, creature_damage_runtime=runtime)
    assert creature.hp == 100000.0 - BLADE_HIT_DAMAGE  # still on cooldown


def test_cooldown_lets_a_blade_hit_the_same_target_again_later() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.blade_orbit = _active_orbit()
    creature = make_creature_state(pos=Vec2(0.0, 0.0), hp=100000.0, size=4000.0)
    runtime = DirectCreatureDamageRuntime(creatures=[creature])

    update_blade_orbits([player], [creature], 0.001, creature_damage_runtime=runtime)
    assert round((100000.0 - creature.hp) / BLADE_HIT_DAMAGE) == 1  # one blade lands per tick

    update_blade_orbits([player], [creature], 0.001, creature_damage_runtime=runtime)
    assert round((100000.0 - creature.hp) / BLADE_HIT_DAMAGE) == 1  # still on cooldown

    update_blade_orbits([player], [creature], BLADE_HIT_COOLDOWN_S + 0.01, creature_damage_runtime=runtime)
    assert round((100000.0 - creature.hp) / BLADE_HIT_DAMAGE) == 2  # cooldown lapsed


@pytest.mark.parametrize("creature_size", [32.0, 45.0, 55.0, 65.0, 80.0])
def test_reach_scales_with_creature_size_so_bigger_aliens_connect_sooner(creature_size: float) -> None:
    reach = BLADE_HIT_RADIUS + creature_size * BLADE_CREATURE_RADIUS_FACTOR
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.blade_orbit = _active_orbit()
    runtime_hit = DirectCreatureDamageRuntime(
        creatures=[make_creature_state(pos=Vec2(BLADE_RADIUS + reach - 1.0, 0.0), hp=1e9, size=creature_size)],
    )
    runtime_miss = DirectCreatureDamageRuntime(
        creatures=[make_creature_state(pos=Vec2(BLADE_RADIUS + reach + 5.0, 0.0), hp=1e9, size=creature_size)],
    )
    update_blade_orbits([player], runtime_hit.creatures, 0.001, creature_damage_runtime=runtime_hit)
    update_blade_orbits([player], runtime_miss.creatures, 0.001, creature_damage_runtime=runtime_miss)
    assert runtime_hit.creatures[0].hp < 1e9  # just inside reach -> hit
    assert runtime_miss.creatures[0].hp == 1e9  # just outside -> no hit


def test_inactive_orbit_produces_no_offsets_and_no_damage() -> None:
    player = PlayerState(index=0, pos=Vec2())
    creature = make_creature_state(pos=Vec2(BLADE_RADIUS, 0.0), hp=100.0)
    runtime = DirectCreatureDamageRuntime(creatures=[creature])

    assert blade_orbit_offsets(player.blade_orbit) == []
    update_blade_orbits([player], [creature], 0.5, creature_damage_runtime=runtime)
    assert creature.hp == 100.0


def test_sound_loop_index_advances_once_per_loop_period() -> None:
    assert blade_sound_loop_index(0.0) == 0
    assert blade_sound_loop_index(BLADE_SOUND_LOOP_S * 0.9) == 0
    assert blade_sound_loop_index(BLADE_SOUND_LOOP_S * 1.1) == 1
    assert blade_sound_loop_index(BLADE_SOUND_LOOP_S * 3.5) == 3
