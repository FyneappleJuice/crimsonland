from __future__ import annotations

"""Pact of Fortification relic (not native, modelled on Path of Exile's
Fortification).

Each direct projectile hit you land (bullet, bounce, rocket impact) grants
Fortification stacks; each stack is 1% less damage taken from hits, up to
12/20/30 stacks for Low/Medium/High. Each hit is worth
FORTIFY_STACKS_PER_MAX_HP * damage / target max HP * rarity_mult stacks
(fractional, capped at FORTIFY_STACKS_PER_HIT_MAX), so the sustained total
tracks damage output against the targets' health: roughly
FORTIFY_STACKS_PER_MAX_HP * FORTIFY_DURATION * DPS / max_hp - holding the
cap takes ~1.5x / 2.5x / 3.75x a normal target's HP per second.

Gains diminish near the cap: each is scaled by
1 - (tracked / cap) ** FORTIFY_DIMINISH_EXPONENT, so the first stacks come
at full rate but the last few need sustained effort - a fast killer like the
Rocket Minigun settles around ~96%/92%/87% of the Low/Medium/High cap rather
than pinning it.

Everything gained within one FORTIFY_GAIN_INTERVAL is pooled into a single
instance (so fast weapons and shotgun pellets lose nothing), and each
instance lasts FORTIFY_DURATION without refreshing any other - instances
keep being tracked past the cap (up to FORTIFY_MAX_INSTANCES), so losing an
old one while over the cap doesn't drop you below it. The displayed stack
count is the pooled total rounded down.

The cost is fixed at every tier: FORTIFY_MOVE_SPEED_MULT (-10%) movement
speed - heavier, but slower to kite.

"Hits" taken means creature contact, creature projectiles and the Volatile
death blast - applied at those call sites, not in player_take_damage, so
self-inflicted costs (Ammunition Within, Leech) aren't reduced.
"""

import math
from typing import TYPE_CHECKING

from ...math_parity import f32
from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...sim.state_types import PlayerState

FORTIFY_DURATION = 4.0
FORTIFY_GAIN_INTERVAL = 0.1
FORTIFY_MAX_INSTANCES = 100
FORTIFY_STACKS_PER_MAX_HP = 2.0  # a hit for the target's full max HP = 2 stacks
FORTIFY_STACKS_PER_HIT_MAX = 5.0
# Near-cap diminishing returns: higher = the slowdown bites later/harder.
FORTIFY_DIMINISH_EXPONENT = 8.0
FORTIFY_DAMAGE_REDUCTION_PER_STACK = 0.01
FORTIFY_MOVE_SPEED_MULT = 0.90  # fixed at every tier: -10% movement speed

# Stack gain bonus by creatures/rarity.py's MonsterRarity (Normal/Tainted/Mutated/Apex).
_RARITY_GAIN_MULT: dict[int, float] = {0: 1.0, 1: 1.5, 2: 2.0, 3: 3.0}

_MAX_STACKS_BY_RELIC: dict[int, int] = {
    RelicId.FORTIFY_LOW: 12,
    RelicId.FORTIFY_MEDIUM: 20,
    RelicId.FORTIFY_HIGH: 30,
}


def _active_relic_id() -> int | None:
    for rid in _MAX_STACKS_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def max_stacks() -> int:
    relic_id = _active_relic_id()
    return 0 if relic_id is None else _MAX_STACKS_BY_RELIC[relic_id]


def stacks_for_hit(creature: CreatureState, hit_damage: float) -> float:
    max_hp = float(creature.max_hp)
    if max_hp <= 0.0 or hit_damage <= 0.0:
        return 0.0
    rarity_mult = _RARITY_GAIN_MULT.get(int(creature.rarity), 1.0)
    raw = FORTIFY_STACKS_PER_MAX_HP * float(hit_damage) / max_hp * rarity_mult
    return min(FORTIFY_STACKS_PER_HIT_MAX, raw)


def gain_from_hit(player: PlayerState, creature: CreatureState, hit_damage: float) -> None:
    """Called for each direct projectile hit the player (or their clone) lands."""
    if _active_relic_id() is None:
        return
    amount = stacks_for_hit(creature, hit_damage)
    cap = max_stacks()
    tracked = float(sum(player.fortify_stacks))
    amount *= max(0.0, 1.0 - (tracked / cap) ** FORTIFY_DIMINISH_EXPONENT)
    if amount <= 0.0:
        return
    # Pool into the newest instance while it's younger than the gain interval.
    if player.fortify_timers and player.fortify_timers[-1] > FORTIFY_DURATION - FORTIFY_GAIN_INTERVAL:
        player.fortify_stacks[-1] = float(player.fortify_stacks[-1]) + amount
        return
    player.fortify_stacks.append(amount)
    player.fortify_timers.append(FORTIFY_DURATION)
    if len(player.fortify_stacks) > FORTIFY_MAX_INSTANCES:
        del player.fortify_stacks[0]
        del player.fortify_timers[0]


def tick(player: PlayerState, dt: float) -> None:
    dt = float(dt)
    if not player.fortify_timers:
        return
    kept_stacks: list[float] = []
    kept_timers: list[float] = []
    for stacks, remaining in zip(player.fortify_stacks, player.fortify_timers):
        remaining -= dt
        if remaining > 0.0:
            kept_stacks.append(stacks)
            kept_timers.append(remaining)
    player.fortify_stacks = kept_stacks
    player.fortify_timers = kept_timers


def current_stacks(player: PlayerState) -> int:
    cap = max_stacks()
    if cap <= 0:
        return 0
    return min(cap, int(math.floor(sum(player.fortify_stacks))))


def fill_fraction(player: PlayerState) -> float:
    """0.0..1.0 of the cap, for the HUD arc."""
    cap = max_stacks()
    return 0.0 if cap <= 0 else current_stacks(player) / cap


def damage_taken_mult(player: PlayerState | None) -> float:
    if player is None:
        return 1.0
    stacks = current_stacks(player)
    if stacks <= 0:
        return 1.0
    return float(f32(1.0 - FORTIFY_DAMAGE_REDUCTION_PER_STACK * stacks))


def speed_mult() -> float:
    return FORTIFY_MOVE_SPEED_MULT if _active_relic_id() is not None else 1.0


__all__ = [
    "FORTIFY_DIMINISH_EXPONENT",
    "FORTIFY_DURATION",
    "FORTIFY_GAIN_INTERVAL",
    "FORTIFY_MAX_INSTANCES",
    "FORTIFY_MOVE_SPEED_MULT",
    "current_stacks",
    "damage_taken_mult",
    "fill_fraction",
    "gain_from_hit",
    "max_stacks",
    "speed_mult",
    "stacks_for_hit",
    "tick",
]
