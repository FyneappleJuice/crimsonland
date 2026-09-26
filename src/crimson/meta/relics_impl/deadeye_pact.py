from __future__ import annotations

"""Pact of the Deadeye relic (not native, inspired by Far Shot).

Projectile damage scales with how far the shot has traveled when it lands:
a fixed -20% penalty at point-blank range, climbing logarithmically (fast up
close, flattening out further away) to +12% at DEADEYE_PACT_FAR_DISTANCE,
clamped there beyond it. Break-even (no bonus) falls out of the curve:
~211 units.

Hooked directly into projectile_pool.py's damage_amount computation (the
`dist` value is already computed there for the plain formula) rather than
inside creature_apply_damage's shooter-perk block, since that block doesn't
have the shot's travel distance available.
"""

import math

from ..relics import RelicId, relic_owned

DEADEYE_PACT_NEAR_DISTANCE = 50.0  # matches the base damage formula's own distance floor
DEADEYE_PACT_FAR_DISTANCE = 500.0
DEADEYE_PACT_NEAR_MULT = 0.80  # -20% at point-blank

_FAR_MULT_BY_RELIC: dict[int, float] = {
    RelicId.DEADEYE_PACT_LOW: 1.12,
}


def _active_relic_id() -> int | None:
    for rid in _FAR_MULT_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def distance_damage_mult(dist: float) -> float:
    """1.0 if the relic isn't equipped; otherwise the near/far multiplier for
    a shot that traveled `dist` units before landing."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 1.0
    dist = float(dist)
    if dist <= DEADEYE_PACT_NEAR_DISTANCE:
        return DEADEYE_PACT_NEAR_MULT
    far_mult = _FAR_MULT_BY_RELIC[relic_id]
    if dist >= DEADEYE_PACT_FAR_DISTANCE:
        return far_mult
    return DEADEYE_PACT_NEAR_MULT + _log_progress(dist) * (far_mult - DEADEYE_PACT_NEAR_MULT)


def _log_progress(dist: float) -> float:
    """0.0 at DEADEYE_PACT_NEAR_DISTANCE, 1.0 at DEADEYE_PACT_FAR_DISTANCE,
    logarithmic in between."""
    return math.log(dist / DEADEYE_PACT_NEAR_DISTANCE) / math.log(DEADEYE_PACT_FAR_DISTANCE / DEADEYE_PACT_NEAR_DISTANCE)


def neutral_distance() -> float | None:
    """Travel distance where the near/far curve crosses exactly 1.0 (no bonus,
    no penalty) - for the in-world ring. None if the relic isn't equipped."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return None
    # Invert the log curve at mult == 1.0.
    far_mult = _FAR_MULT_BY_RELIC[relic_id]
    progress = (1.0 - DEADEYE_PACT_NEAR_MULT) / (far_mult - DEADEYE_PACT_NEAR_MULT)
    return DEADEYE_PACT_NEAR_DISTANCE * (DEADEYE_PACT_FAR_DISTANCE / DEADEYE_PACT_NEAR_DISTANCE) ** progress


__all__ = [
    "DEADEYE_PACT_FAR_DISTANCE",
    "DEADEYE_PACT_NEAR_DISTANCE",
    "DEADEYE_PACT_NEAR_MULT",
    "distance_damage_mult",
    "neutral_distance",
]
