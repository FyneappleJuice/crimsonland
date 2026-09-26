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


def test_heal_per_hit() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    leech.heal_on_hit(player, 100.0)
    assert float(player.health) == pytest.approx(50.0 + 100.0 * 0.00756, rel=1e-5)


def test_nothing_happens_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", ())
    player = PlayerState(index=0, pos=Vec2(), health=80.0)
    assert _kill_cost(player) == 0.0
    leech.heal_on_hit(player, 100.0)
    assert float(player.health) == 80.0
