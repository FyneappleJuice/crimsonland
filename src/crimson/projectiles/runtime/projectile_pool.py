from __future__ import annotations

import math
from collections.abc import MutableSequence, Sequence
from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2
from grim.rand import CrandLike
from grim.sfx_map import SfxId

from ...creatures.damage_runtime import CreatureDamageRuntime, DirectCreatureDamageRuntime
from ...creatures.damage_types import CreatureDamageType
from ...creatures.lifecycle import creature_lifecycle_is_alive, creature_lifecycle_is_collidable
from ...effects import EffectPool
from ...meta.relics_impl import deadeye_pact as relic_deadeye_pact
from ...meta.relics_impl import gathering_winds as relic_gathering_winds
from ...meta.relics_impl import ricochet as relic_ricochet
from ...math_parity import (
    NATIVE_HALF_PI,
    f32,
    x87_pc24_add,
    x87_pc24_cos_mul,
    x87_pc24_mul,
    x87_pc24_sin_mul,
    x87_pc24_sub,
)
from ...owner_ref import OwnerRef
from ...perks import PerkId
from ...perks.helpers import perk_active
from ...perks.impl.harvester_scythe import harvester_scythe_on_crit
from ...progression import resolve_team_stats
from ...rng_caller_static import RngCallerStatic
from ...weapons import WeaponId, weapon_entry_for_projectile_type_id
from ..types import (
    ENERGY_PROJECTILE_TEMPLATE_IDS,
    ION_PROJECTILE_TEMPLATE_IDS,
    MAIN_PROJECTILE_POOL_SIZE,
    PLASMA_PROJECTILE_TEMPLATE_IDS,
    Projectile,
    ProjectileCollisionProfile,
    ProjectileHit,
    ProjectileTemplateId,
    damage_type_for_projectile_type_id,
)
from .behaviors import (
    _PROJECTILE_HIT_PERK_HOOKS,
    _ProjectileHitInfo,
    _ProjectileHitPerkCtx,
    _ProjectileUpdateCtx,
)
from .collision import _apply_damage_to_creature, _hit_radius_for, _within_native_find_radius
from .primary_rules import primary_rule_for_type_id
from .spatial_hash import CreatureSpatialHash

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...gameplay import GameplayState
    from ...sim.state_types import PlayerState

type ProjectileHitPresentation = object


class ProjectileHitRuntime(msgspec.Struct):
    def apply_player_damage(self, player_index: int, damage: float) -> None:
        _ = player_index, damage

    def begin_hit_presentation(self, hit: ProjectileHit) -> ProjectileHitPresentation | None:
        _ = hit
        return None

    def finish_hit_presentation(self, hit: ProjectileHit, presentation: ProjectileHitPresentation) -> None:
        _ = hit, presentation


class ProjectileUpdateOptions(msgspec.Struct, frozen=True):
    world_size: float
    damage_scale_by_type: dict[int, float]
    rng: CrandLike
    runtime_state: GameplayState
    players: Sequence[PlayerState]
    hit_runtime: ProjectileHitRuntime
    creature_damage_runtime: CreatureDamageRuntime | None = None
    ion_aoe_scale: float = 1.0
    detail_preset: int = 5


class PrimaryStepCtx(msgspec.Struct, frozen=True):
    dt: float
    creatures: Sequence[CreatureState]
    options: ProjectileUpdateOptions


_DEFAULT_PROJECTILE_COLLISION_PROFILE = ProjectileCollisionProfile(
    hit_radius=1.0,
    initial_damage_pool=1.0,
)

# Fork Shot bonus (not native): same +-60 degree split Splitter Gun uses on
# its own projectile type (see behaviors.py::_pre_hit_splitter), generalized
# to any non-piercing projectile while the bonus timer is active.
_FORK_SHOT_ANGLE_RAD = 1.0471976
# Fork children fired off a shotgun deal half damage - shotguns already put a
# lot of pellets on target, so a full-power fork off each one is too much.
_FORK_SHOT_SHOTGUN_DAMAGE_MULT = 0.5

# Rewrite-only: Cold Snap - how long a crit freezes its target (seconds).
COLD_SNAP_FREEZE_DURATION = 1.5
# Rewrite-only: Overdue's non-crit streak can advance at most once per this
# many seconds (see the on-hit resolution below), independent of how many
# rolls/sec the weapon fires - without it, a high-roll-rate weapon (Minigun,
# a 12-pellet Shotgun blast) completes a 10-hit streak in under a second
# regardless of OVERDUE_STREAK_THRESHOLD, while a slow weapon (Cannon) is
# still stuck waiting tens of seconds. This puts a shared ceiling on how fast
# ANY weapon can build the streak; weapons already slower than the ceiling
# (Cannon) are unaffected.
OVERDUE_TICK_COOLDOWN = 0.5
# Rewrite-only: Seeker Rounds - fires a free homing rocket every this many
# confirmed hits (not shots fired - a piercing shot connecting with 3
# creatures counts as 3 toward this, same as 3 separate shots would).
SEEKER_ROUNDS_HIT_THRESHOLD = 3
# `Projectile.reserved` (native "unused" field, offset 0x28) doubles as fork
# state: 0 = normal, 1 = has forked / is a plain fork child, 2 = fork child
# that carries the shotgun damage penalty.
_FORK_RESERVED_NONE = 0.0
_FORK_RESERVED_FORKED = 1.0
_FORK_RESERVED_SHOTGUN_CHILD = 2.0
_SHOTGUN_WEAPON_IDS = frozenset({WeaponId.SHOTGUN})

# Tenet Gun (not native): how close a reversed bolt (Projectile.tenet_reverse)
# has to get to its owner before it's considered "arrived" and stops instead
# of flying on through them.
_TENET_REVERSE_STOP_RADIUS = 40.0

# Explosive Payload bonus (not native): "scale" fed into the shared
# secondary-projectile DETONATION state (secondary_pool.py) that a flagged
# pellet spawns on impact - radius grows to `scale * 80` px over ~1/3s,
# dealing `dt * scale * 700` damage per tick to everything caught inside, on
# top of the pellet's own regular hit damage. For reference the Rocket
# Launcher's own on-hit scale is 1.0 (80px / ~233 total damage).
#
# The blast scales with the firing weapon's own `damage_scale`, anchored so
# the Pistol (damage_scale 4.1) gets exactly the reference scale below. The
# raw curve is damped by a square root so the ~112x spread in weapon
# damage_scale (0.25 Fire Bullets .. 28.0 Plasma Cannon) only becomes a ~10x
# spread in blast size/damage - then that result is blended only halfway back
# toward the flat reference (_SCALE_STRENGTH) so the many weapons sitting at
# the common damage_scale of 1.0 (Assault Rifle, SMG, Gauss Gun, Mean
# Minigun, ...) aren't docked much of their blast just for not being the
# Pistol - a big gun's bullets should explode harder, a small one only a
# little softer, never punished hard for being "merely" 1.0x.
_EXPLOSIVE_PAYLOAD_PISTOL_DAMAGE_SCALE = 4.1
_EXPLOSIVE_PAYLOAD_DETONATION_SCALE = 0.3  # what the Pistol's blast should be
_EXPLOSIVE_PAYLOAD_SCALE_EXPONENT = 0.5  # sqrt - "scales, but not as much"
_EXPLOSIVE_PAYLOAD_SCALE_STRENGTH = 0.5  # 0 = flat for every weapon, 1 = full damped curve
# Weapons with damage_scale <= 0 (Shrinkifier 5k, Plague Spreader Gun - pure
# utility, no direct damage) don't get an explosion at all.

# Rewrite-only: weapons.py's WEAPON_TABLE now bakes crit-DPS-neutrality
# straight into damage_scale (see the comment above WEAPON_TABLE there), which
# would otherwise quietly shift every one of these ratios and the "Pistol is
# exactly the reference scale" invariant above. This snapshot holds each
# affected weapon's *original*, pre-compensation damage_scale so Explosive
# Payload's blast calibration stays exactly as tuned, independent of that
# rebalance. Weapons not listed here were never adjusted (damage_scale <= 0
# or 0% crit chance), so their live table value is already the native one.
_EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE: dict[WeaponId, float] = {
    WeaponId.PISTOL: 4.1,
    WeaponId.ASSAULT_RIFLE: 1.0,
    WeaponId.SHOTGUN: 1.2,
    WeaponId.SAWED_OFF_SHOTGUN: 1.0,
    WeaponId.SUBMACHINE_GUN: 1.0,
    WeaponId.GAUSS_GUN: 1.0,
    WeaponId.MEAN_MINIGUN: 1.0,
    WeaponId.PLASMA_RIFLE: 5.0,
    WeaponId.MULTI_PLASMA: 1.0,
    WeaponId.PLASMA_MINIGUN: 2.1,
    WeaponId.ROCKET_LAUNCHER: 1.0,
    WeaponId.SEEKER_ROCKETS: 1.0,
    WeaponId.PLASMA_SHOTGUN: 1.0,
    WeaponId.MINI_ROCKET_SWARMERS: 1.0,
    WeaponId.ROCKET_MINIGUN: 1.0,
    WeaponId.PULSE_GUN: 1.0,
    WeaponId.JACKHAMMER: 1.0,
    WeaponId.ION_RIFLE: 3.0,
    WeaponId.ION_MINIGUN: 1.4,
    WeaponId.ION_CANNON: 16.7,
    WeaponId.BLADE_GUN: 11.0,
    WeaponId.SPIDER_PLASMA: 0.5,
    WeaponId.EVIL_SCYTHE: 1.0,
    WeaponId.PLASMA_CANNON: 28.0,
    WeaponId.SPLITTER_GUN: 6.0,
    WeaponId.GAUSS_SHOTGUN: 1.0,
    WeaponId.ION_SHOTGUN: 1.0,
    WeaponId.TENET_GUN: 4.1,
    WeaponId.RAINBOW_GUN: 1.0,
    WeaponId.FIRE_BULLETS: 0.25,
}


def _native_damage_scale_for_type_id(type_id: int) -> float:
    entry = weapon_entry_for_projectile_type_id(ProjectileTemplateId(type_id))
    override = _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE.get(entry.weapon_id)
    return float(override) if override is not None else float(entry.damage_scale)


def _explosive_payload_blast_scale(weapon_damage_scale: float) -> float:
    weapon_damage_scale = float(weapon_damage_scale)
    if weapon_damage_scale <= 0.0:
        return 0.0
    ratio = weapon_damage_scale / _EXPLOSIVE_PAYLOAD_PISTOL_DAMAGE_SCALE
    full_scale = _EXPLOSIVE_PAYLOAD_DETONATION_SCALE * (ratio**_EXPLOSIVE_PAYLOAD_SCALE_EXPONENT)
    return _EXPLOSIVE_PAYLOAD_DETONATION_SCALE + _EXPLOSIVE_PAYLOAD_SCALE_STRENGTH * (
        full_scale - _EXPLOSIVE_PAYLOAD_DETONATION_SCALE
    )

_PROJECTILE_COLLISION_PROFILE_BY_TYPE_ID: dict[ProjectileTemplateId, ProjectileCollisionProfile] = {
    ProjectileTemplateId.ION_MINIGUN: ProjectileCollisionProfile(hit_radius=3.0, initial_damage_pool=1.0),
    ProjectileTemplateId.ION_RIFLE: ProjectileCollisionProfile(hit_radius=5.0, initial_damage_pool=1.0),
    ProjectileTemplateId.ION_CANNON: ProjectileCollisionProfile(hit_radius=10.0, initial_damage_pool=1.0),
    ProjectileTemplateId.PLASMA_CANNON: ProjectileCollisionProfile(hit_radius=10.0, initial_damage_pool=1.0),
    ProjectileTemplateId.GAUSS_GUN: ProjectileCollisionProfile(hit_radius=1.0, initial_damage_pool=300.0),
    ProjectileTemplateId.FIRE_BULLETS: ProjectileCollisionProfile(hit_radius=1.0, initial_damage_pool=240.0),
    ProjectileTemplateId.BLADE_GUN: ProjectileCollisionProfile(hit_radius=1.0, initial_damage_pool=50.0),
}


def _projectile_damage_amount_f32(dist: float, damage_scale: float) -> float:
    """Mirror native PC_24 arithmetic stores in the projectile damage formula."""

    distance = f32(float(dist))
    if distance < 50.0:
        distance = 50.0
    damage = f32(100.0 / float(distance))
    damage = f32(float(damage) * float(f32(float(damage_scale))))
    damage = f32(float(damage) * 30.0)
    damage = f32(float(damage) + 10.0)
    return f32(float(damage) * float(f32(0.95)))


def _stop_on_hit_jitter_axis_f32(direction: float, jitter: int, pos: float) -> float:
    offset = x87_pc24_mul(direction, float(jitter))
    return x87_pc24_add(offset, pos)


def projectile_collision_profile(type_id: ProjectileTemplateId) -> ProjectileCollisionProfile:
    return _PROJECTILE_COLLISION_PROFILE_BY_TYPE_ID.get(
        type_id,
        _DEFAULT_PROJECTILE_COLLISION_PROFILE,
    )


class ProjectilePool:
    def __init__(self, *, size: int = MAIN_PROJECTILE_POOL_SIZE) -> None:
        self._entries = [Projectile() for _ in range(size)]

    @property
    def entries(self) -> list[Projectile]:
        return self._entries

    def reset(self) -> None:
        for entry in self._entries:
            entry.active = False

    def spawn(
        self,
        *,
        pos: Vec2,
        angle: float,
        type_id: ProjectileTemplateId,
        owner: OwnerRef,
        travel_budget: float = 0.0,
        hits_players: bool = False,
    ) -> int:
        index = None
        for i, entry in enumerate(self._entries):
            if not entry.active:
                index = i
                break
        if index is None:
            index = len(self._entries) - 1
        entry = self._entries[index]

        entry.active = True
        # Native projectile spawn writes angle/pos as float32 fields; keep those
        # stores narrowed so next-tick movement uses the same precision.
        angle_f32 = float(f32(float(angle)))
        pos_f32 = Vec2(float(f32(float(pos.x))), float(f32(float(pos.y))))
        entry.angle = angle_f32
        entry.pos = pos_f32
        entry.origin = pos_f32
        entry.vel = Vec2(
            float(f32(math.cos(float(angle_f32)) * 1.5)),
            float(f32(math.sin(float(angle_f32)) * 1.5)),
        )
        entry.type_id = type_id
        # Native stores the f32 literal 0.4.
        entry.life_timer = float(f32(0.4))
        entry.reserved = 0.0
        entry.energy_heat_mult = 1.0
        entry.crit_mult = 1.0
        entry.perk_damage_mult = 1.0
        entry.did_crit = False
        entry.pierce_left = 0.0
        entry.speed_scale = 1.0
        entry.travel_budget = float(travel_budget)
        weapon_entry = weapon_entry_for_projectile_type_id(type_id)
        entry.travel_budget = float(weapon_entry.travel_budget)
        entry.owner = owner
        entry.hits_players = bool(hits_players)
        entry.tenet_reverse = False
        # Not native: Seeker Rounds - must be reset on every reuse (not just
        # left at whatever the previous occupant of this slot had), or a
        # perk-proc bolt reusing this slot could inherit a stale, still-valid
        # -looking shot_seq and get miscounted as a primary-fire hit.
        entry.shot_seq = -1
        # Not native: Ion Overload - same reuse hazard as shot_seq above. A
        # charged bolt that never hits anything (goes out of bounds, expires
        # mid-flight) leaves this slot's ion_overload_charge nonzero forever,
        # since _maybe_ion_overload_on_hit only clears it on an actual hit.
        # Without this reset, the next totally unrelated shot to reuse this
        # slot (any weapon, any player) silently inherits that stale charge
        # and blooms a giant ion nova the first time IT hits something - at
        # whatever random spot that unrelated shot happens to land.
        entry.ion_overload_charge = 0.0
        # Not native: Pact of Ricochet - same slot-reuse hazard.
        entry.ricochet_chained = False
        entry.ricochet_ignore_idx = -1
        entry.ricochet_damage = 0.0

        collision_profile = projectile_collision_profile(type_id)
        entry.hit_radius = float(collision_profile.hit_radius)
        entry.damage_pool = float(collision_profile.initial_damage_pool)
        return index

    def iter_active(self) -> list[Projectile]:
        return [entry for entry in self._entries if entry.active]

    def step(self, ctx: PrimaryStepCtx) -> list[ProjectileHit]:
        """Update the main projectile pool.

        Modeled after `projectile_update` (0x00420b90) for the subset used by demo/state-9 work.
        """
        dt = float(f32(float(ctx.dt)))
        creatures = ctx.creatures
        options = ctx.options
        world_size = float(f32(float(options.world_size)))
        damage_scale_by_type = options.damage_scale_by_type
        ion_aoe_scale = float(options.ion_aoe_scale)
        detail_preset = int(options.detail_preset)
        rng = options.rng
        runtime_state = options.runtime_state
        players = options.players
        hit_runtime = options.hit_runtime
        creature_damage_runtime = options.creature_damage_runtime
        if creature_damage_runtime is None:
            creature_damage_runtime = DirectCreatureDamageRuntime(creatures=creatures)

        if dt <= 0.0:
            return []

        poison_bullets_active = False
        ion_scale = float(ion_aoe_scale)
        poison_idx = int(PerkId.POISON_BULLETS)
        perk_players = players
        # Barrel Greaser (double step count) and Ion Gun Master (ion blast
        # radius) resolve through crimson.progression now; Poison Bullets is
        # still a raw perk check.
        team_stats = resolve_team_stats(perk_players)
        barrel_greaser_active = team_stats.has("projectile_double_steps")
        ion_gun_master_active = float(team_stats.damage_mult_ion) != 1.0
        # Not native: run mods (crimson.run_mods.RunModId.PROJECTILE_SPEED).
        # Scales each per-tick step's size; Barrel Greaser above instead
        # doubles the step *count* for player-owned bolts - the two compose
        # independently (see the docstring note where PROJECTILE_SPEED is
        # defined in run_mods/ids.py for the full explanation).
        projectile_speed_mult = float(team_stats.projectile_speed_mult)
        for player in perk_players:
            perk_counts = player.perk_counts
            if 0 <= poison_idx < len(perk_counts) and int(perk_counts[poison_idx]) > 0:
                poison_bullets_active = True

        if ion_scale == 1.0 and ion_gun_master_active:
            ion_scale = 1.2

        effects: EffectPool | None = runtime_state.effects
        sfx_queue: MutableSequence[SfxId] | None = runtime_state.sfx_queue

        hits: list[ProjectileHit] = []
        margin = 64.0

        def _creature_is_collidable(creature: CreatureState) -> bool:
            if not creature.active:
                return False
            return creature_lifecycle_is_collidable(creature.lifecycle_stage)

        creature_spatial = CreatureSpatialHash(creatures=creatures, is_collidable=_creature_is_collidable)

        def _damage_scale(type_id: int) -> float:
            value = damage_scale_by_type.get(type_id)
            if value is not None:
                return float(value)
            return float(weapon_entry_for_projectile_type_id(ProjectileTemplateId(type_id)).damage_scale)

        def _damage_distance_f32(origin: Vec2, pos: Vec2) -> float:
            dx = float(f32(float(origin.x) - float(pos.x)))
            dy = float(f32(float(origin.y) - float(pos.y)))
            dist_sq = float(f32(float(f32(float(dx) * float(dx))) + float(f32(float(dy) * float(dy)))))
            return float(f32(math.sqrt(float(dist_sq))))

        def _maybe_fork_shot_on_hit(proj: Projectile, hit_idx: int) -> None:
            """Fork Shot bonus (not native): split a non-piercing hit into two.

            Re-owns children to the struck creature, same as Splitter Gun's own
            `_pre_hit_splitter` - the hit-resolution loop below explicitly
            discards a hit when `owner_creature_idx == hit_idx` (see
            `owner_collision`), so without this the children spawn on top of
            the creature they just came from and can be consumed by it again
            before ever traveling anywhere.
            """

            if proj.reserved != _FORK_RESERVED_NONE:
                return  # already a fork product (or already forked) - fork once
            owner_player_index = proj.owner.player_index_in_bounds(len(players))
            if owner_player_index is None:
                return
            if float(players[owner_player_index].projectile_fork_timer) <= 0.0:
                return
            profile = _PROJECTILE_COLLISION_PROFILE_BY_TYPE_ID.get(proj.type_id)
            if profile is not None and profile.initial_damage_pool > 1.0:
                return  # already pierces - leave piercing weapons alone
            proj.reserved = _FORK_RESERVED_FORKED
            child_reserved = (
                _FORK_RESERVED_SHOTGUN_CHILD
                if players[owner_player_index].weapon.weapon_id in _SHOTGUN_WEAPON_IDS
                else _FORK_RESERVED_FORKED
            )
            for offset in (-_FORK_SHOT_ANGLE_RAD, _FORK_SHOT_ANGLE_RAD):
                child_index = self.spawn(
                    pos=proj.pos,
                    angle=float(proj.angle) + offset,
                    type_id=proj.type_id,
                    owner=OwnerRef.from_creature(int(hit_idx)),
                    travel_budget=float(proj.travel_budget),
                    hits_players=bool(proj.hits_players),
                )
                self._entries[child_index].reserved = child_reserved

        def _maybe_explosive_payload_on_hit(proj: Projectile) -> None:
            """Explosive Payload bonus (not native): detonate a flagged pellet.

            Reuses the exact secondary-projectile DETONATION state the Rocket
            Launcher itself uses on impact (see
            `secondary_pool.py::DetonationRule`) - an expanding-radius pulse
            that deals its own damage over ~1/3s to everything it catches, on
            top of whatever direct damage this hit already dealt. Consumed
            (`is_rocket = False`) so a piercing round only explodes once.

            Blast size/damage scales (damped) with the firing weapon's own
            effective damage_scale - see `_explosive_payload_blast_scale`.
            """

            if not proj.is_rocket:
                return
            proj.is_rocket = False
            blast_scale = _explosive_payload_blast_scale(_native_damage_scale_for_type_id(int(proj.type_id)))
            if blast_scale <= 0.0:
                return  # utility weapons (0 damage_scale) don't get a blast
            from ..types import SecondaryProjectileTypeId
            from .secondary_pool import SecondarySpawnSpec

            runtime_state.secondary_projectiles.spawn_from_spec(
                SecondarySpawnSpec(
                    pos=proj.pos,
                    angle=0.0,
                    type_id=SecondaryProjectileTypeId.DETONATION,
                    owner=proj.owner,
                    time_to_live=blast_scale,
                ),
            )
            if effects is not None:
                effects.spawn_explosion_burst(
                    pos=proj.pos,
                    scale=0.5,
                    rng=rng,
                    detail_preset=int(detail_preset),
                )
            # Not native: half volume (sfx_queue_quiet) - this can retrigger on
            # every shot while the powerup is active, which got loud fast at
            # the default level.
            runtime_state.sfx_queue_quiet.append(SfxId.EXPLOSION_MEDIUM)

        def _maybe_ion_overload_on_hit(proj: Projectile) -> None:
            """Ion Overload bonus (not native): bloom the charged bolt on hit.

            The bolt is a real ION_CANNON-type projectile carrying the total
            charge time it was fired with (`Projectile.ion_overload_charge`).
            Consumed on its first hit, at which point it drops a much bigger
            (logarithmically-scaled) stationary ion nova at the hit position
            instead of falling through to the real Ion Cannon's own fixed
            128px/300dps linger - see bonuses/ion_overload.py.
            """

            charge = float(proj.ion_overload_charge)
            if charge <= 0.0:
                return
            proj.ion_overload_charge = 0.0
            owner_player_index = proj.owner.player_index_in_bounds(len(players))
            if owner_player_index is None:
                return
            from ...bonuses.ion_overload import bloom_ion_overload_nova

            bloom_ion_overload_nova(
                players[owner_player_index],
                proj.pos,
                charge,
                effects=effects,
                detail_preset=int(detail_preset),
            )

        def _damage_type_for(type_id: int) -> int:
            return damage_type_for_projectile_type_id(type_id)

        update_ctx = _ProjectileUpdateCtx(
            pool=self,
            creatures=creatures,
            dt=float(dt),
            ion_scale=float(ion_scale),
            detail_preset=int(detail_preset),
            rng=rng,
            runtime_state=runtime_state,
            effects=effects,
            sfx_queue=sfx_queue,
            creature_damage_runtime=creature_damage_runtime,
            sync_creature_index=creature_spatial.sync_index,
        )

        def _reset_shock_chain_if_owner(index: int) -> None:
            if runtime_state.shock_chain_projectile_id != index:
                return
            runtime_state.shock_chain_projectile_id = -1
            runtime_state.shock_chain_links_left = 0

        for proj_index, proj in enumerate(self._entries):
            if not proj.active:
                continue

            if proj.tenet_reverse:
                # Tenet Gun (not native): this bolt was spawned at the far
                # end of the shot, aimed back at the muzzle (weapon_runtime/
                # tenet_gun_spawn.py) - everything else about it (damage,
                # collision, pierce, Fork Shot, ...) is the normal code every
                # other bullet uses; this just stops it once it arrives back
                # at its owner instead of flying on through them.
                owner_player_index = proj.owner.player_index_in_bounds(len(players))
                if owner_player_index is not None and proj.pos.distance_to(players[owner_player_index].pos) <= _TENET_REVERSE_STOP_RADIUS:
                    proj.active = False
                    continue

            rule = primary_rule_for_type_id(ProjectileTemplateId(proj.type_id))

            if proj.life_timer <= 0.0:
                proj.active = False
                # Native `projectile_update` clears the active flag but still
                # runs this tick's life_timer branch, so expired ion projectiles
                # can apply one final linger AoE pass.

            if proj.life_timer < 0.4:
                if rule.reset_shock_chain_on_linger:
                    _reset_shock_chain_if_owner(proj_index)
                rule.linger(update_ctx, proj)
                continue

            if (
                proj.pos.x < -margin
                or proj.pos.y < -margin
                or proj.pos.x > world_size + margin
                or proj.pos.y > world_size + margin
            ):
                proj.life_timer = float(f32(float(proj.life_timer) - float(dt)))
                continue

            steps = int(proj.travel_budget)
            if barrel_greaser_active and proj.owner.is_player():
                steps *= 2

            # Decompile parity (`projectile_update`, 0x00420b90):
            #   local_cc += (float)(cos(angle - pi/2) * frame_dt * 20.0f) * speed_scale * 3.0f
            #   local_c8 += (float)(sin(angle - pi/2) * frame_dt * 20.0f) * speed_scale * 3.0f
            # The game leaves x87 in 24-bit precision mode, so every arithmetic
            # operation in the integration chain rounds to a 24-bit significand.
            # Transcendental results stay wide until the first multiply.
            heading_radians = x87_pc24_sub(float(proj.angle), NATIVE_HALF_PI)
            effective_speed_scale = float(proj.speed_scale) * projectile_speed_mult
            step_x = x87_pc24_cos_mul(
                heading_radians,
                dt,
                20.0,
                effective_speed_scale,
                3.0,
            )
            step_y = x87_pc24_sin_mul(
                heading_radians,
                dt,
                20.0,
                effective_speed_scale,
                3.0,
            )
            dir_x = math.cos(heading_radians)
            dir_y = math.sin(heading_radians)
            acc = Vec2()
            step = 0
            while step < steps:
                acc = Vec2(
                    x87_pc24_add(acc.x, step_x),
                    x87_pc24_add(acc.y, step_y),
                )

                if acc.length() >= 4.0 or steps <= step + 3:
                    move = acc
                    proj.pos = Vec2(
                        float(f32(float(proj.pos.x) + float(move.x))),
                        float(f32(float(proj.pos.y) + float(move.y))),
                    )
                    acc = Vec2()

                    hit_idx = None
                    owner_creature_idx = proj.owner.creature_index_in_bounds(len(creatures))
                    for idx in creature_spatial.candidate_indices(pos=proj.pos, radius=float(proj.hit_radius)):
                        creature = creatures[idx]
                        if not _creature_is_collidable(creature):
                            continue
                        if proj.ricochet_ignore_idx == idx:
                            # Not native: a Pact of Ricochet bounce passes
                            # through the creature it bounced off - see
                            # Projectile.ricochet_ignore_idx.
                            continue
                        if proj.pierce_left >= 1.0 and creature.hp <= 0.0:
                            # WPU pierce: a corpse we just punched through must not
                            # count as the hit that stops the bolt.
                            continue
                        if _within_native_find_radius(
                            origin=proj.pos,
                            target=creature.pos,
                            radius=float(proj.hit_radius),
                            target_size=float(creature.size),
                        ):
                            hit_idx = idx
                            break

                    owner_collision = (
                        hit_idx is not None and owner_creature_idx is not None and int(hit_idx) == owner_creature_idx
                    )
                    if owner_collision:
                        # Native `creature_find_in_radius` does not skip owner id during
                        # search; owner hits are discarded after the first match instead of
                        # continuing to a later candidate in the same tick.
                        hit_idx = None

                    if hit_idx is None:
                        can_hit_players = True
                        if int(proj_index) == int(
                            runtime_state.shock_chain_projectile_id,
                        ):
                            # Native skips `player_find_in_radius` for the currently tracked
                            # shock-chain projectile slot in this branch.
                            can_hit_players = False

                        if proj.hits_players and can_hit_players:
                            hit_player_idx = None
                            owner_player_index = proj.owner.player_index_in_bounds(len(players))
                            for idx, player in enumerate(players):
                                if owner_player_index is not None and idx == owner_player_index:
                                    continue
                                if float(player.health) <= 0.0:
                                    continue
                                if _within_native_find_radius(
                                    origin=proj.pos,
                                    target=player.pos,
                                    radius=float(proj.hit_radius),
                                    target_size=float(player.size),
                                ):
                                    hit_player_idx = idx
                                    break

                            if hit_player_idx is None:
                                step += 3
                                continue

                            proj.life_timer = 0.25
                            hit_runtime.apply_player_damage(int(hit_player_idx), 10.0)

                            step += 3
                            continue

                        step += 3
                        continue

                    type_id = proj.type_id
                    creature = creatures[hit_idx]

                    perk_ctx = _ProjectileHitPerkCtx(
                        proj=proj,
                        creature=creature,
                        rng=rng,
                        poison_bullets_active=poison_bullets_active,
                    )
                    for hook in _PROJECTILE_HIT_PERK_HOOKS:
                        hook(perk_ctx)

                    rule.pre_hit(update_ctx, proj, int(hit_idx))
                    _maybe_fork_shot_on_hit(proj, int(hit_idx))
                    _maybe_explosive_payload_on_hit(proj)
                    _maybe_ion_overload_on_hit(proj)

                    # Native increments the global shots-hit counter for any
                    # owner (creature-owned splitter children included) when the
                    # target is still at the alive sentinel; non-player owners
                    # map to the player-1 global slot.
                    owner_player_index = proj.owner.player_index_in_bounds(len(runtime_state.shots_hit))
                    if creature_lifecycle_is_alive(creature.lifecycle_stage) and runtime_state.shots_hit:
                        shots_hit = runtime_state.shots_hit
                        shots_hit[owner_player_index if owner_player_index is not None else 0] += 1

                    target = creature.pos
                    hit = ProjectileHit(
                        type_id=type_id,
                        origin=proj.origin,
                        hit=proj.pos,
                        target=target,
                    )
                    hits.append(hit)
                    hit_presentation = hit_runtime.begin_hit_presentation(hit)

                    if proj.life_timer != 0.25 and rule.stop_on_hit and proj.pierce_left < 1.0:
                        proj.life_timer = 0.25
                        jitter = rng.rand_tagged(RngCallerStatic.PROJECTILE_UPDATE_STOP_ON_HIT_JITTER) & 3
                        # Native rounds the multiply and add as separate PC24 operations.
                        proj.pos = Vec2(
                            _stop_on_hit_jitter_axis_f32(dir_x, jitter, proj.pos.x),
                            _stop_on_hit_jitter_axis_f32(dir_y, jitter, proj.pos.y),
                        )

                    dist = _damage_distance_f32(proj.origin, proj.pos)

                    rule.post_hit(
                        update_ctx,
                        _ProjectileHitInfo(
                            proj_index=int(proj_index),
                            proj=proj,
                            hit_idx=int(hit_idx),
                            move=move,
                            target=target,
                        ),
                    )

                    damage_scale = _damage_scale(type_id)
                    damage_amount = _projectile_damage_amount_f32(dist, damage_scale)
                    if proj.reserved == _FORK_RESERVED_SHOTGUN_CHILD:
                        damage_amount = float(f32(float(damage_amount) * _FORK_SHOT_SHOTGUN_DAMAGE_MULT))
                    if proj.energy_heat_mult != 1.0:
                        # Plasma clip-heat ramp, stamped on the bolt when it was fired.
                        damage_amount = float(f32(float(damage_amount) * float(proj.energy_heat_mult)))
                    if proj.crit_mult != 1.0:
                        # Crit compensation/multiplier, stamped on the bolt when it was fired.
                        damage_amount = float(f32(float(damage_amount) * float(proj.crit_mult)))
                    if proj.perk_damage_mult != 1.0:
                        # Perk Efficacy, stamped on a perk-proc bolt when it was fired.
                        damage_amount = float(f32(float(damage_amount) * float(proj.perk_damage_mult)))
                    shooter_index = proj.owner.player_index()
                    shooter = (
                        players[shooter_index]
                        if shooter_index is not None and 0 <= shooter_index < len(players)
                        else None
                    )
                    if proj.did_crit:
                        # Rewrite-only: Cold Snap - a real crit (not just the
                        # compensation-only multiplier) freezes the target.
                        if shooter is not None and perk_active(shooter, PerkId.COLD_SNAP):
                            creature.crit_freeze_timer = COLD_SNAP_FREEZE_DURATION

                    if proj.ricochet_damage > 0.0:
                        # Not native: a Pact of Ricochet bounce deals exactly
                        # what the hit that spawned it dealt (every multiplier
                        # already applied, penalty included) - see
                        # Projectile.ricochet_damage. Recomputing it here
                        # would score the bounce's own short hop as a
                        # point-blank shot and drop every parent multiplier.
                        damage_amount = float(proj.ricochet_damage)
                    elif shooter is not None:
                        # Not native: Pact of the Deadeye relic - near/far
                        # damage curve off the shot's own travel distance.
                        deadeye_mult = relic_deadeye_pact.distance_damage_mult(dist)
                        if deadeye_mult != 1.0:
                            damage_amount = float(f32(float(damage_amount) * deadeye_mult))

                        # Not native: Pact of Ricochet relic - both the
                        # original hit and its one bounce deal reduced
                        # damage; only non-piercing shots chain (a piercing
                        # round already hits multiple targets on its own).
                        ricochet_mult = relic_ricochet.damage_mult()
                        if ricochet_mult != 1.0 and proj.pierce_left < 1.0:
                            damage_amount = float(f32(float(damage_amount) * ricochet_mult))
                            if not proj.ricochet_chained:
                                chain_idx = relic_ricochet.pick_chain_target(proj.pos, int(hit_idx), creatures)
                                if chain_idx is not None:
                                    chain_target = creatures[chain_idx]
                                    chain_dx = float(chain_target.pos.x) - float(proj.pos.x)
                                    chain_dy = float(chain_target.pos.y) - float(proj.pos.y)
                                    chain_angle = math.atan2(chain_dy, chain_dx) + NATIVE_HALF_PI
                                    # Not native: spawning exactly at proj.pos
                                    # (still inside the just-hit creature's own
                                    # hit radius) lets the bounce immediately
                                    # re-hit the same creature and never
                                    # travel anywhere - nudge the spawn point
                                    # partway toward the new target, just far
                                    # enough to clear the struck creature's
                                    # own size, without overshooting past the
                                    # new target itself.
                                    chain_dist = math.hypot(chain_dx, chain_dy)
                                    chain_pos = proj.pos
                                    if chain_dist > 0.0:
                                        clearance = min(chain_dist * 0.5, float(creature.size) + 10.0)
                                        chain_pos = Vec2(
                                            float(proj.pos.x) + chain_dx / chain_dist * clearance,
                                            float(proj.pos.y) + chain_dy / chain_dist * clearance,
                                        )
                                    chain_id = self.spawn(
                                        pos=chain_pos,
                                        angle=chain_angle,
                                        type_id=proj.type_id,
                                        owner=proj.owner,
                                        travel_budget=float(proj.travel_budget),
                                        hits_players=bool(proj.hits_players),
                                    )
                                    self._entries[chain_id].ricochet_chained = True
                                    self._entries[chain_id].ricochet_ignore_idx = int(hit_idx)
                                    self._entries[chain_id].ricochet_damage = float(damage_amount)

                    did_pierce = False
                    if damage_amount > 0.0 and creature.hp > 0.0:
                        # Not native: Overdue's non-crit streak and Harvester's
                        # Scythe's heal only count an actual hit on a live
                        # creature - fire.py rolls (and stamps) the crit at
                        # spawn time, independent of whether the shot ever
                        # connects, so this is the first point a real hit is
                        # confirmed. A piercing shot re-enters this block once
                        # per creature it goes on to hit, so each connect
                        # counts separately, same as a fresh shot would.
                        if shooter is not None:
                            # Not native: Pact of Gathering Winds relic - a
                            # confirmed hit builds a stack, regardless of
                            # weapon/perk. Piercing shots re-enter this block
                            # once per creature hit, same as Seeker Rounds
                            # below, so a pierce through 3 targets grants 3.
                            relic_gathering_winds.gain_stack(shooter)
                            if (
                                perk_active(shooter, PerkId.SEEKER_ROUNDS)
                                and proj.shot_seq >= 0
                                and proj.shot_seq != shooter.seeker_rounds_last_shot_seq
                            ):
                                # Not native: dedupe by shot_seq so a shotgun's
                                # pellets or one piercing round's multiple hits
                                # all count as a single shot, not one per hit.
                                shooter.seeker_rounds_last_shot_seq = proj.shot_seq
                                shooter.seeker_rounds_hit_counter = int(shooter.seeker_rounds_hit_counter) + 1
                                if shooter.seeker_rounds_hit_counter >= SEEKER_ROUNDS_HIT_THRESHOLD:
                                    shooter.seeker_rounds_hit_counter = 0
                                    from ..types import SecondaryProjectileTypeId
                                    from .secondary_pool import SecondarySpawnSpec

                                    # Not native: a Hollow Form clone shares its
                                    # real player's index (see OwnerRef.
                                    # via_hollow_form's comment) - spawn from the
                                    # clone's frozen position instead of wherever
                                    # the real player currently is, when this hit
                                    # came from the clone.
                                    bonus_spawn_pos = (
                                        shooter.hollow_form_pos if proj.owner.via_hollow_form else shooter.pos
                                    )
                                    rocket_idx = runtime_state.secondary_projectiles.spawn_from_spec(
                                        SecondarySpawnSpec(
                                            pos=bonus_spawn_pos,
                                            angle=0.0,
                                            type_id=SecondaryProjectileTypeId.HOMING_ROCKET,
                                            owner=proj.owner,
                                            creatures=creatures,
                                        ),
                                    )
                                    runtime_state.secondary_projectiles.entries[rocket_idx].crit_mult = float(
                                        shooter.stats.perk_efficacy,
                                    )
                            if proj.did_crit:
                                # Harvester's Scythe is unrelated to Overdue's
                                # window and always heals on a real crit hit.
                                harvester_scythe_on_crit(shooter)
                                # A crit still breaks the streak instantly and
                                # unconditionally (while the window isn't
                                # already open, per the freeze rule below) -
                                # only the *ticking up* side gets throttled,
                                # not the reset.
                                if shooter.overdue_window_timer <= 0.0:
                                    shooter.overdue_streak = 0
                            else:
                                # Overdue's streak only advances at most once
                                # per OVERDUE_TICK_COOLDOWN, and not at all
                                # while its window is open (frozen until the
                                # bonus actually ends). Without the tick
                                # cooldown, a high roll-rate weapon (Minigun/
                                # Shotgun) completes the whole streak in a
                                # fraction of a second no matter how high
                                # OVERDUE_STREAK_THRESHOLD is set, trivializing
                                # the perk there while it stays weak on slow
                                # weapons - the cap brings every weapon's
                                # effective streak-building rate down to the
                                # same ceiling; a weapon already slower than
                                # that (Cannon) is untouched by it.
                                if (
                                    shooter.overdue_window_timer <= 0.0
                                    and shooter.overdue_tick_cooldown_timer <= 0.0
                                ):
                                    shooter.overdue_streak = int(shooter.overdue_streak) + 1
                                    shooter.overdue_tick_cooldown_timer = OVERDUE_TICK_COOLDOWN
                        remaining = proj.damage_pool - 1.0
                        proj.damage_pool = remaining
                        # Native `projectile_update` writes both impulse components from the
                        # same cosine term (`cos(angle - pi/2) * speed_scale`).
                        impulse_angle = f32(float(proj.angle) - NATIVE_HALF_PI)
                        impulse_axis = f32(math.cos(float(impulse_angle)) * float(proj.speed_scale))
                        impulse = Vec2(float(impulse_axis), float(impulse_axis))
                        damage_type = _damage_type_for(type_id)
                        if remaining <= 0.0:
                            _apply_damage_to_creature(
                                creatures,
                                int(hit_idx),
                                float(damage_amount),
                                damage_type=damage_type,
                                impulse=impulse,
                                owner=proj.owner,
                                creature_damage_runtime=creature_damage_runtime,
                                is_projectile_hit=True,
                            )
                            creature_spatial.sync_index(int(hit_idx))
                            if proj.pierce_left >= 1.0:
                                # WPU kinetic pierce: full-damage pass-through.
                                proj.pierce_left = float(proj.pierce_left) - 1.0
                                proj.damage_pool = 1.0
                                did_pierce = True
                            elif proj.life_timer != 0.25:
                                proj.life_timer = 0.25
                        else:
                            _apply_damage_to_creature(
                                creatures,
                                int(hit_idx),
                                float(remaining),
                                damage_type=damage_type,
                                impulse=impulse,
                                owner=proj.owner,
                                creature_damage_runtime=creature_damage_runtime,
                                is_projectile_hit=True,
                            )
                            creature_spatial.sync_index(int(hit_idx))
                            proj.damage_pool -= float(creature.hp)

                    # The default single freeze shard (`crt_rand` @ 0x4215fa ->
                    # caller_static 0x4215ff) is presentation: it spawns inside the
                    # post-hit decal branch, after the burn draw, in
                    # `queue_projectile_decals_post_hit`.

                    if not did_pierce and proj.damage_pool == 1.0:
                        # Native clears damage_pool to 0.0 whenever it's exactly 1.0
                        # in this branch, even if life_timer is already 0.25.
                        life_before = float(proj.life_timer)
                        proj.damage_pool = 0.0
                        if life_before != 0.25:
                            proj.life_timer = 0.25

                    if proj.life_timer == 0.25 and rule.stop_on_hit:
                        if hit_presentation is not None:
                            hit_runtime.finish_hit_presentation(hit, hit_presentation)
                        break

                    if not did_pierce and proj.damage_pool <= 0.0:
                        if hit_presentation is not None:
                            hit_runtime.finish_hit_presentation(hit, hit_presentation)
                        break

                    if hit_presentation is not None:
                        hit_runtime.finish_hit_presentation(hit, hit_presentation)

                step += 3

        return hits

    def update_demo(
        self,
        dt: float,
        creatures: Sequence[CreatureState],
        *,
        world_size: float,
        speed_by_type: dict[int, float],
        damage_by_type: dict[int, float],
    ) -> list[ProjectileHit]:
        """Update a small projectile subset for the demo view."""

        if dt <= 0.0:
            return []

        hits: list[ProjectileHit] = []
        margin = 64.0

        for proj in self._entries:
            if not proj.active:
                continue

            if proj.life_timer <= 0.0:
                proj.active = False
                continue

            if proj.life_timer < 0.4:
                if proj.type_id == ProjectileTemplateId.ION_RIFLE:
                    damage = x87_pc24_mul(dt, f32(100.0))
                    radius = 88.0
                    for creature in creatures:
                        if creature.hp <= 0.0:
                            continue
                        creature_radius = _hit_radius_for(creature)
                        hit_r = radius + creature_radius
                        if Vec2.distance_sq(proj.pos, creature.pos) <= hit_r * hit_r:
                            creature.hp = x87_pc24_sub(creature.hp, damage)
                elif proj.type_id == ProjectileTemplateId.ION_MINIGUN:
                    damage = x87_pc24_mul(dt, f32(40.0))
                    radius = 60.0
                    for creature in creatures:
                        if creature.hp <= 0.0:
                            continue
                        creature_radius = _hit_radius_for(creature)
                        hit_r = radius + creature_radius
                        if Vec2.distance_sq(proj.pos, creature.pos) <= hit_r * hit_r:
                            creature.hp = x87_pc24_sub(creature.hp, damage)
                proj.life_timer = float(f32(float(proj.life_timer) - float(dt)))
                continue

            if (
                proj.pos.x < -margin
                or proj.pos.y < -margin
                or proj.pos.x > world_size + margin
                or proj.pos.y > world_size + margin
            ):
                proj.life_timer = float(f32(float(proj.life_timer) - float(dt)))
                continue

            speed = speed_by_type.get(proj.type_id, 650.0) * proj.speed_scale
            direction = Vec2.from_heading(float(proj.angle))
            proj.pos = proj.pos + direction * (speed * dt)

            hit_idx = None
            for idx, creature in enumerate(creatures):
                if creature.hp <= 0.0:
                    continue
                creature_radius = _hit_radius_for(creature)
                hit_r = proj.hit_radius + creature_radius
                if Vec2.distance_sq(proj.pos, creature.pos) <= hit_r * hit_r:
                    hit_idx = idx
                    break
            if hit_idx is None:
                continue

            creature = creatures[hit_idx]
            hits.append(
                ProjectileHit(
                    type_id=proj.type_id,
                    origin=proj.origin,
                    hit=proj.pos,
                    target=creature.pos,
                ),
            )

            creature = creatures[hit_idx]
            creature.hp -= damage_by_type.get(proj.type_id, 10.0)

            proj.life_timer = 0.25

        return hits
