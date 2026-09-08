from __future__ import annotations

"""Render pass for the Blade bonus - the 5 orbiting blades. Not native."""

import math

from grim.assets import TextureId
from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ...bonuses.blade_orbit import blade_orbit_offsets, blade_orbit_progress
from ...projectiles.types import ProjectileTemplateId
from ...sim.world_defs import KNOWN_PROJ_FRAMES
from .context import WorldRenderCtx


def draw_blade_orbits(
    render_ctx: WorldRenderCtx,
    *,
    camera: Vec2,
    view_scale: Vec2,
    scale: float,
    alpha: float = 1.0,
) -> None:
    alpha = clamp(float(alpha), 0.0, 1.0)
    if alpha <= 1e-3:
        return

    frame = render_ctx.frame
    players = frame.players
    if not players or not any(p.blade_orbit.active for p in players):
        return

    texture = frame.resources.texture(TextureId.PROJS)
    if texture is None:
        return
    grid, blade_frame = KNOWN_PROJ_FRAMES[ProjectileTemplateId.BLADE_GUN]

    spin = float(frame.elapsed_ms) * 0.02

    for player in players:
        orbit = player.blade_orbit
        if not orbit.active:
            continue
        # Fade the blades out over the final revolution.
        fade = clamp((1.0 - blade_orbit_progress(orbit)) * 6.0, 0.0, 1.0)
        tint = rl.Color(210, 210, 220, int(fade * alpha * 255.0 + 0.5))
        for offset in blade_orbit_offsets(orbit):
            world = Vec2(player.pos.x + offset.x, player.pos.y + offset.y)
            screen = WorldRenderCtx._world_to_screen_with(world, camera=camera, view_scale=view_scale)
            render_ctx._draw_atlas_sprite(
                texture,
                grid=grid,
                frame=blade_frame,
                pos=screen,
                scale=0.7 * float(scale),
                rotation_rad=spin + math.atan2(offset.y, offset.x),
                tint=tint,
            )
