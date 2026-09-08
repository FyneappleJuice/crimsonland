from __future__ import annotations

"""Data-driven stat / modifier layer for roguelite build depth.

This package is intentionally separate from `crimson.perks`, which is a
faithful port of the original game's hard-wired perk effects. `progression`
is the additive system new content (extra perks, weapon affixes, map
modifiers, curses) plugs into:

- `stats.PlayerStats` - a flat block of named, defaulted numbers plus a set
  of boolean `flags`, recomputed every tick.
- `modifiers.StatMod` - one typed change to one stat (`+flat`, `%increased`,
  `%more`, `override`, or a `flag`). Content is a list of these, not code.
- `sources` - collects the `StatMod`s a player currently has (from perks,
  and later affixes / modifiers) and resolves them into a `PlayerStats`.

See `README.md` for how to migrate an existing hard-wired perk onto this
layer without changing its numbers.
"""

from .modifiers import ModOp, StatMod, resolve_stats
from .sources import (
    PERK_MECHANICAL,
    PERK_STAT_MODS,
    collect_player_stat_mods,
    refresh_player_stats,
    resolve_player_stats,
    resolve_team_stats,
)
from .stats import PlayerStats

__all__ = [
    "PERK_MECHANICAL",
    "PERK_STAT_MODS",
    "ModOp",
    "PlayerStats",
    "StatMod",
    "collect_player_stat_mods",
    "refresh_player_stats",
    "resolve_player_stats",
    "resolve_stats",
    "resolve_team_stats",
]
