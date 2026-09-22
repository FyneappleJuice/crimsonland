from __future__ import annotations

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.gameplay import GameplayState, player_update
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime.spawn import projectile_spawn
from grim.geom import Vec2


def _spawn_type(
    state: GameplayState,
    *,
    players: list[PlayerState],
    owner: OwnerRef,
    owner_player_index: int | None = None,
) -> int:
    proj_id = projectile_spawn(
        state,
        players=players,
        pos=Vec2(100.0, 100.0),
        angle=0.0,
        type_id=ProjectileTemplateId.PISTOL,
        owner=owner,
        owner_player_index=owner_player_index,
    )
    assert proj_id >= 0
    return int(state.projectiles.entries[proj_id].type_id)


def _active_type_ids(state: GameplayState) -> list[int]:
    return [int(entry.type_id) for entry in state.projectiles.entries if bool(entry.active)]


def test_projectile_spawn_fire_bullets_default_uses_owner_timer() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(), fire_bullets_timer=1.0)
    player1 = PlayerState(index=1, pos=Vec2(), fire_bullets_timer=0.0)
    players = [player0, player1]

    player1_type = _spawn_type(state, players=players, owner=OwnerRef.from_player(1))
    player0_type = _spawn_type(state, players=players, owner=OwnerRef.from_player(0))

    assert player1_type == int(ProjectileTemplateId.PISTOL)
    assert player0_type == int(ProjectileTemplateId.FIRE_BULLETS)


def test_projectile_spawn_fire_bullets_default_resolves_owner_index_in_player_slice() -> None:
    state = GameplayState()
    player1 = PlayerState(index=1, pos=Vec2(), fire_bullets_timer=1.0)

    player1_type = _spawn_type(state, players=[player1], owner=OwnerRef.from_local_player(0), owner_player_index=1)

    assert player1_type == int(ProjectileTemplateId.FIRE_BULLETS)


def test_projectile_spawn_fire_bullets_default_uses_owner_player_index_with_owner_minus_100() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(), fire_bullets_timer=1.0)
    player1 = PlayerState(index=1, pos=Vec2(), fire_bullets_timer=0.0)
    players = [player0, player1]

    player1_type = _spawn_type(state, players=players, owner=OwnerRef.from_local_player(0), owner_player_index=1)
    player0_type = _spawn_type(state, players=players, owner=OwnerRef.from_local_player(0), owner_player_index=0)

    assert player1_type == int(ProjectileTemplateId.PISTOL)
    assert player0_type == int(ProjectileTemplateId.FIRE_BULLETS)


def test_projectile_spawn_uses_owner_shots_fired_window() -> None:
    players = [
        PlayerState(index=0, pos=Vec2(), fire_bullets_timer=1.0),
        PlayerState(index=1, pos=Vec2()),
        PlayerState(index=2, pos=Vec2()),
        PlayerState(index=3, pos=Vec2()),
    ]

    state = GameplayState()
    spawned_type = _spawn_type(
        state,
        players=players,
        owner=OwnerRef.from_player(3),
    )
    assert spawned_type == int(ProjectileTemplateId.PISTOL)
    assert state.shots_fired[3] == 1
    assert state.shots_fired_total == 1


def test_nuke_fire_bullets_default_is_owner_scoped_but_still_converts_for_owner() -> None:
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(100.0, 100.0), fire_bullets_timer=1.0)
    player1 = PlayerState(index=1, pos=Vec2(120.0, 100.0), fire_bullets_timer=0.0)
    players = [player0, player1]

    bonus_apply(state, player1, BonusId.NUKE, origin=player1.pos, creatures=[], players=players, detail_preset=5)
    non_owner_types = _active_type_ids(state)

    assert int(ProjectileTemplateId.FIRE_BULLETS) not in non_owner_types
    assert set(non_owner_types) <= {int(ProjectileTemplateId.PISTOL), int(ProjectileTemplateId.GAUSS_GUN)}

    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(100.0, 100.0), fire_bullets_timer=0.0)
    player1 = PlayerState(index=1, pos=Vec2(120.0, 100.0), fire_bullets_timer=1.0)
    players = [player0, player1]

    bonus_apply(state, player1, BonusId.NUKE, origin=player1.pos, creatures=[], players=players, detail_preset=5)
    owner_types = _active_type_ids(state)

    assert owner_types
    assert set(owner_types) == {int(ProjectileTemplateId.FIRE_BULLETS)}


def test_hot_tempered_fire_bullets_default_is_owner_scoped() -> None:
    # Not native: Man Bomb used to be covered here too, but it was reworked
    # into an instant nuke (direct AoE damage, no projectiles at all) - it no
    # longer goes through projectile_spawn, so Fire Bullets' override has
    # nothing left to apply to for it.
    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(100.0, 100.0), fire_bullets_timer=1.0)
    player1 = PlayerState(index=1, pos=Vec2(120.0, 100.0), fire_bullets_timer=0.0, hot_tempered_timer=1.95)
    player1.perk_counts[int(PerkId.HOT_TEMPERED)] = 1
    player_update(state=state, player=player1, input_state=PlayerInput(aim=Vec2(121.0, 100.0)), dt=0.1, players=[player0, player1])
    hot_types_non_owner = _active_type_ids(state)
    assert int(ProjectileTemplateId.FIRE_BULLETS) not in hot_types_non_owner

    state = GameplayState()
    player0 = PlayerState(index=0, pos=Vec2(100.0, 100.0), fire_bullets_timer=0.0)
    player1 = PlayerState(index=1, pos=Vec2(120.0, 100.0), fire_bullets_timer=1.0, hot_tempered_timer=1.95)
    player1.perk_counts[int(PerkId.HOT_TEMPERED)] = 1
    player_update(state=state, player=player1, input_state=PlayerInput(aim=Vec2(121.0, 100.0)), dt=0.1, players=[player0, player1])
    hot_types_owner = _active_type_ids(state)
    assert hot_types_owner
    assert set(hot_types_owner) == {int(ProjectileTemplateId.FIRE_BULLETS)}
