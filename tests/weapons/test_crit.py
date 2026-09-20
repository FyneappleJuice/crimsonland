from __future__ import annotations

import math

import pytest

from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.weapon_runtime.crit import (
    CRIT_CHANCE_BY_ARCHETYPE,
    CRIT_MULTIPLIER,
    crit_chance_for_weapon,
    roll_crit_mult,
)
from crimson.weapon_runtime.tags import WeaponArchetype
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


def test_base_crit_multiplier_is_200_percent() -> None:
    assert CRIT_MULTIPLIER == 2.0


@pytest.mark.parametrize(
    ("weapon_id", "expected_chance"),
    [
        (WeaponId.PISTOL, 0.10),
        (WeaponId.ASSAULT_RIFLE, 0.20),
        (WeaponId.SHOTGUN, 0.05),
        (WeaponId.MEAN_MINIGUN, 0.05),
        (WeaponId.PLASMA_CANNON, 0.15),
        (WeaponId.PULSE_GUN, 0.05),  # Minigun archetype
    ],
)
def test_crit_chance_matches_the_given_archetype_table(weapon_id: WeaponId, expected_chance: float) -> None:
    assert crit_chance_for_weapon(weapon_id) == pytest.approx(expected_chance)


def test_crit_chance_by_archetype_covers_every_archetype() -> None:
    for archetype in WeaponArchetype:
        assert archetype in CRIT_CHANCE_BY_ARCHETYPE


def test_roll_crit_mult_only_ever_returns_two_values() -> None:
    seen = {round(roll_crit_mult(WeaponId.ASSAULT_RIFLE), 9) for _ in range(2000)}
    assert seen == {round(1.0, 9), round(CRIT_MULTIPLIER, 9)}


def test_roll_crit_mult_matches_the_archetype_chance_over_many_rolls() -> None:
    n = 20_000
    crits = sum(1 for _ in range(n) if roll_crit_mult(WeaponId.ASSAULT_RIFLE) == pytest.approx(CRIT_MULTIPLIER))
    # Rifle = 20% chance; a 20000-sample binomial has a tiny window around 0.20.
    assert 0.18 < crits / n < 0.22


def test_roll_crit_mult_is_always_one_at_zero_chance() -> None:
    # Utility archetype (0% chance, e.g. shelved Shrinkifier 5K / Plague Spreader).
    for _ in range(200):
        assert roll_crit_mult(WeaponId.SHRINKIFIER_5K) == pytest.approx(1.0)


def test_average_damage_over_many_shots_matches_the_scaled_up_no_crit_hit() -> None:
    """Neutrality now lives in weapons.py's WEAPON_TABLE (each crit-eligible
    weapon's damage_scale is pre-shrunk by /(1 + chance)), not in a runtime
    compensation factor. So a real average over many rolled shots should land
    at `(a single crit_mult=1.0 hit) * (1 + chance)` - scaling the (already
    shrunk) baseline back up by the same headroom that was baked out of it -
    not at the raw baseline itself."""

    def fire_once(crit_mult: float) -> float:
        creature = _creature(pos=Vec2(30.0, 0.0), hp=100_000.0)
        pool = ProjectilePool(size=1)
        idx = pool.spawn(
            pos=Vec2(),
            angle=math.pi / 2.0,
            type_id=ProjectileTemplateId.ASSAULT_RIFLE,
            owner=OwnerRef.from_local_player(0),
            travel_budget=30.0,
        )
        pool.entries[idx].crit_mult = float(crit_mult)
        hp0 = float(creature.hp)
        pool.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=[creature],
                options=make_projectile_update_options(world_size=1024.0),
            ),
        )
        return hp0 - float(creature.hp)

    baseline = fire_once(1.0)
    assert baseline > 0.0
    chance = crit_chance_for_weapon(WeaponId.ASSAULT_RIFLE)
    expected_average = baseline * (1.0 + chance)

    n = 5000
    total = sum(fire_once(roll_crit_mult(WeaponId.ASSAULT_RIFLE)) for _ in range(n))
    average = total / n
    assert average == pytest.approx(expected_average, rel=0.03)


def test_crit_mult_on_the_projectile_scales_the_recorded_hit() -> None:
    def fire(crit_mult: float) -> float:
        creature = _creature(pos=Vec2(30.0, 0.0), hp=100_000.0)
        pool = ProjectilePool(size=1)
        idx = pool.spawn(
            pos=Vec2(),
            angle=math.pi / 2.0,
            type_id=ProjectileTemplateId.PISTOL,
            owner=OwnerRef.from_local_player(0),
            travel_budget=30.0,
        )
        pool.entries[idx].crit_mult = float(crit_mult)
        hp0 = float(creature.hp)
        pool.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=[creature],
                options=make_projectile_update_options(world_size=1024.0),
            ),
        )
        return hp0 - float(creature.hp)

    base = fire(1.0)
    assert base > 0.0
    assert fire(2.0) == pytest.approx(base * 2.0, rel=1e-4)


# --- Flamethrower / Arc Gun: no damage crit --------------------------------


def test_flamethrower_and_arc_gun_have_zero_crit_chance() -> None:
    assert crit_chance_for_weapon(WeaponId.FLAMETHROWER) == 0.0
    assert crit_chance_for_weapon(WeaponId.BLOW_TORCH) == 0.0
    assert crit_chance_for_weapon(WeaponId.HR_FLAMER) == 0.0
    assert crit_chance_for_weapon(WeaponId.BUBBLEGUN) == 0.0
    assert crit_chance_for_weapon(WeaponId.RAYGUN) == 0.0
    # At 0% chance, roll_crit_mult always returns 1.0 - no crit is possible.
    assert all(roll_crit_mult(WeaponId.FLAMETHROWER) == 1.0 for _ in range(200))
    assert all(roll_crit_mult(WeaponId.RAYGUN) == 1.0 for _ in range(200))


def test_flame_particle_crit_scales_ignite_flammability_not_damage() -> None:
    """Flamethrower's crit_mult (should its archetype chance ever go above
    0%) is wired to ignite flammability gain, not the direct hit - effects.py's
    flame-particle collision code. Verified directly here since the current
    0% archetype chance makes this a no-op in real play."""

    def hit(crit_mult: float) -> tuple[float, float]:
        state = GameplayState()
        creature = CreatureState()
        creature.active = True
        creature.hp = 100_000.0
        creature.pos = Vec2(16.0, 0.0)
        creature.size = 50.0
        creature.lifecycle_stage = 16.0
        idx = state.particles.spawn_particle(pos=Vec2(0.0, 0.0), angle=0.0, intensity=1.0)
        state.particles.entries[idx].crit_mult = float(crit_mult)
        hp0 = float(creature.hp)
        flammability0 = float(creature.ignite_flammability)
        state.particles.update(0.016, creatures=[creature])
        return hp0 - float(creature.hp), float(creature.ignite_flammability) - flammability0

    damage_normal, heat_normal = hit(1.0)
    damage_crit, heat_crit = hit(2.0)

    assert damage_normal > 0.0
    assert heat_normal > 0.0
    assert damage_crit == pytest.approx(damage_normal, rel=1e-4)  # damage untouched by crit
    assert heat_crit == pytest.approx(heat_normal * 2.0, rel=1e-4)  # heat gain doubled
