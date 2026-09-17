from __future__ import annotations

from grim.raylib_api import rl

from .shadow import UI_SHADOW_OFFSET, draw_ui_quad_shadow

# Classic menu panel is rendered from the *inset* inner region of ui_menuPanel:
#   - X inset: 1px on each side (uv 1/512 .. 511/512) => 510px wide
#   - Y inset: 1px on each side (uv 1/256 .. 255/256) => 254px tall
#
# When a panel is taller than the base height, the original stretches it using a
# 3-slice: [top][mid][bottom]. The source slice boundaries are at y=130 and y=150
# in the texture (see grim UVs in ui_render_trace).
MENU_PANEL_INSET = 1.0
MENU_PANEL_SRC_SLICE_Y1 = 130.0
MENU_PANEL_SRC_SLICE_Y2 = 150.0

# Destination slice heights observed in the original at scale=1.0 (1024x768).
MENU_PANEL_DST_TOP_H = 138.0
MENU_PANEL_DST_BOTTOM_H = 116.0

# ui_menuPanel.tga (512x256) isn't a plain rectangle: it has a hinge + dangling
# cable-and-plug baked onto the left side and a loose cable/ring hanging off
# the bottom-right, both extending outside the panel's own frame silhouette
# into the texture's transparent margin. Since draw_classic_menu_panel has no
# horizontal slicing (the whole texture width just stretches to dst.width),
# any panel that isn't drawn at the native ~510px design width stretches that
# dangling hardware into a smeared mess.
#
# These bounds (found by scanning alpha rows/columns away from the hinge) crop
# to just the self-contained rectangle - metal frame + interior, no part of
# which extends past the frame's own silhouette - so it can be safely
# stretched to any width. The left edge keeps its ribbed-hinge styling and the
# right edge its plain rivet styling; flip_x mirrors which side gets which.
MENU_PANEL_CLEAN_SRC_X1 = 183.0
MENU_PANEL_CLEAN_SRC_X2 = 495.0

# The trimmed-off top-left cable+plug decoration, as its own source rect, for
# callers that want it back as a fixed-size (unstretched) accent - see
# draw_menu_panel_hardware.
MENU_PANEL_HARDWARE_SRC = (0.0, 10.0, 183.0, 90.0)


def draw_classic_menu_panel(
    texture: rl.Texture,
    *,
    dst: rl.Rectangle,
    tint: rl.Color = rl.WHITE,
    shadow: bool = False,
    flip_x: bool = False,
    border_scale: float | None = None,
    trim_hardware: bool = False,
) -> None:
    """
    Draw a classic menu panel (ui_menuPanel) with the same slicing behavior as the original.

    - Uses inset source rect (1px border skipped) to match the vertex/UV inset.
    - Uses 3-slice only when dst is taller than (top + bottom); otherwise draws a single quad.
    - `border_scale`: native menu screens always resize width and height together, so the
      original ties border chrome thickness to `dst.width`. Screens that vary width and
      height independently (e.g. the relic inventory grid panel) should pass a fixed
      `border_scale` (1.0 for native-thickness borders) so resizing width alone doesn't
      also stretch the top/bottom border art.
    - `trim_hardware`: crop the source to MENU_PANEL_CLEAN_SRC_X1..X2, excluding the
      dangling hinge-cable (left) and loose cable/ring (bottom-right) baked into the
      texture outside its own frame silhouette. Use this for any panel not drawn at the
      native ~510px design width - otherwise that hardware stretches into a smear.
    """

    tex_w = float(texture.width)
    tex_h = float(texture.height)
    if tex_w <= 0.0 or tex_h <= 0.0:
        return

    inset = MENU_PANEL_INSET
    if trim_hardware:
        src_x = MENU_PANEL_CLEAN_SRC_X1
        src_w = max(0.0, MENU_PANEL_CLEAN_SRC_X2 - MENU_PANEL_CLEAN_SRC_X1)
    else:
        src_x = inset
        src_w = max(0.0, tex_w - inset * 2.0)
    src_y = inset
    src_h = max(0.0, tex_h - inset * 2.0)

    # Scale slice heights with the panel width (menu panel uses the same scale factor),
    # unless the caller pins an explicit border_scale.
    # dst.width is already in our "inset" width space (510 at scale=1.0).
    if border_scale is not None:
        scale = float(border_scale)
    else:
        scale = (float(dst.width) / 510.0) if float(dst.width) != 0.0 else 1.0
    top_h = MENU_PANEL_DST_TOP_H * scale
    bottom_h = MENU_PANEL_DST_BOTTOM_H * scale
    mid_h = float(dst.height) - top_h - bottom_h

    origin = rl.Vector2(0.0, 0.0)

    def _src(rect: rl.Rectangle) -> rl.Rectangle:
        if not flip_x:
            return rect
        # Use negative source width to mirror the panel, but keep src.x in-range.
        #
        # With CLAMP wrap, raylib's DrawTexturePro behaves badly when flipping via
        # src.x=rect.x+rect.width (u near 1.0) and negative widths; it can clamp
        # the UVs to the edge texel and collapse the panel to a transparent strip.
        return rl.Rectangle(rect.x, rect.y, -rect.width, rect.height)

    if mid_h <= 0.0:
        src = _src(rl.Rectangle(src_x, src_y, src_w, src_h))
        if shadow:
            draw_ui_quad_shadow(
                texture=texture,
                src=src,
                dst=rl.Rectangle(
                    float(dst.x + UI_SHADOW_OFFSET),
                    float(dst.y + UI_SHADOW_OFFSET),
                    float(dst.width),
                    float(dst.height),
                ),
                origin=origin,
                rotation_deg=0.0,
            )
        rl.draw_texture_pro(texture, src, dst, origin, 0.0, tint)
        return

    # Source slice rects (in texture pixels, with 1px inset).
    src_top = _src(rl.Rectangle(src_x, src_y, src_w, max(0.0, MENU_PANEL_SRC_SLICE_Y1 - inset)))
    src_mid = _src(
        rl.Rectangle(src_x, MENU_PANEL_SRC_SLICE_Y1, src_w, max(0.0, MENU_PANEL_SRC_SLICE_Y2 - MENU_PANEL_SRC_SLICE_Y1)),
    )
    src_bot = _src(rl.Rectangle(src_x, MENU_PANEL_SRC_SLICE_Y2, src_w, max(0.0, (tex_h - inset) - MENU_PANEL_SRC_SLICE_Y2)))

    # Destination slices.
    dst_top = rl.Rectangle(dst.x, dst.y, float(dst.width), float(top_h))
    dst_mid = rl.Rectangle(dst.x, dst.y + float(top_h), float(dst.width), float(mid_h))
    dst_bot = rl.Rectangle(dst.x, dst.y + float(top_h) + float(mid_h), float(dst.width), float(bottom_h))

    if shadow:
        draw_ui_quad_shadow(
            texture=texture,
            src=src_top,
            dst=rl.Rectangle(
                float(dst_top.x + UI_SHADOW_OFFSET),
                float(dst_top.y + UI_SHADOW_OFFSET),
                float(dst_top.width),
                float(dst_top.height),
            ),
            origin=origin,
            rotation_deg=0.0,
        )
        draw_ui_quad_shadow(
            texture=texture,
            src=src_mid,
            dst=rl.Rectangle(
                float(dst_mid.x + UI_SHADOW_OFFSET),
                float(dst_mid.y + UI_SHADOW_OFFSET),
                float(dst_mid.width),
                float(dst_mid.height),
            ),
            origin=origin,
            rotation_deg=0.0,
        )
        draw_ui_quad_shadow(
            texture=texture,
            src=src_bot,
            dst=rl.Rectangle(
                float(dst_bot.x + UI_SHADOW_OFFSET),
                float(dst_bot.y + UI_SHADOW_OFFSET),
                float(dst_bot.width),
                float(dst_bot.height),
            ),
            origin=origin,
            rotation_deg=0.0,
        )

    rl.draw_texture_pro(texture, src_top, dst_top, origin, 0.0, tint)
    rl.draw_texture_pro(texture, src_mid, dst_mid, origin, 0.0, tint)
    rl.draw_texture_pro(texture, src_bot, dst_bot, origin, 0.0, tint)


def draw_menu_panel_hardware(
    texture: rl.Texture,
    *,
    panel: rl.Rectangle,
    flip_x: bool = False,
    tint: rl.Color = rl.WHITE,
    scale: float = 1.0,
) -> None:
    """Draw the cable+plug decoration (MENU_PANEL_HARDWARE_SRC) at a fixed,
    unstretched size, anchored to `panel`'s top-left corner (top-right when
    flip_x). Pair with draw_classic_menu_panel(..., trim_hardware=True) to get
    the clean stretchable body plus this as a separate, undistorted accent."""

    sx, sy, sw, sh = MENU_PANEL_HARDWARE_SRC
    dw, dh = sw * scale, sh * scale
    top_pad = 8.0 * scale
    if not flip_x:
        src = rl.Rectangle(sx, sy, sw, sh)
        dst = rl.Rectangle(panel.x - dw, panel.y + top_pad, dw, dh)
    else:
        src = rl.Rectangle(sx, sy, -sw, sh)
        dst = rl.Rectangle(panel.x + panel.width, panel.y + top_pad, dw, dh)
    rl.draw_texture_pro(texture, src, dst, rl.Vector2(0.0, 0.0), 0.0, tint)
