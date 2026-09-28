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

from grim.assets import TextureId
from grim.geom import Vec2
from grim.raylib_api import rl

from ..creatures.rarity import AFFIX_BLURB, AFFIXES, RARITY_COLOR, AffixId
from ..meta.relics import RELIC_BLURB, RELIC_NAME, RelicId, debug_set_active_relics
from ..perks.ids import PerkId, perk_display_name
from ..perks.runtime.apply import perk_apply
from ..perks.runtime.counts import adjust_perk_count
from ..run_mods.ids import RunModId, run_mod_display_name
from ..run_mods.runtime.apply import run_mod_apply
from ..run_mods.runtime.counts import adjust_run_mod_count
from ..weapon_runtime.assign import weapon_assign_player
from ..weapon_runtime.fire_recipes import fireable_weapon_ids
from ..weapons import WeaponId, weapon_display_name
from .menu_panel import MENU_PANEL_DST_BOTTOM_H, MENU_PANEL_DST_TOP_H, draw_classic_menu_panel, draw_menu_panel_hardware

_TAB_PERKS = 0
_TAB_RELICS = 1
_TAB_RUN_MODS = 2
_TAB_WEAPONS = 3
_TAB_MONSTER_MODS = 4
_TAB_LABELS = ("Perks", "Relics", "Run Mods", "Weapons", "Monster Mods")

# Not native: Monster Mods tab - tier picked for the NEXT F7/F8 sandbox
# spawn (see modes/maps_mode.py), not a live per-player stat like the other
# tabs. Index lines up with creatures/rarity.py's own tier ints (0=Normal).
_TIER_LABELS = ("Normal", "Tainted", "Mutated", "Apex")
_TIER_BUTTON_H = 22.0
_TIER_ROW_EXTRA_H = _TIER_BUTTON_H + 8.0

# Wide enough for 5 tabs (including the longest label, "Monster Mods") to
# each get a comfortable slot without crowding or overflowing their own tab
# rect.
_PANEL_WIDTH = 480.0
_PANEL_TOP = 60.0
_TAB_HEIGHT = 26.0
_ROW_HEIGHT = 20.0
_PANEL_MARGIN = 16.0

_TOOLTIP_MAX_WIDTH = 260.0
_TOOLTIP_LINE_H = 14.0
_TOOLTIP_PAD = 8.0
_TOOLTIP_BG = rl.Color(10, 12, 18, 235)
_TOOLTIP_BORDER = rl.Color(120, 130, 150, 255)
_TOOLTIP_TITLE_COLOR = rl.Color(230, 220, 160, 255)
_TOOLTIP_TEXT_COLOR = rl.Color(220, 225, 235, 255)

# draw_classic_menu_panel ties its border-chrome thickness to dst.width when
# no explicit border_scale is given (see menu_panel.py) - same scaling this
# panel's own width needs so its tab bar/rows never start under the frame art.
_PANEL_BORDER_SCALE = _PANEL_WIDTH / 510.0
_PANEL_TOP_CHROME_H = MENU_PANEL_DST_TOP_H * _PANEL_BORDER_SCALE
_PANEL_BOTTOM_CHROME_H = MENU_PANEL_DST_BOTTOM_H * _PANEL_BORDER_SCALE

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
        # Monster Mods tab selection, applied to the next F7 (dummy) / F8
        # (stationary monster) sandbox spawn (see modes/maps_mode.py) - not
        # live player/game state like the other four tabs.
        self.monster_mod_tier: int = 0
        self.monster_mod_affixes: set[int] = set()

    def toggle(self) -> None:
        self.open = not self.open

    def _panel_rect(self, screen_w: float, screen_h: float) -> tuple[float, float, float, float]:
        x = screen_w - _PANEL_WIDTH - _PANEL_MARGIN
        y = _PANEL_TOP
        h = screen_h - _PANEL_TOP - _PANEL_MARGIN
        return x, y, _PANEL_WIDTH, h

    def _content_top(self, y: float) -> float:
        """Y below the panel's own top border-chrome art, where the tab bar
        starts - drawing tabs/rows at the bare panel's `y` would draw them
        under the frame."""

        return y + _PANEL_TOP_CHROME_H

    def _content_bottom(self, y: float, h: float) -> float:
        return y + h - _PANEL_BOTTOM_CHROME_H

    def _extra_top_offset(self) -> float:
        """Extra vertical space the Monster Mods tab's tier-picker row needs
        above the regular row list - zero for every other tab."""

        return _TIER_ROW_EXTRA_H if self.tab == _TAB_MONSTER_MODS else 0.0

    def _visible_row_count(self, content_h: float) -> int:
        rows_top = _TAB_HEIGHT + 12.0 + self._extra_top_offset()
        return max(1, int((content_h - rows_top - 10.0) // _ROW_HEIGHT))

    def _current_ids(self) -> list[int]:
        if self.tab == _TAB_PERKS:
            return [int(p) for p in PerkId]
        if self.tab == _TAB_RELICS:
            return [int(r) for r in RelicId]
        if self.tab == _TAB_WEAPONS:
            return [int(w) for w in fireable_weapon_ids()]
        if self.tab == _TAB_MONSTER_MODS:
            return [int(a) for a in AffixId]
        return [int(r) for r in RunModId]

    def _row_label(self, entry_id: int) -> str:
        if self.tab == _TAB_PERKS:
            return perk_display_name(PerkId(entry_id))
        if self.tab == _TAB_RELICS:
            return RELIC_NAME.get(entry_id, f"relic {entry_id}")
        if self.tab == _TAB_WEAPONS:
            return weapon_display_name(WeaponId(entry_id))
        if self.tab == _TAB_MONSTER_MODS:
            spec = AFFIXES.get(entry_id)
            return spec.label if spec is not None else f"affix {entry_id}"
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
        if self.tab == _TAB_MONSTER_MODS:
            return "ON" if entry_id in self.monster_mod_affixes else ""
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
        elif self.tab == _TAB_MONSTER_MODS:
            self.monster_mod_affixes.add(entry_id)
        else:
            run_mod_apply(players, RunModId(entry_id))

    def _remove(self, entry_id: int, *, players, state) -> None:
        """Best-effort: decrementing perk_counts/run_mod_counts undoes
        anything read live off those counts each tick (the vast majority),
        but won't undo a perk whose apply_handler did an irreversible
        one-shot mutation (an instant heal, say) at the moment it was
        granted - there's no "undo" for those, just fewer future ticks of
        the ongoing effect."""
        if self.tab == _TAB_MONSTER_MODS:
            self.monster_mod_affixes.discard(entry_id)
            return
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

    def _wrap_text(self, mode, text: str, *, max_width: float) -> list[str]:
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or mode._ui_text_width(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _draw_title_blurb_tooltip(
        self, mode, *, title: str, blurb: str, anchor_x: float, anchor_y: float, screen_w: float, screen_h: float,
    ) -> None:
        """Hover tooltip: a bold title line + a wrapped mechanical blurb below
        it. Anchored to the LEFT of the panel (which sits at the screen's
        right edge) and clamped to stay fully on-screen either way."""

        if not blurb:
            return
        lines = [title, *self._wrap_text(mode, blurb, max_width=_TOOLTIP_MAX_WIDTH)]
        box_w = _TOOLTIP_MAX_WIDTH + _TOOLTIP_PAD * 2.0
        box_h = len(lines) * _TOOLTIP_LINE_H + _TOOLTIP_PAD * 2.0

        box_x = anchor_x - _TOOLTIP_PAD * 2.0 - box_w
        box_x = max(4.0, min(box_x, screen_w - box_w - 4.0))
        box_y = max(4.0, min(anchor_y, screen_h - box_h - 4.0))

        rl.draw_rectangle(int(box_x), int(box_y), int(box_w), int(box_h), _TOOLTIP_BG)
        rl.draw_rectangle_lines(int(box_x), int(box_y), int(box_w), int(box_h), _TOOLTIP_BORDER)

        ty = box_y + _TOOLTIP_PAD
        for i, line in enumerate(lines):
            color = _TOOLTIP_TITLE_COLOR if i == 0 else _TOOLTIP_TEXT_COLOR
            mode._draw_ui_text(line, Vec2(box_x + _TOOLTIP_PAD, ty), color)
            ty += _TOOLTIP_LINE_H

    def _draw_affix_tooltip(
        self, mode, *, entry_id: int, anchor_x: float, anchor_y: float, screen_w: float, screen_h: float,
    ) -> None:
        """Hover tooltip for a Monster Mods row - explains what the modifier
        actually does, since the name alone often doesn't say."""

        spec = AFFIXES.get(entry_id)
        if spec is None:
            return
        self._draw_title_blurb_tooltip(
            mode,
            title=spec.label,
            blurb=AFFIX_BLURB.get(entry_id, ""),
            anchor_x=anchor_x, anchor_y=anchor_y, screen_w=screen_w, screen_h=screen_h,
        )

    def _draw_relic_tooltip(
        self, mode, *, entry_id: int, anchor_x: float, anchor_y: float, screen_w: float, screen_h: float,
    ) -> None:
        """Hover tooltip for a Relics row - same shape as the Monster Mods
        one, explaining what the relic actually does."""

        self._draw_title_blurb_tooltip(
            mode,
            title=RELIC_NAME.get(entry_id, f"relic {entry_id}"),
            blurb=RELIC_BLURB.get(entry_id, ""),
            anchor_x=anchor_x, anchor_y=anchor_y, screen_w=screen_w, screen_h=screen_h,
        )

    def monster_mod_selection(self) -> tuple[int, tuple[int, ...]]:
        """(tier, affixes) currently picked on the Monster Mods tab - read by
        modes/maps_mode.py's F7/F8 spawn handlers."""

        return self.monster_mod_tier, tuple(sorted(self.monster_mod_affixes))

    def handle_input(self, *, players, state, creatures) -> None:
        if not self.open:
            return

        screen_w = float(rl.get_screen_width())
        screen_h = float(rl.get_screen_height())
        x, y, w, h = self._panel_rect(screen_w, screen_h)
        content_y = self._content_top(y)
        content_bottom = self._content_bottom(y, h)
        mouse = rl.get_mouse_position()

        for i, label in enumerate(_TAB_LABELS):
            tab_w = w / len(_TAB_LABELS)
            tab_x = x + tab_w * i
            if (
                tab_x <= mouse.x <= tab_x + tab_w
                and content_y <= mouse.y <= content_y + _TAB_HEIGHT
                and rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
            ):
                self.tab = i
                self.scroll_rows = 0

        wheel = rl.get_mouse_wheel_move()
        if wheel != 0.0 and x <= mouse.x <= x + w and y <= mouse.y <= y + h:
            self.scroll_rows = max(0, self.scroll_rows - int(wheel))

        ids = self._current_ids()
        visible = self._visible_row_count(content_bottom - content_y)
        max_scroll = max(0, len(ids) - visible)
        self.scroll_rows = min(self.scroll_rows, max_scroll)

        left_click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_LEFT)
        right_click = rl.is_mouse_button_pressed(rl.MouseButton.MOUSE_BUTTON_RIGHT)
        if not (left_click or right_click):
            return

        if self.tab == _TAB_MONSTER_MODS and left_click:
            tier_y = content_y + _TAB_HEIGHT + 6.0
            tier_w = w / len(_TIER_LABELS)
            for tier, label in enumerate(_TIER_LABELS):
                tier_x = x + tier_w * tier
                if tier_x <= mouse.x <= tier_x + tier_w and tier_y <= mouse.y <= tier_y + _TIER_BUTTON_H:
                    self.monster_mod_tier = tier
                    return

        rows_top = content_y + _TAB_HEIGHT + 12.0 + self._extra_top_offset()
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
        content_y = self._content_top(y)
        content_bottom = self._content_bottom(y, h)

        # Real Crimsonland bordered panel art (borders + connecting rods),
        # not a flat rectangle - same primitive perk_history_panel.py uses.
        # trim_hardware=True crops the dangling hinge-cable baked into the
        # texture outside its own frame silhouette (would otherwise smear
        # across a panel this far from the native ~510px design width); the
        # cable+plug accent comes back via draw_menu_panel_hardware below,
        # undistorted, flipped since this panel sits at the screen's right edge.
        panel_tex = mode.render_resources.resources.texture(TextureId.UI_MENU_PANEL)
        panel_dst = rl.Rectangle(x, y, w, h)
        draw_classic_menu_panel(panel_tex, dst=panel_dst, flip_x=True, trim_hardware=True)
        draw_menu_panel_hardware(panel_tex, panel=panel_dst, flip_x=True, scale=0.3)

        tab_w = w / len(_TAB_LABELS)
        for i, label in enumerate(_TAB_LABELS):
            tab_x = x + tab_w * i
            bg = _TAB_BG_ACTIVE if i == self.tab else _TAB_BG
            rl.draw_rectangle(int(tab_x), int(content_y), int(tab_w), int(_TAB_HEIGHT), bg)
            mode._draw_ui_text(label, Vec2(tab_x + 8.0, content_y + 6.0), _TEXT_COLOR, scale=0.85)

        if self.tab == _TAB_MONSTER_MODS:
            tier_y = content_y + _TAB_HEIGHT + 6.0
            tier_w = w / len(_TIER_LABELS)
            for tier, label in enumerate(_TIER_LABELS):
                tier_x = x + tier_w * tier
                active = tier == self.monster_mod_tier
                bg = _TAB_BG_ACTIVE if active else _TAB_BG
                rl.draw_rectangle(int(tier_x + 1), int(tier_y), int(tier_w - 2), int(_TIER_BUTTON_H), bg)
                r, g, b = RARITY_COLOR.get(tier, (225, 230, 240))
                mode._draw_ui_text(
                    label, Vec2(tier_x + 6.0, tier_y + 4.0), rl.Color(r, g, b, 255), scale=0.7,
                )

        ids = self._current_ids()
        visible = self._visible_row_count(content_bottom - content_y)
        rows_top = content_y + _TAB_HEIGHT + 12.0 + self._extra_top_offset()
        mouse = rl.get_mouse_position()

        hovered_affix_id = None
        hovered_relic_id = None
        hovered_tooltip_row_y = 0.0
        for row_i, entry_id in enumerate(ids[self.scroll_rows : self.scroll_rows + visible]):
            row_y = rows_top + row_i * _ROW_HEIGHT
            hovered = row_y <= mouse.y <= row_y + _ROW_HEIGHT and x <= mouse.x <= x + w
            rl.draw_rectangle(int(x + 2), int(row_y), int(w - 4), int(_ROW_HEIGHT - 1), _ROW_BG_HOVER if hovered else _ROW_BG)
            label = self._row_label(entry_id)
            mode._draw_ui_text(label, Vec2(x + 6.0, row_y + 3.0), _TEXT_COLOR, scale=0.75)
            count_text = self._row_count_text(entry_id, player=player)
            if count_text:
                mode._draw_ui_text(count_text, Vec2(x + w - 46.0, row_y + 3.0), _COUNT_COLOR, scale=0.75)
            if hovered and self.tab == _TAB_MONSTER_MODS:
                hovered_affix_id = entry_id
                hovered_tooltip_row_y = row_y
            elif hovered and self.tab == _TAB_RELICS:
                hovered_relic_id = entry_id
                hovered_tooltip_row_y = row_y

        # Not native: hint text moved from below the panel (which could run
        # past the bottom of the screen with little/no margin left) into the
        # panel's own bottom border-chrome strip - guaranteed on-screen since
        # the panel itself always is.
        if self.tab == _TAB_WEAPONS:
            hint = "LMB equip  RMB reset to Pistol  wheel scroll"
        elif self.tab == _TAB_MONSTER_MODS:
            hint = "Pick a tier + mods, F7/F8 to spawn  (Normal = no mods)"
        else:
            hint = "LMB add  RMB remove  wheel scroll  (perk/run-mod remove is best-effort)"
        mode._draw_ui_text(hint, Vec2(x + 6.0, content_bottom + 6.0), _HINT_COLOR, scale=0.6)

        if hovered_affix_id is not None:
            self._draw_affix_tooltip(
                mode,
                entry_id=hovered_affix_id,
                anchor_x=x,
                anchor_y=hovered_tooltip_row_y,
                screen_w=screen_w,
                screen_h=screen_h,
            )
        elif hovered_relic_id is not None:
            self._draw_relic_tooltip(
                mode,
                entry_id=hovered_relic_id,
                anchor_x=x,
                anchor_y=hovered_tooltip_row_y,
                screen_w=screen_w,
                screen_h=screen_h,
            )


__all__ = ["SandboxDebugPanel"]
