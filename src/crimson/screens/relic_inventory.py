from __future__ import annotations

"""Not native: the pre-run relic inventory screen.

Left panel = the global relic inventory, right panel = a 5x5 grid. Click an
inventory relic to pick it up (it follows the cursor), click a grid cell to
place it; click a placed relic to pick it back up. PLAY starts Survival with
every placed relic's mods active for the run; BACK returns to the menu.

Styled to match the classic menu panels (ground backdrop, ui_menuPanel frame,
Crimsonland sign, ui buttons).
"""

from grim.assets import TextureId
from grim.audio import play_sfx, update_audio
from grim.geom import Rect, Vec2
from grim.raylib_api import rl
from grim.sfx_map import SfxId
from grim.terrain_render import GroundRenderer

from ..game.types import GameState
from ..meta import relics
from ..ui.perk_menu import (
    MENU_ITEM_RGB,
    UiButtonState,
    button_draw,
    button_update,
    button_width,
    draw_ui_text,
)
from .assets import require_runtime_resources
from .menu import (
    MENU_SIGN_HEIGHT,
    MENU_SIGN_OFFSET_X,
    MENU_SIGN_OFFSET_Y,
    MENU_SIGN_POS_X_PAD,
    MENU_SIGN_POS_Y,
    MENU_SIGN_POS_Y_SMALL,
    MENU_SIGN_WIDTH,
    MenuView,
    _draw_menu_cursor,
    ensure_menu_ground,
    menu_ground_camera,
)
from ..ui.menu_panel import draw_classic_menu_panel
from .transitions import _draw_screen_fade

_BLUE = rl.Color(*MENU_ITEM_RGB, 255)
_BLUE_DIM = rl.Color(*MENU_ITEM_RGB, 150)
_WHITE = rl.Color(235, 237, 245, 255)
_DIM = rl.Color(160, 162, 172, 255)
_CELL_BG = rl.Color(18, 22, 30, 235)
_CELL_BG_HOVER = rl.Color(40, 56, 78, 235)
_CELL_FILLED = rl.Color(34, 58, 92, 245)

_CELL = 52.0
_CELL_GAP = 8.0


class RelicInventoryView:
    def __init__(self, state: GameState) -> None:
        self.state = state
        self._is_open = False
        self._pending_action: str | None = None
        self._cursor_pulse = 0.0
        self._ground: GroundRenderer | None = None

        self._held: int = 0  # relic id currently on the cursor (0 = none)
        self._inv_rects: list[tuple[Rect, int]] = []  # (row rect, relic id)
        self._grid_rects: list[Rect] = []
        self._left_panel = Rect.from_pos_size(Vec2(), Vec2())
        self._right_panel = Rect.from_pos_size(Vec2(), Vec2())

        self._play_btn = UiButtonState("Play", force_wide=True)
        self._back_btn = UiButtonState("Back", force_wide=True)

    # --- Screen protocol -------------------------------------------------

    def open(self) -> None:
        relics.init_relics(self.state.base_dir)
        relics.end_run()
        self._ground = None if self.state.pause_background is not None else ensure_menu_ground(self.state)
        self._is_open = True
        self._pending_action = None
        self._cursor_pulse = 0.0
        self._held = 0
        self._play_btn = UiButtonState("Play", force_wide=True)
        self._back_btn = UiButtonState("Back", force_wide=True)
        if self.state.audio is not None:
            play_sfx(self.state.audio, SfxId.UI_PANELCLICK)

    def close(self) -> None:
        self._is_open = False
        self._ground = None

    def update(self, dt: float) -> None:
        if self.state.audio is not None:
            update_audio(self.state.audio, dt)
        if self._ground is not None:
            self._ground.process_pending()
        self._cursor_pulse += min(dt, 0.1) * 1.1
        dt_ms = min(dt, 0.1) * 1000.0

        m = rl.get_mouse_position()
        mp = Vec2(float(m.x), float(m.y))
        click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)

        if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
            if self._held:
                self._return_held()
            else:
                self._pending_action = "back_to_menu"
            return

        if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_RIGHT) and self._held:
            self._return_held()
            return

        scale = self._scale()
        play_w = button_width(require_runtime_resources(self.state), "Play", scale=scale, force_wide=True)
        back_w = button_width(require_runtime_resources(self.state), "Back", scale=scale, force_wide=True)
        if button_update(self._back_btn, pos=self._back_pos(back_w), width=back_w, dt_ms=dt_ms, mouse=m, click=click):
            self._return_held()
            self._pending_action = "back_to_menu"
            return
        if button_update(self._play_btn, pos=self._play_pos(play_w), width=play_w, dt_ms=dt_ms, mouse=m, click=click):
            self._return_held()
            relics.begin_run()
            self._pending_action = "start_survival"
            return

        if not click:
            return

        # inventory rows
        for rect, rid in self._inv_rects:
            if rect.contains(mp):
                if self._held:
                    self._return_held()
                else:
                    self._pick_from_inventory(rid)
                return
        # grid cells
        st = relics.relic_state()
        for slot, rect in enumerate(self._grid_rects):
            if not rect.contains(mp):
                continue
            occupant = st.grid[slot]
            if self._held:
                st.grid[slot] = self._held
                self._held = occupant  # swap (0 if empty)
                self._sfx()
                relics.save_relics()
            elif occupant:
                self._held = occupant
                st.grid[slot] = 0
                self._sfx()
                relics.save_relics()
            return
        # clicked empty space while holding -> return it
        if self._held:
            self._return_held()

    def draw(self) -> None:
        rl.clear_background(rl.BLACK)
        if self.state.pause_background is not None:
            self.state.pause_background.draw_pause_background()
        elif self._ground is not None:
            self._ground.draw(menu_ground_camera(self.state))
        _draw_screen_fade(self.state)

        res = require_runtime_resources(self.state)
        font = res.small_font
        sw = float(rl.get_screen_width())
        sh = float(rl.get_screen_height())
        scale = self._scale()
        shadows = self.state.config.display.shadows_enabled
        panel_tex = res.texture(TextureId.UI_MENU_PANEL)

        # --- panels ---------------------------------------------------
        pad = 24.0
        panel_h = min(sh - 150.0, 440.0)
        panel_y = 84.0
        left_w = 330.0
        right_w = relics.GRID_W * _CELL + (relics.GRID_W - 1) * _CELL_GAP + pad * 2.0
        total_w = left_w + right_w + 36.0
        left_x = (sw - total_w) * 0.5
        right_x = left_x + left_w + 36.0
        self._left_panel = Rect.from_pos_size(Vec2(left_x, panel_y), Vec2(left_w, panel_h))
        self._right_panel = Rect.from_pos_size(Vec2(right_x, panel_y), Vec2(right_w, panel_h))

        draw_classic_menu_panel(
            panel_tex, dst=rl.Rectangle(left_x, panel_y, left_w, panel_h), tint=rl.WHITE, shadow=shadows,
        )
        draw_classic_menu_panel(
            panel_tex, dst=rl.Rectangle(right_x, panel_y, right_w, panel_h), tint=rl.WHITE, shadow=shadows, flip_x=True,
        )

        title = "RELICS"
        draw_ui_text(res, title, Vec2(sw * 0.5 - self._w(res, title, scale) * 0.5, 40.0), scale=scale, color=_BLUE)
        hint = "click a relic to pick it up, click a grid cell to place it"
        draw_ui_text(res, hint, Vec2(sw * 0.5 - self._w(res, hint, scale) * 0.5, 58.0), scale=scale, color=_DIM)

        self._draw_inventory(res, scale, mp=Vec2(*self._mouse()))
        self._draw_grid(res, scale, mp=Vec2(*self._mouse()))

        # --- buttons -------------------------------------------------
        play_w = button_width(res, "Play", scale=scale, force_wide=True)
        back_w = button_width(res, "Back", scale=scale, force_wide=True)
        button_draw(res, self._back_btn, pos=self._back_pos(back_w), width=back_w, scale=scale)
        button_draw(res, self._play_btn, pos=self._play_pos(play_w), width=play_w, scale=scale)

        self._draw_sign(res)

        # --- held relic follows the cursor -------------------------
        if self._held:
            mx, my = self._mouse()
            rl.draw_rectangle(int(mx + 10), int(my + 10), int(_CELL), int(_CELL), _CELL_FILLED)
            rl.draw_rectangle_lines(int(mx + 10), int(my + 10), int(_CELL), int(_CELL), _BLUE)
            draw_ui_text(res, "+1", Vec2(mx + 10 + _CELL * 0.5 - 7.0, my + 10 + _CELL * 0.5 - 6.0), scale=scale, color=_BLUE)

        _draw_menu_cursor(self.state, resources=res, pulse_time=self._cursor_pulse)

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    # --- content -------------------------------------------------------

    def _draw_inventory(self, res, scale: float, *, mp: Vec2) -> None:
        p = self._left_panel
        x = p.x + 26.0
        y = p.y + 30.0
        w = p.w - 52.0
        draw_ui_text(res, "INVENTORY", Vec2(x, y), scale=scale, color=_BLUE)

        st = relics.relic_state()
        counts: dict[int, int] = {}
        for rid in st.owned:
            counts[rid] = counts.get(rid, 0) + 1

        self._inv_rects = []
        ry = y + 24.0
        for rid in sorted(counts):
            rect = Rect.from_pos_size(Vec2(x, ry), Vec2(w, 24.0))
            self._inv_rects.append((rect, rid))
            hovered = rect.contains(mp)
            rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.w), int(rect.h),
                              _CELL_BG_HOVER if hovered else _CELL_BG)
            rl.draw_rectangle_lines(int(rect.x), int(rect.y), int(rect.w), int(rect.h), _BLUE_DIM)
            name = relics.RELIC_NAME.get(rid, f"relic {rid}")
            draw_ui_text(res, name, Vec2(rect.x + 8.0, rect.y + 5.0), scale=scale, color=_WHITE)
            cnt = f"x{counts[rid]}"
            draw_ui_text(res, cnt, Vec2(rect.x + rect.w - self._w(res, cnt, scale) - 8.0, rect.y + 5.0),
                         scale=scale, color=_BLUE)
            ry += 28.0

        if not counts:
            draw_ui_text(res, "empty - kill monsters to find relics", Vec2(x, y + 28.0), scale=scale, color=_DIM)

        held_line = "holding: +1 Clip Size" if self._held else ""
        draw_ui_text(res, held_line, Vec2(x, p.y + p.h - 34.0), scale=scale, color=_BLUE)

    def _draw_grid(self, res, scale: float, *, mp: Vec2) -> None:
        p = self._right_panel
        gx = p.x + (p.w - (relics.GRID_W * _CELL + (relics.GRID_W - 1) * _CELL_GAP)) * 0.5
        gy = p.y + 44.0
        draw_ui_text(res, "RELIC GRID", Vec2(gx, p.y + 22.0), scale=scale, color=_BLUE)

        st = relics.relic_state()
        self._grid_rects = []
        for row in range(relics.GRID_H):
            for col in range(relics.GRID_W):
                slot = row * relics.GRID_W + col
                cx = gx + col * (_CELL + _CELL_GAP)
                cy = gy + row * (_CELL + _CELL_GAP)
                rect = Rect.from_pos_size(Vec2(cx, cy), Vec2(_CELL, _CELL))
                self._grid_rects.append(rect)
                filled = st.grid[slot] != 0
                hovered = rect.contains(mp)
                bg = _CELL_FILLED if filled else (_CELL_BG_HOVER if hovered else _CELL_BG)
                rl.draw_rectangle(int(cx), int(cy), int(_CELL), int(_CELL), bg)
                rl.draw_rectangle_lines(int(cx), int(cy), int(_CELL), int(_CELL), _BLUE if hovered else _BLUE_DIM)
                if filled:
                    draw_ui_text(res, "+1", Vec2(cx + _CELL * 0.5 - 7.0, cy + _CELL * 0.5 - 6.0),
                                 scale=scale, color=_BLUE)

        n = len(relics.placed_relic_ids())
        summary = f"run bonus:  +{n} clip size"
        draw_ui_text(res, summary, Vec2(gx, gy + relics.GRID_H * (_CELL + _CELL_GAP) + 6.0), scale=scale, color=_WHITE)

    def _draw_sign(self, res) -> None:
        screen_w = float(self.state.config.display.width)
        sign_scale, shift_x = MenuView._sign_layout_scale(int(screen_w))
        sign_pos = Vec2(
            screen_w + MENU_SIGN_POS_X_PAD,
            MENU_SIGN_POS_Y if screen_w > 900 else MENU_SIGN_POS_Y_SMALL,
        )
        sign = res.texture(TextureId.UI_SIGN_CRIMSON)
        rl.draw_texture_pro(
            sign,
            rl.Rectangle(0.0, 0.0, float(sign.width), float(sign.height)),
            rl.Rectangle(
                sign_pos.x + MENU_SIGN_OFFSET_X * sign_scale + shift_x,
                sign_pos.y + MENU_SIGN_OFFSET_Y * sign_scale,
                MENU_SIGN_WIDTH * sign_scale,
                MENU_SIGN_HEIGHT * sign_scale,
            ),
            rl.Vector2(0.0, 0.0),
            0.0,
            rl.WHITE,
        )

    # --- interaction helpers ---------------------------------------

    def _pick_from_inventory(self, relic_id: int) -> None:
        st = relics.relic_state()
        for i, rid in enumerate(st.owned):
            if rid == relic_id:
                self._held = st.owned.pop(i)
                self._sfx()
                relics.save_relics()
                return

    def _return_held(self) -> None:
        if not self._held:
            return
        relics.relic_state().owned.append(self._held)
        self._held = 0
        relics.save_relics()

    def _sfx(self) -> None:
        if self.state.audio is not None:
            play_sfx(self.state.audio, SfxId.UI_BUTTONCLICK)

    # --- layout helpers ------------------------------------------

    def _scale(self) -> float:
        return 1.0

    def _w(self, res, s: str, scale: float) -> float:
        from grim.fonts.small import measure_small_text_width

        return measure_small_text_width(res.small_font, s)

    def _mouse(self) -> tuple[float, float]:
        m = rl.get_mouse_position()
        return float(m.x), float(m.y)

    def _play_pos(self, width: float) -> Vec2:
        sh = float(rl.get_screen_height())
        sw = float(rl.get_screen_width())
        return Vec2(sw * 0.5 + 20.0, sh - 64.0)

    def _back_pos(self, width: float) -> Vec2:
        sh = float(rl.get_screen_height())
        sw = float(rl.get_screen_width())
        return Vec2(sw * 0.5 - width - 20.0, sh - 64.0)
