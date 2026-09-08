from __future__ import annotations

import pytest

from crimson.creatures.ignite import (
    IGNITE_DPS,
    IGNITE_DURATION_S,
    IGNITE_HEAT_DECAY_PER_S,
    IGNITE_HEAT_PER_HIT,
    IGNITE_HEAT_THRESHOLD,
    flame_ignite_accumulate,
    ignite_tick,
)
from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def _creature(hp: float = 1000.0) -> CreatureState:
    return CreatureState(active=True, hp=hp, max_hp=hp, pos=Vec2(), size=45.0, lifecycle_stage=16.0)


def _tick(creature: CreatureState, dt: float, *, runtime=None) -> bool:
    return ignite_tick(
        creature,
        creature_index=0,
        dt=dt,
        state=GameplayState(),
        players=[PlayerState(index=0, pos=Vec2())],
        rng=GameplayState().rng,
        detail_preset=5,
        creature_damage_runtime=runtime,
    )


def test_heat_accumulates_and_ignites_at_the_threshold() -> None:
    c = _creature()
    hits = 0
    while c.ignite_timer <= 0.0:
        flame_ignite_accumulate(c, IGNITE_HEAT_PER_HIT)
        hits += 1
    assert hits == pytest.approx(IGNITE_HEAT_THRESHOLD / IGNITE_HEAT_PER_HIT, abs=1)
    assert c.ignite_timer == IGNITE_DURATION_S
    assert c.ignite_heat == 0.0  # consumed on ignite


def test_a_burning_creature_cannot_be_re_ignited_until_it_expires() -> None:
    c = _creature()
    c.ignite_timer = IGNITE_DURATION_S
    for _ in range(50):
        flame_ignite_accumulate(c, IGNITE_HEAT_PER_HIT)
    assert c.ignite_heat == 0.0  # heat is ignored while burning
    assert c.ignite_timer == IGNITE_DURATION_S


def test_heat_decays_while_not_burning_so_a_graze_cools_off() -> None:
    c = _creature()
    flame_ignite_accumulate(c, IGNITE_HEAT_THRESHOLD * 0.6)  # not enough to ignite
    assert c.ignite_timer <= 0.0
    _tick(c, 1.0)  # one second of cooling
    assert c.ignite_heat == pytest.approx(IGNITE_HEAT_THRESHOLD * 0.6 - IGNITE_HEAT_DECAY_PER_S)
    assert c.ignite_timer <= 0.0


def test_ignite_tick_deals_fire_damage_over_the_duration_then_can_relight() -> None:
    c = _creature(hp=100000.0)
    hp0 = c.hp
    c.ignite_timer = IGNITE_DURATION_S

    dt = 1.0 / 60.0
    ticks = 0
    while c.ignite_timer > 0.0:
        _tick(c, dt)
        ticks += 1

    assert ticks == pytest.approx(IGNITE_DURATION_S * 60.0, abs=1)
    assert (hp0 - c.hp) == pytest.approx(IGNITE_DPS * IGNITE_DURATION_S, rel=0.02)
    # eligible again now that the burn lapsed
    flame_ignite_accumulate(c, IGNITE_HEAT_THRESHOLD)
    assert c.ignite_timer == IGNITE_DURATION_S


def test_ignite_damage_is_fire_typed_so_pyromaniac_scales_it() -> None:
    from crimson.perks.ids import PerkId

    plain = _creature(hp=100000.0)
    plain.ignite_timer = IGNITE_DURATION_S
    _tick(plain, 0.5)
    plain_loss = 100000.0 - plain.hp

    pyro = _creature(hp=100000.0)
    pyro.ignite_timer = IGNITE_DURATION_S
    pyro_player = PlayerState(index=0, pos=Vec2())
    pyro_player.perk_counts[int(PerkId.PYROMANIAC)] = 1
    ignite_tick(
        pyro,
        creature_index=0,
        dt=0.5,
        state=GameplayState(),
        players=[pyro_player],
        rng=GameplayState().rng,
        detail_preset=5,
        creature_damage_runtime=None,
    )
    assert (100000.0 - pyro.hp) == pytest.approx(plain_loss * 1.5, rel=1e-4)


def test_ignite_tick_is_inert_with_no_burn_and_no_heat() -> None:
    c = _creature()
    assert _tick(c, 1.0) is False
    assert c.hp == 1000.0
