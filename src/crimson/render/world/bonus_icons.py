from __future__ import annotations

"""Not native: icon art for the two project-added bonuses.

The shared 4x4 bonus sheet (game/bonuses.jaz) has no frame for Fork Shot, and
Blade only borrows an unrelated frame. Both are drawn here instead - Fork Shot
procedurally, Blade from its actual orbiting-blade sprite - and used by both the
ground pickup renderer (render/world/bonuses.py) and the character-anchored
power-up stack (render/world/player_status.py).
"""

import math

from grim.assets import TextureId
from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ...projectiles.types import ProjectileTemplateId
from ...sim.world_defs import KNOWN_PROJ_FRAMES
from .context import WorldRenderCtx

_FORK_TINE_ANGLE = math.pi / 3.0  # matches _FORK_SHOT_ANGLE_RAD


def draw_fork_icon(cx: float, cy: float, size: float, alpha: float, rotation_rad: float = 0.0) -> None:
    """A stem splitting into three gold tines at 0 / +-60 deg, centred on (cx, cy)."""
    a = clamp(float(alpha), 0.0, 1.0)
    if a <= 1e-3 or size <= 0.0:
        return
    gold = rl.Color(240, 200, 90, int(255 * a))
    dark = rl.Color(120, 90, 20, int(255 * a))
    thick = max(1.5, size * 0.11)
    cos_r, sin_r = math.cos(rotation_rad), math.sin(rotation_rad)

    def pt(dx: float, dy: float) -> rl.Vector2:
        return rl.Vector2(cx + dx * cos_r - dy * sin_r, cy + dx * sin_r + dy * cos_r)

    junction_y = size * 0.04
    base = pt(0.0, size * 0.44)
    junction = pt(0.0, junction_y)
    rl.draw_line_ex(base, junction, thick, dark)
    rl.draw_line_ex(base, junction, thick * 0.55, gold)

    tine_len = size * 0.46
    for ang in (-math.pi / 2.0, -math.pi / 2.0 - _FORK_TINE_ANGLE, -math.pi / 2.0 + _FORK_TINE_ANGLE):
        tip = pt(math.cos(ang) * tine_len, junction_y + math.sin(ang) * tine_len)
        rl.draw_line_ex(junction, tip, thick, dark)
        rl.draw_line_ex(junction, tip, thick * 0.55, gold)
        rl.draw_circle(int(tip.x), int(tip.y), max(1.0, thick * 0.85), gold)


def draw_blade_icon(
    render_ctx: WorldRenderCtx, cx: float, cy: float, size: float, alpha: float, rotation_rad: float = 0.0,
) -> None:
    """The actual orbiting-blade sprite (PROJS atlas, BLADE_GUN frame), centred on (cx, cy)."""
    a = clamp(float(alpha), 0.0, 1.0)
    if a <= 1e-3 or size <= 0.0:
        return
    tex = render_ctx.frame.resources.texture(TextureId.PROJS)
    if tex is None:
        return
    grid, blade_frame = KNOWN_PROJ_FRAMES[ProjectileTemplateId.BLADE_GUN]
    cell = max(1.0, float(tex.width) / float(max(1, int(grid))))
    render_ctx._draw_atlas_sprite(
        tex,
        grid=int(grid),
        frame=int(blade_frame),
        pos=Vec2(cx, cy),
        scale=(size / cell) * 1.05,
        rotation_rad=rotation_rad,
        tint=rl.Color(220, 220, 230, int(255 * a)),
    )


__all__ = ["draw_blade_icon", "draw_fork_icon"]
