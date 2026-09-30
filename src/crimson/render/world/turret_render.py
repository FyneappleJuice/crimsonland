from __future__ import annotations

"""Relic of the Turret rendering (not native).

A turret is drawn as two independent layers from one 3x3-grid spritesheet
(turret1.png) - a static base (never rotates) and a gun on top that rotates
to face `creature.heading`, exactly the split render/world/trooper.py already
uses for the player's legs (heading) vs torso/gun (aim_heading). Both layers
share `_draw_atlas_sprite`'s pivot-centered rotation (render/world/context.py),
the same helper trooper.py uses.

Also draws a small HP-bar fill (there's no existing literal health-bar
precedent anywhere else in the codebase - the closest is
render/world/dummy_stats.py's world-anchored text readout, whose positioning
this borrows), each turret's own ammo count and reload gauge (mirroring
render/world/player_status.py's on-character ammo text and
render/world/draw.py's draw_aim_indicators reload clock gauge, just fed from
the turret's own WeaponSlot instead of the player's), and the turret
build-progress radial gauge (offset toward the player's bottom-right so it
doesn't collide with their own health ring, drawn centered on the player).
"""

import math
from typing import TYPE_CHECKING

from grim.assets import TextureId
from grim.fonts.small import draw_small_text, measure_small_text_width
from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from .overlays import draw_clock_gauge

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from .context import WorldRenderCtx
    from .draw import WorldDrawContext

# One 64x64 cell of the 192x192, 3x3-grid spritesheet at scale 1.0 - matches
# both the "size==64 -> scale 1.0" convention every other creature sprite
# uses (see draw.py's _BARREL_REFERENCE_SIZE) and the actual source art size.
_TURRET_REFERENCE_SIZE = 64.0
_TURRET_GRID = 3
_TURRET_BASE_FRAME = 2  # row 0, col 2 - static base, never rotates
_TURRET_GUN_FRAME = 4  # row 1, col 1 - rotates to face creature.heading
# Not native: the gun art's default (unrotated) orientation doesn't match
# trooper.py's convention (heading passed straight through) - confirmed
# visually 90 degrees off. draw_creature_sprite's own convention for native
# creature sprites (render/world/draw.py's `rotation_rad=heading - pi/2`) is
# the better fit for a non-player sprite like this one. If it's still off
# (rotated the other way), flip the sign here.
_TURRET_GUN_ROTATION_OFFSET = -math.pi / 2.0

_HP_BAR_ABOVE_OFFSET = 44.0
_HP_BAR_WIDTH = 40.0
_HP_BAR_HEIGHT = 5.0
_HUD_TEXT_SCALE = 1.2

# Not native: keeps the build-progress gauge just clear of the player's own
# on-character health ring (render/world/player_status.py's _RING_OUTER,
# 22.5 * scale) - offsets the gauge's top-left corner (draw_clock_gauge
# doesn't center on `pos`) diagonally by ~the ring's radius, so it sits right
# at the ring's bottom-right edge instead of far off in the corner.
_BUILD_GAUGE_OFFSET_X = 18.0
_BUILD_GAUGE_OFFSET_Y = 18.0


def draw_turrets(render_ctx: WorldRenderCtx, *, ctx: WorldDrawContext) -> None:
    frame = render_ctx.frame
    texture = frame.resources.texture_optional(TextureId.TURRET1)
    if texture is None:
        return
    tint = rl.Color(255, 255, 255, int(clamp(ctx.entity_alpha, 0.0, 1.0) * 255.0 + 0.5))
    for creature in frame.creatures.entries:
        if not creature.active or not creature.is_turret:
            continue
        screen = render_ctx._world_to_screen_with(creature.pos, camera=ctx.camera, view_scale=ctx.view_scale)
        size_scale = clamp(float(creature.size) / _TURRET_REFERENCE_SIZE, 0.25, 2.0) * ctx.scale
        render_ctx._draw_atlas_sprite(
            texture,
            grid=_TURRET_GRID,
            frame=_TURRET_BASE_FRAME,
            pos=screen,
            scale=size_scale,
            rotation_rad=0.0,
            tint=tint,
        )
        render_ctx._draw_atlas_sprite(
            texture,
            grid=_TURRET_GRID,
            frame=_TURRET_GUN_FRAME,
            pos=screen,
            scale=size_scale,
            rotation_rad=float(creature.heading) + _TURRET_GUN_ROTATION_OFFSET,
            tint=tint,
        )
        _draw_turret_hp_bar(creature, screen=screen, scale=ctx.scale, alpha=ctx.entity_alpha)
        _draw_turret_ammo(render_ctx, creature, screen=screen, scale=ctx.scale, alpha=ctx.entity_alpha)
        _draw_turret_reload_gauge(render_ctx, creature, screen=screen, scale=ctx.scale, alpha=ctx.entity_alpha)


def _draw_turret_hp_bar(creature: CreatureState, *, screen: Vec2, scale: float, alpha: float) -> None:
    if float(creature.max_hp) <= 0.0:
        return
    frac = clamp(float(creature.hp) / float(creature.max_hp), 0.0, 1.0)
    top_y = screen.y - _HP_BAR_ABOVE_OFFSET * scale
    w = _HP_BAR_WIDTH * scale
    h = _HP_BAR_HEIGHT * scale
    left = screen.x - w * 0.5
    a = clamp(alpha, 0.0, 1.0)
    rl.draw_rectangle(int(left), int(top_y), int(w), int(h), rl.Color(60, 0, 0, int(200 * a)))
    rl.draw_rectangle(int(left), int(top_y), int(w * frac), int(h), rl.Color(220, 60, 60, int(230 * a)))


def _draw_turret_ammo(render_ctx: WorldRenderCtx, creature: CreatureState, *, screen: Vec2, scale: float, alpha: float) -> None:
    # Mirrors player_status.py's on-character ammo readout, flanking the HP
    # bar on the right instead of sitting above the character's own ring.
    weapon = creature.turret_weapon
    if weapon is None:
        return
    font = render_ctx.frame.resources.small_font
    if font is None:
        return
    a = clamp(alpha, 0.0, 1.0)
    shadow = rl.Color(0, 0, 0, int(185 * a))
    tx = screen.x + (_HP_BAR_WIDTH * 0.5 + 6.0) * scale
    ty = screen.y - _HP_BAR_ABOVE_OFFSET * scale - 1.0 * scale

    alt = creature.turret_alt_weapon
    if alt is None:
        ammo = max(0, int(float(weapon.ammo)))
        text = str(ammo)
        fg = rl.Color(240, 240, 240, int(255 * a)) if ammo > 0 else rl.Color(210, 90, 90, int(255 * a))
        draw_small_text(font, text, Vec2(tx + 1.0, ty + 1.0), shadow, scale=_HUD_TEXT_SCALE)
        draw_small_text(font, text, Vec2(tx, ty), fg, scale=_HUD_TEXT_SCALE)
        return

    # Pact of the Giant - "A, B" clip counts for both slots, mirroring
    # player_status.py's own _draw_dual_ammo (no active-slot underline here -
    # a turret never picks up weapons itself, so that concept doesn't apply).
    counts = (max(0, int(float(weapon.ammo))), max(0, int(float(alt.ammo))))
    parts = ((str(counts[0]), 0), (", ", None), (str(counts[1]), 1))
    x = float(int(tx))
    for text, slot in parts:
        width = measure_small_text_width(font, text) * _HUD_TEXT_SCALE
        color = (
            (rl.Color(240, 240, 240, int(255 * a)) if counts[slot] > 0 else rl.Color(210, 90, 90, int(255 * a)))
            if slot is not None
            else rl.Color(200, 200, 205, int(255 * a))
        )
        draw_small_text(font, text, Vec2(x + 1.0, ty + 1.0), shadow, scale=_HUD_TEXT_SCALE)
        draw_small_text(font, text, Vec2(x, ty), color, scale=_HUD_TEXT_SCALE)
        x += width


def _draw_turret_reload_gauge(render_ctx: WorldRenderCtx, creature: CreatureState, *, screen: Vec2, scale: float, alpha: float) -> None:
    # Mirrors draw_aim_indicators' player reload clock gauge, flanking the HP
    # bar on the left, fed from the turret's own WeaponSlot instead.
    weapon = creature.turret_weapon
    if weapon is None or float(weapon.reload_timer_max) <= 1e-6 or float(weapon.reload_timer) <= 0.0:
        return
    progress = clamp(float(weapon.reload_timer) / float(weapon.reload_timer_max), 0.0, 1.0)
    ms = int(progress * 60000.0)
    gauge_size = 32.0 * scale
    pos = Vec2(
        screen.x - (_HP_BAR_WIDTH * 0.5 + 6.0) * scale - gauge_size,
        screen.y - _HP_BAR_ABOVE_OFFSET * scale - (gauge_size - _HP_BAR_HEIGHT * scale) * 0.5,
    )
    draw_clock_gauge(render_ctx, pos=pos, ms=ms, scale=scale, alpha=alpha)


def draw_turret_build_progress(render_ctx: WorldRenderCtx, *, ctx: WorldDrawContext) -> None:
    for player in render_ctx.frame.players:
        if not player.turret_relic_building or float(player.turret_build_duration) <= 1e-6:
            continue
        progress = float(player.turret_build_timer) / float(player.turret_build_duration)
        if progress <= 0.0:
            continue
        screen = render_ctx._world_to_screen_with(player.pos, camera=ctx.camera, view_scale=ctx.view_scale)
        ms = int(clamp(progress, 0.0, 1.0) * 60000.0)
        pos = Vec2(
            screen.x + _BUILD_GAUGE_OFFSET_X * ctx.scale,
            screen.y + _BUILD_GAUGE_OFFSET_Y * ctx.scale,
        )
        draw_clock_gauge(
            render_ctx,
            pos=Vec2(int(pos.x), int(pos.y)),
            ms=ms,
            scale=ctx.scale,
            alpha=ctx.entity_alpha,
        )


__all__ = [
    "draw_turret_build_progress",
    "draw_turrets",
]
