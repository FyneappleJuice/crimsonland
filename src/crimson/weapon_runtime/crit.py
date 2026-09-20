from __future__ import annotations

"""Not native: the crit-chance system (rewrite-only).

A chance, per weapon-archetype tag (weapon_runtime/tags.py), to deal
CRIT_MULTIPLIER damage instead of the normal amount. Unbuffed average DPS is
kept unchanged not here but in weapons.py: every crit-eligible weapon's
WEAPON_TABLE damage_scale is baked down by /(1 + that weapon's crit chance)
once, ahead of time, so a plain (non-crit) hit already carries the same
"headroom cut" a runtime compensation factor used to apply on every hit. A
perk that changes the odds or the multiplier (Overdue, Diamond Flask, ...) is
just a bonus on top of that already-neutral baseline - it doesn't need to
solve its own compensation math the way it would if neutrality still lived
here.

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


def roll_crit_mult(weapon_id: WeaponId) -> float:
    """The single outgoing multiplier for one shot/pellet/bolt/tick - 1.0 on
    a miss, CRIT_MULTIPLIER on a crit. Meant to be rolled once per discrete
    damage event (once per pellet/rocket/particle/swing/chain-strike) and
    reused across anything that event goes on to hit (e.g. a piercing
    bullet, a rocket's detonation AoE)."""
    chance = crit_chance_for_weapon(weapon_id)
    if chance > 0.0 and _CRIT_RNG.random() < chance:
        return CRIT_MULTIPLIER
    return 1.0


DIAMOND_FLASK_DOUBLE_MULT = 2.0


def roll_primary_crit(
    weapon_id: WeaponId,
    *,
    force_crit: bool = False,
    bonus_crit_mult: float = 0.0,
    lucky: bool = False,
) -> tuple[float, bool]:
    """Like `roll_crit_mult`, but also reports whether this particular roll
    crit (needed by perks that react to a real crit landing, e.g. Cold Snap's
    freeze) and lets a caller force/boost the roll (Death Wish, Overdue).

    `lucky` (Diamond Flask) rolls the crit chance twice and crits on either
    success; if *both* rolls succeed, the crit multiplier is itself doubled.
    No compensation math needed here - see the module docstring; the
    unbuffed baseline is already neutral before any of these bonuses apply.

    Scoped to the player's own direct trigger-pull (fire.py's primary pellet
    loop) only - not threaded through every crit call site, since none of the
    perks that need this act on bonus-spawned projectiles.
    """
    chance = crit_chance_for_weapon(weapon_id)

    if lucky and chance > 0.0:
        roll1 = _CRIT_RNG.random() < chance
        roll2 = _CRIT_RNG.random() < chance
        is_crit = force_crit or roll1 or roll2
        if is_crit:
            mult = CRIT_MULTIPLIER + bonus_crit_mult
            if (not force_crit) and roll1 and roll2:
                mult *= DIAMOND_FLASK_DOUBLE_MULT
            return mult, True
        return 1.0, False

    is_crit = force_crit or (chance > 0.0 and _CRIT_RNG.random() < chance)
    if is_crit:
        return CRIT_MULTIPLIER + bonus_crit_mult, True
    return 1.0, False


__all__ = [
    "CRIT_CHANCE_BY_ARCHETYPE",
    "CRIT_MULTIPLIER",
    "crit_chance_for_weapon",
    "roll_crit_mult",
    "roll_primary_crit",
]
