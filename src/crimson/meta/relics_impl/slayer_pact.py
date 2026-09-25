from __future__ import annotations

"""Pact of the Slayer relic (not native).

A promotion of the existing Bane of Legends perk ("Taste of Blood") to relic
tier, with a harder-earned payoff. The perk opens its +30% window on *any*
single kill; this relic instead needs a real kill streak (SLAYER_PACT_
KILL_THRESHOLD kills within SLAYER_PACT_WINDOW_SECONDS) before its bonus
kicks in - and the bonus is tuned so the net multiplier while active is
exactly the relic's own tier value (1.12/1.20/1.30), not just "less bad than
usual" - see [[project-relic-system]]. The -20% baseline is identical at
every tier; only the streak payoff scales, so High always strictly beats Low.
"""

from ..relics import RelicId, relic_owned
from ...sim.state_types import PlayerState

SLAYER_PACT_WINDOW_SECONDS = 5.0
SLAYER_PACT_KILL_THRESHOLD = 3
SLAYER_PACT_BASELINE_MULT = 0.8

# Active-window bonus (added on top of the baseline): 0.8 * (1 + bonus) lands
# on exactly 1.12 / 1.20 / 1.30.
_ACTIVE_BONUS_BY_RELIC: dict[int, float] = {
    RelicId.SLAYER_PACT_LOW: 0.40,
    RelicId.SLAYER_PACT_MEDIUM: 0.50,
    RelicId.SLAYER_PACT_HIGH: 0.625,
}


def _active_relic_id() -> int | None:
    for rid in _ACTIVE_BONUS_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def register_kill(player: PlayerState) -> None:
    """Called from creatures/runtime.py's kill-confirmation hook, same spot
    that refreshes bane_of_legends_timer."""
    if _active_relic_id() is None:
        return
    player.slayer_pact_kill_window.append(SLAYER_PACT_WINDOW_SECONDS)


def update_kill_window(player: PlayerState, dt: float) -> None:
    """Per-tick decay - drop entries once they age out of the window. Called
    unconditionally from gameplay.py's player_update (relics aren't gated
    behind perk_active, so this can't live in the perk tick pipeline)."""
    window = player.slayer_pact_kill_window
    if not window:
        return
    dt = float(dt)
    player.slayer_pact_kill_window = [t - dt for t in window if t - dt > 0.0]


def buff_remaining(player: PlayerState) -> float:
    """Seconds until the active streak bonus runs out, 0.0 if it isn't active
    (or the relic isn't equipped). The bonus holds while at least
    SLAYER_PACT_KILL_THRESHOLD kills are still inside the window, so it ends
    when the threshold-th most recent kill ages out."""
    if _active_relic_id() is None:
        return 0.0
    window = player.slayer_pact_kill_window
    if len(window) < SLAYER_PACT_KILL_THRESHOLD:
        return 0.0
    return float(sorted(window, reverse=True)[SLAYER_PACT_KILL_THRESHOLD - 1])


def damage_mult(player: PlayerState) -> float:
    """The multiplier to apply to the shooter's outgoing damage - 1.0 if the
    relic isn't equipped."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 1.0
    mult = SLAYER_PACT_BASELINE_MULT
    if len(player.slayer_pact_kill_window) >= SLAYER_PACT_KILL_THRESHOLD:
        mult *= 1.0 + _ACTIVE_BONUS_BY_RELIC[relic_id]
    return mult


__all__ = [
    "SLAYER_PACT_KILL_THRESHOLD",
    "SLAYER_PACT_WINDOW_SECONDS",
    "buff_remaining",
    "damage_mult",
    "register_kill",
    "update_kill_window",
]
