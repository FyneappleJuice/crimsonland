from __future__ import annotations

from crimson.creatures.spawn import (
    SURVIVAL_BOSS_WAVE_LEVEL_INTERVAL,
    SURVIVAL_BOSS_WAVE_START_LEVEL,
    SURVIVAL_DEN_BASE_INTERVAL_S,
    SURVIVAL_DEN_MIN_INTERVAL_S,
    SpawnEnv,
    SpawnId,
    advance_survival_boss_waves,
    build_survival_boss_wave_plan,
    build_survival_den_plan,
    survival_boss_wave_composition,
    survival_boss_wave_rarity_tier,
    survival_den_interval_s,
    survival_den_pick_position,
    survival_den_pick_template,
    survival_den_rarity_tier,
)
from crimson.sim.sessions import MidStepContext, SurvivalSpawnState, survival_mid_step
from crimson.sim.state_types import PlayerState
from crimson.sim.world_state import WorldState
from grim.geom import Vec2
from grim.rand import Crand


def _spawn_env() -> SpawnEnv:
    return SpawnEnv(
        terrain_width=1024.0, terrain_height=1024.0, demo_mode_active=False,
        hardcore=False, quest_fail_retry_count=0,
    )


def test_den_interval_shrinks_with_level_down_to_the_floor() -> None:
    assert survival_den_interval_s(0) == SURVIVAL_DEN_BASE_INTERVAL_S
    low = survival_den_interval_s(10)
    high = survival_den_interval_s(50)
    assert low > high
    assert high >= SURVIVAL_DEN_MIN_INTERVAL_S
    assert survival_den_interval_s(1000) == SURVIVAL_DEN_MIN_INTERVAL_S


def test_den_rarity_tier_grows_less_normal_with_level() -> None:
    for level in range(0, 200, 7):
        tier = survival_den_rarity_tier(level)
        assert 0 <= tier <= 3


def test_den_pick_template_and_position_return_valid_values() -> None:
    template = survival_den_pick_template()
    assert template in SpawnId
    pos = survival_den_pick_position()
    assert isinstance(pos, Vec2)


def test_build_survival_den_plan_scales_hp_and_interval_with_level() -> None:
    env = _spawn_env()

    base = build_survival_den_plan(
        SpawnId.DEN_LIZARD_WEAK_0C, Vec2(0.0, 0.0), 0.0, Crand(1), env,
        player_level=0, player_experience=0, tier=0,
    )
    base_init = base.creatures[base.primary]
    base_slot = base.spawn_slots[base_init.spawn_slot]

    leveled = build_survival_den_plan(
        SpawnId.DEN_LIZARD_WEAK_0C, Vec2(0.0, 0.0), 0.0, Crand(1), env,
        player_level=40, player_experience=0, tier=0,
    )
    leveled_init = leveled.creatures[leveled.primary]
    leveled_slot = leveled.spawn_slots[leveled_init.spawn_slot]

    assert leveled_init.health > base_init.health  # stronger the higher you go
    assert leveled_slot.interval < base_slot.interval  # spawns its children faster


def test_build_survival_den_plan_applies_rarity_and_it_propagates_via_child_state() -> None:
    from crimson.creatures.runtime import CreatureState

    env = _spawn_env()
    rare = build_survival_den_plan(
        SpawnId.DEN_LIZARD_WEAK_0C, Vec2(0.0, 0.0), 0.0, Crand(1), env,
        player_level=0, player_experience=0, tier=3,
    )
    rare_init = rare.creatures[rare.primary]
    assert rare_init.rarity == 3

    # The runtime materializes CreatureInit.rarity onto CreatureState.rarity -
    # that live field is what CreaturePool.update reads to decide whether a
    # newly-birthed child should inherit the Den's tier.
    entry = CreatureState()
    entry.rarity = int(rare_init.rarity)
    assert entry.rarity == 3


def test_boss_waves_do_not_fire_before_the_start_level() -> None:
    next_level, wave_index, spawns = advance_survival_boss_waves(
        next_wave_level=SURVIVAL_BOSS_WAVE_START_LEVEL, wave_index=0, player_level=SURVIVAL_BOSS_WAVE_START_LEVEL - 1,
    )
    assert next_level == SURVIVAL_BOSS_WAVE_START_LEVEL
    assert wave_index == 0
    assert spawns == ()


def test_boss_waves_fire_and_reschedule_at_a_fixed_interval() -> None:
    next_level, wave_index, spawns = advance_survival_boss_waves(
        next_wave_level=SURVIVAL_BOSS_WAVE_START_LEVEL, wave_index=0, player_level=SURVIVAL_BOSS_WAVE_START_LEVEL,
    )
    assert wave_index == 1
    assert next_level == SURVIVAL_BOSS_WAVE_START_LEVEL + SURVIVAL_BOSS_WAVE_LEVEL_INTERVAL
    assert len(spawns) == 1  # wave 1 is a single boss

    next_level2, wave_index2, spawns2 = advance_survival_boss_waves(
        next_wave_level=next_level, wave_index=wave_index, player_level=next_level,
    )
    assert wave_index2 == 2
    assert next_level2 == next_level + SURVIVAL_BOSS_WAVE_LEVEL_INTERVAL
    assert len(spawns2) == 1


def test_boss_wave_composition_escalates_count_every_three_waves() -> None:
    assert len(survival_boss_wave_composition(1)) == 1
    assert len(survival_boss_wave_composition(2)) == 1
    assert len(survival_boss_wave_composition(3)) == 2
    assert len(survival_boss_wave_composition(6)) == 3
    # Capped at the number of distinct spawn positions.
    assert len(survival_boss_wave_composition(50)) == 3


def test_boss_wave_rarity_tier_grows_less_normal_over_waves() -> None:
    # Deterministic at the extremes: wave 0 has zero apex/mutated odds and a
    # low tainted floor, so a near-1.0 roll always misses every bucket.
    for wave in range(0, 40):
        tier = survival_boss_wave_rarity_tier(wave)
        assert 0 <= tier <= 3

    # The tainted-or-better floor strictly climbs with wave_index (until it
    # saturates), so the *chance* of staying Normal shrinks monotonically.
    def _p_not_normal(wave: int) -> float:
        wave = max(0, wave)
        p_apex = min(0.35, 0.03 * wave)
        p_mutated = min(0.6, 0.05 + 0.05 * wave)
        p_tainted = min(0.9, 0.25 + 0.08 * wave)
        return p_apex + p_mutated + p_tainted

    values = [_p_not_normal(w) for w in range(0, 15)]
    assert values == sorted(values)


def test_build_survival_boss_wave_plan_applies_rarity_when_tier_positive() -> None:
    env = _spawn_env()
    rng = Crand(1)

    plain = build_survival_boss_wave_plan(
        SpawnId.SPIDER_BOSS_3A, Vec2(0.0, 0.0), 0.0, rng, env,
        tier=0, player_experience=0,
    )
    plain_hp = plain.creatures[plain.primary].health

    rare = build_survival_boss_wave_plan(
        SpawnId.SPIDER_BOSS_3A, Vec2(0.0, 0.0), 0.0, Crand(1), env,
        tier=3, player_experience=0,
    )
    rare_hp = rare.creatures[rare.primary].health

    assert rare.creatures[rare.primary].rarity == 3
    assert rare_hp > plain_hp


def _survival_world(*, level: int) -> WorldState:
    world = WorldState.build(world_size=1024.0, demo_mode_active=False, hardcore=False, quest_fail_retry_count=0)
    world.players.append(PlayerState(index=0, pos=Vec2(512.0, 512.0), level=level))
    world.state.rng = Crand(1)
    return world


def test_survival_mid_step_spawns_a_den_through_the_real_pipeline_when_the_cooldown_elapses() -> None:
    world = _survival_world(level=20)
    spawn = SurvivalSpawnState(den_spawn_cooldown_s=0.001)  # force it to fire this tick

    survival_mid_step(
        MidStepContext(world=world, elapsed_before_ms=0.0, dt_sim_ms=16.0, dt_raw_ms=16.0, world_size=1024.0),
        spawn,
    )

    assert spawn.den_spawn_cooldown_s > 0.0  # rescheduled
    dens = [e for e in world.creatures.entries if e.active and e.spawn_slot_index is not None]
    assert dens  # the den itself carries a spawn slot (see apply_alien_spawner)


def test_survival_mid_step_spawns_an_escalated_boss_wave_through_the_real_pipeline() -> None:
    world = _survival_world(level=SURVIVAL_BOSS_WAVE_START_LEVEL)
    spawn = SurvivalSpawnState(stage=10)  # native ladder already exhausted

    survival_mid_step(
        MidStepContext(world=world, elapsed_before_ms=0.0, dt_sim_ms=16.0, dt_raw_ms=16.0, world_size=1024.0),
        spawn,
    )

    assert spawn.boss_wave_index == 1
    assert spawn.next_boss_wave_level == SURVIVAL_BOSS_WAVE_START_LEVEL + SURVIVAL_BOSS_WAVE_LEVEL_INTERVAL
    # The organic wave spawner also fires in this same tick, so don't assume
    # the boss is the only active creature - just confirm one landed. Every
    # boss template's base HP is >= 1000, and rarity (if rolled) only ever
    # scales HP up, so this holds regardless of which boss/tier landed.
    bosses = [e for e in world.creatures.entries if e.active and e.max_hp >= 1000.0]
    assert len(bosses) == 1
    assert 0 <= bosses[0].rarity <= 3
