from __future__ import annotations

"""`StatMod` - one typed change to one stat - and the resolver that folds a
pile of them into a `PlayerStats`.

Resolution order per numeric stat (Path of Exile style):

    final = (identity + Σ FLAT) * (1 + Σ INC) * Π (1 + MORE_i)

`OVERRIDE` short-circuits everything (last override wins). `FLAG` entries do
not touch numbers; they add a string to `PlayerStats.flags`.
"""

import enum
from collections.abc import Iterable

import msgspec

from .stats import STAT_IDENTITIES, PlayerStats


class ModOp(enum.Enum):
    FLAT = "flat"          # +N to the stat, before percentages
    INC = "inc"            # +N as "increased" - these sum, then scale once
    MORE = "more"          # +N as "more" - these chain multiplicatively
    OVERRIDE = "override"  # set the stat to N outright (last one wins)
    FLAG = "flag"          # add `stat` to PlayerStats.flags; `value` unused


class StatMod(msgspec.Struct, frozen=True):
    stat: str
    op: ModOp
    value: float = 0.0
    # free-text origin for debugging / tooltips ("perk:fastshot", "affix:searing")
    source: str = ""

    def __post_init__(self) -> None:
        if self.op is ModOp.FLAG:
            return
        if self.stat not in STAT_IDENTITIES:
            raise ValueError(f"StatMod targets unknown stat {self.stat!r}")


def flat(stat: str, value: float, *, source: str = "") -> StatMod:
    return StatMod(stat=stat, op=ModOp.FLAT, value=float(value), source=source)


def increased(stat: str, value: float, *, source: str = "") -> StatMod:
    return StatMod(stat=stat, op=ModOp.INC, value=float(value), source=source)


def more(stat: str, value: float, *, source: str = "") -> StatMod:
    return StatMod(stat=stat, op=ModOp.MORE, value=float(value), source=source)


def override(stat: str, value: float, *, source: str = "") -> StatMod:
    return StatMod(stat=stat, op=ModOp.OVERRIDE, value=float(value), source=source)


def flag(name: str, *, source: str = "") -> StatMod:
    return StatMod(stat=name, op=ModOp.FLAG, source=source)


def resolve_stats(mods: Iterable[StatMod]) -> PlayerStats:
    """Fold `mods` into a `PlayerStats`. Order-independent for numbers."""

    flat_sum: dict[str, float] = {}
    inc_sum: dict[str, float] = {}
    more_terms: dict[str, list[float]] = {}
    overrides: dict[str, float] = {}
    flags: set[str] = set()

    for mod in mods:
        if mod.op is ModOp.FLAG:
            flags.add(mod.stat)
            continue
        if mod.op is ModOp.OVERRIDE:
            overrides[mod.stat] = mod.value
        elif mod.op is ModOp.FLAT:
            flat_sum[mod.stat] = flat_sum.get(mod.stat, 0.0) + mod.value
        elif mod.op is ModOp.INC:
            inc_sum[mod.stat] = inc_sum.get(mod.stat, 0.0) + mod.value
        elif mod.op is ModOp.MORE:
            more_terms.setdefault(mod.stat, []).append(mod.value)

    resolved: dict[str, float] = {}
    touched = set(flat_sum) | set(inc_sum) | set(more_terms) | set(overrides)
    for stat in touched:
        if stat in overrides:
            resolved[stat] = overrides[stat]
            continue
        value = STAT_IDENTITIES[stat] + flat_sum.get(stat, 0.0)
        value *= 1.0 + inc_sum.get(stat, 0.0)
        for term in more_terms.get(stat, ()):
            value *= 1.0 + term
        resolved[stat] = value

    return PlayerStats(**resolved, flags=frozenset(flags))
