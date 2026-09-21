from __future__ import annotations

import math

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.gameplay import GameplayState
from crimson.math_parity import NATIVE_HALF_PI, NATIVE_PI, f32
from crimson.projectiles.runtime import (
    PrimaryStepCtx,
    ProjectilePool,
    SecondaryProjectilePool,
    SecondarySpawnSpec,
    SecondaryStepCtx,
)
from crimson.projectiles.types import SecondaryProjectileTypeId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.factories import make_creature_state, make_projectile_update_options
from tests.support.helpers import ScriptedCrand


def test_shock_chain_initial_target_miss_handling() -> None:
    pool = ProjectilePool(size=4)
    state = GameplayState(projectiles=pool)
    player = PlayerState(index=0, pos=Vec2())
    creatures = [make_creature_state(pos=Vec2(50.0, 0.0), active=False)]

    bonus_apply(state, player, BonusId.SHOCK_CHAIN, origin=player.pos, creatures=creatures, players=[player])

    assert state.shock_chain_links_left == 0
    assert state.sfx_queue == []
    assert sum(1 for entry in pool.entries if entry.active) == 0
    assert state.shock_chain_projectile_id == -1


def test_shock_chain_uses_native_f32_nearest_ordering() -> None:
    pool = ProjectilePool(size=4)
    state = GameplayState(projectiles=pool)
    player = PlayerState(index=0, pos=Vec2())
    first_pos = Vec2(-1727.156494140625, -1351.4605712890625)
    creatures = [
        make_creature_state(pos=first_pos, hp=100.0),
        make_creature_state(pos=Vec2(1722.1292724609375, -1357.8604736328125), hp=100.0),
    ]

    bonus_apply(state, player, BonusId.SHOCK_CHAIN, origin=player.pos, creatures=creatures, players=[player])

    projectile = pool.entries[state.shock_chain_projectile_id]
    expected_angle = f32(math.atan2(first_pos.y, first_pos.x) - NATIVE_HALF_PI - NATIVE_PI)
    assert projectile.angle == expected_angle


def test_shock_chain_retarget_miss_handling() -> None:
    pool = ProjectilePool(size=8)
    state = GameplayState(projectiles=pool)
    player = PlayerState(index=0, pos=Vec2())
    creatures = [
        make_creature_state(pos=Vec2(200.0, 0.0), active=False),
        make_creature_state(pos=Vec2(50.0, 0.0), hp=100.0),
    ]

    bonus_apply(state, player, BonusId.SHOCK_CHAIN, origin=player.pos, creatures=creatures, players=[player])
    first_proj = int(state.shock_chain_projectile_id)
    assert first_proj >= 0

    for _ in range(2):
        pool.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=creatures,
                options=make_projectile_update_options(
                    world_size=1024.0,
                    rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
                    runtime_state=state,
                ),
            ),
        )

    assert state.shock_chain_links_left == 0x1F
    assert state.shock_chain_projectile_id == first_proj
    assert sum(1 for entry in pool.entries if entry.active) == 1


def test_seeker_spawn_target_miss_handling() -> None:
    pool = SecondaryProjectilePool(size=1)
    creatures = [make_creature_state(pos=Vec2(100.0, 0.0), active=False)]

    idx = pool.spawn_from_spec(
        SecondarySpawnSpec(
            pos=Vec2(),
            angle=0.0,
            type_id=SecondaryProjectileTypeId.HOMING_ROCKET,
            creatures=creatures,
        ),
    )

    assert pool.entries[idx].target_id == -1


def test_seeker_retarget_miss_handling() -> None:
    pool = SecondaryProjectilePool(size=1)
    creatures = [make_creature_state(pos=Vec2(100.0, 0.0), active=False)]
    state = GameplayState(secondary_projectiles=pool)

    idx = pool.spawn_from_spec(
        SecondarySpawnSpec(
            pos=Vec2(),
            angle=0.0,
            type_id=SecondaryProjectileTypeId.HOMING_ROCKET,
        ),
    )
    pool.entries[idx].target_id = 0

    pool.step(
        SecondaryStepCtx(
            dt=0.01,
            creatures=creatures,
            runtime_state=state,
        ),
    )

    assert pool.entries[idx].target_id == -1
