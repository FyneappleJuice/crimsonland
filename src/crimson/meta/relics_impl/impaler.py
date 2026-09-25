from __future__ import annotations

"""Pact of the Impaler relic (not native, modelled on Path of Exile's Impale).

Every direct projectile hit (bullet, bounce, rocket impact) deals
IMPALER_DIRECT_MULT (-20%, fixed at every tier) of its normal damage, and
leaves an Impale on the target that stores a tier-scaled fraction of that
hit's (post-penalty) damage. Every later hit on the same target also deals
the stored amount of *every* Impale on it, as a separate burst, and uses up
one of each Impale's IMPALER_MAX_HITS hits. Applying a fresh Impale refreshes
the whole stack's IMPALER_DURATION timer, so one shared timer per creature
is enough: the stack only drops if the target goes that long unhit.

At steady state (5 Impales up, from the 6th hit onward) a hit deals
0.8 * (1 + 5 * stored) = 1.12 / 1.20 / 1.30 of normal - the relic's tier
value. One-shot kills only ever pay the -20%; focused fire on tough targets
is where it pays off. Ticking damage (explosion blast, ion cloud, ignite)
never applies or triggers Impales - it would burn the hit counts in frames.

The burst is recorded before the target's own mitigation and released
through creature_apply_damage once, so the shooter's damage bonuses and the
target's resistances each apply to it exactly once. It can't crit, chain,
apply a new Impale, or heal through Leech (OwnerRef.via_impale).
"""

from typing import TYPE_CHECKING

from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...owner_ref import OwnerRef

IMPALER_DIRECT_MULT = 0.80  # fixed at every tier: -20% direct hit damage
IMPALER_MAX_HITS = 5
IMPALER_DURATION = 8.0

_STORED_FRACTION_BY_RELIC: dict[int, float] = {
    RelicId.IMPALER_LOW: 0.08,  # 0.8 * (1 + 5 * 0.08) = 1.12
    RelicId.IMPALER_MEDIUM: 0.10,  # 0.8 * (1 + 5 * 0.10) = 1.20
    RelicId.IMPALER_HIGH: 0.125,  # 0.8 * (1 + 5 * 0.125) = 1.30
}


def _active_relic_id() -> int | None:
    for rid in _STORED_FRACTION_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def impaler_active_for(owner: OwnerRef) -> bool:
    """Only the player's own projectile hits impale (same scoping as Pact of
    Ricochet's penalty); a creature-owned derived shot never does."""
    return owner.is_player() and not owner.via_impale and _active_relic_id() is not None


def on_direct_hit(creature: CreatureState, hit_damage: float) -> float:
    """Resolve one direct hit (already at IMPALER_DIRECT_MULT) on `creature`:
    trigger every Impale on it - returning their summed burst damage, each
    using up one hit - then add this hit's own Impale and refresh the stack's
    timer. Call only when impaler_active_for(owner)."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 0.0
    burst = float(sum(creature.impale_stored))
    kept_stored: list[float] = []
    kept_hits: list[int] = []
    for stored, hits_left in zip(creature.impale_stored, creature.impale_hits_left):
        if hits_left - 1 > 0:
            kept_stored.append(stored)
            kept_hits.append(hits_left - 1)
    stored_now = float(hit_damage) * _STORED_FRACTION_BY_RELIC[relic_id]
    if stored_now > 0.0:
        kept_stored.append(stored_now)
        kept_hits.append(IMPALER_MAX_HITS)
    creature.impale_stored = kept_stored
    creature.impale_hits_left = kept_hits
    creature.impale_timer = IMPALER_DURATION if kept_stored else 0.0
    return burst


def tick(creature: CreatureState, dt: float) -> None:
    """Expire the whole stack once IMPALER_DURATION passes without a fresh
    Impale."""
    if creature.impale_timer <= 0.0:
        return
    creature.impale_timer = max(0.0, float(creature.impale_timer) - float(dt))
    if creature.impale_timer <= 0.0:
        clear(creature)


def clear(creature: CreatureState) -> None:
    creature.impale_stored = []
    creature.impale_hits_left = []
    creature.impale_timer = 0.0


__all__ = [
    "IMPALER_DIRECT_MULT",
    "IMPALER_DURATION",
    "IMPALER_MAX_HITS",
    "clear",
    "impaler_active_for",
    "on_direct_hit",
    "tick",
]
