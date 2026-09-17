from __future__ import annotations

from enum import IntEnum

import msgspec

from grim.geom import Vec2

from ..owner_ref import OwnerRef

MAIN_PROJECTILE_POOL_SIZE = 0x60
SECONDARY_PROJECTILE_POOL_SIZE = 0x40


class ProjectileTemplateId(IntEnum):
    # Values are projectile type ids (not weapon ids). Based on the decompile
    # for `player_fire_weapon` and `projectile_update`.
    PISTOL = 0x01
    ASSAULT_RIFLE = 0x02
    SHOTGUN = 0x03
    SUBMACHINE_GUN = 0x05
    GAUSS_GUN = 0x06
    PLASMA_RIFLE = 0x09
    PLASMA_MINIGUN = 0x0B
    PULSE_GUN = 0x13
    ION_RIFLE = 0x15
    ION_MINIGUN = 0x16
    ION_CANNON = 0x17
    SHRINKIFIER = 0x18
    BLADE_GUN = 0x19
    SPIDER_PLASMA = 0x1A
    PLASMA_CANNON = 0x1C
    SPLITTER_GUN = 0x1D
    PLAGUE_SPREADER = 0x29
    RAINBOW_GUN = 0x2B
    FIRE_BULLETS = 0x2D


# Rewrite-only: templates that deal CreatureDamageType.PLASMA instead of BULLET.
# Covers every plasma weapon (Multi-Plasma / Plasma Shotgun spawn these types).
PLASMA_PROJECTILE_TEMPLATE_IDS: frozenset[ProjectileTemplateId] = frozenset(
    {
        ProjectileTemplateId.PLASMA_RIFLE,
        ProjectileTemplateId.PLASMA_MINIGUN,
        ProjectileTemplateId.PLASMA_CANNON,
        ProjectileTemplateId.SPIDER_PLASMA,
    }
)

# Rewrite-only: templates that deal CreatureDamageType.ENERGY instead of
# BULLET - Gauss Gun / Gauss Shotgun's own bucket, separate from plasma
# (Gauss Shotgun fires GAUSS_GUN pellets, already covered).
ENERGY_PROJECTILE_TEMPLATE_IDS: frozenset[ProjectileTemplateId] = frozenset(
    {
        ProjectileTemplateId.GAUSS_GUN,
    }
)

# Rewrite-only: templates that deal CreatureDamageType.ION on direct hit (not
# just their lingering AoE tick) - Ion Rifle/Minigun/Cannon (Ion Shotgun fires
# ION_MINIGUN pellets, already covered).
ION_PROJECTILE_TEMPLATE_IDS: frozenset[ProjectileTemplateId] = frozenset(
    {
        ProjectileTemplateId.ION_RIFLE,
        ProjectileTemplateId.ION_MINIGUN,
        ProjectileTemplateId.ION_CANNON,
    }
)


class SecondaryProjectileTypeId(IntEnum):
    NONE = 0
    ROCKET = 1
    HOMING_ROCKET = 2
    DETONATION = 3
    ROCKET_MINIGUN = 4


class ProjectileCollisionProfile(msgspec.Struct, frozen=True):
    hit_radius: float
    initial_damage_pool: float


class ProjectileHit(msgspec.Struct, frozen=True):
    type_id: ProjectileTemplateId
    origin: Vec2
    hit: Vec2
    target: Vec2


class Projectile(msgspec.Struct):
    active: bool = False
    angle: float = 0.0
    pos: Vec2 = Vec2()
    origin: Vec2 = Vec2()
    vel: Vec2 = Vec2()
    type_id: ProjectileTemplateId = ProjectileTemplateId.PISTOL
    life_timer: float = 0.0
    reserved: float = 0.0
    # Rewrite-only: outgoing energy-damage multiplier stamped at spawn from the
    # firing weapon's clip-heat (see weapon_runtime/plasma_heat.py). 1.0 = no
    # ramp / not a plasma bolt.
    energy_heat_mult: float = 1.0
    # Rewrite-only: outgoing crit multiplier stamped at spawn from the firing
    # weapon's archetype crit chance (weapon_runtime/crit.py). Always applied
    # at hit time (compensation factor on a miss, compensation*2 on a crit) so
    # DPS averages stay anchored to the pre-crit baseline.
    crit_mult: float = 1.0
    # Rewrite-only: extra full-damage targets this bolt punches through before it
    # stops (Weapon Power Up for kinetic lead). 0 = native stop-on-first-hit.
    pierce_left: float = 0.0
    # Rewrite-only: this pellet is flagged to detonate on impact (the
    # "Explosive Payload" bonus - bonuses/explosive_payload.py). Consumed
    # (cleared) on its first hit so a piercing round only explodes once.
    is_rocket: bool = False
    # Rewrite-only: this bolt carries an Ion Overload payload (bonuses/
    # ion_overload.py) - the total charge time (seconds) that led to it.
    # 0.0 = not an Overload bolt. Consumed (cleared) on its first hit, which
    # blooms the scaled nova at the hit position instead of the real Ion
    # Cannon's own fixed-size linger.
    ion_overload_charge: float = 0.0
    speed_scale: float = 1.0
    damage_pool: float = 1.0
    hit_radius: float = 1.0
    travel_budget: float = 0.0
    owner: OwnerRef = msgspec.field(default_factory=OwnerRef.none)
    hits_players: bool = False


class SecondaryProjectile(msgspec.Struct):
    active: bool = False
    angle: float = 0.0
    speed: float = 0.0
    pos: Vec2 = Vec2()
    vel: Vec2 = Vec2()
    detonation_t: float = 0.0
    detonation_scale: float = 1.0
    type_id: SecondaryProjectileTypeId = SecondaryProjectileTypeId.NONE
    owner: OwnerRef = msgspec.field(default_factory=lambda: OwnerRef.from_local_player(0))
    trail_timer: float = 0.0
    target_id: int = -1
    # Rewrite-only: outgoing crit multiplier stamped at spawn (weapon_runtime/
    # crit.py) - carries through from the direct-hit burst into the
    # detonation AoE tick, since both phases come from the same rocket.
    crit_mult: float = 1.0


__all__ = [
    "ENERGY_PROJECTILE_TEMPLATE_IDS",
    "ION_PROJECTILE_TEMPLATE_IDS",
    "PLASMA_PROJECTILE_TEMPLATE_IDS",
    "MAIN_PROJECTILE_POOL_SIZE",
    "SECONDARY_PROJECTILE_POOL_SIZE",
    "OwnerRef",
    "Projectile",
    "ProjectileCollisionProfile",
    "ProjectileHit",
    "ProjectileTemplateId",
    "SecondaryProjectile",
    "SecondaryProjectileTypeId",
]
