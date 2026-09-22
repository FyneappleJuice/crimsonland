from __future__ import annotations

from ...sim.state_types import PlayerState
from ..ids import RunModId


def adjust_run_mod_count(player: PlayerState, run_mod_id: RunModId, *, amount: int = 1) -> None:
    idx = int(run_mod_id)
    if 0 <= idx < len(player.run_mod_counts):
        player.run_mod_counts[idx] += int(amount)


def adjust_run_mod_penalty_count(player: PlayerState, run_mod_id: RunModId, *, amount: int = 1) -> None:
    idx = int(run_mod_id)
    if 0 <= idx < len(player.run_mod_penalty_counts):
        player.run_mod_penalty_counts[idx] += int(amount)
