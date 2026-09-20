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
