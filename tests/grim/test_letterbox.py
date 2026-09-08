from __future__ import annotations

import pytest

from grim import letterbox


@pytest.fixture(autouse=True)
def _reset_letterbox():
    letterbox.uninstall()
    yield
    letterbox.uninstall()


def test_virtual_for_window_matches_window_aspect_locking_short_axis():
    # base 4:3; a 16:9 window keeps height, widens the logical size
    assert letterbox.virtual_for_window(1024, 768, 3840, 2160) == (1365, 768)
    # a window narrower than base keeps width, grows the logical height
    assert letterbox.virtual_for_window(1024, 768, 800, 1200) == (1024, 1536)
    # an exact-match window is the identity
    assert letterbox.virtual_for_window(1024, 768, 1024, 768) == (1024, 768)


def test_virtual_for_window_scale_is_uniform():
    for ww, wh in ((3840, 2160), (1600, 900), (1000, 1400), (1024, 768)):
        vw, vh = letterbox.virtual_for_window(1024, 768, ww, wh)
        assert vw / ww == pytest.approx(vh / wh, rel=1e-3)


def test_mouse_maps_into_virtual_space_and_is_not_clamped(monkeypatch):
    window = [1600, 1000]
    cursor = [800.0, 500.0]

    monkeypatch.setattr(letterbox, "_real_get_screen_width", lambda: window[0])
    monkeypatch.setattr(letterbox, "_real_get_screen_height", lambda: window[1])
    monkeypatch.setattr(
        letterbox, "_real_get_mouse_position", lambda: type("V", (), {"x": cursor[0], "y": cursor[1]})(),
    )

    letterbox.install(1024, 768)
    vw, vh = letterbox.virtual_size()

    # window centre -> virtual centre
    mx, my = letterbox._mouse_virtual()
    assert mx == pytest.approx(vw / 2, rel=1e-3)
    assert my == pytest.approx(vh / 2, rel=1e-3)

    # cursor past the top-left edge stays negative (no snap to a corner)
    cursor[0], cursor[1] = -40.0, -25.0
    mx, my = letterbox._mouse_virtual()
    assert mx < 0.0
    assert my < 0.0


def test_mouse_mapping_follows_a_live_window_resize(monkeypatch):
    window = [1024, 768]
    monkeypatch.setattr(letterbox, "_real_get_screen_width", lambda: window[0])
    monkeypatch.setattr(letterbox, "_real_get_screen_height", lambda: window[1])
    monkeypatch.setattr(letterbox, "_real_get_mouse_position", lambda: type("V", (), {"x": window[0] * 0.25, "y": window[1] * 0.5})())

    letterbox.install(1024, 768)
    mx1, my1 = letterbox._mouse_virtual()

    # maximise the window; the mapping must recompute, not lag a frame
    window[0], window[1] = 3840, 2160
    mx2, my2 = letterbox._mouse_virtual()
    vw, vh = letterbox.virtual_size()

    # cursor is still at 25% / 50% of the window -> same fraction of virtual space
    assert mx2 == pytest.approx(vw * 0.25, rel=1e-3)
    assert my2 == pytest.approx(vh * 0.5, rel=1e-3)
    assert (mx2, my2) != (mx1, my1)
