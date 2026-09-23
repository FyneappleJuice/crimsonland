from __future__ import annotations

from enum import IntEnum

import msgspec

from grim.geom import Vec2

from ..creatures.damage_types import CreatureDamageType
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


def damage_type_for_projectile_type_id(type_id: int) -> int:
    """The creature-damage type a primary-pool bullet of this type deals.

    Extracted from projectile_pool.py's own per-tick `_damage_type_for` so
    other callers can reuse the exact same mapping without duplicating it."""

    tid = ProjectileTemplateId(type_id)
    if tid in ION_PROJECTILE_TEMPLATE_IDS:
        return int(CreatureDamageType.ION)
    if tid == ProjectileTemplateId.FIRE_BULLETS:
        return int(CreatureDamageType.FIRE)
    if tid in PLASMA_PROJECTILE_TEMPLATE_IDS:
        return int(CreatureDamageType.PLASMA)
    if tid in ENERGY_PROJECTILE_TEMPLATE_IDS:
        return int(CreatureDamageType.ENERGY)
    return int(CreatureDamageType.BULLET)


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
    # weapon's archetype crit chance (weapon_runtime/crit.py) - 1.0 on a miss,
    # CRIT_MULTIPLIER (plus any perk bonus) on a crit. DPS neutrality is baked
    # into the weapon's own damage_scale (weapons.py) instead of into this
    # multiplier, so a plain miss is exactly 1.0 here.
    crit_mult: float = 1.0
    # Rewrite-only: outgoing Perk Efficacy multiplier stamped at spawn for a
    # canned perk-proc burst (Man Bomb/Hot Tempered/Fire Cough/Angry Reloader)
    # - these spawn a fixed-damage-type projectile independent of the player's
    # actual weapon, so their own damage number needs its own per-instance
    # multiplier rather than reading a shared damage_mult_* bucket. 1.0 = not
    # a perk-proc bolt / no Perk Efficacy stacks.
    perk_damage_mult: float = 1.0
    # Rewrite-only: whether this specific pellet actually rolled a crit (not
    # just "crit_mult != 1.0" - a non-crit shot can still carry a nonzero
    # multiplier here from a perk like Pendulum's damage-phase bonus). Only
    # stamped true for the player's own direct trigger-pull
    # (weapon_runtime/fire.py's primary pellet loop); everything else defaults
    # false. Consumed by Cold Snap's on-crit freeze.
    did_crit: bool = False
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
    # Rewrite-only: a Tenet Gun shot (weapon_runtime/tenet_gun_spawn.py) -
    # spawned at the far end of the shot and aimed back at the muzzle instead
    # of the usual pos/angle, so it flies into the player instead of away
    # from them. Everything else about it (damage, collision, pierce, Fork
    # Shot, ...) is the same unmodified code every other bullet uses; this
    # flag only marks it so the pool's step() stops it once it arrives back
    # at its owner, instead of flying on through them.
    tenet_reverse: bool = False
    # Rewrite-only: the firing player's PlayerState.shot_seq at the moment of
    # this trigger-pull, stamped only by the primary pellet loop (weapon_runtime/
    # fire.py's PrimaryPelletsMode - same scoping as did_crit above). Every
    # pellet from one shotgun-style blast shares the same value, and a single
    # piercing bolt keeps it across every creature it goes on to hit, so
    # Seeker Rounds can dedupe "one hit confirmed" down to "one shot fired"
    # regardless of pellet count or pierce count. -1 = not a primary-fire
    # bolt (perk-proc bursts, secondary weapons, ...) - never counted.
    shot_seq: int = -1


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
    # Rewrite-only: whether this rocket actually rolled a crit - Projectile.
    # did_crit's counterpart. Stamped only by the player's own trigger-pull
    # (weapon_runtime/fire.py); consumed on the direct hit by Cold Snap's
    # freeze, Harvester's Scythe and Overdue's streak.
    did_crit: bool = False
    # Rewrite-only: Fork Shot bonus - True once this rocket has forked on hit
    # (as a parent) or is itself a fork child; either way it must not fork
    # again on its own hit. Mirrors Projectile.reserved's gating role for
    # bullets, but doesn't need to also encode a damage multiplier the way
    # that field does - a fork child's damage penalty is folded straight into
    # its own crit_mult at spawn instead (see secondary_pool.py).
    fork_reserved: bool = False
    # Rewrite-only: Explosive Payload eligibility - stamped at spawn from
    # whether the bonus was active *then* (weapon_runtime/fire.py), not
    # re-read from the player at hit time. That distinction matters for a
    # snapshotted "freebie" shot (Domino Effect/Momentum's bonus shot, fired
    # from a clone with every powerup timer deliberately zeroed) - checking
    # the real player's live timer at hit time would let it inherit whatever
    # Explosive Payload the real player happens to have running, defeating
    # the whole point of the snapshot. Mini-Rocket Swarmers is treated as a
    # shotgun-style weapon for this bonus (SwarmerDumpMode): only one
    # randomly chosen rocket per volley is flagged True, the rest False, so a
    # 5-rocket dump doesn't proc 5 bonus explosions. Defaults False so any
    # spawn path that doesn't explicitly set it (Fork Shot's own children,
    # Seeker Rounds' bonus rocket, ...) doesn't chain into another bonus.
    explosive_payload_eligible: bool = False
    # Rewrite-only: Fork Shot eligibility - same spawn-time-snapshot reasoning
    # as explosive_payload_eligible above, and the same reason it defaults
    # False.
    fork_shot_eligible: bool = False
    # Rewrite-only: the firing player's PlayerState.shot_seq at the moment of
    # this trigger-pull, mirroring Projectile.shot_seq's same role for bullets -
    # every rocket from one trigger pull (Mini-Rocket Swarmers' whole volley)
    # shares the same value, so Seeker Rounds/Fire and Forget (PerkId.
    # SEEKER_ROUNDS) can dedupe "one hit confirmed" down to "one shot fired"
    # regardless of how many rockets that shot spawned. -1 = not tracked
    # (never counted).
    shot_seq: int = -1


__all__ = [
    "ENERGY_PROJECTILE_TEMPLATE_IDS",
    "ION_PROJECTILE_TEMPLATE_IDS",
    "PLASMA_PROJECTILE_TEMPLATE_IDS",
    "MAIN_PROJECTILE_POOL_SIZE",
    "SECONDARY_PROJECTILE_POOL_SIZE",
    "OwnerRef",
    "damage_type_for_projectile_type_id",
    "Projectile",
    "ProjectileCollisionProfile",
    "ProjectileHit",
    "ProjectileTemplateId",
    "SecondaryProjectile",
    "SecondaryProjectileTypeId",
]
