from __future__ import annotations

"""Roguelite relics (rewrite-only, NOT native).

Relics persist across runs. Monsters drop them (auto-collected into the global
inventory); before a Survival run the player places them into a 5x5 relic grid,
and every placed relic's stat mods apply for that run.

Relics can occupy more than one grid cell (see `RELIC_SHAPE`): a placement is
tracked as one (relic_id, anchor row, anchor col) triple rather than a per-cell
id, so a 1x2 relic is one object spanning two cells for hover/pickup purposes,
not two independent 1x1s.
"""

from enum import IntEnum
from pathlib import Path

import msgspec

from ..progression.modifiers import StatMod
from ..test_mode import test_mode_enabled

GRID_W = 5
GRID_H = 5
GRID_SLOTS = GRID_W * GRID_H

_RELICS_FILE = "relics.json"


class RelicId(IntEnum):
    # 1 (+1 Clip Size) and 2 (+5% Fire Rate) were the original placeholder
    # test relics - removed; _normalize() strips them out of old saves.

    # Deadeye pacts (meta/relics_impl/deadeye_pact.py, ricochet.py,
    # gathering_winds.py) - each drops at one of 3 fixed strengths instead of
    # the low/medium/high grid-tier system being rolled per-instance; see
    # each impl module's TIER_* tables for the numbers.
    DEADEYE_PACT_LOW = 10
    DEADEYE_PACT_MEDIUM = 11
    DEADEYE_PACT_HIGH = 12
    RICOCHET_LOW = 13
    RICOCHET_MEDIUM = 14
    RICOCHET_HIGH = 15
    GATHERING_WINDS_LOW = 16
    GATHERING_WINDS_MEDIUM = 17
    GATHERING_WINDS_HIGH = 18

    # Slayer pacts (meta/relics_impl/slayer_pact.py, critical_mass.py, leech.py)
    SLAYER_PACT_LOW = 19
    SLAYER_PACT_MEDIUM = 20
    SLAYER_PACT_HIGH = 21
    CRITICAL_MASS_LOW = 22
    CRITICAL_MASS_MEDIUM = 23
    CRITICAL_MASS_HIGH = 24
    LEECH_LOW = 25
    LEECH_MEDIUM = 26
    LEECH_HIGH = 27


# Not native: with --test-mode, init_relics tops the inventory up so exactly
# one of each of these exists (owned or placed) - every pact at every tier,
# ready to try. Counts what's already placed, so it never creates duplicates.
_TEST_MODE_SEED_OWNED_RELICS: tuple[int, ...] = tuple(RelicId)

# Pact family (the pact itself, regardless of tier). Only one relic per
# family can be placed at a time - see _family_conflict.
RELIC_FAMILY: dict[int, str] = {
    RelicId.DEADEYE_PACT_LOW: "deadeye",
    RelicId.DEADEYE_PACT_MEDIUM: "deadeye",
    RelicId.DEADEYE_PACT_HIGH: "deadeye",
    RelicId.RICOCHET_LOW: "ricochet",
    RelicId.RICOCHET_MEDIUM: "ricochet",
    RelicId.RICOCHET_HIGH: "ricochet",
    RelicId.GATHERING_WINDS_LOW: "gathering_winds",
    RelicId.GATHERING_WINDS_MEDIUM: "gathering_winds",
    RelicId.GATHERING_WINDS_HIGH: "gathering_winds",
    RelicId.SLAYER_PACT_LOW: "slayer",
    RelicId.SLAYER_PACT_MEDIUM: "slayer",
    RelicId.SLAYER_PACT_HIGH: "slayer",
    RelicId.CRITICAL_MASS_LOW: "critical_mass",
    RelicId.CRITICAL_MASS_MEDIUM: "critical_mass",
    RelicId.CRITICAL_MASS_HIGH: "critical_mass",
    RelicId.LEECH_LOW: "leech",
    RelicId.LEECH_MEDIUM: "leech",
    RelicId.LEECH_HIGH: "leech",
}

_TIER_SUFFIX = {"Low": " (Low)", "Medium": " (Medium)", "High": " (High)"}

RELIC_NAME: dict[int, str] = {
    RelicId.DEADEYE_PACT_LOW: "Pact of the Deadeye (Low)",
    RelicId.DEADEYE_PACT_MEDIUM: "Pact of the Deadeye (Medium)",
    RelicId.DEADEYE_PACT_HIGH: "Pact of the Deadeye (High)",
    RelicId.RICOCHET_LOW: "Pact of Ricochet (Low)",
    RelicId.RICOCHET_MEDIUM: "Pact of Ricochet (Medium)",
    RelicId.RICOCHET_HIGH: "Pact of Ricochet (High)",
    RelicId.GATHERING_WINDS_LOW: "Pact of Gathering Winds (Low)",
    RelicId.GATHERING_WINDS_MEDIUM: "Pact of Gathering Winds (Medium)",
    RelicId.GATHERING_WINDS_HIGH: "Pact of Gathering Winds (High)",
    RelicId.SLAYER_PACT_LOW: "Pact of the Slayer (Low)",
    RelicId.SLAYER_PACT_MEDIUM: "Pact of the Slayer (Medium)",
    RelicId.SLAYER_PACT_HIGH: "Pact of the Slayer (High)",
    RelicId.CRITICAL_MASS_LOW: "Critical Mass (Low)",
    RelicId.CRITICAL_MASS_MEDIUM: "Critical Mass (Medium)",
    RelicId.CRITICAL_MASS_HIGH: "Critical Mass (High)",
    RelicId.LEECH_LOW: "Leech (Low)",
    RelicId.LEECH_MEDIUM: "Leech (Medium)",
    RelicId.LEECH_HIGH: "Leech (High)",
}

# Short label drawn inside a placed relic's grid cells.
RELIC_LABEL: dict[int, str] = {
    RelicId.DEADEYE_PACT_LOW: "Far L",
    RelicId.DEADEYE_PACT_MEDIUM: "Far M",
    RelicId.DEADEYE_PACT_HIGH: "Far H",
    RelicId.RICOCHET_LOW: "Chain L",
    RelicId.RICOCHET_MEDIUM: "Chain M",
    RelicId.RICOCHET_HIGH: "Chain H",
    RelicId.GATHERING_WINDS_LOW: "Wind L",
    RelicId.GATHERING_WINDS_MEDIUM: "Wind M",
    RelicId.GATHERING_WINDS_HIGH: "Wind H",
    RelicId.SLAYER_PACT_LOW: "Slay L",
    RelicId.SLAYER_PACT_MEDIUM: "Slay M",
    RelicId.SLAYER_PACT_HIGH: "Slay H",
    RelicId.CRITICAL_MASS_LOW: "Crit L",
    RelicId.CRITICAL_MASS_MEDIUM: "Crit M",
    RelicId.CRITICAL_MASS_HIGH: "Crit H",
    RelicId.LEECH_LOW: "Leech L",
    RelicId.LEECH_MEDIUM: "Leech M",
    RelicId.LEECH_HIGH: "Leech H",
}

# (width, height) in grid cells. Unlisted ids default to 1x1. The pact
# relics are all 1x1 for now - the 3x4 grid + polyomino low/medium/high
# footprint (2/3/4 cells) is a separate, not-yet-built rework; see the
# relics_impl modules' own docstrings.
RELIC_SHAPE: dict[int, tuple[int, int]] = {}


def relic_shape(relic_id: int) -> tuple[int, int]:
    return RELIC_SHAPE.get(int(relic_id), (1, 1))


def relic_stat_mods(relic_id: int) -> list[StatMod]:
    # No relic is a plain stat mod right now - the pacts all have custom
    # mechanics, hooked in through active_relic_ids() instead. Kept as the
    # extension point for future plain-stat relics.
    _ = relic_id
    return []


class PlacedRelic(msgspec.Struct):
    relic_id: int
    row: int  # top-left anchor cell
    col: int


class RelicSave(msgspec.Struct):
    # Global inventory: relic ids the player owns but has NOT placed in the grid.
    owned: list[int] = msgspec.field(default_factory=list)
    # Relics placed in the 5x5 grid, one entry per relic instance (not per cell).
    placements: list[PlacedRelic] = msgspec.field(default_factory=list)


# --- module state --------------------------------------------------------

_STATE: RelicSave | None = None
_PATH: Path | None = None
_ACTIVE_RUN_MODS: tuple[StatMod, ...] = ()
# Not native: a frozen snapshot of which relic ids are active for the run
# about to start, alongside _ACTIVE_RUN_MODS - the pact relics have custom
# mechanics (chain-on-hit, kill-streak tracking, ...) that a plain StatMod
# can't express, so their gameplay hooks check membership here directly
# instead of going through the stat pipeline. Frozen at begin_run() for the
# same determinism/replay reasons the stat mods are.
_ACTIVE_RELIC_IDS: tuple[int, ...] = ()


def _default_state() -> RelicSave:
    return RelicSave(owned=[], placements=[])


_KNOWN_RELIC_IDS = frozenset(int(r) for r in RelicId)


def _normalize(state: RelicSave) -> RelicSave:
    # Drop ids that no longer exist (the removed +1 Clip / +5% Fire Rate
    # placeholders) so an old save doesn't carry dead entries around.
    return RelicSave(
        owned=[int(r) for r in (state.owned or []) if int(r) in _KNOWN_RELIC_IDS],
        placements=[p for p in (state.placements or []) if int(p.relic_id) in _KNOWN_RELIC_IDS],
    )


def init_relics(base_dir: Path | str) -> RelicSave:
    """Load relics.json from the runtime dir, or seed a fresh profile."""
    global _STATE, _PATH
    _PATH = Path(base_dir) / _RELICS_FILE
    if _PATH.is_file():
        try:
            _STATE = _normalize(msgspec.json.decode(_PATH.read_bytes(), type=RelicSave))
        except Exception:
            _STATE = _default_state()
            save_relics()
    else:
        _STATE = _default_state()
        save_relics()
    if test_mode_enabled():
        # Top up to one of each - counting placed relics too, so a relic
        # sitting in the grid isn't handed out again as a duplicate.
        have = set(_STATE.owned) | {int(p.relic_id) for p in _STATE.placements}
        for relic_id in _TEST_MODE_SEED_OWNED_RELICS:
            if int(relic_id) not in have:
                _STATE.owned.append(int(relic_id))
    return _STATE


def relic_state() -> RelicSave:
    global _STATE
    if _STATE is None:
        _STATE = _default_state()
    return _STATE


def save_relics() -> None:
    if _PATH is None or _STATE is None:
        return
    try:
        _PATH.write_bytes(msgspec.json.encode(_STATE))
    except Exception:
        pass


# --- grid geometry -------------------------------------------------------


def occupied_cells(placement: PlacedRelic) -> list[tuple[int, int]]:
    """(row, col) cells covered by a placement, top-left anchored."""
    w, h = relic_shape(placement.relic_id)
    return [(placement.row + dy, placement.col + dx) for dy in range(h) for dx in range(w)]


def _fits(
    state: RelicSave, row: int, col: int, w: int, h: int, *, ignore_index: int | None = None,
) -> bool:
    if row < 0 or col < 0 or row + h > GRID_H or col + w > GRID_W:
        return False
    occupied: set[tuple[int, int]] = set()
    for i, p in enumerate(state.placements):
        if i == ignore_index:
            continue
        occupied.update(occupied_cells(p))
    return all((row + dy, col + dx) not in occupied for dy in range(h) for dx in range(w))


def _family_conflict(state: RelicSave, relic_id: int) -> bool:
    """True if a relic of the same pact family (any tier) is already placed -
    only one of each pact can be equipped at a time."""
    family = RELIC_FAMILY.get(int(relic_id))
    if family is None:
        return False
    return any(RELIC_FAMILY.get(int(p.relic_id)) == family for p in state.placements)


def family_conflict(relic_id: int) -> bool:
    return _family_conflict(relic_state(), relic_id)


def fits(relic_id: int, row: int, col: int) -> bool:
    """Would relic_id fit anchored at (row, col) against the current grid?
    For the UI to preview a placement before the click actually commits it."""

    st = relic_state()
    if _family_conflict(st, relic_id):
        return False
    w, h = relic_shape(relic_id)
    return _fits(st, row, col, w, h)


def placement_at(row: int, col: int) -> tuple[int, PlacedRelic] | None:
    """The (index, placement) covering (row, col), or None if that cell is empty."""
    for i, p in enumerate(relic_state().placements):
        if (row, col) in occupied_cells(p):
            return i, p
    return None


# --- inventory ops ------------------------------------------------------


def award_relic_drop(relic_id: int) -> None:
    """A monster dropped a relic - auto-collected into the global inventory."""
    relic_state().owned.append(int(relic_id))
    save_relics()


def equip_from_owned(owned_index: int) -> bool:
    """Move owned[owned_index] into the first grid position its shape fits."""
    st = relic_state()
    if not (0 <= owned_index < len(st.owned)):
        return False
    relic_id = st.owned[owned_index]
    if _family_conflict(st, relic_id):
        return False
    w, h = relic_shape(relic_id)
    for row in range(GRID_H):
        for col in range(GRID_W):
            if _fits(st, row, col, w, h):
                st.owned.pop(owned_index)
                st.placements.append(PlacedRelic(relic_id=relic_id, row=row, col=col))
                save_relics()
                return True
    return False  # doesn't fit anywhere


def place_held_relic(relic_id: int, row: int, col: int) -> bool:
    """Place relic_id anchored at (row, col) if its shape fits there.

    Doesn't touch `owned` - the relic-on-cursor lives outside the owned list
    while held (see RelicInventoryView._held), same as the UI already treats it.
    """
    st = relic_state()
    w, h = relic_shape(relic_id)
    if _family_conflict(st, relic_id) or not _fits(st, row, col, w, h):
        return False
    st.placements.append(PlacedRelic(relic_id=relic_id, row=row, col=col))
    save_relics()
    return True


def remove_placement_to_held(index: int) -> int | None:
    """Pop placements[index] without returning it to owned - for picking it back
    up onto the cursor (see place_held_relic's docstring)."""
    st = relic_state()
    if not (0 <= index < len(st.placements)):
        return None
    p = st.placements.pop(index)
    save_relics()
    return p.relic_id


def placed_relic_ids() -> list[int]:
    return [p.relic_id for p in relic_state().placements]


# --- run lifecycle -----------------------------------------------------


def begin_run() -> None:
    """Freeze the placed relics' stat mods for the run about to start."""
    global _ACTIVE_RUN_MODS, _ACTIVE_RELIC_IDS
    ids = placed_relic_ids()
    mods: list[StatMod] = []
    for rid in ids:
        mods.extend(relic_stat_mods(rid))
    _ACTIVE_RUN_MODS = tuple(mods)
    _ACTIVE_RELIC_IDS = tuple(ids)


def end_run() -> None:
    global _ACTIVE_RUN_MODS, _ACTIVE_RELIC_IDS
    _ACTIVE_RUN_MODS = ()
    _ACTIVE_RELIC_IDS = ()


def active_run_stat_mods() -> tuple[StatMod, ...]:
    """Read by progression.refresh_player_stats each sim tick."""
    return _ACTIVE_RUN_MODS


def active_relic_ids() -> tuple[int, ...]:
    """Read by the pact relics' own gameplay hooks - see _ACTIVE_RELIC_IDS."""
    return _ACTIVE_RELIC_IDS


def relic_owned(relic_id: int) -> bool:
    return int(relic_id) in _ACTIVE_RELIC_IDS
