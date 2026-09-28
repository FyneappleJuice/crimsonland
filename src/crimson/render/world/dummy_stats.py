from __future__ import annotations

"""Not native: sandbox mode damage-dummy floating stats (creatures/dummy.py).

Three stacked lines above every active damage dummy - damage / dps / last hit -
following render/world/player_status.py's established world-anchored-text
pattern (world_to_screen, then a shadow-offset draw followed by a foreground
draw for legibility)."""

from grim.fonts.small import draw_small_text
from grim.geom import Vec2
from grim.raylib_api import rl

from ...creatures.dummy import dummy_dps
from .context import WorldRenderCtx

_LINE_GAP = 13.0
_ABOVE_HEAD_OFFSET = 44.0  # world px above the dummy's center, before view scale
_TEXT_SCALE = 1.1


def draw_dummy_stats(
    render_ctx: WorldRenderCtx,
    *,
    camera: Vec2,
    view_scale: Vec2,
    scale: float,
    alpha: float = 1.0,
) -> None:
    if alpha <= 1e-3:
        return
    for creature in render_ctx.frame.creatures.entries:
        if not creature.active or not creature.is_test_dummy:
            continue

        screen = render_ctx._world_to_screen_with(creature.pos, camera=camera, view_scale=view_scale)
        top = Vec2(screen.x, screen.y - _ABOVE_HEAD_OFFSET * scale)
        gap = _LINE_GAP * scale

        lines = (
            (f"damage: {creature.dummy_damage_total:.1f}", rl.Color(255, 210, 90, int(255 * alpha))),
            (f"dps: {dummy_dps(creature):.1f}", rl.Color(255, 120, 90, int(255 * alpha))),
            (f"last hit: {creature.dummy_last_hit_amount:.1f}", rl.Color(200, 200, 255, int(255 * alpha))),
        )

        font = render_ctx.frame.resources.small_font
        shadow = rl.Color(0, 0, 0, int(185 * alpha))
        for i, (text, color) in enumerate(lines):
            pos = Vec2(top.x, top.y + gap * i)
            if font is not None:
                draw_small_text(font, text, Vec2(pos.x + 1.0, pos.y + 1.0), shadow, scale=_TEXT_SCALE)
                draw_small_text(font, text, pos, color, scale=_TEXT_SCALE)
            else:
                rl.draw_text(text, int(pos.x), int(pos.y), 16, color)


__all__ = ["draw_dummy_stats"]
