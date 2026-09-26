from __future__ import annotations

import msgspec

from grim.geom import Vec2

from ..aim_schemes import AimScheme
from ..movement_controls import MovementControlType


class PlayerInput(msgspec.Struct, frozen=True):
    move: Vec2 = Vec2()
    aim: Vec2 = Vec2()
    move_mode: MovementControlType | None = None
    aim_scheme: AimScheme | None = None
    fire_down: bool = False
    fire_pressed: bool = False
    reload_pressed: bool = False
    reload_down: bool = False
    # Not native: Auto-fire toggle keybind (default T) - a discrete press
    # edge only, no held/down state needed (see gameplay.py's player_update,
    # which flips PlayerState.auto_fire_mode_enabled on each press).
    auto_fire_pressed: bool = False
    move_to_cursor_pressed: bool = False
    move_forward_pressed: bool | None = None
    move_backward_pressed: bool | None = None
    turn_left_pressed: bool | None = None
    turn_right_pressed: bool | None = None
