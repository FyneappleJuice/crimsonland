from __future__ import annotations

"""Roguelite relics (rewrite-only, NOT native).

Relics persist across runs. Monsters drop them (auto-collected into the global
inventory); before a Survival run the player places them into a 5x5 relic grid,
and every placed relic's stat mods apply for that run.

For now every relic is `+1 clip size`.
"""

import json
from enum import IntEnum
from pathlib import Path

import msgspec

from ..progression.modifiers import StatMod, flat

GRID_W = 5
GRID_H = 5
GRID_SLOTS = GRID_W * GRID_H

# Relics granted on a fresh profile (no relics.json yet) - handy for testing.
SEED_RELIC_COUNT = 8

_RELICS_FILE = "relics.json"


class RelicId(IntEnum):
    CLIP_PLUS_1 = 1


RELIC_NAME: dict[int, str] = {
    RelicId.CLIP_PLUS_1: "+1 Clip Size",
}


def relic_stat_mods(relic_id: int) -> list[StatMod]:
    if int(relic_id) == RelicId.CLIP_PLUS_1:
        return [flat("clip_size_add", 1.0, source="relic:clip_plus_1")]
    return []


class RelicSave(msgspec.Struct):
    # Global inventory: relic ids the player owns but has NOT placed in the grid.
    owned: list[int] = msgspec.field(default_factory=list)
    # 5x5 grid, one relic id per slot (0 = empty).
    grid: list[int] = msgspec.field(default_factory=lambda: [0] * GRID_SLOTS)


# --- module state --------------------------------------------------------

_STATE: RelicSave | None = None
_PATH: Path | None = None
_ACTIVE_RUN_MODS: tuple[StatMod, ...] = ()


def _default_state() -> RelicSave:
    return RelicSave(
        owned=[int(RelicId.CLIP_PLUS_1)] * SEED_RELIC_COUNT,
        grid=[0] * GRID_SLOTS,
    )


def _normalize(state: RelicSave) -> RelicSave:
    grid = list(state.grid or [])
    if len(grid) < GRID_SLOTS:
        grid += [0] * (GRID_SLOTS - len(grid))
    elif len(grid) > GRID_SLOTS:
        grid = grid[:GRID_SLOTS]
    return RelicSave(owned=list(state.owned or []), grid=grid)


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
        _PATH.write_text(json.dumps({"owned": list(_STATE.owned), "grid": list(_STATE.grid)}))
    except Exception:
        pass


# --- inventory ops ------------------------------------------------------


def award_relic_drop(relic_id: int = int(RelicId.CLIP_PLUS_1)) -> None:
    """A monster dropped a relic - auto-collected into the global inventory."""
    relic_state().owned.append(int(relic_id))
    save_relics()


def equip_from_owned(owned_index: int) -> bool:
    """Move owned[owned_index] into the first empty grid slot."""
    st = relic_state()
    if not (0 <= owned_index < len(st.owned)):
        return False
    for slot in range(GRID_SLOTS):
        if st.grid[slot] == 0:
            st.grid[slot] = st.owned.pop(owned_index)
            save_relics()
            return True
    return False  # grid full


def unequip_slot(slot: int) -> bool:
    st = relic_state()
    if not (0 <= slot < GRID_SLOTS) or st.grid[slot] == 0:
        return False
    st.owned.append(st.grid[slot])
    st.grid[slot] = 0
    save_relics()
    return True


def placed_relic_ids() -> list[int]:
    return [r for r in relic_state().grid if r != 0]


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
