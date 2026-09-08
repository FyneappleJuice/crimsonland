from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

from ..bonuses.ids import BonusId
from ..math_parity import f32
from ..progression.stats import PlayerStats
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
    # Seconds the gun has been firing without a break - drives the looping crackle.
    sound_elapsed: float = 0.0


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
    # Not native: resolved build stats (crimson.progression). Recomputed each
    # sim tick from perks + affixes + modifiers; all-default until content
    # registers StatMods, so native runs are unaffected.
    stats: PlayerStats = msgspec.field(default_factory=PlayerStats)
    plaguebearer_active: bool = False
    hot_tempered_timer: float = 0.0
    man_bomb_timer: float = 0.0
    living_fortress_timer: float = 0.0
    fire_cough_timer: float = 0.0

    speed_bonus_timer: float = 0.0
    shield_timer: float = 0.0
    fire_bullets_timer: float = 0.0
    # Not native: backs the "Fork Shot" bonus (bonuses/projectile_fork.py).
    projectile_fork_timer: float = 0.0
    # Not native: backs the "Blade" bonus (bonuses/blade_orbit.py).
    blade_orbit: BladeOrbitState = msgspec.field(default_factory=BladeOrbitState)
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
