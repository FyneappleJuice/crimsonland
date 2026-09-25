from __future__ import annotations

import pytest

from crimson.perks.ids import PerkId
from crimson.perks.impl.soul_tether import SOUL_TETHER_MAX_SHIELD, soul_tether_clamp_and_gain
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def _tethered(health: float = 100.0, shield: float = 0.0) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(), health=health)
    player.perk_counts[int(PerkId.SOUL_TETHER)] = 1
    player.soul_tether_shield = shield
    return player


def test_overflow_heal_goes_into_the_shield() -> None:
    player = _tethered(health=95.0)
    assert soul_tether_clamp_and_gain(player, 95.0 + 20.0) == 100.0
    assert player.soul_tether_shield == pytest.approx(15.0)


def test_shield_caps_at_100() -> None:
    assert SOUL_TETHER_MAX_SHIELD == 100.0
    player = _tethered(shield=90.0)
    soul_tether_clamp_and_gain(player, 100.0 + 25.0)
    assert player.soul_tether_shield == pytest.approx(100.0)
    soul_tether_clamp_and_gain(player, 100.0 + 50.0)
    assert player.soul_tether_shield == pytest.approx(100.0)


def test_without_the_perk_overflow_is_discarded() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=95.0)
    assert soul_tether_clamp_and_gain(player, 120.0) == 100.0
    assert player.soul_tether_shield == 0.0
