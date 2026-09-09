from __future__ import annotations

import pytest

from crimson.creatures import rarity as R
from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureInit, build_survival_spawn_creature
from crimson.owner_ref import OwnerRef
from crimson.rng_caller_static import RngCallerStatic
from grim.geom import Vec2


class _LcgRng:
    """Cheap varying rng; forces the yellow (Apex) variant roll to hit."""

    def __init__(self, seed: int = 1, *, force_tier: str | None = "yellow") -> None:
        self.s = seed
        self.force_tier = force_tier

    def _next(self) -> int:
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return self.s

    def rand(self) -> int:
        return self._next()

    def rand_tagged(self, caller) -> int:
        name = getattr(caller, "name", str(caller))
        v = self._next()
        if self.force_tier == "yellow" and "RARE_YELLOW" in name:
            return 0
        if self.force_tier == "purple" and "RARE_PURPLE" in name:
            return 0
        if "RARE_" in name:
            return 999999
        return v


def _apex(seed: int = 1) -> CreatureInit:
    return build_survival_spawn_creature(Vec2(100.0, 100.0), _LcgRng(seed), player_experience=40000)


def test_apex_rolls_five_affixes_and_scales_reward() -> None:
    c = _apex(1)
    assert c.rarity == R.MonsterRarity.APEX
    assert len(c.affixes) == 5
    assert len(set(c.affixes)) == 5  # distinct
    # at most one aura
    assert sum(1 for a in c.affixes if R.AFFIXES[a].aura) <= 1
    # reward is well above a normal mob's (~a few hundred at this xp)
    assert c.reward_value > 2000.0


def test_purple_is_mutated_with_three_affixes() -> None:
    c = build_survival_spawn_creature(
        Vec2(100.0, 100.0), _LcgRng(3, force_tier="purple"), player_experience=40000,
    )
    assert c.rarity == R.MonsterRarity.MUTATED
    assert len(c.affixes) == 3


def test_display_name_uses_prefix_and_suffix() -> None:
    name = R.monster_display_name("alien", (R.AffixId.OVERGROWN, R.AffixId.ARMORED))
    assert name == "Brood-Fed Alien of Plating"


def test_resist_affix_reduces_incoming_damage_of_that_type() -> None:
    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, rarity=1,
        affixes=(R.AffixId.FLAME_WARDED,),
        damage_taken_mult_by_type={int(CreatureDamageType.FIRE): 0.4},
    )
    from grim.rand import Crand

    creature_apply_damage(
        creature, damage_amount=100.0, damage_type=int(CreatureDamageType.FIRE),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert 1000.0 - creature.hp == pytest.approx(40.0)  # 100 * 0.4

    # a non-warded type is untouched
    creature.hp = 1000.0
    creature_apply_damage(
        creature, damage_amount=100.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert 1000.0 - creature.hp == pytest.approx(100.0)


def test_regenerating_heals_after_a_pause_and_a_hit_resets_it() -> None:
    creature = CreatureState(
        active=True, hp=500.0, max_hp=1000.0, rarity=1,
        affixes=(R.AffixId.REGENERATING,),
    )

    class _Pool:
        def __init__(self, entries):
            self.entries = entries

    pool = _Pool([creature])

    class _State:
        pass

    R.update_monster_affixes([], pool, 1.0, state=_State())
    assert creature.hp > 500.0  # regen ran (no recent hit)

    # a hit sets the pause
    R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET))
    assert creature.affix_regen_pause == pytest.approx(R.REGEN_PAUSE_S)
    hp_before = creature.hp
    R.update_monster_affixes([], pool, 0.1, state=_State())
    assert creature.hp == pytest.approx(hp_before)  # paused, no regen


def test_frothing_speeds_up_as_hp_drops() -> None:
    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, move_speed=2.0, contact_damage=5.0,
        rarity=1, affixes=(R.AffixId.FROTHING,),
    )

    class _Pool:
        def __init__(self, entries):
            self.entries = entries

    pool = _Pool([creature])

    R.update_monster_affixes([], pool, 0.016, state=object())
    full_hp_speed = creature.move_speed
    assert full_hp_speed == pytest.approx(2.0)

    creature.hp = 100.0  # 90% missing
    R.update_monster_affixes([], pool, 0.016, state=object())
    assert creature.move_speed > full_hp_speed


def test_native_variant_path_is_unchanged_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crimson.creatures.rarity.MONSTER_RARITY_ENABLED", False)
    from grim.rand import Crand

    c = build_survival_spawn_creature(Vec2(1.0, 2.0), Crand(0x66), player_experience=0)
    assert c.rarity == 0
    assert c.health == pytest.approx(65.0)  # native red variant
