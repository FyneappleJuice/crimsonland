from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from grim.raylib_api import rl

from .render_pipeline import RaylibDrawScope, RenderPipeline, WindowSink
from .view import View

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_KEY = rl.KeyboardKey.KEY_F12


def _make_process_dpi_aware() -> None:
    """Windows only: opt the process into real physical pixels before the window
    is created.

    Without this, a DPI-unaware process on a scaled display gets its window
    virtualised: raylib renders at the requested size and Windows bitmap-scales
    the result to the screen (blurry), while ``GetMousePosition`` and
    ``GetScreenWidth`` end up in different unit spaces - which made the aim
    reticle snap to a point in a screen corner (the letterbox mouse map divided
    by a window size that was off by the DPI factor).
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # PER_MONITOR_AWARE_V2 (Win10 1703+).
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        # SYSTEM_DPI_AWARE (Win8.1+).
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class RunViewHooks:
    def should_close(self) -> bool:
        return False

    def consume_screenshot_request(self) -> bool:
        return False


class ViewRunHooks(RunViewHooks):
    def __init__(self, view: object) -> None:
        self._view = view

    def should_close(self) -> bool:
        should_close_fn = getattr(self._view, "should_close", None)
        if callable(should_close_fn):
            return bool(should_close_fn())
        close_requested = getattr(self._view, "close_requested", False)
        if isinstance(close_requested, bool):
            return close_requested
        return False

    def consume_screenshot_request(self) -> bool:
        consume_fn = getattr(self._view, "consume_screenshot_request", None)
        if callable(consume_fn):
            return bool(consume_fn())
        return False


def _next_screenshot_index(directory: Path) -> int:
    if not directory.exists():
        return 1
    max_index = 0
    for entry in directory.glob("*.png"):
        stem = entry.stem
        if stem.isdigit():
            max_index = max(max_index, int(stem))
    return max_index + 1


def run_view(
    view: View,
    *,
    width: int = 1280,
    height: int = 720,
    title: str = "Crimsonland",
    fps: int = 60,
    config_flags: int = 0,
    exit_key: int | None = None,
    hooks: RunViewHooks | None = None,
    virtual_size: tuple[int, int] | None = None,
    on_virtual_resize: Callable[[int, int], None] | None = None,
) -> None:
    """Run a Raylib window with a pluggable debug view.

    ``virtual_size`` is the base logical resolution. The frame is rendered to an
    off-screen target whose size tracks the window's aspect ratio (locked on the
    shorter axis to the base size) and blitted to fill the whole window with a
    uniform scale - no distortion, no bars - while the raylib screen / mouse
    accessors are patched to virtual space. ``on_virtual_resize(vw, vh)`` is
    called with the logical size whenever it changes (initially and on resize).
    Omit ``virtual_size`` (the default) to draw straight to the window as before.
    """
    _make_process_dpi_aware()
    if config_flags:
        rl.set_config_flags(config_flags)
    rl.init_window(width, height, title)
    if exit_key is not None:
        rl.set_exit_key(exit_key)
    rl.set_target_fps(fps)
    run_hooks = hooks if hooks is not None else RunViewHooks()
    render_pipeline = RenderPipeline(
        sink=WindowSink(),
        draw_scope=RaylibDrawScope(raylib=rl),
    )

    letterbox = None
    vt_box: list = []  # single-slot cell so the nested helper can swap the texture
    vt_size: list = []  # [(vw, vh)] currently allocated
    base_w = base_h = 0

    def _sync_virtual_target() -> tuple[int, int]:
        """Resize the off-screen target to match the current window aspect."""
        ww, wh = letterbox.real_window_size()
        vw, vh = letterbox.virtual_for_window(base_w, base_h, ww, wh)
        if vt_size != [(vw, vh)] or not vt_box:
            if vt_box:
                rl.unload_render_texture(vt_box[0])
                vt_box.clear()
            target = rl.load_render_texture(vw, vh)
            rl.set_texture_filter(target.texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
            vt_box.append(target)
            vt_size[:] = [(vw, vh)]
            if on_virtual_resize is not None:
                on_virtual_resize(vw, vh)
        return vw, vh

    if virtual_size is not None:
        from . import letterbox as _letterbox

        letterbox = _letterbox
        base_w = max(1, int(virtual_size[0]))
        base_h = max(1, int(virtual_size[1]))
        letterbox.install(base_w, base_h)
        _sync_virtual_target()

    def _draw_letterboxed() -> None:
        vw, vh = _sync_virtual_target()
        ww, wh = letterbox.real_window_size()
        target = vt_box[0]
        rl.begin_drawing()
        try:
            letterbox.begin_target()
            rl.begin_texture_mode(target)
            try:
                rl.clear_background(rl.BLACK)
                view.draw()
            finally:
                rl.end_texture_mode()
                letterbox.end_target()
            rl.clear_background(rl.BLACK)
            src = rl.Rectangle(0.0, 0.0, float(vw), float(-vh))  # flip Y: RT origin is bottom-left
            rl.draw_texture_pro(
                target.texture,
                src,
                rl.Rectangle(0.0, 0.0, float(ww), float(wh)),
                rl.Vector2(0.0, 0.0),
                0.0,
                rl.WHITE,
            )
        finally:
            rl.end_drawing()

    try:
        view.open()
        screenshot_dir = SCREENSHOT_DIR if SCREENSHOT_DIR.is_absolute() else Path.cwd() / SCREENSHOT_DIR
        screenshot_index = _next_screenshot_index(screenshot_dir)
        while not rl.window_should_close():
            dt = rl.get_frame_time()
            view.update(dt)
            take_screenshot = rl.is_key_pressed(SCREENSHOT_KEY)
            if run_hooks.consume_screenshot_request():
                take_screenshot = True
            if letterbox is not None:
                _draw_letterboxed()
            else:
                render_pipeline.draw(
                    draw_frame=view.draw,
                    width=rl.get_render_width(),
                    height=rl.get_render_height(),
                )
                render_pipeline.present()
            if run_hooks.should_close():
                break
            if take_screenshot:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{screenshot_index:05d}.png"
                rl.take_screenshot(filename)
                src = Path.cwd() / filename
                if src.exists():
                    shutil.move(str(src), str(screenshot_dir / filename))
                screenshot_index += 1
    finally:
        try:
            view.close()
        finally:
            render_pipeline.close()
            if vt_box:
                rl.unload_render_texture(vt_box[0])
                vt_box.clear()
            if letterbox is not None:
                letterbox.uninstall()
            rl.close_window()


def run_window(
    width: int = 1280,
    height: int = 720,
    title: str = "Crimsonland",
    fps: int = 60,
) -> None:
    """Open a minimal Raylib window for the reference implementation."""

    class _EmptyView:
        def open(self) -> None:
            return None

        def update(self, dt: float) -> None:
            return None

        def draw(self) -> None:
            rl.clear_background(rl.BLACK)

        def close(self) -> None:
            return None

    run_view(_EmptyView(), width=width, height=height, title=title, fps=fps)
