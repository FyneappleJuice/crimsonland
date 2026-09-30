from __future__ import annotations

"""Not native: a small golden spark burst plays wherever a crit lands on a
creature - rewrite-only, no native counterpart. Queued from the hit-
resolution sites that already know `did_crit` (projectiles/runtime/
projectile_pool.py, projectiles/runtime/secondary_pool.py), ticked once a
frame, and drawn as a plain forward frame lookup (see render/world/draw.py's
_draw_crit_sparks) - same "no runtime blending" lesson as Cinderburst's own
ground decal, and unnecessary here anyway since this is a one-shot burst,
never mid-transition with another instance of itself.
"""

from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

if TYPE_CHECKING:
    from ..gameplay import GameplayState

CRIT_SPARK_FRAME_COUNT = 8
# ~0.045s/frame - a quick flash, not a lingering effect, since this can fire
# many times a second in a dense fight.
CRIT_SPARK_DURATION_S = 0.36
# World px diameter - small next to a creature (~50-64px) but still a clearly
# readable golden flash at the hit point.
CRIT_SPARK_WORLD_SIZE = 26.0


class CritSparkEffect(msgspec.Struct):
    pos: Vec2
    elapsed: float = 0.0


def queue_crit_spark(state: GameplayState, pos: Vec2) -> None:
    pending = getattr(state, "pending_crit_sparks", None)
    if pending is None:
        return
    pending.append(CritSparkEffect(pos=Vec2(float(pos.x), float(pos.y))))


def tick_crit_spark_effects(state: GameplayState, dt: float) -> None:
    dt = float(dt)
    if dt <= 0.0:
        return
    pending = getattr(state, "pending_crit_sparks", None)
    if not pending:
        return
    remaining: list[CritSparkEffect] = []
    for effect in pending:
        effect.elapsed = float(effect.elapsed) + dt
        if effect.elapsed < CRIT_SPARK_DURATION_S:
            remaining.append(effect)
    state.pending_crit_sparks = remaining


__all__ = [
    "CRIT_SPARK_DURATION_S",
    "CRIT_SPARK_FRAME_COUNT",
    "CRIT_SPARK_WORLD_SIZE",
    "CritSparkEffect",
    "queue_crit_spark",
    "tick_crit_spark_effects",
]
