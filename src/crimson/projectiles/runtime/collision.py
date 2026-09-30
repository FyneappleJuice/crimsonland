from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from grim.geom import Vec2

from ...collision_math import native_find_size_margin, within_native_find_radius
from ...creatures.damage_runtime import CreatureDamageRuntime
from ...creatures.lifecycle import creature_lifecycle_is_alive
from ...math_parity import f32, x87_pc24_hypot, x87_pc24_sub
from ...owner_ref import OwnerRef

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState

def _hit_radius_for(creature: CreatureState) -> float:
    """Return the native size term used by the radius predicates.

    The native code compares `distance - radius < creature.size * 0.14285715 + 3.0`.
    """

    return native_find_size_margin(float(creature.size))


def _within_native_find_radius(*, origin: Vec2, target: Vec2, radius: float, target_size: float) -> bool:
    """Mirror native `creature_find_in_radius` / `player_find_in_radius` predicate.

    Native uses:
      sqrt(dx*dx + dy*dy) - radius < size * 0.14285715 + 3.0
    """

    return within_native_find_radius(
        origin=origin,
        target=target,
        radius=radius,
        target_size=target_size,
    )


def creature_find_nearest_alive(
    *,
    creatures: Sequence[CreatureState],
    origin: Vec2,
) -> int:
    """Port of `creature_find_nearest(origin, -1, 0.0)`."""

    best_idx = -1
    best_distance = f32(1_000_000.0)
    # Not native: was capped at the original engine's fixed 384-slot array
    # (0x180) - now scans the real (possibly larger) pool. Owner-approved
    # parity break.
    max_index = len(creatures)
    for idx in range(max_index):
        creature = creatures[idx]
        if not creature.active:
            continue
        if not creature_lifecycle_is_alive(creature.lifecycle_stage):
            continue
        # Not native: Relic of the Turret - every caller of this function is
        # player-sourced targeting (homing rockets, chain lightning); a
        # turret should never be lockable as a target by the player's own
        # utility effects.
        if creature.is_turret:
            continue
        dx = x87_pc24_sub(f32(origin.x), f32(creature.pos.x))
        dy = x87_pc24_sub(f32(origin.y), f32(creature.pos.y))
        distance = x87_pc24_hypot(dx, dy)
        if distance < best_distance:
            best_distance = distance
            best_idx = idx
    return best_idx


def creature_find_nearest_active(
    *,
    creatures: Sequence[CreatureState],
    origin: Vec2,
    exclude_id: int,
    min_dist: float,
) -> int:
    """Port of ``creature_find_nearest(origin, exclude_id, min_dist)``.

    This native branch accepts every active creature, regardless of lifecycle,
    and compares the stored PC=24 square-root distance against both bounds.
    """

    best_idx = -1
    best_distance = f32(1_000_000.0)
    minimum_distance = f32(min_dist)
    # Not native: was capped at the original engine's fixed 384-slot array
    # (0x180) - now scans the real (possibly larger) pool. Owner-approved
    # parity break.
    max_index = len(creatures)
    for idx in range(max_index):
        creature = creatures[idx]
        if not creature.active or idx == int(exclude_id):
            continue
        # Not native: Relic of the Turret - this is the Ion Rifle shock-chain
        # target search, player-sourced; a turret should never be chainable.
        if creature.is_turret:
            continue
        dx = x87_pc24_sub(f32(origin.x), f32(creature.pos.x))
        dy = x87_pc24_sub(f32(origin.y), f32(creature.pos.y))
        distance = x87_pc24_hypot(dx, dy)
        if distance > minimum_distance and distance < best_distance:
            best_distance = distance
            best_idx = idx
    return best_idx


def _apply_damage_to_creature(
    creatures: Sequence[CreatureState],
    creature_index: int,
    damage: float,
    *,
    damage_type: int,
    impulse: Vec2,
    owner: OwnerRef,
    creature_damage_runtime: CreatureDamageRuntime,
    is_projectile_hit: bool = False,
) -> None:
    if damage <= 0.0:
        return
    idx = int(creature_index)
    if not (0 <= idx < len(creatures)):
        return
    creature_damage_runtime.apply_creature_damage(
        idx,
        float(damage),
        int(damage_type),
        impulse,
        owner,
        is_projectile_hit=is_projectile_hit,
    )


__all__ = [
    "_apply_damage_to_creature",
    "_hit_radius_for",
    "_within_native_find_radius",
    "creature_find_nearest_active",
    "creature_find_nearest_alive",
    "native_find_size_margin",
]
