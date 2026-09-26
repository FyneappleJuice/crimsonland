from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.perks.ids import PerkId
from crimson.projectiles.runtime import PrimaryStepCtx
from crimson.projectiles.runtime.projectile_pool import SEEKER_ROUNDS_HIT_THRESHOLD
from crimson.projectiles.runtime.secondary_pool import SecondaryStepCtx
from crimson.projectiles.types import SecondaryProjectileTypeId
from crimson.run_mods.ids import RunModId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WEAPON_BY_ID, WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state, make_projectile_update_options


def _fresh_shot(player: PlayerState) -> None:
    player.weapon.shot_cooldown = 0.0
    player.weapon.reload_active = False
    player.weapon.reload_timer = 0.0
    player.weapon.ammo = float(WEAPON_BY_ID[WeaponId(player.weapon.weapon_id)].clip_size)


def _player(weapon_id: WeaponId = WeaponId.PISTOL) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.perk_counts[int(PerkId.SEEKER_ROUNDS)] = 1
    player.weapon.weapon_id = weapon_id
    return player


def _fire_and_resolve(state: GameplayState, player: PlayerState, creature) -> None:
    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(50.0, 0.0), fire_down=True), dt=0.016, state=state),
    )
    for _ in range(10):
        state.projectiles.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=[creature],
                options=make_projectile_update_options(runtime_state=state, players=[player]),
            ),
        )


def _active_rockets(state: GameplayState) -> list:
    return [
        entry
        for entry in state.secondary_projectiles.entries
        if entry.active and entry.type_id == SecondaryProjectileTypeId.HOMING_ROCKET
    ]


def test_seeker_rounds_fires_a_rocket_exactly_at_the_hit_threshold() -> None:
    state = GameplayState()
    player = _player()

    for shot in range(SEEKER_ROUNDS_HIT_THRESHOLD):
        creature = make_creature_state(pos=Vec2(50.0, 0.0), size=200.0, hp=1_000_000.0)
        _fire_and_resolve(state, player, creature)
        if shot < SEEKER_ROUNDS_HIT_THRESHOLD - 1:
            assert _active_rockets(state) == []
            assert player.seeker_rounds_hit_counter == shot + 1

    assert len(_active_rockets(state)) == 1
    assert player.seeker_rounds_hit_counter == 0


def test_seeker_rounds_misses_do_not_advance_the_counter() -> None:
    state = GameplayState()
    player = _player()
    # Nothing within range to hit - every shot whiffs.
    far_away_creature = make_creature_state(pos=Vec2(5000.0, 5000.0), size=10.0, hp=1_000_000.0)

    for _ in range(SEEKER_ROUNDS_HIT_THRESHOLD * 2):
        _fire_and_resolve(state, player, far_away_creature)

    assert player.seeker_rounds_hit_counter == 0
    assert _active_rockets(state) == []


def test_seeker_rounds_counter_survives_ammo_running_out_and_reloading() -> None:
    state = GameplayState()
    player = _player()

    for _ in range(SEEKER_ROUNDS_HIT_THRESHOLD - 1):
        creature = make_creature_state(pos=Vec2(50.0, 0.0), size=200.0, hp=1_000_000.0)
        _fire_and_resolve(state, player, creature)
    assert player.seeker_rounds_hit_counter == SEEKER_ROUNDS_HIT_THRESHOLD - 1

    # Simulate ammo hitting empty and a reload completing - nothing about the
    # counter is tied to weapon/ammo state, so it should be untouched.
    player.weapon.ammo = 0.0
    player.weapon.reload_active = True
    player.weapon.reload_timer = player.weapon.reload_timer_max
    player.weapon.reload_active = False
    player.weapon.ammo = float(WEAPON_BY_ID[WeaponId(player.weapon.weapon_id)].clip_size)

    assert player.seeker_rounds_hit_counter == SEEKER_ROUNDS_HIT_THRESHOLD - 1

    creature = make_creature_state(pos=Vec2(50.0, 0.0), size=200.0, hp=1_000_000.0)
    _fire_and_resolve(state, player, creature)
    assert len(_active_rockets(state)) == 1
    assert player.seeker_rounds_hit_counter == 0


def test_seeker_rounds_counts_a_shotgun_blast_as_one_shot_not_one_per_pellet() -> None:
    # Shotgun fires 12 pellets in a single trigger-pull - a big, close target
    # should catch several of them, but that must only advance the counter once.
    state = GameplayState()
    player = _player(WeaponId.SHOTGUN)
    creature = make_creature_state(pos=Vec2(50.0, 0.0), size=500.0, hp=1_000_000.0)

    _fire_and_resolve(state, player, creature)

    assert player.seeker_rounds_hit_counter == 1


def test_seeker_rounds_counts_a_piercing_shot_through_multiple_enemies_as_one() -> None:
    state = GameplayState()
    player = _player(WeaponId.PISTOL)
    state.bonuses.weapon_power_up = 999.0  # kinetic Weapon Power Up grants pierce
    near = make_creature_state(pos=Vec2(40.0, 0.0), size=100.0, hp=1_000_000.0)
    far = make_creature_state(pos=Vec2(60.0, 0.0), size=100.0, hp=1_000_000.0)

    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(50.0, 0.0), fire_down=True), dt=0.016, state=state),
    )
    for _ in range(15):
        state.projectiles.step(
            PrimaryStepCtx(
                dt=0.1,
                creatures=[near, far],
                options=make_projectile_update_options(runtime_state=state, players=[player]),
            ),
        )

    assert player.seeker_rounds_hit_counter <= 1


def test_seeker_rounds_rocket_scales_with_perk_efficacy() -> None:
    state = GameplayState()
    player = _player()
    player.run_mod_counts[int(RunModId.PERK_EFFICACY)] = 1

    for _ in range(SEEKER_ROUNDS_HIT_THRESHOLD):
        creature = make_creature_state(pos=Vec2(50.0, 0.0), size=200.0, hp=1_000_000.0)
        _fire_and_resolve(state, player, creature)

    rockets = _active_rockets(state)
    assert len(rockets) == 1
    assert rockets[0].crit_mult == pytest.approx(1.05)


def test_seeker_rounds_rocket_compounds_with_the_hitting_bullets_crit_mult() -> None:
    # Regression: the bonus rocket used to stamp perk_efficacy alone, ignoring
    # whatever multiplier the triggering bullet itself hit with - a real crit
    # or a Domino Effect freebie's discount should compound with it, not be
    # overwritten by it.
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT

    state = GameplayState()
    player = _player()
    player.run_mod_counts[int(RunModId.PERK_EFFICACY)] = 1

    for shot in range(SEEKER_ROUNDS_HIT_THRESHOLD):
        creature = make_creature_state(pos=Vec2(50.0, 0.0), size=200.0, hp=1_000_000.0)
        _fresh_shot(player)
        fire_weapon(
            WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(50.0, 0.0), fire_down=True), dt=0.016, state=state),
        )
        if shot == SEEKER_ROUNDS_HIT_THRESHOLD - 1:
            for entry in state.projectiles.entries:
                if entry.active:
                    entry.crit_mult = MOMENTUM_DAMAGE_MULT
        for _ in range(10):
            state.projectiles.step(
                PrimaryStepCtx(
                    dt=0.1,
                    creatures=[creature],
                    options=make_projectile_update_options(runtime_state=state, players=[player]),
                ),
            )

    rockets = _active_rockets(state)
    assert len(rockets) == 1
    assert rockets[0].crit_mult == pytest.approx(1.05 * MOMENTUM_DAMAGE_MULT)


# --- rocket-type weapons: Fire and Forget had no effect at all before -------
# (they spawn straight into the secondary pool, which the hit-resolution
# block above never touches). Handled in secondary_pool.py's
# _maybe_rocket_seeker_rounds_on_hit now, same dedup-by-shot_seq mechanism.


def _fire_rocket_and_resolve(state: GameplayState, player: PlayerState, creature) -> None:
    player.aim_heading = 1.5707963267948966  # heading convention: 0=up, +90deg=+x
    weapon_assign_player(player, WeaponId(player.weapon.weapon_id), state=state)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(aim=Vec2(60.0, 0.0), fire_down=True),
            dt=0.016,
            state=state,
            creatures=(creature,),
        ),
    )
    player.weapon.shot_cooldown = 0.0
    for _ in range(120):
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), runtime_state=state, players=[player]),
        )


def test_seeker_rounds_fires_a_rocket_when_a_rocket_weapon_lands_the_hits() -> None:
    # Rocket Minigun's own rockets are type ROCKET_MINIGUN, not HOMING_ROCKET,
    # so counting HOMING_ROCKET spawns unambiguously counts only the bonus -
    # avoids racing against how fast the bonus rocket itself might resolve.
    state = GameplayState()
    player = _player(WeaponId.ROCKET_MINIGUN)
    creature = make_creature_state(pos=Vec2(60.0, 0.0), size=200.0, hp=1_000_000.0)

    bonus_rocket_spawns = 0
    original_spawn = state.secondary_projectiles.spawn_from_spec

    def _counting_spawn(spec):
        nonlocal bonus_rocket_spawns
        if spec.type_id == SecondaryProjectileTypeId.HOMING_ROCKET:
            bonus_rocket_spawns += 1
        return original_spawn(spec)

    state.secondary_projectiles.spawn_from_spec = _counting_spawn

    for shot in range(SEEKER_ROUNDS_HIT_THRESHOLD):
        _fire_rocket_and_resolve(state, player, creature)
        if shot < SEEKER_ROUNDS_HIT_THRESHOLD - 1:
            assert player.seeker_rounds_hit_counter == shot + 1

    assert player.seeker_rounds_hit_counter == 0
    assert bonus_rocket_spawns == 1


def test_seeker_rounds_rocket_path_compounds_with_the_hitting_rockets_crit_mult() -> None:
    # Regression: the rocket-path bonus rocket (secondary_pool.py's
    # _maybe_rocket_seeker_rounds_on_hit) used to stamp perk_efficacy alone,
    # ignoring whatever multiplier the triggering rocket itself hit with -
    # same class of bug as the bullet path. Captured at spawn time via
    # spawn_from_spec, since the bonus rocket has time to hit its own target
    # and convert to a detonation before the stepping loop below ends.
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT

    state = GameplayState()
    player = _player(WeaponId.ROCKET_MINIGUN)
    player.run_mod_counts[int(RunModId.PERK_EFFICACY)] = 1
    creature = make_creature_state(pos=Vec2(60.0, 0.0), size=200.0, hp=1_000_000.0)

    for shot in range(SEEKER_ROUNDS_HIT_THRESHOLD):
        if shot < SEEKER_ROUNDS_HIT_THRESHOLD - 1:
            _fire_rocket_and_resolve(state, player, creature)
            continue
        player.aim_heading = 1.5707963267948966
        weapon_assign_player(player, WeaponId(player.weapon.weapon_id), state=state)
        fire_weapon(
            WeaponFireCtx(
                player=player,
                input_state=PlayerInput(aim=Vec2(60.0, 0.0), fire_down=True),
                dt=0.016,
                state=state,
                creatures=(creature,),
            ),
        )
        for entry in state.secondary_projectiles.entries:
            if entry.active and entry.type_id == SecondaryProjectileTypeId.ROCKET_MINIGUN:
                entry.crit_mult = MOMENTUM_DAMAGE_MULT
        player.weapon.shot_cooldown = 0.0
        # crit_mult is stamped onto the bonus rocket synchronously, within the
        # same step() call that spawns it - poll right after each step and
        # capture it before the rocket has a chance to hit its own target and
        # convert to a detonation.
        bonus_crit_mult = None
        for _ in range(120):
            state.secondary_projectiles.step(
                SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), runtime_state=state, players=[player]),
            )
            if bonus_crit_mult is None:
                for entry in state.secondary_projectiles.entries:
                    if entry.active and entry.type_id == SecondaryProjectileTypeId.HOMING_ROCKET:
                        bonus_crit_mult = float(entry.crit_mult)
                        break

    assert bonus_crit_mult == pytest.approx(1.05 * MOMENTUM_DAMAGE_MULT)


def test_seeker_rounds_counts_a_mini_rocket_swarmers_volley_as_one_shot() -> None:
    # Mini-Rocket Swarmers dumps its whole clip (multiple rockets) in a single
    # trigger pull - like the bullet Shotgun test above, that must only
    # advance the counter once, not once per rocket that connects.
    state = GameplayState()
    player = _player(WeaponId.MINI_ROCKET_SWARMERS)
    creature = make_creature_state(pos=Vec2(60.0, 0.0), size=500.0, hp=1_000_000.0)

    _fire_rocket_and_resolve(state, player, creature)

    assert player.seeker_rounds_hit_counter == 1
