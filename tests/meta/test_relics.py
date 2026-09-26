from __future__ import annotations

import json

import pytest

from crimson.meta import relics as R
from crimson.test_mode import set_test_mode_enabled

CHAIN = int(R.RelicId.RICOCHET_LOW)
CRIT = int(R.RelicId.CRITICAL_MASS_LOW)
LEECH = int(R.RelicId.LEECH_LOW)


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
    # 1 = +1 Clip Size, 2 = +5% Fire Rate - both removed. Also covers the
    # since-removed Medium/High relic tiers (e.g. old id 15 = RICOCHET_HIGH)
    # via the same _KNOWN_RELIC_IDS strip - _normalize() doesn't care why an
    # id no longer exists.
    (tmp_path / "relics.json").write_text(
        json.dumps(
            {
                "owned": [1, 1, 2, CHAIN, 15, 1],
                "placements": [{"relic_id": 2, "row": 0, "col": 0}, {"relic_id": CRIT, "row": 1, "col": 1}],
            },
        ),
    )
    monkeypatch.setattr(R, "_STATE", None)
    st = R.init_relics(tmp_path)
    assert st.owned == [CHAIN]
    assert [p.relic_id for p in st.placements] == [CRIT]


def test_test_mode_tops_up_to_one_of_each_without_duplicating_placed(tmp_path, monkeypatch):
    (tmp_path / "relics.json").write_text(
        json.dumps({"owned": [LEECH], "placements": [{"relic_id": CHAIN, "row": 0, "col": 0}]}),
    )
    monkeypatch.setattr(R, "_STATE", None)
    set_test_mode_enabled(True)
    st = R.init_relics(tmp_path)
    everything = sorted(st.owned + [p.relic_id for p in st.placements])
    assert everything == sorted(int(r) for r in R.RelicId if int(r) not in R.SHELVED_RELIC_IDS)  # one of each

    # Relaunching doesn't add more.
    monkeypatch.setattr(R, "_STATE", None)
    R.save_relics()
    st = R.init_relics(tmp_path)
    assert sorted(st.owned + [p.relic_id for p in st.placements]) == everything


def test_equip_moves_from_inventory_to_first_empty_slot():
    _own(CHAIN, CRIT)
    assert R.equip_from_owned(0)
    st = R.relic_state()
    assert [(p.relic_id, p.row, p.col) for p in st.placements] == [(CHAIN, 0, 0)]
    assert st.owned == [CRIT]

    assert R.equip_from_owned(0)
    assert (st.placements[1].row, st.placements[1].col) == (0, 1)


def test_only_one_pact_of_each_type_can_be_equipped():
    # Owning two copies of the same pact (two drops of the same relic) -
    # only one of them may ever be placed at a time.
    _own(CHAIN, CHAIN)
    assert R.place_held_relic(CHAIN, 0, 0)
    assert R.family_conflict(CHAIN)
    assert not R.fits(CHAIN, 2, 2)
    assert not R.place_held_relic(CHAIN, 2, 2)
    assert not R.equip_from_owned(0)
    # ...but a different pact is fine.
    assert R.place_held_relic(CRIT, 2, 2)

    # Once the first is removed, the second copy can go in.
    R.remove_placement_to_held(0)
    assert R.place_held_relic(CHAIN, 0, 0)


def test_multi_cell_relic_occupies_its_cells_as_one_placement(monkeypatch):
    monkeypatch.setitem(R.RELIC_SHAPE, CHAIN, (1, 2))
    assert R.place_held_relic(CHAIN, 0, 0)
    p = R.relic_state().placements[0]
    assert R.occupied_cells(p) == [(0, 0), (1, 0)]
    assert R.placement_at(0, 0) == (0, p)
    assert R.placement_at(1, 0) == (0, p)
    assert R.placement_at(2, 0) is None


def test_place_held_relic_respects_collision_and_bounds(monkeypatch):
    monkeypatch.setitem(R.RELIC_SHAPE, CHAIN, (1, 2))
    # A 1x2 (w,h) relic anchored at the last row would need a row past the grid.
    assert not R.place_held_relic(CHAIN, R.GRID_H - 1, 0)
    assert R.place_held_relic(CHAIN, R.GRID_H - 2, 0)
    # Another relic can't overlap its occupied cells.
    assert not R.place_held_relic(CRIT, R.GRID_H - 1, 0)
    assert R.place_held_relic(CRIT, 0, 0)


def test_unequip_returns_to_cursor_not_owned():
    _own(CHAIN, CRIT)
    R.equip_from_owned(0)
    before = len(R.relic_state().owned)
    assert R.remove_placement_to_held(0) == CHAIN
    assert R.relic_state().placements == []
    # remove_placement_to_held hands the relic to the caller (the cursor) -
    # it does not go back into owned automatically.
    assert len(R.relic_state().owned) == before


def test_drop_is_persisted():
    R.award_relic_drop(CHAIN)
    R.award_relic_drop(CRIT)
    assert R.relic_state().owned == [CHAIN, CRIT]
    saved = json.loads((R._PATH).read_text())
    assert saved["owned"] == [CHAIN, CRIT]


def test_begin_run_freezes_placed_relic_ids():
    _own(CHAIN, CRIT)
    R.equip_from_owned(0)
    R.equip_from_owned(0)
    assert R.active_relic_ids() == ()
    R.begin_run()
    assert set(R.active_relic_ids()) == {CHAIN, CRIT}
    R.end_run()
    assert R.active_relic_ids() == ()


def test_shelved_relics_are_stripped_and_never_seeded(tmp_path, monkeypatch):
    shelved = sorted(R.SHELVED_RELIC_IDS)
    assert shelved  # First Strike, for now
    (tmp_path / "relics.json").write_text(
        json.dumps({"owned": [shelved[0], CHAIN], "placements": []}),
    )
    monkeypatch.setattr(R, "_STATE", None)
    set_test_mode_enabled(True)
    st = R.init_relics(tmp_path)
    ids = set(st.owned) | {p.relic_id for p in st.placements}
    assert not ids & R.SHELVED_RELIC_IDS
