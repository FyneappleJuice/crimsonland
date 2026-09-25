from __future__ import annotations

"""Pact of Gathering Winds relic (not native).

Fixed floor of -20% move speed / +20% damage taken at every tier. Each shot
that *lands a hit* grants a stack of Tailwind (max GATHERING_WINDS_MAX_STACKS);
each stack moves you toward a tier-scaled ceiling (+12/+20/+30% speed,
-12/-20/-30% damage taken). Getting hit removes GATHERING_WINDS_STACKS_LOST_PER_HIT
(5) stacks - half the climb, not all of it.

Stacks are read directly by their consumption points (gameplay.py's
movement-speed calc, player_damage.py's damage-taken calc) instead of going
through the static stat-mod pipeline, since they change every tick/hit - same
reasoning as Living Fortress's inline multiplier in creatures/damage.py.

Stack gain has to be hooked in both projectile pools (primary bullets in
projectiles/runtime/projectile_pool.py, secondary rockets in
projectiles/runtime/secondary_pool.py) since they're two separate hit-
resolution loops. Stack loss has to be hooked in both player_damage.py entry
points (player_take_damage for melee/contact, player_take_projectile_damage
for creature ranged attacks) for the same reason - see the pipeline
asymmetry noted in [[project-relic-system]].
"""

from ...sim.state_types import PlayerState
from ..relics import RelicId, relic_owned

GATHERING_WINDS_MAX_STACKS = 10
GATHERING_WINDS_STACKS_LOST_PER_HIT = 5
GATHERING_WINDS_FLOOR_SPEED = -0.20  # fixed at every tier
GATHERING_WINDS_FLOOR_DAMAGE_TAKEN = 0.20  # fixed at every tier (a penalty, so positive)

_CEILING_BY_RELIC: dict[int, float] = {
    RelicId.GATHERING_WINDS_LOW: 0.12,
    RelicId.GATHERING_WINDS_MEDIUM: 0.20,
    RelicId.GATHERING_WINDS_HIGH: 0.30,
}


def _active_relic_id() -> int | None:
    for rid in _CEILING_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def gain_stack(player: PlayerState) -> None:
    """Called wherever the player's own shot is confirmed to land a hit."""
    if _active_relic_id() is None:
        return
    player.gathering_winds_stacks = min(GATHERING_WINDS_MAX_STACKS, int(player.gathering_winds_stacks) + 1)


def lose_stack(player: PlayerState) -> None:
    """Called wherever the player is confirmed to take damage."""
    if _active_relic_id() is None:
        return
    player.gathering_winds_stacks = max(0, int(player.gathering_winds_stacks) - GATHERING_WINDS_STACKS_LOST_PER_HIT)


def _fraction(player: PlayerState) -> float:
    """0.0 at 0 stacks, 1.0 at GATHERING_WINDS_MAX_STACKS stacks."""
    raw = float(player.gathering_winds_stacks) / GATHERING_WINDS_MAX_STACKS
    return min(1.0, max(0.0, raw))


def speed_mult(player: PlayerState) -> float:
    """Multiplier to apply on top of the normal move-speed calc - 1.0 if the
    relic isn't equipped."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 1.0
    ceiling = _CEILING_BY_RELIC[relic_id]
    floor = GATHERING_WINDS_FLOOR_SPEED
    pct = floor + _fraction(player) * (ceiling - floor)
    return 1.0 + pct


def damage_taken_mult(player: PlayerState) -> float:
    """Multiplier to apply on top of the normal damage-taken calc - 1.0 if the
    relic isn't equipped."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 1.0
    ceiling = -_CEILING_BY_RELIC[relic_id]
    floor = GATHERING_WINDS_FLOOR_DAMAGE_TAKEN
    pct = floor + _fraction(player) * (ceiling - floor)
    return 1.0 + pct


__all__ = [
    "GATHERING_WINDS_MAX_STACKS",
    "GATHERING_WINDS_STACKS_LOST_PER_HIT",
    "damage_taken_mult",
    "gain_stack",
    "lose_stack",
    "speed_mult",
]
