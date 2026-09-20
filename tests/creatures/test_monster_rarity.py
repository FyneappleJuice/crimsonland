from __future__ import annotations

import pytest

from crimson.creatures import rarity as R
from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureInit, build_survival_spawn_creature
from crimson.owner_ref import OwnerRef
from crimson.rng_caller_static import RngCallerStatic
from crimson.sim.state_types import PlayerState
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


def test_tooltip_lines_are_rarity_then_modifier_names() -> None:
    lines = R.monster_tooltip_lines("alien", 3, (R.AffixId.COLOSSAL, R.AffixId.ARMORED))
    assert lines[0] == "Apex"
    assert lines[1].startswith("Oversized - ")
    assert lines[2].startswith("Armored - ")
    assert "alien" not in " ".join(lines).lower()  # no monster name


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


def _plain_init(**overrides) -> "CreatureInit":
    from crimson.creatures.spawn import CreatureInit

    kwargs = dict(
        origin_template_id=0, pos=Vec2(), heading=0.0, phase_seed=0,
        health=100.0, move_speed=1.0, contact_damage=0.0, reward_value=10.0,
    )
    kwargs.update(overrides)
    return CreatureInit(**kwargs)


def test_glass_frame_penalizes_damage_resist_and_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "roll_affixes", lambda tier, xp: (R.AffixId.GLASS_FRAME,))
    init = _plain_init()
    R.apply_rarity(init, tier=1, player_experience=0)
    assert init.move_speed == pytest.approx(1.6)
    assert init.damage_taken_mult_by_type[int(CreatureDamageType.BULLET)] == pytest.approx(1.4)


def test_feralization_boosts_reward_speed_and_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "roll_affixes", lambda tier, xp: (R.AffixId.FERALIZATION,))
    init = _plain_init(contact_damage=5.0)
    R.apply_rarity(init, tier=2, player_experience=0)
    assert init.move_speed == pytest.approx(2.5)
    assert init.contact_damage == pytest.approx(10.0)
    expected_reward = 10.0 * R._TIER_REWARD_MULT[2] * 3.0 * (1.0 + R._THREAT_REWARD_PER_POINT * 3)
    assert init.reward_value == pytest.approx(expected_reward)


def test_ironhide_caps_single_hit_damage_at_a_fraction_of_max_hp() -> None:
    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, rarity=2,
        affixes=(R.AffixId.IRONHIDE,),
    )
    from grim.rand import Crand

    creature_apply_damage(
        creature, damage_amount=500.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert 1000.0 - creature.hp == pytest.approx(80.0)  # capped to 8% of max_hp

    # A hit already below the cap is untouched.
    creature.hp = 1000.0
    creature_apply_damage(
        creature, damage_amount=10.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert 1000.0 - creature.hp == pytest.approx(10.0)


def test_overshield_blocks_the_first_three_hits_then_drops() -> None:
    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, rarity=2,
        affixes=(R.AffixId.OVERSHIELD,),
    )
    from grim.rand import Crand

    for _ in range(3):
        creature_apply_damage(
            creature, damage_amount=100.0, damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
        )
    assert creature.hp == pytest.approx(1000.0)  # first 3 hits fully absorbed
    assert creature.affix_shield_hits == 0

    creature_apply_damage(
        creature, damage_amount=100.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert creature.hp == pytest.approx(900.0)  # 4th hit lands normally


def test_evasive_dodges_a_deterministic_fraction_of_bullet_hits() -> None:
    from grim.rand import Crand

    dodged = 0
    total = 400
    for _ in range(total):
        creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.EVASIVE,))
        creature_apply_damage(
            creature, damage_amount=100.0, damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
        )
        if creature.hp == pytest.approx(1000.0):
            dodged += 1
    # ~35% dodge chance; assert it's in a sane band rather than an exact count.
    assert 0.20 < dodged / total < 0.50

    # Non-bullet damage is never dodged by this affix.
    creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.EVASIVE,))
    creature_apply_damage(
        creature, damage_amount=100.0, damage_type=int(CreatureDamageType.FIRE),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert creature.hp == pytest.approx(900.0)


def test_hatch_death_children_spawn_alive_not_as_corpses() -> None:
    from crimson.creatures.lifecycle import CREATURE_LIFECYCLE_ALIVE

    # The dying parent's lifecycle_stage is already decaying toward the
    # corpse-fade state by the time death affixes run - regression coverage
    # for children inheriting that via msgspec.structs.replace() and
    # spawning already treated as dead corpses.
    creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.HATCHING,),
        lifecycle_stage=-3.0, pos=Vec2(10.0, 20.0),
    )

    class _Pool:
        def __init__(self) -> None:
            self._entries = [CreatureState(active=False) for _ in range(8)]
            self.spawned_count = 0

        def _alloc_slot(self):
            for i, e in enumerate(self._entries):
                if not e.active:
                    return i
            return None

    pool = _Pool()
    R.apply_monster_death_affixes(
        pool, 0, creature,
        state=object(), players=[], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )
    children = [e for e in pool._entries if e.active]
    assert len(children) == R.HATCHING_COUNT
    for child in children:
        assert child.hp > 0.0
        assert child.lifecycle_stage == pytest.approx(CREATURE_LIFECYCLE_ALIVE)


def test_frag_death_spawns_a_ring_of_shrapnel_on_death() -> None:
    from crimson.projectiles.runtime.projectile_pool import ProjectilePool

    creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=1, affixes=(R.AffixId.FRAG_DEATH,), pos=Vec2(50.0, 60.0),
    )

    class _State:
        def __init__(self) -> None:
            self.projectiles = ProjectilePool()

    state = _State()
    R.apply_monster_death_affixes(
        object(), 3, creature,
        state=state, players=[], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )
    spawned = [p for p in state.projectiles.iter_active()]
    assert len(spawned) == R.FRAG_DEATH_COUNT
    assert all(p.hits_players for p in spawned)


class _AffixPool:
    """Minimal pool stand-in for update_monster_affixes: exposes .entries."""

    def __init__(self, entries: list[CreatureState]) -> None:
        self._entries = entries

    @property
    def entries(self):
        return self._entries


def test_tick_bloodhungry_heals_only_near_a_player() -> None:
    far_player = PlayerState(index=0, pos=Vec2(10_000.0, 10_000.0))
    near_player = PlayerState(index=0, pos=Vec2(10.0, 10.0))
    creature = CreatureState(
        active=True, hp=100.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.TICK_BLOODHUNGRY,), pos=Vec2(0.0, 0.0),
    )

    R.update_monster_affixes([far_player], _AffixPool([creature]), 1.0, state=object())
    assert creature.hp == pytest.approx(100.0)  # too far, no heal

    R.update_monster_affixes([near_player], _AffixPool([creature]), 1.0, state=object())
    assert creature.hp == pytest.approx(100.0 + 1000.0 * R.TICK_FRAC_PER_S)



def test_lunging_dashes_periodically_then_returns_to_base_speed() -> None:
    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, move_speed=1.0, contact_damage=5.0,
        rarity=2, affixes=(R.AffixId.LUNGING,),
    )
    pool = _AffixPool([creature])

    # First tick establishes the base speed/contact and starts the countdown.
    R.update_monster_affixes([], pool, 0.016, state=object())
    assert creature.move_speed == pytest.approx(1.0)

    # Advance past the lunge interval: the dash should kick in.
    R.update_monster_affixes([], pool, R.LUNGE_INTERVAL_S, state=object())
    assert creature.move_speed == pytest.approx(4.0)  # 1 + LUNGE_SPEED_BONUS(3.0)
    assert creature.contact_damage == pytest.approx(10.0)  # 5 * (1 + LUNGE_CONTACT_BONUS(1.0))

    # Advance past the dash duration: it should drop back to base.
    R.update_monster_affixes([], pool, R.LUNGE_DURATION_S + 0.01, state=object())
    assert creature.move_speed == pytest.approx(1.0)
    assert creature.contact_damage == pytest.approx(5.0)


def test_acid_lob_fires_a_projectile_at_the_nearest_player_periodically() -> None:
    from crimson.projectiles.runtime.projectile_pool import ProjectilePool

    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.ACID_LOB,), pos=Vec2(0.0, 0.0),
    )
    pool = _AffixPool([creature])
    player = PlayerState(index=0, pos=Vec2(100.0, 0.0))

    class _State:
        def __init__(self) -> None:
            self.projectiles = ProjectilePool()

    state = _State()
    # The lob timer starts at 0.0 (like native attack_cooldown), so the very
    # first tick fires immediately.
    R.update_monster_affixes([player], pool, 0.016, state=state)
    assert len(state.projectiles.iter_active()) == 1

    # It shouldn't fire again until a full interval has elapsed.
    R.update_monster_affixes([player], pool, 0.016, state=state)
    assert len(state.projectiles.iter_active()) == 1

    R.update_monster_affixes([player], pool, R.ACID_LOB_INTERVAL_S, state=state)
    spawned = state.projectiles.iter_active()
    assert len(spawned) == 2
    assert all(p.hits_players for p in spawned)


def test_feasting_heals_the_creature_from_contact_damage_it_deals() -> None:
    from crimson.creatures.runtime import _creature_interaction_contact_damage, _CreatureInteractionCtx
    from crimson.gameplay import GameplayState

    creature = CreatureState(
        active=True, hp=500.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.FEASTING,),
        contact_damage=20.0, size=50.0, attack_cooldown=0.0,
    )
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=1000.0)
    state = GameplayState()

    ctx = _CreatureInteractionCtx(
        pool=object(), creature_index=0, creature=creature, state=state,
        players=[player], player=player, dt=0.016, rng=state.rng, detail_preset=5,
        world_width=1000.0, world_height=1000.0, fx_queue=None, deaths=[], sfx=[],
        contact_distance=0.0,
    )
    _creature_interaction_contact_damage(ctx)
    assert creature.hp == pytest.approx(500.0 + 20.0 * R.FEASTING_HEAL_FRACTION)


def test_on_death_affix_tints_red_regardless_of_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "roll_affixes", lambda tier, xp: (R.AffixId.DETONATING,))
    init = _plain_init()
    R.apply_rarity(init, tier=3, player_experience=0)  # Apex tier -> gold normally
    expected_r, expected_g, expected_b = R.DEATH_AFFIX_COLOR
    assert init.tint[0] == pytest.approx((expected_r / 255.0) * 0.55 + 1.0 * 0.45)
    assert init.tint[1] == pytest.approx((expected_g / 255.0) * 0.55 + 1.0 * 0.45)
    assert init.tint[2] == pytest.approx((expected_b / 255.0) * 0.55 + 1.0 * 0.45)


def test_no_on_death_affix_keeps_the_tier_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(R, "roll_affixes", lambda tier, xp: (R.AffixId.OVERGROWN,))
    init = _plain_init()
    R.apply_rarity(init, tier=3, player_experience=0)  # Apex tier -> gold
    expected_r, expected_g, expected_b = R.RARITY_COLOR[3]
    assert init.tint[0] == pytest.approx((expected_r / 255.0) * 0.55 + 1.0 * 0.45)
    assert init.tint[1] == pytest.approx((expected_g / 255.0) * 0.55 + 1.0 * 0.45)
    assert init.tint[2] == pytest.approx((expected_b / 255.0) * 0.55 + 1.0 * 0.45)


def test_native_variant_path_is_unchanged_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("crimson.creatures.rarity.MONSTER_RARITY_ENABLED", False)
    from grim.rand import Crand

    c = build_survival_spawn_creature(Vec2(1.0, 2.0), Crand(0x66), player_experience=0)
    assert c.rarity == 0
    assert c.health == pytest.approx(65.0)  # native red variant
