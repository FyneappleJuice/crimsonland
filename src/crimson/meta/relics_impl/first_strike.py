from __future__ import annotations

"""Pact of the First Strike relic (not native).

SHELVED (meta/relics.py's SHELVED_RELIC_IDS): to be reworked so the opening
hit on each creature is a guaranteed crit and later hits can't crit, instead
of the flat opening-damage bonus below.

The opposite shape to Pact of the Impaler: the *opening* hit on each creature
is the big one. The first direct projectile hit (bullet, bounce, rocket
impact) you land on a creature deals +60%/+100%/+150% - only that one hit: a
shotgun blast's other pellets, and every later shot, deal normal damage - and
the creature is then Struck. Averaged over a typical ~5-hit kill that's the
tier's +12%/+20%/+30%; it's huge against hordes you tag once and negligible
against a single tanky target.

The cost is fixed at every tier: a creature you haven't hit yet deals
FIRST_STRIKE_DANGER_MULT (+40%) damage to you - contact, its projectiles and
its death explosion - until you hit it.
"""

from typing import TYPE_CHECKING

from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...owner_ref import OwnerRef

FIRST_STRIKE_DANGER_MULT = 1.40  # fixed at every tier: unstruck creatures hit you +40%

_OPENER_BONUS_BY_RELIC: dict[int, float] = {
    RelicId.FIRST_STRIKE_LOW: 0.60,
    RelicId.FIRST_STRIKE_MEDIUM: 1.00,
    RelicId.FIRST_STRIKE_HIGH: 1.50,
}


def _active_relic_id() -> int | None:
    for rid in _OPENER_BONUS_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def first_strike_active() -> bool:
    return _active_relic_id() is not None


def opening_hit_mult(creature: CreatureState, owner: OwnerRef) -> float:
    """Damage multiplier for a direct projectile hit by `owner` on `creature`,
    marking it Struck. Only a player's own hit strikes it; only the very
    first one gets the bonus (a shotgun's later pellets see it Struck)."""
    if not owner.is_player() or owner.via_impale:
        return 1.0
    if creature.struck:
        return 1.0
    creature.struck = True
    relic_id = _active_relic_id()
    if relic_id is None:
        return 1.0
    return 1.0 + _OPENER_BONUS_BY_RELIC[relic_id]


def incoming_damage_mult(creature: CreatureState | None) -> float:
    """Multiplier on damage `creature` deals to a player - the relic's cost."""
    if creature is None or creature.struck or _active_relic_id() is None:
        return 1.0
    return FIRST_STRIKE_DANGER_MULT


__all__ = [
    "FIRST_STRIKE_DANGER_MULT",
    "first_strike_active",
    "incoming_damage_mult",
    "opening_hit_mult",
]
