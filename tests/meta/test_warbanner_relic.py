from __future__ import annotations

import pytest

from crimson.gameplay import (
    GameplayState,
    advance_weapon_shot_cooldown,
    survival_check_level_up,
    survival_level_threshold,
)
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import warbanner
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def _level_up_at(state: GameplayState, player: PlayerState, pos: Vec2) -> None:
    player.pos = pos
    player.experience = survival_level_threshold(player.level) + 1
    assert survival_check_level_up(player, state.perk_selection) == 1


@pytest.mark.parametrize(("relic", "r"), [(RelicId.WARBANNER_LOW, 75.0)])
def test_level_ups_plant_banners_that_buff_inside_their_radius(monkeypatch: pytest.MonkeyPatch, relic: RelicId, r: float) -> None:
    _equip(monkeypatch, relic)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    _level_up_at(state, player, Vec2(100.0, 100.0))
    _level_up_at(state, player, Vec2(800.0, 800.0))
    assert len(player.warbanner_positions) == 2  # both stay for the run

    player.pos = Vec2(100.0 + r - 1.0, 100.0)
    assert warbanner.attack_speed_mult(player) == pytest.approx(1.30)
    assert warbanner.move_speed_mult(player) == pytest.approx(1.30)
    player.pos = Vec2(100.0 + r + 1.0, 100.0)
    assert warbanner.attack_speed_mult(player) == 1.0
    assert warbanner.move_speed_mult(player) == 1.0


def test_overlapping_banners_do_not_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.WARBANNER_LOW)
    player = PlayerState(index=0, pos=Vec2())
    player.warbanner_positions = [Vec2(), Vec2(10.0, 0.0), Vec2(0.0, 10.0)]
    assert warbanner.attack_speed_mult(player) == pytest.approx(1.30)


def test_no_banners_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    _level_up_at(state, player, Vec2(100.0, 100.0))
    assert player.warbanner_positions == []
    assert warbanner.move_speed_mult(player) == 1.0


def test_banner_speeds_up_shot_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.WARBANNER_LOW)
    state = GameplayState()

    def _after(in_banner: bool) -> float:
        player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL, shot_cooldown=1.0))
        player.warbanner_positions = [Vec2()] if in_banner else [Vec2(5000.0, 0.0)]
        advance_weapon_shot_cooldown(player, state, 0.5)
        return float(player.weapon.shot_cooldown)

    assert _after(False) == pytest.approx(0.5)
    assert _after(True) == pytest.approx(1.0 - 0.5 * 1.3)
