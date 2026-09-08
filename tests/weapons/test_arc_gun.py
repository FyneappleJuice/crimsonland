from __future__ import annotations

import pytest

from crimson.creatures.damage_types import CreatureDamageType
from crimson.gameplay import GameplayState
from crimson.progression import refresh_player_stats
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime.arc_gun import (
    ARC_BOLT_LIFETIME,
    ARC_CHAIN_GROWTH,
    ARC_CHAIN_RANGE,
    ARC_DAMAGE,
    ARC_MAX_RANGE,
    ARC_WPU_DAMAGE_MULT,
    ARC_WPU_EXTRA_LINKS,
    arc_chain_points,
    start_arc_strike,
    update_arc_gun,
)
from crimson.weapons import WeaponId, weapon_display_name
from grim.geom import Vec2
from tests.support.factories import RecordingCreatureDamageRuntime
from tests.support.factories import make_creature_state as _creature
from tests.support.helpers import ScriptedCrand


def _RecordingRuntime(creatures):
    return RecordingCreatureDamageRuntime(creatures=creatures, apply_damage=True)


def _calls(runtime) -> list[tuple[int, float, int]]:
    return [(c[0], c[1], c[2]) for c in runtime.calls]


def _rng() -> ScriptedCrand:
    return ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)


def _resolve(player: PlayerState, creatures, runtime) -> None:
    update_arc_gun([player], creatures, 0.016, rng=_rng(), creature_damage_runtime=runtime)


def test_weapon_is_the_arc_gun() -> None:
    assert weapon_display_name(WeaponId.RAYGUN) == "Arc Gun"


def test_firing_flags_a_pending_strike_that_the_updater_resolves() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.RAYGUN, state=state)
    refresh_player_stats([player])

    fire_weapon(WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True, aim=Vec2(200.0, 0.0)), dt=0.016, state=state))
    assert player.arc_gun.pending

    _resolve(player, [], None)
    assert not player.arc_gun.pending


def test_primary_hits_the_creature_nearest_the_cursor_and_chains() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    cursor = Vec2(200.0, 0.0)
    # near cursor, then a chain within ARC_CHAIN_RANGE of it, then one more
    a = _creature(pos=Vec2(210.0, 10.0), hp=1e9, size=20.0)
    b = _creature(pos=Vec2(210.0 + ARC_CHAIN_RANGE - 20.0, 0.0), hp=1e9, size=20.0)
    c = _creature(pos=Vec2(210.0 + 2 * (ARC_CHAIN_RANGE - 20.0), 0.0), hp=1e9, size=20.0)
    far = _creature(pos=Vec2(900.0, 900.0), hp=1e9, size=20.0)  # out of everything
    creatures = [a, b, c, far]
    runtime = _RecordingRuntime(creatures)

    start_arc_strike(player, cursor, weapon_power_up=False)
    _resolve(player, creatures, runtime)

    hit_order = [ci for ci, _, _ in _calls(runtime)]
    assert hit_order[0] == 0  # 'a', nearest the cursor
    assert 3 not in hit_order  # 'far' never touched
    assert all(dt == int(CreatureDamageType.LIGHTNING) for _, _, dt in _calls(runtime))
    # damage *builds* per hop
    dmgs = [d for _, d, _ in _calls(runtime)]
    assert dmgs[0] == pytest.approx(ARC_DAMAGE)
    assert dmgs[1] == pytest.approx(ARC_DAMAGE * ARC_CHAIN_GROWTH)
    assert dmgs[2] == pytest.approx(ARC_DAMAGE * ARC_CHAIN_GROWTH**2)


def test_no_creature_near_the_cursor_fizzles_without_damage() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    lonely = _creature(pos=Vec2(0.0, 400.0), hp=1e9, size=20.0)  # nowhere near the cursor
    runtime = _RecordingRuntime([lonely])

    start_arc_strike(player, Vec2(300.0, 0.0), weapon_power_up=False)
    _resolve(player, [lonely], runtime)

    assert _calls(runtime) == []
    assert player.arc_gun.bolt_timer == pytest.approx(ARC_BOLT_LIFETIME)  # still draws a fizzle
    assert len(arc_chain_points(player.arc_gun)) == 2


def test_target_beyond_max_range_is_ignored() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    cursor = Vec2(ARC_MAX_RANGE + 100.0, 0.0)
    beyond = _creature(pos=Vec2(ARC_MAX_RANGE + 90.0, 0.0), hp=1e9, size=20.0)
    runtime = _RecordingRuntime([beyond])

    start_arc_strike(player, cursor, weapon_power_up=False)
    _resolve(player, [beyond], runtime)
    assert _calls(runtime) == []


def test_wpu_does_not_touch_the_strike_itself() -> None:
    # Normalized WPU: the arc gun gets the +30% fire-rate lever only - the strike
    # geometry / damage / link count are identical hot or cold.
    from crimson.weapon_runtime.arc_gun import ARC_CHAIN_LINKS

    assert ARC_WPU_EXTRA_LINKS == 0
    assert ARC_WPU_DAMAGE_MULT == pytest.approx(1.0)

    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    cursor = Vec2(200.0, 0.0)
    step = ARC_CHAIN_RANGE - 30.0
    creatures = [_creature(pos=Vec2(200.0 + i * step, 0.0), hp=1e9, size=16.0) for i in range(10)]
    runtime = _RecordingRuntime(creatures)

    start_arc_strike(player, cursor, weapon_power_up=True)
    _resolve(player, creatures, runtime)

    assert len(_calls(runtime)) == 1 + ARC_CHAIN_LINKS
    assert _calls(runtime)[0][1] == pytest.approx(ARC_DAMAGE)


def test_lightning_is_its_own_damage_type_and_scaling_line() -> None:
    from crimson.creatures.damage import (
        _CREATURE_DAMAGE_GLOBAL_PRE_STEPS,
        _CreatureDamageCtx,
        _damage_lightning_damage_mult,
    )
    from crimson.owner_ref import OwnerRef
    from crimson.progression.stats import PlayerStats

    assert int(CreatureDamageType.LIGHTNING) == 9
    assert _damage_lightning_damage_mult in _CREATURE_DAMAGE_GLOBAL_PRE_STEPS[CreatureDamageType.LIGHTNING]

    def scaled(team_stats: PlayerStats) -> float:
        ctx = _CreatureDamageCtx(
            creature=_creature(pos=Vec2(), hp=1e9, size=50.0),
            damage=100.0,
            damage_type=int(CreatureDamageType.LIGHTNING),
            impulse=Vec2(),
            owner=OwnerRef.from_player(0),
            dt=0.016,
            players=[],
            rng=_rng(),
            preserve_bugs=False,
            team_stats=team_stats,
        )
        _damage_lightning_damage_mult(ctx)
        return float(ctx.damage)

    assert scaled(PlayerStats()) == pytest.approx(100.0)
    assert scaled(PlayerStats(damage_mult_lightning=1.5)) == pytest.approx(150.0)
    assert scaled(PlayerStats(damage_mult_ion=1.5)) == pytest.approx(100.0)  # ion doesn't touch lightning


def test_bolt_ages_out() -> None:
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    start_arc_strike(player, Vec2(50.0, 0.0), weapon_power_up=False)
    _resolve(player, [], None)
    assert player.arc_gun.bolt_timer > 0.0

    update_arc_gun([player], [], ARC_BOLT_LIFETIME + 0.01, rng=_rng(), creature_damage_runtime=None)
    assert player.arc_gun.bolt_timer == 0.0
    assert player.arc_gun.chain == []
