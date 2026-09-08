from __future__ import annotations

from crimson.owner_ref import OwnerKind, OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import RecordingCreatureDamageRuntime, make_projectile_update_options
from tests.support.factories import make_creature_state as _creature


def _fire_and_step(
    *,
    type_id: ProjectileTemplateId,
    fork_timer: float,
    pool_size: int = 4,
    weapon_id: WeaponId = WeaponId.PISTOL,
) -> tuple[ProjectilePool, int]:
    pool = ProjectilePool(size=pool_size)
    creature = _creature(pos=Vec2(100.0, 100.0))
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), weapon=WeaponSlot(weapon_id=weapon_id))
    player.projectile_fork_timer = float(fork_timer)

    idx = pool.spawn(
        pos=Vec2(99.0, 100.0),
        angle=0.0,
        type_id=type_id,
        owner=OwnerRef.from_local_player(0),
        travel_budget=100.0,
    )
    pool.step(
        PrimaryStepCtx(
            dt=0.06,
            creatures=(creature,),
            options=make_projectile_update_options(world_size=1024.0, players=[player]),
        ),
    )
    return pool, idx


def test_fork_shot_splits_a_non_piercing_hit_into_two() -> None:
    pool, idx = _fire_and_step(type_id=ProjectileTemplateId.PISTOL, fork_timer=5.0)

    original = pool.entries[idx]
    assert original.reserved == 1.0, "the projectile that forked should be marked so it can't fork again"

    children = [
        (i, p)
        for i, p in enumerate(pool.entries)
        if i != idx and p.active and p.type_id == ProjectileTemplateId.PISTOL
    ]
    assert len(children) == 2, "exactly two forked children should spawn"
    angles = sorted(round(float(p.angle), 4) for _, p in children)
    assert angles == sorted(round(a, 4) for a in (-1.0471976, 1.0471976))
    for _, child in children:
        assert child.reserved == 1.0, "forked children must be marked so they don't fork again on their next hit"
        # Re-owned to the struck creature (index 0, the only creature here),
        # same as Splitter Gun - this is what lets the owner-collision check
        # in projectile_pool.py skip re-hitting that same creature immediately.
        assert child.owner == OwnerRef.from_creature(0)
        assert child.owner.kind == OwnerKind.CREATURE


def test_fork_shot_children_do_not_immediately_reconsume_the_struck_creature() -> None:
    pool = ProjectilePool(size=4)
    creature = _creature(pos=Vec2(100.0, 100.0))
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.projectile_fork_timer = 5.0
    damage_runtime = RecordingCreatureDamageRuntime(creatures=[creature])

    pool.spawn(
        pos=Vec2(99.0, 100.0),
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=100.0,
    )
    pool.step(
        PrimaryStepCtx(
            dt=0.06,
            creatures=(creature,),
            options=make_projectile_update_options(
                world_size=1024.0,
                players=[player],
                creature_damage_runtime=damage_runtime,
            ),
        ),
    )

    # The parent hits the creature once; the two forked children spawn on top
    # of it but must NOT also register as hits against that same creature.
    assert len(damage_runtime.calls) == 1, (
        f"expected exactly one damage application to the struck creature, got {damage_runtime.calls}"
    )


def test_fork_shot_does_nothing_without_an_active_timer() -> None:
    pool, idx = _fire_and_step(type_id=ProjectileTemplateId.PISTOL, fork_timer=0.0)

    active_count = sum(1 for p in pool.entries if p.active)
    assert active_count == 1, "no bonus timer active -> no forking, only the original projectile remains"
    assert pool.entries[idx].reserved == 0.0


def test_fork_shot_skips_piercing_weapons() -> None:
    pool, idx = _fire_and_step(type_id=ProjectileTemplateId.GAUSS_GUN, fork_timer=5.0, pool_size=6)

    active_count = sum(1 for p in pool.entries if p.active)
    assert active_count == 1, "Gauss Gun already pierces; Fork Shot must leave it alone"
    assert pool.entries[idx].reserved == 0.0


def _fork_children(pool: ProjectilePool, parent_idx: int, type_id: ProjectileTemplateId) -> list:
    return [p for i, p in enumerate(pool.entries) if i != parent_idx and p.active and p.type_id == type_id]


def test_fork_children_off_a_shotgun_carry_the_half_damage_marker() -> None:
    pool, idx = _fire_and_step(
        type_id=ProjectileTemplateId.SHOTGUN,
        fork_timer=5.0,
        weapon_id=WeaponId.SHOTGUN,
    )
    children = _fork_children(pool, idx, ProjectileTemplateId.SHOTGUN)
    assert len(children) == 2
    assert all(child.reserved == 2.0 for child in children)  # 2.0 = shotgun fork child
    assert pool.entries[idx].reserved == 1.0  # the parent itself keeps full damage


def test_fork_children_off_a_non_shotgun_are_full_damage() -> None:
    pool, idx = _fire_and_step(
        type_id=ProjectileTemplateId.PISTOL,
        fork_timer=5.0,
        weapon_id=WeaponId.ASSAULT_RIFLE,
    )
    children = _fork_children(pool, idx, ProjectileTemplateId.PISTOL)
    assert len(children) == 2
    assert all(child.reserved == 1.0 for child in children)


def test_a_shotgun_fork_child_deals_half_the_damage_of_a_plain_one() -> None:
    def _hit_damage(reserved: float) -> float:
        pool = ProjectilePool(size=2)
        creature = _creature(pos=Vec2(100.0, 100.0), hp=100000.0)
        runtime = RecordingCreatureDamageRuntime(creatures=[creature])
        i = pool.spawn(
            pos=Vec2(99.0, 100.0),
            angle=0.0,
            type_id=ProjectileTemplateId.SHOTGUN,
            owner=OwnerRef.from_local_player(0),
            travel_budget=100.0,
        )
        pool.entries[i].reserved = reserved
        pool.step(
            PrimaryStepCtx(
                dt=0.06,
                creatures=(creature,),
                options=make_projectile_update_options(
                    world_size=1024.0,
                    players=[PlayerState(index=0, pos=Vec2())],
                    creature_damage_runtime=runtime,
                ),
            ),
        )
        assert runtime.calls, "the projectile should have hit the creature"
        return runtime.calls[0][1]

    plain = _hit_damage(1.0)
    shotgun_child = _hit_damage(2.0)
    assert shotgun_child == plain * 0.5
