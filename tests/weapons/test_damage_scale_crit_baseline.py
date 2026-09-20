from __future__ import annotations

"""Guards weapons.py's baked-in crit-DPS-neutrality against drift.

Every crit-eligible weapon's WEAPON_TABLE damage_scale is `native / (1 +
chance)`, computed once by hand instead of at runtime (see the comment above
WEAPON_TABLE in weapons.py and the module docstring in weapon_runtime/crit.py
for why). If anyone changes a weapon's crit chance in
weapon_runtime/crit.py's CRIT_CHANCE_BY_ARCHETYPE without also re-baking the
affected weapons' damage_scale here, this test catches it - the two are only
related by this one-time arithmetic, not by any runtime link.

Reuses projectile_pool.py's _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE as the
"native, pre-compensation" reference values, since that snapshot exists for
exactly the same reason (Explosive Payload's blast calibration needs the
original numbers) and must already stay in sync with the real native values.
"""

import pytest

from crimson.projectiles.runtime.projectile_pool import _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE
from crimson.weapon_runtime.crit import crit_chance_for_weapon
from crimson.weapons import WEAPON_BY_ID


@pytest.mark.parametrize("weapon_id", list(_EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE))
def test_damage_scale_is_native_value_divided_by_one_plus_crit_chance(weapon_id) -> None:
    native = _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE[weapon_id]
    chance = crit_chance_for_weapon(weapon_id)
    expected = native / (1.0 + chance)
    assert float(WEAPON_BY_ID[weapon_id].damage_scale) == pytest.approx(expected, rel=1e-6)


def test_every_weapon_with_nonzero_crit_chance_and_damage_scale_is_covered() -> None:
    """Catches the reverse drift: a weapon gains crit chance (or a nonzero
    damage_scale) later and nobody adds it to the native-scale snapshot, so
    it silently never gets baked at all."""
    from crimson.weapon_runtime.tags import WEAPON_TAGS

    missing = []
    for weapon_id in WEAPON_TAGS:
        entry = WEAPON_BY_ID.get(weapon_id)
        if entry is None or float(entry.damage_scale) <= 0.0:
            continue
        if crit_chance_for_weapon(weapon_id) <= 0.0:
            continue
        if weapon_id not in _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE:
            missing.append(weapon_id)
    assert missing == []
