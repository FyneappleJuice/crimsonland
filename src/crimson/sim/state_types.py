from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

from ..bonuses.ids import BonusId
from ..math_parity import f32
from ..progression.stats import PlayerStats
from ..run_mods.ids import RUN_MOD_COUNT_SIZE
from ..weapons import WeaponId

PERK_COUNT_SIZE = 0x80


class WeaponSlot(msgspec.Struct):
    weapon_id: WeaponId
    clip_size: int = 0
    ammo: float = 0.0
    reload_active: bool = False
    reload_timer: float = 0.0
    reload_timer_max: float = 0.0
    shot_cooldown: float = 0.0


class BladeOrbitState(msgspec.Struct):
    """Not native: backs the "Blade" bonus (bonuses/blade_orbit.py).

    `elapsed` runs 0 -> BLADE_DURATION_S; `theta0` / `phi0` are the random
    start phases; `hit_cooldowns` maps a creature index to the seconds left
    before a blade may hit it again.
    """

    active: bool = False
    elapsed: float = 0.0
    theta0: float = 0.0
    phi0: float = 0.0
    hit_cooldowns: dict[int, float] = msgspec.field(default_factory=dict)


class IonOverloadState(msgspec.Struct):
    """Not native: backs the "Ion Overload" bonus (bonuses/ion_overload.py).

    `charge_timer` counts down from each pickup's contribution (repeat
    pickups while charging extend it, same stacking as the other timers);
    `charge_seconds` only ever accumulates and is read once `charge_timer`
    reaches zero, at which point a stationary ion nova is dropped at
    `cloud_pos` sized from the total charge (`cloud_radius`/`cloud_dps`/
    `cloud_timer`), then `charge_seconds` resets to 0.0 for the next charge
    cycle.
    """

    charge_timer: float = 0.0
    charge_seconds: float = 0.0
    cloud_timer: float = 0.0
    cloud_radius: float = 0.0
    cloud_dps: float = 0.0
    cloud_pos: Vec2 = Vec2()


class ScytheSwingState(msgspec.Struct):
    """Not native: backs the Evil Scythe melee sweep (weapon_runtime/scythe_sweep.py).

    A swing runs `elapsed` 0 -> SCYTHE_SWING_DURATION_S. `base_angle` is the
    world-space aim angle captured when the swing started; `direction` is +1 for
    a left->right sweep and -1 for right->left. `hit` holds the creature indices
    already struck by this swing. `prev_angle` is last tick's blade bearing, so
    a fast sweep never skips a creature between ticks.
    """

    active: bool = False
    elapsed: float = 0.0
    base_angle: float = 0.0
    direction: float = 1.0
    prev_angle: float = 0.0
    hit: list[int] = msgspec.field(default_factory=list)
    # Effective geometry / damage for this swing, resolved at start (Weapon
    # Power Up widens and hardens the sweep). 0.0 means "use the base constant".
    arc: float = 0.0
    reach: float = 0.0
    damage: float = 0.0


class ArcGunState(msgspec.Struct):
    """Not native: backs the Arc Gun chain-lightning weapon (weapon_runtime/arc_gun.py).

    ``pending`` is set by the fire path and consumed by the world-step updater,
    which picks the targets, applies the chain damage and freezes the bolt path
    into ``chain`` (a flat ``[x0, y0, x1, y1, ...]`` list of world points, first
    point = the muzzle) for ``bolt_timer`` seconds of rendering. ``seed`` bumps
    each strike so the VFX jitter re-rolls.
    """

    pending: bool = False
    aim_x: float = 0.0
    aim_y: float = 0.0
    weapon_power_up: bool = False
    bolt_timer: float = 0.0
    chain: list[float] = msgspec.field(default_factory=list)
    seed: int = 0
    # Rewrite-only: outgoing crit multiplier stamped when the strike is fired
    # (weapon_runtime/crit.py), consumed by update_arc_gun for every hop.
    crit_mult: float = 1.0


class PlayerState(msgspec.Struct):
    index: int
    pos: Vec2
    health: float = 100.0
    size: float = 48.0

    speed_multiplier: float = 2.0
    move_speed: float = 0.0
    move_phase: float = 0.0
    heading: float = 0.0
    turn_speed: float = 1.0
    death_timer: float = 16.0
    low_health_timer: float = 100.0

    aim: Vec2 = Vec2()
    aim_heading: float = 0.0
    aim_dir: Vec2 = Vec2(1.0, 0.0)
    evil_eyes_target_creature: int = -1
    auto_target: int = -1

    bonus_aim_hover_index: int = -1
    bonus_aim_hover_timer_ms: float = 0.0

    weapon: WeaponSlot = msgspec.field(default_factory=lambda: WeaponSlot(weapon_id=WeaponId.PISTOL))
    alt_weapon: WeaponSlot | None = None

    shot_seq: int = 0
    weapon_reset_latch: int = 0
    aux_timer: float = 0.0
    spread_heat: float = f32(0.01)
    muzzle_flash_alpha: float = 0.0

    experience: int = 0
    level: int = 1

    perk_counts: list[int] = msgspec.field(default_factory=lambda: [0] * PERK_COUNT_SIZE)
    # Not native: how many times each run mod (crimson.run_mods) has been
    # picked this run - a separate, per-run-only pool from perks and from the
    # persistent crimson.meta.relics grid. Sized to len(RunModId) exactly.
    run_mod_counts: list[int] = msgspec.field(default_factory=lambda: [0] * RUN_MOD_COUNT_SIZE)
    # Not native: a separate negative-direction stack, fed only by Wildcard's
    # "upgrade" outcome (run_mods/selection.py) - each entry here applies that
    # run mod's own StatMods inverted (worse), independent of - and additive
    # with - any normal positive stacks of the same id in run_mod_counts.
    run_mod_penalty_counts: list[int] = msgspec.field(default_factory=lambda: [0] * RUN_MOD_COUNT_SIZE)
    # Not native: resolved build stats (crimson.progression). Recomputed each
    # sim tick from perks + affixes + modifiers; all-default until content
    # registers StatMods, so native runs are unaffected.
    stats: PlayerStats = msgspec.field(default_factory=PlayerStats)
    plaguebearer_active: bool = False
    hot_tempered_timer: float = 0.0
    man_bomb_timer: float = 0.0
    living_fortress_timer: float = 0.0
    fire_cough_timer: float = 0.0

    # Rewrite-only: Overdue's consecutive-non-crit counter (weapon_runtime/fire.py)
    # and the bonus-damage window it opens once the streak hits threshold.
    overdue_streak: int = 0
    overdue_window_timer: float = 0.0
    # Internal cooldown on the streak counter itself (projectiles/runtime/
    # projectile_pool.py's OVERDUE_TICK_COOLDOWN) - without this, a weapon
    # firing many rolls/sec (Minigun/Shotgun) completes the streak almost
    # instantly regardless of threshold, trivializing the perk for fast
    # weapons while slow weapons (Cannon) still struggle.
    overdue_tick_cooldown_timer: float = 0.0

    # Rewrite-only: Seeker Rounds - counts confirmed *shots* landed (not
    # individual hit instances - a shotgun's pellets or one piercing round's
    # multiple hits all count once, deduped via seeker_rounds_last_shot_seq
    # against Projectile.shot_seq), persisting across reloads; fires a free
    # homing rocket and resets once it reaches SEEKER_ROUNDS_HIT_THRESHOLD
    # (projectiles/runtime/projectile_pool.py).
    seeker_rounds_hit_counter: int = 0
    seeker_rounds_last_shot_seq: int = -1

    # Rewrite-only: Kinetic Discipline - continuous ramp (0-1) that builds while
    # moving in a sustained, roughly-straight line and decays otherwise.
    kinetic_charge: float = 0.0
    kinetic_prev_heading: float = 0.0

    # Rewrite-only: Adrenaline Rush's bonus-damage window, opened whenever the
    # player actually loses health (weapon_runtime/../player_damage.py).
    adrenaline_rush_window_timer: float = 0.0

    # Rewrite-only: Pendulum - flips each time a reload completes (natural or
    # forced). False = damage phase, True = fire-rate phase. The snapshot
    # field freezes whichever phase was active when a Fire Bullets / Weapon
    # Power Up bonus was granted, for that bonus's whole duration.
    pendulum_phase: bool = False
    pendulum_snapshot_phase: bool = False

    # Rewrite-only: Bane of Legends - counts down from 5.0 after a kill; the
    # +30% bonus is active while this is > 0 (creatures/runtime.py sets it).
    bane_of_legends_timer: float = 0.0

    # Rewrite-only: Harvester's Scythe - counts down from
    # HARVESTER_SCYTHE_FLASH_DURATION on every crit heal; purely a visual cue
    # (render/world/player_status.py flashes the health ring green while > 0),
    # no gameplay effect.
    harvester_scythe_flash_timer: float = 0.0

    # Rewrite-only: Soul Tether - overheal-turned-shield. Absorbed before HP
    # in player_damage.py; degenerates 5s after last gaining any shield.
    soul_tether_shield: float = 0.0
    soul_tether_decay_delay_timer: float = 0.0

    # Rewrite-only: Hollow Form - hollow_form_timer counts down to the next
    # clone spawn. When it fires, hollow_form_snapshot holds a frozen copy of
    # the player (weapon, perks, active powerup timers) that stands at
    # hollow_form_pos and fires on its own for hollow_form_active_timer
    # seconds (perks/impl/hollow_form.py), then the snapshot is cleared.
    hollow_form_timer: float = 0.0
    hollow_form_active_timer: float = 0.0
    hollow_form_snapshot: PlayerState | None = None
    hollow_form_pos: Vec2 = Vec2()

    # Rewrite-only: The Hit List - permanent damage bonus, +HIT_LIST_BONUS_PER_KILL
    # per marked-Apex kill, capped at HIT_LIST_MAX_BONUS (perks/impl/hit_list.py,
    # creatures/runtime.py's death handler).
    hit_list_bonus: float = 0.0

    speed_bonus_timer: float = 0.0
    shield_timer: float = 0.0
    fire_bullets_timer: float = 0.0
    # Not native: backs the "Fork Shot" bonus (bonuses/projectile_fork.py).
    projectile_fork_timer: float = 0.0
    # Not native: backs the "Explosive Payload" bonus (bonuses/explosive_payload.py).
    explosive_payload_timer: float = 0.0
    # Not native: backs the "Plasma Overload" bonus (bonuses/plasma_overload.py).
    plasma_overload_timer: float = 0.0
    # Not native: backs the "Blade" bonus (bonuses/blade_orbit.py).
    blade_orbit: BladeOrbitState = msgspec.field(default_factory=BladeOrbitState)
    # Not native: backs the "Ion Overload" bonus (bonuses/ion_overload.py).
    ion_overload: IonOverloadState = msgspec.field(default_factory=IonOverloadState)
    # Not native: backs the Evil Scythe melee sweep (weapon_runtime/scythe_sweep.py).
    scythe_swing: ScytheSwingState = msgspec.field(default_factory=ScytheSwingState)
    # Not native: backs the Arc Gun chain lightning (weapon_runtime/arc_gun.py).
    arc_gun: ArcGunState = msgspec.field(default_factory=ArcGunState)


class BonusPickupEvent(msgspec.Struct, frozen=True):
    player_index: int
    bonus_id: BonusId
    amount: int
    pos: Vec2


if TYPE_CHECKING:
    from ..gameplay import GameplayState
else:
    type GameplayState = object
