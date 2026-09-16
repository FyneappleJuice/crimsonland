from __future__ import annotations

import pytest

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.bonuses.ion_overload import (
    ION_OVERLOAD_BASE_CHARGE_SECONDS,
    ION_OVERLOAD_BASE_DPS,
    ION_OVERLOAD_BASE_DURATION,
    ION_OVERLOAD_BASE_RADIUS,
    bloom_ion_overload_nova,
    fire_ion_overload_bolt,
    ion_overload_scale,
    update_ion_overload_clouds,
)
from crimson.creatures.damage_types import CreatureDamageType
from crimson.effects import EffectPool
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.perks.runtime.effects_context import PerksUpdateEffectsCtx
from crimson.perks.runtime.player_bonus_timers import update_player_bonus_timers
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.state_types import IonOverloadState, PlayerState
from grim.geom import Vec2
from tests.support.factories import (
    RecordingCreatureDamageRuntime,
    make_creature_state,
    make_projectile_update_options,
)


def test_pickup_starts_a_five_second_charge() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0))

    bonus_apply(state, player, BonusId.ION_OVERLOAD, origin=player.pos, creatures=[], players=[player])

    assert player.ion_overload.charge_timer == pytest.approx(ION_OVERLOAD_BASE_CHARGE_SECONDS)
    assert player.ion_overload.charge_seconds == pytest.approx(ION_OVERLOAD_BASE_CHARGE_SECONDS)


def test_repeat_pickup_while_charging_extends_both_the_timer_and_the_charge() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0))

    bonus_apply(state, player, BonusId.ION_OVERLOAD, origin=player.pos, creatures=[], players=[player])
    bonus_apply(state, player, BonusId.ION_OVERLOAD, origin=player.pos, creatures=[], players=[player])

    assert player.ion_overload.charge_timer == pytest.approx(ION_OVERLOAD_BASE_CHARGE_SECONDS * 2.0)
    assert player.ion_overload.charge_seconds == pytest.approx(ION_OVERLOAD_BASE_CHARGE_SECONDS * 2.0)


def _run_charge_to_zero(player: PlayerState, state: GameplayState, *, dt: float = 0.1) -> None:
    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=dt, creatures=[], fx_queue=None)
    guard = 0
    while player.ion_overload.charge_timer > 0.0:
        update_player_bonus_timers(ctx)
        guard += 1
        assert guard < 100000  # safety net against an infinite loop on a bug


def test_charge_reaching_zero_fires_a_real_ion_cannon_bolt() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(321.0, 654.0), aim_heading=1.2345)
    player.ion_overload.charge_timer = ION_OVERLOAD_BASE_CHARGE_SECONDS
    player.ion_overload.charge_seconds = ION_OVERLOAD_BASE_CHARGE_SECONDS

    _run_charge_to_zero(player, state)

    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    bolt = live[0]
    assert bolt.type_id == ProjectileTemplateId.ION_CANNON
    assert bolt.ion_overload_charge == pytest.approx(ION_OVERLOAD_BASE_CHARGE_SECONDS)
    assert float(bolt.angle) == pytest.approx(float(player.aim_heading), abs=1e-3)
    # charge_seconds is consumed (spent) into the fired bolt
    assert player.ion_overload.charge_seconds == 0.0
    assert player.ion_overload.cloud_timer == 0.0  # no instant nova - it blooms on hit


def test_no_charge_fires_no_bolt() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    fire_ion_overload_bolt(state, player)
    assert [p for p in state.projectiles.entries if p.active] == []
    assert state.sfx_queue == []


def test_launching_the_bolt_queues_the_ion_cannons_own_fire_sound() -> None:
    from crimson.weapons import weapon_entry_for_projectile_type_id

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    player.ion_overload.charge_seconds = ION_OVERLOAD_BASE_CHARGE_SECONDS

    fire_ion_overload_bolt(state, player)

    expected_sound = weapon_entry_for_projectile_type_id(ProjectileTemplateId.ION_CANNON).fire_sound
    assert state.sfx_queue == [expected_sound]


def test_scale_is_one_at_the_baseline_charge() -> None:
    assert ion_overload_scale(ION_OVERLOAD_BASE_CHARGE_SECONDS) == pytest.approx(1.0)


def test_scale_grows_linearly_with_charge() -> None:
    double = ion_overload_scale(ION_OVERLOAD_BASE_CHARGE_SECONDS * 2.0)
    quadruple = ion_overload_scale(ION_OVERLOAD_BASE_CHARGE_SECONDS * 4.0)
    assert double == pytest.approx(2.0)
    assert quadruple == pytest.approx(4.0)


def test_each_successive_stacked_pickup_adds_the_same_scale() -> None:
    # The realistic stacking scenario: repeated +5s pickups. Linear scaling
    # means each one buys exactly the same extra scale as the last.
    base = ION_OVERLOAD_BASE_CHARGE_SECONDS
    scales = [ion_overload_scale(base * n) for n in (1, 2, 3, 4)]
    deltas = [b - a for a, b in zip(scales, scales[1:])]
    assert all(d == pytest.approx(deltas[0]) for d in deltas)


def _step_and_hit(*, ion_overload_charge: float) -> tuple[ProjectilePool, GameplayState, PlayerState]:
    pool = ProjectilePool(size=8)
    creature = make_creature_state(pos=Vec2(100.0, 100.0))
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    state = GameplayState()

    idx = pool.spawn(
        pos=Vec2(99.0, 100.0),
        angle=0.0,
        type_id=ProjectileTemplateId.ION_CANNON,
        owner=OwnerRef.from_local_player(0),
        travel_budget=100.0,
    )
    pool.entries[idx].ion_overload_charge = ion_overload_charge
    pool.step(
        PrimaryStepCtx(
            dt=0.06,
            creatures=(creature,),
            options=make_projectile_update_options(world_size=1024.0, players=[player], runtime_state=state),
        ),
    )
    return pool, state, player


def test_bolt_hitting_a_creature_blooms_the_scaled_nova_at_the_hit_position() -> None:
    charge = ION_OVERLOAD_BASE_CHARGE_SECONDS * 2.0
    pool, _state, player = _step_and_hit(ion_overload_charge=charge)

    scale = ion_overload_scale(charge)
    assert player.ion_overload.cloud_radius == pytest.approx(ION_OVERLOAD_BASE_RADIUS * scale)
    assert player.ion_overload.cloud_timer == pytest.approx(ION_OVERLOAD_BASE_DURATION * scale)
    assert player.ion_overload.cloud_dps == pytest.approx(ION_OVERLOAD_BASE_DPS * scale)
    # Lands at the hit position, not the player's own position (0, 0).
    assert player.ion_overload.cloud_pos.x == pytest.approx(100.0, abs=20.0)
    assert player.ion_overload.cloud_pos.y == pytest.approx(100.0, abs=20.0)


def test_unflagged_bolt_hitting_a_creature_blooms_no_nova() -> None:
    _pool, _state, player = _step_and_hit(ion_overload_charge=0.0)
    assert player.ion_overload.cloud_timer == 0.0
    assert player.ion_overload.cloud_radius == 0.0


def test_bloom_spawns_a_vfx_sized_and_timed_to_the_actual_nova() -> None:
    player = PlayerState(index=0, pos=Vec2())
    effects = EffectPool(size=8)
    charge = ION_OVERLOAD_BASE_CHARGE_SECONDS * 2.0

    bloom_ion_overload_nova(player, Vec2(50.0, 60.0), charge, effects=effects, detail_preset=5)

    live = [e for e in effects.entries if e.flags]
    assert len(live) == 1
    vfx = live[0]
    scale = ion_overload_scale(charge)
    # Full-size immediately (no growth animation) and matches the real radius,
    # not the native ion-hit ring's fixed ~148px.
    assert vfx.half_width == pytest.approx(ION_OVERLOAD_BASE_RADIUS * scale)
    assert vfx.half_height == pytest.approx(ION_OVERLOAD_BASE_RADIUS * scale)
    assert vfx.scale_step == 0.0
    # Fades over the real duration, not the native ring's fixed ~0.8s.
    assert vfx.lifetime == pytest.approx(ION_OVERLOAD_BASE_DURATION * scale)
    assert vfx.pos == Vec2(50.0, 60.0)


def test_no_effect_pool_is_a_safe_noop_for_the_vfx() -> None:
    player = PlayerState(index=0, pos=Vec2())
    # Doesn't raise, and the gameplay state (radius/timer) still updates.
    bloom_ion_overload_nova(player, Vec2(), ION_OVERLOAD_BASE_CHARGE_SECONDS, effects=None)
    assert player.ion_overload.cloud_radius == pytest.approx(ION_OVERLOAD_BASE_RADIUS)


def test_flag_is_consumed_so_a_second_hit_cant_bloom_again() -> None:
    pool, state, player = _step_and_hit(ion_overload_charge=ION_OVERLOAD_BASE_CHARGE_SECONDS)
    live = [p for p in pool.entries if p.active]
    assert all(p.ion_overload_charge == 0.0 for p in live)


def test_nova_damages_targets_inside_the_radius_and_spares_those_outside() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.ion_overload = IonOverloadState(
        cloud_timer=1.0,
        cloud_radius=300.0,
        cloud_dps=ION_OVERLOAD_BASE_DPS,
        cloud_pos=Vec2(0.0, 0.0),
    )
    inside = make_creature_state(pos=Vec2(250.0, 0.0), hp=1e9, size=10.0)
    outside = make_creature_state(pos=Vec2(400.0, 0.0), hp=1e9, size=10.0)
    runtime = RecordingCreatureDamageRuntime(creatures=[inside, outside])

    update_ion_overload_clouds([player], [inside, outside], 0.1, creature_damage_runtime=runtime)

    assert inside.hp < 1e9
    assert outside.hp == 1e9
    assert all(int(call[2]) == int(CreatureDamageType.ION) for call in runtime.calls)


def test_nova_ends_after_its_own_duration() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.ion_overload = IonOverloadState(
        cloud_timer=0.5,
        cloud_radius=300.0,
        cloud_dps=ION_OVERLOAD_BASE_DPS,
        cloud_pos=Vec2(),
    )
    creature = make_creature_state(pos=Vec2(0.0, 0.0), hp=1e9, size=10.0)
    runtime = RecordingCreatureDamageRuntime(creatures=[creature])

    update_ion_overload_clouds([player], [creature], 0.6, creature_damage_runtime=runtime)

    assert player.ion_overload.cloud_timer == 0.0
    assert player.ion_overload.cloud_radius == 0.0
    assert player.ion_overload.cloud_dps == 0.0

    hp_after_expiry = creature.hp
    update_ion_overload_clouds([player], [creature], 0.1, creature_damage_runtime=runtime)
    assert creature.hp == hp_after_expiry  # no further damage once it's over


@pytest.mark.parametrize("fps", [60.0, 120.0, 144.0])
def test_baseline_charge_deals_base_dps_worth_of_total_damage_at_any_framerate(fps: float) -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.ion_overload = IonOverloadState(
        cloud_timer=ION_OVERLOAD_BASE_DURATION,
        cloud_radius=ION_OVERLOAD_BASE_RADIUS,
        cloud_dps=ION_OVERLOAD_BASE_DPS,
        cloud_pos=Vec2(),
    )
    creature = make_creature_state(pos=Vec2(0.0, 0.0), hp=1e9, size=10.0)
    runtime = RecordingCreatureDamageRuntime(creatures=[creature])

    dt = 1.0 / fps
    for _ in range(round(ION_OVERLOAD_BASE_DURATION / dt) + 2):
        update_ion_overload_clouds([player], [creature], dt, creature_damage_runtime=runtime)

    total_damage = 1e9 - creature.hp
    # 1s duration at base dps -> total damage ~= ION_OVERLOAD_BASE_DPS, at any framerate.
    assert total_damage == pytest.approx(ION_OVERLOAD_BASE_DPS, rel=0.05)
