from __future__ import annotations

import pytest

from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureFlags
from crimson.gameplay import GameplayState, player_update
from crimson.perks import PerkId
from crimson.projectiles.runtime import ProjectilePool
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from grim.sfx_map import SfxId

# Not native: Man Bomb was reworked from an 8-way ion-projectile ring into a
# single instant nuke centered on the player - these cover the new AoE
# damage/radius behavior directly (see man_bomb.py for the constants).
_MAN_BOMB_NUKE_RADIUS = 140.0


def _creature_at(pos: Vec2, *, hp: float = 1000.0) -> CreatureState:
    return CreatureState(active=True, hp=hp, max_hp=hp, size=20.0, pos=pos, flags=CreatureFlags(0))


def _fire_man_bomb(player: PlayerState, creatures: list[CreatureState]) -> GameplayState:
    state = GameplayState()
    player_update(
        player,
        PlayerInput(aim=Vec2(player.pos.x + 1.0, player.pos.y)),
        0.2,
        state,
        players=[player],
        creatures=creatures,
        creature_damage_runtime=DirectCreatureDamageRuntime(creatures=creatures),
    )
    return state


def _player() -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0), man_bomb_timer=3.9)
    player.perk_counts[int(PerkId.MAN_BOMB)] = 1
    return player


def test_man_bomb_deals_no_damage_and_stays_idle_when_not_triggered() -> None:
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0), man_bomb_timer=0.0)
    player.perk_counts[int(PerkId.MAN_BOMB)] = 1
    creature = _creature_at(Vec2(120.0, 100.0))

    _fire_man_bomb(player, [creature])

    assert creature.hp == 1000.0


def test_man_bomb_damages_a_creature_within_radius() -> None:
    player = _player()
    creature = _creature_at(Vec2(150.0, 100.0))  # 50px away, well inside the radius

    _fire_man_bomb(player, [creature])

    assert creature.hp < 1000.0


def test_man_bomb_deals_no_damage_outside_radius() -> None:
    player = _player()
    creature = _creature_at(Vec2(100.0 + _MAN_BOMB_NUKE_RADIUS + 50.0, 100.0))

    _fire_man_bomb(player, [creature])

    assert creature.hp == 1000.0


def test_man_bomb_damage_falls_off_with_distance() -> None:
    player_near = _player()
    near = _creature_at(Vec2(120.0, 100.0))
    _fire_man_bomb(player_near, [near])

    player_far = _player()
    far = _creature_at(Vec2(220.0, 100.0))
    _fire_man_bomb(player_far, [far])

    near_damage = 1000.0 - near.hp
    far_damage = 1000.0 - far.hp
    assert near_damage > far_damage > 0.0


def test_man_bomb_ignores_inactive_creatures() -> None:
    player = _player()
    creature = _creature_at(Vec2(120.0, 100.0))
    creature.active = False

    _fire_man_bomb(player, [creature])

    assert creature.hp == 1000.0


def test_man_bomb_spawns_no_projectiles_and_plays_nuke_sfx() -> None:
    pool = ProjectilePool(size=8)
    player = _player()
    state = GameplayState(projectiles=pool)
    creature = _creature_at(Vec2(120.0, 100.0))

    player_update(
        player,
        PlayerInput(aim=Vec2(101.0, 100.0)),
        0.2,
        state,
        players=[player],
        creatures=[creature],
        creature_damage_runtime=DirectCreatureDamageRuntime(creatures=[creature]),
    )

    assert pool.iter_active() == []
    assert list(state.sfx_queue_quiet) == [SfxId.EXPLOSION_LARGE, SfxId.SHOCKWAVE]


def test_man_bomb_timer_resets_after_triggering() -> None:
    player = _player()
    _fire_man_bomb(player, [])

    assert player.man_bomb_timer == pytest.approx(3.9 + 0.2 - 4.0)
