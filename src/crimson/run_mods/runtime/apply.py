from __future__ import annotations

from ...sim.state_types import PlayerState
from ..ids import RunModId
from .counts import adjust_run_mod_count, adjust_run_mod_penalty_count


def run_mod_apply(players: list[PlayerState], run_mod_id: RunModId, *, amount: int = 1) -> None:
    """Increment the run-mod counter. Every run mod is a pure StatMod (see
    stat_mods.py) - unlike perks, there is no per-id one-shot handler.

    `amount` is normally 1; Wildcard's "upgrade" outcome (run_mods/selection.py)
    passes 3 to apply three stacks worth of the same bonus in one pick.
    """

    if not players:
        return
    owner = players[0]
    try:
        adjust_run_mod_count(owner, run_mod_id, amount=amount)
    finally:
        if len(players) > 1:
            for player in players[1:]:
                player.run_mod_counts[:] = owner.run_mod_counts


def run_mod_apply_penalty(players: list[PlayerState], run_mod_id: RunModId, *, amount: int = 1) -> None:
    """Increment the negative-direction counter (Wildcard's upgrade penalty
    half) - see `PlayerState.run_mod_penalty_counts`."""

    if not players:
        return
    owner = players[0]
    try:
        adjust_run_mod_penalty_count(owner, run_mod_id, amount=amount)
    finally:
        if len(players) > 1:
            for player in players[1:]:
                player.run_mod_penalty_counts[:] = owner.run_mod_penalty_counts
