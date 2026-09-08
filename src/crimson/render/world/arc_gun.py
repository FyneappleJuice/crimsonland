from __future__ import annotations

"""Render pass for the Arc Gun chain lightning. Not native.

Fully procedural - no texture. Each bolt segment is subdivided and jittered
perpendicular to its run (amplitude tapering to zero at the endpoints so the
ends stay pinned to the struck creatures), re-rolled every render frame off a
per-strike seed so it crackles. Three stroke passes give it a glow / body /
white-hot core, and each struck node gets a little spark burst.

Hot path notes: pyray's struct constructors and per-call FFI marshalling are the
dominant cost, so this converts each polyline to ``rl.Vector2`` once (all stroke
passes reuse it), hoists the ``rl.Color`` objects out of the per-link loop, and
uses a precomputed jitter table instead of hashing per point.
"""

import math

from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ...weapon_runtime.arc_gun import ARC_BOLT_LIFETIME, arc_chain_points
from .context import WorldRenderCtx

_GLOW = (70, 170, 255)
_BODY = (150, 230, 255)
_CORE = (240, 255, 255)
_SEG_LEN = 10.0   # world units per jitter segment - shorter = more jags
_JITTER = 13.0    # max perpendicular offset (world units), mid-span
_FORK_CHANCE = 0.26   # per interior node, spawn a short dead-end tendril
_FORK_LEN = 26.0      # world units

# Precomputed pseudo-random jitter table in [-1, 1]. Indexed by a cheap integer
# mix of the jitter coordinates - no per-point hashing.
_LUT_N = 1024
_LUT = [
    (((i * 1103515245 + 12345) & 0x7FFFFFFF) / 0x3FFFFFFF) - 1.0 for i in range(_LUT_N)
]
_LUT_MASK = _LUT_N - 1


def _jit(a: int, b: int, c: int) -> float:
    return _LUT[(a * 374761393 + b * 668265263 + c * 2246822519) >> 7 & _LUT_MASK]


def _stroke(pts: list, width: float, color: rl.Color) -> None:
    for i in range(len(pts) - 1):
        rl.draw_line_ex(pts[i], pts[i + 1], width, color)


def draw_arc_bolts(
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
    if not players or not any(float(p.arc_gun.bolt_timer) > 0.0 for p in players):
        return

    cx, cy = float(camera.x), float(camera.y)
    sx, sy = float(view_scale.x), float(view_scale.y)

    def to_screen(wx: float, wy: float) -> rl.Vector2:
        return rl.Vector2((wx + cx) * sx, (wy + cy) * sy)

    scale = float(scale)
    w_glow, w_body, w_core = 7.5 * scale, 3.4 * scale, 1.5 * scale
    # Fast bucket re-rolls the fine jitter almost every frame; the coarse layers
    # lag so the bolt writhes rather than just vibrating.
    fast = int(float(frame.elapsed_ms) / 9.0)
    slow = fast >> 2

    for player in players:
        arc = player.arc_gun
        if float(arc.bolt_timer) <= 0.0:
            continue
        nodes = arc_chain_points(arc)
        if len(nodes) < 2:
            continue

        life = clamp(float(arc.bolt_timer) / ARC_BOLT_LIFETIME, 0.0, 1.0)
        a = alpha * (0.35 + 0.65 * life)
        seed = int(arc.seed)
        c_glow = rl.Color(_GLOW[0], _GLOW[1], _GLOW[2], int(a * 60))
        c_body = rl.Color(_BODY[0], _BODY[1], _BODY[2], int(a * 165))
        c_core = rl.Color(_CORE[0], _CORE[1], _CORE[2], int(a * 235))
        c_fork = rl.Color(_BODY[0], _BODY[1], _BODY[2], int(a * 120))
        c_spark = rl.Color(_BODY[0], _BODY[1], _BODY[2], int(a * 150))
        c_hub = rl.Color(_CORE[0], _CORE[1], _CORE[2], int(a * 220))

        for li in range(len(nodes) - 1):
            p0, p1 = nodes[li], nodes[li + 1]
            rx, ry = float(p1.x) - float(p0.x), float(p1.y) - float(p0.y)
            length = math.hypot(rx, ry)
            if length < 1e-3:
                continue
            inv = 1.0 / length
            nx, ny = -ry * inv, rx * inv  # unit perpendicular
            steps = max(3, int(length * (1.0 / _SEG_LEN)))
            p0x, p0y = float(p0.x), float(p0.y)

            screen_pts: list = []
            world_pts: list[tuple[float, float]] = []
            for s in range(steps + 1):
                t = s / steps
                taper = math.sin(t * math.pi) ** 0.65
                amp = _JITTER * taper
                off = _jit(seed + s, li, fast) * amp
                off += _jit(seed, s // 3, slow) * amp * 0.7
                off += _jit(seed, s * 7 + 1, fast * 3) * amp * 0.35
                wx = p0x + rx * t + nx * off
                wy = p0y + ry * t + ny * off
                world_pts.append((wx, wy))
                screen_pts.append(to_screen(wx, wy))

            _stroke(screen_pts, w_glow, c_glow)
            _stroke(screen_pts, w_body, c_body)
            _stroke(screen_pts, w_core, c_core)

            # short dead-end tendrils off interior nodes
            for s in range(2, steps - 1):
                if abs(_jit(seed, s * 31, slow)) > (1.0 - _FORK_CHANCE):
                    ox, oy = world_pts[s]
                    fdir = _jit(seed, s, fast) * math.pi
                    flen = _FORK_LEN * (0.4 + 0.6 * abs(_jit(seed, s + 5, fast)))
                    tx, ty = ox + math.cos(fdir) * flen, oy + math.sin(fdir) * flen
                    mx = (ox + tx) * 0.5 + nx * _jit(seed, s + 2, fast) * _JITTER * 0.5
                    my = (oy + ty) * 0.5 + ny * _jit(seed, s + 2, fast) * _JITTER * 0.5
                    fork = [to_screen(ox, oy), to_screen(mx, my), to_screen(tx, ty)]
                    _stroke(fork, 2.2 * scale, c_fork)
                    _stroke(fork, 1.0 * scale, c_core)

            # spark burst at the far node (a struck creature)
            hub = screen_pts[-1]
            rl.draw_circle_v(hub, 3.2 * scale, c_hub)
            for k in range(6):
                ang = _jit(seed, k, fast) * math.pi
                rad = (5.0 + 9.0 * abs(_jit(seed, k + 9, fast))) * scale
                rl.draw_line_ex(hub, rl.Vector2(hub.x + math.cos(ang) * rad, hub.y + math.sin(ang) * rad), 1.4 * scale, c_spark)
