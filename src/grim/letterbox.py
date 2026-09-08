from __future__ import annotations

"""Virtual-resolution scaling for the interactive window.

The game's world, HUD and menu UI are laid out in pixels against a logical
resolution. Only the world camera scales freely to arbitrary window sizes; the
HUD and menus use fixed metrics with native-parity breakpoints. So the frame is
rendered to an off-screen target at a logical resolution and blitted to the
window.

The logical resolution tracks the window's aspect ratio (locked on the shorter
axis to the configured base size), so the blit fills the whole window with a
uniform scale - no distortion and no black bars - while every call site keeps
working unchanged: ``rl.get_screen_*`` in the world renderer / HUD / menus and
``rl.get_mouse_*`` for input are patched to report virtual space.

Every patched accessor derives its result live from the current window size, so
there is no cross-frame staleness when the window is resized. When the window
matches the base size (the default case) the mapping is the identity.
"""

import pyray as rl

# Bind the real raylib accessors once, before install() shadows them.
_real_get_screen_width = rl.get_screen_width
_real_get_screen_height = rl.get_screen_height
_real_get_render_width = rl.get_render_width
_real_get_render_height = rl.get_render_height
_real_get_mouse_position = rl.get_mouse_position
_real_get_mouse_x = rl.get_mouse_x
_real_get_mouse_y = rl.get_mouse_y


class _State:
    installed: bool = False
    # configured base (logical) resolution; 0 => letterbox inactive
    base_w: int = 0
    base_h: int = 0
    # set while run_view is drawing into the letterbox render target, so
    # off-screen render-target work (terrain baking) can defer instead of
    # nesting begin_texture_mode calls
    target_open: bool = False


_S = _State()


def real_window_size() -> tuple[int, int]:
    """Actual OS window size, bypassing the virtual-size patch."""
    return int(_real_get_screen_width()), int(_real_get_screen_height())


def raw_mouse_position() -> tuple[float, float]:
    """Cursor position in real window pixels, bypassing the virtual-space patch."""
    p = _real_get_mouse_position()
    return float(p.x), float(p.y)


def virtual_for_window(base_w: int, base_h: int, ww: int, wh: int) -> tuple[int, int]:
    """Logical size that matches the window's aspect, locked on the shorter axis
    to the base size so the blit fills the window with a uniform scale."""
    base_w = max(1, int(base_w))
    base_h = max(1, int(base_h))
    ww = max(1, int(ww))
    wh = max(1, int(wh))
    win_aspect = ww / wh
    base_aspect = base_w / base_h
    if win_aspect >= base_aspect:
        return max(base_w, round(base_h * win_aspect)), base_h
    return base_w, max(base_h, round(base_w / win_aspect))


def virtual_size() -> tuple[int, int]:
    """Current logical size, derived live from the window (base size if inactive)."""
    if _S.base_w <= 0:
        return real_window_size()
    ww, wh = real_window_size()
    return virtual_for_window(_S.base_w, _S.base_h, ww, wh)


def begin_target() -> None:
    _S.target_open = True


def end_target() -> None:
    _S.target_open = False


def target_open() -> bool:
    """True while run_view holds the letterbox render target open."""
    return _S.target_open


def _mouse_virtual() -> tuple[float, float]:
    p = _real_get_mouse_position()
    ww, wh = real_window_size()
    if _S.base_w <= 0 or ww <= 0 or wh <= 0:
        return float(p.x), float(p.y)
    vw, vh = virtual_for_window(_S.base_w, _S.base_h, ww, wh)
    # Scale window pixels into virtual space. Do NOT clamp: native
    # `get_mouse_position` returns out-of-bounds values when the cursor leaves
    # the window, and callers that need a bounded value clamp it themselves
    # (e.g. base_gameplay_mode._update_ui_mouse). Clamping here made the aim
    # reticle snap to a window corner whenever the cursor slipped past an edge.
    return float(p.x) * (vw / ww), float(p.y) * (vh / wh)


def _patched_get_mouse_position():
    vx, vy = _mouse_virtual()
    return rl.Vector2(vx, vy)


def _patched_get_mouse_x() -> int:
    return int(_mouse_virtual()[0])


def _patched_get_mouse_y() -> int:
    return int(_mouse_virtual()[1])


def _patched_get_screen_width() -> int:
    return int(virtual_size()[0]) if _S.base_w > 0 else int(_real_get_screen_width())


def _patched_get_screen_height() -> int:
    return int(virtual_size()[1]) if _S.base_w > 0 else int(_real_get_screen_height())


def _patched_get_render_width() -> int:
    return int(virtual_size()[0]) if _S.base_w > 0 else int(_real_get_render_width())


def _patched_get_render_height() -> int:
    return int(virtual_size()[1]) if _S.base_w > 0 else int(_real_get_render_height())


def install(base_w: int, base_h: int) -> None:
    """Route the raylib screen / mouse accessors through the virtual mapping,
    for a base (logical) resolution of ``base_w`` x ``base_h``."""
    _S.base_w = max(1, int(base_w))
    _S.base_h = max(1, int(base_h))
    if _S.installed:
        return
    rl.get_mouse_position = _patched_get_mouse_position
    rl.get_mouse_x = _patched_get_mouse_x
    rl.get_mouse_y = _patched_get_mouse_y
    rl.get_screen_width = _patched_get_screen_width
    rl.get_screen_height = _patched_get_screen_height
    rl.get_render_width = _patched_get_render_width
    rl.get_render_height = _patched_get_render_height
    _S.installed = True


def uninstall() -> None:
    if not _S.installed:
        _S.base_w = _S.base_h = 0
        return
    rl.get_mouse_position = _real_get_mouse_position
    rl.get_mouse_x = _real_get_mouse_x
    rl.get_mouse_y = _real_get_mouse_y
    rl.get_screen_width = _real_get_screen_width
    rl.get_screen_height = _real_get_screen_height
    rl.get_render_width = _real_get_render_width
    rl.get_render_height = _real_get_render_height
    _S.installed = False
    _S.base_w = _S.base_h = 0
    _S.target_open = False


__all__ = [
    "begin_target",
    "end_target",
    "install",
    "raw_mouse_position",
    "real_window_size",
    "target_open",
    "uninstall",
    "virtual_for_window",
    "virtual_size",
]
