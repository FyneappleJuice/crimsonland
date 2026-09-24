from __future__ import annotations

import pytest

from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.perks.ids import PerkId
from crimson.perks.impl.hollow_form import HOLLOW_FORM_ACTIVE_DURATION
from crimson.perks.runtime.effects import perks_update_effects
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime.assign import weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _make_target(pos: Vec2) -> CreatureState:
    creature = CreatureState(active=True, hp=1_000_000.0, max_hp=1_000_000.0)
    creature.pos = pos
    return creature


def test_hollow_form_spawns_a_snapshot_at_the_player_and_fires() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(50.0, 25.0), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    creature = _make_target(Vec2(250.0, 25.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])

    assert player.hollow_form_snapshot is not None
    assert player.hollow_form_pos == player.pos
    assert player.hollow_form_snapshot.weapon.weapon_id == WeaponId.PISTOL

    # Spawning and firing are separate ticks - the clone aims and pulls the
    # trigger starting the tick *after* it appears.
    perks_update_effects(state, [player], 0.016, creatures=[creature])
    assert any(entry.active for entry in state.projectiles.entries)


def test_hollow_form_never_touches_the_real_players_weapon_or_streak_state() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    ammo_before = player.weapon.ammo
    creature = _make_target(Vec2(200.0, 0.0))

    for _ in range(10):
        perks_update_effects(state, [player], 0.016, creatures=[creature])

    assert player.weapon.ammo == ammo_before
    assert player.shot_seq == 0
    assert player.overdue_streak == 0


def test_hollow_form_fires_more_often_on_a_faster_weapon() -> None:
    def shots_fired(weapon_id: WeaponId) -> int:
        state = GameplayState()
        player = PlayerState(index=0, pos=Vec2(), health=100.0)
        player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
        weapon_assign_player(player, weapon_id, state=state)
        creature = _make_target(Vec2(200.0, 0.0))

        shots = 0
        for i in range(80):
            before = sum(1 for e in state.projectiles.entries if e.active)
            perks_update_effects(state, [player], 0.016, creatures=[creature])
            after = sum(1 for e in state.projectiles.entries if e.active)
            shots += max(0, after - before)
            if player.hollow_form_snapshot is None and i > 5:
                break
        return shots

    pistol_shots = shots_fired(WeaponId.PISTOL)
    minigun_shots = shots_fired(WeaponId.MEAN_MINIGUN)
    assert pistol_shots >= 1
    assert minigun_shots > pistol_shots


def test_hollow_form_clone_vanishes_after_the_active_duration() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    creature = _make_target(Vec2(200.0, 0.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])
    assert player.hollow_form_snapshot is not None

    perks_update_effects(state, [player], HOLLOW_FORM_ACTIVE_DURATION + 0.1, creatures=[creature])
    assert player.hollow_form_snapshot is None
    assert player.hollow_form_active_timer == 0.0
    # A fresh recharge interval should now be counting down (4-10s).
    assert 4.0 <= player.hollow_form_timer <= 10.0


def test_hollow_form_does_nothing_without_a_living_target() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    dead_creature = CreatureState(active=True, hp=0.0, max_hp=100.0)
    dead_creature.pos = Vec2(200.0, 0.0)

    perks_update_effects(state, [player], 0.016, creatures=[dead_creature])

    assert player.hollow_form_snapshot is not None  # still spawns...
    assert not any(entry.active for entry in state.projectiles.entries)  # ...but never fires


def test_hollow_form_clone_can_proc_its_own_hot_tempered() -> None:
    # The clone now runs the same periodic-perk-tick pipeline a real player's
    # frame does, so a Hot Tempered ring (8 plasma projectiles) should fire
    # off the clone's own snapshot, independent of pulling the trigger.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(50.0, 25.0), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    player.perk_counts[int(PerkId.HOT_TEMPERED)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    creature = _make_target(Vec2(250.0, 25.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])
    assert player.hollow_form_snapshot is not None

    # A dt bigger than Hot Tempered's ~1.4s default interval forces the
    # clone's own timer past threshold in a single tick. perks_update_effects
    # never calls player_update(), so this can only be the clone's own tick -
    # the real player's Hot Tempered never runs in this harness.
    perks_update_effects(state, [player], 1.5, creatures=[creature])

    active = [entry for entry in state.projectiles.entries if entry.active]
    assert len(active) >= 8


def test_hollow_form_clone_gets_stationary_reloader_since_it_never_moves() -> None:
    # Regression: the clone's own weapon-timer decrement used to always skip
    # Stationary Reloader ("no Stationary Reloader nuance"), so a clone stuck
    # in one spot for its whole 2s window never got the bonus a real
    # stationary player would - most visible on a dump-clip weapon like
    # Mini-Rocket Swarmers, where reload is the main bottleneck between shots.
    def rockets_fired(*, stationary_reloader: bool) -> int:
        state = GameplayState()
        player = PlayerState(index=0, pos=Vec2(), health=100.0)
        player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
        if stationary_reloader:
            player.perk_counts[int(PerkId.STATIONARY_RELOADER)] = 1
        weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=state)
        creature = _make_target(Vec2(200.0, 0.0))

        fired = 0
        for i in range(600):
            before = sum(1 for e in state.secondary_projectiles.entries if e.active)
            perks_update_effects(state, [player], 0.016, creatures=[creature])
            after = sum(1 for e in state.secondary_projectiles.entries if e.active)
            fired += max(0, after - before)
        return fired

    without = rockets_fired(stationary_reloader=False)
    with_perk = rockets_fired(stationary_reloader=True)
    assert with_perk > without


def test_hollow_form_clone_gets_angry_reloader_ring_burst_mid_reload() -> None:
    # Regression: the clone's weapon-timer advance now reuses player_update's
    # own gameplay.advance_weapon_reload verbatim (instead of a hand-rolled
    # reimplementation), so perks hooked into that pipeline that nobody
    # thought to special-case for the clone - Angry Reloader's mid-reload
    # projectile-ring burst - now fire for it too.
    from crimson.projectiles.types import ProjectileTemplateId

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    player.perk_counts[int(PerkId.ANGRY_RELOADER)] = 1
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    creature = _make_target(Vec2(200.0, 0.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])
    clone = player.hollow_form_snapshot
    assert clone is not None

    # Force the clone straight into a mid-reload state rather than waiting
    # out a full clip - Angry Reloader triggers once reload_timer crosses
    # below half of reload_timer_max.
    clone.weapon.ammo = 0.0
    clone.weapon.reload_active = True
    clone.weapon.reload_timer_max = 1.0
    clone.weapon.reload_timer = 0.6

    for _ in range(20):
        perks_update_effects(state, [player], 0.016, creatures=[creature])
        if clone.weapon.reload_timer <= 0.5:
            break

    ring_bolts = [
        e for e in state.projectiles.entries if e.active and e.type_id == ProjectileTemplateId.PLASMA_MINIGUN
    ]
    assert len(ring_bolts) >= 7  # Angry Reloader's ring is "7 + reload_timer_max * 4" bolts


def test_hollow_form_clone_seeker_rounds_bonus_rocket_spawns_from_the_clone_bullet_weapon() -> None:
    # Regression: the clone shares its real player's own index/OwnerRef, so
    # anything that looked the shooter up by that index (Seeker Rounds' bonus
    # rocket) always found the *real* player and used their current
    # position - even when the clone, not the real player, was the one
    # actually firing. Move the real player far away right after the clone
    # spawns; the bonus rocket must still appear at the clone's frozen spot.
    from crimson.projectiles.runtime import PrimaryStepCtx
    from crimson.projectiles.types import SecondaryProjectileTypeId
    from tests.support.factories import make_projectile_update_options

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    player.perk_counts[int(PerkId.SEEKER_ROUNDS)] = 1
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=state)
    creature = _make_target(Vec2(60.0, 0.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])
    assert player.hollow_form_snapshot is not None
    clone_pos = player.hollow_form_pos

    player.pos = Vec2(900.0, 900.0)

    spawn_positions: list[Vec2] = []
    for _ in range(120):
        before = {
            i for i, e in enumerate(state.secondary_projectiles.entries)
            if e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET
        }
        perks_update_effects(state, [player], 0.016, creatures=[creature])
        state.projectiles.step(
            PrimaryStepCtx(
                dt=0.016,
                creatures=[creature],
                options=make_projectile_update_options(runtime_state=state, players=[player]),
            ),
        )
        for i, e in enumerate(state.secondary_projectiles.entries):
            if e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET and i not in before:
                spawn_positions.append(e.pos)
        if player.hollow_form_snapshot is None:
            break

    assert len(spawn_positions) >= 1
    for pos in spawn_positions:
        assert pos.distance_to(clone_pos) < 50.0
        assert pos.distance_to(player.pos) > 500.0


def test_hollow_form_clone_seeker_rounds_bonus_rocket_spawns_from_the_clone_rocket_weapon() -> None:
    from crimson.projectiles.runtime.secondary_pool import SecondaryStepCtx
    from crimson.projectiles.types import SecondaryProjectileTypeId

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=100.0)
    player.perk_counts[int(PerkId.HOLLOW_FORM)] = 1
    player.perk_counts[int(PerkId.SEEKER_ROUNDS)] = 1
    weapon_assign_player(player, WeaponId.ROCKET_MINIGUN, state=state)
    creature = _make_target(Vec2(60.0, 0.0))

    perks_update_effects(state, [player], 0.016, creatures=[creature])
    assert player.hollow_form_snapshot is not None
    clone_pos = player.hollow_form_pos

    player.pos = Vec2(900.0, 900.0)

    spawn_positions: list[Vec2] = []
    for _ in range(120):
        before = {
            i for i, e in enumerate(state.secondary_projectiles.entries)
            if e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET
        }
        perks_update_effects(state, [player], 0.016, creatures=[creature])
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=0.016, creatures=[creature], runtime_state=state, players=[player]),
        )
        for i, e in enumerate(state.secondary_projectiles.entries):
            if e.active and e.type_id == SecondaryProjectileTypeId.HOMING_ROCKET and i not in before:
                spawn_positions.append(e.pos)
        if player.hollow_form_snapshot is None:
            break

    assert len(spawn_positions) >= 1
    for pos in spawn_positions:
        assert pos.distance_to(clone_pos) < 50.0
        assert pos.distance_to(player.pos) > 500.0


def test_hollow_form_resets_when_perk_is_not_active() -> None:
    state = GameplayState()
    player = PlayerState(
        index=0,
        pos=Vec2(),
        health=100.0,
        hollow_form_timer=5.0,
        hollow_form_active_timer=0.5,
    )
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    player.hollow_form_snapshot = player  # any non-None sentinel

    perks_update_effects(state, [player], 0.016, creatures=[])

    assert player.hollow_form_timer == 0.0
    assert player.hollow_form_active_timer == 0.0
    assert player.hollow_form_snapshot is None
