from __future__ import annotations

from enum import IntEnum


class CreatureDamageType(IntEnum):
    SELF_TICK = 0
    BULLET = 1
    MELEE = 2
    EXPLOSION = 3
    FIRE = 4
    ION = 7
    # Rewrite-only: plasma / energy weapons. Native lumped these in with BULLET;
    # split out so plasma scales on its own perk line (crimson.progression) and
    # the clip-heat ramp, instead of riding the kinetic-bullet perks.
    ENERGY = 8
    # Rewrite-only: chain lightning (Arc Gun). Its own line, separate from ION.
    LIGHTNING = 9


__all__ = ["CreatureDamageType"]
