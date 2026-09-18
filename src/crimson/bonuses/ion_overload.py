from __future__ import annotations

"""Ion Overload bonus - an original addition, not present in the native game.

Unlike Fire Bullets/Plasma Overload, this one doesn't touch the player's own
shooting at all. Picking it up starts a 5-second charge (`ion_overload.
charge_timer`); picking up another while it's still charging extends the
timer, same stacking as every other timed bonus. `charge_seconds` tracks the
total charge time separately - it only ever grows, and is read once
`charge_timer` finally counts down to zero.

At that instant a single real ION_CANNON-type bolt is fired straight out of
the player, aimed at their current heading - `fire_ion_overload_bolt` below -
carrying the total charge on `Projectile.ion_overload_charge`. It behaves
like a normal Ion Cannon shot (own direct-hit damage, own travel) until it
hits something: `_maybe_ion_overload_on_hit` (projectiles/runtime/
projectile_pool.py) then blooms a stationary nova at the hit position instead
of falling through to the real Ion Cannon's own fixed 128px/300dps linger.

The nova's damage reuses the real Ion mechanic's own shape (a flat-dps radius
tick, `CreatureDamageType.ION` - not the rocket/explosion DETONATION path),
but as a standalone timed entity per player (`state_types.py::
IonOverloadState`, `update_ion_overload_clouds` below) rather than the
Projectile pool's own linger dispatch, since that only supports lingering for
a fraction of a second and this can run past that at high charge. Its visual
is a dedicated ring spawned once in `bloom_ion_overload_nova`, sized and
timed to the *actual* radius/duration - the native ion-hit ring (fixed
~148px/~0.8s, calibrated for the real Ion Cannon's own linger) is far too
small/short for this and isn't reused.

Numbers, calibrated at the 5-second baseline charge, scaling linearly with
total charge time beyond it (radius, dps, and duration all scale together,
so total damage grows with the *square* of the charge ratio):

    scale    = charge / ION_OVERLOAD_BASE_CHARGE_SECONDS
    radius   = ION_OVERLOAD_BASE_RADIUS   * scale   (350px at baseline)
    duration = ION_OVERLOAD_BASE_DURATION * scale   (1s at baseline)
    dps      = ION_OVERLOAD_BASE_DPS      * scale   (1500 at baseline)
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from grim.color import RGBA
from grim.geom import Vec2

from ..creatures.damage_types import CreatureDamageType
from ..creatures.lifecycle import creature_lifecycle_is_collidable
from ..effects_atlas import EffectId
from ..math_parity import f32, native_fire_muzzle_pos
from ..owner_ref import OwnerRef
from ..projectiles.types import ProjectileTemplateId
from ..sim.state_types import GameplayState, PlayerState
from ..weapon_runtime.spawn import owner_ref_for_player_projectiles, travel_budget_for_type_id
from ..weapon_runtime.tenet_gun_spawn import tenet_reverse_spawn_params
from ..weapons import WeaponId, weapon_entry_for_projectile_type_id
from .apply_context import BonusApplyCtx, bonus_apply_seconds

if TYPE_CHECKING:
    from ..creatures.damage_runtime import CreatureDamageRuntime
    from ..creatures.runtime import CreatureState
    from ..effects import EffectPool

# Same light-blue ion identity color as the native ion-hit VFX
# (projectiles/effects.py::_spawn_ion_hit_effects), so this reads as "ion",
# not an explosion.
_ION_OVERLOAD_CLOUD_COLOR = RGBA(0.6, 0.6, 0.9, 1.0)

ION_OVERLOAD_BASE_CHARGE_SECONDS = 5.0
ION_OVERLOAD_BASE_RADIUS = 350.0
ION_OVERLOAD_BASE_DURATION = 1.0
ION_OVERLOAD_BASE_DPS = 1500.0


def apply_ion_overload(ctx: BonusApplyCtx) -> None:
    overload = ctx.player.ion_overload
    should_register = float(overload.charge_timer) <= 0.0
    if len(ctx.players) > 1:
        should_register = (
            float(ctx.players[0].ion_overload.charge_timer) <= 0.0
            and float(ctx.players[1].ion_overload.charge_timer) <= 0.0
        )
    if should_register:
        ctx.register_player("ion_overload_charge_timer")
    added = bonus_apply_seconds(ctx) * float(ctx.economist_multiplier)
    overload.charge_timer = float(f32(float(overload.charge_timer) + added))
    overload.charge_seconds = float(f32(float(overload.charge_seconds) + added))


def ion_overload_scale(charge_seconds: float) -> float:
    """1.0 at the baseline charge, linear beyond (and below) it."""

    return float(charge_seconds) / ION_OVERLOAD_BASE_CHARGE_SECONDS


def fire_ion_overload_bolt(state: GameplayState, player: PlayerState) -> None:
    """Called once, the exact frame `charge_timer` crosses to zero."""

    overload = player.ion_overload
    charge_seconds = float(overload.charge_seconds)
    overload.charge_seconds = 0.0
    if charge_seconds <= 0.0:
        return

    muzzle = native_fire_muzzle_pos(player.pos, float(player.aim_heading))
    spawn_pos, spawn_angle = muzzle, float(player.aim_heading)
    tenet_reverse = int(player.weapon.weapon_id) == int(WeaponId.TENET_GUN)
    if tenet_reverse:
        # See weapon_runtime/spawn.py::projectile_spawn's Tenet Gun check -
        # this bolt fires on its own via `state.projectiles.spawn` directly
        # instead of through that chokepoint, so it needs the same treatment
        # applied by hand.
        spawn_pos, spawn_angle = tenet_reverse_spawn_params(
            origin=muzzle,
            muzzle=muzzle,
            aim=player.aim,
            angle=float(player.aim_heading),
        )
    proj_id = state.projectiles.spawn(
        pos=spawn_pos,
        angle=spawn_angle,
        type_id=ProjectileTemplateId.ION_CANNON,
        owner=owner_ref_for_player_projectiles(state, player.index),
        travel_budget=travel_budget_for_type_id(ProjectileTemplateId.ION_CANNON),
        hits_players=bool(state.friendly_fire_enabled),
    )
    state.projectiles.entries[proj_id].ion_overload_charge = charge_seconds
    if tenet_reverse:
        state.projectiles.entries[proj_id].tenet_reverse = True
    # This bolt fires on its own (the charge timer expiring, not a trigger
    # pull), so it doesn't go through the normal per-shot sfx dispatch
    # (audio_router.py / sim/presentation_step.py) - queue the Ion Cannon's
    # own fire sound directly.
    state.sfx_queue.append(weapon_entry_for_projectile_type_id(ProjectileTemplateId.ION_CANNON).fire_sound)


def bloom_ion_overload_nova(
    player: PlayerState,
    pos: Vec2,
    charge_seconds: float,
    *,
    effects: EffectPool | None = None,
    detail_preset: int = 5,
) -> None:
    """Called from the bolt's on-hit hook - drops the scaled nova at `pos`."""

    if charge_seconds <= 0.0:
        return
    scale = ion_overload_scale(charge_seconds)
    radius = ION_OVERLOAD_BASE_RADIUS * scale
    duration = ION_OVERLOAD_BASE_DURATION * scale
    dps = ION_OVERLOAD_BASE_DPS * scale
    overload = player.ion_overload
    overload.cloud_radius = radius
    overload.cloud_timer = duration
    overload.cloud_dps = dps
    overload.cloud_pos = pos

    if effects is None:
        return
    # Spawn already at its real radius/duration (no growth animation, just a
    # steady field that fades near the end) - the native ion-hit ring is
    # calibrated for its own tiny fixed radius, not this bonus's much bigger,
    # longer-lived nova, so it can't be reused here.
    effects.spawn(
        effect_id=int(EffectId.RING),
        pos=pos,
        vel=Vec2(),
        rotation=0.0,
        scale=1.0,
        half_width=radius,
        half_height=radius,
        age=0.0,
        lifetime=duration,
        flags=0x10,  # fade alpha over lifetime; no rotate/scale-grow/decal
        color=_ION_OVERLOAD_CLOUD_COLOR,
        rotation_step=0.0,
        scale_step=0.0,
        detail_preset=int(detail_preset),
    )


def update_ion_overload_clouds(
    players: list[PlayerState],
    creatures: Sequence[CreatureState],
    dt: float,
    *,
    creature_damage_runtime: CreatureDamageRuntime | None,
) -> None:
    """Advance every active ion-overload nova and apply its tick damage. Not native."""

    dt = float(dt)
    if dt <= 0.0:
        return

    for player in players:
        overload = player.ion_overload
        if overload.cloud_timer <= 0.0:
            continue

        overload.cloud_timer = float(f32(float(overload.cloud_timer) - dt))
        if overload.cloud_timer <= 0.0:
            overload.cloud_timer = 0.0
            overload.cloud_radius = 0.0
            overload.cloud_dps = 0.0
            continue

        if creature_damage_runtime is None or not creatures:
            continue

        damage = float(f32(dt * float(overload.cloud_dps)))
        radius = float(overload.cloud_radius)
        radius_sq = radius * radius
        owner = OwnerRef.from_local_player(int(player.index))
        for idx, creature in enumerate(creatures):
            if not creature.active or float(creature.hp) <= 0.0:
                continue
            if not creature_lifecycle_is_collidable(creature.lifecycle_stage):
                continue
            dx = float(creature.pos.x) - float(overload.cloud_pos.x)
            dy = float(creature.pos.y) - float(overload.cloud_pos.y)
            if dx * dx + dy * dy > radius_sq:
                continue
            creature_damage_runtime.apply_creature_damage(
                idx,
                damage,
                int(CreatureDamageType.ION),
                Vec2(),
                owner,
            )
