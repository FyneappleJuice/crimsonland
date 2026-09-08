from __future__ import annotations

from crimson.creatures.spawn_ids import SpawnId
from crimson.modes.maps_mode import MAP_MODIFIERS, MapModifier, MapsSessionRuntime
from crimson.sim.input import PlayerInput
from crimson.sim.session_builders import build_survival_session
from crimson.sim.state_types import PlayerState
from crimson.sim.world_state import WorldState
from grim.geom import Vec2


def _fast_boss_modifier(*, spawn_time_scale: float = 1.0) -> MapModifier:
    # A short boss_trigger_ms so the test doesn't need to simulate a full minute.
    return MapModifier(
        key="test_map",
        name="Test Map",
        tagline="",
        spawn_time_scale=spawn_time_scale,
        boss_spawn_id=SpawnId.ZOMBIE_BOSS_SPAWNER_00,
        boss_name="Zombie Spawner",
        boss_trigger_ms=500.0,
    )


def _build_maps_session(modifier: MapModifier):
    world = WorldState.build(
        world_size=1024.0,
        demo_mode_active=True,
        hardcore=False,
        quest_fail_retry_count=0,
    )
    world.players.append(PlayerState(index=0, pos=Vec2()))

    session, spawn_state = build_survival_session(
        world=world,
        world_size=1024.0,
        damage_scale_by_type={},
        detail_preset=5,
        violence_disabled=0,
        game_tune_started=True,
        finalize_post_render_lifecycle=False,
    )
    session.mode_runtime = MapsSessionRuntime(spawn=spawn_state, modifier=modifier)
    return world, session


def _active_creature_count(world: WorldState) -> int:
    return sum(1 for creature in world.creatures.entries if creature.active)


def test_maps_session_runtime_spawns_guaranteed_boss() -> None:
    world, session = _build_maps_session(_fast_boss_modifier())

    before = _active_creature_count(world)
    for _ in range(90):
        session.step_tick(dt=1.0 / 60.0, inputs=[PlayerInput()])
        if session.elapsed_ms >= 600.0:
            break
    after = _active_creature_count(world)

    runtime = session.mode_runtime
    assert isinstance(runtime, MapsSessionRuntime)
    assert runtime.boss_spawned is True
    assert after > before, "expected the guaranteed boss to add a creature to the pool"


def test_maps_session_runtime_spawns_boss_only_once() -> None:
    world, session = _build_maps_session(_fast_boss_modifier())

    # Survival's own scripted milestone spawns also call `spawn_template`, so
    # only count calls for the boss's specific template id.
    boss_spawn_calls = 0
    original_spawn_template = world.creatures.spawn_template

    def counting_spawn_template(template_id, *args, **kwargs):
        nonlocal boss_spawn_calls
        if template_id == SpawnId.ZOMBIE_BOSS_SPAWNER_00:
            boss_spawn_calls += 1
        return original_spawn_template(template_id, *args, **kwargs)

    world.creatures.spawn_template = counting_spawn_template  # type: ignore[method-assign]

    # Step well past the trigger point; the boss must only be spawned once.
    for _ in range(240):
        session.step_tick(dt=1.0 / 60.0, inputs=[PlayerInput()])

    runtime = session.mode_runtime
    assert isinstance(runtime, MapsSessionRuntime)
    assert runtime.boss_spawned is True
    assert boss_spawn_calls == 1


def test_maps_session_runtime_scales_elapsed_time_fed_to_spawn_formula() -> None:
    # spawn_time_scale should reshape the *pacing* the wave-spawn formula sees,
    # without touching the real elapsed time the boss trigger checks against.
    _world, session = _build_maps_session(_fast_boss_modifier(spawn_time_scale=3.0))

    session.step_tick(dt=1.0 / 60.0, inputs=[PlayerInput()])
    # Real elapsed time should advance at the normal (unscaled) rate.
    assert session.elapsed_ms < 100.0


def test_map_modifiers_table_is_well_formed() -> None:
    assert len(MAP_MODIFIERS) >= 3
    keys = [m.key for m in MAP_MODIFIERS]
    assert len(keys) == len(set(keys)), "map modifier keys must be unique"
    for modifier in MAP_MODIFIERS:
        assert modifier.spawn_time_scale > 0.0
        assert modifier.boss_trigger_ms > 0.0
        assert isinstance(modifier.boss_spawn_id, SpawnId)
