from __future__ import annotations

import pytest

from crimson.creatures.damage_types import CreatureDamageType
from crimson.weapon_runtime.fire_recipes import fireable_weapon_ids
from crimson.weapon_runtime.tags import (
    WEAPON_TAGS,
    WeaponArchetype,
    WeaponDelivery,
    weapon_tags,
    weapons_with_archetype,
    weapons_with_damage_type,
    weapons_with_delivery,
)
from crimson.weapons import WeaponId


def test_every_fireable_weapon_has_tags() -> None:
    missing = [w for w in fireable_weapon_ids() if w not in WEAPON_TAGS]
    assert missing == []


def test_pulse_gun_is_minigun_archetype() -> None:
    assert weapon_tags(WeaponId.PULSE_GUN).archetype == WeaponArchetype.MINIGUN


def test_plasma_shotgun_matches_the_worked_example() -> None:
    # Plasma Shotgun -> Shotgun, Plasma, Projectile (the design's own example).
    tags = weapon_tags(WeaponId.PLASMA_SHOTGUN)
    assert tags.tag_names() == ("Shotgun", "Plasma", "Projectile")


def test_evil_scythe_is_melee_on_every_axis() -> None:
    tags = weapon_tags(WeaponId.EVIL_SCYTHE)
    assert tags.archetype == WeaponArchetype.MELEE
    assert tags.damage_type == CreatureDamageType.MELEE
    assert tags.delivery == WeaponDelivery.MELEE


def test_arc_gun_is_arc_lightning_beam() -> None:
    tags = weapon_tags(WeaponId.RAYGUN)
    assert tags.tag_names() == ("Arc", "Lightning", "Beam")


def test_rocket_minigun_is_minigun_archetype_but_explosion_damage() -> None:
    # Archetype and damage type are independent axes - a Minigun-archetype
    # weapon can still deal Explosion damage.
    tags = weapon_tags(WeaponId.ROCKET_MINIGUN)
    assert tags.archetype == WeaponArchetype.MINIGUN
    assert tags.damage_type == CreatureDamageType.EXPLOSION


def test_bubblegun_shares_flamethrower_tags() -> None:
    # Bubblegun hits through the exact same particle-stream code path as
    # Flamethrower/Blow Torch/HR Flamer (effects.py hard-codes FIRE for all
    # of them) - tags reflect that, even though it's shelved for play.
    assert weapon_tags(WeaponId.BUBBLEGUN) == weapon_tags(WeaponId.FLAMETHROWER)


def test_weapons_with_archetype_finds_every_rifle() -> None:
    rifles = weapons_with_archetype(WeaponArchetype.RIFLE)
    assert WeaponId.ASSAULT_RIFLE in rifles
    assert WeaponId.PLASMA_RIFLE in rifles
    assert WeaponId.ION_RIFLE in rifles
    assert WeaponId.GAUSS_GUN in rifles
    assert WeaponId.SHOTGUN not in rifles


def test_weapons_with_damage_type_finds_every_explosion_weapon() -> None:
    explosive = weapons_with_damage_type(CreatureDamageType.EXPLOSION)
    assert WeaponId.ROCKET_LAUNCHER in explosive
    assert WeaponId.SEEKER_ROCKETS in explosive
    assert WeaponId.MINI_ROCKET_SWARMERS in explosive
    assert WeaponId.ROCKET_MINIGUN in explosive
    assert WeaponId.ASSAULT_RIFLE not in explosive


def test_weapons_with_delivery_finds_every_stream_weapon() -> None:
    streams = weapons_with_delivery(WeaponDelivery.STREAM)
    assert WeaponId.FLAMETHROWER in streams
    assert WeaponId.BLOW_TORCH in streams
    assert WeaponId.HR_FLAMER in streams
    assert WeaponId.BUBBLEGUN in streams
    assert WeaponId.PISTOL not in streams


def test_weapon_tags_raises_for_a_non_fireable_stub() -> None:
    with pytest.raises(ValueError, match="weapon has no tags"):
        weapon_tags(WeaponId.FLAMEBURST)
