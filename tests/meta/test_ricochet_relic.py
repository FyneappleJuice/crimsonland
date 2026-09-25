from __future__ import annotations

import math

import pytest

from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


@pytest.fixture(autouse=True)
def _ricochet_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.RICOCHET_HIGH),))


def _fire(pool: ProjectilePool) -> None:
    pool.spawn(
        pos=Vec2(110.0, 512.0),
        angle=math.pi / 2,  # heading convention: 0=up, +90deg=+x
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
    )


def _step(pool: ProjectilePool, creatures: tuple, *, ticks: int) -> None:
    player = PlayerState(index=0, pos=Vec2(100.0, 512.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    options = make_projectile_update_options(world_size=1024.0, players=[player])
    for _ in range(ticks):
        pool.step(PrimaryStepCtx(dt=1.0 / 60.0, creatures=creatures, options=options))


@pytest.mark.parametrize("angle_deg", range(0, 360, 30))
def test_bounce_reaches_a_target_overlapping_the_struck_creature(angle_deg: int) -> None:
    # Packed-horde case: the chain target sits inside the struck creature's own
    # hit radius, so the bounce used to re-hit the struck creature instead.
    struck = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    a = math.radians(angle_deg)
    other = _creature(pos=Vec2(400.0 + 10.0 * math.cos(a), 512.0 + 10.0 * math.sin(a)), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    _fire(pool)
    _step(pool, (struck, other), ticks=60)
    assert other.hp < 1.0e9


def test_reused_pool_slot_does_not_inherit_the_chained_flag() -> None:
    pool = ProjectilePool(size=4)
    idx = pool.spawn(pos=Vec2(0.0, 0.0), angle=0.0, type_id=ProjectileTemplateId.PISTOL, owner=OwnerRef.none())
    pool.entries[idx].ricochet_chained = True
    pool.entries[idx].ricochet_ignore_idx = 3
    pool.entries[idx].active = False

    reused = pool.spawn(pos=Vec2(0.0, 0.0), angle=0.0, type_id=ProjectileTemplateId.PISTOL, owner=OwnerRef.none())
    assert reused == idx
    assert pool.entries[reused].ricochet_chained is False
    assert pool.entries[reused].ricochet_ignore_idx == -1


def test_every_shot_in_sustained_fire_chains() -> None:
    struck = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    other = _creature(pos=Vec2(400.0, 650.0), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    for _ in range(40):
        before = other.hp
        _fire(pool)
        _step(pool, (struck, other), ticks=4)  # next shot fires before this one's bounce slot frees up
        _step(pool, (struck, other), ticks=20)
        assert other.hp < before
