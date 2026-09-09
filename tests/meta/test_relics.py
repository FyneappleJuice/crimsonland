from __future__ import annotations

import json

import pytest

from crimson.meta import relics as R


@pytest.fixture(autouse=True)
def _fresh_relics(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_STATE", None)
    monkeypatch.setattr(R, "_PATH", None)
    monkeypatch.setattr(R, "_ACTIVE_RUN_MODS", ())
    R.init_relics(tmp_path)
    yield


def test_fresh_profile_is_seeded_and_persisted(tmp_path):
    st = R.relic_state()
    assert st.owned == [int(R.RelicId.CLIP_PLUS_1)] * R.SEED_RELIC_COUNT
    assert st.grid == [0] * R.GRID_SLOTS
    assert (tmp_path / "relics.json").is_file()


def test_equip_moves_from_inventory_to_first_empty_slot():
    R.equip_from_owned(0)
    st = R.relic_state()
    assert st.grid[0] == int(R.RelicId.CLIP_PLUS_1)
    assert len(st.owned) == R.SEED_RELIC_COUNT - 1

    R.equip_from_owned(0)
    assert R.relic_state().grid[1] == int(R.RelicId.CLIP_PLUS_1)


def test_grid_is_capped_at_25():
    for _ in range(R.SEED_RELIC_COUNT):
        R.equip_from_owned(0)
    for _ in range(40):
        R.award_relic_drop()
        R.equip_from_owned(0)
    assert sum(1 for x in R.relic_state().grid if x) == R.GRID_SLOTS
    assert len(R.placed_relic_ids()) == 25


def test_unequip_returns_to_inventory():
    R.equip_from_owned(0)
    assert R.unequip_slot(0)
    assert R.relic_state().grid[0] == 0
    assert len(R.relic_state().owned) == R.SEED_RELIC_COUNT


def test_drop_is_persisted():
    R.award_relic_drop()
    R.award_relic_drop()
    assert len(R.relic_state().owned) == R.SEED_RELIC_COUNT + 2
    saved = json.loads((R._PATH).read_text())
    assert len(saved["owned"]) == R.SEED_RELIC_COUNT + 2


def test_begin_run_freezes_placed_relic_mods():
    for _ in range(3):
        R.equip_from_owned(0)
    assert R.active_run_stat_mods() == ()
    R.begin_run()
    mods = R.active_run_stat_mods()
    assert len(mods) == 3
    assert all(m.stat == "clip_size_add" and m.value == 1.0 for m in mods)
    R.end_run()
    assert R.active_run_stat_mods() == ()


def test_placed_relics_add_to_clip_size_through_progression(tmp_path):
    from crimson.gameplay import GameplayState
    from crimson.progression import refresh_player_stats
    from crimson.sim.state_types import PlayerState
    from crimson.weapon_runtime import weapon_assign_player
    from crimson.weapons import WeaponId
    from grim.geom import Vec2

    for _ in range(2):
        R.equip_from_owned(0)
    R.begin_run()

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    refresh_player_stats([player])
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    assert player.stats.clip_size_add == 2.0
    assert player.weapon.clip_size == 14  # pistol base 12 + 2

    R.end_run()
