from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool, SecondaryStepCtx
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


# --- rocket-type weapons: Explosive Payload now spawns a second, separate ---
# detonation on hit, same as the bullet version above (`_maybe_explosive_
# payload_on_hit` there) instead of the earlier flat crit_mult multiplier -
# "doesn't matter if we get 2 explosions" is exactly the point.


def _fire_rocket_and_step_to_first_hit(
    weapon_id: WeaponId,
    *,
    explosive_payload_timer: float,
    target_pos: Vec2 = Vec2(60.0, 0.0),
    max_steps: int = 300,
    crit_mult: float = 1.0,
):
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.explosive_payload_timer = float(explosive_payload_timer)
    player.aim_heading = 1.5707963267948966  # heading convention: 0=up, +90deg=+x
    creature = _creature(pos=target_pos, hp=1.0e9)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=target_pos),
            dt=0.016,
            state=state,
            creatures=(creature,),
        ),
    )
    if crit_mult != 1.0:
        for entry in state.secondary_projectiles.entries:
            if entry.active and entry.type_id in (
                SecondaryProjectileTypeId.ROCKET,
                SecondaryProjectileTypeId.HOMING_ROCKET,
            ):
                entry.crit_mult = float(crit_mult)
    for _ in range(max_steps):
        was_detonation = any(
            e.active and e.type_id == SecondaryProjectileTypeId.DETONATION
            for e in state.secondary_projectiles.entries
        )
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), runtime_state=state, players=[player]),
        )
        is_detonation_now = any(
            e.active and e.type_id == SecondaryProjectileTypeId.DETONATION
            for e in state.secondary_projectiles.entries
        )
        if is_detonation_now and not was_detonation:
            break  # the rocket just hit and converted this tick - stop right here
    return state


def test_rocket_launcher_gets_a_second_detonation_when_explosive_payload_is_active() -> None:
    from crimson.projectiles.runtime.secondary_pool import _ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE

    active_state = _fire_rocket_and_step_to_first_hit(WeaponId.ROCKET_LAUNCHER, explosive_payload_timer=5.0)
    detonations = [
        e for e in active_state.secondary_projectiles.entries
        if e.active and e.type_id == SecondaryProjectileTypeId.DETONATION
    ]
    # The rocket's own natural detonation, plus a second bonus one from Explosive
    # Payload - both independently ticking, not one bigger/multiplied blast.
    assert len(detonations) == 2
    scales = sorted(float(d.detonation_scale) for d in detonations)
    assert scales[0] == pytest.approx(_ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE)
    assert scales[1] == pytest.approx(1.0)  # RocketRule's own natural detonation_scale


def test_rocket_launcher_gets_only_one_detonation_without_explosive_payload() -> None:
    inactive_state = _fire_rocket_and_step_to_first_hit(WeaponId.ROCKET_LAUNCHER, explosive_payload_timer=0.0)
    detonations = [
        e for e in inactive_state.secondary_projectiles.entries
        if e.active and e.type_id == SecondaryProjectileTypeId.DETONATION
    ]
    assert len(detonations) == 1


def test_rocket_bonus_detonation_inherits_the_rockets_crit_mult() -> None:
    # Regression: the rocket-path bonus detonation (secondary_pool.py's
    # _maybe_rocket_explosive_payload_on_hit) used to always stamp
    # crit_mult=1.0, same class of bug as the bullet path above.
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT
    from crimson.projectiles.runtime.secondary_pool import _ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE

    active_state = _fire_rocket_and_step_to_first_hit(
        WeaponId.ROCKET_LAUNCHER, explosive_payload_timer=5.0, crit_mult=MOMENTUM_DAMAGE_MULT,
    )
    bonus_detonations = [
        e for e in active_state.secondary_projectiles.entries
        if e.active and e.type_id == SecondaryProjectileTypeId.DETONATION
        and float(e.detonation_scale) == pytest.approx(_ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE)
    ]
    assert bonus_detonations
    assert bonus_detonations[0].crit_mult == pytest.approx(MOMENTUM_DAMAGE_MULT)


def test_mini_rocket_swarmers_flags_exactly_one_rocket_per_volley() -> None:
    # Not native: MRS is treated as a shotgun for this bonus - one volley is
    # "one shot", so only one of its rockets (random) is allowed to proc the
    # bonus detonation, not all five.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=state)
    player.explosive_payload_timer = 5.0
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state),
    )
    rockets = [
        e for e in state.secondary_projectiles.entries
        if e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET
    ]
    assert len(rockets) == player.weapon.clip_size
    eligible = [e for e in rockets if e.explosive_payload_eligible]
    assert len(eligible) == 1


def test_mini_rocket_swarmers_volley_only_procs_one_bonus_detonation_total() -> None:
    active_state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=active_state)
    player.explosive_payload_timer = 5.0
    player.aim_heading = 1.5707963267948966
    target_pos = Vec2(60.0, 0.0)
    creature = _creature(pos=target_pos, hp=1.0e9)

    bonus_detonation_spawns = 0
    original_spawn = active_state.secondary_projectiles.spawn_from_spec

    def _counting_spawn(spec):
        nonlocal bonus_detonation_spawns
        if spec.type_id == SecondaryProjectileTypeId.DETONATION:
            bonus_detonation_spawns += 1  # only the bonus goes through spawn_from_spec -
        return original_spawn(spec)       # a rocket's own natural detonation is an in-place conversion

    active_state.secondary_projectiles.spawn_from_spec = _counting_spawn
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=target_pos),
            dt=0.016,
            state=active_state,
            creatures=(creature,),
        ),
    )
    for _ in range(300):
        active_state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), runtime_state=active_state, players=[player]),
        )
        if not any(e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET for e in active_state.secondary_projectiles.entries):
            break  # every rocket in the volley has hit or expired

    assert bonus_detonation_spawns == 1


def _step_and_hit(
    *, is_rocket: bool, type_id: ProjectileTemplateId = ProjectileTemplateId.PISTOL, crit_mult: float = 1.0,
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
    pool.entries[idx].crit_mult = float(crit_mult)
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


def test_detonation_inherits_the_hitting_bullets_crit_mult() -> None:
    # Regression: the bonus detonation used to always stamp crit_mult=1.0,
    # ignoring whatever multiplier the bullet that triggered it actually hit
    # with - a real crit or a Domino Effect freebie's discount.
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT

    pool, state, idx = _step_and_hit(is_rocket=True, crit_mult=MOMENTUM_DAMAGE_MULT)
    detonations = [s for s in state.secondary_projectiles.entries if s.active]
    assert len(detonations) == 1
    assert detonations[0].crit_mult == pytest.approx(MOMENTUM_DAMAGE_MULT)


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


def test_the_common_1x_damage_scale_stays_close_to_the_anchor() -> None:
    # The vast majority of weapons (Assault Rifle, SMG, Gauss Gun, Mean
    # Minigun, ...) sit at damage_scale 1.0 - they shouldn't be docked much of
    # the Pistol's blast just for not being the anchor weapon.
    scale = _explosive_payload_blast_scale(1.0)
    assert scale > 0.7 * _EXPLOSIVE_PAYLOAD_DETONATION_SCALE
