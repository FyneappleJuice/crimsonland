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

from ..debug import debug_enabled
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
from ..ui.menu_panel import draw_classic_menu_panel, draw_menu_panel_hardware
from .transitions import _draw_screen_fade

_BLUE = rl.Color(*MENU_ITEM_RGB, 255)
_WHITE = rl.Color(235, 237, 245, 255)
_DIM = rl.Color(160, 162, 172, 255)

# Slot backgrounds reuse the native ui_indPanel plate (same texture the HUD
# stretches under bonus-timer/weapon-popup slots - see ui/hud.py) rather than
# flat rl.draw_rectangle fills, so the screen reads as the game's own UI.
_SLOT_TINT_IDLE = rl.Color(180, 186, 198, 130)
_SLOT_TINT_HOVER = rl.Color(255, 255, 255, 235)
_SLOT_TINT_FILLED = rl.Color(*MENU_ITEM_RGB, 235)

# Placement preview (held relic hovering the grid): green if it would fit at
# the hovered anchor, red if it wouldn't (collision or out of bounds).
_PREVIEW_OK = rl.Color(90, 230, 120, 255)
_PREVIEW_BAD = rl.Color(230, 90, 90, 255)

# Fixed content-layout constants (grid/inventory row fitting inside whatever
# panel rect is in effect). Not sliders - see _DBG_SLIDERS below for the
# panel-geometry knobs, which are the ones actually in flux right now.
_DEFAULT_CELL = 58.0
_DEFAULT_CELL_GAP = 0.0  # cells are neighbors - no gap between them
_DEFAULT_GRID_TOP = 54.0
_DEFAULT_HEADER_PAD = 38.0

# Panel-open slide-in, same 300ms native timing/easing the other classic-
# menu-panel screens use (see MenuView._ui_element_anim, reused below via
# screens/panels/base.py's PanelMenuView pattern) - left panel slides in
# from off-screen left, right panel from off-screen right, both settling
# into place together. Clicks are held off until it finishes.
_PANEL_SLIDE_MS = 300

# Panel geometry - each panel is defined directly by its own x, y, w, h
# (independent left/right corner control, no derived centering/gap math to
# fight with) - live-tunable in --debug via the on-screen sliders (see
# _DBG_SLIDERS / _update_debug_tuner / _draw_debug_tuner).
_DEFAULT_LEFT = (80.0, 180.0, 500.0, 420.0)  # x, y, w, h
_DEFAULT_RIGHT = (750.0, 180.0, 500.0, 420.0)

# (label, attr name, min, max) - every entry here gets a slider row.
# x/y allow negative values so a panel can be pushed fully off-screen (left
# edge past 0) rather than clamping at the screen boundary.
_DBG_SLIDERS: tuple[tuple[str, str, float, float], ...] = (
    ("left x", "_dbg_left_x", -400.0, 1200.0),
    ("left y", "_dbg_left_y", -400.0, 800.0),
    ("left w", "_dbg_left_w", 50.0, 900.0),
    ("left h", "_dbg_left_h", 50.0, 800.0),
    ("right x", "_dbg_right_x", -400.0, 1600.0),
    ("right y", "_dbg_right_y", -400.0, 800.0),
    ("right w", "_dbg_right_w", 50.0, 900.0),
    ("right h", "_dbg_right_h", 50.0, 800.0),
)
_DBG_ORIGIN = Vec2(16.0, 16.0)
_DBG_WIDTH = 220.0
_DBG_ROW_H = 26.0
_DBG_PANEL_W = 340.0


def _draw_slot_plate(tex: rl.Texture, rect: Rect, tint: rl.Color) -> None:
    src = rl.Rectangle(0.0, 0.0, float(tex.width), float(tex.height))
    dst = rl.Rectangle(rect.x, rect.y, rect.w, rect.h)
    rl.draw_texture_pro(tex, src, dst, rl.Vector2(0.0, 0.0), 0.0, tint)


def _draw_shape_plate(
    ind_panel: rl.Texture, origin: Vec2, w_cells: int, h_cells: int, cell: float, gap: float, tint: rl.Color,
) -> Rect:
    """One ind_panel plate per cell, tiled - not one plate stretched to fit
    the whole shape - so a 1x2 relic reads as two 1x1 cells stitched
    together instead of a smeared 1x1 texture. Returns the shape's overall
    bounding Rect (for hover outlines etc.)."""

    for dy in range(h_cells):
        for dx in range(w_cells):
            cx = origin.x + dx * (cell + gap)
            cy = origin.y + dy * (cell + gap)
            _draw_slot_plate(ind_panel, Rect.from_pos_size(Vec2(cx, cy), Vec2(cell, cell)), tint)
    w = w_cells * cell + (w_cells - 1) * gap
    h = h_cells * cell + (h_cells - 1) * gap
    return Rect.from_pos_size(origin, Vec2(w, h))


def _draw_wysiwyg_rect(r: Rect, color: rl.Color, *, fill: bool = False) -> None:
    """A pixel-exact border (optionally filled) with no texture stretching
    involved - used by the debug tuner to show the true slider-driven bounds,
    either standalone or overlaid on the real textured panel for comparison."""

    if fill:
        rl.draw_rectangle(int(r.x), int(r.y), int(r.w), int(r.h), rl.Color(color.r, color.g, color.b, 40))
    rl.draw_rectangle_lines_ex(rl.Rectangle(r.x, r.y, r.w, r.h), 2.0, color)


class RelicInventoryView:
    def __init__(self, state: GameState) -> None:
        self.state = state
        self._is_open = False
        self._pending_action: str | None = None
        self._cursor_pulse = 0.0
        self._ground: GroundRenderer | None = None

        self._timeline_ms: int = 0  # panel slide progress, see _PANEL_SLIDE_MS
        self._closing = False  # True = timeline is counting back down to 0 before _close_action fires
        self._close_action: str | None = None
        self._held: int = 0  # relic id currently on the cursor (0 = none)
        self._inv_rects: list[tuple[Rect, int]] = []  # (icon rect, relic id)
        # Grid geometry from the last draw() call, so update() can map a mouse
        # position to a (row, col) cell without keeping a 25-Rect list around.
        self._grid_gx = 0.0
        self._grid_gy = 0.0
        self._grid_cell = 0.0
        self._grid_gap = 0.0
        self._left_panel = Rect.from_pos_size(Vec2(), Vec2())
        self._right_panel = Rect.from_pos_size(Vec2(), Vec2())

        self._play_btn = UiButtonState("Play", force_wide=True)
        self._back_btn = UiButtonState("Back", force_wide=True)

        # --debug only: live panel-geometry tuner (sliders + numeric readout).
        # Each panel is its own independent x/y/w/h - see _DBG_SLIDERS.
        self._dbg_left_x, self._dbg_left_y, self._dbg_left_w, self._dbg_left_h = _DEFAULT_LEFT
        self._dbg_right_x, self._dbg_right_y, self._dbg_right_w, self._dbg_right_h = _DEFAULT_RIGHT
        self._dbg_active_slider: str | None = None
        self._dbg_hover_slider: str | None = None

    # --- Screen protocol -------------------------------------------------

    def open(self) -> None:
        relics.init_relics(self.state.base_dir)
        relics.end_run()
        self._ground = None if self.state.pause_background is not None else ensure_menu_ground(self.state)
        self._is_open = True
        self._pending_action = None
        self._cursor_pulse = 0.0
        self._timeline_ms = 0
        self._closing = False
        self._close_action = None
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

        if self._update_debug_tuner(mp):
            return

        if self._closing:
            # Panels/buttons are sliding back out - let the animation finish,
            # then hand the action to take_action() (no input while closing).
            self._timeline_ms = max(0, self._timeline_ms - int(dt_ms))
            if self._timeline_ms <= 0:
                self._pending_action = self._close_action
            return

        self._timeline_ms = min(_PANEL_SLIDE_MS, self._timeline_ms + int(dt_ms))
        if self._timeline_ms < _PANEL_SLIDE_MS:
            # Panels are still sliding in - hold off on clicks/hotkeys until
            # they settle, matching PanelMenuView._entry_enabled's gate on
            # the other classic-menu-panel screens.
            return

        if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
            if self._held:
                self._return_held()
            else:
                self._begin_close_transition("back_to_menu")
            return

        if rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_RIGHT):
            if self._held:
                self._return_held()
                return
            # Right-click a placed relic to unequip it straight back to the
            # inventory list, no need to pick it up onto the cursor first.
            cell = self._grid_cell_at(mp)
            if cell is not None:
                found = relics.placement_at(*cell)
                if found is not None:
                    idx, _placement = found
                    self._unequip_to_inventory(idx)
                return

        scale = self._scale()
        play_w = button_width(require_runtime_resources(self.state), "Play", scale=scale, force_wide=True)
        back_w = button_width(require_runtime_resources(self.state), "Back", scale=scale, force_wide=True)
        if button_update(self._back_btn, pos=self._back_pos(back_w), width=back_w, dt_ms=dt_ms, mouse=m, click=click):
            self._return_held()
            self._begin_close_transition("back_to_menu")
            return
        if button_update(self._play_btn, pos=self._play_pos(play_w), width=play_w, dt_ms=dt_ms, mouse=m, click=click):
            self._return_held()
            relics.begin_run()
            self._begin_close_transition("start_survival")
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

        # grid cells - a placement is one object spanning its whole shape, so
        # clicking any of its cells picks up the whole thing, and placing
        # anchors the held relic's top-left at the clicked cell.
        cell = self._grid_cell_at(mp)
        if cell is not None:
            row, col = cell
            if self._held:
                if relics.place_held_relic(self._held, row, col):
                    self._held = 0
                    self._sfx()
                return
            found = relics.placement_at(row, col)
            if found is not None:
                idx, _placement = found
                self._held = relics.remove_placement_to_held(idx) or 0
                self._sfx()
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
        ind_panel = res.texture(TextureId.UI_IND_PANEL)

        # --- panels ---------------------------------------------------
        debug = debug_enabled()

        # Each panel is its own independent rect while tuning (see _DBG_SLIDERS).
        left_x, left_y, left_w, left_h = self._dbg_left_x, self._dbg_left_y, self._dbg_left_w, self._dbg_left_h
        right_x, right_y, right_w, right_h = (
            self._dbg_right_x, self._dbg_right_y, self._dbg_right_w, self._dbg_right_h,
        )
        if not debug:
            # Slide both panels in from off-screen on open (left panel from
            # the left, right panel from the right), settling into place
            # over _PANEL_SLIDE_MS - skipped in --debug so the sliders stay
            # WYSIWYG accurate to the tuned rect.
            _, slide_l = MenuView._ui_element_anim(
                self, index=1, start_ms=_PANEL_SLIDE_MS, end_ms=0, width=left_w, direction_flag=0,
            )
            _, slide_r = MenuView._ui_element_anim(
                self, index=1, start_ms=_PANEL_SLIDE_MS, end_ms=0, width=right_w, direction_flag=1,
            )
            left_x += slide_l
            right_x += slide_r
        self._left_panel = Rect.from_pos_size(Vec2(left_x, left_y), Vec2(left_w, left_h))
        self._right_panel = Rect.from_pos_size(Vec2(right_x, right_y), Vec2(right_w, right_h))

        # border_scale=1.0 pins the frame's top/bottom border chrome to its
        # native thickness - without this, draw_classic_menu_panel ties border
        # thickness to dst.width, so widening the panel also stretched the
        # border art. trim_hardware=True crops out the dangling hinge-cable
        # (left) and loose cable/ring (bottom-right) baked into the texture
        # outside its own frame silhouette - without it, stretching to a
        # non-native width smears that hardware across the panel.
        draw_classic_menu_panel(
            panel_tex, dst=rl.Rectangle(left_x, left_y, left_w, left_h), tint=rl.WHITE, shadow=shadows,
            border_scale=1.0, trim_hardware=True,
        )
        draw_classic_menu_panel(
            panel_tex, dst=rl.Rectangle(right_x, right_y, right_w, right_h), tint=rl.WHITE, shadow=shadows,
            flip_x=True, border_scale=1.0, trim_hardware=True,
        )
        # The cable/hinge decoration trimmed out above, reattached as a fixed-
        # size accent: top-left on the left panel, top-right (mirrored) on the
        # right panel - undistorted regardless of how the panels are sized.
        draw_menu_panel_hardware(panel_tex, panel=rl.Rectangle(left_x, left_y, left_w, left_h))
        draw_menu_panel_hardware(panel_tex, panel=rl.Rectangle(right_x, right_y, right_w, right_h), flip_x=True)
        if debug:
            # Outline-only overlay of the exact slider-driven rect, drawn ON
            # TOP of the real textured panel, so you can see directly whether
            # the native art's visible edge lines up with the numbers or sits
            # inset from them (ui_menuPanel's border art isn't drawn flush to
            # its own bounding box - draw_classic_menu_panel only slices
            # vertically, so the texture's built-in edge padding stretches
            # with width instead of staying a fixed border).
            _draw_wysiwyg_rect(self._left_panel, rl.Color(255, 210, 60, 255))
            _draw_wysiwyg_rect(self._right_panel, rl.Color(255, 210, 60, 255))

        # Sit just above the panels, whatever their tuned y ends up being.
        title_y = min(left_y, right_y) - 46.0
        title = "RELICS"
        draw_ui_text(res, title, Vec2(sw * 0.5 - self._w(res, title, scale) * 0.5, title_y), scale=scale, color=_BLUE)
        hint = "click a relic to pick it up, click a grid cell to place it, right-click to unequip"
        draw_ui_text(res, hint, Vec2(sw * 0.5 - self._w(res, hint, scale) * 0.5, title_y + 20.0), scale=scale, color=_DIM)

        # While tuning panel geometry, keep the two panels blank (no relic
        # rows / grid cells) so the borders/corners are easy to read.
        if not debug:
            self._draw_inventory(
                res, scale, ind_panel=ind_panel, header_pad=_DEFAULT_HEADER_PAD, mp=Vec2(*self._mouse()),
            )
            self._draw_grid(
                res, scale, ind_panel=ind_panel, cell=_DEFAULT_CELL, gap=_DEFAULT_CELL_GAP,
                grid_top=_DEFAULT_GRID_TOP, header_pad=_DEFAULT_HEADER_PAD,
                mp=Vec2(*self._mouse()),
            )
        else:
            self._inv_rects = []

        # --- buttons -------------------------------------------------
        # Slide with the panels they sit nearest to - Back (left side of the
        # screen) with the left panel, Play (right side) with the right
        # panel - same _timeline_ms drives both the entrance (counting up in
        # update()) and, while _closing, the exit (counting back down).
        play_w = button_width(res, "Play", scale=scale, force_wide=True)
        back_w = button_width(res, "Back", scale=scale, force_wide=True)
        back_pos = self._back_pos(back_w)
        play_pos = self._play_pos(play_w)
        if not debug:
            _, slide_back = MenuView._ui_element_anim(
                self, index=1, start_ms=_PANEL_SLIDE_MS, end_ms=0, width=back_w, direction_flag=0,
            )
            _, slide_play = MenuView._ui_element_anim(
                self, index=1, start_ms=_PANEL_SLIDE_MS, end_ms=0, width=play_w, direction_flag=1,
            )
            back_pos = Vec2(back_pos.x + slide_back, back_pos.y)
            play_pos = Vec2(play_pos.x + slide_play, play_pos.y)
        button_draw(res, self._back_btn, pos=back_pos, width=back_w, scale=scale)
        button_draw(res, self._play_btn, pos=play_pos, width=play_w, scale=scale)

        self._draw_sign(res)

        # --- held relic follows the cursor -------------------------
        if self._held and not debug:
            mx, my = self._mouse()
            cell = _DEFAULT_CELL
            w_cells, h_cells = relics.relic_shape(self._held)
            held_rect = _draw_shape_plate(
                ind_panel, Vec2(mx + 10, my + 10), w_cells, h_cells, cell, _DEFAULT_CELL_GAP, _SLOT_TINT_FILLED,
            )
            label = relics.RELIC_LABEL.get(self._held, "?")
            label_w = self._w(res, label, scale)
            draw_ui_text(
                res, label,
                Vec2(held_rect.x + held_rect.w * 0.5 - label_w * 0.5, held_rect.y + held_rect.h * 0.5 - 6.0),
                scale=scale, color=_WHITE,
            )

        # Debug tuner draws BEFORE the cursor so the cursor sprite always
        # renders on top and stays visible while you're pointing at a slider.
        if debug:
            self._draw_debug_tuner(res, scale)

        _draw_menu_cursor(self.state, resources=res, pulse_time=self._cursor_pulse)

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    # --- content -------------------------------------------------------

    def _draw_inventory(
        self, res, scale: float, *, ind_panel: rl.Texture, header_pad: float, mp: Vec2,
    ) -> None:
        p = self._left_panel
        x = p.x + header_pad
        y = p.y + header_pad + 2.0
        draw_ui_text(res, "INVENTORY", Vec2(x, y), scale=scale, color=_BLUE)

        st = relics.relic_state()
        counts: dict[int, int] = {}
        for rid in st.owned:
            counts[rid] = counts.get(rid, 0) + 1

        cell = _DEFAULT_CELL
        row_gap = 12.0
        ry = y + 30.0  # top-left aligned, right under the header - not centered

        self._inv_rects = []
        for rid in sorted(counts):
            w_cells, h_cells = relics.relic_shape(rid)
            icon_w = w_cells * cell + (w_cells - 1) * _DEFAULT_CELL_GAP
            icon_h = h_cells * cell + (h_cells - 1) * _DEFAULT_CELL_GAP
            # The hover/click target is the relic's own shape-sized icon, not
            # a wide row spanning the panel - a 1x1 relic highlights a single
            # cell, a 1x2 highlights a 1x2 block, matching the grid.
            icon_rect = Rect.from_pos_size(Vec2(x, ry), Vec2(icon_w, icon_h))
            self._inv_rects.append((icon_rect, rid))
            hovered = icon_rect.contains(mp)
            _draw_shape_plate(
                ind_panel, Vec2(x, ry), w_cells, h_cells, cell, _DEFAULT_CELL_GAP,
                _SLOT_TINT_HOVER if hovered else _SLOT_TINT_IDLE,
            )
            if hovered:
                rl.draw_rectangle_lines_ex(rl.Rectangle(icon_rect.x, icon_rect.y, icon_w, icon_h), 2.0, _BLUE)
            label = relics.RELIC_LABEL.get(rid, "?")
            label_w = self._w(res, label, scale)
            draw_ui_text(
                res, label, Vec2(icon_rect.x + icon_w * 0.5 - label_w * 0.5, icon_rect.y + icon_h * 0.5 - 6.0),
                scale=scale, color=_WHITE,
            )

            text_y = ry + icon_h * 0.5 - 6.0
            name = relics.RELIC_NAME.get(rid, f"relic {rid}")
            draw_ui_text(res, name, Vec2(x + icon_w + 12.0, text_y), scale=scale, color=_WHITE)
            cnt = f"x{counts[rid]}"
            draw_ui_text(
                res, cnt, Vec2(p.x + p.w - header_pad - self._w(res, cnt, scale), text_y),
                scale=scale, color=_BLUE,
            )
            ry += icon_h + row_gap

        if not counts:
            draw_ui_text(res, "empty - kill monsters to find relics", Vec2(x, ry), scale=scale, color=_DIM)

        held_name = relics.RELIC_NAME.get(self._held, "")
        held_line = f"holding: {held_name}" if self._held else ""
        draw_ui_text(res, held_line, Vec2(x, p.y + p.h - 34.0), scale=scale, color=_BLUE)

    def _grid_cell_at(self, mp: Vec2) -> tuple[int, int] | None:
        """(row, col) under `mp`, or None - accounts for the gap dead zone
        between cells (currently 0, but kept general)."""

        pitch = self._grid_cell + self._grid_gap
        if pitch <= 0.0:
            return None
        rel_x = mp.x - self._grid_gx
        rel_y = mp.y - self._grid_gy
        if rel_x < 0.0 or rel_y < 0.0:
            return None
        col = int(rel_x // pitch)
        row = int(rel_y // pitch)
        if not (0 <= row < relics.GRID_H and 0 <= col < relics.GRID_W):
            return None
        if (rel_x - col * pitch) > self._grid_cell or (rel_y - row * pitch) > self._grid_cell:
            return None
        return row, col

    def _draw_grid(
        self, res, scale: float, *, ind_panel: rl.Texture, cell: float, gap: float, grid_top: float,
        header_pad: float, mp: Vec2,
    ) -> None:
        p = self._right_panel
        gx = p.x + (p.w - (relics.GRID_W * cell + (relics.GRID_W - 1) * gap)) * 0.5
        gy = p.y + grid_top
        self._grid_gx, self._grid_gy, self._grid_cell, self._grid_gap = gx, gy, cell, gap
        draw_ui_text(res, "RELIC GRID", Vec2(gx, p.y + header_pad - 8.0), scale=scale, color=_BLUE)

        st = relics.relic_state()
        hovered_cell = self._grid_cell_at(mp)

        # While holding a relic, hovering previews its whole footprint
        # anchored at the hovered cell (not just that one cell) - green if it
        # would fit there, red if it wouldn't (collision or out of bounds).
        preview_w = preview_h = 0
        can_place = False
        if self._held and hovered_cell is not None:
            preview_w, preview_h = relics.relic_shape(self._held)
            can_place = relics.fits(self._held, *hovered_cell)

        hovered_placement_idx: int | None = None
        if not self._held and hovered_cell is not None:
            found = relics.placement_at(*hovered_cell)
            if found is not None:
                hovered_placement_idx = found[0]

        covered: set[tuple[int, int]] = set()
        for placement in st.placements:
            covered.update(relics.occupied_cells(placement))

        # Empty 1x1 slots first (background grid).
        for row in range(relics.GRID_H):
            for col in range(relics.GRID_W):
                if (row, col) in covered:
                    continue
                cx = gx + col * (cell + gap)
                cy = gy + row * (cell + gap)
                is_hover = (not self._held) and hovered_cell == (row, col) and hovered_placement_idx is None
                tint = _SLOT_TINT_HOVER if is_hover else _SLOT_TINT_IDLE
                _draw_slot_plate(ind_panel, Rect.from_pos_size(Vec2(cx, cy), Vec2(cell, cell)), tint)
                if is_hover:
                    rl.draw_rectangle_lines_ex(rl.Rectangle(cx, cy, cell, cell), 2.0, _BLUE)

        # Placed relics as one merged block per placement, tiled cell-by-cell
        # (not one plate stretched over the whole footprint) - a 1x2 relic
        # highlights and reads as two 1x1 cells stitched together, not a
        # smeared 1x1 texture.
        for idx, placement in enumerate(st.placements):
            w_cells, h_cells = relics.relic_shape(placement.relic_id)
            cx = gx + placement.col * (cell + gap)
            cy = gy + placement.row * (cell + gap)
            block = _draw_shape_plate(ind_panel, Vec2(cx, cy), w_cells, h_cells, cell, gap, _SLOT_TINT_FILLED)
            if idx == hovered_placement_idx:
                rl.draw_rectangle_lines_ex(rl.Rectangle(block.x, block.y, block.w, block.h), 2.0, _BLUE)
            label = relics.RELIC_LABEL.get(placement.relic_id, "?")
            label_w = self._w(res, label, scale)
            draw_ui_text(
                res, label, Vec2(block.x + block.w * 0.5 - label_w * 0.5, block.y + block.h * 0.5 - 6.0),
                scale=scale, color=_WHITE,
            )

        if self._held and hovered_cell is not None:
            row, col = hovered_cell
            px = gx + col * (cell + gap)
            py = gy + row * (cell + gap)
            pw = preview_w * cell + (preview_w - 1) * gap
            ph = preview_h * cell + (preview_h - 1) * gap
            preview_color = _PREVIEW_OK if can_place else _PREVIEW_BAD
            rl.draw_rectangle(int(px), int(py), int(pw), int(ph), rl.Color(preview_color.r, preview_color.g, preview_color.b, 90))
            rl.draw_rectangle_lines_ex(rl.Rectangle(px, py, pw, ph), 2.0, preview_color)

        clip_id = int(relics.RelicId.CLIP_PLUS_1)
        fire_rate_id = int(relics.RelicId.FIRE_RATE_PLUS_5)
        clip_n = sum(1 for p in st.placements if p.relic_id == clip_id)
        fire_rate_n = sum(1 for p in st.placements if p.relic_id == fire_rate_id)
        parts = []
        if clip_n:
            parts.append(f"+{clip_n} clip size")
        if fire_rate_n:
            parts.append(f"+{fire_rate_n * 5}% fire rate")
        summary = "run bonus:  " + (", ".join(parts) if parts else "none")
        draw_ui_text(res, summary, Vec2(gx, gy + relics.GRID_H * (cell + gap) + 6.0), scale=scale, color=_WHITE)

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

    def _unequip_to_inventory(self, index: int) -> None:
        relic_id = relics.remove_placement_to_held(index)
        if not relic_id:
            return
        relics.relic_state().owned.append(relic_id)
        relics.save_relics()
        self._sfx()

    def _sfx(self) -> None:
        if self.state.audio is not None:
            play_sfx(self.state.audio, SfxId.UI_BUTTONCLICK)

    def _begin_close_transition(self, action: str) -> None:
        if self._closing:
            return
        self._sfx()
        self._closing = True
        self._close_action = action

    # --- debug panel-sizing tuner (--debug only) --------------------

    _DBG_READOUT_LINES = 6

    def _debug_slider_rows(self) -> tuple[float, float]:
        """Returns (x0, first_row_y) for the slider stack, shared by update/draw.
        Each row: label text at `y`, track at `y + 14`."""

        return _DBG_ORIGIN.x + 12.0, _DBG_ORIGIN.y + 30.0

    def _debug_panel_height(self) -> float:
        """Total backdrop height, shared by the hit-test and the draw call so
        they never drift apart."""

        _, first_row_y = self._debug_slider_rows()
        header_h = first_row_y - _DBG_ORIGIN.y
        sliders_h = len(_DBG_SLIDERS) * _DBG_ROW_H
        readout_h = 8.0 + self._DBG_READOUT_LINES * 16.0
        return header_h + sliders_h + readout_h + 10.0

    def _update_debug_tuner(self, mp: Vec2) -> bool:
        """Drag-handles the sliders; returns True if input was consumed so the
        normal relic click handling should skip this frame."""

        if not debug_enabled():
            self._dbg_active_slider = None
            self._dbg_hover_slider = None
            return False

        mouse_down = rl.is_mouse_button_down(rl.MouseButton.MOUSE_BUTTON_LEFT)
        just_pressed = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
        x0, y0 = self._debug_slider_rows()
        y = y0
        self._dbg_hover_slider = None
        for _label, attr, minv, maxv in _DBG_SLIDERS:
            # Full-row hit box (no gaps between rows) so grabbing a slider
            # doesn't require pixel-precise aim at the thin track itself.
            hit = Rect.from_top_left(Vec2(x0 - 8.0, y - 4.0), _DBG_WIDTH + 16.0, _DBG_ROW_H)
            if hit.contains(mp):
                self._dbg_hover_slider = attr
                if just_pressed:
                    self._dbg_active_slider = attr
            if self._dbg_active_slider == attr and mouse_down:
                t = max(0.0, min(1.0, (mp.x - x0) / _DBG_WIDTH))
                setattr(self, attr, minv + t * (maxv - minv))
            y += _DBG_ROW_H

        if not mouse_down:
            self._dbg_active_slider = None
        # Consume the click/drag whenever the mouse is anywhere over the tuner
        # panel, not just while a slider is actively grabbed - otherwise a
        # click that starts a drag on frame N but lands just outside a hit
        # box on frame N+1 would fall through to the relic grid underneath.
        over_panel = Rect.from_top_left(_DBG_ORIGIN, _DBG_PANEL_W, self._debug_panel_height()).contains(mp)
        return self._dbg_active_slider is not None or over_panel

    def _draw_debug_tuner(self, res, scale: float) -> None:
        x0, y0 = _DBG_ORIGIN.x, _DBG_ORIGIN.y
        lp, rp = self._left_panel, self._right_panel
        sw = float(rl.get_screen_width())
        right_edge = rp.x + rp.w
        fits = lp.x >= 0.0 and right_edge <= sw

        panel_h = self._debug_panel_height()
        rl.draw_rectangle(int(x0), int(y0), int(_DBG_PANEL_W), int(panel_h), rl.Color(10, 12, 16, 225))
        rl.draw_rectangle_lines(int(x0), int(y0), int(_DBG_PANEL_W), int(panel_h), _BLUE)

        draw_ui_text(res, "DEBUG TUNER  (drag sliders; click+drag anywhere on a row)", Vec2(x0 + 10.0, y0 + 6.0), scale=scale, color=_BLUE)

        slider_x0, y = self._debug_slider_rows()
        for label, attr, minv, maxv in _DBG_SLIDERS:
            value = float(getattr(self, attr))
            hovered = self._dbg_hover_slider == attr
            active = self._dbg_active_slider == attr
            track_y = y + 14.0
            t = (value - minv) / (maxv - minv) if maxv > minv else 0.0
            handle_x = slider_x0 + max(0.0, min(1.0, t)) * _DBG_WIDTH
            if active or hovered:
                rl.draw_rectangle(
                    int(x0 + 4.0), int(y - 4.0), int(_DBG_PANEL_W - 8.0), int(_DBG_ROW_H),
                    rl.Color(*MENU_ITEM_RGB, 45),
                )
            track_color = _BLUE if (active or hovered) else rl.Color(90, 95, 105, 220)
            rl.draw_rectangle(int(slider_x0), int(track_y), int(_DBG_WIDTH), 4, track_color)
            rl.draw_rectangle(int(handle_x - 5.0), int(track_y - 6.0), 10, 16, _BLUE if active else _WHITE)
            draw_ui_text(res, f"{label}: {value:.0f}", Vec2(slider_x0, y), scale=scale, color=_WHITE)
            y += _DBG_ROW_H

        y += 8.0

        def corners(r: Rect) -> tuple[str, str]:
            tl = f"TL=({r.x:.0f},{r.y:.0f})"
            tr = f"TR=({r.x + r.w:.0f},{r.y:.0f})"
            bl = f"BL=({r.x:.0f},{r.y + r.h:.0f})"
            br = f"BR=({r.x + r.w:.0f},{r.y + r.h:.0f})"
            return f"{tl}  {tr}", f"{bl}  {br}"

        l_top, l_bot = corners(lp)
        r_top, r_bot = corners(rp)
        lines = [
            f"screen w: {sw:.0f}   right edge: {right_edge:.0f}   fits: {'YES' if fits else 'NO - shrink/move a panel'}",
            f"LEFT   {l_top}",
            f"LEFT   {l_bot}",
            f"RIGHT  {r_top}",
            f"RIGHT  {r_bot}",
            f"mouse: {rl.get_mouse_position().x:.0f}, {rl.get_mouse_position().y:.0f}",
        ]
        for i, line in enumerate(lines):
            color = (rl.Color(120, 220, 140, 255) if fits else rl.Color(230, 90, 90, 255)) if i == 0 else _DIM
            draw_ui_text(res, line, Vec2(x0 + 10.0, y), scale=scale, color=color)
            y += 16.0

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
