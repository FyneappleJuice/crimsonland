from __future__ import annotations

import pytest

from crimson.creatures.spawn import (
    SURVIVAL_RARITY_RAMP_START_LEVEL,
    CreatureFlags,
    CreatureTypeId,
    _survival_creature_type_weights,
    _survival_rarity_divisor,
    _survival_weighted_type_pick,
    build_survival_spawn_creature,
)
from crimson.gameplay import survival_level_threshold
from crimson.math_parity import f32, f32_from_bits
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand, assert_float_close


def _survival_spawn_exact_values(*, type_roll: int, reward_bonus_roll: int = 0) -> list[int]:
    """Not native: the draw sequence build_survival_spawn_creature now makes -
    two shorter than the original (the parity-pick and rare-override draws
    are gone, see the type-selection rewrite). Red/green/blue/purple/yellow
    are tuned to 2/2/2/4/4 so every rarity check misses (Normal tier, white
    tint) at xp=0, where the divisors are still 19/30/58."""
    return [
        0,  # alloc slot phase seed
        type_roll,  # type roll
        0,  # size
        0,  # heading
        0,  # health
        0,  # tint_g
        0,  # tint_b
        reward_bonus_roll,  # reward bonus
        2,  # rare red
        2,  # rare green
        2,  # rare blue
        4,  # rare purple
        4,  # rare yellow
    ]


# --- type-selection weight table -------------------------------------------


def test_type_weight_brackets_always_sum_to_ten() -> None:
    for xp in (0, 5_000, 12_000, 25_000, 42_000, 90_000, 160_000, 500_000, 5_000_000):
        assert sum(_survival_creature_type_weights(xp)) == 10


def test_every_creature_type_is_reachable_from_the_very_start_of_a_run() -> None:
    # The actual regression this locks in: Lizard (and every other type) must
    # be pickable at xp=0, not gated behind some later threshold.
    weights = _survival_creature_type_weights(0)
    assert len(weights) == 5
    assert all(w > 0 for w in weights)


@pytest.mark.parametrize("xp", [0, 5_000, 12_000, 25_000, 42_000, 90_000, 160_000, 1_000_000])
def test_every_creature_type_is_reachable_at_every_bracket(xp: int) -> None:
    weights = _survival_creature_type_weights(xp)
    assert all(w > 0 for w in weights)


def test_weighted_type_pick_maps_roll_to_type_by_cumulative_weight() -> None:
    weights = (3, 2, 3, 1, 1)  # zombie 0-2, lizard 3-4, alien 5-7, spider_sp1 8, spider_sp2 9
    assert [_survival_weighted_type_pick(weights, r) for r in range(10)] == [
        0, 0, 0, 1, 1, 2, 2, 2, 3, 4,
    ]


# --- build_survival_spawn_creature: type-dependent post-processing ---------


def test_zombie_gets_the_speed_floor_and_health_multiplier_when_picked() -> None:
    rng = ScriptedCrand(_survival_spawn_exact_values(type_roll=0))
    c = build_survival_spawn_creature(Vec2(1.0, 2.0), rng, player_experience=90_000)

    assert c.type_id == CreatureTypeId.ZOMBIE
    assert_float_close(c.move_speed, float(f32(1.3)))
    assert_float_close(c.health, 246.75)
    assert_float_close(c.max_health, 246.75)


def test_spider_sp1_gets_the_speed_boost_and_ai7_flag_when_picked() -> None:
    rng = ScriptedCrand(_survival_spawn_exact_values(type_roll=6))
    c = build_survival_spawn_creature(Vec2(1.0, 2.0), rng, player_experience=90_000)

    assert c.type_id == CreatureTypeId.SPIDER_SP1
    assert (c.flags & CreatureFlags.AI7_LINK_TIMER) != 0
    assert_float_close(c.move_speed, 2.0279998779296875)
    assert_float_close(c.health, 164.5)


def test_survival_spawn_creature_rounds_native_stat_chain_at_each_pc24_operation() -> None:
    # type_roll=5 lands on Alien at xp=0 (no zombie/spider_sp1 multiplier),
    # isolating the pc24-rounding behavior this test is actually about.
    values = _survival_spawn_exact_values(type_roll=5, reward_bonus_roll=1)
    c = build_survival_spawn_creature(Vec2(1.0, 2.0), ScriptedCrand(values), player_experience=0)

    assert c.type_id == CreatureTypeId.ALIEN
    assert c.contact_damage == f32_from_bits(0x40861862)
    assert c.reward_value == f32_from_bits(0x41FDC677)
    # Not native: Normal rarity (tier 0 here) stays undyed white - see the
    # comment in build_survival_spawn_creature.
    assert c.tint == (
        f32_from_bits(0x3F800000),
        f32_from_bits(0x3F800000),
        f32_from_bits(0x3F800000),
        f32_from_bits(0x3F800000),
    )


# --- native colour-variant fallback (MONSTER_RARITY_ENABLED=False) --------


@pytest.mark.parametrize(
    ("rare_values", "expected_size", "expected_health", "expected_reward_value", "expected_tint"),
    [
        # Rare stat overrides (color-coded variants) - each REPLACES health/
        # reward/tint outright, so they don't depend on the type/xp-derived
        # base health at all. Purple/yellow (drawn unconditionally after
        # red/green/blue, regardless of their outcome) are held at a miss
        # value (4) in every row here so they don't also fire.
        ([0, 4, 4], 44.0, 65.0, 256.0, (0.9, 0.4, 0.4)),  # red hits (r%180<2 -> value 0)
        ([2, 0, 4, 4], 44.0, 85.0, 336.0, (0.4, 0.9, 0.4)),  # red misses, green hits
        ([2, 2, 0, 4, 4], 44.0, 125.0, 416.0, (0.4, 0.4, 0.9)),  # red+green miss, blue hits
        # Rare health/size boosts ADD to whatever health preceded them, so
        # these do depend on the (here: Alien, no multiplier) base health.
        ([2, 2, 2, 0], 80.0, 282.0, 480.0, (0.84, 0.24, 0.89)),  # purple hits (base health 52)
        ([2, 2, 2, 4, 0], 85.0, 2282.0, 720.0, (0.94, 0.84, 0.29)),  # purple misses, yellow hits
    ],
    ids=["red", "green", "blue", "purple", "yellow"],
)
def test_survival_spawn_creature_rare_variants(
    rare_values: list[int],
    expected_size: float,
    expected_health: float,
    expected_reward_value: float,
    expected_tint: tuple[float, float, float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # These assert the native colour-variant stat overrides; the rewrite-only
    # rarity/affix system replaces that path (see creatures/rarity.py).
    monkeypatch.setattr("crimson.creatures.rarity.MONSTER_RARITY_ENABLED", False)
    # type_roll=5 -> Alien at xp=0 (no health/speed multiplier), so the
    # "boost" cases add onto a known, unscaled base health of 52.0.
    values = [0, 5, 0, 0, 0, 0, 0, 0, *rare_values]
    rng = ScriptedCrand(values, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    c = build_survival_spawn_creature(Vec2(1.0, 2.0), rng, player_experience=0)

    assert c.type_id == CreatureTypeId.ALIEN
    assert c.flags == CreatureFlags(0)

    assert_float_close(c.size, expected_size)
    assert_float_close(c.health, expected_health)
    assert_float_close(c.max_health, expected_health)
    assert_float_close(c.reward_value, expected_reward_value)

    assert c.tint is not None
    assert c.tint[0] == f32(expected_tint[0])
    assert c.tint[1] == f32(expected_tint[1])
    assert c.tint[2] == f32(expected_tint[2])
    assert c.tint[3] == f32(1.0)


def test_rarity_divisor_shrinks_with_xp_and_floors() -> None:
    # At xp=0 this must reproduce the original flat odds exactly.
    assert _survival_rarity_divisor(19, 6, 0, xp_per_step=15_000) == 19
    assert _survival_rarity_divisor(30, 8, 0, xp_per_step=20_000) == 30
    assert _survival_rarity_divisor(58, 12, 0, xp_per_step=25_000) == 58

    # Stays flat right up to reaching SURVIVAL_RARITY_RAMP_START_LEVEL...
    ramp_xp = survival_level_threshold(SURVIVAL_RARITY_RAMP_START_LEVEL - 1)
    assert _survival_rarity_divisor(19, 6, ramp_xp, xp_per_step=15_000) == 19
    # ...then climbs (shrinks the divisor => raises the hit chance) with XP past it...
    assert _survival_rarity_divisor(19, 6, ramp_xp + 45_000, xp_per_step=15_000) == 16
    # ...and never drops below the floor, however high XP goes.
    assert _survival_rarity_divisor(19, 6, 10_000_000, xp_per_step=15_000) == 6
