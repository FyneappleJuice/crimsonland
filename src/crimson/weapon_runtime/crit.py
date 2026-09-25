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


def crit_chance_for_weapon(weapon_id: WeaponId, *, increased_chance: float = 0.0) -> float:
    """`increased_chance` is stats.crit_chance - a summed "increased %" (e.g.
    0.05 = +5%) applied against the weapon's own base chance, PoE-style, not
    a flat add. A weapon with 0% base chance (Flamethrower, Arc) stays at 0%
    regardless, same as any other multiplier on a zero base."""
    base = CRIT_CHANCE_BY_ARCHETYPE.get(weapon_tags(WeaponId(weapon_id)).archetype, 0.0)
    return base * (1.0 + float(increased_chance))


def roll_crit_mult(weapon_id: WeaponId, *, increased_chance: float = 0.0, crit_mult: float = CRIT_MULTIPLIER) -> float:
    """The single outgoing multiplier for one shot/pellet/bolt/tick - 1.0 on
    a miss, `crit_mult` (stats.crit_mult, run mods' Crit Multiplier bucket) on
    a crit. Meant to be rolled once per discrete damage event (once per
    pellet/rocket/particle/swing/chain-strike) and reused across anything
    that event goes on to hit (e.g. a piercing bullet, a rocket's detonation
    AoE)."""
    chance = crit_chance_for_weapon(weapon_id, increased_chance=increased_chance)
    if chance > 0.0 and _CRIT_RNG.random() < chance:
        return crit_mult
    return 1.0


# Diamond Flask's "roll N times, crit on any success" - expressed as a
# continuous success-probability formula (1 - (1-chance)^power) instead of
# literally rolling `power` times, so Perk Efficacy can scale `power` smoothly
# (2.1, 2.2, ...) instead of only ever landing on whole extra rolls.
DIAMOND_FLASK_BASE_POWER = 2.0


def roll_primary_crit(
    weapon_id: WeaponId,
    *,
    force_crit: bool = False,
    lucky_power: float = 0.0,
    increased_chance: float = 0.0,
    crit_mult: float = CRIT_MULTIPLIER,
    added_chance: float = 0.0,
) -> tuple[float, bool]:
    """Like `roll_crit_mult`, but also reports whether this particular roll
    crit (needed by perks that react to a real crit landing, e.g. Cold Snap's
    freeze) and lets a caller force the roll (Death Wish).

    `lucky_power` (Diamond Flask, `DIAMOND_FLASK_BASE_POWER` scaled by Perk
    Efficacy) raises the crit chance to `1 - (1-chance)^lucky_power` - the
    probability that at least one of `lucky_power` independent rolls at the
    base chance would succeed, without needing `lucky_power` to be a whole
    number. 0.0 = off (plain single roll). No compensation math needed here -
    see the module docstring; the unbuffed baseline is already neutral before
    any of these bonuses apply.

    Overdue's window bonus is *not* threaded through here any more - it grants
    flat +damage% to every hit (creatures/damage.py's OVERDUE_BONUS_DAMAGE),
    not a crit-multiplier boost, so it no longer needs a crit-roll-time hook.

    Scoped to the player's own direct trigger-pull (fire.py's primary pellet
    loop) only - not threaded through every crit call site, since none of the
    perks that need this act on bonus-spawned projectiles.
    """
    chance = crit_chance_for_weapon(weapon_id, increased_chance=increased_chance)
    # `added_chance` (Critical Mass) is a flat add on top of the weapon's own
    # (increased) chance, not another "increased%" - so it's worth the same
    # absolute amount on every weapon, including 0%-base ones.
    if added_chance > 0.0:
        chance = min(1.0, chance + float(added_chance))

    if lucky_power > 0.0 and chance > 0.0:
        effective_chance = 1.0 - (1.0 - chance) ** lucky_power
        is_crit = force_crit or _CRIT_RNG.random() < effective_chance
        if is_crit:
            return crit_mult, True
        return 1.0, False

    is_crit = force_crit or (chance > 0.0 and _CRIT_RNG.random() < chance)
    if is_crit:
        return crit_mult, True
    return 1.0, False


__all__ = [
    "CRIT_CHANCE_BY_ARCHETYPE",
    "CRIT_MULTIPLIER",
    "crit_chance_for_weapon",
    "roll_crit_mult",
    "roll_primary_crit",
]
