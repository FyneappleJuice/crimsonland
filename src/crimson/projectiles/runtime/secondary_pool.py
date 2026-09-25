from __future__ import annotations

import math
from collections.abc import Callable, MutableSequence, Sequence
from typing import TYPE_CHECKING

import msgspec

from grim.color import RGBA
from grim.geom import Vec2
from grim.rand import Crand
from grim.sfx_map import SfxId

from ...creatures.damage_runtime import CreatureDamageRuntime, DirectCreatureDamageRuntime
from ...creatures.damage_types import CreatureDamageType
from ...creatures.lifecycle import creature_lifecycle_is_alive, creature_lifecycle_is_collidable
from ...effects import EffectPool, FxQueue, SpriteEffectPool
from ...effects_atlas import EffectId
from ...meta.relics_impl import gathering_winds as relic_gathering_winds
from ...math_parity import (
    NATIVE_HALF_PI,
    f32,
    x87_fpatan,
    x87_pc24_add,
    x87_pc24_cos_mul,
    x87_pc24_mul,
    x87_pc24_sin_mul,
    x87_pc24_sub,
)
from ...owner_ref import OwnerRef
from ...perks.helpers import perk_active
from ...perks.ids import PerkId
from ...perks.impl.harvester_scythe import harvester_scythe_on_crit
from ...rng_caller_static import RngCallerStatic
from ..types import (
    SECONDARY_PROJECTILE_POOL_SIZE,
    SecondaryProjectile,
    SecondaryProjectileTypeId,
)
from .collision import _apply_damage_to_creature, _within_native_find_radius, creature_find_nearest_alive
from .projectile_pool import (
    COLD_SNAP_FREEZE_DURATION,
    OVERDUE_TICK_COOLDOWN,
    SEEKER_ROUNDS_HIT_THRESHOLD,
    _explosive_payload_blast_scale,
)
from .secondary_rules import (
    DetonationRule,
    HomingRocketRule,
    RocketMinigunRule,
    RocketRule,
    secondary_rule_for_type_id,
)
from .spatial_hash import CreatureSpatialHash

if TYPE_CHECKING:
    from ...creatures.runtime import CreatureState
    from ...gameplay import GameplayState
    from ...sim.state_types import PlayerState


# Not native: Fork Shot / Explosive Payload for rocket-family weapons, now on
# hit instead of at spawn (see the removed on-spawn version's history in
# fire.py) - same +-60 degree split as the bullet version, spawned from the
# impact point instead of the muzzle so a homing child gets a fresh shot at
# retargeting rather than just repeating the parent's original flight.
_ROCKET_FORK_SHOT_ANGLE_RAD = 1.0471976
# Rocket weapons already carry a heavier per-hit punch (direct hit + AoE) than
# a bullet pellet, so a fork child defaults to half damage - same 50% cut the
# Shotgun's own bullet fork children take, and for the same reason (already a
# lot of damage on target; a full-power third copy is too much).
_ROCKET_FORK_CHILD_DAMAGE_MULT_DEFAULT = 0.5
# Rocket Launcher fires one rocket at a time (no pellet/volley multiplier to
# begin with), so its fork children only take half of the default penalty.
_ROCKET_FORK_CHILD_DAMAGE_MULT_ROCKET_LAUNCHER = 0.75
# All four rocket weapons share the same native, pre-crit-compensation
# damage_scale override (1.0) in projectile_pool.py's
# _EXPLOSIVE_PAYLOAD_NATIVE_DAMAGE_SCALE, so the blast this bonus adds on a
# rocket hit is the same fixed size for all of them - reuses the exact
# formula/anchor bullets use, just with that shared 1.0 baked in instead of
# looking up a per-weapon damage_scale that rocket damage doesn't otherwise use.
_ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE = _explosive_payload_blast_scale(1.0)


_SECONDARY_PRE_HIT_DECAL_CALLERS = (
    (
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DX_1,
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DY_1,
    ),
    (
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DX_2,
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DY_2,
    ),
    (
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DX_3,
        RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_DECAL_DY_3,
    ),
)


class SecondarySpawnSpec(msgspec.Struct, frozen=True):
    pos: Vec2
    angle: float
    type_id: SecondaryProjectileTypeId
    owner: OwnerRef = msgspec.field(default_factory=lambda: OwnerRef.from_local_player(0))
    time_to_live: float = 2.0
    target_hint: Vec2 | None = None
    creatures: Sequence[CreatureState] | None = None


class SecondaryStepCtx(msgspec.Struct, frozen=True):
    dt: float
    creatures: Sequence[CreatureState]
    runtime_state: GameplayState | None = None
    fx_queue: FxQueue | None = None
    detail_preset: int = 5
    creature_damage_runtime: CreatureDamageRuntime | None = None
    # Native secondary-rocket hits run the same first-hit game-tune branch as
    # bullet hits (sfx_play_exclusive + one playlist rand) outside demo/rush;
    # when unset, the plain explosion sound is queued directly.
    play_rocket_hit_audio: Callable[[], None] | None = None
    # Not native: needed to read the firing player's Fork Shot / Explosive
    # Payload timers on a direct hit (see _maybe_fork_shot_on_hit /
    # _maybe_explosive_payload_on_hit below) - both bonuses live on
    # PlayerState, not the projectile itself.
    players: Sequence[PlayerState] = ()


class SecondaryProjectilePool:
    def __init__(self, *, size: int = SECONDARY_PROJECTILE_POOL_SIZE) -> None:
        self._entries = [SecondaryProjectile() for _ in range(size)]

    @property
    def entries(self) -> list[SecondaryProjectile]:
        return self._entries

    def reset(self) -> None:
        for entry in self._entries:
            entry.active = False

    def spawn_from_spec(self, spec: SecondarySpawnSpec) -> int:
        pos = Vec2(f32(spec.pos.x), f32(spec.pos.y))
        angle = f32(spec.angle)
        type_id = SecondaryProjectileTypeId(spec.type_id)
        owner = spec.owner
        time_to_live = float(spec.time_to_live)
        target_hint = spec.target_hint
        creatures = spec.creatures

        index = None
        for i, entry in enumerate(self._entries):
            if not entry.active:
                index = i
                break
        if index is None:
            index = len(self._entries) - 1

        entry = self._entries[index]
        entry.active = True
        entry.angle = float(angle)
        entry.type_id = type_id
        entry.pos = pos
        entry.owner = owner
        entry.trail_timer = 0.0
        entry.vel = Vec2()
        entry.detonation_t = 0.0
        entry.detonation_scale = 1.0
        entry.crit_mult = 1.0
        entry.did_crit = False
        # Reset every rewrite-only per-shot flag - a reused pool slot must not
        # carry over a previous occupant's Fork Shot / Explosive Payload /
        # Seeker Rounds state.
        entry.fork_reserved = False
        entry.explosive_payload_eligible = False
        entry.fork_shot_eligible = False
        entry.shot_seq = -1

        rule = secondary_rule_for_type_id(type_id)
        match rule:
            case DetonationRule():
                # Detonation uses explicit timer/scale fields now.
                entry.detonation_t = 0.0
                entry.detonation_scale = float(time_to_live)
                entry.vel = Vec2(0.0, f32(time_to_live))
                entry.speed = float(f32(float(time_to_live)))
                return index
            case (
                RocketRule(base_speed=base_speed)
                | HomingRocketRule(base_speed=base_speed)
                | RocketMinigunRule(
                    base_speed=base_speed,
                )
            ):
                radians = x87_pc24_sub(float(angle), NATIVE_HALF_PI)
                if isinstance(rule, HomingRocketRule):
                    # Native stores each trig result as float32 before the
                    # seeker-specific 190x velocity override.
                    entry.vel = Vec2(
                        x87_pc24_cos_mul(radians, 1.0, float(base_speed)),
                        x87_pc24_sin_mul(radians, 1.0, float(base_speed)),
                    )
                else:
                    entry.vel = Vec2(
                        x87_pc24_cos_mul(radians, float(base_speed)),
                        x87_pc24_sin_mul(radians, float(base_speed)),
                    )
                entry.speed = float(f32(float(time_to_live)))

        if isinstance(rule, HomingRocketRule):
            # Native `fx_spawn_secondary_projectile` seeds seeker target_id at spawn via
            # `creature_find_nearest(&player_aim_x, -1, 0.0)`.
            entry.target_id = -1
            if creatures is not None:
                origin = target_hint if target_hint is not None else pos
                entry.target_id = creature_find_nearest_alive(
                    creatures=creatures,
                    origin=origin,
                )

        return index

    def iter_active(self) -> list[SecondaryProjectile]:
        return [entry for entry in self._entries if entry.active]

    def step(self, ctx: SecondaryStepCtx) -> int:
        """Update the secondary projectile pool subset (types 1/2/4 + detonation type 3)."""
        dt = float(ctx.dt)
        creatures = ctx.creatures
        runtime_state = ctx.runtime_state
        fx_queue = ctx.fx_queue
        detail_preset = int(ctx.detail_preset)
        creature_damage_runtime = ctx.creature_damage_runtime
        if creature_damage_runtime is None:
            creature_damage_runtime = DirectCreatureDamageRuntime(creatures=creatures)
        players = ctx.players

        if dt <= 0.0:
            return 0

        def _apply_secondary_damage(
            creature_index: int,
            damage: float,
            *,
            owner: OwnerRef,
            impulse: Vec2 = Vec2(),
            is_projectile_hit: bool = False,
        ) -> None:
            _apply_damage_to_creature(
                creatures,
                int(creature_index),
                float(damage),
                damage_type=CreatureDamageType.EXPLOSION,
                impulse=impulse,
                owner=owner,
                creature_damage_runtime=creature_damage_runtime,
                is_projectile_hit=is_projectile_hit,
            )

        rng = Crand(0)
        freeze_active = False
        effects: EffectPool | None = None
        sprite_effects: SpriteEffectPool | None = None
        sfx_queue: MutableSequence[SfxId] | None = None
        if runtime_state is not None:
            rng = runtime_state.rng
            freeze_active = float(runtime_state.bonuses.freeze) > 0.0
            effects = runtime_state.effects
            sprite_effects = runtime_state.sprite_effects
            sfx_queue = runtime_state.sfx_queue

        def _maybe_rocket_fork_on_hit(entry: SecondaryProjectile, hit_idx: int) -> None:
            """Fork Shot bonus (not native): split a rocket's own hit into two
            more, fired from the impact point - mirrors the bullet version
            (projectile_pool.py::_maybe_fork_shot_on_hit) instead of the
            earlier spawn-time version that forked every rocket at the muzzle.

            Re-owns children to the struck creature, same as the bullet
            version and for the same reason: they spawn on top of it, and the
            owner_creature_idx discard above stops that being an instant
            self-hit.

            Gated on fork_shot_eligible (stamped at spawn), not a live read of
            the owning player's projectile_fork_timer - see that field's
            comment (types.py) for why a snapshotted freebie shot needs this.
            """

            if entry.fork_reserved or not entry.fork_shot_eligible:
                return  # already a fork product (or already forked) - fork once
            entry.fork_reserved = True
            child_mult = (
                _ROCKET_FORK_CHILD_DAMAGE_MULT_ROCKET_LAUNCHER
                if entry.type_id == SecondaryProjectileTypeId.ROCKET
                else _ROCKET_FORK_CHILD_DAMAGE_MULT_DEFAULT
            )
            child_owner = OwnerRef.from_creature(int(hit_idx))
            for offset in (-_ROCKET_FORK_SHOT_ANGLE_RAD, _ROCKET_FORK_SHOT_ANGLE_RAD):
                child_index = self.spawn_from_spec(
                    SecondarySpawnSpec(
                        pos=entry.pos,
                        angle=float(entry.angle) + offset,
                        type_id=entry.type_id,
                        owner=child_owner,
                        creatures=creatures,
                    ),
                )
                child = self._entries[child_index]
                child.fork_reserved = True
                # Not native: a fresh multiplier, not a re-roll/inherit of the
                # parent's own crit_mult - matches the bullet fork children's
                # "plain/uncritted" convention (weapon_runtime/fire.py).
                child.crit_mult = float(child_mult)

        def _maybe_rocket_explosive_payload_on_hit(entry: SecondaryProjectile) -> None:
            """Explosive Payload bonus (not native): an extra, separate
            detonation on a rocket's own hit - mirrors the bullet version
            (projectile_pool.py::_maybe_explosive_payload_on_hit, "doesn't
            matter if we get 2 explosions") instead of the earlier flat
            damage-multiplier version.

            Gated on explosive_payload_eligible (stamped at spawn), not a live
            read of the owning player's explosive_payload_timer - see that
            field's comment (types.py) for why a snapshotted freebie shot
            needs this, and Mini-Rocket Swarmers' one-rocket-per-volley rule.
            """

            if not entry.explosive_payload_eligible:
                return
            self.spawn_from_spec(
                SecondarySpawnSpec(
                    pos=entry.pos,
                    angle=0.0,
                    type_id=SecondaryProjectileTypeId.DETONATION,
                    owner=entry.owner,
                    time_to_live=_ROCKET_EXPLOSIVE_PAYLOAD_BLAST_SCALE,
                ),
            )
            if effects is not None:
                effects.spawn_explosion_burst(pos=entry.pos, scale=0.5, rng=rng, detail_preset=int(detail_preset))
            if runtime_state is not None:
                # Not native: half volume, same as the bullet version - this can
                # retrigger on every rocket hit while the powerup is active.
                runtime_state.sfx_queue_quiet.append(SfxId.EXPLOSION_MEDIUM)

        def _maybe_rocket_seeker_rounds_on_hit(entry: SecondaryProjectile) -> None:
            """Fire and Forget bonus (PerkId.SEEKER_ROUNDS, not native to rocket
            weapons): mirrors the bullet version (projectile_pool.py's inline
            hit-resolution block) - a private hit counter fires a free homing
            rocket every SEEKER_ROUNDS_HIT_THRESHOLD confirmed hits, deduped by
            shot_seq so Mini-Rocket Swarmers' whole volley counts as one shot.

            Unlike Fork Shot / Explosive Payload above, this checks the real
            owning player live, not a spawn-time snapshot - Seeker Rounds is a
            perk, not a timer-based powerup, and perks (unlike active powerup
            timers) are meant to carry over onto a Domino Effect/Momentum
            freebie shot (see creatures/runtime.py's _fire_momentum_shot).
            """

            owner_player_index = entry.owner.player_index_in_bounds(len(players))
            if owner_player_index is None:
                return
            shooter = players[owner_player_index]
            if not perk_active(shooter, PerkId.SEEKER_ROUNDS):
                return
            if entry.shot_seq < 0 or entry.shot_seq == shooter.seeker_rounds_last_shot_seq:
                return
            shooter.seeker_rounds_last_shot_seq = int(entry.shot_seq)
            shooter.seeker_rounds_hit_counter = int(shooter.seeker_rounds_hit_counter) + 1
            if shooter.seeker_rounds_hit_counter < SEEKER_ROUNDS_HIT_THRESHOLD:
                return
            shooter.seeker_rounds_hit_counter = 0
            # Not native: a Hollow Form clone shares its real player's index
            # (see OwnerRef.via_hollow_form's comment) - spawn from the
            # clone's frozen position instead of wherever the real player
            # currently is, when this hit came from the clone.
            spawn_pos = shooter.hollow_form_pos if entry.owner.via_hollow_form else shooter.pos
            bonus_index = self.spawn_from_spec(
                SecondarySpawnSpec(
                    pos=spawn_pos,
                    angle=0.0,
                    type_id=SecondaryProjectileTypeId.HOMING_ROCKET,
                    owner=entry.owner,
                    creatures=creatures,
                ),
            )
            self._entries[bonus_index].crit_mult = float(shooter.stats.perk_efficacy)

        def _rocket_on_direct_hit(entry: SecondaryProjectile, hit_idx: int) -> None:
            """Crit-reactive perks on a rocket's direct hit - mirrors the bullet
            version (projectile_pool.py's inline hit-resolution block). Only the
            creature struck directly is affected, never the detonation AoE."""

            owner_player_index = entry.owner.player_index_in_bounds(len(players))
            if owner_player_index is None:
                return
            shooter = players[owner_player_index]
            creature = creatures[int(hit_idx)]
            if entry.did_crit and perk_active(shooter, PerkId.COLD_SNAP):
                creature.crit_freeze_timer = COLD_SNAP_FREEZE_DURATION
            if creature.hp <= 0.0:
                return
            if entry.did_crit:
                harvester_scythe_on_crit(shooter)
                if shooter.overdue_window_timer <= 0.0:
                    shooter.overdue_streak = 0
            elif shooter.overdue_window_timer <= 0.0 and shooter.overdue_tick_cooldown_timer <= 0.0:
                shooter.overdue_streak = int(shooter.overdue_streak) + 1
                shooter.overdue_tick_cooldown_timer = OVERDUE_TICK_COOLDOWN

        def _creature_is_collidable(creature: CreatureState) -> bool:
            if not creature.active:
                return False
            return creature_lifecycle_is_collidable(creature.lifecycle_stage)

        creature_spatial = CreatureSpatialHash(creatures=creatures, is_collidable=_creature_is_collidable)
        hit_count = 0

        for entry in self._entries:
            if not entry.active:
                continue

            rule = secondary_rule_for_type_id(SecondaryProjectileTypeId(entry.type_id))

            if isinstance(rule, DetonationRule):
                if runtime_state is not None:
                    runtime_state.camera_shake_pulses = 4

                entry.detonation_t = x87_pc24_add(entry.detonation_t, x87_pc24_mul(dt, 3.0))
                entry.vel = Vec2(entry.detonation_t, entry.detonation_scale)
                t = float(entry.detonation_t)
                scale = float(entry.detonation_scale)
                if t > 1.0:
                    if fx_queue is not None:
                        fx_queue.add(
                            effect_id=int(EffectId.AURA),
                            pos=entry.pos,
                            width=float(scale) * 256.0,
                            height=float(scale) * 256.0,
                            rotation=0.0,
                            rgba=RGBA(0.0, 0.0, 0.0, 0.25),
                        )
                    entry.active = False

                radius = scale * t * 80.0
                radius_sq = radius * radius
                damage = x87_pc24_mul(dt, scale)
                damage = x87_pc24_mul(damage, 700.0)
                if entry.crit_mult != 1.0:
                    # Crit compensation/multiplier, stamped on the rocket when it was
                    # fired - carries through into its detonation AoE tick.
                    damage = x87_pc24_mul(damage, float(entry.crit_mult))
                for creature_idx in creature_spatial.candidate_indices(pos=entry.pos, radius=float(radius)):
                    creature = creatures[int(creature_idx)]
                    if not _creature_is_collidable(creature):
                        continue
                    if creature.hp <= 0.0:
                        continue
                    d_sq = Vec2.distance_sq(entry.pos, creature.pos)
                    if d_sq < radius_sq:
                        hp_before = float(creature.hp)
                        impulse_dir = (creature.pos - entry.pos).normalized()
                        impulse = Vec2(
                            f32(float(impulse_dir.x) * 0.1),
                            f32(float(impulse_dir.y) * 0.1),
                        )
                        _apply_secondary_damage(
                            creature_idx,
                            damage,
                            owner=entry.owner,
                            impulse=impulse,
                        )
                        creature_spatial.sync_index(int(creature_idx))
                        if hp_before > 0.0 and float(creature.hp) <= 0.0:
                            # Native detonation AoE does an extra two random decals and a
                            # second `creature_handle_death` call after the killing hit.
                            if fx_queue is not None:
                                fx_queue.add_random(pos=creature.pos, rng=rng)
                                fx_queue.add_random(pos=creature.pos, rng=rng)
                            creature_damage_runtime.on_secondary_detonation_kill(int(creature_idx))
                continue

            if not isinstance(rule, (RocketRule, HomingRocketRule, RocketMinigunRule)):
                continue

            # Move. Native keeps pos/vel as f32 fields: `pos += f32(dt * vel)`.
            entry.pos = Vec2(
                float(f32(float(entry.pos.x) + float(f32(float(dt) * float(entry.vel.x))))),
                float(f32(float(entry.pos.y) + float(f32(float(dt) * float(entry.vel.y))))),
            )

            # Update velocity + countdown.
            speed_mag = math.sqrt(float(entry.vel.x) * float(entry.vel.x) + float(entry.vel.y) * float(entry.vel.y))
            match rule:
                case (
                    RocketRule(
                        accel_factor_scale=accel_factor_scale,
                        speed_cap=speed_cap,
                        ttl_decay_scale=ttl_decay_scale,
                    )
                    | RocketMinigunRule(
                        accel_factor_scale=accel_factor_scale,
                        speed_cap=speed_cap,
                        ttl_decay_scale=ttl_decay_scale,
                    )
                ):
                    if speed_mag < float(speed_cap):
                        factor = float(f32(float(dt) * float(accel_factor_scale) + 1.0))
                        entry.vel = Vec2(
                            float(f32(factor * float(entry.vel.x))),
                            float(f32(factor * float(entry.vel.y))),
                        )
                    entry.speed = float(f32(float(entry.speed) - float(dt) * float(ttl_decay_scale)))
                case HomingRocketRule(
                    target_accel=target_accel,
                    max_velocity=max_velocity,
                    ttl_decay_scale=ttl_decay_scale,
                    velocity_damping=velocity_damping,
                ):
                    # Type 2: homing projectile.
                    target_id = entry.target_id
                    if not (0 <= target_id < len(creatures)) or not creatures[target_id].active:
                        entry.target_id = creature_find_nearest_alive(
                            creatures=creatures,
                            origin=entry.pos,
                        )
                        target_id = entry.target_id

                    if 0 <= target_id < len(creatures):
                        target = creatures[target_id]
                        # Native steering: angle = atan2(pos - target) kept in
                        # extended precision; the stored f32 angle is atan - pi/2.
                        # vel_x adds cos((atan - pi/2) - pi/2) from the extended
                        # angle; vel_y (and the over-cap subtraction for both
                        # components) recompute from the stored f32 angle, so the
                        # add-then-subtract is not an exact identity.
                        atan_ext = x87_fpatan(
                            x87_pc24_sub(entry.pos.y, target.pos.y),
                            x87_pc24_sub(entry.pos.x, target.pos.x),
                        )
                        entry.angle = x87_pc24_sub(atan_ext, NATIVE_HALF_PI)
                        heading_ext = x87_pc24_sub(
                            x87_pc24_sub(atan_ext, NATIVE_HALF_PI),
                            NATIVE_HALF_PI,
                        )
                        heading_stored = x87_pc24_sub(entry.angle, NATIVE_HALF_PI)
                        entry.vel = Vec2(
                            x87_pc24_add(
                                entry.vel.x,
                                x87_pc24_cos_mul(
                                    heading_ext,
                                    dt,
                                    target_accel,
                                ),
                            ),
                            x87_pc24_add(
                                entry.vel.y,
                                x87_pc24_sin_mul(
                                    heading_stored,
                                    dt,
                                    target_accel,
                                ),
                            ),
                        )
                        speed_after = math.sqrt(
                            float(entry.vel.x) * float(entry.vel.x) + float(entry.vel.y) * float(entry.vel.y),
                        )
                        if speed_after > float(max_velocity):
                            entry.vel = Vec2(
                                x87_pc24_sub(
                                    entry.vel.x,
                                    x87_pc24_cos_mul(
                                        heading_stored,
                                        dt,
                                        target_accel,
                                    ),
                                ),
                                x87_pc24_sub(
                                    entry.vel.y,
                                    x87_pc24_sin_mul(
                                        heading_stored,
                                        dt,
                                        target_accel,
                                    ),
                                ),
                            )

                        # Not native: see HomingRocketRule.velocity_damping - bleeds
                        # off the raw accelerate-toward-target velocity so an
                        # overshooting rocket settles onto the target instead of
                        # orbiting it forever.
                        if float(velocity_damping) > 0.0:
                            damping_factor = max(0.0, 1.0 - float(velocity_damping) * dt)
                            entry.vel = Vec2(
                                float(entry.vel.x) * damping_factor,
                                float(entry.vel.y) * damping_factor,
                            )

                    entry.speed = float(f32(float(entry.speed) - float(dt) * float(ttl_decay_scale)))

            # Rocket smoke trail (`trail_timer` in crimsonland.exe).
            trail_speed = x87_pc24_add(abs(entry.vel.x), abs(entry.vel.y))
            trail_decay = x87_pc24_mul(trail_speed, dt)
            trail_decay = x87_pc24_mul(trail_decay, 0.01)
            entry.trail_timer = x87_pc24_sub(entry.trail_timer, trail_decay)
            if float(entry.trail_timer) < 0.0:
                direction = Vec2.from_heading(entry.angle)
                spawn_pos = entry.pos - direction * 9.0
                # Native bug: both trail velocity components come from cosine
                # (fcos with no fsin), so the smoke drifts diagonally.
                trail_cos = math.cos(float(f32(entry.angle)) + NATIVE_HALF_PI)
                trail_velocity = Vec2(float(f32(trail_cos)) * 90.0, float(f32(trail_cos * 90.0)))
                if sprite_effects is not None:
                    sprite_effects.spawn(
                        pos=spawn_pos,
                        vel=trail_velocity,
                        scale=14.0,
                        color=RGBA(1.0, 1.0, 1.0, 0.25),
                    )
                entry.trail_timer = float(f32(0.06))

            # projectile_update uses creature_find_in_radius(..., 8.0, ...)
            hit_idx: int | None = None
            for idx in creature_spatial.candidate_indices(pos=entry.pos, radius=8.0):
                creature = creatures[int(idx)]
                if not _creature_is_collidable(creature):
                    continue
                if _within_native_find_radius(
                    origin=entry.pos,
                    target=creature.pos,
                    radius=8.0,
                    target_size=float(creature.size),
                ):
                    hit_idx = idx
                    break

            # Not native: needed once rockets could be owned by a creature
            # (Fork Shot's children below, re-owned to the struck creature so
            # they don't instantly "hit" it again on top of themselves) -
            # mirrors the bullet pool's own owner_collision discard.
            owner_creature_idx = entry.owner.creature_index_in_bounds(len(creatures))
            if hit_idx is not None and owner_creature_idx is not None and int(hit_idx) == owner_creature_idx:
                hit_idx = None

            if hit_idx is not None:
                hit_count += 1
                if runtime_state is not None:
                    owner_player_index = entry.owner.player_index_in_bounds(len(runtime_state.shots_hit))
                    if owner_player_index is not None and creature_lifecycle_is_alive(
                        creatures[int(hit_idx)].lifecycle_stage,
                    ):
                        shots_hit = runtime_state.shots_hit
                        shots_hit[owner_player_index] += 1

                if ctx.play_rocket_hit_audio is not None:
                    ctx.play_rocket_hit_audio()
                elif sfx_queue is not None:
                    sfx_queue.append(SfxId.EXPLOSION_MEDIUM)

                det_scale = 0.5
                damage_speed_mul = 0.0
                damage_base = 150.0
                burst_scale: float | None = None
                burst_min_detail = 0
                extra_decals = 0
                extra_radius = 0.0
                freeze_shard_target_pos = False
                match rule:
                    case RocketRule(
                        detonation_scale=detonation_scale,
                        damage_speed_mul=rule_damage_speed_mul,
                        damage_base=rule_damage_base,
                        burst_scale=rule_burst_scale,
                        burst_min_detail=rule_burst_min_detail,
                        extra_decals=rule_extra_decals,
                        extra_radius=rule_extra_radius,
                        freeze_shard_target_pos=rule_freeze_shard_target_pos,
                    ):
                        det_scale = float(detonation_scale)
                        damage_speed_mul = float(rule_damage_speed_mul)
                        damage_base = float(rule_damage_base)
                        burst_scale = None if rule_burst_scale is None else float(rule_burst_scale)
                        burst_min_detail = int(rule_burst_min_detail)
                        extra_decals = int(rule_extra_decals)
                        extra_radius = float(rule_extra_radius)
                        freeze_shard_target_pos = bool(rule_freeze_shard_target_pos)
                    case HomingRocketRule(
                        detonation_scale=detonation_scale,
                        damage_speed_mul=rule_damage_speed_mul,
                        damage_base=rule_damage_base,
                        extra_decals=rule_extra_decals,
                        extra_radius=rule_extra_radius,
                        freeze_shard_target_pos=rule_freeze_shard_target_pos,
                    ):
                        det_scale = float(detonation_scale)
                        damage_speed_mul = float(rule_damage_speed_mul)
                        damage_base = float(rule_damage_base)
                        extra_decals = int(rule_extra_decals)
                        extra_radius = float(rule_extra_radius)
                        freeze_shard_target_pos = bool(rule_freeze_shard_target_pos)
                    case RocketMinigunRule(
                        detonation_scale=detonation_scale,
                        damage_speed_mul=rule_damage_speed_mul,
                        damage_base=rule_damage_base,
                        extra_decals=rule_extra_decals,
                        extra_radius=rule_extra_radius,
                        freeze_shard_target_pos=rule_freeze_shard_target_pos,
                    ):
                        det_scale = float(detonation_scale)
                        damage_speed_mul = float(rule_damage_speed_mul)
                        damage_base = float(rule_damage_base)
                        extra_decals = int(rule_extra_decals)
                        extra_radius = float(rule_extra_radius)
                        freeze_shard_target_pos = bool(rule_freeze_shard_target_pos)

                if freeze_active:
                    if effects is not None:
                        for _ in range(4):
                            shard_angle = (
                                float(
                                    rng.rand_tagged(
                                RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_PRE_HIT_FREEZE_SHARD_ANGLE,
                                    )
                                    % 612,
                                )
                                * 0.01
                            )
                            effects.spawn_freeze_shard(
                                pos=entry.pos,
                                angle=shard_angle,
                                rng=rng,
                                detail_preset=int(detail_preset),
                            )
                elif fx_queue is not None:
                    for dx_caller, dy_caller in _SECONDARY_PRE_HIT_DECAL_CALLERS:
                        offset = Vec2(
                            float(rng.rand_tagged(dx_caller) % 20 - 10),
                            float(rng.rand_tagged(dy_caller) % 20 - 10),
                        )
                        fx_queue.add_random(
                            pos=creatures[hit_idx].pos + offset,
                            rng=rng,
                        )

                if burst_scale is not None and effects is not None and int(detail_preset) > int(burst_min_detail):
                    effects.spawn_explosion_burst(
                        pos=entry.pos,
                        scale=float(burst_scale),
                        rng=rng,
                        detail_preset=int(detail_preset),
                    )

                # Native `projectile_update` applies hit visuals before
                # `creature_apply_damage` for secondary projectiles.
                damage = x87_pc24_add(
                    x87_pc24_mul(entry.speed, float(damage_speed_mul)),
                    float(damage_base),
                )
                if entry.crit_mult != 1.0:
                    # Crit compensation/multiplier, stamped on the rocket when it was fired.
                    damage = x87_pc24_mul(damage, float(entry.crit_mult))
                inv_dt = f32(1.0 / float(dt))
                impulse = Vec2(
                    x87_pc24_mul(inv_dt, entry.vel.x),
                    x87_pc24_mul(inv_dt, entry.vel.y),
                )
                _rocket_on_direct_hit(entry, int(hit_idx))
                _apply_secondary_damage(
                    hit_idx,
                    damage,
                    owner=entry.owner,
                    impulse=impulse,
                    is_projectile_hit=True,
                )
                creature_spatial.sync_index(int(hit_idx))
                _maybe_rocket_fork_on_hit(entry, int(hit_idx))
                _maybe_rocket_explosive_payload_on_hit(entry)
                _maybe_rocket_seeker_rounds_on_hit(entry)
                # Not native: Pact of Gathering Winds relic - same direct-hit
                # scoping as Seeker Rounds above (a rocket's own splash damage
                # doesn't separately grant stacks, only the direct hit does).
                rocket_owner_idx = entry.owner.player_index_in_bounds(len(players))
                if rocket_owner_idx is not None:
                    relic_gathering_winds.gain_stack(players[rocket_owner_idx])

                entry.type_id = SecondaryProjectileTypeId.DETONATION
                entry.vel = Vec2(0.0, f32(det_scale))
                entry.detonation_t = 0.0
                entry.detonation_scale = f32(det_scale)

                # Extra debris/scorch decals (or freeze shards) on detonation.
                if freeze_active:
                    if effects is not None:
                        shard_pos = entry.pos
                        freeze_angle_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_FREEZE_SHARD_ANGLE
                        if isinstance(rule, HomingRocketRule):
                            freeze_angle_caller = (
                                RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_SEEKER_ROCKET_FREEZE_SHARD_ANGLE
                            )
                        elif isinstance(rule, RocketMinigunRule):
                            freeze_angle_caller = (
                                RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_MINIGUN_FREEZE_SHARD_ANGLE
                            )
                        if freeze_shard_target_pos:
                            shard_pos = creatures[hit_idx].pos
                        for _ in range(8):
                            shard_angle = float(rng.rand_tagged(freeze_angle_caller) % 612) * 0.01
                            effects.spawn_freeze_shard(
                                pos=shard_pos,
                                angle=shard_angle,
                                rng=rng,
                                detail_preset=int(detail_preset),
                            )
                else:
                    if fx_queue is not None and extra_decals > 0:
                        center = creatures[hit_idx].pos
                        angle_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_DECAL_ANGLE
                        radius_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_DECAL_RADIUS
                        if isinstance(rule, HomingRocketRule):
                            angle_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_SEEKER_ROCKET_DECAL_ANGLE
                            radius_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_SEEKER_ROCKET_DECAL_RADIUS
                        elif isinstance(rule, RocketMinigunRule):
                            angle_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_MINIGUN_DECAL_ANGLE
                            radius_caller = RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_ROCKET_MINIGUN_DECAL_RADIUS
                        for _ in range(int(extra_decals)):
                            angle = float(rng.rand_tagged(angle_caller) % 628) * 0.01
                            if isinstance(rule, HomingRocketRule):
                                radius = float(rng.rand_tagged(radius_caller) & 0x3F)
                            else:
                                radius = float(rng.rand_tagged(radius_caller) % max(1, int(extra_radius)))
                            fx_queue.add_random(
                                pos=center + Vec2.from_angle(angle) * radius,
                                rng=rng,
                            )

                if sprite_effects is not None:
                    step = math.tau / 10.0
                    for idx in range(10):
                        mag = (
                            float(
                                rng.rand_tagged(RngCallerStatic.SECONDARY_PROJECTILE_UPDATE_DETONATION_SPRITE_MAG)
                                % 800,
                            )
                            * 0.1
                        )
                        ang = float(idx) * step
                        velocity = Vec2.from_angle(ang) * mag
                        sprite_effects.spawn(
                            pos=entry.pos,
                            vel=velocity,
                            scale=14.0,
                            color=RGBA(1.0, 1.0, 1.0, 0.37),
                        )

            # Native's TTL check runs after the hit handling in the same
            # iteration (no early-out): a rocket that hits while its TTL is
            # already spent gets its detonation scale overwritten to 0.5, and
            # exactly-zero TTL detonates this tick (<=, not <).
            if entry.speed <= 0.0:
                entry.type_id = SecondaryProjectileTypeId.DETONATION
                entry.vel = Vec2(0.0, 0.5)
                entry.detonation_t = 0.0
                entry.detonation_scale = 0.5
        return hit_count
