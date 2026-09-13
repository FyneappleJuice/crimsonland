from __future__ import annotations

from crimson.creatures.damage_types import CreatureDamageType
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import RecordingCreatureDamageRuntime
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


def _fire(weapon_id: WeaponId, *, ion_payload_timer: float):
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.ion_payload_timer = float(ion_payload_timer)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )
    return state, player


def test_single_pellet_weapon_is_flagged_when_active() -> None:
    state, _ = _fire(WeaponId.PISTOL, ion_payload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].is_ion_payload is True


def test_single_pellet_weapon_is_untouched_when_inactive() -> None:
    state, _ = _fire(WeaponId.PISTOL, ion_payload_timer=0.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert live[0].is_ion_payload is False


def test_shotgun_flags_only_the_centre_most_pellet() -> None:
    state, _ = _fire(WeaponId.SHOTGUN, ion_payload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 12
    flagged = [i for i, p in enumerate(live) if p.is_ion_payload]
    assert flagged == [12 // 2]


def _step_and_hit(*, is_ion_payload: bool) -> tuple[ProjectilePool, GameplayState, int]:
    pool = ProjectilePool(size=8)
    creature = _creature(pos=Vec2(100.0, 100.0))
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    state = GameplayState()

    idx = pool.spawn(
        pos=Vec2(99.0, 100.0),
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=100.0,
    )
    pool.entries[idx].is_ion_payload = is_ion_payload
    pool.step(
        PrimaryStepCtx(
            dt=0.06,
            creatures=(creature,),
            options=make_projectile_update_options(world_size=1024.0, players=[player], runtime_state=state),
        ),
    )
    return pool, state, idx


def test_flagged_pellet_spawns_a_stationary_lingering_cloud_and_consumes_the_flag() -> None:
    pool, state, idx = _step_and_hit(is_ion_payload=True)

    assert pool.entries[idx].is_ion_payload is False  # consumed

    clouds = [
        p for i, p in enumerate(pool.entries) if i != idx and p.active and p.type_id == ProjectileTemplateId.ION_MINIGUN
    ]
    assert len(clouds) == 1
    cloud = clouds[0]
    assert cloud.life_timer < 0.4  # already inside the native "linger" window
    assert cloud.vel == Vec2()  # stationary


def test_unflagged_pellet_spawns_no_cloud() -> None:
    pool, _state, idx = _step_and_hit(is_ion_payload=False)
    clouds = [p for i, p in enumerate(pool.entries) if i != idx and p.active]
    assert clouds == []


def test_the_cloud_deals_real_lingering_ion_damage() -> None:
    pool, state, idx = _step_and_hit(is_ion_payload=True)
    cloud_idx = next(
        i for i, p in enumerate(pool.entries) if i != idx and p.active and p.type_id == ProjectileTemplateId.ION_MINIGUN
    )

    # A second creature standing near (not on top of) the impact point, within
    # the Ion Minigun's own lingering-AoE radius (60px).
    bystander = _creature(pos=Vec2(pool.entries[idx].pos.x + 30.0, pool.entries[idx].pos.y), hp=1e9, size=20.0)
    runtime = RecordingCreatureDamageRuntime(creatures=[bystander])

    pool.step(
        PrimaryStepCtx(
            dt=0.016,
            creatures=(bystander,),
            options=make_projectile_update_options(
                world_size=1024.0,
                players=[PlayerState(index=0, pos=Vec2(0.0, 0.0))],
                runtime_state=state,
                creature_damage_runtime=runtime,
            ),
        ),
    )

    assert len(runtime.calls) >= 1
    assert all(int(call[2]) == int(CreatureDamageType.ION) for call in runtime.calls)
    assert pool.entries[cloud_idx].active  # still lingering (life_timer started at 0.35)
