from __future__ import annotations

from enum import IntEnum


class CreatureDamageType(IntEnum):
    SELF_TICK = 0
    BULLET = 1
    MELEE = 2
    EXPLOSION = 3
    FIRE = 4
    ION = 7
    # Rewrite-only: plasma weapons (Plasma Rifle/Minigun/Cannon, Multi-Plasma).
    # Native lumped these in with BULLET; split out so plasma scales on its own
    # perk line (crimson.progression) and the clip-heat ramp, instead of
    # riding the kinetic-bullet perks.
    PLASMA = 8
    # Rewrite-only: chain lightning (Arc Gun). Its own line, separate from ION.
    LIGHTNING = 9
    # Rewrite-only: Gauss Gun / Gauss Shotgun. Its own line, separate from
    # PLASMA - a railgun slug, not a plasma bolt or a lead round.
    ENERGY = 10


__all__ = ["CreatureDamageType"]
