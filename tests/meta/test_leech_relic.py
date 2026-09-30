from __future__ import annotations

import pytest

from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import leech
from crimson.perks.ids import PerkId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


@pytest.fixture(autouse=True)
def _leech_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.LEECH_LOW),))


def _kill_cost(player: PlayerState) -> float:
    before = float(player.health)
    leech.hp_cost_on_kill(player)
    return before - float(player.health)


def test_kill_costs_five_percent_of_current_hp() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=80.0)
    assert _kill_cost(player) == pytest.approx(80.0 * 0.05, rel=1e-5)


def test_kill_cost_is_a_straight_hp_loss_not_damage_taken() -> None:
    # Nothing that reacts to a hit applies: not Thick Skinned's reduction,
    # not a shield, not Adrenaline Rush's window.
    player = PlayerState(index=0, pos=Vec2(), health=80.0, shield_timer=5.0)
    player.perk_counts[int(PerkId.THICK_SKINNED)] = 1
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1
    assert _kill_cost(player) == pytest.approx(80.0 * 0.05, rel=1e-5)
    assert player.adrenaline_rush_window_timer == 0.0


def test_heal_on_hit_queues_an_instance_instead_of_healing_immediately() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    leech.heal_on_hit(player, 100.0)
    assert float(player.health) == 50.0  # nothing yet - it drips via tick()
    assert player.leech_pending_heal == [pytest.approx(100.0 * 0.00756)]
    assert player.leech_pending_timers == [leech.LEECH_HEAL_DURATION]


def test_heal_drips_over_the_full_duration_then_stops() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    leech.heal_on_hit(player, 100.0)
    total = 100.0 * 0.00756
    step = leech.LEECH_HEAL_DURATION / 10.0
    for _ in range(10):
        leech.tick(player, step)
    assert float(player.health) == pytest.approx(50.0 + total, rel=1e-4)
    assert player.leech_pending_heal == []
    assert player.leech_pending_timers == []
    # Nothing more drips once the instance has expired.
    leech.tick(player, step)
    assert float(player.health) == pytest.approx(50.0 + total, rel=1e-4)


def test_each_hit_gets_its_own_independent_instance() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    leech.heal_on_hit(player, 100.0)
    leech.tick(player, leech.LEECH_HEAL_DURATION / 2.0)  # first instance half-drained
    leech.heal_on_hit(player, 200.0)  # a second, independent instance starts fresh
    assert len(player.leech_pending_heal) == 2
    assert player.leech_pending_timers[0] == pytest.approx(leech.LEECH_HEAL_DURATION / 2.0)
    assert player.leech_pending_timers[1] == pytest.approx(leech.LEECH_HEAL_DURATION)


def test_a_proc_past_the_instance_cap_heals_nothing() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    for _ in range(leech.LEECH_MAX_INSTANCES):
        leech.heal_on_hit(player, 100.0)
    assert len(player.leech_pending_timers) == leech.LEECH_MAX_INSTANCES

    leech.heal_on_hit(player, 100.0)  # the 11th proc

    assert len(player.leech_pending_timers) == leech.LEECH_MAX_INSTANCES
    assert len(player.leech_pending_heal) == leech.LEECH_MAX_INSTANCES

    # Once one instance expires, there's room for a fresh proc again.
    leech.tick(player, leech.LEECH_HEAL_DURATION)
    assert player.leech_pending_timers == []
    leech.heal_on_hit(player, 100.0)
    assert len(player.leech_pending_timers) == 1


def test_nothing_happens_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", ())
    player = PlayerState(index=0, pos=Vec2(), health=80.0)
    assert _kill_cost(player) == 0.0
    leech.heal_on_hit(player, 100.0)
    assert player.leech_pending_heal == []
    leech.tick(player, 1.0)
    assert float(player.health) == 80.0
