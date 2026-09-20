from __future__ import annotations

from crimson.gameplay import GameplayState
from crimson.math_parity import f32, x87_pc24_mul, x87_pc24_sub
from crimson.perks import PerkId
from crimson.perks.runtime.apply import perk_apply
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import assert_float_close


def test_thick_skinned_keeps_two_thirds_health() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=90.0)

    perk_apply(state, [player], PerkId.THICK_SKINNED)

    assert_float_close(
        player.health,
        x87_pc24_sub(90.0, x87_pc24_mul(90.0, f32(0.33333334))),
    )


def test_thick_skinned_rounds_multiply_before_health_subtraction() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=25.506977081298828)

    perk_apply(state, [player], PerkId.THICK_SKINNED)

    assert player.health == 17.004650115966797


def test_thick_skinned_floors_at_one_hp() -> None:
    # Rewrite-only: a self-inflicted, non-enemy cost must never be the thing
    # that kills the player, so very low HP (e.g. after Infernal Contract)
    # floors at 1.0 instead of cutting further.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=1.0)

    perk_apply(state, [player], PerkId.THICK_SKINNED)

    assert player.health == 1.0


def test_thick_skinned_skips_dead_players() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=-5.0)

    perk_apply(state, [player], PerkId.THICK_SKINNED)

    assert player.health == -5.0


def test_thick_skinned_plus_cuts_the_remaining_health_by_a_further_third() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=90.0)

    perk_apply(state, [player], PerkId.THICK_SKINNED)
    after_base = player.health  # 60.0
    perk_apply(state, [player], PerkId.THICK_SKINNED_PLUS)

    assert_float_close(
        player.health,
        x87_pc24_sub(after_base, x87_pc24_mul(after_base, f32(0.33333334))),
    )
    assert_float_close(player.health, 40.0)


def test_thick_skinned_plus_composes_damage_reduction_multiplicatively() -> None:
    from crimson.progression.sources import _THICK_SKINNED_DAMAGE_SCALE, resolve_player_stats

    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.THICK_SKINNED)] = 1
    player.perk_counts[int(PerkId.THICK_SKINNED_PLUS)] = 1

    stats = resolve_player_stats(player)

    # ~0.666^2 = ~0.444 - a further third off what's left, not off the original.
    assert_float_close(stats.damage_taken_mult, _THICK_SKINNED_DAMAGE_SCALE * _THICK_SKINNED_DAMAGE_SCALE)
