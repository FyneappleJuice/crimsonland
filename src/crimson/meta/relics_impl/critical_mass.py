from __future__ import annotations

"""Critical Mass relic (not native).

Crit chance scales with how many enemies are packed in close around you (up
to a cap); if the crowd's thin, crit multiplier itself is docked instead.
Standing in the middle of a horde makes you a crit machine; picking off a
lone straggler hits softer than normal.

Crit is rolled once per shot at fire time (weapon_runtime/fire.py), stamped
onto the projectile and applied at hit time - not re-rolled per hit - so this
has to be evaluated at the same fire-time point every other crit modifier is:
right before roll_primary_crit/roll_crit_mult is called.

The bonus is a flat crit chance per nearby enemy, added on top of the
weapon's own (not an "increased%" of it), growing up to
CRITICAL_MASS_CAP_ENEMY_COUNT enemies. Tuned so a Rifle (20% base, 2.0x)
gains exactly the relic's tier value in average damage at
CRITICAL_MASS_TUNING_ENEMY_COUNT enemies: +12%/+20%/+30%. Below CRITICAL_MASS_LOW_ENEMY_THRESHOLD enemies
the crit multiplier is also docked.
CRITICAL_MASS_RADIUS was widened from a first-guess 200 to 400 by playtest.

Rockets read this too (weapon_runtime/fire.py's _rocket_crit_mult_with_powerups),
not just the primary pellet loop.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from grim.geom import Vec2

from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState

CRITICAL_MASS_RADIUS = 400.0
CRITICAL_MASS_CAP_ENEMY_COUNT = 10
CRITICAL_MASS_TUNING_ENEMY_COUNT = 7  # where the tier value lands exactly
CRITICAL_MASS_LOW_ENEMY_THRESHOLD = 5  # fewer than this -> crit mult penalty
CRITICAL_MASS_MULT_PENALTY = 0.25  # fixed at every tier: -25% crit mult when thin

# Flat crit chance per nearby enemy. A Rifle (EV 1.2) needs +14.4/+24/+36
# points at 7 enemies to average 1.344/1.44/1.56 (+12%/+20%/+30%).
_CHANCE_PER_ENEMY_BY_RELIC: dict[int, float] = {
    RelicId.CRITICAL_MASS_LOW: 0.144 / CRITICAL_MASS_TUNING_ENEMY_COUNT,
    RelicId.CRITICAL_MASS_MEDIUM: 0.24 / CRITICAL_MASS_TUNING_ENEMY_COUNT,
    RelicId.CRITICAL_MASS_HIGH: 0.36 / CRITICAL_MASS_TUNING_ENEMY_COUNT,
}


def _active_relic_id() -> int | None:
    for rid in _CHANCE_PER_ENEMY_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def critical_mass_active() -> bool:
    return _active_relic_id() is not None


def _nearby_enemy_count(player_pos: Vec2, creatures: Sequence[CreatureState] | None) -> int:
    if not creatures:
        return 0
    radius_sq = CRITICAL_MASS_RADIUS * CRITICAL_MASS_RADIUS
    px, py = float(player_pos.x), float(player_pos.y)
    count = 0
    for creature in creatures:
        if not creature.active or float(creature.hp) <= 0.0:
            continue
        dx = float(creature.pos.x) - px
        dy = float(creature.pos.y) - py
        if dx * dx + dy * dy <= radius_sq:
            count += 1
    return count


def crit_bonus_chance(player_pos: Vec2, creatures: Sequence[CreatureState] | None) -> float:
    """Flat crit chance added on top of the weapon's own (crit.py's
    roll_primary_crit `added_chance`) from nearby enemies, capped."""
    relic_id = _active_relic_id()
    if relic_id is None:
        return 0.0
    count = min(_nearby_enemy_count(player_pos, creatures), CRITICAL_MASS_CAP_ENEMY_COUNT)
    return count * _CHANCE_PER_ENEMY_BY_RELIC[relic_id]


def crit_mult_penalty_mult(player_pos: Vec2, creatures: Sequence[CreatureState] | None) -> float:
    """Multiplier to apply to the base crit_mult - 1.0 normally, (1 -
    CRITICAL_MASS_MULT_PENALTY) when the crowd's thin. Fixed at every tier."""
    if _active_relic_id() is None:
        return 1.0
    count = _nearby_enemy_count(player_pos, creatures)
    if count < CRITICAL_MASS_LOW_ENEMY_THRESHOLD:
        return 1.0 - CRITICAL_MASS_MULT_PENALTY
    return 1.0


__all__ = [
    "CRITICAL_MASS_CAP_ENEMY_COUNT",
    "CRITICAL_MASS_LOW_ENEMY_THRESHOLD",
    "CRITICAL_MASS_MULT_PENALTY",
    "CRITICAL_MASS_RADIUS",
    "CRITICAL_MASS_TUNING_ENEMY_COUNT",
    "crit_bonus_chance",
    "critical_mass_active",
    "crit_mult_penalty_mult",
]
