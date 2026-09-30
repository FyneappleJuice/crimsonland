from __future__ import annotations

import math

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


def test_acid_lob_fires_toward_the_player_not_rotated_90_degrees() -> None:
    """Regression test: the fired angle used to be a raw atan2(dy, dx), but
    this codebase's projectile movement always reads angle - HALF_PI as the
    actual travel direction (see projectile_pool.py's step()), so the shot
    flew 90 degrees off from the player it was aimed at."""
    import math

    from crimson.math_parity import NATIVE_HALF_PI
    from crimson.projectiles.runtime.projectile_pool import ProjectilePool
    from crimson.projectiles.types import ProjectileTemplateId

    creature = CreatureState(
        active=True, hp=1000.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.ACID_LOB,), pos=Vec2(0.0, 0.0),
    )
    pool = _AffixPool([creature])
    player = PlayerState(index=0, pos=Vec2(100.0, 50.0))

    class _State:
        def __init__(self) -> None:
            self.projectiles = ProjectilePool()

    state = _State()
    R.update_monster_affixes([player], pool, 0.016, state=state)
    spawned = state.projectiles.iter_active()
    assert len(spawned) == 1
    proj = spawned[0]
    assert proj.type_id == ProjectileTemplateId.ACID_LOB
    expected_angle = math.atan2(50.0, 100.0) + NATIVE_HALF_PI
    assert proj.angle == pytest.approx(expected_angle)


def test_hatch_death_children_are_buffed_from_the_original_weak_stats() -> None:
    creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.HATCHING,),
        pos=Vec2(10.0, 20.0), move_speed=1.0,
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
        assert child.hp == pytest.approx(45.0)
        assert child.max_hp == pytest.approx(45.0)
        assert child.size == pytest.approx(38.0)
        assert child.contact_damage == pytest.approx(8.0)


def test_bomber_death_queues_a_delayed_detonation_instead_of_an_instant_one() -> None:
    from crimson.gameplay import GameplayState

    creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.DETONATING,), pos=Vec2(50.0, 50.0),
    )
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(50.0, 60.0), health=100.0)

    R.apply_monster_death_affixes(
        object(), 0, creature,
        state=state, players=[player], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )

    # No instant damage - the blast is fused, not immediate.
    assert player.health == pytest.approx(100.0)
    assert len(state.pending_monster_detonations) == 1
    det = state.pending_monster_detonations[0]
    assert det.timer == pytest.approx(R.BOMBER_FUSE_DELAY_S)
    assert det.player_damage == pytest.approx(R.VOLATILE_DAMAGE * R.BOMBER_DAMAGE_MULT)
    assert det.creature_damage == pytest.approx(R.VOLATILE_DAMAGE * R.BOMBER_DAMAGE_MULT)


def test_monster_display_name_has_no_prefix_suffix_cap() -> None:
    # Not native: the mechanical prefix/suffix split is gone - every "before"
    # word and every "of X" word shows, however many are rolled.
    name = R.monster_display_name(
        "zombie",
        (R.AffixId.OVERGROWN, R.AffixId.HASTED, R.AffixId.ARMORED, R.AffixId.FLAME_WARDED),
    )
    assert name == "Brood-Fed Rampant Zombie of Plating of Warding"


def test_turtle_resists_a_front_hit_but_not_a_flanked_one() -> None:
    creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=1, affixes=(R.AffixId.SHELLED,), heading=0.0)
    # front-facing direction = heading - HALF_PI; a hit whose impulse points
    # the opposite way (i.e. the shooter was roughly in front of it) should
    # be resisted.
    from crimson.math_parity import NATIVE_HALF_PI

    front_angle = 0.0 - NATIVE_HALF_PI
    front_impulse = Vec2(-math.cos(front_angle), -math.sin(front_angle))
    mult = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 100.0, impulse=front_impulse)
    assert mult == pytest.approx(R.TURTLE_FRONT_RESIST_MULT)

    flank_impulse = Vec2(-math.cos(front_angle + math.pi / 2.0), -math.sin(front_angle + math.pi / 2.0))
    mult = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 100.0, impulse=flank_impulse)
    assert mult == pytest.approx(1.0)


def test_endurance_caps_only_the_first_hit_in_each_window() -> None:
    creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=2, affixes=(R.AffixId.ENDURANCE,))
    first = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 50.0)
    assert first * 50.0 == pytest.approx(R.ENDURANCE_CAP_DAMAGE)
    assert creature.affix_endurance_window == pytest.approx(R.ENDURANCE_WINDOW_S)

    second = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 50.0)
    assert second == pytest.approx(1.0)

    creature.affix_endurance_window = 0.0
    third = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 50.0)
    assert third * 50.0 == pytest.approx(R.ENDURANCE_CAP_DAMAGE)


def test_flickering_is_fully_invulnerable_during_its_window() -> None:
    creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=3, affixes=(R.AffixId.FLICKERING,))
    creature.affix_flicker_active = 0.5
    assert R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 999.0) == 0.0

    creature.affix_flicker_active = 0.0
    assert R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 999.0) == pytest.approx(1.0)


def test_flickering_cycles_through_telegraph_and_active_windows() -> None:
    creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, rarity=3, affixes=(R.AffixId.FLICKERING,))
    pool = _AffixPool([creature])

    R.update_monster_affixes([], pool, R.FLICKER_INTERVAL_S, state=object())
    assert creature.affix_flicker_active == pytest.approx(R.FLICKER_DURATION_S)

    R.update_monster_affixes([], pool, R.FLICKER_DURATION_S + 0.01, state=object())
    assert creature.affix_flicker_active == 0.0
    assert creature.affix_flicker_timer == pytest.approx(R.FLICKER_INTERVAL_S)


def test_second_wind_saves_the_creature_once_then_heals_over_time() -> None:
    creature = CreatureState(active=True, hp=10.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.SECOND_WIND,))
    mult = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 500.0)
    creature.hp = max(0.0, creature.hp - 500.0 * mult)

    assert creature.hp == pytest.approx(1.0)
    assert creature.affix_second_wind_used is True
    assert creature.affix_second_wind_heal_remaining == pytest.approx(100.0 * R.SECOND_WIND_HEAL_FRACTION)

    # It's a one-time save - the next lethal hit isn't clamped.
    mult_again = R.monster_affix_on_hit(creature, int(CreatureDamageType.BULLET), 500.0)
    assert mult_again == pytest.approx(1.0)

    pool = _AffixPool([creature])
    R.update_monster_affixes([], pool, R.SECOND_WIND_HEAL_DURATION_S, state=object())
    assert creature.hp == pytest.approx(1.0 + 100.0 * R.SECOND_WIND_HEAL_FRACTION)
    assert creature.affix_second_wind_heal_timer == 0.0


def test_inevitability_fully_heals_and_grants_a_new_modifier_after_the_interval() -> None:
    creature = CreatureState(
        active=True, hp=1.0, max_hp=500.0, rarity=3, affixes=(R.AffixId.INEVITABILITY,),
    )
    pool = _AffixPool([creature])
    player = PlayerState(index=0, pos=Vec2(), experience=50_000)

    R.update_monster_affixes([player], pool, R.INEVITABILITY_INTERVAL_S, state=object())

    assert creature.hp == pytest.approx(500.0)
    assert len(creature.affixes) == 2
    gained = creature.affixes[1]
    assert gained not in R._STATIC_STAT_ONLY_AFFIX_IDS
    assert creature.affix_inevitability_timer == pytest.approx(R.INEVITABILITY_INTERVAL_S)


def test_command_aura_boosts_nearby_allies_contact_damage_not_its_own() -> None:
    caster = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.COMMAND,), pos=Vec2(0.0, 0.0))
    ally = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=1, contact_damage=10.0, pos=Vec2(50.0, 0.0))
    pool = _AffixPool([caster, ally])

    R.update_monster_affixes([], pool, 0.016, state=object())

    assert ally.contact_damage == pytest.approx(10.0 * (1.0 + R.COMMAND_AURA_CONTACT_BONUS))
    assert caster.contact_damage == pytest.approx(0.0)  # doesn't buff itself


def test_choir_aura_heals_nearby_allies() -> None:
    caster = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.CHOIR,), pos=Vec2(0.0, 0.0))
    ally = CreatureState(active=True, hp=50.0, max_hp=200.0, rarity=1, pos=Vec2(50.0, 0.0))
    pool = _AffixPool([caster, ally])

    R.update_monster_affixes([], pool, 1.0, state=object())

    assert ally.hp == pytest.approx(50.0 + 200.0 * R.CHOIR_AURA_HEAL_FRAC_PER_S)


def test_vanguard_and_warding_ground_reduce_incoming_damage_for_nearby_allies() -> None:
    warder = CreatureState(
        active=True, hp=100.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.WARDING_GROUND,), pos=Vec2(0.0, 0.0),
    )
    guardian = CreatureState(
        active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.VANGUARD,), pos=Vec2(0.0, 0.0),
    )
    ally = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=1, pos=Vec2(50.0, 0.0))
    pool = _AffixPool([warder, guardian, ally])

    R.update_monster_affixes([], pool, 0.016, state=object())

    assert ally.affix_incoming_damage_mult == pytest.approx(R.WARDING_GROUND_MULT * R.VANGUARD_AURA_MULT)
    mult = R.monster_affix_on_hit(ally, int(CreatureDamageType.BULLET), 100.0)
    assert mult == pytest.approx(R.WARDING_GROUND_MULT * R.VANGUARD_AURA_MULT)


def test_phalanx_reduces_damage_per_nearby_linked_ally_up_to_the_cap() -> None:
    a = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.PHALANX,), pos=Vec2(0.0, 0.0))
    b = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.PHALANX,), pos=Vec2(10.0, 0.0))
    c = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.PHALANX,), pos=Vec2(20.0, 0.0))
    pool = _AffixPool([a, b, c])

    R.update_monster_affixes([], pool, 0.016, state=object())

    # `a` has 2 other Phalanx allies nearby -> -20%.
    assert a.affix_incoming_damage_mult == pytest.approx(1.0 - 2 * R.PHALANX_REDUCTION_PER_ALLY)


def test_growth_and_soul_eater_stack_off_a_nearby_ally_death() -> None:
    dying = CreatureState(active=True, hp=0.0, max_hp=50.0, rarity=1, pos=Vec2(0.0, 0.0))
    grower = CreatureState(
        active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.GROWTH,), pos=Vec2(10.0, 0.0),
    )
    reaper = CreatureState(
        active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.SOULS,), pos=Vec2(10.0, 0.0),
    )
    pool = _AffixPool([dying, grower, reaper])

    R.apply_monster_death_affixes(
        pool, 0, dying, state=object(), players=[], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )

    assert grower.affix_growth_stacks == 1
    assert grower.max_hp == pytest.approx(100.0 * (1.0 + R.GROWTH_HP_BONUS_PER_STACK))
    assert grower.hp == pytest.approx(100.0 * (1.0 + R.GROWTH_HP_BONUS_PER_STACK))
    assert reaper.affix_soul_stacks == 1


def test_dread_static_and_gluttony_auras_affect_nearby_players() -> None:
    from crimson.gameplay import GameplayState

    state = GameplayState()
    state.bonuses.freeze = 5.0
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    player.weapon.reload_timer = 2.0
    dread = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.DREAD,), pos=Vec2(0.0, 0.0))
    static = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.STATIC,), pos=Vec2(0.0, 0.0))
    gluttony = CreatureState(
        active=True, hp=100.0, max_hp=100.0, rarity=4, affixes=(R.AffixId.GLUTTONY,), pos=Vec2(0.0, 0.0),
    )
    pool = _AffixPool([dread, static, gluttony])
    start_spread = float(player.spread_heat)
    start_reload = float(player.weapon.reload_timer)

    R.update_monster_affixes([player], pool, 1.0, state=state)

    assert float(player.spread_heat) > start_spread
    assert float(player.weapon.reload_timer) > start_reload
    # update_monster_affixes only applies Gluttony's *extra* drain here - the
    # base 1x decay happens separately in bonuses/update.py.
    assert state.bonuses.freeze == pytest.approx(5.0 - R.GLUTTONY_EXTRA_DECAY_MULT)


def test_vortex_pulls_the_player_toward_it() -> None:
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.VORTEX,), pos=Vec2(0.0, 0.0))
    player = PlayerState(index=0, pos=Vec2(100.0, 0.0))
    pool = _AffixPool([creature])

    R.update_monster_affixes([player], pool, 1.0, state=object())

    assert 0.0 < player.pos.x < 100.0


def test_vortex_also_pulls_a_turret_toward_it() -> None:
    # Not native: Relic of the Turret (meta/relics_impl/turret.py) - a turret
    # has move_speed=0.0 by design (no self-propulsion), but Vortex's pull is
    # a direct position lerp independent of move_speed, so it should still
    # drag a turret the same as it would any other unit on the field.
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.VORTEX,), pos=Vec2(0.0, 0.0))
    turret = CreatureState(active=True, is_turret=True, hp=100.0, max_hp=100.0, move_speed=0.0, pos=Vec2(100.0, 0.0))
    pool = _AffixPool([creature, turret])

    R.update_monster_affixes([], pool, 1.0, state=object())

    assert 0.0 < turret.pos.x < 100.0


def test_pyre_and_anchoring_queue_a_delayed_area_effect_then_resolve() -> None:
    from crimson.gameplay import GameplayState

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0), health=100.0)
    pyre_creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.PYRE,), pos=Vec2(0.0, 0.0),
    )

    R.apply_monster_death_affixes(
        object(), 0, pyre_creature, state=state, players=[player], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )

    assert len(state.pending_monster_area_effects) == 1
    effect = state.pending_monster_area_effects[0]
    assert effect.triggered is False

    class _EmptyPool:
        entries: list = []

    # Still fused.
    R._tick_pending_area_effects([player], _EmptyPool(), 0.05, state=state)
    assert player.health == pytest.approx(100.0)
    assert state.pending_monster_area_effects[0].triggered is False

    # Fuse runs out - the field goes live and starts ticking damage.
    R._tick_pending_area_effects([player], _EmptyPool(), R.PYRE_FUSE_DELAY_S, state=state)
    assert state.pending_monster_area_effects[0].triggered is True
    assert player.health < 100.0

    # Runs for its full duration, then despawns.
    R._tick_pending_area_effects([player], _EmptyPool(), R.PYRE_DURATION_S, state=state)
    assert state.pending_monster_area_effects == []


def test_anchoring_also_pulls_a_turret_toward_the_zone() -> None:
    # Not native: same move_speed-independent pull as Vortex, but for the
    # delayed post-death "Gravemark" zone instead of a live creature's aura.
    from crimson.gameplay import GameplayState

    state = GameplayState()
    anchor_creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=3, affixes=(R.AffixId.ANCHORING,), pos=Vec2(0.0, 0.0),
    )
    turret = CreatureState(active=True, is_turret=True, hp=100.0, max_hp=100.0, move_speed=0.0, pos=Vec2(100.0, 0.0))

    R.apply_monster_death_affixes(
        object(), 0, anchor_creature, state=state, players=[], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )
    assert len(state.pending_monster_area_effects) == 1

    pool = _AffixPool([turret])
    # Fuse runs out - the pull zone goes live.
    R._tick_pending_area_effects([], pool, R.ANCHORING_FUSE_DELAY_S, state=state)
    assert state.pending_monster_area_effects[0].triggered is True
    assert 0.0 < turret.pos.x < 100.0


def test_bomber_detonation_resolves_with_nerfed_damage_once_the_fuse_runs_out() -> None:
    from crimson.gameplay import GameplayState

    creature = CreatureState(
        active=True, hp=0.0, max_hp=100.0, rarity=2, affixes=(R.AffixId.DETONATING,), pos=Vec2(50.0, 50.0),
    )
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(50.0, 60.0), health=100.0)

    R.apply_monster_death_affixes(
        object(), 0, creature,
        state=state, players=[player], rng=None, detail_preset=5,
        world_width=1000.0, world_height=1000.0,
    )

    class _EmptyPool:
        entries: list = []

    # Still fused - not enough time has passed.
    R._tick_pending_detonations([player], _EmptyPool(), 0.1, state=state)
    assert player.health == pytest.approx(100.0)
    assert len(state.pending_monster_detonations) == 1

    # Fuse runs out - the blast actually lands now, nerfed from the old flat
    # VOLATILE_DAMAGE.
    R._tick_pending_detonations([player], _EmptyPool(), R.BOMBER_FUSE_DELAY_S, state=state)
    assert player.health == pytest.approx(100.0 - R.VOLATILE_DAMAGE * R.BOMBER_DAMAGE_MULT)
    assert state.pending_monster_detonations == []
