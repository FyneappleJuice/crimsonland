from __future__ import annotations

import math

import pytest

from crimson.creatures.runtime import CreaturePool
from crimson.creatures.spawn import CreatureAiMode, CreatureFlags, CreatureInit
from crimson.gameplay import GameplayState
from crimson.math_parity import f32
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx
from crimson.projectiles.types import ProjectileTemplateId
from crimson.rng_caller_static import RngCallerStatic
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from grim.sfx_map import SfxId
from tests.support.factories import (
    RecordingProjectileHitRuntime,
    make_creature_update_options,
    make_projectile_update_options,
)
from tests.support.helpers import ScriptedCrand, assert_float_close


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % math.tau - math.pi


def test_ranged_creature_fires_along_heading_not_direct_aim() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 200.0))

    pool = CreaturePool()
    creature = pool.entries[0]
    creature.active = True
    creature.hp = 10.0
    creature.pos = Vec2()
    creature.heading = 0.0
    creature.flags = CreatureFlags.RANGED_ATTACK_SHOCK
    creature.ai_mode = CreatureAiMode.CHASE_PLAYER
    creature.contact_damage = 0.0

    result = pool.update(0.001, options=make_creature_update_options(state=state, players=[player]))

    spawned = [proj for proj in state.projectiles.entries if proj.active]
    assert len(spawned) == 1
    proj = spawned[0]
    assert proj.hits_players is True
    assert int(proj.type_id) == 9
    assert_float_close(proj.angle, creature.heading)

    direct_aim = math.atan2(player.pos.y - creature.pos.y, player.pos.x - creature.pos.x) + math.pi / 2.0
    assert abs(_wrap_angle(proj.angle - direct_aim)) > 0.1
    assert result.sfx == (SfxId.SHOCK_FIRE,)


def test_ranged_creature_does_not_fire_when_too_close() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 64.0))

    pool = CreaturePool()
    creature = pool.entries[0]
    creature.active = True
    creature.hp = 10.0
    creature.pos = Vec2()
    creature.flags = CreatureFlags.RANGED_ATTACK_SHOCK
    creature.ai_mode = CreatureAiMode.CHASE_PLAYER
    creature.move_speed = 0.0
    creature.contact_damage = 0.0

    result = pool.update(0.001, options=make_creature_update_options(state=state, players=[player]))

    spawned = [proj for proj in state.projectiles.entries if proj.active]
    assert not spawned
    assert result.sfx == ()


def test_ranged_variant_uses_orbit_radius_as_projectile_type() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 200.0))
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)

    pool = CreaturePool()
    creature = pool.entries[0]
    creature.active = True
    creature.hp = 10.0
    creature.pos = Vec2()
    creature.heading = 0.0
    creature.flags = CreatureFlags.RANGED_ATTACK_VARIANT
    creature.ai_mode = CreatureAiMode.CHASE_PLAYER
    creature.orbit_radius = 26.0
    creature.orbit_angle = 0.4
    creature.contact_damage = 0.0

    result = pool.update(
        0.001,
        options=make_creature_update_options(
            state=state,
            players=[player],
            rng=rng,
        ),
    )

    spawned = [proj for proj in state.projectiles.entries if proj.active]
    assert len(spawned) == 1
    proj = spawned[0]
    assert proj.hits_players is True
    assert int(proj.type_id) == 26
    assert creature.attack_cooldown == f32(0.4)
    assert result.sfx == (SfxId.PLASMAMINIGUN_FIRE,)
    assert [record.caller for record in rng.records_since()] == [
        RngCallerStatic.CREATURE_UPDATE_ALL_PLASMAMINIGUN_COOLDOWN,
    ]


def test_spawn_init_packs_ranged_projectile_type_into_orbit_radius() -> None:
    pool = CreaturePool()
    init = CreatureInit(
        origin_template_id=0,
        pos=Vec2(),
        heading=0.0,
        phase_seed=0,
        flags=CreatureFlags.RANGED_ATTACK_VARIANT,
        ai_mode=2,
        ranged_projectile_type=26,
    )
    idx = pool.spawn_init(init)
    assert idx is not None
    assert pool.entries[idx].orbit_radius == 26.0


def test_ranged_projectile_can_damage_player() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(4.0, 0.0))

    state.projectiles.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.PLASMA_RIFLE,
        owner=OwnerRef.from_creature(0),
        travel_budget=45.0,
        hits_players=True,
    )

    hit_runtime = RecordingProjectileHitRuntime(players=[player])

    state.projectiles.step(
        PrimaryStepCtx(
            dt=0.001,
            creatures=[],
            options=make_projectile_update_options(
                world_size=1024.0,
                rng=state.rng,
                runtime_state=state,
                players=[player],
                hit_runtime=hit_runtime,
            ),
        ),
    )

    assert hit_runtime.player_damage_calls == [(0, 10.0)]
    assert player.health < 100.0


def test_ranged_projectile_can_damage_creature_before_player() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(4.0, 0.0))

    pool = CreaturePool()
    shooter = pool.entries[0]
    shooter.active = True
    shooter.hp = 10.0
    shooter.pos = Vec2(-200.0, -200.0)

    target = pool.entries[1]
    target.active = True
    target.hp = 100.0
    target.pos = Vec2(4.0, 0.0)

    state.projectiles.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.PLASMA_RIFLE,
        owner=OwnerRef.from_creature(0),
        travel_budget=45.0,
        hits_players=True,
    )

    hit_runtime = RecordingProjectileHitRuntime(players=[player])

    state.projectiles.step(
        PrimaryStepCtx(
            dt=0.1,
            creatures=pool.entries[:2],
            options=make_projectile_update_options(
                world_size=1024.0,
                rng=state.rng,
                runtime_state=state,
                players=[player],
                hit_runtime=hit_runtime,
            ),
        ),
    )

    assert target.hp < 100.0
    assert hit_runtime.player_damage_calls == []
    assert player.health == 100.0


def test_acid_lob_phases_through_creatures_and_queues_a_dot_instead_of_a_direct_hit() -> None:
    from crimson.creatures import rarity as monster_rarity

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(4.0, 0.0))

    pool = CreaturePool()
    blocker = pool.entries[0]
    blocker.active = True
    blocker.hp = 100.0
    blocker.max_hp = 100.0
    blocker.pos = Vec2(2.0, 0.0)  # sitting directly between the shot and the player

    state.projectiles.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.ACID_LOB,
        owner=OwnerRef.from_creature(1),
        travel_budget=45.0,
        hits_players=True,
    )

    hit_runtime = RecordingProjectileHitRuntime(players=[player])

    state.projectiles.step(
        PrimaryStepCtx(
            dt=0.001,
            creatures=pool.entries[:1],
            options=make_projectile_update_options(
                world_size=1024.0,
                rng=state.rng,
                runtime_state=state,
                players=[player],
                hit_runtime=hit_runtime,
            ),
        ),
    )

    assert blocker.hp == 100.0  # phased straight through, not stopped by it
    assert hit_runtime.player_damage_calls == []  # no direct hit - it's a DoT
    assert player.health == 100.0  # DoT drains over time, not instantly
    assert player.acid_dot_pending_damage == [pytest.approx(monster_rarity.ACID_LOB_DOT_TOTAL_DAMAGE)]
    assert player.acid_dot_pending_timers == [pytest.approx(monster_rarity.ACID_LOB_DOT_DURATION_S)]


def test_acid_lob_projectile_steers_partially_toward_the_player_each_tick() -> None:
    from crimson.projectiles.runtime.projectile_pool import _ACID_LOB_TURN_RATE_RAD_PER_S

    state = GameplayState()
    # Placed diagonally so the desired turn is unambiguous (not the exact
    # +-pi edge case a straight-behind target would hit).
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0))

    state.projectiles.spawn(
        pos=Vec2(0.0, 0.0),
        angle=0.0,  # aimed somewhere else entirely
        type_id=ProjectileTemplateId.ACID_LOB,
        owner=OwnerRef.from_creature(0),
        travel_budget=45.0,
        hits_players=True,
    )
    proj = state.projectiles.entries[0]
    start_angle = float(proj.angle)

    dt = 0.05
    state.projectiles.step(
        PrimaryStepCtx(
            dt=dt,
            creatures=[],
            options=make_projectile_update_options(
                world_size=1024.0,
                rng=state.rng,
                runtime_state=state,
                players=[player],
            ),
        ),
    )

    turned = float(proj.angle) - start_angle
    # The true bearing to the player is far more than one tick's max turn can
    # cover, so the steering should be clamped to exactly the turn rate - not
    # a full snap (only "some" homing capability was asked for).
    assert turned == pytest.approx(_ACID_LOB_TURN_RATE_RAD_PER_S * dt, abs=1e-6)
