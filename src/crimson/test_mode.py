from __future__ import annotations

"""Test mode: a debug-only flag for trying out in-development mechanics
(currently: forces a Fork Shot bonus to spawn every few seconds). Not native
behavior - mirrors the existing `debug.py` flag pattern."""

import os

_TEST_MODE_OVERRIDE: bool | None = None


def set_test_mode_enabled(enabled: bool) -> None:
    global _TEST_MODE_OVERRIDE
    _TEST_MODE_OVERRIDE = enabled


def test_mode_enabled() -> bool:
    if _TEST_MODE_OVERRIDE is not None:
        return _TEST_MODE_OVERRIDE
    return os.environ.get("CRIMSON_TEST_MODE") == "1"
