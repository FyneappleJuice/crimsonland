from __future__ import annotations

"""Display strings for a `RunModChoice` - a thin dispatch over the three
kinds a secondary-panel slot can be, kept separate from `state.py` (data)
and `selection.py` (generation/resolution) so the UI layer has one place to
import from regardless of which kind a slot turned out to be."""

import re

from ..perks.ids import perk_display_description, perk_display_name
from .ids import RunModId, run_mod_display_description, run_mod_display_name
from .state import RunModChoice, RunModChoiceKind

# Every non-meta, non-hidden-target run mod's own description is already
# hand-authored with the correct human-facing sign for its stat (e.g. Reload
# Speed's benefit reads "-3%", since less time is the win, while Fire Rate's
# benefit reads "+2%", since more rate is the win - the two are stored as
# StatMods with opposite-signed values for the "same shape" of improvement).
# Scaling that authored percentage (not the raw StatMod value) is what keeps
# a tripled/inverted phrase reading correctly either way.
_PERCENT_PATTERN = re.compile(r"([+-]\d+(?:\.\d+)?)%")


def _percent_phrase(run_mod_id: RunModId, *, scale: float) -> str:
    """`scale`d version of `run_mod_id`'s own authored percentage, e.g. "+9%
    Bullet Damage" (scale=3.0) or "-2% Fire Rate" (scale=-1.0)."""

    match = _PERCENT_PATTERN.search(run_mod_display_description(run_mod_id))
    assert match is not None, f"{run_mod_id!r}'s description has no N% to scale"
    value = float(match.group(1)) * scale
    sign = "+" if value >= 0.0 else ""
    return f"{sign}{value:.0f}% {run_mod_display_name(run_mod_id)}"


def run_mod_choice_display_name(choice: RunModChoice, *, violence_disabled: int = 0) -> str:
    if choice.kind == RunModChoiceKind.PERK:
        assert choice.perk_id is not None
        return perk_display_name(choice.perk_id, violence_disabled=violence_disabled)
    if choice.kind == RunModChoiceKind.UPGRADED_RUN_MOD:
        return f"{run_mod_display_name(choice.run_mod_id)}+"
    return run_mod_display_name(choice.run_mod_id)


def run_mod_choice_display_description(choice: RunModChoice, *, violence_disabled: int = 0) -> str:
    if choice.kind == RunModChoiceKind.PERK:
        assert choice.perk_id is not None
        return perk_display_description(choice.perk_id, violence_disabled=violence_disabled)
    if choice.kind == RunModChoiceKind.UPGRADED_RUN_MOD:
        assert choice.penalty_run_mod_id is not None
        boosted = _percent_phrase(choice.run_mod_id, scale=3.0)
        penalty = _percent_phrase(choice.penalty_run_mod_id, scale=-1.0)
        return f"{boosted}, {penalty}."
    return run_mod_display_description(choice.run_mod_id)
