from __future__ import annotations

import msgspec

from crimson.perks.ids import PerkId
from crimson.progression.stats import PlayerStats
from crimson.sim.state_types import PlayerState
from crimson.ui.perk_history_panel import owned_perk_rows, stat_summary_rows
from grim.geom import Vec2


def test_owned_perk_rows_lists_only_picked_perks_with_counts() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.FASTSHOT)] = 1
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 2

    rows = owned_perk_rows(player)

    assert ("Fastshot", 1) in rows
    assert ("Barrel Greaser", 2) in rows
    assert len(rows) == 2


def test_owned_perk_rows_is_empty_for_a_fresh_player() -> None:
    player = PlayerState(index=0, pos=Vec2())
    assert owned_perk_rows(player) == []


def test_stat_summary_rows_skips_untouched_defaults() -> None:
    assert stat_summary_rows(PlayerStats()) == []


def test_stat_summary_rows_formats_percent_and_multiplier_stats() -> None:
    stats = msgspec.structs.replace(
        PlayerStats(),
        damage_mult_bullet=1.5,
        shot_cooldown_mult=0.85,
        crit_mult=2.5,
        crit_chance=0.10,
        clip_size_add=3.0,
    )

    rows = dict(stat_summary_rows(stats))

    assert rows["Bullet Dmg"] == "+50%"
    # shot_cooldown_mult < 1.0 is a buff (fires faster) - displayed as a
    # positive percent, not a negative one, so it reads as good news.
    assert rows["Fire Rate"] == "+15%"
    assert rows["Crit Multiplier"] == "x2.50"
    assert rows["Crit Chance"] == "+10%"
    assert rows["Clip Size"] == "+3"


def test_stat_summary_rows_derives_archetype_labels_from_the_field_suffix() -> None:
    stats = msgspec.structs.replace(PlayerStats(), damage_mult_archetype_shotgun=1.2)

    rows = dict(stat_summary_rows(stats))

    assert rows["Shotgun Dmg"] == "+20%"
