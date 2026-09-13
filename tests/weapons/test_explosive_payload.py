from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.runtime.projectile_pool import (
    _EXPLOSIVE_PAYLOAD_DETONATION_SCALE,
    _EXPLOSIVE_PAYLOAD_PISTOL_DAMAGE_SCALE,
    _explosive_payload_blast_scale,
)
from crimson.projectiles.types import ProjectileTemplateId, SecondaryProjectileTypeId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


def _fire(weapon_id: WeaponId, *, explosive_payload_timer: float) -> tuple[GameplayState, PlayerState]:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.explosive_payload_timer = float(explosive_payload_timer)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )
    return state, player


def test_single_pellet_weapon_becomes_a_rocket_when_active() -> None:
    state, _ = _fire(WeaponId.PISTOL, explosive_payload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].is_rocket is True


def test_single_pellet_weapon_is_untouched_when_inactive() -> None:
    state, _ = _fire(WeaponId.PISTOL, explosive_payload_timer=0.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 1
    assert live[0].is_rocket is False


def test_shotgun_flags_only_the_centre_most_pellet() -> None:
    state, _ = _fire(WeaponId.SHOTGUN, explosive_payload_timer=5.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 12  # Shotgun pellet_count
    rockets = [i for i, p in enumerate(live) if p.is_rocket]
    assert rockets == [12 // 2]  # the centre-most pellet in spawn order


def test_shotgun_pellets_are_untouched_when_inactive() -> None:
    state, _ = _fire(WeaponId.SHOTGUN, explosive_payload_timer=0.0)
    live = [p for p in state.projectiles.entries if p.active]
    assert len(live) == 12
    assert not any(p.is_rocket for p in live)


def _step_and_hit(
    *, is_rocket: bool, type_id: ProjectileTemplateId = ProjectileTemplateId.PISTOL,
) -> tuple[ProjectilePool, GameplayState, int]:
    pool = ProjectilePool(size=4)
    creature = _creature(pos=Vec2(100.0, 100.0))
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    state = GameplayState()

    idx = pool.spawn(
        pos=Vec2(99.0, 100.0),
        angle=0.0,
        type_id=type_id,
        owner=OwnerRef.from_local_player(0),
        travel_budget=100.0,
    )
    pool.entries[idx].is_rocket = is_rocket
    pool.step(
        PrimaryStepCtx(
            dt=0.06,
            creatures=(creature,),
            options=make_projectile_update_options(world_size=1024.0, players=[player], runtime_state=state),
        ),
    )
    return pool, state, idx


def test_flagged_pellet_detonates_on_hit_and_consumes_the_flag() -> None:
    pool, state, idx = _step_and_hit(is_rocket=True)

    assert pool.entries[idx].is_rocket is False  # consumed - won't re-detonate if it pierces again

    detonations = [s for s in state.secondary_projectiles.entries if s.active]
    assert len(detonations) == 1
    assert detonations[0].type_id == SecondaryProjectileTypeId.DETONATION
    # Pistol IS the anchor weapon, so its blast is (within f32 rounding) the
    # reference scale.
    assert detonations[0].detonation_scale == pytest.approx(_EXPLOSIVE_PAYLOAD_DETONATION_SCALE, abs=1e-6)


def test_unflagged_pellet_does_not_detonate() -> None:
    _pool, state, _idx = _step_and_hit(is_rocket=False)
    assert not any(s.active for s in state.secondary_projectiles.entries)


def test_weaker_weapon_gets_a_smaller_blast_on_hit() -> None:
    # Assault Rifle's damage_scale (1.0) is a quarter of the Pistol's (4.1).
    _pool, state, _idx = _step_and_hit(is_rocket=True, type_id=ProjectileTemplateId.ASSAULT_RIFLE)
    detonations = [s for s in state.secondary_projectiles.entries if s.active]
    assert len(detonations) == 1
    assert 0.0 < detonations[0].detonation_scale < _EXPLOSIVE_PAYLOAD_DETONATION_SCALE


def test_zero_damage_scale_weapon_gets_no_blast() -> None:
    _pool, state, _idx = _step_and_hit(is_rocket=True, type_id=ProjectileTemplateId.SHRINKIFIER)
    assert not any(s.active for s in state.secondary_projectiles.entries)


# --- _explosive_payload_blast_scale: the damped scaling curve itself -------


def test_pistol_is_the_anchor() -> None:
    assert _explosive_payload_blast_scale(_EXPLOSIVE_PAYLOAD_PISTOL_DAMAGE_SCALE) == pytest.approx(
        _EXPLOSIVE_PAYLOAD_DETONATION_SCALE,
    )


def test_scale_is_monotonic_but_damped_relative_to_damage_scale() -> None:
    # Plasma Cannon (28.0) hits ~6.8x harder than Pistol (4.1), but its blast
    # should come out well under 6.8x bigger - damped ("scales, but not as
    # much"), not linear.
    weak = _explosive_payload_blast_scale(1.0)  # most guns
    pistol = _explosive_payload_blast_scale(4.1)
    strong = _explosive_payload_blast_scale(28.0)  # Plasma Cannon

    assert weak < pistol < strong
    damage_ratio = 28.0 / 4.1
    blast_ratio = strong / pistol
    assert blast_ratio < damage_ratio


def test_non_positive_damage_scale_disables_the_blast() -> None:
    assert _explosive_payload_blast_scale(0.0) == 0.0
    assert _explosive_payload_blast_scale(-1.0) == 0.0
