from __future__ import annotations

"""Not native: the crit-chance system (rewrite-only).

A chance, per weapon-archetype tag (weapon_runtime/tags.py), to deal
CRIT_MULTIPLIER damage instead of the normal amount. To keep average
unbuffed DPS unchanged, every hit's base damage carries a flat compensation
factor (1 / (1 + chance)) regardless of whether that particular hit crits:

    (1-chance) * compensation + chance * compensation * CRIT_MULTIPLIER == 1.0

Rolled on a private RNG (not the sim `rng`), same reasoning as the relic
drop roll in creatures/runtime.py - crit is presentation/build variance, not
run state, so it must not perturb replay determinism or the RNG-trace tests
that script the sim stream's exact draw sequence.
"""

import random as _random

from ..weapons import WeaponId
from .tags import WeaponArchetype, weapon_tags

CRIT_MULTIPLIER = 2.0

CRIT_CHANCE_BY_ARCHETYPE: dict[WeaponArchetype, float] = {
    WeaponArchetype.PISTOL: 0.10,
    WeaponArchetype.RIFLE: 0.20,
    WeaponArchetype.SHOTGUN: 0.05,
    WeaponArchetype.MINIGUN: 0.05,
    WeaponArchetype.CANNON: 0.15,
    # Flamethrower doesn't crit on damage - see effects.py's flame-particle hit
    # handling, where crit_mult (whenever nonzero) multiplies ignite heat gain
    # instead of the direct hit, so a "crit" ember just builds toward ignition
    # faster rather than hitting harder.
    WeaponArchetype.FLAMETHROWER: 0.0,
    WeaponArchetype.ARC: 0.0,
    # Not explicitly given - proposed pending review:
    WeaponArchetype.MELEE: 0.20,  # single heavy hit, matches Rifle
    WeaponArchetype.SMG: 0.05,  # spray tier, matches Shotgun/Minigun (inactive: Submachine Gun)
    WeaponArchetype.UTILITY: 0.0,  # no direct damage (inactive: Shrinkifier 5K, Plague Spreader)
}

_CRIT_RNG = _random.Random(0xC817)


def crit_chance_for_weapon(weapon_id: WeaponId) -> float:
    return CRIT_CHANCE_BY_ARCHETYPE.get(weapon_tags(WeaponId(weapon_id)).archetype, 0.0)


def crit_damage_compensation(chance: float) -> float:
    """Flat multiplier every hit takes (crit or not) so a weapon's average
    damage-per-hit stays equal to its pre-crit baseline."""
    return 1.0 / (1.0 + chance)


def roll_crit_mult(weapon_id: WeaponId) -> float:
    """The single outgoing multiplier for one shot/pellet/bolt/tick -
    compensation on a miss, compensation * CRIT_MULTIPLIER on a crit. Meant
    to be rolled once per discrete damage event (once per pellet/rocket/
    particle/swing/chain-strike) and reused across anything that event goes
    on to hit (e.g. a piercing bullet, a rocket's detonation AoE)."""
    chance = crit_chance_for_weapon(weapon_id)
    compensation = crit_damage_compensation(chance)
    if chance > 0.0 and _CRIT_RNG.random() < chance:
        return compensation * CRIT_MULTIPLIER
    return compensation


def roll_primary_crit(
    weapon_id: WeaponId,
    *,
    force_crit: bool = False,
    bonus_crit_mult: float = 0.0,
) -> tuple[float, bool]:
    """Like `roll_crit_mult`, but also reports whether this particular roll
    crit (needed by perks that react to a real crit landing, e.g. Cold Snap's
    freeze) and lets a caller force/boost the roll (Death Wish, Overdue).

    Scoped to the player's own direct trigger-pull (fire.py's primary pellet
    loop) only - not threaded through every crit call site, since none of the
    perks that need this act on bonus-spawned projectiles.
    """
    chance = crit_chance_for_weapon(weapon_id)
    compensation = crit_damage_compensation(chance)
    is_crit = force_crit or (chance > 0.0 and _CRIT_RNG.random() < chance)
    if is_crit:
        return compensation * (CRIT_MULTIPLIER + bonus_crit_mult), True
    return compensation, False


__all__ = [
    "CRIT_CHANCE_BY_ARCHETYPE",
    "CRIT_MULTIPLIER",
    "crit_chance_for_weapon",
    "crit_damage_compensation",
    "roll_crit_mult",
    "roll_primary_crit",
]
