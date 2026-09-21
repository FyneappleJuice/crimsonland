from __future__ import annotations

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.progression import refresh_player_stats
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def test_bonus_economist_extends_bonus_timers() -> None:
    base_state = GameplayState()
    base_player = PlayerState(index=0, pos=Vec2())
    refresh_player_stats([base_player])
    bonus_apply(base_state, base_player, BonusId.DOUBLE_EXPERIENCE, amount=10, origin=base_player.pos, creatures=[], players=[base_player])
    assert base_state.bonuses.double_experience == 6.0

    perk_state = GameplayState()
    perk_player = PlayerState(index=0, pos=Vec2())
    perk_player.perk_counts[int(PerkId.BONUS_ECONOMIST)] = 1
    refresh_player_stats([perk_player])
    bonus_apply(perk_state, perk_player, BonusId.DOUBLE_EXPERIENCE, amount=10, origin=perk_player.pos, creatures=[], players=[perk_player])
    assert perk_state.bonuses.double_experience == 9.0


def test_bonus_economist_player_ownership() -> None:
    # Perk ownership is per-player: the pickup owner's own perks are read, not
    # player slot zero's.
    state = GameplayState()
    players = [
        PlayerState(index=0, pos=Vec2()),
        PlayerState(index=1, pos=Vec2()),
    ]
    players[1].perk_counts[int(PerkId.BONUS_ECONOMIST)] = 1
    refresh_player_stats(players)

    bonus_apply(
        state,
        players[1],
        BonusId.DOUBLE_EXPERIENCE,
        amount=10,
        origin=players[1].pos,
        creatures=[],
        players=players,
    )

    assert state.bonuses.double_experience == 9.0
