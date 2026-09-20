from __future__ import annotations

"""Not native: Like Clockwork.

Doubles the rate every periodic perk-proc timer counts toward its threshold,
so each one fires in half the time. Applied as a rate multiplier on `dt` at
each timer's own accumulation site (fire_cough.py, hot_tempered.py,
man_bomb.py, jinxed_effect.py, pyrokinetic_effect.py) rather than touching any
of their own interval-roll RNG, so the *values* those rolls produce are
unaffected - only how fast the timer walks toward them.
"""

from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId

LIKE_CLOCKWORK_RATE_MULT = 2.0


def like_clockwork_rate_mult(player: PlayerState) -> float:
    return LIKE_CLOCKWORK_RATE_MULT if perk_active(player, PerkId.LIKE_CLOCKWORK) else 1.0
