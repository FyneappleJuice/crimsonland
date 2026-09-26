from __future__ import annotations

"""Pact of Ricochet relic (not native).

Each non-piercing projectile chains once, to a *random* nearby enemy (not
the closest) - both the original hit and the chained bounce deal 48% less
damage, so a full trigger-pull only ever deals 104% of its normal
single-target damage in total, split across two different targets instead of
concentrated in one.

RICOCHET_SEARCH_RADIUS is a first guess for how far the bounce can reach,
not measured against real gameplay - retune by feel.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

import random as _random

from grim.geom import Vec2

from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...owner_ref import OwnerRef

RICOCHET_SEARCH_RADIUS = 300.0

# Both the original and the bounce hit deal (1 - penalty) of normal damage.
_PENALTY_BY_RELIC: dict[int, float] = {
    RelicId.RICOCHET_LOW: 0.48,
}

# Private RNG for the chain-target pick only (cosmetic build variance, same
# reasoning as crit.py's own private RNG) - not the sim RNG, so it can't
# perturb replay determinism.
_RICOCHET_RNG = _random.Random(0x21C0C4E7)


def active_relic_id() -> int | None:
    for rid in _PENALTY_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def damage_mult() -> float:
    """1.0 if the relic isn't equipped; otherwise the (1 - penalty) multiplier
    applied to both the original hit and the chain bounce."""
    relic_id = active_relic_id()
    if relic_id is None:
        return 1.0
    return 1.0 - _PENALTY_BY_RELIC[relic_id]


def projectile_damage_mult(owner: OwnerRef) -> float:
    """The penalty for damage from a projectile (or anything it spawned - a
    bounce, an explosion, an ion cloud) owned by `owner`. Chaining is a
    projectile property, so only projectile damage pays for it: non-projectile
    damage (Nuke, Man Bomb, Radioactive, plague, flamethrower particles and
    their ignite) is never penalized, and neither is a creature-owned derived
    shot (Fork Shot / Splitter children, Shock Chain relays)."""
    if not owner.is_player():
        return 1.0
    return damage_mult()


def pick_chain_target(
    origin_pos: Vec2,
    exclude_idx: int,
    creatures: Sequence[CreatureState],
) -> int | None:
    """A uniformly random *living* creature within RICOCHET_SEARCH_RADIUS of
    origin_pos, excluding exclude_idx - or None if nothing qualifies."""
    radius_sq = RICOCHET_SEARCH_RADIUS * RICOCHET_SEARCH_RADIUS
    ox, oy = float(origin_pos.x), float(origin_pos.y)
    candidates: list[int] = []
    for idx, creature in enumerate(creatures):
        if idx == exclude_idx or not creature.active or float(creature.hp) <= 0.0:
            continue
        dx = float(creature.pos.x) - ox
        dy = float(creature.pos.y) - oy
        if dx * dx + dy * dy <= radius_sq:
            candidates.append(idx)
    if not candidates:
        return None
    return candidates[_RICOCHET_RNG.randrange(len(candidates))]


__all__ = [
    "RICOCHET_SEARCH_RADIUS",
    "active_relic_id",
    "damage_mult",
    "pick_chain_target",
    "projectile_damage_mult",
]
