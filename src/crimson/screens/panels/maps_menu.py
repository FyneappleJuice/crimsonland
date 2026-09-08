from __future__ import annotations

from grim.audio import update_audio
from grim.fonts.small import draw_small_text
from grim.geom import Vec2
from grim.raylib_api import rl

from ...game.types import GameState
from ...game_modes import GameMode
from ...modes.maps_mode import MapsMode
from ...ui.perk_menu import UiButtonState, button_draw, button_update, button_width
from ..assets import require_runtime_resources
from .base import PanelMenuView

_CONTENT_X = 32.0
_TITLE_Y = 140.0
_TAGLINE_Y = 176.0
_BOSS_Y = 198.0
_BUTTON_Y = 236.0
_BUTTON_GAP = 40.0
_TEXT_COLOR = rl.Color(220, 220, 220, 255)
_HINT_COLOR = rl.Color(170, 150, 120, 255)


class MapsMenuView(PanelMenuView):
    """Map-select screen: rolls a `MapModifier` and previews it before launch.

    Reuses `PanelMenuView` for the shared menu chrome (panel background, Back
    button, ESC/fade handling) and the same button widgets `PlayGameMenuView`
    uses; simpler custom layout since there is no native reference for this
    screen to match.
    """

    def __init__(self, state: GameState, *, maps_mode: MapsMode) -> None:
        super().__init__(
            state,
            title="Maps",
            back_pos=Vec2(-55.0, 462.0),
        )
        self._maps_mode = maps_mode
        self._enter_button = UiButtonState("Enter Map")
        self._reroll_button = UiButtonState("Reroll")

    def open(self) -> None:
        super().open()
        self._maps_mode.roll_modifier()
        self._enter_button = UiButtonState("Enter Map")
        self._reroll_button = UiButtonState("Reroll")

    def update(self, dt: float) -> None:
        self._assert_open()
        if self.state.audio is not None:
            update_audio(self.state.audio, dt)
        if self._ground is not None:
            self._ground.process_pending()
        self._cursor_pulse_time += min(dt, 0.1) * 1.1
        dt_ms = int(min(dt, 0.1) * 1000.0)

        if self._closing:
            if dt_ms > 0 and self._pending_action is None:
                self._timeline_ms -= dt_ms
                if self._timeline_ms < 0 and self._close_action is not None:
                    self._pending_action = self._close_action
                    self._close_action = None
            return

        if dt_ms > 0:
            self._timeline_ms = min(self._timeline_max_ms, self._timeline_ms + dt_ms)
            if self._timeline_ms >= self._timeline_max_ms:
                self.state.menu_sign_locked = True

        entry = self._entry
        if entry is None:
            return

        enabled = self._entry_enabled(entry)
        hovered_back = enabled and self._hovered_entry(entry)
        self._hovered = hovered_back

        if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE) and enabled:
            self._begin_close_transition(self._back_action)
        if enabled and hovered_back and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
            self._begin_close_transition(self._back_action)

        if hovered_back:
            entry.hover_amount += dt_ms * 6
        else:
            entry.hover_amount -= dt_ms * 2
        entry.hover_amount = max(0, min(1000, entry.hover_amount))

        if entry.ready_timer_ms < 0x100:
            entry.ready_timer_ms = min(0x100, entry.ready_timer_ms + dt_ms)

        if not enabled:
            return

        resources = require_runtime_resources(self.state)
        mouse = rl.get_mouse_position()
        click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

        reroll_width = button_width(resources, self._reroll_button.label, scale=1.0, force_wide=False)
        if button_update(
            self._reroll_button,
            pos=Vec2(_CONTENT_X, _BUTTON_Y),
            width=reroll_width,
            dt_ms=float(dt_ms),
            mouse=mouse,
            click=click,
        ):
            self._maps_mode.roll_modifier()
            return

        enter_width = button_width(resources, self._enter_button.label, scale=1.0, force_wide=True)
        if button_update(
            self._enter_button,
            pos=Vec2(_CONTENT_X, _BUTTON_Y + _BUTTON_GAP),
            width=enter_width,
            dt_ms=float(dt_ms),
            mouse=mouse,
            click=click,
        ):
            self.state.config.gameplay.mode = GameMode.MAPS
            self._begin_close_transition("start_maps")

    def _draw_contents(self) -> None:
        resources = require_runtime_resources(self.state)
        font = resources.small_font
        modifier = self._maps_mode.current_modifier

        rl.draw_text(self._title, int(_CONTENT_X), int(_TITLE_Y), 28, _TEXT_COLOR)
        draw_small_text(font, modifier.name, Vec2(_CONTENT_X, _TAGLINE_Y), _TEXT_COLOR)
        draw_small_text(font, modifier.tagline, Vec2(_CONTENT_X, _TAGLINE_Y + 16.0), _HINT_COLOR)
        draw_small_text(
            font,
            f"Boss: {modifier.boss_name}  (arrives at {int(modifier.boss_trigger_ms // 1000)}s)",
            Vec2(_CONTENT_X, _BOSS_Y),
            _HINT_COLOR,
        )

        reroll_width = button_width(resources, self._reroll_button.label, scale=1.0, force_wide=False)
        button_draw(resources, self._reroll_button, pos=Vec2(_CONTENT_X, _BUTTON_Y), width=reroll_width, scale=1.0)

        enter_width = button_width(resources, self._enter_button.label, scale=1.0, force_wide=True)
        button_draw(
            resources,
            self._enter_button,
            pos=Vec2(_CONTENT_X, _BUTTON_Y + _BUTTON_GAP),
            width=enter_width,
            scale=1.0,
        )
