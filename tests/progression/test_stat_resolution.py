from __future__ import annotations

import math

import pytest

from crimson.progression import ModOp, PlayerStats, StatMod, resolve_stats
from crimson.progression.modifiers import flag, flat, increased, more, override
from crimson.progression.stats import STAT_IDENTITIES


def test_empty_modifier_list_resolves_to_all_defaults() -> None:
    assert resolve_stats([]) == PlayerStats()


def test_identity_table_matches_struct_defaults() -> None:
    defaults = PlayerStats()
    for name, identity in STAT_IDENTITIES.items():
        assert getattr(defaults, name) == identity


def test_flat_then_increased_then_more_order() -> None:
    stats = resolve_stats(
        [
            flat("clip_size_add", 2.0),
            flat("clip_size_add", 1.0),
        ],
    )
    assert stats.clip_size_add == 3.0


def test_increased_modifiers_are_additive_with_each_other() -> None:
    stats = resolve_stats(
        [
            increased("damage_mult", 0.4),
            increased("damage_mult", 0.25),
        ],
    )
    # (1 + 0.4 + 0.25) = 1.65
    assert stats.damage_mult == pytest.approx(1.65)


def test_more_modifiers_chain_multiplicatively() -> None:
    stats = resolve_stats(
        [
            more("shot_cooldown_mult", -0.12),
            more("shot_cooldown_mult", -0.10),
        ],
    )
    assert stats.shot_cooldown_mult == pytest.approx(0.88 * 0.90)


def test_full_formula_flat_inc_more_together() -> None:
    stats = resolve_stats(
        [
            flat("damage_mult", 0.5),       # identity 1.0 -> 1.5
            increased("damage_mult", 1.0),  # * (1 + 1.0) -> 3.0
            more("damage_mult", 0.5),       # * 1.5 -> 4.5
            more("damage_mult", -0.25),     # * 0.75 -> 3.375
        ],
    )
    assert stats.damage_mult == pytest.approx((1.0 + 0.5) * 2.0 * 1.5 * 0.75)


def test_override_wins_and_ignores_other_ops() -> None:
    stats = resolve_stats(
        [
            increased("move_speed_mult", 5.0),
            more("move_speed_mult", 10.0),
            override("move_speed_mult", 0.5),
        ],
    )
    assert stats.move_speed_mult == 0.5


def test_flags_accumulate_into_a_set() -> None:
    stats = resolve_stats([flag("projectiles_chain"), flag("no_pierce"), flag("projectiles_chain")])
    assert stats.flags == frozenset({"projectiles_chain", "no_pierce"})
    assert stats.has("projectiles_chain")
    assert not stats.has("crit_on_kill")


def test_resolution_is_order_independent() -> None:
    mods = [
        more("damage_mult", 0.3),
        flat("damage_mult", 0.2),
        increased("damage_mult", 0.5),
        more("damage_mult", -0.1),
    ]
    forward = resolve_stats(mods)
    backward = resolve_stats(list(reversed(mods)))
    assert forward.damage_mult == pytest.approx(backward.damage_mult)


def test_unknown_stat_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown stat"):
        StatMod(stat="not_a_real_stat", op=ModOp.FLAT, value=1.0)


def test_flag_mod_does_not_validate_against_stat_table() -> None:
    # flags are free-form strings, not numeric stats
    mod = StatMod(stat="whatever_keystone", op=ModOp.FLAG)
    assert resolve_stats([mod]).flags == frozenset({"whatever_keystone"})
