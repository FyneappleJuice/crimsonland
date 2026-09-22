from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from grim.geom import Vec2

from ...creatures.damage_runtime import CreatureDamageRuntime
from ...sim.state_types import GameplayState, PlayerState
from .manifest import PLAYER_PERK_TICK_STEPS
from .player_tick_context import (
    OwnerRefForPlayerFn,
    OwnerRefForPlayerProjectilesFn,
    PlayerPerkTickCtx,
    ProjectileSpawnFn,
)

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState

_PLAYER_PERK_TICK_STEPS = PLAYER_PERK_TICK_STEPS


def apply_player_perk_ticks(
    *,
    player: PlayerState,
    player_pos_before_move: Vec2,
    dt: float,
    state: GameplayState,
    players: list[PlayerState] | None,
    owner_ref_for_player: OwnerRefForPlayerFn,
    owner_ref_for_player_projectiles: OwnerRefForPlayerProjectilesFn,
    projectile_spawn: ProjectileSpawnFn,
    aim: Vec2 | None = None,
    creatures: Sequence[CreatureState] | None = None,
    creature_damage_runtime: CreatureDamageRuntime | None = None,
) -> None:
    ctx = PlayerPerkTickCtx(
        state=state,
        player=player,
        perk_player=player,
        player_pos_before_move=player_pos_before_move,
        players=players,
        dt=dt,
        owner_ref_for_player=owner_ref_for_player,
        owner_ref_for_player_projectiles=owner_ref_for_player_projectiles,
        projectile_spawn=projectile_spawn,
        aim=aim if aim is not None else player.aim,
        creatures=creatures,
        creature_damage_runtime=creature_damage_runtime,
    )
    for step in _PLAYER_PERK_TICK_STEPS:
        step(ctx)
