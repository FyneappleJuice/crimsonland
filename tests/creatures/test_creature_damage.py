from __future__ import annotations

from collections.abc import Callable

from crimson.creatures.damage import (
    creature_apply_damage,
    creature_apply_damage_with_lethal_followup,
    resolve_native_death_sfx,
)
from crimson.creatures.damage_runtime import CreatureDamageRuntime
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreaturePool, CreatureState
from crimson.creatures.spawn import CreatureFlags, CreatureTypeId
from crimson.effects_atlas import EffectId
from crimson.gameplay import GameplayState
from crimson.math_parity import f32, x87_pc24_mul, x87_pc24_sub
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.rng_caller_static import RngCallerStatic
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from grim.sfx_map import SfxId
from tests.support.helpers import ScriptedCrand, assert_float_close, assert_rng_progression


def test_damage_type1_heading_jitter_uses_rand_without_player_attacker() -> None:
    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0), heading=0.0)
    player = PlayerState(index=0, pos=Vec2())
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    before_calls = rng.calls
    before_state = rng.state

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_creature(38),
        dt=0.016,
        players=[player],
        rng=rng,
    )

    assert killed is False
    assert_rng_progression(
        rng,
        before_calls=before_calls,
        before_state=before_state,
        expected_draws=1,
        expected_after_state=0,
    )
    assert rng.values_since(before_calls) == [0]
    assert [record.caller for record in rng.records_since(before_calls)] == [
        RngCallerStatic.CREATURE_APPLY_DAMAGE_HEADING_JITTER,
    ]
    assert creature.heading == -0.10240000486373901


def test_damage_type1_heading_jitter_rounds_each_x87_operation() -> None:
    creature = CreatureState(
        active=True,
        hp=1.5709114074707031,
        size=45.0,
        flags=CreatureFlags(0),
        heading=-0.054194413125514984,
    )

    killed = creature_apply_damage(
        creature,
        damage_amount=109.99357604980469,
        damage_type=1,
        impulse=Vec2(1.0, 1.0),
        owner=OwnerRef.from_player(0),
        dt=0.09600000083446503,
        players=[PlayerState(index=0, pos=Vec2())],
        rng=ScriptedCrand(2932),
    )

    assert killed
    assert creature.heading == 0.03825003653764725


def test_damage_type1_heading_jitter_skips_ping_pong_creatures() -> None:
    creature = CreatureState(
        active=True,
        hp=100.0,
        size=50.0,
        flags=CreatureFlags.ANIM_PING_PONG,
        heading=0.0,
    )
    player = PlayerState(index=0, pos=Vec2())
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    before_calls = rng.calls
    before_state = rng.state

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_creature(38),
        dt=0.016,
        players=[player],
        rng=rng,
    )

    assert killed is False
    assert_rng_progression(
        rng,
        before_calls=before_calls,
        before_state=before_state,
        expected_draws=0,
        expected_after_state=0,
    )
    assert rng.values_since(before_calls) == []
    assert_float_close(creature.heading, 0.0)


def test_damage_type1_global_perks_apply_with_non_player_owner() -> None:
    creature = CreatureState(active=True, hp=74.0413, size=50.0, flags=CreatureFlags(0), heading=0.0)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 1

    killed = creature_apply_damage(
        creature,
        damage_amount=73.5593,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_creature(10),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is True
    assert creature.hp == -80.43323516845703


def test_damage_perks_use_any_player_owning_them() -> None:
    player0 = PlayerState(index=0, pos=Vec2())
    player1 = PlayerState(index=1, pos=Vec2())
    player1.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1

    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0))

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=CreatureDamageType.BULLET,
        impulse=Vec2(),
        owner=OwnerRef.from_player(1),
        dt=0.016,
        players=[player0, player1],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is False
    assert_float_close(creature.hp, 85.0)


def test_stacked_bullet_damage_perks_fold_into_one_multiply() -> None:
    # Barrel Greaser (x1.4) and Doctor (x1.2) now both feed
    # stats.damage_mult_bullet (crimson.progression) and resolve to a single
    # x1.68 multiply instead of the original two sequential pc24 multiplies -
    # a deliberate, documented ULP change (build content no longer chases
    # native float parity). A single perk still matches its old constant
    # exactly; see tests/progression/test_migrated_perks.py.
    creature = CreatureState(
        active=True,
        hp=435.9342956542969,
        size=50.0,
        flags=CreatureFlags.ANIM_PING_PONG,
    )
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 1
    player.perk_counts[int(PerkId.DOCTOR)] = 1

    killed = creature_apply_damage(
        creature,
        damage_amount=261.8189392089844,
        damage_type=CreatureDamageType.BULLET,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is True
    assert creature.hp == -3.9215087890625


def test_owner_exempt_from_run_mod_affinity_ignores_elemental_affinity_run_mod() -> None:
    # Man Bomb/Hot Tempered/Angry Reloader/Fire Cough all spawn their canned
    # burst with OwnerRef.without_run_mod_affinity() - a matching Elemental
    # Affinity pick (here: Ion Damage) must not scale the hit.
    from crimson.run_mods.ids import RunModId

    player = PlayerState(index=0, pos=Vec2())
    player.run_mod_counts[int(RunModId.ION_DAMAGE)] = 1

    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0))
    creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=CreatureDamageType.ION,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0).without_run_mod_affinity(),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert_float_close(creature.hp, 90.0)


def test_owner_exempt_from_run_mod_affinity_ignores_weapon_affinity_run_mod() -> None:
    # Weapon Affinity (Pistol Damage) must not scale a Mr. Melee-style
    # MELEE hit even though the player is currently holding a pistol.
    from crimson.run_mods.ids import RunModId
    from crimson.sim.state_types import WeaponSlot
    from crimson.weapons import WeaponId

    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    player.run_mod_counts[int(RunModId.PISTOL_DAMAGE)] = 1

    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0))
    creature_apply_damage(
        creature,
        damage_amount=25.0,
        damage_type=CreatureDamageType.MELEE,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0).without_run_mod_affinity(),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert_float_close(creature.hp, 75.0)


def test_owner_exempt_from_run_mod_affinity_still_gets_all_damage_run_mod() -> None:
    from crimson.run_mods.ids import RunModId

    player = PlayerState(index=0, pos=Vec2())
    player.run_mod_counts[int(RunModId.ALL_DAMAGE)] = 1

    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0))
    creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=CreatureDamageType.ION,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0).without_run_mod_affinity(),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    expected_damage = x87_pc24_mul(f32(10.0), f32(1.015))
    assert_float_close(creature.hp, x87_pc24_sub(f32(100.0), expected_damage))


def test_owner_exempt_from_run_mod_affinity_still_gets_real_perk_interactions() -> None:
    # Ion Gun Master and Pyromaniac are native perks, not run mods - they
    # still boost Man Bomb's/Fire Cough's own exempt damage even though the
    # new run-mod Elemental Affinity bucket does not.
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.ION_GUN_MASTER)] = 1

    creature = CreatureState(active=True, hp=100.0, size=50.0, flags=CreatureFlags(0))
    creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=CreatureDamageType.ION,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0).without_run_mod_affinity(),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    # Ion Mastery: x1.5 -> 10 * 1.5 = 15.0
    assert_float_close(creature.hp, 85.0)


def test_damage_float_parameter_rounds_at_the_native_abi_boundary() -> None:
    creature = CreatureState(active=True, hp=554.2709350585938, size=50.0)

    killed = creature_apply_damage(
        creature,
        damage_amount=616.6504260335757,
        damage_type=CreatureDamageType.EXPLOSION,
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is True
    assert creature.hp == -62.3795166015625


def test_nonlethal_damage_does_not_reset_non_alive_lifecycle_stage() -> None:
    creature = CreatureState(active=True, hp=100.0, lifecycle_stage=12.0, size=50.0, flags=CreatureFlags(0))

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=3,
        impulse=Vec2(),
        owner=OwnerRef.from_creature(0),
        dt=0.016,
        players=[],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is False
    assert_float_close(creature.lifecycle_stage, 12.0)


def test_lethal_shock_damage_spawns_armored_debris_after_death_handling() -> None:
    state = GameplayState()
    creature = CreatureState(
        active=True,
        hp=5.0,
        lifecycle_stage=16.0,
        size=50.0,
        flags=CreatureFlags.RANGED_ATTACK_SHOCK,
        pos=Vec2(10.0, 20.0),
        vel=Vec2(10.0, 20.0),
    )
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    before_calls = rng.calls
    order: list[str] = []

    class _Runtime(CreatureDamageRuntime):
        def on_creature_lethal(
            self,
            creature_index: int,
            resolve_damage_followup: Callable[[], tuple[SfxId, ...]],
        ) -> None:
            # Native order: `creature_handle_death` draws happen here, before the
            # shock-burst / death-SFX rands.
            assert rng.calls - before_calls == 0
            order.append(f"handle_death:{creature_index}")
            assert creature.vel == Vec2(9.0, 18.0)
            assert resolve_damage_followup() == ()
            assert creature.vel == Vec2(7.0, 14.0)
            order.append("death_followup")

    killed = creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=7,
        damage_amount=10.0,
        damage_type=3,
        impulse=Vec2(1.0, 2.0),
        owner=OwnerRef.from_creature(0),
        dt=0.016,
        players=[],
        rng=rng,
        effects=state.effects,
        detail_preset=5,
        creature_damage_runtime=_Runtime(),
    )

    assert killed is True
    assert order == ["handle_death:7", "death_followup"]
    active = state.effects.iter_active()
    assert len(active) == 5
    assert all(int(entry.effect_id) == int(EffectId.BURST) for entry in active)
    assert rng.calls - before_calls == 20
    assert [record.caller for record in rng.records_since(before_calls)] == [
        RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_ROTATION,
        RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_VEL_X,
        RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_VEL_Y,
        RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_SCALE_STEP,
    ] * 5


def test_split_children_inherit_only_initial_damage_impulse() -> None:
    state = GameplayState()
    pool = CreaturePool()
    creature = pool.entries[0]
    creature.active = True
    creature.hp = 5.0
    creature.max_hp = 400.0
    creature.lifecycle_stage = 16.0
    creature.size = 40.0
    creature.flags = CreatureFlags.SPLIT_ON_DEATH
    creature.vel = Vec2(10.0, 20.0)
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)

    class _Runtime(CreatureDamageRuntime):
        def on_creature_lethal(
            self,
            creature_index: int,
            resolve_damage_followup: Callable[[], tuple[SfxId, ...]],
        ) -> None:
            pool.handle_death(
                creature_index,
                state=state,
                players=[],
                rng=rng,
                dt=0.016,
                world_width=1024.0,
                world_height=1024.0,
                fx_queue=None,
            )
            assert creature.vel == Vec2(9.0, 18.0)
            assert pool.entries[1].vel == Vec2(9.0, 18.0)
            assert pool.entries[2].vel == Vec2(9.0, 18.0)

            resolve_damage_followup()

            assert creature.vel == Vec2(7.0, 14.0)
            assert pool.entries[1].vel == Vec2(9.0, 18.0)
            assert pool.entries[2].vel == Vec2(9.0, 18.0)

    killed = creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=0,
        damage_amount=10.0,
        damage_type=CreatureDamageType.EXPLOSION,
        impulse=Vec2(1.0, 2.0),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[],
        rng=rng,
        effects=state.effects,
        creature_damage_runtime=_Runtime(),
    )

    assert killed


def test_lethal_death_sfx_rand_draws_after_death_handling() -> None:
    state = GameplayState()
    creature = CreatureState(
        active=True,
        hp=5.0,
        lifecycle_stage=16.0,
        size=50.0,
        type_id=CreatureTypeId.TROOPER,
        flags=CreatureFlags(0),
        pos=Vec2(10.0, 20.0),
    )
    rng = ScriptedCrand(1, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    before_calls = rng.calls
    order: list[str] = []

    class _Runtime(CreatureDamageRuntime):
        def on_creature_lethal(
            self,
            creature_index: int,
            resolve_damage_followup: Callable[[], tuple[SfxId, ...]],
        ) -> None:
            assert rng.calls - before_calls == 0
            order.append("handle_death")
            assert resolve_damage_followup() == (SfxId.TROOPER_DIE_02,)
            order.append("death_followup")

    killed = creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=0,
        damage_amount=10.0,
        damage_type=3,
        impulse=Vec2(),
        owner=OwnerRef.from_creature(0),
        dt=0.016,
        players=[],
        rng=rng,
        effects=state.effects,
        detail_preset=5,
        creature_damage_runtime=_Runtime(),
    )

    assert killed is True
    assert order == ["handle_death", "death_followup"]
    assert rng.calls - before_calls == 1
    assert [record.caller for record in rng.records_since(before_calls)] == [
        RngCallerStatic.CREATURE_APPLY_DAMAGE_DEATH_SFX,
    ]


def test_resolve_native_death_sfx_default_fixes_trooper_uninitialized_fourth_slot() -> None:
    creature = CreatureState(type_id=CreatureTypeId.TROOPER, flags=CreatureFlags(0))
    rng = ScriptedCrand([0, 1, 2, 3])

    resolved = [resolve_native_death_sfx(creature, rng=rng)[0] for _ in range(4)]

    assert resolved == [
        SfxId.TROOPER_DIE_01,
        SfxId.TROOPER_DIE_02,
        SfxId.TROOPER_DIE_03,
        SfxId.TROOPER_DIE_01,
    ]
    assert [record.caller for record in rng.records] == [
        RngCallerStatic.CREATURE_APPLY_DAMAGE_DEATH_SFX,
    ] * 4
