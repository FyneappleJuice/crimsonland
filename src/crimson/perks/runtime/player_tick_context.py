from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

from ...creatures.damage_runtime import CreatureDamageRuntime
from ...owner_ref import OwnerRef
from ...sim.state_types import GameplayState, PlayerState

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState

ProjectileSpawnFn = Callable[..., int]
OwnerRefForPlayerFn = Callable[[int], OwnerRef]
OwnerRefForPlayerProjectilesFn = Callable[[GameplayState, int], OwnerRef]


class PlayerPerkTickCtx(msgspec.Struct):
    state: GameplayState
    player: PlayerState
    perk_player: PlayerState
    player_pos_before_move: Vec2
    players: list[PlayerState] | None
    dt: float
    owner_ref_for_player: OwnerRefForPlayerFn
    owner_ref_for_player_projectiles: OwnerRefForPlayerProjectilesFn
    projectile_spawn: ProjectileSpawnFn
    # Not native: this frame's raw mouse/aim world position, ahead of
    # `player.aim`/`player.aim_heading` being refreshed from it later in
    # `player_update` - perks that spawn an aim-relative pattern here (Hot
    # Tempered) need the current frame's aim, not last frame's stale value.
    aim: Vec2 = Vec2()
    # Not native: lets a perk tick (Man Bomb's nuke) apply instant AoE damage
    # with proper death/corpse/XP follow-up, same runtime real gameplay wires
    # into creature/projectile collision - see world_state.py's step_runtime.
    creatures: Sequence[CreatureState] | None = None
    creature_damage_runtime: CreatureDamageRuntime | None = None
