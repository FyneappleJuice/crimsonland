from __future__ import annotations

"""Not native: the pre-run relic inventory screen.

Shown when the player picks Survival. Left = the global relic inventory,
right = a 5x5 grid. Click an inventory relic to place it, click a placed relic
to take it back. PLAY starts Survival with every placed relic's mods active;
BACK returns to the menu.
"""

from grim.audio import play_sfx, update_audio
from grim.fonts.small import draw_small_text, measure_small_text_width
from grim.geom import Rect, Vec2
from grim.raylib_api import rl
from grim.sfx_map import SfxId

from ..game.types import GameState
from ..meta import relics
from .assets import require_runtime_resources
from .menu import _draw_menu_cursor

_BG = rl.Color(12, 12, 16, 255)
_PANEL = rl.Color(24, 24, 30, 255)
_CELL = rl.Color(34, 34, 42, 255)
_CELL_FILLED = rl.Color(70, 90, 120, 255)
_BORDER = rl.Color(90, 90, 110, 255)
_ACCENT = rl.Color(150, 200, 255, 255)
_TEXT = rl.Color(225, 227, 235, 255)
_DIM = rl.Color(150, 152, 162, 255)

_CELL_SIZE = 52.0
_CELL_GAP = 6.0


class RelicInventoryView:
    def __init__(self, state: GameState) -> None:
        self.state = state
        self._is_open = False
        self._pending_action: str | None = None
        self._cursor_pulse = 0.0
        self._inv_rows: list[Rect] = []
        self._inv_group_ids: list[int] = []
        self._grid_cells: list[Rect] = []
        self._play_rect = Rect.from_pos_size(Vec2(), Vec2())
        self._back_rect = Rect.from_pos_size(Vec2(), Vec2())

    # --- Screen protocol -------------------------------------------------

    def open(self) -> None:
        relics.init_relics(self.state.base_dir)
        relics.end_run()
        self._is_open = True
        self._pending_action = None
        self._cursor_pulse = 0.0

    def close(self) -> None:
        self._is_open = False

    def update(self, dt: float) -> None:
        if self.state.audio is not None:
            update_audio(self.state.audio, dt)
        self._cursor_pulse += min(dt, 0.1) * 1.1

        if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
            self._pending_action = "back_to_menu"
            return

        if not rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT):
            return
        m = rl.get_mouse_position()
        mp = Vec2(float(m.x), float(m.y))

        if self._play_rect.contains(mp):
            self._click_sfx()
            relics.begin_run()
            self._pending_action = "start_survival"
            return
        if self._back_rect.contains(mp):
            self._click_sfx()
            self._pending_action = "back_to_menu"
            return

        st = relics.relic_state()
        # inventory rows are grouped by relic id; _inv_rows[i] -> that group's id
        for i, rect in enumerate(self._inv_rows):
            if rect.contains(mp) and i < len(self._inv_group_ids):
                if relics.equip_from_owned(self._first_owned_index(self._inv_group_ids[i])):
                    self._click_sfx()
                return
        for slot, rect in enumerate(self._grid_cells):
            if rect.contains(mp) and st.grid[slot] != 0:
                if relics.unequip_slot(slot):
                    self._click_sfx()
                return

    def draw(self) -> None:
        rl.clear_background(_BG)
        res = require_runtime_resources(self.state)
        font = res.small_font
        sw = float(rl.get_screen_width())
        sh = float(rl.get_screen_height())

        self._text(font, "RELICS", Vec2(sw * 0.5 - measure_small_text_width(font, "RELICS") * 0.5, 24.0), _ACCENT)
        self._text(
            font,
            "place relics into the grid, then PLAY",
            Vec2(sw * 0.5 - measure_small_text_width(font, "place relics into the grid, then PLAY") * 0.5, 44.0),
            _DIM,
        )

        grid_w = relics.GRID_W * _CELL_SIZE + (relics.GRID_W - 1) * _CELL_GAP
        grid_h = relics.GRID_H * _CELL_SIZE + (relics.GRID_H - 1) * _CELL_GAP
        grid_x = sw - grid_w - 60.0
        grid_y = 90.0
        inv_x = 50.0
        inv_y = 90.0
        inv_w = grid_x - inv_x - 40.0

        self._draw_inventory(font, inv_x, inv_y, inv_w, sh)
        self._draw_grid(font, grid_x, grid_y)

        # buttons
        bw, bh = 140.0, 34.0
        by = sh - bh - 28.0
        self._back_rect = Rect.from_pos_size(Vec2(50.0, by), Vec2(bw, bh))
        self._play_rect = Rect.from_pos_size(Vec2(sw - bw - 60.0, by), Vec2(bw, bh))
        self._draw_button(font, self._back_rect, "BACK", _DIM)
        self._draw_button(font, self._play_rect, "PLAY", _ACCENT)

        _draw_menu_cursor(self.state, resources=res, pulse_time=self._cursor_pulse)

    def take_action(self) -> str | None:
        action = self._pending_action
        self._pending_action = None
        return action

    # --- drawing helpers ----------------------------------------------

    def _draw_inventory(self, font, x: float, y: float, w: float, sh: float) -> None:
        st = relics.relic_state()
        rl.draw_rectangle(int(x - 10), int(y - 10), int(w + 20), int(sh - y - 90), _PANEL)
        rl.draw_rectangle_lines(int(x - 10), int(y - 10), int(w + 20), int(sh - y - 90), _BORDER)
        self._text(font, "INVENTORY", Vec2(x, y - 2.0), _TEXT)

        counts: dict[int, int] = {}
        for rid in st.owned:
            counts[rid] = counts.get(rid, 0) + 1

        self._inv_group_ids: list[int] = sorted(counts)
        self._inv_rows = []
        row_h = 26.0
        ry = y + 20.0
        for rid in self._inv_group_ids:
            rect = Rect.from_pos_size(Vec2(x, ry), Vec2(w, row_h - 4.0))
            self._inv_rows.append(rect)
            hovered = rect.contains(Vec2(*self._mouse()))
            rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.w), int(rect.h), _CELL_FILLED if hovered else _CELL)
            rl.draw_rectangle_lines(int(rect.x), int(rect.y), int(rect.w), int(rect.h), _BORDER)
            name = relics.RELIC_NAME.get(rid, f"relic {rid}")
            self._text(font, f"{name}", Vec2(rect.x + 8.0, rect.y + 4.0), _TEXT)
            cnt = f"x{counts[rid]}"
            self._text(font, cnt, Vec2(rect.x + rect.w - measure_small_text_width(font, cnt) - 8.0, rect.y + 4.0), _ACCENT)
            ry += row_h

        if not self._inv_group_ids:
            self._text(font, "(empty - kill monsters to find relics)", Vec2(x, y + 24.0), _DIM)

    def _draw_grid(self, font, x: float, y: float) -> None:
        st = relics.relic_state()
        self._text(font, "RELIC GRID", Vec2(x, y - 22.0), _TEXT)
        self._grid_cells = []
        for row in range(relics.GRID_H):
            for col in range(relics.GRID_W):
                slot = row * relics.GRID_W + col
                cx = x + col * (_CELL_SIZE + _CELL_GAP)
                cy = y + row * (_CELL_SIZE + _CELL_GAP)
                rect = Rect.from_pos_size(Vec2(cx, cy), Vec2(_CELL_SIZE, _CELL_SIZE))
                self._grid_cells.append(rect)
                filled = st.grid[slot] != 0
                rl.draw_rectangle(int(cx), int(cy), int(_CELL_SIZE), int(_CELL_SIZE), _CELL_FILLED if filled else _CELL)
                rl.draw_rectangle_lines(int(cx), int(cy), int(_CELL_SIZE), int(_CELL_SIZE), _BORDER)
                if filled:
                    self._text(font, "+1", Vec2(cx + _CELL_SIZE * 0.5 - 7.0, cy + _CELL_SIZE * 0.5 - 6.0), _ACCENT)

        n = len(relics.placed_relic_ids())
        self._text(font, f"clip size: +{n}", Vec2(x, y + relics.GRID_H * (_CELL_SIZE + _CELL_GAP) + 4.0), _ACCENT)

    def _draw_button(self, font, rect: Rect, label: str, color: rl.Color) -> None:
        hovered = rect.contains(Vec2(*self._mouse()))
        rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.w), int(rect.h), _CELL_FILLED if hovered else _CELL)
        rl.draw_rectangle_lines(int(rect.x), int(rect.y), int(rect.w), int(rect.h), color)
        tx = rect.x + rect.w * 0.5 - measure_small_text_width(font, label) * 0.5
        self._text(font, label, Vec2(tx, rect.y + rect.h * 0.5 - 6.0), color)

    def _text(self, font, s: str, pos: Vec2, color: rl.Color) -> None:
        draw_small_text(font, s, Vec2(pos.x + 1.0, pos.y + 1.0), rl.Color(0, 0, 0, 200))
        draw_small_text(font, s, pos, color)

    def _mouse(self) -> tuple[float, float]:
        m = rl.get_mouse_position()
        return float(m.x), float(m.y)

    def _click_sfx(self) -> None:
        if self.state.audio is not None:
            play_sfx(self.state.audio, SfxId.UI_BUTTONCLICK)

    def _first_owned_index(self, relic_id: int) -> int:
        st = relics.relic_state()
        for i, rid in enumerate(st.owned):
            if rid == relic_id:
                return i
        return -1
