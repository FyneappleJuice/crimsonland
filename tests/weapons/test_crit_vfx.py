from __future__ import annotations

import math

from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.weapon_runtime.crit_vfx import (
    CRIT_SPARK_DURATION_S,
    CritSparkEffect,
    queue_crit_spark,
    tick_crit_spark_effects,
)
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


def test_queue_crit_spark_appends_an_effect_at_the_hit_position() -> None:
    state = GameplayState()
    queue_crit_spark(state, Vec2(12.0, 34.0))

    assert len(state.pending_crit_sparks) == 1
    assert state.pending_crit_sparks[0].pos == Vec2(12.0, 34.0)
    assert state.pending_crit_sparks[0].elapsed == 0.0


def test_crit_spark_ages_out_after_its_duration() -> None:
    state = GameplayState()
    state.pending_crit_sparks.append(CritSparkEffect(pos=Vec2()))

    tick_crit_spark_effects(state, CRIT_SPARK_DURATION_S - 0.05)
    assert len(state.pending_crit_sparks) == 1

    tick_crit_spark_effects(state, 0.1)
    assert state.pending_crit_sparks == []


def test_tick_is_a_no_op_with_no_pending_effects() -> None:
    state = GameplayState()
    tick_crit_spark_effects(state, 0.05)
    assert state.pending_crit_sparks == []


def test_a_real_crit_hit_queues_a_spark_at_the_creature() -> None:
    """A primary-projectile hit stamped did_crit=True should queue a spark at
    the struck creature's position - the actual wiring in
    projectiles/runtime/projectile_pool.py, not just the crit_vfx module in
    isolation."""
    state = GameplayState()
    creature = _creature(pos=Vec2(30.0, 0.0), hp=100_000.0)
    pool = ProjectilePool(size=1)
    idx = pool.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=30.0,
    )
    pool.entries[idx].did_crit = True

    pool.step(
        PrimaryStepCtx(
            dt=0.1,
            creatures=[creature],
            options=make_projectile_update_options(world_size=1024.0, runtime_state=state),
        ),
    )

    assert len(state.pending_crit_sparks) == 1
    assert state.pending_crit_sparks[0].pos == creature.pos


def test_a_non_crit_hit_queues_nothing() -> None:
    state = GameplayState()
    creature = _creature(pos=Vec2(30.0, 0.0), hp=100_000.0)
    pool = ProjectilePool(size=1)
    idx = pool.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=30.0,
    )
    pool.entries[idx].did_crit = False

    pool.step(
        PrimaryStepCtx(
            dt=0.1,
            creatures=[creature],
            options=make_projectile_update_options(world_size=1024.0, runtime_state=state),
        ),
    )

    assert state.pending_crit_sparks == []
