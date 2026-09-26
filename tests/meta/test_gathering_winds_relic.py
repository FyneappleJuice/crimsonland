from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import gathering_winds
from crimson.player_damage import player_take_damage
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


@pytest.fixture(autouse=True)
def _gathering_winds_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.GATHERING_WINDS_LOW),))


@pytest.mark.parametrize(("before", "after"), [(10, 5), (7, 2), (3, 0), (0, 0)])
def test_getting_hit_removes_five_stacks(before: int, after: int) -> None:
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.gathering_winds_stacks = before
    player_take_damage(GameplayState(), player, 5.0, players=[player])
    assert player.gathering_winds_stacks == after
    assert gathering_winds.GATHERING_WINDS_STACKS_LOST_PER_HIT == 5
