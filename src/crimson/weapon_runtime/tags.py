from __future__ import annotations

"""Not native: static weapon classification for masteries/crit (rewrite-only).

Three independent axes per weapon - archetype, damage type, delivery - so a
future modifier can target any one of them without caring about the others
(e.g. "Rifle Mastery" boosts every Rifle regardless of damage type,
"Explosion Mastery" boosts every Explosion-dealing weapon regardless of
archetype). See docs/design/monster-rarity.md's sibling design note for the
mastery system this feeds - crit chance is the first consumer.

Covers every weapon `fireable_weapon_ids()` (weapon_runtime/fire_recipes.py)
returns, including the currently-shelved roster in
weapon_runtime/availability.py's INACTIVE_WEAPON_IDS - they keep their tags
so re-activating one later doesn't need this module touched too.
"""

from enum import IntEnum

import msgspec

from ..creatures.damage_types import CreatureDamageType
from ..weapons import WeaponId


class WeaponArchetype(IntEnum):
    """Firing-pattern/role tag - independent of what damage type is dealt."""

    PISTOL = 1
    RIFLE = 2
    SMG = 3
    SHOTGUN = 4
    MINIGUN = 5
    CANNON = 6
    FLAMETHROWER = 8
    ARC = 9
    MELEE = 10
    UTILITY = 11  # no direct damage (Shrinkifier 5K, Plague Spreader Gun)


class WeaponDelivery(IntEnum):
    """How a hit reaches its target."""

    PROJECTILE = 1  # discrete traveling shot (bullet, pellet, rocket)
    STREAM = 2  # continuous particle emission (Flamethrower family)
    BEAM = 3  # instant, no travel time (Arc Gun's chain strike)
    MELEE = 4  # swing (Evil Scythe)


class WeaponTags(msgspec.Struct, frozen=True):
    archetype: WeaponArchetype
    damage_type: CreatureDamageType
    delivery: WeaponDelivery

    def tag_names(self) -> tuple[str, str, str]:
        """(archetype, damage type, delivery) as display strings, e.g.
        ("Shotgun", "Plasma", "Projectile")."""
        return (
            self.archetype.name.title(),
            self.damage_type.name.title(),
            self.delivery.name.title(),
        )


_A = WeaponArchetype
_D = CreatureDamageType
_L = WeaponDelivery

# Damage type here is the weapon's own dispatched type (creatures/damage.py's
# _CREATURE_DAMAGE_PRE_STEPS keys / projectile_pool.py's _damage_type_for /
# the hard-coded FIRE on every particle-stream hit in effects.py) - verified
# against that code, not guessed from the weapon's name.
WEAPON_TAGS: dict[WeaponId, WeaponTags] = {
    WeaponId.PISTOL: WeaponTags(_A.PISTOL, _D.BULLET, _L.PROJECTILE),
    WeaponId.ASSAULT_RIFLE: WeaponTags(_A.RIFLE, _D.BULLET, _L.PROJECTILE),
    WeaponId.SHOTGUN: WeaponTags(_A.SHOTGUN, _D.BULLET, _L.PROJECTILE),
    WeaponId.SAWED_OFF_SHOTGUN: WeaponTags(_A.SHOTGUN, _D.BULLET, _L.PROJECTILE),
    WeaponId.SUBMACHINE_GUN: WeaponTags(_A.SMG, _D.BULLET, _L.PROJECTILE),  # inactive
    WeaponId.GAUSS_GUN: WeaponTags(_A.RIFLE, _D.ENERGY, _L.PROJECTILE),
    WeaponId.MEAN_MINIGUN: WeaponTags(_A.MINIGUN, _D.BULLET, _L.PROJECTILE),
    WeaponId.FLAMETHROWER: WeaponTags(_A.FLAMETHROWER, _D.FIRE, _L.STREAM),
    WeaponId.PLASMA_RIFLE: WeaponTags(_A.RIFLE, _D.PLASMA, _L.PROJECTILE),
    WeaponId.MULTI_PLASMA: WeaponTags(_A.SHOTGUN, _D.PLASMA, _L.PROJECTILE),
    WeaponId.PLASMA_MINIGUN: WeaponTags(_A.MINIGUN, _D.PLASMA, _L.PROJECTILE),
    WeaponId.ROCKET_LAUNCHER: WeaponTags(_A.CANNON, _D.EXPLOSION, _L.PROJECTILE),
    WeaponId.SEEKER_ROCKETS: WeaponTags(_A.RIFLE, _D.EXPLOSION, _L.PROJECTILE),
    WeaponId.PLASMA_SHOTGUN: WeaponTags(_A.SHOTGUN, _D.PLASMA, _L.PROJECTILE),
    WeaponId.BLOW_TORCH: WeaponTags(_A.FLAMETHROWER, _D.FIRE, _L.STREAM),  # inactive
    WeaponId.HR_FLAMER: WeaponTags(_A.FLAMETHROWER, _D.FIRE, _L.STREAM),  # inactive
    WeaponId.MINI_ROCKET_SWARMERS: WeaponTags(_A.SHOTGUN, _D.EXPLOSION, _L.PROJECTILE),
    WeaponId.ROCKET_MINIGUN: WeaponTags(_A.MINIGUN, _D.EXPLOSION, _L.PROJECTILE),
    WeaponId.PULSE_GUN: WeaponTags(_A.MINIGUN, _D.BULLET, _L.PROJECTILE),
    WeaponId.JACKHAMMER: WeaponTags(_A.SHOTGUN, _D.BULLET, _L.PROJECTILE),
    WeaponId.ION_RIFLE: WeaponTags(_A.RIFLE, _D.ION, _L.PROJECTILE),
    WeaponId.ION_MINIGUN: WeaponTags(_A.MINIGUN, _D.ION, _L.PROJECTILE),
    WeaponId.ION_CANNON: WeaponTags(_A.CANNON, _D.ION, _L.PROJECTILE),
    WeaponId.SHRINKIFIER_5K: WeaponTags(_A.UTILITY, _D.BULLET, _L.PROJECTILE),  # inactive
    WeaponId.BLADE_GUN: WeaponTags(_A.RIFLE, _D.BULLET, _L.PROJECTILE),
    WeaponId.SPIDER_PLASMA: WeaponTags(_A.RIFLE, _D.PLASMA, _L.PROJECTILE),  # enemy-only
    WeaponId.EVIL_SCYTHE: WeaponTags(_A.MELEE, _D.MELEE, _L.MELEE),
    WeaponId.PLASMA_CANNON: WeaponTags(_A.CANNON, _D.PLASMA, _L.PROJECTILE),
    WeaponId.SPLITTER_GUN: WeaponTags(_A.RIFLE, _D.BULLET, _L.PROJECTILE),
    WeaponId.GAUSS_SHOTGUN: WeaponTags(_A.SHOTGUN, _D.ENERGY, _L.PROJECTILE),
    WeaponId.ION_SHOTGUN: WeaponTags(_A.SHOTGUN, _D.ION, _L.PROJECTILE),
    WeaponId.RAYGUN: WeaponTags(_A.ARC, _D.LIGHTNING, _L.BEAM),
    WeaponId.PLAGUE_SPREADER_GUN: WeaponTags(_A.UTILITY, _D.BULLET, _L.PROJECTILE),  # inactive
    WeaponId.BUBBLEGUN: WeaponTags(_A.FLAMETHROWER, _D.FIRE, _L.STREAM),  # inactive
    WeaponId.RAINBOW_GUN: WeaponTags(_A.RIFLE, _D.BULLET, _L.PROJECTILE),  # inactive
    WeaponId.FIRE_BULLETS: WeaponTags(_A.MINIGUN, _D.FIRE, _L.PROJECTILE),
}


def weapon_tags(weapon_id: WeaponId) -> WeaponTags:
    tags = WEAPON_TAGS.get(WeaponId(weapon_id))
    if tags is None:
        raise ValueError(f"weapon has no tags: {int(weapon_id)}")
    return tags


def weapons_with_archetype(archetype: WeaponArchetype) -> tuple[WeaponId, ...]:
    return tuple(wid for wid, tags in WEAPON_TAGS.items() if tags.archetype == archetype)


def weapons_with_damage_type(damage_type: CreatureDamageType) -> tuple[WeaponId, ...]:
    return tuple(wid for wid, tags in WEAPON_TAGS.items() if tags.damage_type == damage_type)


def weapons_with_delivery(delivery: WeaponDelivery) -> tuple[WeaponId, ...]:
    return tuple(wid for wid, tags in WEAPON_TAGS.items() if tags.delivery == delivery)


__all__ = [
    "WEAPON_TAGS",
    "WeaponArchetype",
    "WeaponDelivery",
    "WeaponTags",
    "weapon_tags",
    "weapons_with_archetype",
    "weapons_with_damage_type",
    "weapons_with_delivery",
]
