from __future__ import annotations

"""Not native: sandbox mode (modes/maps_mode.py) debug panel.

A mouse-driven panel listing every PerkId / RelicId / RunModId with a
per-row Add/Remove, instead of only rolling them through the normal random
level-up choice screen. Kept deliberately simple (plain rectangles + small
text, immediate-mode hit-testing) rather than reusing perk_menu.py's
animated button widgets - a debug tool doesn't need the same visual polish,
and 97 PerkIds is a lot of persisted per-row animation state to manage for
no real benefit here.

Left-click a row: add one. Right-click a row: remove one (perks/run mods
only - see _remove note below). Mouse wheel: scroll the current tab.
"""

from grim.geom import Vec2
from grim.raylib_api import rl

from ..meta.relics import RELIC_NAME, RelicId, debug_set_active_relics
from ..perks.ids import PerkId, perk_display_name
from ..perks.runtime.apply import perk_apply
from ..perks.runtime.counts import adjust_perk_count
from ..run_mods.ids import RunModId, run_mod_display_name
from ..run_mods.runtime.apply import run_mod_apply
from ..run_mods.runtime.counts import adjust_run_mod_count
from ..weapon_runtime.assign import weapon_assign_player
from ..weapon_runtime.fire_recipes import fireable_weapon_ids
from ..weapons import WeaponId, weapon_display_name

_TAB_PERKS = 0
_TAB_RELICS = 1
_TAB_RUN_MODS = 2
_TAB_WEAPONS = 3
_TAB_LABELS = ("Perks", "Relics", "Run Mods", "Weapons")

_PANEL_WIDTH = 340.0
_PANEL_TOP = 60.0
_TAB_HEIGHT = 26.0
_ROW_HEIGHT = 20.0
_PANEL_MARGIN = 16.0

_BG = rl.Color(15, 18, 26, 235)
_TAB_BG = rl.Color(35, 40, 55, 255)
_TAB_BG_ACTIVE = rl.Color(60, 90, 130, 255)
_ROW_BG = rl.Color(28, 32, 44, 200)
_ROW_BG_HOVER = rl.Color(45, 55, 75, 220)
_TEXT_COLOR = rl.Color(225, 230, 240, 255)
_COUNT_COLOR = rl.Color(140, 220, 150, 255)
_HINT_COLOR = rl.Color(160, 170, 190, 220)


class SandboxDebugPanel:
    def __init__(self) -> None:
        self.open = False
        self.tab = _TAB_PERKS
        self.scroll_rows = 0
        # Relics have no per-count stat (they're either active for the
        # session or they aren't) - tracked here, not on PlayerState.
        self.active_relic_ids: set[int] = set()

    def toggle(self) -> None:
        self.open = not self.open

    def _panel_rect(self, screen_w: float, screen_h: float) -> tuple[float, float, float, float]:
        x = screen_w - _PANEL_WIDTH - _PANEL_MARGIN
        y = _PANEL_TOP
        h = screen_h - _PANEL_TOP - _PANEL_MARGIN
        return x, y, _PANEL_WIDTH, h

    def _visible_row_count(self, panel_h: float) -> int:
        rows_top = _TAB_HEIGHT + 12.0
        return max(1, int((panel_h - rows_top - 10.0) // _ROW_HEIGHT))

    def _current_ids(self) -> list[int]:
        if self.tab == _TAB_PERKS:
            return [int(p) for p in PerkId]
        if self.tab == _TAB_RELICS:
            return [int(r) for r in RelicId]
        if self.tab == _TAB_WEAPONS:
            return [int(w) for w in fireable_weapon_ids()]
        return [int(r) for r in RunModId]

    def _row_label(self, entry_id: int) -> str:
        if self.tab == _TAB_PERKS:
            return perk_display_name(PerkId(entry_id))
        if self.tab == _TAB_RELICS:
            return RELIC_NAME.get(entry_id, f"relic {entry_id}")
        if self.tab == _TAB_WEAPONS:
            return weapon_display_name(WeaponId(entry_id))
        return run_mod_display_name(RunModId(entry_id))

    def _row_count_text(self, entry_id: int, *, player) -> str:
        if self.tab == _TAB_PERKS:
            counts = player.perk_counts
            n = counts[entry_id] if 0 <= entry_id < len(counts) else 0
            return f"x{n}" if n else ""
        if self.tab == _TAB_RELICS:
            return "ON" if entry_id in self.active_relic_ids else ""
        if self.tab == _TAB_WEAPONS:
            return "EQUIPPED" if int(player.weapon.weapon_id) == entry_id else ""
        counts = player.run_mod_counts
        n = counts[entry_id] if 0 <= entry_id < len(counts) else 0
        return f"x{n}" if n else ""

    def _add(self, entry_id: int, *, players, state, creatures) -> None:
        if self.tab == _TAB_PERKS:
            perk_apply(state, players, PerkId(entry_id), creatures=creatures)
        elif self.tab == _TAB_RELICS:
            self.active_relic_ids.add(entry_id)
            debug_set_active_relics(sorted(self.active_relic_ids))
        elif self.tab == _TAB_WEAPONS:
            if players:
                weapon_assign_player(players[0], WeaponId(entry_id), state=state)
        else:
            run_mod_apply(players, RunModId(entry_id))

    def _remove(self, entry_id: int, *, players, state) -> None:
        """Best-effort: decrementing perk_counts/run_mod_counts undoes
        anything read live off those counts each tick (the vast majority),
        but won't undo a perk whose apply_handler did an irreversible
        one-shot mutation (an instant heal, say) at the moment it was
        granted - there's no "undo" for those, just fewer future ticks of
        the ongoing effect."""
        owner = players[0] if players else None
        if owner is None:
            return
        if self.tab == _TAB_PERKS:
            if owner.perk_counts[entry_id] > 0:
                adjust_perk_count(owner, PerkId(entry_id), amount=-1)
        elif self.tab == _TAB_RELICS:
            self.active_relic_ids.discard(entry_id)
            debug_set_active_relics(sorted(self.active_relic_ids))
        elif self.tab == _TAB_WEAPONS:
            # "Remove" doesn't quite apply to a single equipped weapon -
            # right-click just resets back to the starting Pistol instead.
            weapon_assign_player(owner, WeaponId.PISTOL, state=state)
        else:
            if owner.run_mod_counts[entry_id] > 0:
                adjust_run_mod_count(owner, RunModId(entry_id), amount=-1)

    def handle_input(self, *, players, state, creatures) -> None:
        if not self.open:
            return

        screen_w = float(rl.get_screen_width())
        screen_h = float(rl.get_screen_height())
        x, y, w, h = self._panel_rect(screen_w, screen_h)
        mouse = rl.get_mouse_position()

        for i, label in enumerate(_TAB_LABELS):
            tab_w = w / len(_TAB_LABELS)
            tab_x = x + tab_w * i
            if (
                tab_x <= mouse.x <= tab_x + tab_w
                and y <= mouse.y <= y + _TAB_HEIGHT
                and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
            ):
                self.tab = i
                self.scroll_rows = 0

        wheel = rl.get_mouse_wheel_move()
        if wheel != 0.0 and x <= mouse.x <= x + w and y <= mouse.y <= y + h:
            self.scroll_rows = max(0, self.scroll_rows - int(wheel))

        ids = self._current_ids()
        visible = self._visible_row_count(h)
        max_scroll = max(0, len(ids) - visible)
        self.scroll_rows = min(self.scroll_rows, max_scroll)

        left_click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
        right_click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_RIGHT)
        if not (left_click or right_click):
            return

        rows_top = y + _TAB_HEIGHT + 12.0
        for row_i, entry_id in enumerate(ids[self.scroll_rows : self.scroll_rows + visible]):
            row_y = rows_top + row_i * _ROW_HEIGHT
            if row_y <= mouse.y <= row_y + _ROW_HEIGHT and x <= mouse.x <= x + w:
                if left_click:
                    self._add(entry_id, players=players, state=state, creatures=creatures)
                elif right_click:
                    self._remove(entry_id, players=players, state=state)
                break

    def draw(self, mode) -> None:
        if not self.open:
            return
        players = mode.sim_world.players
        if not players:
            return
        player = players[0]

        screen_w = float(rl.get_screen_width())
        screen_h = float(rl.get_screen_height())
        x, y, w, h = self._panel_rect(screen_w, screen_h)

        rl.draw_rectangle(int(x), int(y), int(w), int(h), _BG)
        rl.draw_rectangle_lines(int(x), int(y), int(w), int(h), rl.Color(90, 100, 120, 255))

        tab_w = w / len(_TAB_LABELS)
        for i, label in enumerate(_TAB_LABELS):
            tab_x = x + tab_w * i
            bg = _TAB_BG_ACTIVE if i == self.tab else _TAB_BG
            rl.draw_rectangle(int(tab_x), int(y), int(tab_w), int(_TAB_HEIGHT), bg)
            mode._draw_ui_text(label, Vec2(tab_x + 8.0, y + 6.0), _TEXT_COLOR, scale=0.85)

        ids = self._current_ids()
        visible = self._visible_row_count(h)
        rows_top = y + _TAB_HEIGHT + 12.0
        mouse = rl.get_mouse_position()

        for row_i, entry_id in enumerate(ids[self.scroll_rows : self.scroll_rows + visible]):
            row_y = rows_top + row_i * _ROW_HEIGHT
            hovered = row_y <= mouse.y <= row_y + _ROW_HEIGHT and x <= mouse.x <= x + w
            rl.draw_rectangle(int(x + 2), int(row_y), int(w - 4), int(_ROW_HEIGHT - 1), _ROW_BG_HOVER if hovered else _ROW_BG)
            label = self._row_label(entry_id)
            mode._draw_ui_text(label, Vec2(x + 6.0, row_y + 3.0), _TEXT_COLOR, scale=0.75)
            count_text = self._row_count_text(entry_id, player=player)
            if count_text:
                mode._draw_ui_text(count_text, Vec2(x + w - 46.0, row_y + 3.0), _COUNT_COLOR, scale=0.75)

        hint = (
            "LMB equip  RMB reset to Pistol  wheel scroll"
            if self.tab == _TAB_WEAPONS
            else "LMB add  RMB remove  wheel scroll  (perk/run-mod remove is best-effort)"
        )
        mode._draw_ui_text(hint, Vec2(x, y + h + 4.0), _HINT_COLOR, scale=0.6)


__all__ = ["SandboxDebugPanel"]
