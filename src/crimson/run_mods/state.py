from __future__ import annotations

from enum import IntEnum, unique

import msgspec

from ..perks.ids import PerkId
from .ids import RunModId


@unique
class RunModChoiceKind(IntEnum):
    RUN_MOD = 0
    # Not native: Wildcard's "upgrade" outcome - run_mod_id applies at 3x,
    # penalty_run_mod_id applies inverted (worse) at 1x, in the same pick.
    UPGRADED_RUN_MOD = 1
    # Not native: Wildcard's "replace" outcome - this slot offers and applies
    # a real primary perk instead of a run mod, entirely through the run-mod
    # panel's own pick flow.
    PERK = 2


class RunModChoice(msgspec.Struct, frozen=True):
    kind: RunModChoiceKind = RunModChoiceKind.RUN_MOD
    run_mod_id: RunModId = RunModId.FIRE_RATE
    penalty_run_mod_id: RunModId | None = None
    perk_id: PerkId | None = None


class RunModSelectionState(msgspec.Struct):
    pending_count: int = 0
    choices: list[RunModChoice] = msgspec.field(default_factory=list)
    choices_dirty: bool = True
