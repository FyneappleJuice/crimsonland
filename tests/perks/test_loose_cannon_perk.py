from __future__ import annotations

import statistics

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureFlags
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand


def _hit(
    *,
    damage_type: CreatureDamageType,
    is_projectile_hit: bool = False,
    hp: float = 1_000_000.0,
) -> float:
    """Return the actual damage dealt (positive) or healed (negative)."""

    creature = CreatureState(active=True, hp=hp, max_hp=hp, size=50.0, flags=CreatureFlags(0))
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.LOOSE_CANNON)] = 1

    creature_apply_damage(
        creature,
        damage_amount=100.0,
        damage_type=int(damage_type),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
        is_projectile_hit=is_projectile_hit,
    )
    return hp - float(creature.hp)


def test_loose_cannon_leaves_dot_damage_completely_untouched() -> None:
    # Self-tick, and Fire/Explosion/Ion's non-direct-hit half, must always
    # deal exactly their flat value - no variance, every single time.
    dot_cases = [
        (CreatureDamageType.SELF_TICK, False),
        (CreatureDamageType.FIRE, False),
        (CreatureDamageType.EXPLOSION, False),
        (CreatureDamageType.ION, False),
    ]
    for damage_type, is_projectile_hit in dot_cases:
        for _ in range(20):
            assert _hit(damage_type=damage_type, is_projectile_hit=is_projectile_hit) == pytest.approx(100.0)


def test_loose_cannon_varies_every_non_dot_hit() -> None:
    non_dot_cases = [
        (CreatureDamageType.BULLET, False),
        (CreatureDamageType.PLASMA, False),
        (CreatureDamageType.ENERGY, False),
        (CreatureDamageType.LIGHTNING, False),
        (CreatureDamageType.MELEE, False),
        (CreatureDamageType.FIRE, True),
        (CreatureDamageType.EXPLOSION, True),
        (CreatureDamageType.ION, True),
    ]
    for damage_type, is_projectile_hit in non_dot_cases:
        samples = {_hit(damage_type=damage_type, is_projectile_hit=is_projectile_hit) for _ in range(30)}
        # Overwhelmingly unlikely all 30 independent draws land on exactly
        # the same float if variance is actually being applied.
        assert len(samples) > 1


def test_loose_cannon_stays_within_its_declared_range_and_averages_to_1_5x() -> None:
    samples = [_hit(damage_type=CreatureDamageType.BULLET) for _ in range(2000)]
    assert all(-100.0 <= value <= 400.0 for value in samples)
    assert statistics.mean(samples) == pytest.approx(150.0, rel=0.1)


def test_loose_cannon_can_roll_negative_and_heal_the_target() -> None:
    saw_a_heal = False
    for _ in range(500):
        if _hit(damage_type=CreatureDamageType.BULLET) < 0.0:
            saw_a_heal = True
            break
    assert saw_a_heal
