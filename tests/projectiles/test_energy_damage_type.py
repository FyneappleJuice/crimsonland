from __future__ import annotations

import math

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.owner_ref import OwnerRef
from crimson.perks.ids import PerkId
from crimson.progression import refresh_player_stats
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ENERGY_PROJECTILE_TEMPLATE_IDS, ProjectileTemplateId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options
from tests.support.helpers import ScriptedCrand


def _rng() -> ScriptedCrand:
    return ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)


def _player_with(*perks: PerkId) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2())
    for perk in perks:
        player.perk_counts[int(perk)] = 1
    refresh_player_stats([player])
    return player


def _apply(damage_type: CreatureDamageType, *perks: PerkId, amount: float = 100.0) -> float:
    creature = _creature(pos=Vec2(), hp=100_000.0, size=50.0)
    hp0 = float(creature.hp)
    creature_apply_damage(
        creature,
        damage_amount=amount,
        damage_type=int(damage_type),
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[_player_with(*perks)],
        rng=_rng(),
        preserve_bugs=False,
    )
    return hp0 - float(creature.hp)


# --- damage-type routing --------------------------------------------------


def test_energy_type_exists_and_plasma_templates_are_tagged() -> None:
    assert int(CreatureDamageType.ENERGY) == 8
    assert ProjectileTemplateId.PLASMA_RIFLE in ENERGY_PROJECTILE_TEMPLATE_IDS
    assert ProjectileTemplateId.PLASMA_MINIGUN in ENERGY_PROJECTILE_TEMPLATE_IDS
    assert ProjectileTemplateId.PLASMA_CANNON in ENERGY_PROJECTILE_TEMPLATE_IDS
    assert ProjectileTemplateId.SPIDER_PLASMA in ENERGY_PROJECTILE_TEMPLATE_IDS
    assert ProjectileTemplateId.PISTOL not in ENERGY_PROJECTILE_TEMPLATE_IDS
    assert ProjectileTemplateId.GAUSS_GUN not in ENERGY_PROJECTILE_TEMPLATE_IDS


# --- the perk taxonomy ---------------------------------------------------


def test_doctor_and_barrel_greaser_scale_both_kinetic_and_energy() -> None:
    base_b = _apply(CreatureDamageType.BULLET)
    base_e = _apply(CreatureDamageType.ENERGY)
    assert _apply(CreatureDamageType.BULLET, PerkId.DOCTOR) == pytest.approx(base_b * 1.2, rel=1e-4)
    assert _apply(CreatureDamageType.ENERGY, PerkId.DOCTOR) == pytest.approx(base_e * 1.2, rel=1e-4)
    assert _apply(CreatureDamageType.ENERGY, PerkId.BARREL_GREASER) == pytest.approx(base_e * 1.4, rel=1e-4)


def test_uranium_filled_bullets_is_kinetic_only() -> None:
    base_b = _apply(CreatureDamageType.BULLET)
    base_e = _apply(CreatureDamageType.ENERGY)
    assert _apply(CreatureDamageType.BULLET, PerkId.URANIUM_FILLED_BULLETS) == pytest.approx(base_b * 2.0, rel=1e-4)
    assert _apply(CreatureDamageType.ENERGY, PerkId.URANIUM_FILLED_BULLETS) == pytest.approx(base_e, rel=1e-4)


def test_energy_pre_steps_run_projectile_then_energy_layer() -> None:
    from crimson.creatures.damage import (
        _CREATURE_DAMAGE_PRE_STEPS,
        _damage_energy_damage_mult,
        _damage_kinetic_bullet_damage_mult,
        _damage_projectile_damage_mult,
    )

    energy_steps = _CREATURE_DAMAGE_PRE_STEPS[CreatureDamageType.ENERGY]
    assert _damage_projectile_damage_mult in energy_steps
    assert _damage_energy_damage_mult in energy_steps
    # kinetic-lead scaling must NOT run for energy
    assert _damage_kinetic_bullet_damage_mult not in energy_steps
    # ...and it still runs for kinetic bullets
    assert _damage_kinetic_bullet_damage_mult in _CREATURE_DAMAGE_PRE_STEPS[CreatureDamageType.BULLET]


# --- clip-heat mult stamped on the bolt --------------------------------


def test_energy_heat_mult_on_bolt_scales_the_recorded_hit() -> None:
    def fire(type_id: ProjectileTemplateId, heat_mult: float) -> float:
        creature = _creature(pos=Vec2(30.0, 0.0), hp=100_000.0)
        pool = ProjectilePool(size=1)
        idx = pool.spawn(
            pos=Vec2(),
            angle=math.pi / 2.0,
            type_id=type_id,
            owner=OwnerRef.from_local_player(0),
            travel_budget=30.0,
        )
        pool.entries[idx].energy_heat_mult = float(heat_mult)
        hp0 = float(creature.hp)
        pool.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=[creature],
                options=make_projectile_update_options(world_size=1024.0),
            ),
        )
        return hp0 - float(creature.hp)

    base = fire(ProjectileTemplateId.PLASMA_RIFLE, 1.0)
    assert base > 0.0
    assert fire(ProjectileTemplateId.PLASMA_RIFLE, 1.5) == pytest.approx(base * 1.5, rel=1e-4)
