from __future__ import annotations

"""Render pass for the Evil Scythe melee sweep. Not native.

The blade sprite is grip-anchored at the player and rotated so its shaft points
along the current swing bearing, with a short fan of fading ghost copies for the
motion trail. Falls back to a procedural blue arc when the optional
`game/scythe.tga` texture is missing.

With CRIMSON_DEBUG=1 or in --test-mode a green overlay shows the real damage
geometry: the reach circle, the cone edges, the live blade edge, and a marker on
every creature the swing has hit.
"""

import math

from grim.assets import TextureId
from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ...debug import debug_enabled
from ...test_mode import test_mode_enabled
from ...weapon_runtime.scythe_sweep import (
    SCYTHE_CREATURE_REACH_FACTOR,
    scythe_arc_angle_for,
    scythe_blade_angle,
    scythe_progress,
    scythe_swing_arc,
    scythe_swing_reach,
)
from .context import WorldRenderCtx

# --- sprite anchoring (measured from game/scythe.tga, 172x172) ---------------
# Grip corner (down-left of the art) as a fraction of the canvas.
_GRIP = (0.047, 0.924)
# Grip -> shaft-top distance, as a multiple of canvas width.
_GRIP_TO_TIP_FRAC = 1.193
# Bearing of the grip -> shaft-top vector in the sprite's own pixels (y-down).
_ART_DIR = math.radians(-47.4)
# Draw the blade a little past the collision reach so the edge visibly leads.
_BLADE_OVERREACH = 1.12
_TINT = (110, 235, 210)  # spectral teal
_TRAIL_COPIES = 5
_DEBUG_GREEN = (60, 235, 90)


def _draw_scythe_sprite(
    texture: rl.Texture,
    *,
    grip_screen: Vec2,
    angle: float,
    reach: float,
    view_scale: float,
    tint: rl.Color,
    mirror: bool = False,
) -> None:
    tw = float(texture.width)
    th = float(texture.height)
    # Scale so grip -> shaft-top spans reach * overreach screen pixels.
    want_px = float(reach) * _BLADE_OVERREACH * float(view_scale)
    sprite_scale = want_px / (_GRIP_TO_TIP_FRAC * tw)
    dw = tw * sprite_scale
    dh = th * sprite_scale
    # On the back-sweep, mirror the art so the blade still leads the motion.
    if mirror:
        src = rl.Rectangle(0.0, 0.0, -tw, th)
        grip_x = 1.0 - _GRIP[0]
        art_dir = math.atan2(math.sin(_ART_DIR), -math.cos(_ART_DIR))
    else:
        src = rl.Rectangle(0.0, 0.0, tw, th)
        grip_x = _GRIP[0]
        art_dir = _ART_DIR
    dst = rl.Rectangle(float(grip_screen.x), float(grip_screen.y), dw, dh)
    origin = rl.Vector2(grip_x * dw, _GRIP[1] * dh)
    rotation_deg = math.degrees(float(angle) - art_dir)
    rl.draw_texture_pro(texture, src, dst, origin, float(rotation_deg), tint)


def _line(a: Vec2, b: Vec2, color: rl.Color, thick: float = 1.5) -> None:
    rl.draw_line_ex(rl.Vector2(a.x, a.y), rl.Vector2(b.x, b.y), float(thick), color)


def draw_scythe_swings(
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
    if not players or not any(p.scythe_swing.active for p in players):
        return

    def to_screen(world: Vec2) -> Vec2:
        return WorldRenderCtx._world_to_screen_with(world, camera=camera, view_scale=view_scale)

    texture = frame.resources.texture_optional(TextureId.SCYTHE)
    show_debug = debug_enabled() or test_mode_enabled()
    scale = float(scale)

    for player in players:
        swing = player.scythe_swing
        if not swing.active:
            continue

        base = float(swing.base_angle)
        direction = float(swing.direction)
        progress = scythe_progress(swing)
        grip_screen = to_screen(player.pos)
        mirror = direction < 0.0
        arc = scythe_swing_arc(swing)
        reach = scythe_swing_reach(swing)

        # --- the blade + trail ------------------------------------------------
        span = min(progress, 0.42)
        for i in range(_TRAIL_COPIES, -1, -1):
            frac = i / float(_TRAIL_COPIES)
            p = max(0.0, progress - span * frac)
            ang = scythe_arc_angle_for(swing, p)
            lead = 1.0 - frac
            copy_alpha = alpha * (0.10 + 0.72 * lead * lead)  # ghostly - never fully opaque
            a255 = int(clamp(copy_alpha, 0.0, 1.0) * 255.0 + 0.5)

            if texture is not None:
                _draw_scythe_sprite(
                    texture,
                    grip_screen=grip_screen,
                    angle=ang,
                    reach=reach,
                    view_scale=scale,
                    tint=rl.Color(_TINT[0], _TINT[1], _TINT[2], a255),
                    mirror=mirror,
                )
            else:
                r_in = reach * 0.30 * scale
                r_out = reach * 1.04 * scale
                a0 = math.degrees(ang - arc * 0.05)
                a1 = math.degrees(ang + arc * 0.05)
                rl.draw_ring(
                    rl.Vector2(grip_screen.x, grip_screen.y),
                    float(r_in), float(r_out), float(a0), float(a1), 10,
                    rl.Color(_TINT[0], _TINT[1], _TINT[2], int(a255 * 0.8)),
                )

        if not show_debug:
            continue

        # --- green debug: the real damage geometry --------------------------
        g = rl.Color(_DEBUG_GREEN[0], _DEBUG_GREEN[1], _DEBUG_GREEN[2], 210)
        g_dim = rl.Color(_DEBUG_GREEN[0], _DEBUG_GREEN[1], _DEBUG_GREEN[2], 90)
        reach_px = reach * scale

        # max-reach ring
        rl.draw_circle_lines(int(grip_screen.x), int(grip_screen.y), reach_px, g_dim)
        # cone edges
        for edge in (base - arc * 0.5, base + arc * 0.5):
            tip = Vec2(
                player.pos.x + reach * math.cos(edge),
                player.pos.y + reach * math.sin(edge),
            )
            _line(grip_screen, to_screen(tip), g_dim, 1.5)
        # live blade edge (where damage lands this instant)
        cur = scythe_blade_angle(swing)
        blade_tip = Vec2(
            player.pos.x + reach * math.cos(cur),
            player.pos.y + reach * math.sin(cur),
        )
        _line(grip_screen, to_screen(blade_tip), g, 3.0)
        # per-creature reach circles + hit markers
        creatures = frame.creatures.entries
        for idx, creature in enumerate(creatures):
            if not creature.active or float(creature.hp) <= 0.0:
                continue
            cs = to_screen(creature.pos)
            crush = (reach + float(creature.size) * SCYTHE_CREATURE_REACH_FACTOR) * scale
            if math.hypot(cs.x - grip_screen.x, cs.y - grip_screen.y) > crush + 40.0:
                continue
            if idx in swing.hit:
                rl.draw_circle_lines(int(cs.x), int(cs.y), 10.0, g)
                rl.draw_circle_lines(int(cs.x), int(cs.y), 6.0, g)
            else:
                rl.draw_circle_lines(int(cs.x), int(cs.y), 8.0, g_dim)
