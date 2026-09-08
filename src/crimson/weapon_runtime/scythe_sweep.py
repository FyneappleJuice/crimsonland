from __future__ import annotations

"""Evil Scythe melee sweep (rewrite-only).

Firing the Evil Scythe does not spawn a projectile. It starts a *swing* on the
player: a scythe blade sweeps a wide cone in front of the aim over
``SCYTHE_SWING_DURATION_S`` seconds, dealing melee damage to each creature the
edge passes over (once per swing). The clip holds two swings and they alternate
direction - swing 0 goes left->right, swing 1 right->left - so the rhythm is
sweep, back-sweep, short reload.

Weapon Power Up widens the cone, extends the reach and hardens the hit
(``SCYTHE_WPU_*``); it does **not** speed up the swing or reload (see
``weapon_runtime.power_up.WPU_NO_RATE_WEAPON_IDS``). The effective arc / reach /
damage are frozen onto the ``ScytheSwingState`` when the swing starts.

Geometry is world-space ``atan2``: ``base_angle`` is the aim bearing captured at
swing start, the blade bearing runs from ``base - dir*arc/2`` to
``base + dir*arc/2`` as ``progress`` goes 0 -> 1.
"""

import math

from grim.geom import Vec2

from ..creatures.damage_types import CreatureDamageType
from ..owner_ref import OwnerRef
from ..sim.state_types import PlayerState, ScytheSwingState

# Total cone the blade sweeps (radians). ~162 degrees.
SCYTHE_ARC = math.radians(162.0)
# Seconds for one full sweep.
SCYTHE_SWING_DURATION_S = 0.28
# Blade reach from the player centre, plus a small slice of the target's own
# size so big aliens connect from a touch further out. Kept tight so the hit
# window matches the drawn blade rather than reaching past it.
SCYTHE_REACH = 104.0
SCYTHE_CREATURE_REACH_FACTOR = 0.3
# Angular slack on the leading/trailing edge of the swept slice each tick - just
# enough that a fast sweep never skips a creature between ticks.
SCYTHE_EDGE_PAD = math.radians(5.0)
SCYTHE_DAMAGE = 45.6
SCYTHE_KNOCKBACK = 2.6

# Weapon Power Up: ~+30% DPS, delivered as swing damage (no cadence change - the
# scythe is in power_up.WPU_NO_RATE_WEAPON_IDS). A hair of extra reach for feel.
SCYTHE_WPU_ARC_MULT = 1.0
SCYTHE_WPU_REACH_MULT = 1.12
SCYTHE_WPU_DAMAGE_MULT = 1.3


def _swing_arc(swing: ScytheSwingState) -> float:
    return float(swing.arc) if float(swing.arc) > 0.0 else SCYTHE_ARC


def _swing_reach(swing: ScytheSwingState) -> float:
    return float(swing.reach) if float(swing.reach) > 0.0 else SCYTHE_REACH


def _swing_damage(swing: ScytheSwingState) -> float:
    return float(swing.damage) if float(swing.damage) > 0.0 else SCYTHE_DAMAGE


# Public accessors for the renderer.
scythe_swing_arc = _swing_arc
scythe_swing_reach = _swing_reach


def _norm_angle(x: float) -> float:
    return math.atan2(math.sin(x), math.cos(x))


def _blade_angle_at(base_angle: float, direction: float, progress: float, arc: float) -> float:
    """World bearing of the blade at 0<=progress<=1 (relative to swing start)."""

    edge0 = base_angle - direction * arc * 0.5
    return edge0 + direction * arc * progress


def scythe_progress(swing: ScytheSwingState) -> float:
    if not swing.active:
        return 1.0
    return min(1.0, float(swing.elapsed) / SCYTHE_SWING_DURATION_S)


def scythe_arc_angle_for(swing: ScytheSwingState, progress: float) -> float:
    """Blade bearing at an arbitrary progress on this swing - for the trail render."""

    return _blade_angle_at(float(swing.base_angle), float(swing.direction), float(progress), _swing_arc(swing))


def scythe_blade_angle(swing: ScytheSwingState) -> float:
    """Current world bearing of the blade - used by the renderer."""

    return scythe_arc_angle_for(swing, scythe_progress(swing))


def start_scythe_swing(
    player: PlayerState,
    aim_world: Vec2,
    *,
    shots_fired_this_clip: int,
    weapon_power_up: bool = False,
) -> None:
    """Begin a swing. Even shots sweep left->right (+1), odd shots right->left."""

    swing = player.scythe_swing
    dx = float(aim_world.x) - float(player.pos.x)
    dy = float(aim_world.y) - float(player.pos.y)
    base_angle = math.atan2(dy, dx) if (dx or dy) else float(player.aim_heading)
    direction = 1.0 if (int(shots_fired_this_clip) % 2 == 0) else -1.0

    arc = SCYTHE_ARC * (SCYTHE_WPU_ARC_MULT if weapon_power_up else 1.0)
    swing.active = True
    swing.elapsed = 0.0
    swing.base_angle = float(base_angle)
    swing.direction = float(direction)
    swing.arc = float(arc)
    swing.reach = float(SCYTHE_REACH * (SCYTHE_WPU_REACH_MULT if weapon_power_up else 1.0))
    swing.damage = float(SCYTHE_DAMAGE * (SCYTHE_WPU_DAMAGE_MULT if weapon_power_up else 1.0))
    swing.prev_angle = _blade_angle_at(base_angle, direction, 0.0, arc)
    swing.hit = []


def update_scythe_swings(
    players: list[PlayerState],
    creatures,
    dt: float,
    *,
    creature_damage_runtime,
) -> None:
    """Advance every active scythe swing and apply the edge's melee hits."""

    dt = float(dt)
    if dt <= 0.0:
        return

    for player in players:
        swing = player.scythe_swing
        if not swing.active:
            continue

        swing.elapsed = float(swing.elapsed) + dt
        progress = min(1.0, float(swing.elapsed) / SCYTHE_SWING_DURATION_S)

        base = float(swing.base_angle)
        direction = float(swing.direction)
        arc = _swing_arc(swing)
        reach_base = _swing_reach(swing)
        damage = _swing_damage(swing)
        curr_angle = _blade_angle_at(base, direction, progress, arc)

        if creature_damage_runtime is not None and creatures:
            prev_rel = _norm_angle(float(swing.prev_angle) - base)
            curr_rel = _norm_angle(curr_angle - base)
            lo = min(prev_rel, curr_rel) - SCYTHE_EDGE_PAD
            hi = max(prev_rel, curr_rel) + SCYTHE_EDGE_PAD
            px = float(player.pos.x)
            py = float(player.pos.y)
            owner = OwnerRef.from_local_player(0)

            for idx, creature in enumerate(creatures):
                if not creature.active or float(creature.hp) <= 0.0:
                    continue
                if idx in swing.hit:
                    continue
                cdx = float(creature.pos.x) - px
                cdy = float(creature.pos.y) - py
                dist = math.hypot(cdx, cdy)
                reach = reach_base + float(creature.size) * SCYTHE_CREATURE_REACH_FACTOR
                if dist > reach:
                    continue
                bearing_rel = _norm_angle(math.atan2(cdy, cdx) - base)
                if not (lo <= bearing_rel <= hi):
                    continue

                swing.hit.append(idx)
                inv = (1.0 / dist) if dist > 1e-6 else 0.0
                impulse = Vec2(cdx * inv * SCYTHE_KNOCKBACK, cdy * inv * SCYTHE_KNOCKBACK)
                creature_damage_runtime.apply_creature_damage(
                    idx,
                    damage,
                    int(CreatureDamageType.MELEE),
                    impulse,
                    owner,
                )

        swing.prev_angle = curr_angle
        if progress >= 1.0:
            swing.active = False
            swing.hit = []
