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

from ..progression.modifiers import StatMod, flat, more

GRID_W = 5
GRID_H = 5
GRID_SLOTS = GRID_W * GRID_H

# Relics granted on a fresh profile (no relics.json yet) - handy for testing.
SEED_RELIC_COUNT = 8
SEED_FIRE_RATE_RELIC_COUNT = 6  # exercises 1x2 placement/collision on a fresh profile

_RELICS_FILE = "relics.json"


class RelicId(IntEnum):
    CLIP_PLUS_1 = 1
    FIRE_RATE_PLUS_5 = 2


RELIC_NAME: dict[int, str] = {
    RelicId.CLIP_PLUS_1: "+1 Clip Size",
    RelicId.FIRE_RATE_PLUS_5: "+5% Fire Rate",
}

# Short label drawn inside a placed relic's grid cells.
RELIC_LABEL: dict[int, str] = {
    RelicId.CLIP_PLUS_1: "+1",
    RelicId.FIRE_RATE_PLUS_5: "+5%",
}

# (width, height) in grid cells. Unlisted ids default to 1x1.
RELIC_SHAPE: dict[int, tuple[int, int]] = {
    RelicId.CLIP_PLUS_1: (1, 1),
    RelicId.FIRE_RATE_PLUS_5: (1, 2),
}


def relic_shape(relic_id: int) -> tuple[int, int]:
    return RELIC_SHAPE.get(int(relic_id), (1, 1))


def relic_stat_mods(relic_id: int) -> list[StatMod]:
    if int(relic_id) == RelicId.CLIP_PLUS_1:
        return [flat("clip_size_add", 1.0, source="relic:clip_plus_1")]
    if int(relic_id) == RelicId.FIRE_RATE_PLUS_5:
        return [more("shot_cooldown_mult", -0.05, source="relic:fire_rate_plus_5")]
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


def _default_state() -> RelicSave:
    return RelicSave(
        owned=(
            [int(RelicId.CLIP_PLUS_1)] * SEED_RELIC_COUNT
            + [int(RelicId.FIRE_RATE_PLUS_5)] * SEED_FIRE_RATE_RELIC_COUNT
        ),
        placements=[],
    )


def _normalize(state: RelicSave) -> RelicSave:
    return RelicSave(owned=list(state.owned or []), placements=list(state.placements or []))


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


def fits(relic_id: int, row: int, col: int) -> bool:
    """Would relic_id fit anchored at (row, col) against the current grid?
    For the UI to preview a placement before the click actually commits it."""

    w, h = relic_shape(relic_id)
    return _fits(relic_state(), row, col, w, h)


def placement_at(row: int, col: int) -> tuple[int, PlacedRelic] | None:
    """The (index, placement) covering (row, col), or None if that cell is empty."""
    for i, p in enumerate(relic_state().placements):
        if (row, col) in occupied_cells(p):
            return i, p
    return None


# --- inventory ops ------------------------------------------------------


def award_relic_drop(relic_id: int = int(RelicId.CLIP_PLUS_1)) -> None:
    """A monster dropped a relic - auto-collected into the global inventory."""
    relic_state().owned.append(int(relic_id))
    save_relics()


def equip_from_owned(owned_index: int) -> bool:
    """Move owned[owned_index] into the first grid position its shape fits."""
    st = relic_state()
    if not (0 <= owned_index < len(st.owned)):
        return False
    relic_id = st.owned[owned_index]
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
    if not _fits(st, row, col, w, h):
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
    global _ACTIVE_RUN_MODS
    mods: list[StatMod] = []
    for rid in placed_relic_ids():
        mods.extend(relic_stat_mods(rid))
    _ACTIVE_RUN_MODS = tuple(mods)


def end_run() -> None:
    global _ACTIVE_RUN_MODS
    _ACTIVE_RUN_MODS = ()


def active_run_stat_mods() -> tuple[StatMod, ...]:
    """Read by progression.refresh_player_stats each sim tick."""
    return _ACTIVE_RUN_MODS
