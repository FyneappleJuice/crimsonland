from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.progression import refresh_player_stats
from crimson.sim.state_types import PlayerState
from crimson.ui.player_stats_readout import player_stat_lines
from crimson.weapon_runtime import init_default_alt_weapon, weapon_assign_player
from crimson.weapon_runtime.assign import weapon_slot_active
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _rows(player: PlayerState) -> dict[str, str]:
    refresh_player_stats([player])
    return dict(player_stat_lines(player))


def test_single_weapon_readout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", ())
    player = PlayerState(index=0, pos=Vec2(), health=87.25)
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=GameplayState())
    rows = _rows(player)
    assert list(rows) == ["HP", "Crit chance", "Crit multiplier", "Move speed", "Reload time"]
    assert rows["HP"] == "87.2 / 100" or rows["HP"] == "87.3 / 100"
    assert rows["Crit chance"] == "20.0%"  # Rifle base
    assert rows["Crit multiplier"] == "2.00x"
    assert rows["Move speed"] == "100.0%"
    assert rows["Reload time"] == "1.20s"


def test_dual_wielding_lists_both_weapons_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.GIANT_PACT_LOW),))
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=state)
    init_default_alt_weapon(player)
    assert player.alt_weapon is not None
    with weapon_slot_active(player, player.alt_weapon):
        weapon_assign_player(player, WeaponId.SHOTGUN, state=state)
    rows = _rows(player)
    assert rows["Crit chance"] == "20.0%, 5.0%"
    assert rows["Reload time"].count(",") == 1
