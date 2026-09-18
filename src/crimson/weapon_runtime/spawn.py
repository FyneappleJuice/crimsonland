from __future__ import annotations

import math

from grim.geom import Vec2

from ..math_parity import f32
from ..owner_ref import OwnerRef
from ..projectiles.types import ProjectileTemplateId
from ..sim.state_types import GameplayState, PlayerState
from ..weapons import WeaponId, weapon_entry_for_projectile_type_id
from .tenet_gun_spawn import tenet_reverse_spawn_params


def owner_ref_for_player(player_index: int) -> OwnerRef:
    return OwnerRef.from_player(int(player_index))


def owner_ref_for_player_projectiles(state: GameplayState, player_index: int) -> OwnerRef:
    if not state.friendly_fire_enabled:
        return OwnerRef.from_local_player(0)
    return owner_ref_for_player(player_index)


def travel_budget_for_type_id(type_id: ProjectileTemplateId) -> float:
    return float(weapon_entry_for_projectile_type_id(type_id).travel_budget)


def _uses_native_player_projectile_path(owner: OwnerRef) -> bool:
    legacy_owner = int(owner.to_legacy())
    return legacy_owner == -100 or -3 <= legacy_owner <= -1


def _resolve_player_slot(players: list[PlayerState], *, player_index: int) -> int | None:
    target_index = int(player_index)
    if 0 <= target_index < len(players):
        direct = players[target_index]
        if int(direct.index) == target_index:
            return int(target_index)
    for slot, player in enumerate(players):
        if int(player.index) == target_index:
            return int(slot)
    return None


def _resolve_owner_player(
    players: list[PlayerState] | None,
    *,
    owner: OwnerRef,
    owner_player_index: int | None,
) -> PlayerState | None:
    """Mirror `_shots_fired_player_index`'s owner precedence, but return the
    actual `PlayerState` instead of an index - used to check what weapon the
    player who triggered this spawn is holding (see the Tenet Gun check in
    `projectile_spawn` below)."""

    if not players:
        return None

    target_index: int | None = None
    if owner_player_index is not None:
        target_index = int(owner_player_index)
    elif owner.is_player() and not (owner.local_host and owner.index == 0):
        target_index = int(owner.index)
    elif owner.local_host and owner.index == 0 and len(players) == 1:
        target_index = int(players[0].index)

    if target_index is None:
        return None
    slot = _resolve_player_slot(players, player_index=target_index)
    if slot is None:
        return None
    return players[slot]


def _shots_fired_player_index(
    *,
    state: GameplayState,
    players: list[PlayerState] | None,
    owner: OwnerRef,
    owner_player_index: int | None,
) -> int | None:
    if owner_player_index is not None:
        player_index = int(owner_player_index)
        if 0 <= player_index < len(state.shots_fired):
            return int(player_index)

    if owner.is_player() and not (owner.local_host and owner.index == 0):
        player_index = int(owner.index)
        if 0 <= player_index < len(state.shots_fired):
            return int(player_index)

    if owner.local_host and owner.index == 0 and players and len(players) == 1:
        player_index = int(players[0].index)
        if 0 <= player_index < len(state.shots_fired):
            return int(player_index)

    return None


def _fire_bullets_active(
    players: list[PlayerState] | None,
    *,
    state: GameplayState,
    owner: OwnerRef,
    owner_player_index: int | None,
) -> bool:
    if not players:
        return False

    # Native `projectile_spawn` checks player-1/player-2 Fire Bullets timers
    # globally, regardless of projectile ownership.
    if bool(state.preserve_bugs):
        return any(float(player.fire_bullets_timer) > 0.0 for player in players[:2])

    resolved_owner_slot: int | None = None
    if owner_player_index is not None:
        resolved_owner_slot = _resolve_player_slot(players, player_index=int(owner_player_index))
    elif owner.is_player() and not (owner.local_host and owner.index == 0):
        resolved_owner_slot = _resolve_player_slot(players, player_index=int(owner.index))
    elif owner.local_host and owner.index == 0 and len(players) == 1:
        # Callers that only pass one player are explicitly indicating the owner
        # context (for example OwnerRef.from_local_player(0) with friendly fire disabled).
        resolved_owner_slot = 0

    if resolved_owner_slot is None:
        return False
    if not (0 <= resolved_owner_slot < len(players)):
        return False
    return float(players[resolved_owner_slot].fire_bullets_timer) > 0.0


def projectile_spawn(
    state: GameplayState,
    *,
    players: list[PlayerState] | None,
    pos: Vec2,
    angle: float,
    type_id: ProjectileTemplateId,
    owner: OwnerRef,
    owner_player_index: int | None = None,
    hits_players: bool = False,
) -> int:
    # Mirror `projectile_spawn` (0x00420440) Fire Bullets override.
    uses_player_projectile_path = owner.is_player() and (
        not bool(state.preserve_bugs) or _uses_native_player_projectile_path(owner)
    )
    if (not state.bonus_spawn_guard) and uses_player_projectile_path:
        while True:
            player_index = _shots_fired_player_index(
                state=state,
                players=players,
                owner=owner,
                owner_player_index=owner_player_index,
            )
            state.shots_fired_total += 1
            if player_index is not None:
                state.shots_fired[player_index] += 1
            if type_id == ProjectileTemplateId.FIRE_BULLETS:
                break
            if not _fire_bullets_active(
                players,
                state=state,
                owner=owner,
                owner_player_index=owner_player_index,
            ):
                break
            type_id = ProjectileTemplateId.FIRE_BULLETS

    # Tenet Gun (weapon_runtime/tenet_gun_spawn.py): every projectile that
    # originates from a Tenet-Gun-wielding player - not just their own direct
    # trigger-pull, but also Fireblast/Nuke/Shock Chain's opening bolt/Fire
    # Cough/Hot Tempered/Man Bomb/Angry Reloader, all of which route through
    # this one chokepoint - spawns at that player's aim point and flies back
    # instead of out. Derived/chained spawns (Shock Chain's own relay hits,
    # Fork Shot children, ...) re-own to a creature and go through
    # `pool.spawn`/`ctx.pool.spawn` directly, bypassing this function, so they
    # stay unaffected by design.
    spawn_pos, spawn_angle = pos, float(angle)
    tenet_reverse = False
    owner_player = _resolve_owner_player(players, owner=owner, owner_player_index=owner_player_index)
    if owner_player is not None and int(owner_player.weapon.weapon_id) == int(WeaponId.TENET_GUN):
        tenet_reverse = True
        spawn_pos, spawn_angle = tenet_reverse_spawn_params(
            origin=pos,
            muzzle=pos,
            aim=owner_player.aim,
            angle=float(angle),
        )

    meta = travel_budget_for_type_id(type_id)
    proj_id = state.projectiles.spawn(
        pos=spawn_pos,
        angle=spawn_angle,
        type_id=type_id,
        owner=owner,
        travel_budget=float(meta),
        hits_players=bool(hits_players),
    )
    if tenet_reverse:
        state.projectiles.entries[int(proj_id)].tenet_reverse = True
    return proj_id


def spawn_projectile_ring(
    state: GameplayState,
    origin_pos: Vec2,
    *,
    count: int,
    angle_offset: float,
    type_id: ProjectileTemplateId,
    owner: OwnerRef,
    owner_player_index: int | None = None,
    players: list[PlayerState] | None = None,
) -> None:
    if count <= 0:
        return
    # Native multiplies the loop index by an f32 step literal (e.g. 0.3926991f
    # for the 16-ring); keep the f32 rounding so the ring angles match.
    step = float(f32(math.tau / float(count)))
    for idx in range(count):
        projectile_spawn(
            state,
            players=players,
            pos=origin_pos,
            angle=float(f32(float(idx) * step)) + float(angle_offset),
            type_id=type_id,
            owner=owner,
            owner_player_index=owner_player_index,
        )
