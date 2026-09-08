from __future__ import annotations

import pytest

from crimson.perks.ids import PERK_BY_ID, PerkId
from crimson.progression import PERK_MECHANICAL, PERK_STAT_MODS
from crimson.progression.modifiers import ModOp
from crimson.progression.stats import STAT_IDENTITIES


def test_every_perk_is_classified_exactly_once() -> None:
    stat_perks = set(PERK_STAT_MODS)
    mechanical_perks = set(PERK_MECHANICAL)
    all_perks = set(PerkId)

    overlap = stat_perks & mechanical_perks
    assert not overlap, f"perks in both registries: {sorted(p.name for p in overlap)}"

    unclassified = all_perks - stat_perks - mechanical_perks
    assert not unclassified, f"perks in neither registry: {sorted(p.name for p in unclassified)}"

    unknown = (stat_perks | mechanical_perks) - all_perks
    assert not unknown, f"registry references unknown perk ids: {unknown}"


def test_stat_mod_registry_targets_are_well_formed() -> None:
    for perk_id, mods in PERK_STAT_MODS.items():
        assert perk_id in PERK_BY_ID, perk_id
        assert mods, f"{perk_id.name} has an empty mod tuple"
        for mod in mods:
            if mod.op is ModOp.FLAG:
                assert mod.stat and " " not in mod.stat
            else:
                assert mod.stat in STAT_IDENTITIES
            assert mod.source, f"{perk_id.name} mod is missing a source tag"


def test_mechanical_registry_entries_have_a_reason() -> None:
    for perk_id, reason in PERK_MECHANICAL.items():
        assert isinstance(reason, str) and len(reason) > 10, perk_id


@pytest.mark.parametrize(
    ("perk_id", "flag_name"),
    [
        (PerkId.UNSTOPPABLE, "no_hit_stagger"),
        (PerkId.BARREL_GREASER, "projectile_double_steps"),
    ],
)
def test_expected_keystone_flags_are_registered(perk_id: PerkId, flag_name: str) -> None:
    flags = {m.stat for m in PERK_STAT_MODS[perk_id] if m.op is ModOp.FLAG}
    assert flag_name in flags
