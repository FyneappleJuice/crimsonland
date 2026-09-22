from __future__ import annotations

"""Not native: layout for the secondary "run mod" choice panel, drawn beside
the classic perk-selection panel (see ui/perk_menu.py) at every level-up.
Reuses that module's shared drawing/hit-test helpers (draw_classic_menu_panel,
draw_ui_text, menu_item_hit_rect, draw_menu_item, UiButtonState/button_*) -
only the panel geometry here is new."""

import msgspec

from grim.geom import Rect, Vec2

from .layout import menu_widescreen_y_shift
from .perk_menu import PERK_MENU_ANIM_END_MS, PERK_MENU_ANIM_START_MS, PerkMenuLayout, ui_element_slide_x

RUN_MOD_MENU_TRANSITION_MS = PERK_MENU_ANIM_START_MS

# The perk panel's resting right edge (PerkMenuLayout's own panel_pos/panel_size
# defaults: -108 + 510 = 402) - the run-mod panel slides in from exactly this
# x, so it visually emerges from the perk panel's edge instead of from some
# unrelated point further right.
_PERK_PANEL_RIGHT_EDGE_X = PerkMenuLayout().panel_pos.x + PerkMenuLayout().panel_size.x

RUN_MOD_PANEL_ANCHOR_X = 40.0
RUN_MOD_PANEL_ANCHOR_Y = 40.0
RUN_MOD_TITLE_X = 8.0
RUN_MOD_TITLE_Y = 4.0
RUN_MOD_LIST_Y = 32.0
RUN_MOD_LIST_STEP = 20.0
RUN_MOD_DESC_X = 0.0
RUN_MOD_DESC_Y_AFTER_LIST = 20.0
RUN_MOD_BUTTON_X = 18.0
RUN_MOD_BUTTON_Y = 160.0


class RunModMenuLayout(msgspec.Struct):
    # To the right of the classic perk panel (ui/perk_menu.py's PerkMenuLayout
    # occupies x in [-108, 402] of the same raw-pixel UI space), same Y so the
    # two panels sit side by side, with a 40px gap for the connecting hardware.
    panel_pos: Vec2 = Vec2(442.0, 29.0)
    panel_size: Vec2 = Vec2(320.0, 220.0)


class RunModMenuComputedLayout(msgspec.Struct):
    panel: Rect
    title_pos: Vec2
    list_pos: Vec2
    list_step_y: float
    desc: Rect
    cancel_pos: Vec2


def run_mod_menu_panel_slide_x(t_ms: float, *, layout: RunModMenuLayout) -> float:
    """Slide in/out from exactly the perk panel's right edge (not a fixed
    off-screen offset), so the panel visually emerges from / retracts into
    the perk panel rather than from some unrelated point on screen."""

    width = layout.panel_pos.x - _PERK_PANEL_RIGHT_EDGE_X
    return ui_element_slide_x(
        t_ms,
        start_ms=PERK_MENU_ANIM_START_MS,
        end_ms=PERK_MENU_ANIM_END_MS,
        width=width,
        direction_flag=0,
    )


def run_mod_menu_compute_layout(
    layout: RunModMenuLayout,
    *,
    screen_w: float,
    origin: Vec2,
    scale: float,
    choice_count: int,
    panel_slide_x: float = 0.0,
) -> RunModMenuComputedLayout:
    layout_w = screen_w / scale if scale else screen_w
    widescreen_shift_y = menu_widescreen_y_shift(layout_w)
    panel_pos = layout.panel_pos + Vec2(panel_slide_x, widescreen_shift_y)
    panel = Rect.from_pos_size(origin + panel_pos * scale, layout.panel_size * scale)
    anchor_pos = Vec2(
        panel.x + RUN_MOD_PANEL_ANCHOR_X * scale,
        panel.y + RUN_MOD_PANEL_ANCHOR_Y * scale,
    )

    title_pos = anchor_pos.offset(dx=RUN_MOD_TITLE_X * scale, dy=RUN_MOD_TITLE_Y * scale)

    list_step_y = RUN_MOD_LIST_STEP
    list_pos = Vec2(anchor_pos.x, anchor_pos.y + RUN_MOD_LIST_Y * scale)

    desc_pos = Vec2(
        anchor_pos.x + RUN_MOD_DESC_X * scale,
        list_pos.y + choice_count * list_step_y * scale + RUN_MOD_DESC_Y_AFTER_LIST * scale,
    )
    cancel_pos = anchor_pos.offset(dx=RUN_MOD_BUTTON_X * scale, dy=RUN_MOD_BUTTON_Y * scale)
    desc_size = Vec2(
        max(0.0, panel.x + layout.panel_size.x * scale - desc_pos.x),
        max(0.0, cancel_pos.y - 12.0 * scale - desc_pos.y),
    )
    desc = Rect.from_pos_size(desc_pos, desc_size)

    return RunModMenuComputedLayout(
        panel=panel,
        title_pos=title_pos,
        list_pos=list_pos,
        list_step_y=list_step_y * scale,
        desc=desc,
        cancel_pos=cancel_pos,
    )
