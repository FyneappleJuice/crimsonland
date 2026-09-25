from __future__ import annotations

import pytest

from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import deadeye_pact, slayer_pact
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def test_slayer_buff_remaining_is_the_third_newest_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.SLAYER_PACT_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    player.slayer_pact_kill_window = [4.5, 1.2, 3.0]
    assert slayer_pact.buff_remaining(player) == pytest.approx(1.2)
    player.slayer_pact_kill_window = [4.5, 1.2, 3.0, 4.9]
    assert slayer_pact.buff_remaining(player) == pytest.approx(3.0)  # still 3 kills after 1.2s ages out
    # The buff lasts exactly that long: after it, fewer than 3 kills remain.
    slayer_pact.update_kill_window(player, 3.0)
    assert slayer_pact.buff_remaining(player) == 0.0


def test_slayer_buff_remaining_is_zero_without_a_streak_or_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.slayer_pact_kill_window = [4.0, 3.0]
    _equip(monkeypatch, RelicId.SLAYER_PACT_HIGH)
    assert slayer_pact.buff_remaining(player) == 0.0
    player.slayer_pact_kill_window = [4.0, 3.0, 2.0]
    _equip(monkeypatch)
    assert slayer_pact.buff_remaining(player) == 0.0


@pytest.mark.parametrize("relic", [RelicId.DEADEYE_PACT_LOW, RelicId.DEADEYE_PACT_MEDIUM, RelicId.DEADEYE_PACT_HIGH])
def test_deadeye_neutral_distance_is_where_damage_is_unchanged(monkeypatch: pytest.MonkeyPatch, relic: RelicId) -> None:
    _equip(monkeypatch, relic)
    distance = deadeye_pact.neutral_distance()
    assert distance is not None
    assert deadeye_pact.distance_damage_mult(distance) == pytest.approx(1.0)


def test_deadeye_neutral_distance_values(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {RelicId.DEADEYE_PACT_LOW: 210.8, RelicId.DEADEYE_PACT_MEDIUM: 158.1, RelicId.DEADEYE_PACT_HIGH: 125.6}
    for relic, distance in expected.items():
        _equip(monkeypatch, relic)
        assert deadeye_pact.neutral_distance() == pytest.approx(distance, abs=0.1)
    _equip(monkeypatch)
    assert deadeye_pact.neutral_distance() is None


@pytest.mark.parametrize(
    ("relic", "far_mult"),
    [(RelicId.DEADEYE_PACT_LOW, 1.12), (RelicId.DEADEYE_PACT_MEDIUM, 1.20), (RelicId.DEADEYE_PACT_HIGH, 1.30)],
)
def test_deadeye_curve_endpoints_unchanged(monkeypatch: pytest.MonkeyPatch, relic: RelicId, far_mult: float) -> None:
    _equip(monkeypatch, relic)
    assert deadeye_pact.distance_damage_mult(10.0) == pytest.approx(0.80)
    assert deadeye_pact.distance_damage_mult(50.0) == pytest.approx(0.80)
    assert deadeye_pact.distance_damage_mult(500.0) == pytest.approx(far_mult)
    assert deadeye_pact.distance_damage_mult(900.0) == pytest.approx(far_mult)  # clamped past 500
    # Climbs the whole way, fastest up close (logarithmic - each step's gain
    # shrinks with distance).
    samples = [deadeye_pact.distance_damage_mult(d) for d in range(50, 501, 25)]
    gains = [b - a for a, b in zip(samples, samples[1:])]
    assert all(g > 0.0 for g in gains)
    assert gains == sorted(gains, reverse=True)
