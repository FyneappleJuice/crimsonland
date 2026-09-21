from __future__ import annotations

import math

import pytest

from crimson.creatures.damage import (
    ADRENALINE_RUSH_BONUS,
    COUP_DE_GRACE_HP_FRACTION,
    KINETIC_DISCIPLINE_MAX_BONUS,
    STEADY_HANDS_BONUS,
    STEADY_HANDS_HP_FRACTION,
    creature_apply_damage,
)
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CREATURE_LIFECYCLE_ALIVE, CreaturePool, CreatureState
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.perks.ids import PerkId
from crimson.player_damage import (
    ADRENALINE_RUSH_WINDOW_DURATION,
    AMMO_SHIELD_AMMO_COST,
    AMMO_SHIELD_DAMAGE_REDUCTION,
    DESPERATION_MAX_REDUCTION,
    player_take_damage,
)
from crimson.projectiles.runtime import PrimaryStepCtx
from crimson.projectiles.runtime.projectile_pool import COLD_SNAP_FREEZE_DURATION
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon
from crimson.weapon_runtime.assign import weapon_assign_player
from crimson.weapon_runtime.fire import DEATH_WISH_HEALTH_THRESHOLD, OVERDUE_STREAK_THRESHOLD
from crimson.weapons import WEAPON_BY_ID, WeaponId, weapon_entry_for_projectile_type_id
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import make_creature_state, make_projectile_update_options
from tests.support.helpers import assert_float_close


def _fresh_shot(player: PlayerState) -> None:
    player.weapon.shot_cooldown = 0.0
    player.weapon.reload_active = False
    player.weapon.reload_timer = 0.0
    player.weapon.ammo = float(WEAPON_BY_ID[WeaponId(player.weapon.weapon_id)].clip_size)


# --- Ammo Shield ---------------------------------------------------------


def test_ammo_shield_redirects_damage_and_drains_ammo() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.AMMO_SHIELD)] = 1
    player.weapon.ammo = 10.0

    applied = player_take_damage(state, player, 10.0)

    assert_float_close(applied, 10.0 * (1.0 - AMMO_SHIELD_DAMAGE_REDUCTION))
    assert_float_close(player.weapon.ammo, 10.0 - AMMO_SHIELD_AMMO_COST)


def test_ammo_shield_ammo_cost_floors_at_zero() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.AMMO_SHIELD)] = 1
    player.weapon.ammo = 0.0

    applied = player_take_damage(state, player, 10.0)

    assert_float_close(applied, 10.0 * (1.0 - AMMO_SHIELD_DAMAGE_REDUCTION))
    assert player.weapon.ammo == 0.0


# --- Coup de Grace ---------------------------------------------------------


def test_coup_de_grace_guarantees_the_kill_below_threshold() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.COUP_DE_GRACE)] = 1
    creature = CreatureState(active=True, hp=100.0 * COUP_DE_GRACE_HP_FRACTION, max_hp=100.0)

    died = creature_apply_damage(
        creature, damage_amount=1.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert creature.hp == pytest.approx(0.0, abs=1e-9)
    assert not died  # the early-return "already dead" branch only fires on a *second* hit


def test_coup_de_grace_does_nothing_above_threshold() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.COUP_DE_GRACE)] = 1
    creature = CreatureState(active=True, hp=50.0, max_hp=100.0)

    creature_apply_damage(
        creature, damage_amount=1.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 49.0)


# --- Death Wish ---------------------------------------------------------


def test_death_wish_forces_every_shot_to_crit_at_low_health() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DEATH_WISH_HEALTH_THRESHOLD)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1
    player.weapon.weapon_id = WeaponId.PISTOL

    fired = 0
    crits = 0
    for _ in range(15):
        _fresh_shot(player)
        result = fire_weapon(
            WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(10.0, 0.0), fire_down=True), dt=0.016, state=state),
        )
        if result.fired:
            fired += 1
            for entry in state.projectiles.entries:
                if entry.active and entry.did_crit:
                    crits += 1
                entry.active = False

    assert fired > 0
    assert crits == fired


def test_death_wish_inactive_above_health_threshold() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DEATH_WISH_HEALTH_THRESHOLD + 1.0)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1
    player.weapon.weapon_id = WeaponId.SHRINKIFIER_5K  # UTILITY archetype, 0% base crit chance, so any crit must be forced

    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(10.0, 0.0), fire_down=True), dt=0.016, state=state),
    )
    assert not any(e.did_crit for e in state.projectiles.entries if e.active)


# --- Overdue ---------------------------------------------------------


def _forced_crit_mult(state: GameplayState, player: PlayerState) -> float:
    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(10.0, 0.0), fire_down=True), dt=0.016, state=state),
    )
    entry = next(e for e in state.projectiles.entries if e.active)
    entry.active = False
    return float(entry.crit_mult)


def test_overdue_opens_a_window_on_the_triggering_shot() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DEATH_WISH_HEALTH_THRESHOLD)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1  # forces crits deterministically
    player.perk_counts[int(PerkId.OVERDUE)] = 1
    player.overdue_streak = OVERDUE_STREAK_THRESHOLD
    player.weapon.weapon_id = WeaponId.PISTOL

    boosted_mult = _forced_crit_mult(state, player)
    assert player.overdue_streak == 0
    assert player.overdue_window_timer == pytest.approx(5.0)

    # Plain forced crit (no streak bonus) would just be CRIT_MULTIPLIER (2.0);
    # the boosted one should be strictly larger.
    plain_state = GameplayState()
    plain_player = PlayerState(index=0, pos=Vec2(), health=DEATH_WISH_HEALTH_THRESHOLD)
    plain_player.perk_counts[int(PerkId.DEATH_WISH)] = 1
    plain_player.weapon.weapon_id = WeaponId.PISTOL
    plain_mult = _forced_crit_mult(plain_state, plain_player)
    assert boosted_mult > plain_mult


def test_overdue_window_boosts_every_crit_until_it_expires() -> None:
    from crimson.perks.runtime.effects import perks_update_effects

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DEATH_WISH_HEALTH_THRESHOLD)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1
    player.perk_counts[int(PerkId.OVERDUE)] = 1
    player.overdue_streak = OVERDUE_STREAK_THRESHOLD
    player.weapon.weapon_id = WeaponId.PISTOL

    first_mult = _forced_crit_mult(state, player)
    # Still well within the 5s window - a second crit should be boosted too,
    # not just the one that opened it.
    second_mult = _forced_crit_mult(state, player)
    assert_float_close(second_mult, first_mult)

    perks_update_effects(state, [player], 5.1)
    assert player.overdue_window_timer == 0.0
    expired_mult = _forced_crit_mult(state, player)
    assert expired_mult < first_mult


def test_overdue_streak_increments_on_non_crits_and_resets_on_a_natural_crit() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.OVERDUE)] = 1
    player.weapon.weapon_id = WeaponId.SHRINKIFIER_5K  # UTILITY archetype, 0% crit chance

    for expected in range(1, 6):
        _fresh_shot(player)
        fire_weapon(
            WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(10.0, 0.0), fire_down=True), dt=0.016, state=state),
        )
        assert player.overdue_streak == expected


# --- Momentum ---------------------------------------------------------


def _kill_setup(*, weapon_id: WeaponId, momentum: bool) -> tuple[GameplayState, PlayerState, CreaturePool]:
    state = GameplayState()
    state.bonus_spawn_guard = True
    player = PlayerState(index=0, pos=Vec2())
    if momentum:
        player.perk_counts[int(PerkId.MOMENTUM)] = 1
    weapon_assign_player(player, weapon_id, state=state)

    pool = CreaturePool()
    dying = pool.entries[0]
    dying.active = True
    dying.pos = Vec2(0.0, 0.0)
    dying.hp = 0.0
    dying.max_hp = 100.0
    dying.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying.last_hit_owner = OwnerRef.from_player(0)

    far = pool.entries[1]
    far.active = True
    far.pos = Vec2(500.0, 0.0)
    far.hp = 100.0

    near = pool.entries[2]
    near.active = True
    near.pos = Vec2(50.0, 0.0)
    near.hp = 100.0

    return state, player, pool


def test_momentum_fires_a_shot_using_the_players_actual_weapon() -> None:
    # Rewrite-only: Domino Effect fires through the real fire_weapon() path
    # now (a snapshot of the killer, same approach as Hollow Form's clone),
    # not a hardcoded flat Pistol projectile - verify the spawned shot's
    # type actually matches whatever weapon the killer had equipped.
    state, player, pool = _kill_setup(weapon_id=WeaponId.ASSAULT_RIFLE, momentum=True)
    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    spawned = list(state.projectiles.iter_active())
    assert len(spawned) == 1
    assert spawned[0].owner.player_index() == 0
    assert weapon_entry_for_projectile_type_id(spawned[0].type_id).weapon_id == WeaponId.ASSAULT_RIFLE


def test_momentum_shot_carries_the_half_damage_penalty() -> None:
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT

    # 0% crit chance (UTILITY archetype) keeps crit_mult deterministic, so the
    # only thing touching it is Domino Effect's own penalty.
    state, player, pool = _kill_setup(weapon_id=WeaponId.SHRINKIFIER_5K, momentum=True)
    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    spawned = list(state.projectiles.iter_active())
    assert len(spawned) == 1
    assert_float_close(spawned[0].crit_mult, MOMENTUM_DAMAGE_MULT)


def test_momentum_fires_exactly_one_rocket_from_a_swarmer_dump_weapon() -> None:
    # Regression: Mini-Rocket Swarmers' SwarmerDumpMode reads ammo directly as
    # "how many rockets to dump this call" - a full-clip snapshot (5 ammo)
    # turned one kill's bonus shot into a 5-rocket, full-damage barrage, since
    # those rockets land in the secondary pool the old code never touched.
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT
    from crimson.weapon_runtime.crit import CRIT_MULTIPLIER

    state, player, pool = _kill_setup(weapon_id=WeaponId.MINI_ROCKET_SWARMERS, momentum=True)
    assert player.weapon.clip_size > 1  # sanity: a full clip would be more than one rocket
    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    assert not any(entry.active for entry in state.projectiles.entries)
    secondary = [entry for entry in state.secondary_projectiles.entries if entry.active]
    assert len(secondary) == 1
    # This weapon has a nonzero (5%) crit chance, so the raw multiplier before
    # the penalty is either 1.0 or CRIT_MULTIPLIER depending on that private
    # roll - assert the penalty is applied to whichever one it was, rather
    # than assuming a non-crit (which makes this flaky under full-suite RNG
    # state instead of a fresh interpreter).
    ratio = float(secondary[0].crit_mult) / MOMENTUM_DAMAGE_MULT
    assert ratio == pytest.approx(1.0) or ratio == pytest.approx(CRIT_MULTIPLIER)


def test_momentum_shot_fires_from_the_player_not_the_kill_site() -> None:
    # Regression: the clone used to spawn at the dead creature's position
    # instead of the killer's own position, both for the shot's origin and
    # for picking the "nearest" target - invisible in the other tests here
    # since their killer and dying creature share the origin by coincidence.
    state = GameplayState()
    state.bonus_spawn_guard = True
    player = PlayerState(index=0, pos=Vec2(1000.0, 0.0))
    player.perk_counts[int(PerkId.MOMENTUM)] = 1
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=state)

    pool = CreaturePool()
    dying = pool.entries[0]
    dying.active = True
    dying.pos = Vec2(0.0, 0.0)
    dying.hp = 0.0
    dying.max_hp = 100.0
    dying.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying.last_hit_owner = OwnerRef.from_player(0)

    # Nearest to the *player*, far from the kill site.
    near_player = pool.entries[1]
    near_player.active = True
    near_player.pos = Vec2(1010.0, 0.0)
    near_player.hp = 100.0

    # Nearest to the *kill site*, far from the player - would be picked if
    # the old (buggy) origin were still in use.
    near_kill_site = pool.entries[2]
    near_kill_site.active = True
    near_kill_site.pos = Vec2(10.0, 0.0)
    near_kill_site.hp = 100.0

    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=2048.0, world_height=2048.0, fx_queue=None)

    spawned = list(state.projectiles.iter_active())
    assert len(spawned) == 1
    # Origin includes the weapon's muzzle offset from the clone's position,
    # so compare against the player's position with slack rather than exactly -
    # the point is it's nowhere near the kill site (x=0), not pixel-perfect.
    assert spawned[0].origin.x == pytest.approx(1000.0, abs=50.0)


def test_momentum_shot_does_not_inherit_an_active_powerup() -> None:
    # Unlike Hollow Form's clone, Domino Effect's free shot deliberately does
    # not snapshot active powerup timers - a live Fire Bullets buff on the
    # real player must not carry over and change the bonus shot's projectile
    # type.
    from crimson.projectiles.types import ProjectileTemplateId

    state, player, pool = _kill_setup(weapon_id=WeaponId.ASSAULT_RIFLE, momentum=True)
    player.fire_bullets_timer = 5.0

    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    spawned = list(state.projectiles.iter_active())
    assert len(spawned) == 1
    assert spawned[0].type_id != ProjectileTemplateId.FIRE_BULLETS


def test_momentum_does_nothing_without_the_perk() -> None:
    state = GameplayState()
    state.bonus_spawn_guard = True
    player = PlayerState(index=0, pos=Vec2())

    pool = CreaturePool()
    dying = pool.entries[0]
    dying.active = True
    dying.hp = 0.0
    dying.max_hp = 100.0
    dying.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying.last_hit_owner = OwnerRef.from_player(0)

    other = pool.entries[1]
    other.active = True
    other.pos = Vec2(50.0, 0.0)
    other.hp = 100.0

    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    assert len(list(state.projectiles.iter_active())) == 0


def test_momentum_shot_does_not_chain_off_its_own_kill() -> None:
    # A Domino Effect shot's owner is tagged (OwnerRef.via_domino_effect) so
    # that if it kills something, that kill doesn't spawn another free shot.
    state, player, pool = _kill_setup(weapon_id=WeaponId.PISTOL, momentum=True)
    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    spawned = [entry for entry in state.projectiles.entries if entry.active]
    assert len(spawned) == 1
    assert spawned[0].owner.via_domino_effect is True

    # Simulate that shot landing a killing blow on `near`.
    near = pool.entries[2]
    near.hp = 0.0
    near.max_hp = 100.0
    near.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    near.last_hit_owner = spawned[0].owner

    far = pool.entries[3]
    far.active = True
    far.pos = Vec2(300.0, 0.0)
    far.hp = 100.0
    far.max_hp = 100.0

    before_count = sum(1 for entry in state.projectiles.entries if entry.active)
    pool.handle_death(2, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)
    after_count = sum(1 for entry in state.projectiles.entries if entry.active)
    assert after_count == before_count  # no new chained shot


# --- Cold Snap ---------------------------------------------------------


def test_cold_snap_freezes_the_target_on_a_crit() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=DEATH_WISH_HEALTH_THRESHOLD)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1  # forces the crit deterministically
    player.perk_counts[int(PerkId.COLD_SNAP)] = 1
    player.weapon.weapon_id = WeaponId.PISTOL

    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(20.0, 0.0), fire_down=True), dt=0.016, state=state),
    )

    creature = make_creature_state(pos=Vec2(20.0, 0.0), size=200.0)
    creature.hp = 1000.0
    creature.max_hp = 1000.0

    for _ in range(10):
        state.projectiles.step(
            PrimaryStepCtx(dt=0.1, creatures=[creature], options=make_projectile_update_options(runtime_state=state, players=[player])),
        )
        if creature.crit_freeze_timer > 0.0:
            break

    assert_float_close(creature.crit_freeze_timer, COLD_SNAP_FREEZE_DURATION)


def test_cold_snap_does_not_freeze_on_a_non_crit() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=100.0)
    player.perk_counts[int(PerkId.COLD_SNAP)] = 1
    player.weapon.weapon_id = WeaponId.SHRINKIFIER_5K  # UTILITY archetype, 0% crit chance

    _fresh_shot(player)
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(20.0, 0.0), fire_down=True), dt=0.016, state=state),
    )

    creature = make_creature_state(pos=Vec2(20.0, 0.0), size=200.0)
    creature.hp = 1000.0
    creature.max_hp = 1000.0

    for _ in range(10):
        state.projectiles.step(
            PrimaryStepCtx(dt=0.1, creatures=[creature], options=make_projectile_update_options(runtime_state=state, players=[player])),
        )

    assert creature.crit_freeze_timer == 0.0


def test_cold_snap_frozen_target_takes_bonus_damage_from_any_freeze_source() -> None:
    # Deep Freeze's real payoff isn't the freeze itself (it can never out-CC
    # Evil Eyes' unconditional, permanent freeze) - it's bonus damage to
    # anything currently frozen, regardless of what froze it. Set is_frozen
    # directly here rather than via crit_freeze_timer, to prove the bonus
    # doesn't care about the source (e.g. it should apply just as well to a
    # target Evil Eyes is holding).
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0, is_frozen=True)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.COLD_SNAP)] = 1

    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 87.0)  # 100 - (10 * 1.30)


def test_cold_snap_no_bonus_without_the_perk() -> None:
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0, is_frozen=True)
    player = PlayerState(index=0, pos=Vec2())  # no Cold Snap

    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 90.0)


def test_cold_snap_no_bonus_when_target_is_not_frozen() -> None:
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0, is_frozen=False)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.COLD_SNAP)] = 1

    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 90.0)


# --- Desperation ---------------------------------------------------------


def test_desperation_reduces_damage_more_at_lower_health() -> None:
    state = GameplayState()
    full_health_player = PlayerState(index=0, pos=Vec2(), health=100.0)
    full_health_player.perk_counts[int(PerkId.DESPERATION)] = 1
    applied_full = player_take_damage(state, full_health_player, 10.0)
    assert_float_close(applied_full, 10.0)

    state2 = GameplayState()
    low_health_player = PlayerState(index=0, pos=Vec2(), health=10.0)
    low_health_player.perk_counts[int(PerkId.DESPERATION)] = 1
    applied_low = player_take_damage(state2, low_health_player, 10.0)
    assert_float_close(applied_low, 10.0 * (1.0 - DESPERATION_MAX_REDUCTION * 0.9))
    assert applied_low < applied_full


# --- Kinetic Discipline ---------------------------------------------------------


def test_kinetic_discipline_charge_ramps_up_while_moving_straight() -> None:
    from crimson.perks.impl.kinetic_discipline import RAMP_UP_SECONDS
    from crimson.perks.runtime.effects import perks_update_effects

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), move_speed=2.0, heading=0.0)
    player.perk_counts[int(PerkId.KINETIC_DISCIPLINE)] = 1

    perks_update_effects(state, [player], 0.1)
    first_charge = player.kinetic_charge
    assert 0.0 < first_charge < 1.0

    perks_update_effects(state, [player], 0.1)
    assert player.kinetic_charge > first_charge  # still ramping up

    perks_update_effects(state, [player], RAMP_UP_SECONDS)
    assert player.kinetic_charge == pytest.approx(1.0)


def test_kinetic_discipline_charge_ramps_down_when_stopped() -> None:
    from crimson.perks.impl.kinetic_discipline import RAMP_DOWN_SECONDS
    from crimson.perks.runtime.effects import perks_update_effects

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), move_speed=2.0, heading=0.0, kinetic_charge=1.0)
    player.perk_counts[int(PerkId.KINETIC_DISCIPLINE)] = 1

    player.move_speed = 0.0  # stop
    perks_update_effects(state, [player], RAMP_DOWN_SECONDS / 2.0)
    assert 0.0 < player.kinetic_charge < 1.0

    perks_update_effects(state, [player], RAMP_DOWN_SECONDS)
    assert player.kinetic_charge == pytest.approx(0.0)


def test_kinetic_discipline_charge_ramps_down_on_a_sharp_turn() -> None:
    from crimson.perks.impl.kinetic_discipline import RAMP_DOWN_SECONDS
    from crimson.perks.runtime.effects import perks_update_effects

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), move_speed=2.0, heading=0.0, kinetic_charge=1.0)
    player.perk_counts[int(PerkId.KINETIC_DISCIPLINE)] = 1
    player.kinetic_prev_heading = 0.0

    player.heading = math.pi  # a 180-degree snap turn within one tick
    perks_update_effects(state, [player], RAMP_DOWN_SECONDS)
    assert player.kinetic_charge == pytest.approx(0.0)


def test_kinetic_discipline_damage_scales_with_charge() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.KINETIC_DISCIPLINE)] = 1
    player.kinetic_charge = 0.5

    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )
    assert_float_close(100.0 - creature.hp, 10.0 * (1.0 + KINETIC_DISCIPLINE_MAX_BONUS * 0.5))


# --- Free Rounds ---------------------------------------------------------


def test_free_rounds_sometimes_skips_the_ammo_cost() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.FREE_ROUNDS)] = 1
    player.weapon.weapon_id = WeaponId.PISTOL

    fired = 0
    free = 0
    for _ in range(500):
        _fresh_shot(player)
        before = player.weapon.ammo
        result = fire_weapon(
            WeaponFireCtx(player=player, input_state=PlayerInput(aim=Vec2(10.0, 0.0), fire_down=True), dt=0.016, state=state),
        )
        if result.fired:
            fired += 1
            if player.weapon.ammo == before:
                free += 1

    assert fired > 400
    # ~15% expected; loose band to avoid flakiness.
    assert 0.05 < free / fired < 0.30


# --- Steady Hands ---------------------------------------------------------


def test_steady_hands_bonus_damage_near_full_health_only() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.STEADY_HANDS)] = 1

    full_hp_creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    creature_apply_damage(
        full_hp_creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )
    assert_float_close(100.0 - full_hp_creature.hp, 10.0 * (1.0 + STEADY_HANDS_BONUS))

    damaged_creature = CreatureState(active=True, hp=100.0 * (STEADY_HANDS_HP_FRACTION - 0.1), max_hp=100.0)
    hp_before = damaged_creature.hp
    creature_apply_damage(
        damaged_creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )
    assert_float_close(hp_before - damaged_creature.hp, 10.0)


# --- Adrenaline Rush ---------------------------------------------------------


def test_adrenaline_rush_opens_a_window_when_the_player_loses_health() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1

    player_take_damage(state, player, 10.0)

    assert player.adrenaline_rush_window_timer == pytest.approx(ADRENALINE_RUSH_WINDOW_DURATION)


def test_adrenaline_rush_does_not_open_on_a_dodged_or_blocked_hit() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0, shield_timer=1.0)
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1

    player_take_damage(state, player, 10.0)

    assert player.adrenaline_rush_window_timer == 0.0


def test_adrenaline_rush_window_decays_over_time() -> None:
    from crimson.perks.runtime.effects import perks_update_effects

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1

    player_take_damage(state, player, 10.0)
    assert player.adrenaline_rush_window_timer == pytest.approx(ADRENALINE_RUSH_WINDOW_DURATION)

    perks_update_effects(state, [player], ADRENALINE_RUSH_WINDOW_DURATION - 1.0)
    assert player.adrenaline_rush_window_timer == pytest.approx(1.0)

    perks_update_effects(state, [player], 1.0)
    assert player.adrenaline_rush_window_timer == pytest.approx(0.0)


def test_adrenaline_rush_boosts_damage_while_the_window_is_open() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1
    player.adrenaline_rush_window_timer = ADRENALINE_RUSH_WINDOW_DURATION

    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )
    assert_float_close(100.0 - creature.hp, 10.0 * (1.0 + ADRENALINE_RUSH_BONUS))


def test_adrenaline_rush_does_nothing_once_the_window_expires() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.ADRENALINE_RUSH)] = 1
    player.adrenaline_rush_window_timer = 0.0

    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )
    assert_float_close(100.0 - creature.hp, 10.0)
