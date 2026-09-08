from __future__ import annotations

from enum import IntEnum


class GameMode(IntEnum):
    """Known `game_mode` ids from the original config / highscore tables."""

    DEMO = 0
    SURVIVAL = 1
    RUSH = 2
    QUESTS = 3
    TYPO = 4
    TUTORIAL = 8

    # Not a native id: this rewrite-only mode has no equivalent in the original
    # game, so it is assigned a value well outside the native table's range.
    MAPS = 100

