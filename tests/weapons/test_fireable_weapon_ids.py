from __future__ import annotations

import pytest

from crimson.weapon_runtime.fire_recipes import fireable_weapon_ids, resolve_fire_recipe
from crimson.weapons import WEAPON_BY_ID, WeaponId

# Cut / unimplemented stubs: in the table but with no projectile template or
# fire recipe, so equipping and firing one raises.
_KNOWN_UNIMPLEMENTED = {
    WeaponId.FLAMEBURST,
    WeaponId.GRIM_WEAPON,
    WeaponId.TRANSMUTATOR,
    WeaponId.BLASTER_R_300,
    WeaponId.LIGHTNING_RIFLE,
    WeaponId.NUKE_LAUNCHER,
}


def test_every_fireable_weapon_resolves_a_recipe() -> None:
    for weapon_id in fireable_weapon_ids():
        resolve_fire_recipe(
            weapon_id=weapon_id,
            pellet_count=int(WEAPON_BY_ID[weapon_id].pellet_count),
            fire_bullets_active=False,
        )  # must not raise


def test_unimplemented_stubs_are_excluded() -> None:
    fireable = set(fireable_weapon_ids())
    assert _KNOWN_UNIMPLEMENTED.isdisjoint(fireable)
    # and each stub genuinely raises when resolved
    for weapon_id in _KNOWN_UNIMPLEMENTED:
        with pytest.raises((ValueError, KeyError)):
            resolve_fire_recipe(
                weapon_id=weapon_id,
                pellet_count=int(WEAPON_BY_ID[weapon_id].pellet_count),
                fire_bullets_active=False,
            )


def test_the_standard_roster_and_fork_weapons_are_fireable() -> None:
    fireable = set(fireable_weapon_ids())
    for weapon_id in (
        WeaponId.PISTOL,
        WeaponId.PLASMA_MINIGUN,
        WeaponId.ROCKET_LAUNCHER,
        WeaponId.EVIL_SCYTHE,
        WeaponId.RAYGUN,
    ):
        assert weapon_id in fireable
