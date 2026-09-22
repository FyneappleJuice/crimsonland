from __future__ import annotations

from crimson.gameplay import (
    GameplayState,
    player_update,
)
from crimson.math_parity import f32
from crimson.perks import PerkId
from crimson.perks.availability import build_perk_availability, perk_can_offer
from crimson.game_modes import GameMode
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import assert_float_close


def test_anxious_loader_is_disabled_by_design_not_offer_predicate() -> None:
    # Disabled the same way ANTIPERK is: excluded from availability so it's
    # never offered/selected again, while its mechanic (below) still resolves
    # correctly for any player that already has it (old saves/replays,
    # debug-granted perks).
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    assert perk_can_offer(state, player, PerkId.ANXIOUS_LOADER, game_mode=GameMode.SURVIVAL, player_count=1)
    assert not build_perk_availability(status=None)[int(PerkId.ANXIOUS_LOADER)]


def test_anxious_loader_reduces_reload_timer_on_fire_press() -> None:
    state = GameplayState()

    base_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    base_player.weapon.reload_active = True
    base_player.weapon.reload_timer_max = 1.0
    base_player.weapon.reload_timer = 1.0

    perk_player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    perk_player.perk_counts[int(PerkId.ANXIOUS_LOADER)] = 1
    perk_player.weapon.reload_active = True
    perk_player.weapon.reload_timer_max = 1.0
    perk_player.weapon.reload_timer = 1.0

    input_state = PlayerInput(fire_pressed=True)
    player_update(base_player, input_state, dt=0.1, state=state)
    player_update(perk_player, input_state, dt=0.1, state=state)

    expected_base_timer = f32(f32(1.0) - f32(0.1))
    expected_perk_timer = f32(f32(f32(1.0) - 0.05) - f32(0.1))
    assert_float_close(base_player.weapon.reload_timer, expected_base_timer)
    assert_float_close(perk_player.weapon.reload_timer, expected_perk_timer)
