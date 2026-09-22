from __future__ import annotations

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.rarity import MonsterRarity
from crimson.creatures.runtime import CREATURE_LIFECYCLE_ALIVE, CreaturePool, CreatureState
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.perks.impl.delicate_watch import DELICATE_WATCH_BONUS, DELICATE_WATCH_BREAK_THRESHOLD
from crimson.perks.impl.harvester_scythe import HARVESTER_SCYTHE_HEAL_PER_CRIT, harvester_scythe_on_crit
from crimson.perks.impl.hit_list import HIT_LIST_BONUS_PER_KILL, HIT_LIST_MAX_BONUS, update_hit_list_mark
from crimson.perks.ids import PerkId
from crimson.perks.runtime.effects_context import PerksUpdateEffectsCtx
from crimson.projectiles.runtime import PrimaryStepCtx
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon
from crimson.weapon_runtime.assign import weapon_assign_player
from crimson.weapon_runtime.fire import DEATH_WISH_HEALTH_THRESHOLD
from crimson.weapons import WeaponId
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import make_creature_state, make_projectile_update_options
from tests.support.helpers import assert_float_close

# --- The Hit List ----------------------------------------------------------


def test_hit_list_only_marks_apex_tier_monsters() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.HIT_LIST)] = 1

    pool = CreaturePool()
    tainted = pool.entries[0]
    tainted.active = True
    tainted.hp = 10.0
    tainted.rarity = int(MonsterRarity.TAINTED)

    apex = pool.entries[1]
    apex.active = True
    apex.hp = 10.0
    apex.rarity = int(MonsterRarity.APEX)

    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=0.016, creatures=pool.entries, fx_queue=None)
    update_hit_list_mark(ctx)

    assert not tainted.hit_list_marked
    assert apex.hit_list_marked


def test_hit_list_does_nothing_without_the_perk() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())

    pool = CreaturePool()
    apex = pool.entries[0]
    apex.active = True
    apex.hp = 10.0
    apex.rarity = int(MonsterRarity.APEX)

    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=0.016, creatures=pool.entries, fx_queue=None)
    update_hit_list_mark(ctx)

    assert not apex.hit_list_marked


def test_hit_list_kill_grants_capped_permanent_bonus() -> None:
    state = GameplayState()
    state.bonus_spawn_guard = True
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.HIT_LIST)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    pool = CreaturePool()
    dying = pool.entries[0]
    dying.active = True
    dying.pos = Vec2()
    dying.hp = 0.0
    dying.max_hp = 100.0
    dying.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying.last_hit_owner = OwnerRef.from_player(0)
    dying.hit_list_marked = True

    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    assert_float_close(player.hit_list_bonus, HIT_LIST_BONUS_PER_KILL)

    # Repeated marked kills cap out instead of growing forever.
    player.hit_list_bonus = HIT_LIST_MAX_BONUS
    dying2 = pool.entries[1]
    dying2.active = True
    dying2.pos = Vec2()
    dying2.hp = 0.0
    dying2.max_hp = 100.0
    dying2.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying2.last_hit_owner = OwnerRef.from_player(0)
    dying2.hit_list_marked = True
    pool.handle_death(1, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    assert_float_close(player.hit_list_bonus, HIT_LIST_MAX_BONUS)


def test_hit_list_unmarked_kill_grants_no_bonus() -> None:
    state = GameplayState()
    state.bonus_spawn_guard = True
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.HIT_LIST)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    pool = CreaturePool()
    dying = pool.entries[0]
    dying.active = True
    dying.pos = Vec2()
    dying.hp = 0.0
    dying.max_hp = 100.0
    dying.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
    dying.last_hit_owner = OwnerRef.from_player(0)

    pool.handle_death(0, state=state, players=[player], rng=state.rng, world_width=1024.0, world_height=1024.0, fx_queue=None)

    assert player.hit_list_bonus == 0.0


def test_hit_list_damage_bonus_scales_creature_damage() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.HIT_LIST)] = 1
    player.hit_list_bonus = 0.10
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)

    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 100.0 - 11.0)


# --- Delicate Watch ----------------------------------------------------------


def test_delicate_watch_boosts_outgoing_damage() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.DELICATE_WATCH)] = 1
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)

    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_player(0), dt=0.016, players=[player], rng=Crand(1),
    )

    assert_float_close(creature.hp, 100.0 - 10.0 * (1.0 + DELICATE_WATCH_BONUS))


def test_delicate_watch_breaks_below_threshold_and_can_be_offered_again() -> None:
    from crimson.perks.impl.delicate_watch import update_delicate_watch_break

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DELICATE_WATCH_BREAK_THRESHOLD - 1.0)
    player.perk_counts[int(PerkId.DELICATE_WATCH)] = 1

    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=0.016, creatures=None, fx_queue=None)
    update_delicate_watch_break(ctx)

    # Broken == not owned any more (perks/selection.py re-offers on count 0).
    assert player.perk_counts[int(PerkId.DELICATE_WATCH)] == 0


def test_delicate_watch_survives_at_or_above_threshold() -> None:
    from crimson.perks.impl.delicate_watch import update_delicate_watch_break

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=DELICATE_WATCH_BREAK_THRESHOLD)
    player.perk_counts[int(PerkId.DELICATE_WATCH)] = 1

    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=0.016, creatures=None, fx_queue=None)
    update_delicate_watch_break(ctx)

    assert player.perk_counts[int(PerkId.DELICATE_WATCH)] == 1


# --- Harvester's Scythe ------------------------------------------------------


def test_harvester_scythe_heals_on_crit() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1

    harvester_scythe_on_crit(player)

    assert_float_close(player.health, 50.0 + HARVESTER_SCYTHE_HEAL_PER_CRIT)


def test_harvester_scythe_does_nothing_without_the_perk() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)

    harvester_scythe_on_crit(player)

    assert player.health == 50.0


def test_harvester_scythe_clamps_at_full_health() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=99.5)
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1

    harvester_scythe_on_crit(player)

    assert player.health <= 100.0


def test_harvester_scythe_heals_through_a_real_forced_crit_shot() -> None:
    # Integration check that the heal is actually wired into the crit
    # resolution path - not just callable in isolation - and specifically
    # that it fires on an actual HIT (projectile_pool.py), not merely on a
    # shot being fired: force every shot to crit via Death Wish's low-health
    # threshold, then simulate the bolt actually connecting with a creature.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=DEATH_WISH_HEALTH_THRESHOLD)
    player.perk_counts[int(PerkId.DEATH_WISH)] = 1
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)

    health_before = player.health
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=Vec2(20.0, 0.0)),
            dt=0.0,
            state=state,
            players=[player],
        ),
    )

    # A whiffed crit (nothing in the bolt's path) must NOT heal.
    for _ in range(5):
        state.projectiles.step(
            PrimaryStepCtx(dt=0.1, creatures=[], options=make_projectile_update_options(runtime_state=state, players=[player])),
        )
    assert player.health == health_before

    weapon_assign_player(player, WeaponId.PISTOL, state=state)  # fresh ammo/cooldown for a second shot
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=Vec2(20.0, 0.0)),
            dt=0.0,
            state=state,
            players=[player],
        ),
    )
    creature = make_creature_state(pos=Vec2(20.0, 0.0), size=200.0)
    creature.hp = 1000.0
    creature.max_hp = 1000.0
    for _ in range(10):
        state.projectiles.step(
            PrimaryStepCtx(dt=0.1, creatures=[creature], options=make_projectile_update_options(runtime_state=state, players=[player])),
        )
        if player.health > health_before:
            break

    assert player.health > health_before


def test_harvester_scythe_crit_opens_the_flash_window() -> None:
    from crimson.perks.impl.harvester_scythe import HARVESTER_SCYTHE_FLASH_DURATION

    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1
    assert player.harvester_scythe_flash_timer == 0.0

    harvester_scythe_on_crit(player)

    assert player.harvester_scythe_flash_timer == HARVESTER_SCYTHE_FLASH_DURATION


def test_harvester_scythe_flash_counts_down_via_effects_step() -> None:
    from crimson.perks.impl.harvester_scythe import (
        HARVESTER_SCYTHE_FLASH_DURATION,
        update_harvester_scythe_flash,
    )

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1
    harvester_scythe_on_crit(player)

    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=0.016, creatures=None, fx_queue=None)
    update_harvester_scythe_flash(ctx)

    # f32 (not double) rounding throughout x87_pc24_sub - loose tolerance.
    assert player.harvester_scythe_flash_timer == pytest.approx(HARVESTER_SCYTHE_FLASH_DURATION - 0.016, abs=1e-5)

    # Long enough dt floors it at 0, never negative.
    ctx = PerksUpdateEffectsCtx(state=state, players=[player], dt=10.0, creatures=None, fx_queue=None)
    update_harvester_scythe_flash(ctx)

    assert player.harvester_scythe_flash_timer == 0.0
