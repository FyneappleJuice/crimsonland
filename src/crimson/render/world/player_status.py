from __future__ import annotations

"""Not native: character-anchored player status.

- A depleting red health ring around the player.
- The current clip ammo as a number at the player's upper-right.
- Active timed power-ups as an icon stack at the player's upper-left, oldest
  (front of the FIFO queue) nearest the character and newer ones stacking away
  upward, each with its remaining seconds in the icon's top-left corner.

``ui/hud.py`` suppresses the top-of-screen heart / health bar / ammo pips while
``HUD_VITALS_ON_CHARACTER`` is set, and the sliding bonus panel while
``HUD_POWERUP_ON_CHARACTER`` is set.
"""

import math

from grim.assets import TextureId
from grim.fonts.small import draw_small_text
from grim.geom import Vec2
from grim.math import clamp
from grim.raylib_api import rl

from ...bonuses.ids import BonusId
from ...sim.state_types import PlayerState
from .bonus_icons import draw_blade_icon, draw_fork_icon
from .context import WorldRenderCtx

# Ring geometry in world pixels, before the view scale is applied.
_RING_INNER = 18.0
_RING_OUTER = 22.5
_RING_SEGMENTS = 64
_LOW_HEALTH_RATIO = 0.30

# Power-up stack, in world pixels before the view scale.
_PU_ICON = 21.0
_PU_GAP = 4.0
_BONUS_ICON_GRID = 4


def _bonus_icon_src(texture: rl.Texture, icon_id: int) -> rl.Rectangle:
    cell_w = float(texture.width) / _BONUS_ICON_GRID
    cell_h = float(texture.height) / _BONUS_ICON_GRID
    col = int(icon_id) % _BONUS_ICON_GRID
    row = int(icon_id) // _BONUS_ICON_GRID
    return rl.Rectangle(col * cell_w, row * cell_h, cell_w, cell_h)


def draw_player_status(
    render_ctx: WorldRenderCtx,
    player: PlayerState,
    *,
    camera: Vec2,
    view_scale: Vec2,
    scale: float,
    alpha: float = 1.0,
) -> None:
    a = clamp(float(alpha), 0.0, 1.0)
    if a <= 1e-3 or float(player.health) <= 0.0:
        return

    screen = render_ctx._world_to_screen_with(player.pos, camera=camera, view_scale=view_scale)
    center = rl.Vector2(float(screen.x), float(screen.y))
    r_in = max(1.0, _RING_INNER * float(scale))
    r_out = max(r_in + 1.0, _RING_OUTER * float(scale))
    ratio = clamp(float(player.health) / 100.0, 0.0, 1.0)

    # Dim full-circle backing so the spent arc still reads as a ring.
    rl.draw_ring(center, r_in, r_out, 0.0, 360.0, _RING_SEGMENTS, rl.Color(15, 0, 0, int(140 * a)))

    if ratio > 0.0:
        # Deplete clockwise from 12 o'clock (-90 deg in raylib's y-down frame).
        start = -90.0
        end = start + 360.0 * ratio
        if ratio <= _LOW_HEALTH_RATIO:
            pulse = math.sin(float(rl.get_time()) * 8.0) * 0.5 + 0.5
            chan = int(40 + 70 * pulse)
            col = rl.Color(255, chan, chan, int(240 * a))
        else:
            col = rl.Color(210, 30, 30, int(225 * a))
        rl.draw_ring(center, r_in, r_out, start, end, _RING_SEGMENTS, col)

    # Current clip ammo, upper-right of the player.
    font = render_ctx.frame.resources.small_font
    ammo = max(0, int(float(player.weapon.ammo)))
    text = str(ammo)
    tx = float(screen.x) + r_out * 0.75
    ty = float(screen.y) - r_out - 11.0 * float(scale)
    shadow = rl.Color(0, 0, 0, int(185 * a))
    fg = rl.Color(240, 240, 240, int(255 * a)) if ammo > 0 else rl.Color(210, 90, 90, int(255 * a))
    if font is not None:
        draw_small_text(font, text, Vec2(tx + 1.0, ty + 1.0), shadow)
        draw_small_text(font, text, Vec2(tx, ty), fg)
    else:
        rl.draw_text(text, int(tx), int(ty), 18, fg)

    _draw_player_powerups(render_ctx, screen=screen, scale=float(scale), r_out=r_out, alpha=a)


def _active_powerup_slots(render_ctx: WorldRenderCtx) -> list:
    state = render_ctx.frame.state
    bonus_hud = getattr(state, "bonus_hud", None)
    if bonus_hud is None:
        return []
    out = []
    for slot in bonus_hud.slots:
        if not slot.active:
            continue
        # Blade / Fork Shot draw their own icon; the rest need a valid sheet cell.
        drawable = int(slot.icon_id) >= 0 or slot.bonus_id in (BonusId.BLADE, BonusId.PROJECTILE_FORK)
        if not drawable:
            continue
        remaining = max(float(slot.timer_value), float(slot.timer_value_alt))
        if remaining > 0.0:
            out.append((slot, remaining))
    return out


def _draw_player_powerups(
    render_ctx: WorldRenderCtx,
    *,
    screen: Vec2,
    scale: float,
    r_out: float,
    alpha: float,
) -> None:
    slots = _active_powerup_slots(render_ctx)
    if not slots:
        return

    resources = render_ctx.frame.resources
    font = resources.small_font
    bonuses_tex = resources.texture(TextureId.BONUSES)

    icon = max(6.0, _PU_ICON * scale)
    pitch = icon + _PU_GAP * scale
    # First (oldest) icon sits just off the ring at the player's upper-left;
    # the stack grows upward, away from the character.
    x = float(screen.x) - r_out - icon - 2.0 * scale
    base_y = float(screen.y) - r_out * 0.4 - icon
    a255 = int(255 * alpha)
    shadow = rl.Color(0, 0, 0, int(195 * alpha))

    for i, (slot, remaining) in enumerate(slots):
        y = base_y - i * pitch
        if slot.bonus_id == BonusId.BLADE:
            draw_blade_icon(render_ctx, x + icon * 0.5, y + icon * 0.5, icon, alpha)
        elif slot.bonus_id == BonusId.PROJECTILE_FORK:
            draw_fork_icon(x + icon * 0.5, y + icon * 0.5, icon, alpha)
        else:
            src = _bonus_icon_src(bonuses_tex, int(slot.icon_id))
            dst = rl.Rectangle(x, y, icon, icon)
            rl.draw_texture_pro(
                bonuses_tex, src, dst, rl.Vector2(0.0, 0.0), 0.0, rl.Color(255, 255, 255, a255),
            )

        secs = max(0, int(math.ceil(remaining)))
        label = str(secs)
        chip_w = (len(label) * 6.0 + 4.0) * max(0.6, min(1.0, scale))
        rl.draw_rectangle(int(x - 1.0), int(y - 1.0), int(chip_w), int(11.0 * max(0.7, min(1.0, scale)) + 2.0), rl.Color(0, 0, 0, int(150 * alpha)))
        tcol = rl.Color(245, 245, 245, a255) if secs > 3 else rl.Color(255, 120, 120, a255)
        if font is not None:
            draw_small_text(font, label, Vec2(x + 1.0, y + 0.5), shadow)
            draw_small_text(font, label, Vec2(x, y - 0.5), tcol)
        else:
            rl.draw_text(label, int(x), int(y), 12, tcol)


def draw_players_status(
    render_ctx: WorldRenderCtx,
    *,
    camera: Vec2,
    view_scale: Vec2,
    scale: float,
    alpha: float = 1.0,
) -> None:
    for player in render_ctx.frame.players:
        if float(player.health) > 0.0:
            draw_player_status(
                render_ctx,
                player,
                camera=camera,
                view_scale=view_scale,
                scale=scale,
                alpha=alpha,
            )


__all__ = ["draw_player_status", "draw_players_status"]
