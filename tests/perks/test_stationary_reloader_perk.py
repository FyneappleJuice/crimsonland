from __future__ import annotations

from crimson.gameplay import (
    GameplayState,
    player_update,
)
from crimson.math_parity import f32
from crimson.perks import PerkId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import assert_float_close


def test_stationary_reloader_triples_reload_speed() -> None:
    state = GameplayState()

    base_player = PlayerState(index=0, pos=Vec2(100.0, 100.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    base_player.weapon.reload_active = True
    base_player.weapon.reload_timer_max = 1.0
    base_player.weapon.reload_timer = 1.0

    perk_player = PlayerState(index=0, pos=Vec2(100.0, 100.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    perk_player.perk_counts[int(PerkId.STATIONARY_RELOADER)] = 1
    perk_player.weapon.reload_active = True
    perk_player.weapon.reload_timer_max = 1.0
    perk_player.weapon.reload_timer = 1.0

    player_update(base_player, PlayerInput(), dt=0.1, state=state)
    player_update(perk_player, PlayerInput(), dt=0.1, state=state)

    assert_float_close(base_player.weapon.reload_timer, f32(0.9))
    assert_float_close(perk_player.weapon.reload_timer, f32(0.7))


def test_stationary_reloader_also_speeds_up_swarmer_dump_shot_cooldown() -> None:
    # Regression: Mini-Rocket Swarmers' shot_cooldown *is* the between-volleys
    # wait (same role reload_timer plays everywhere else), but Stationary
    # Reloader used to only ever scale reload_timer's own decay. A Free
    # Rounds proc skips starting a reload entirely that cycle, so it fell
    # back to the slow, un-boosted native shot_cooldown while a normal
    # (non-proc) cycle enjoyed the boosted reload - proccing what's supposed
    # to be a pure bonus perk made the next shot arrive *later*. Both must
    # decay at the same boosted rate now.
    from crimson.weapon_runtime import weapon_assign_player

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.STATIONARY_RELOADER)] = 1
    weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=state)
    player.weapon.shot_cooldown = 1.0
    # No ammo cost was ever charged this cycle (as a Free Rounds proc would
    # leave it) - reload_timer stays untouched at 0, only shot_cooldown ticks.

    player_update(player, PlayerInput(), dt=0.1, state=state)

    assert_float_close(player.weapon.shot_cooldown, f32(0.7))
