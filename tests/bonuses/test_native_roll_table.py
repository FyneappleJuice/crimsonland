from __future__ import annotations

from collections import Counter

from crimson.bonuses.ids import BonusId
from crimson.bonuses.selection import _NATIVE_ROLL_TABLE


def test_native_roll_table_has_162_entries() -> None:
    assert len(_NATIVE_ROLL_TABLE) == 162


def test_native_roll_table_matches_the_native_distribution() -> None:
    # Locks in the exact shape of `bonus_pick_random_type`'s (0x412470) roll
    # table, now that it's a precomputed array instead of an inline bucket
    # walk: 13 rolls to Points, roll 14 unresolved (None - the caller handles
    # the live Weapon-vs-Energizer sub-roll), 10 rolls each for the 12 native
    # ids 3..14, and 28 dead-space rolls (17.3% of the table) that the
    # rewrite-only bonus pool spends when `fork_bonus_in_pool` is on.
    counts = Counter(_NATIVE_ROLL_TABLE)

    assert _NATIVE_ROLL_TABLE[13] is None  # roll 14
    assert counts[None] == 1
    assert counts[BonusId.POINTS] == 13
    assert counts[BonusId.UNUSED] == 28
    for bonus_value in range(int(BonusId.WEAPON), int(BonusId.FIRE_BULLETS) + 1):
        assert counts[BonusId(bonus_value)] == 10
    assert sum(counts.values()) == 162
