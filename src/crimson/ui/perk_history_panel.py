from __future__ import annotations

"""Not native: read-only sidebar shown alongside the perk-selection screen.

Lists every perk the player has picked this run, plus a compact summary of
resolved `PlayerStats` buckets (progression/stats.py) that currently differ
from their identity default. Purely informational - no picks, no input
handling - so unlike ui/perk_menu.py and ui/run_mod_menu.py this has no
"controller" of its own; it just mirrors PerkMenuController's own
open/timeline state (see survival_mode.py/quest_mode.py's draw calls).

Slides in from the real screen's right edge rather than a fixed spot in the
classic 640-wide UI space the other two panels share - it's meant to hug
whatever resolution is actually running instead of leaving dead space on a
wide monitor or overlapping the run-mod panel on a narrow one.
"""

import msgspec

from grim.assets import RuntimeResources, TextureId
from grim.fonts.small import draw_small_text, measure_small_text_width
from grim.geom import Rect, Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ..perks.ids import PerkId, perk_display_name
from ..progression.stats import PlayerStats
from ..sim.state_types import PlayerState
from .menu_panel import MENU_PANEL_DST_BOTTOM_H, MENU_PANEL_DST_TOP_H, draw_classic_menu_panel, draw_menu_panel_hardware
from .perk_menu import PERK_MENU_ANIM_END_MS, PERK_MENU_ANIM_START_MS, ui_element_slide_x

PERK_HISTORY_PANEL_WIDTH = 220.0
PERK_HISTORY_MARGIN_RIGHT = 12.0
PERK_HISTORY_MARGIN_TOP = 40.0
PERK_HISTORY_MARGIN_BOTTOM = 40.0
PERK_HISTORY_PADDING_X = 10.0

# draw_classic_menu_panel ties its border-chrome thickness to dst.width when
# no explicit border_scale is given (see menu_panel.py) - same as the
# run-mod panel's own draw call. Mirrored here so text never starts under
# the panel's own top/bottom frame art.
_PANEL_BORDER_SCALE = PERK_HISTORY_PANEL_WIDTH / 510.0
_PANEL_TOP_CHROME_H = MENU_PANEL_DST_TOP_H * _PANEL_BORDER_SCALE
_PANEL_BOTTOM_CHROME_H = MENU_PANEL_DST_BOTTOM_H * _PANEL_BORDER_SCALE

PERK_HISTORY_TITLE_Y = _PANEL_TOP_CHROME_H + 8.0
PERK_HISTORY_LIST_Y = _PANEL_TOP_CHROME_H + 26.0
PERK_HISTORY_LIST_STEP = 14.0
PERK_HISTORY_STATS_SECTION_H = 190.0
PERK_HISTORY_STATS_TITLE_H = 16.0
PERK_HISTORY_STATS_ROW_H = 13.0

PERK_HISTORY_TITLE_COLOR = rl.Color(255, 210, 120, 255)
PERK_HISTORY_TEXT_COLOR = rl.Color(215, 215, 215, 255)
PERK_HISTORY_COUNT_COLOR = rl.Color(140, 195, 255, 255)
PERK_HISTORY_EMPTY_COLOR = rl.Color(140, 140, 140, 200)
PERK_HISTORY_STATS_TITLE_COLOR = rl.Color(140, 220, 235, 255)
PERK_HISTORY_STATS_TEXT_COLOR = rl.Color(185, 230, 185, 255)
PERK_HISTORY_STATS_MORE_COLOR = rl.Color(140, 140, 140, 200)


def perk_history_panel_slide_x(t_ms: float) -> float:
    """Slides in from the real screen's right edge (+width -> 0)."""

    return ui_element_slide_x(
        t_ms,
        start_ms=PERK_MENU_ANIM_START_MS,
        end_ms=PERK_MENU_ANIM_END_MS,
        width=PERK_HISTORY_PANEL_WIDTH + PERK_HISTORY_MARGIN_RIGHT,
        direction_flag=1,
    )


class PerkHistoryPanelComputedLayout(msgspec.Struct):
    panel: Rect
    title_pos: Vec2
    list_pos: Vec2
    list_step_y: float
    list_bottom: float
    stats_title_pos: Vec2
    stats_list_pos: Vec2
    stats_row_h: float


def perk_history_panel_compute_layout(
    *,
    screen_w: float,
    screen_h: float,
    slide_x: float,
) -> PerkHistoryPanelComputedLayout:
    panel_x = screen_w - PERK_HISTORY_PANEL_WIDTH - PERK_HISTORY_MARGIN_RIGHT + slide_x
    panel_y = PERK_HISTORY_MARGIN_TOP
    panel_h = max(0.0, screen_h - PERK_HISTORY_MARGIN_TOP - PERK_HISTORY_MARGIN_BOTTOM)
    panel = Rect.from_pos_size(Vec2(panel_x, panel_y), Vec2(PERK_HISTORY_PANEL_WIDTH, panel_h))

    title_pos = panel.top_left.offset(dx=PERK_HISTORY_PADDING_X, dy=PERK_HISTORY_TITLE_Y)
    list_pos = panel.top_left.offset(dx=PERK_HISTORY_PADDING_X, dy=PERK_HISTORY_LIST_Y)
    stats_title_pos = Vec2(panel.x + PERK_HISTORY_PADDING_X, panel.bottom - PERK_HISTORY_STATS_SECTION_H)
    stats_list_pos = stats_title_pos.offset(dy=PERK_HISTORY_STATS_TITLE_H)
    list_bottom = stats_title_pos.y - 6.0

    return PerkHistoryPanelComputedLayout(
        panel=panel,
        title_pos=title_pos,
        list_pos=list_pos,
        list_step_y=PERK_HISTORY_LIST_STEP,
        list_bottom=list_bottom,
        stats_title_pos=stats_title_pos,
        stats_list_pos=stats_list_pos,
        stats_row_h=PERK_HISTORY_STATS_ROW_H,
    )


def owned_perk_rows(player: PlayerState, *, violence_disabled: int = 0) -> list[tuple[str, int]]:
    """(display name, count) for every perk this player has picked at least
    once this run, in PerkId declaration order (no pick-order history is
    tracked anywhere - perk_counts is just a flat per-id counter)."""

    counts = player.perk_counts
    rows: list[tuple[str, int]] = []
    for perk_id in PerkId:
        idx = int(perk_id)
        if idx >= len(counts):
            continue
        count = int(counts[idx])
        if count <= 0:
            continue
        rows.append((perk_display_name(perk_id, violence_disabled=violence_disabled), count))
    return rows


# (stat field name, display label, format kind). Only fields worth surfacing
# to a player as a build summary - not every internal PlayerStats field reads
# meaningfully on its own (flags has no numeric bucket at all).
# format kinds: "pct" = (value-1)*100 signed percent, "chance" = value*100
# signed percent, "mult" = raw "xN.NN", "flat" = signed integer, "rate" =
# signed one-decimal "+N.N/s".
_STAT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("damage_mult", "All Damage", "pct"),
    ("damage_mult_projectile", "Projectile Dmg", "pct"),
    ("damage_mult_bullet", "Bullet Dmg", "pct"),
    ("damage_mult_fire", "Fire Dmg", "pct"),
    ("damage_mult_ion", "Ion Dmg", "pct"),
    ("damage_mult_plasma", "Plasma Dmg", "pct"),
    ("damage_mult_lightning", "Lightning Dmg", "pct"),
    ("damage_mult_explosion", "Explosion Dmg", "pct"),
    ("damage_mult_energy", "Energy Dmg", "pct"),
    ("shot_cooldown_mult", "Fire Rate", "inv_pct"),
    ("reload_time_mult", "Reload Speed", "inv_pct"),
    ("clip_size_mult", "Clip Size", "pct"),
    ("clip_size_add", "Clip Size", "flat"),
    ("projectile_count_add", "Extra Projectiles", "flat"),
    ("pierce_add", "Pierce", "flat"),
    ("projectile_speed_mult", "Projectile Speed", "pct"),
    ("spread_mult", "Spread", "inv_pct"),
    ("crit_chance", "Crit Chance", "chance"),
    ("crit_mult", "Crit Multiplier", "mult"),
    ("damage_taken_mult", "Damage Taken", "pct"),
    ("max_health_mult", "Max Health", "pct"),
    ("health_regen_per_sec", "Health Regen", "rate"),
    ("dodge_chance", "Dodge Chance", "chance"),
    ("move_speed_mult", "Move Speed", "pct"),
    ("xp_mult", "XP Gain", "pct"),
    ("bonus_duration_mult", "Power-up Duration", "pct"),
    ("pickup_radius_mult", "Pickup Radius", "pct"),
    ("luck", "Luck", "flat"),
    ("perk_efficacy", "Perk Efficacy", "pct"),
)
_ARCHETYPE_PREFIX = "damage_mult_archetype_"


def _format_stat(kind: str, value: float) -> str:
    if kind == "pct":
        return f"{(value - 1.0) * 100.0:+.0f}%"
    if kind == "inv_pct":
        # <1.0 is the good direction (faster fire/reload, tighter spread) -
        # flip the sign so the displayed percent still reads as a buff.
        return f"{(1.0 - value) * 100.0:+.0f}%"
    if kind == "chance":
        return f"{value * 100.0:+.0f}%"
    if kind == "mult":
        return f"x{value:.2f}"
    if kind == "rate":
        return f"{value:+.1f}/s"
    return f"{value:+.0f}"


def stat_summary_rows(stats: PlayerStats) -> list[tuple[str, str]]:
    """(label, formatted value) for every resolved stat that currently
    differs from its identity default - the "secondary stat buckets" a
    build has quietly accumulated from perks/run mods/relics alike."""

    rows: list[tuple[str, str]] = []
    for field, label, kind in _STAT_ROWS:
        value = float(getattr(stats, field))
        identity = 2.0 if field == "crit_mult" else 0.0 if kind in ("flat", "rate", "chance") else 1.0
        if abs(value - identity) <= 1e-6:
            continue
        rows.append((label, _format_stat(kind, value)))
    for field in stats.__struct_fields__:
        if not field.startswith(_ARCHETYPE_PREFIX):
            continue
        value = float(getattr(stats, field))
        if abs(value - 1.0) <= 1e-6:
            continue
        archetype = field[len(_ARCHETYPE_PREFIX) :].replace("_", " ").title()
        rows.append((f"{archetype} Dmg", _format_stat("pct", value)))
    return rows


def _text_width(text: str, resources: RuntimeResources) -> float:
    return measure_small_text_width(resources.small_font, text)


def draw_perk_history_panel(
    *,
    resources: RuntimeResources,
    player: PlayerState,
    timeline_ms: float,
    violence_disabled: int = 0,
    shadows_enabled: bool = False,
) -> None:
    menu_t = clamp(timeline_ms / PERK_MENU_ANIM_START_MS, 0.0, 1.0)
    if menu_t <= 1e-3:
        return

    screen_w = float(rl.get_screen_width())
    screen_h = float(rl.get_screen_height())
    slide_x = perk_history_panel_slide_x(timeline_ms)
    layout = perk_history_panel_compute_layout(screen_w=screen_w, screen_h=screen_h, slide_x=slide_x)

    # Same textured metal-plate panel as the main perk list / run-mod side
    # panel / relic screen (ui_menuPanel), not a flat rectangle - keeps this
    # panel visually consistent with the rest of Crimsonland's UI.
    # trim_hardware=True crops out the dangling hinge-cable/ring baked into
    # the texture outside its own frame silhouette (otherwise it smears
    # across a panel this far from the native ~510px design width); the
    # cable+plug accent comes back via draw_menu_panel_hardware below,
    # undistorted, flipped to point back toward the game world since this
    # panel sits at the screen's right edge.
    panel_tex = resources.texture(TextureId.UI_MENU_PANEL)
    draw_classic_menu_panel(
        panel_tex,
        dst=layout.panel.to_rl(),
        shadow=shadows_enabled,
        flip_x=True,
        trim_hardware=True,
    )
    draw_menu_panel_hardware(panel_tex, panel=layout.panel.to_rl(), flip_x=True, scale=0.3)

    font = resources.small_font
    draw_small_text(font, "Your Perks", layout.title_pos, PERK_HISTORY_TITLE_COLOR)

    rows = owned_perk_rows(player, violence_disabled=violence_disabled)
    pos = layout.list_pos
    if not rows:
        draw_small_text(font, "(none yet)", pos, PERK_HISTORY_EMPTY_COLOR)
    else:
        max_width = layout.panel.w - PERK_HISTORY_PADDING_X * 2.0
        for row_index, (name, count) in enumerate(rows):
            if pos.y + layout.list_step_y > layout.list_bottom:
                remaining = len(rows) - row_index
                draw_small_text(font, f"...+{remaining} more", pos, PERK_HISTORY_EMPTY_COLOR)
                break
            suffix = f" x{count}" if count > 1 else ""
            line = name + suffix
            # Trim long names so they never bleed past the panel's own edge.
            while line and _text_width(line, resources) > max_width:
                name = name[:-1]
                line = name + suffix
            draw_small_text(font, name, pos, PERK_HISTORY_TEXT_COLOR)
            if suffix:
                draw_small_text(
                    font,
                    suffix,
                    pos.offset(dx=_text_width(name, resources)),
                    PERK_HISTORY_COUNT_COLOR,
                )
            pos = pos.offset(dy=layout.list_step_y)

    draw_small_text(font, "Stat Bonuses", layout.stats_title_pos, PERK_HISTORY_STATS_TITLE_COLOR)
    stat_rows = stat_summary_rows(player.stats)
    pos = layout.stats_list_pos
    stats_bottom = layout.panel.bottom - _PANEL_BOTTOM_CHROME_H - 8.0
    if not stat_rows:
        draw_small_text(font, "(none yet)", pos, PERK_HISTORY_EMPTY_COLOR)
    else:
        max_rows = int((stats_bottom - pos.y) / layout.stats_row_h)
        shown = stat_rows[: max(0, max_rows)]
        for label, value in shown:
            if pos.y + layout.stats_row_h > stats_bottom:
                break
            text = f"{label}: {value}"
            draw_small_text(font, text, pos, PERK_HISTORY_STATS_TEXT_COLOR)
            pos = pos.offset(dy=layout.stats_row_h)
        if len(stat_rows) > len(shown):
            draw_small_text(font, f"...+{len(stat_rows) - len(shown)} more", pos, PERK_HISTORY_STATS_MORE_COLOR)


__all__ = [
    "PerkHistoryPanelComputedLayout",
    "draw_perk_history_panel",
    "owned_perk_rows",
    "perk_history_panel_compute_layout",
    "perk_history_panel_slide_x",
    "stat_summary_rows",
]
