from __future__ import annotations

"""Not native: hover tooltip for rare monsters.

When the aim cursor is over an affixed creature, its rarity + modifier list is
drawn as a panel at the top centre of the screen, one modifier per line.
"""

import math

from grim.fonts.small import draw_small_text, measure_small_text_width
from grim.geom import Vec2
from grim.raylib_api import rl

from ...creatures.rarity import RARITY_COLOR, monster_tooltip_lines
from .context import WorldRenderCtx

_LINE_H = 15.0
_PAD_X = 10.0
_PAD_Y = 7.0
_TOP_MARGIN = 8.0
_HOVER_SLACK = 10.0  # world px added to the creature radius for the hover test


def _hovered_creature(frame):
    if not frame.players:
        return None
    aim = frame.players[0].aim
    ax, ay = float(aim.x), float(aim.y)
    best = None
    best_d = 1e18
    for c in frame.creatures.entries:
        if not c.active or not c.rarity or float(c.hp) <= 0.0:
            continue
        d = math.hypot(float(c.pos.x) - ax, float(c.pos.y) - ay)
        reach = float(c.size) * 0.6 + _HOVER_SLACK
        if d <= reach and d < best_d:
            best = c
            best_d = d
    return best


def draw_monster_rarity_tooltip(render_ctx: WorldRenderCtx, *, out_size: Vec2) -> None:
    frame = render_ctx.frame
    creature = _hovered_creature(frame)
    if creature is None:
        return

    type_name = creature.type_id.name.lower()
    lines = monster_tooltip_lines(type_name, int(creature.rarity), tuple(creature.affixes))
    if not lines:
        return

    font = frame.resources.small_font
    if font is None:
        return

    width = max(measure_small_text_width(font, ln) for ln in lines) + 2.0 * _PAD_X
    height = _LINE_H * len(lines) + 2.0 * _PAD_Y
    x0 = (float(out_size.x) - width) * 0.5
    y0 = _TOP_MARGIN

    rl.draw_rectangle(int(x0), int(y0), int(width), int(height), rl.Color(8, 8, 12, 220))
    rc = RARITY_COLOR.get(int(creature.rarity), (255, 255, 255))
    border = rl.Color(rc[0], rc[1], rc[2], 255)
    rl.draw_rectangle_lines(int(x0), int(y0), int(width), int(height), border)

    tx = x0 + _PAD_X
    ty = y0 + _PAD_Y
    for i, ln in enumerate(lines):
        color = border if i == 0 else rl.Color(220, 222, 230, 255)
        draw_small_text(font, ln, Vec2(tx + 1.0, ty + 1.0), rl.Color(0, 0, 0, 200))
        draw_small_text(font, ln, Vec2(tx, ty), color)
        ty += _LINE_H
