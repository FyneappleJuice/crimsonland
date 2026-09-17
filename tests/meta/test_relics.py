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
    assert st.owned == (
        [int(R.RelicId.CLIP_PLUS_1)] * R.SEED_RELIC_COUNT
        + [int(R.RelicId.FIRE_RATE_PLUS_5)] * R.SEED_FIRE_RATE_RELIC_COUNT
    )
    assert st.placements == []
    assert (tmp_path / "relics.json").is_file()


def test_equip_moves_from_inventory_to_first_empty_slot():
    R.equip_from_owned(0)
    st = R.relic_state()
    assert len(st.placements) == 1
    assert st.placements[0].relic_id == int(R.RelicId.CLIP_PLUS_1)
    assert (st.placements[0].row, st.placements[0].col) == (0, 0)
    assert len(st.owned) == R.SEED_RELIC_COUNT + R.SEED_FIRE_RATE_RELIC_COUNT - 1

    R.equip_from_owned(0)
    assert (R.relic_state().placements[1].row, R.relic_state().placements[1].col) == (0, 1)


def test_1x2_relic_occupies_two_cells_as_one_placement():
    # Owned list is seeded [CLIP_PLUS_1 x8, FIRE_RATE_PLUS_5 x6]; index 8 is
    # the first fire-rate relic.
    R.equip_from_owned(8)
    st = R.relic_state()
    assert len(st.placements) == 1
    p = st.placements[0]
    assert p.relic_id == int(R.RelicId.FIRE_RATE_PLUS_5)
    assert R.relic_shape(p.relic_id) == (1, 2)
    assert R.occupied_cells(p) == [(0, 0), (1, 0)]
    # Both cells resolve to the same placement instance.
    assert R.placement_at(0, 0) == (0, p)
    assert R.placement_at(1, 0) == (0, p)
    assert R.placement_at(2, 0) is None


def test_grid_is_capped_by_available_cells():
    clip = int(R.RelicId.CLIP_PLUS_1)
    for row in range(R.GRID_H):
        for col in range(R.GRID_W):
            assert R.place_held_relic(clip, row, col)
    assert len(R.relic_state().placements) == R.GRID_SLOTS
    assert len(R.placed_relic_ids()) == R.GRID_SLOTS
    # Every cell is taken - a further relic has nowhere to go.
    assert not R.equip_from_owned(0)


def test_unequip_returns_to_cursor_not_owned():
    R.equip_from_owned(0)
    before = len(R.relic_state().owned)
    relic_id = R.remove_placement_to_held(0)
    assert relic_id == int(R.RelicId.CLIP_PLUS_1)
    assert R.relic_state().placements == []
    # remove_placement_to_held hands the relic to the caller (the cursor) -
    # it does not go back into owned automatically.
    assert len(R.relic_state().owned) == before


def test_place_held_relic_respects_collision_and_bounds():
    fire_rate = int(R.RelicId.FIRE_RATE_PLUS_5)
    # A 1x2 (w,h) relic anchored at the last row (4) would need row 5, out of bounds.
    assert not R.place_held_relic(fire_rate, 4, 0)
    assert R.relic_state().placements == []

    # One row up, it fits (rows 3 and 4).
    assert R.place_held_relic(fire_rate, 3, 0)
    assert R.occupied_cells(R.relic_state().placements[0]) == [(3, 0), (4, 0)]

    # A second relic can't overlap any of those occupied cells.
    assert not R.place_held_relic(int(R.RelicId.CLIP_PLUS_1), 3, 0)
    assert not R.place_held_relic(fire_rate, 3, 0)
    # But a non-overlapping cell is fine.
    assert R.place_held_relic(int(R.RelicId.CLIP_PLUS_1), 0, 0)


def test_drop_is_persisted():
    before = len(R.relic_state().owned)
    R.award_relic_drop()
    R.award_relic_drop()
    assert len(R.relic_state().owned) == before + 2
    saved = json.loads((R._PATH).read_text())
    assert len(saved["owned"]) == before + 2


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


def test_fire_rate_relic_lowers_shot_cooldown_through_progression():
    """Unlike clip_size (baked into player.weapon.clip_size once, at
    weapon_assign_player time), shot_cooldown_mult is read straight off
    player.stats on every single shot (weapon_runtime/fire.py fire_weapon,
    `cooldown_mult = perk_player.stats.shot_cooldown_mult`) - so there's no
    "only applies at pickup" gap to worry about here; confirming the stat
    resolves correctly is confirming the whole pipeline."""

    from crimson.progression import refresh_player_stats
    from crimson.sim.state_types import PlayerState
    from crimson.weapons import WEAPON_BY_ID, WeaponId
    from grim.geom import Vec2

    # owned is seeded [CLIP_PLUS_1 x8, FIRE_RATE_PLUS_5 x6]; index 8 is the
    # first fire-rate relic.
    for _ in range(3):
        R.equip_from_owned(8)
    R.begin_run()

    mods = R.active_run_stat_mods()
    assert len(mods) == 3
    assert all(m.stat == "shot_cooldown_mult" and m.value == -0.05 for m in mods)

    player = PlayerState(index=0, pos=Vec2())
    refresh_player_stats([player])

    # Three "more -0.05" mods chain multiplicatively: 0.95 ** 3.
    assert player.stats.shot_cooldown_mult == pytest.approx(0.95**3)
    assert player.stats.shot_cooldown_mult < 1.0  # strictly faster, not a no-op

    pistol_base_cooldown = float(WEAPON_BY_ID[WeaponId.PISTOL].shot_cooldown)
    effective_cooldown = pistol_base_cooldown * player.stats.shot_cooldown_mult
    assert effective_cooldown < pistol_base_cooldown

    R.end_run()
    assert R.active_run_stat_mods() == ()
