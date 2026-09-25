from __future__ import annotations

"""Pact of the Deadeye relic (not native, inspired by Far Shot).

Projectile damage scales with how far the shot has traveled when it lands:
a fixed -25% penalty at point-blank range, climbing linearly to a tier-scaled
bonus (+12%/+20%/+30%) by DEADEYE_PACT_FAR_DISTANCE. The near-side penalty is
identical at every tier - only the far-side payoff scales - so High always
strictly beats Low (same cost, bigger reward), never a bigger drawback.

Hooked directly into projectile_pool.py's damage_amount computation (the
`dist` value is already computed there for the plain formula) rather than
inside creature_apply_damage's shooter-perk block, since that block doesn't
have the shot's travel distance available.
"""

from ..relics import RelicId, relic_owned

DEADEYE_PACT_NEAR_DISTANCE = 50.0  # matches the base damage formula's own distance floor
DEADEYE_PACT_FAR_DISTANCE = 500.0
DEADEYE_PACT_NEAR_MULT = 0.75  # fixed at every tier: -25% at point-blank

_FAR_MULT_BY_RELIC: dict[int, float] = {
    RelicId.DEADEYE_PACT_LOW: 1.12,
    RelicId.DEADEYE_PACT_MEDIUM: 1.20,
    RelicId.DEADEYE_PACT_HIGH: 1.30,
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
    t = (dist - DEADEYE_PACT_NEAR_DISTANCE) / (DEADEYE_PACT_FAR_DISTANCE - DEADEYE_PACT_NEAR_DISTANCE)
    return DEADEYE_PACT_NEAR_MULT + t * (far_mult - DEADEYE_PACT_NEAR_MULT)


__all__ = [
    "DEADEYE_PACT_FAR_DISTANCE",
    "DEADEYE_PACT_NEAR_DISTANCE",
    "DEADEYE_PACT_NEAR_MULT",
    "distance_damage_mult",
]
