from __future__ import annotations

"""Test mode: a debug-only flag for trying out in-development mechanics
(currently: forces a Fork Shot bonus to spawn every few seconds). Not native
behavior - mirrors the existing `debug.py` flag pattern."""

import os

_TEST_MODE_OVERRIDE: bool | None = None
_ALPHA_BUILD_OVERRIDE: bool | None = None


def set_test_mode_enabled(enabled: bool) -> None:
    global _TEST_MODE_OVERRIDE
    _TEST_MODE_OVERRIDE = enabled


def test_mode_enabled() -> bool:
    if _TEST_MODE_OVERRIDE is not None:
        return _TEST_MODE_OVERRIDE
    return os.environ.get("CRIMSON_TEST_MODE") == "1"


def set_alpha_build_enabled(enabled: bool) -> None:
    """Not native: distinguishes the packaged alpha-tester build (which
    force-enables test_mode unconditionally, see build_scripts/launch_alpha.py)
    from a normal local --test-mode/CRIMSON_TEST_MODE dev launch - some
    test-mode content (ad hoc weapon drops, starting perks for whatever a
    session happens to be debugging) is only meant for local use, not for
    what actually ships to a tester."""
    global _ALPHA_BUILD_OVERRIDE
    _ALPHA_BUILD_OVERRIDE = enabled


def alpha_build_enabled() -> bool:
    if _ALPHA_BUILD_OVERRIDE is not None:
        return _ALPHA_BUILD_OVERRIDE
    return os.environ.get("CRIMSON_ALPHA_BUILD") == "1"
