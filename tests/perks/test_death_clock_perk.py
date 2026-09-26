from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.math_parity import f32, x87_pc24_mul, x87_pc24_sub
from crimson.meta import relics as relics_mod
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import leech as relic_leech
from crimson.perks import PerkId
from crimson.perks.impl.harvester_scythe import harvester_scythe_on_crit
from crimson.perks.impl.soul_tether import soul_tether_absorb
from crimson.perks.runtime.apply import perk_apply
from crimson.perks.runtime.effects import perks_update_effects
from crimson.player_damage import player_take_damage, player_take_projectile_damage
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand, assert_float_close


def test_death_clock_clears_regeneration_and_restores_health() -> None:
    state = GameplayState()
    owner = PlayerState(index=0, pos=Vec2(), health=50.0)
    other = PlayerState(index=1, pos=Vec2(), health=75.0)

    owner.perk_counts[int(PerkId.REGENERATION)] = 2
    owner.perk_counts[int(PerkId.GREATER_REGENERATION)] = 1

    perk_apply(state, [owner, other], PerkId.DEATH_CLOCK)

    assert owner.perk_counts[int(PerkId.DEATH_CLOCK)] == 1
    assert owner.perk_counts[int(PerkId.REGENERATION)] == 0
    assert owner.perk_counts[int(PerkId.GREATER_REGENERATION)] == 0
    assert owner.health == 100.0

    assert other.perk_counts[int(PerkId.DEATH_CLOCK)] == 1
    assert other.perk_counts[int(PerkId.REGENERATION)] == 0
    assert other.perk_counts[int(PerkId.GREATER_REGENERATION)] == 0
    assert other.health == 100.0


def test_death_clock_blocks_damage() -> None:
    state = GameplayState(rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST))
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    applied = player_take_damage(state, player, 10.0, dt=0.1)

    assert applied == 0.0
    assert player.health == 100.0


def test_death_clock_blocks_the_projectile_hit_path_too() -> None:
    # Regression: this path used to skip the Death Clock check entirely (it's
    # the thinner of the two player-damage entry points, and skips several
    # other stat hooks too) - "hits do nothing until then" means *every* hit,
    # not just contact damage.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    applied = player_take_projectile_damage(state, player, 10.0)

    assert applied == 0.0
    assert player.health == 100.0


def test_death_clock_strips_any_existing_shield_on_pickup() -> None:
    state = GameplayState()
    owner = PlayerState(index=0, pos=Vec2(), health=50.0)
    owner.soul_tether_shield = 40.0

    perk_apply(state, [owner], PerkId.DEATH_CLOCK)

    assert owner.soul_tether_shield == 0.0


def test_death_clock_blocks_soul_tether_absorb(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1
    player.perk_counts[int(PerkId.SOUL_TETHER)] = 1
    player.soul_tether_shield = 40.0

    remaining = soul_tether_absorb(player, 10.0)

    assert remaining == 10.0
    assert player.soul_tether_shield == 40.0


def test_death_clock_blocks_leech_heal_on_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: this is the actual bug report - Leech's heal-per-hit easily
    # outpaces Death Clock's fixed ~3.33 HP/s drain on any real weapon's DPS,
    # turning "guaranteed death in 30s" into free permanent invincibility.
    monkeypatch.setattr(relics_mod, "_ACTIVE_RELIC_IDS", (int(RelicId.LEECH_LOW),))
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    relic_leech.heal_on_hit(player, 10_000.0)

    assert player.health == 50.0


def test_death_clock_blocks_leech_kill_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics_mod, "_ACTIVE_RELIC_IDS", (int(RelicId.LEECH_LOW),))
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    relic_leech.hp_cost_on_kill(player)

    assert player.health == 50.0


def test_death_clock_blocks_harvester_scythe_heal() -> None:
    player = PlayerState(index=0, pos=Vec2(), health=50.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1
    player.perk_counts[int(PerkId.HARVESTER_SCYTHE)] = 1

    harvester_scythe_on_crit(player)

    assert player.health == 50.0


def test_death_clock_drains_health_over_time() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    perks_update_effects(state, [player], 1.0)

    assert_float_close(
        player.health,
        x87_pc24_sub(
            f32(100.0),
            x87_pc24_mul(f32(1.0), f32(3.33333325)),
        ),
    )


def test_death_clock_reaches_native_zero_crossing_at_30hz() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=100.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    for _ in range(900):
        perks_update_effects(state, [player], 1.0 / 30.0)

    assert player.health == -0.0008849054574966431

    perks_update_effects(state, [player], 1.0 / 30.0)

    assert player.health == 0.0


def test_death_clock_clamps_dead_health_to_zero() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), health=-1.0)
    player.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    perks_update_effects(state, [player], 0.1)

    assert player.health == 0.0


def test_death_clock_tick_is_gated_by_player0_perk_state() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(), health=100.0)
    player1 = PlayerState(index=1, pos=Vec2(), health=100.0)
    player1.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    perks_update_effects(state, [player0, player1], 1.0)

    assert player0.health == 100.0
    assert player1.health == 100.0


def test_death_clock_tick_applies_to_all_players_when_player0_has_perk() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(), health=100.0)
    player1 = PlayerState(index=1, pos=Vec2(), health=100.0)
    player0.perk_counts[int(PerkId.DEATH_CLOCK)] = 1

    perks_update_effects(state, [player0, player1], 1.0)

    expected = x87_pc24_sub(
        f32(100.0),
        x87_pc24_mul(f32(1.0), f32(3.33333325)),
    )
    assert_float_close(player0.health, expected)
    assert_float_close(player1.health, expected)
