from __future__ import annotations

import math

import pytest

from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime
from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.math_parity import NATIVE_HALF_PI, native_fire_muzzle_pos
from crimson.owner_ref import OwnerRef
from crimson.progression import refresh_player_stats
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime.availability import (
    _TENET_GUN_RARE_DROP_CHANCE,
    _TENET_GUN_RARE_RNG,
    prepare_weapon_availability,
    weapon_pick_random_available,
)
from crimson.weapon_runtime.crit import crit_chance_for_weapon
from crimson.weapon_runtime.spawn import owner_ref_for_player, projectile_spawn
from crimson.weapon_runtime.tags import weapon_tags
from crimson.weapon_runtime.tenet_gun_spawn import tenet_reverse_spawn_params
from crimson.weapons import WEAPON_BY_ID, WeaponId
from grim.geom import Vec2
from tests.support.factories import make_projectile_update_options


def _player_with_tenet_gun(state: GameplayState, *, pos: Vec2 = Vec2(0.0, 0.0)) -> PlayerState:
    player = PlayerState(index=0, pos=pos)
    weapon_assign_player(player, WeaponId.TENET_GUN, state=state)
    refresh_player_stats([player])
    return player


def _fire(state: GameplayState, player: PlayerState, *, aim: Vec2, creatures=()) -> None:
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=aim),
            dt=0.016,
            state=state,
            creatures=creatures,
        ),
    )


# --- Tenet Gun is a pure Pistol clone -----------------------------------


def test_stats_are_an_exact_pistol_clone() -> None:
    pistol = WEAPON_BY_ID[WeaponId.PISTOL]
    tenet = WEAPON_BY_ID[WeaponId.TENET_GUN]
    for field in (
        "ammo_class",
        "clip_size",
        "shot_cooldown",
        "reload_time",
        "spread_heat_inc",
        "fire_sound",
        "reload_sound",
        "flags",
        "travel_budget",
        "damage_scale",
        "pellet_count",
    ):
        assert getattr(tenet, field) == getattr(pistol, field), field


def test_crit_chance_and_archetype_match_pistol() -> None:
    assert crit_chance_for_weapon(WeaponId.TENET_GUN) == crit_chance_for_weapon(WeaponId.PISTOL)
    assert weapon_tags(WeaponId.TENET_GUN).archetype == weapon_tags(WeaponId.PISTOL).archetype


# --- The spawn/direction flip itself -------------------------------------


def test_tenet_reverse_spawn_params_flips_position_and_direction() -> None:
    muzzle = Vec2(10.0, -5.0)
    aim = Vec2(300.0, 200.0)
    pos, angle = tenet_reverse_spawn_params(origin=muzzle, muzzle=muzzle, aim=aim, angle=1.2)

    assert pos == aim
    assert angle == pytest.approx(1.2 + math.pi)


def test_tenet_reverse_spawn_params_preserves_lateral_offset() -> None:
    # Plasma Overload's twin bolts are offset sideways from the muzzle - that
    # same offset should carry over to the aim point, not collapse to it.
    muzzle = Vec2(0.0, 0.0)
    origin = Vec2(5.0, 0.0)  # muzzle + 5 units lateral offset
    aim = Vec2(300.0, 0.0)
    pos, _ = tenet_reverse_spawn_params(origin=origin, muzzle=muzzle, aim=aim, angle=0.0)

    assert pos == Vec2(305.0, 0.0)


def test_firing_spawns_a_real_projectile_at_the_aim_point_flying_backward() -> None:
    state = GameplayState()
    player = _player_with_tenet_gun(state)

    _fire(state, player, aim=Vec2(200.0, 0.0))

    shots = [p for p in state.projectiles.entries if p.active]
    assert len(shots) == 1
    shot = shots[0]
    assert shot.type_id == ProjectileTemplateId.PISTOL
    assert shot.tenet_reverse is True
    assert shot.pos == pytest.approx(Vec2(200.0, 0.0))


def test_a_plain_pistol_shot_spawns_normally_at_the_muzzle() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    refresh_player_stats([player])

    _fire(state, player, aim=Vec2(200.0, 0.0))

    shots = [p for p in state.projectiles.entries if p.active]
    assert len(shots) == 1
    assert shots[0].tenet_reverse is False
    assert shots[0].pos == pytest.approx(native_fire_muzzle_pos(player.pos, player.aim_heading))


def test_fire_bullets_and_plasma_overload_also_spawn_reversed() -> None:
    state = GameplayState()
    player = _player_with_tenet_gun(state)
    player.fire_bullets_timer = 5.0
    _fire(state, player, aim=Vec2(200.0, 0.0))
    fire_bullets_shot = next(p for p in state.projectiles.entries if p.active)
    assert fire_bullets_shot.type_id == ProjectileTemplateId.FIRE_BULLETS
    assert fire_bullets_shot.tenet_reverse is True

    state2 = GameplayState()
    player2 = _player_with_tenet_gun(state2)
    player2.plasma_overload_timer = 5.0
    _fire(state2, player2, aim=Vec2(200.0, 0.0))
    bolts = [p for p in state2.projectiles.entries if p.active]
    assert len(bolts) == 2
    assert all(b.type_id == ProjectileTemplateId.PLASMA_RIFLE for b in bolts)
    assert all(b.tenet_reverse for b in bolts)


# --- It's a completely normal projectile otherwise: real damage, real ---
# --- pierce, real collision - no special-cased Tenet Gun logic at all ---


def test_a_creature_between_the_aim_point_and_the_player_is_damaged_normally() -> None:
    pool = ProjectilePool(size=8)
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), aim_heading=0.0)
    # A plain forward Pistol shot at this heading travels toward +x; reversed,
    # it spawns out at the aim point and flies back toward -x.
    pos, angle = tenet_reverse_spawn_params(
        origin=Vec2(0.0, 0.0),
        muzzle=Vec2(0.0, 0.0),
        aim=Vec2(200.0, 0.0),
        angle=NATIVE_HALF_PI,
    )
    idx = pool.spawn(
        pos=pos,
        angle=angle,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=55.0,
    )
    pool.entries[idx].tenet_reverse = True
    creature = CreatureState(active=True, hp=100000.0, pos=Vec2(100.0, 0.0), size=30.0)
    state = GameplayState()
    runtime = DirectCreatureDamageRuntime(creatures=[creature])

    for _ in range(4):
        pool.step(
            PrimaryStepCtx(
                dt=0.06,
                creatures=[creature],
                options=make_projectile_update_options(
                    world_size=4096.0,
                    runtime_state=state,
                    players=[player],
                    creature_damage_runtime=runtime,
                ),
            ),
        )

    assert creature.hp < 100000.0  # normal damage, same collision code as any other bullet


def test_fire_bullets_still_pierces_through_more_than_one_enemy() -> None:
    # Fire Bullets' real pierce/damage-pool mechanic (projectile_pool.py) is
    # completely unmodified now, so it should just work, the same as it does
    # for any other weapon.
    pool = ProjectilePool(size=8)
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), aim_heading=0.0)
    pos, angle = tenet_reverse_spawn_params(
        origin=Vec2(0.0, 0.0),
        muzzle=Vec2(0.0, 0.0),
        aim=Vec2(80.0, 0.0),
        angle=NATIVE_HALF_PI,
    )
    idx = pool.spawn(
        pos=pos,
        angle=angle,
        type_id=ProjectileTemplateId.FIRE_BULLETS,
        owner=OwnerRef.from_local_player(0),
        travel_budget=60.0,
    )
    pool.entries[idx].tenet_reverse = True
    near = CreatureState(active=True, hp=300.0, pos=Vec2(60.0, 0.0), size=10.0)
    far = CreatureState(active=True, hp=300.0, pos=Vec2(20.0, 0.0), size=10.0)
    state = GameplayState()
    runtime = DirectCreatureDamageRuntime(creatures=[near, far])

    for _ in range(6):
        pool.step(
            PrimaryStepCtx(
                dt=0.06,
                creatures=[near, far],
                options=make_projectile_update_options(
                    world_size=4096.0,
                    runtime_state=state,
                    players=[player],
                    creature_damage_runtime=runtime,
                ),
            ),
        )

    assert near.hp < 300.0
    assert far.hp < 300.0  # pierced through to the second enemy too


# --- It stops when it arrives back at its owner --------------------------


def test_a_reversed_bolt_stops_once_it_reaches_its_owner() -> None:
    pool = ProjectilePool(size=8)
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    idx = pool.spawn(
        pos=Vec2(5.0, 0.0),  # already essentially back at the player
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=55.0,
    )
    pool.entries[idx].tenet_reverse = True
    state = GameplayState()

    pool.step(
        PrimaryStepCtx(
            dt=0.016,
            creatures=[],
            options=make_projectile_update_options(world_size=4096.0, runtime_state=state, players=[player]),
        ),
    )

    assert not pool.entries[idx].active


def test_a_reversed_bolt_far_from_its_owner_keeps_travelling() -> None:
    pool = ProjectilePool(size=8)
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    idx = pool.spawn(
        pos=Vec2(500.0, 0.0),
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=55.0,
    )
    pool.entries[idx].tenet_reverse = True
    state = GameplayState()

    pool.step(
        PrimaryStepCtx(
            dt=0.016,
            creatures=[],
            options=make_projectile_update_options(world_size=4096.0, runtime_state=state, players=[player]),
        ),
    )

    assert pool.entries[idx].active


def test_a_normal_bullet_is_unaffected_by_the_stop_near_owner_check() -> None:
    pool = ProjectilePool(size=8)
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    idx = pool.spawn(
        pos=Vec2(5.0, 0.0),  # would trigger the stop-check if tagged
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
        travel_budget=55.0,
    )
    state = GameplayState()

    pool.step(
        PrimaryStepCtx(
            dt=0.016,
            creatures=[],
            options=make_projectile_update_options(world_size=4096.0, runtime_state=state, players=[player]),
        ),
    )

    assert pool.entries[idx].active


# --- Bonus/perk-triggered spawns (Shock Chain's opening bolt, Fireblast, --
# --- Ion Overload, Angry Reloader, Fire Cough, Hot Tempered, Man Bomb, ----
# --- Nuke, ...) all get the same reverse-spawn treatment as the player's --
# --- own trigger-pull, since they all originate from the player too - ----
# --- every one of them routes through `projectile_spawn`/               --
# --- `spawn_projectile_ring` (weapon_runtime/spawn.py), which is where --
# --- the check actually lives. Derived spawns that re-own to something --
# --- other than the triggering player - Shock Chain's own relay hits,  --
# --- Fork Shot children - go through the pool directly and bypass this --
# --- chokepoint entirely, so they stay unaffected by construction. -----


def test_bonus_triggered_spawns_are_also_reversed_for_a_tenet_gun_player() -> None:
    state = GameplayState()
    player = _player_with_tenet_gun(state)
    player.aim = Vec2(300.0, 0.0)

    idx = projectile_spawn(
        state,
        players=[player],
        pos=Vec2(0.0, 0.0),  # Shock Chain/Fireblast/etc. spawn at the player
        angle=0.0,
        type_id=ProjectileTemplateId.ION_RIFLE,  # Shock Chain's own bolt type
        owner=owner_ref_for_player(player.index),
        owner_player_index=player.index,
    )

    shot = state.projectiles.entries[idx]
    assert shot.tenet_reverse is True
    assert shot.pos == pytest.approx(player.aim)
    assert shot.angle == pytest.approx(math.pi)


def test_bonus_triggered_spawns_are_unaffected_for_a_non_tenet_gun_player() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.SHOTGUN, state=state)
    refresh_player_stats([player])

    idx = projectile_spawn(
        state,
        players=[player],
        pos=Vec2(0.0, 0.0),
        angle=0.0,
        type_id=ProjectileTemplateId.ION_RIFLE,
        owner=owner_ref_for_player(player.index),
        owner_player_index=player.index,
    )

    shot = state.projectiles.entries[idx]
    assert shot.tenet_reverse is False
    assert shot.pos == pytest.approx(Vec2(0.0, 0.0))


def test_ion_overload_bolt_is_reversed_too() -> None:
    from crimson.bonuses.ion_overload import fire_ion_overload_bolt

    state = GameplayState()
    player = _player_with_tenet_gun(state)
    player.aim = Vec2(300.0, 0.0)
    player.ion_overload.charge_seconds = 5.0

    fire_ion_overload_bolt(state, player)

    shots = [p for p in state.projectiles.entries if p.active]
    assert len(shots) == 1
    assert shots[0].tenet_reverse is True
    assert shots[0].pos == pytest.approx(player.aim)


# --- Meme-tier rarity -----------------------------------------------------


def test_tenet_gun_is_not_reachable_through_the_normal_weapon_id_roll() -> None:
    # Its own id (54) sits outside the 1-33 range native
    # weapon_pick_random_available rolls over - it can only come from the
    # separate rare-roll below.
    from crimson.weapon_runtime.availability import WEAPON_DROP_ID_COUNT

    assert int(WeaponId.TENET_GUN) > WEAPON_DROP_ID_COUNT


def test_the_rare_roll_can_hit() -> None:
    # Rolled on a private RNG (not state.rng), same reasoning as crit.py's
    # own roll - purely cosmetic build variance, must not perturb replay
    # determinism or the RNG-trace tests that script the sim stream's exact
    # draw sequence (this used to draw from state.rng and broke several).
    state = GameplayState()
    prepare_weapon_availability(state)

    original = _TENET_GUN_RARE_RNG.random
    _TENET_GUN_RARE_RNG.random = lambda: 0.0  # type: ignore[method-assign]
    try:
        assert weapon_pick_random_available(state) == WeaponId.TENET_GUN
    finally:
        _TENET_GUN_RARE_RNG.random = original  # type: ignore[method-assign]


def test_the_rare_roll_is_actually_rare() -> None:
    state = GameplayState()
    prepare_weapon_availability(state)

    original = _TENET_GUN_RARE_RNG.random
    _TENET_GUN_RARE_RNG.random = lambda: 0.5  # type: ignore[method-assign]  # well above the threshold
    try:
        assert weapon_pick_random_available(state) != WeaponId.TENET_GUN
    finally:
        _TENET_GUN_RARE_RNG.random = original  # type: ignore[method-assign]
    assert _TENET_GUN_RARE_DROP_CHANCE <= 0.01  # meme-tier, not a coin flip
