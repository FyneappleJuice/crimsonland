from __future__ import annotations

import json

import pytest

from crimson.meta import relics as R
from crimson.test_mode import set_test_mode_enabled

CHAIN_L = int(R.RelicId.RICOCHET_LOW)
CHAIN_H = int(R.RelicId.RICOCHET_HIGH)
CRIT_H = int(R.RelicId.CRITICAL_MASS_HIGH)
LEECH_H = int(R.RelicId.LEECH_HIGH)


@pytest.fixture(autouse=True)
def _fresh_relics(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_STATE", None)
    monkeypatch.setattr(R, "_PATH", None)
    monkeypatch.setattr(R, "_ACTIVE_RUN_MODS", ())
    monkeypatch.setattr(R, "_ACTIVE_RELIC_IDS", ())
    set_test_mode_enabled(False)
    R.init_relics(tmp_path)
    yield
    set_test_mode_enabled(False)


def _own(*relic_ids: int) -> None:
    R.relic_state().owned.extend(int(r) for r in relic_ids)


def test_fresh_profile_is_empty_and_persisted(tmp_path):
    st = R.relic_state()
    assert st.owned == []
    assert st.placements == []
    assert (tmp_path / "relics.json").is_file()


def test_old_save_drops_removed_placeholder_relics(tmp_path, monkeypatch):
    # 1 = +1 Clip Size, 2 = +5% Fire Rate - both removed.
    (tmp_path / "relics.json").write_text(
        json.dumps(
            {
                "owned": [1, 1, 2, CHAIN_H, 1],
                "placements": [{"relic_id": 2, "row": 0, "col": 0}, {"relic_id": CRIT_H, "row": 1, "col": 1}],
            },
        ),
    )
    monkeypatch.setattr(R, "_STATE", None)
    st = R.init_relics(tmp_path)
    assert st.owned == [CHAIN_H]
    assert [p.relic_id for p in st.placements] == [CRIT_H]


def test_test_mode_tops_up_to_one_of_each_without_duplicating_placed(tmp_path, monkeypatch):
    (tmp_path / "relics.json").write_text(
        json.dumps({"owned": [LEECH_H], "placements": [{"relic_id": CHAIN_H, "row": 0, "col": 0}]}),
    )
    monkeypatch.setattr(R, "_STATE", None)
    set_test_mode_enabled(True)
    st = R.init_relics(tmp_path)
    everything = sorted(st.owned + [p.relic_id for p in st.placements])
    assert everything == sorted(int(r) for r in R.RelicId)  # exactly one of each

    # Relaunching doesn't add more.
    monkeypatch.setattr(R, "_STATE", None)
    R.save_relics()
    st = R.init_relics(tmp_path)
    assert sorted(st.owned + [p.relic_id for p in st.placements]) == everything


def test_equip_moves_from_inventory_to_first_empty_slot():
    _own(CHAIN_H, CRIT_H)
    assert R.equip_from_owned(0)
    st = R.relic_state()
    assert [(p.relic_id, p.row, p.col) for p in st.placements] == [(CHAIN_H, 0, 0)]
    assert st.owned == [CRIT_H]

    assert R.equip_from_owned(0)
    assert (st.placements[1].row, st.placements[1].col) == (0, 1)


def test_only_one_pact_of_each_type_can_be_equipped():
    _own(CHAIN_L, CHAIN_H)
    assert R.place_held_relic(CHAIN_H, 0, 0)
    # A different tier of the same pact is refused, wherever it goes...
    assert R.family_conflict(CHAIN_L)
    assert not R.fits(CHAIN_L, 2, 2)
    assert not R.place_held_relic(CHAIN_L, 2, 2)
    assert not R.equip_from_owned(0)
    # ...but a different pact is fine.
    assert R.place_held_relic(CRIT_H, 2, 2)

    # Once the first is removed, the other tier can go in.
    R.remove_placement_to_held(0)
    assert R.place_held_relic(CHAIN_L, 0, 0)


def test_multi_cell_relic_occupies_its_cells_as_one_placement(monkeypatch):
    monkeypatch.setitem(R.RELIC_SHAPE, CHAIN_H, (1, 2))
    assert R.place_held_relic(CHAIN_H, 0, 0)
    p = R.relic_state().placements[0]
    assert R.occupied_cells(p) == [(0, 0), (1, 0)]
    assert R.placement_at(0, 0) == (0, p)
    assert R.placement_at(1, 0) == (0, p)
    assert R.placement_at(2, 0) is None


def test_place_held_relic_respects_collision_and_bounds(monkeypatch):
    monkeypatch.setitem(R.RELIC_SHAPE, CHAIN_H, (1, 2))
    # A 1x2 (w,h) relic anchored at the last row would need a row past the grid.
    assert not R.place_held_relic(CHAIN_H, R.GRID_H - 1, 0)
    assert R.place_held_relic(CHAIN_H, R.GRID_H - 2, 0)
    # Another relic can't overlap its occupied cells.
    assert not R.place_held_relic(CRIT_H, R.GRID_H - 1, 0)
    assert R.place_held_relic(CRIT_H, 0, 0)


def test_unequip_returns_to_cursor_not_owned():
    _own(CHAIN_H, CRIT_H)
    R.equip_from_owned(0)
    before = len(R.relic_state().owned)
    assert R.remove_placement_to_held(0) == CHAIN_H
    assert R.relic_state().placements == []
    # remove_placement_to_held hands the relic to the caller (the cursor) -
    # it does not go back into owned automatically.
    assert len(R.relic_state().owned) == before


def test_drop_is_persisted():
    R.award_relic_drop(CHAIN_H)
    R.award_relic_drop(CRIT_H)
    assert R.relic_state().owned == [CHAIN_H, CRIT_H]
    saved = json.loads((R._PATH).read_text())
    assert saved["owned"] == [CHAIN_H, CRIT_H]


def test_begin_run_freezes_placed_relic_ids():
    _own(CHAIN_H, CRIT_H)
    R.equip_from_owned(0)
    R.equip_from_owned(0)
    assert R.active_relic_ids() == ()
    R.begin_run()
    assert set(R.active_relic_ids()) == {CHAIN_H, CRIT_H}
    R.end_run()
    assert R.active_relic_ids() == ()
