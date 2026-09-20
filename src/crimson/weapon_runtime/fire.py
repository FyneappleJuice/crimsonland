from __future__ import annotations

import math
import random as _random
from collections.abc import Sequence
from typing import TYPE_CHECKING

import msgspec

from grim.color import RGBA
from grim.geom import Vec2
from grim.rand import CrandLike

from ..math_parity import (
    NATIVE_HALF_PI,
    NATIVE_PI,
    f32,
    native_fire_muzzle_pos,
    native_shot_angle_from_jitter_draws,
    x87_pc24_add,
    x87_pc24_mul,
    x87_pc24_sub,
)
from ..perks import PerkId
from ..perks.helpers import perk_active
from ..progression import refresh_player_stats
from ..player_damage import PlayerDeathRuntime
from ..projectiles.runtime import SecondarySpawnSpec
from ..projectiles.types import ProjectileTemplateId, SecondaryProjectileTypeId
from ..rng_caller_static import RngCallerStatic
from ..sim.input import PlayerInput
from ..sim.state_types import GameplayState, PlayerState
from ..weapons import WEAPON_TABLE, WeaponId, weapon_entry_for_projectile_type_id
from .assign import player_start_reload, weapon_entry
from .crit import roll_crit_mult, roll_primary_crit
from .fire_recipes import (
    ArcStrikeMode,
    MaskCenteredJitter,
    MeleeSweepMode,
    ModuloCenteredJitter,
    ModuloSpeedScale,
    MultiPlasmaFanMode,
    NoJitter,
    NoSpeedScale,
    ParticleStreamMode,
    PlasmaOverloadMode,
    PrimaryPelletsMode,
    SecondaryShotMode,
    SwarmerDumpMode,
    UseAimTargetHint,
    resolve_fire_recipe,
)
from .plasma_heat import is_plasma_heat_weapon, plasma_energy_heat_mult
from .spawn import owner_ref_for_player, owner_ref_for_player_projectiles, travel_budget_for_type_id
from .tenet_gun_spawn import tenet_reverse_spawn_params

if TYPE_CHECKING:
    from ..creatures.runtime import CreatureState

WEAPON_COUNT_SIZE = max(int(entry.weapon_id) for entry in WEAPON_TABLE) + 1

# Rewrite-only: Death Wish / Overdue tuning (health is a 0-100 value).
DEATH_WISH_HEALTH_THRESHOLD = 15.0
OVERDUE_STREAK_THRESHOLD = 5
OVERDUE_WINDOW_DURATION = 5.0  # seconds the bonus stays up once the streak triggers it
OVERDUE_BONUS_CRIT_MULT = 1.0  # added to CRIT_MULTIPLIER on every crit during the window

# Rewrite-only: Free Rounds - a private per-shot roll (build variance, not run
# state, same reasoning as crit.py's own private RNG) for skipping this shot's
# ammo cost entirely.
FREE_ROUNDS_CHANCE = 0.15
_FREE_ROUNDS_RNG = _random.Random(0xF6EED5)

# Not native: Plasma Overload bonus (bonuses/plasma_overload.py) - twin bolts
# fired side-by-side on the same heading, `_PLASMA_OVERLOAD_LATERAL_SPACING`
# px apart, instead of a fan.
_PLASMA_OVERLOAD_BOLT_COUNT = 2
_PLASMA_OVERLOAD_LATERAL_SPACING = 10.0
# A bit faster than the Assault Rifle's own 0.117s this was originally pinned
# to.
_PLASMA_OVERLOAD_COOLDOWN = 0.1
# Tighter than any real weapon's own spread_heat_inc (Assault Rifle's 0.09 is
# among the lowest) so sustained fire stays accurate instead of drifting wide.
_PLASMA_OVERLOAD_SPREAD_HEAT = 0.05

_NATIVE_FIRE_MUZZLE_SPRITES: dict[int, tuple[tuple[float, float, float], ...]] = {
    WeaponId.PISTOL: ((25.0, 1.0, 0.23), (15.0, 2.0, 0.213)),
    # Rewrite-only: Tenet Gun is mechanically a Pistol clone - same muzzle fx.
    WeaponId.TENET_GUN: ((25.0, 1.0, 0.23), (15.0, 2.0, 0.213)),
    WeaponId.ASSAULT_RIFLE: ((25.0, 1.0, 0.23), (15.0, 2.0, 0.213)),
    WeaponId.SHOTGUN: ((25.0, 1.0, 0.25), (15.0, 2.0, 0.223)),
    WeaponId.SAWED_OFF_SHOTGUN: ((25.0, 1.0, 0.26), (15.0, 2.0, 0.233)),
    WeaponId.SUBMACHINE_GUN: ((25.0, 1.0, 0.23), (15.0, 2.0, 0.213)),
    WeaponId.GAUSS_GUN: ((25.0, 1.0, 0.33), (15.0, 2.0, 0.263)),
    WeaponId.ROCKET_LAUNCHER: ((25.0, 1.0, 0.34), (15.0, 2.0, 0.283)),
    WeaponId.SEEKER_ROCKETS: ((25.0, 1.0, 0.31), (15.0, 2.0, 0.243)),
    WeaponId.MINI_ROCKET_SWARMERS: ((25.0, 1.0, 0.34), (15.0, 2.0, 0.283)),
    WeaponId.ROCKET_MINIGUN: ((25.0, 1.0, 0.34),),
    WeaponId.JACKHAMMER: ((15.0, 2.0, 0.223),),
    WeaponId.SHRINKIFIER_5K: ((25.0, 1.0, 0.23), (15.0, 2.0, 0.213)),
    WeaponId.GAUSS_SHOTGUN: ((25.0, 1.0, 0.33), (15.0, 2.0, 0.263)),
}

_NATIVE_FIRE_MUZZLE_AFTER_PROJECTILE: frozenset[int] = frozenset(
    {
        WeaponId.PISTOL,
        WeaponId.SHRINKIFIER_5K,
        WeaponId.TENET_GUN,
    },
)

_PELLET_JITTER_CALLER_BY_WEAPON: dict[WeaponId, int] = {
    WeaponId.SHOTGUN: RngCallerStatic.PLAYER_UPDATE_SHOTGUN_PELLET_JITTER,
    WeaponId.SAWED_OFF_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_SAWED_OFF_SHOTGUN_PELLET_JITTER,
    WeaponId.JACKHAMMER: RngCallerStatic.PLAYER_UPDATE_JACKHAMMER_PELLET_JITTER,
    WeaponId.ION_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_ION_SHOTGUN_PELLET_JITTER,
    WeaponId.GAUSS_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_GAUSS_SHOTGUN_PELLET_JITTER,
    WeaponId.PLASMA_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_PLASMA_SHOTGUN_PELLET_JITTER,
}

_PELLET_SPEED_SCALE_CALLER_BY_WEAPON: dict[WeaponId, int] = {
    WeaponId.SHOTGUN: RngCallerStatic.PLAYER_UPDATE_SHOTGUN_PELLET_SPEED_SCALE,
    WeaponId.SAWED_OFF_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_SAWED_OFF_SHOTGUN_PELLET_SPEED_SCALE,
    WeaponId.JACKHAMMER: RngCallerStatic.PLAYER_UPDATE_JACKHAMMER_PELLET_SPEED_SCALE,
    WeaponId.ION_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_ION_SHOTGUN_PELLET_SPEED_SCALE,
    WeaponId.GAUSS_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_GAUSS_SHOTGUN_PELLET_SPEED_SCALE,
    WeaponId.PLASMA_SHOTGUN: RngCallerStatic.PLAYER_UPDATE_PLASMA_SHOTGUN_PELLET_SPEED_SCALE,
}


class WeaponFireCtx(msgspec.Struct):
    player: PlayerState
    input_state: PlayerInput
    dt: float
    state: GameplayState
    detail_preset: int = 5
    creatures: Sequence[CreatureState] | None = None
    players: Sequence[PlayerState] | None = None
    force_pre_swap_fire_gate: bool = False
    player_death_runtime: PlayerDeathRuntime | None = None


class WeaponFireResult(msgspec.Struct, frozen=True):
    fired: bool
    shot_count: int = 0
    ammo_cost: float = 0.0


def _spawn_native_fire_muzzle_sprites(
    *,
    state: GameplayState,
    weapon_id: int,
    muzzle: Vec2,
    aim_heading: float,
    fire_bullets_active: bool,
) -> None:
    if fire_bullets_active:
        specs: tuple[tuple[float, float, float], ...] = ((25.0, 1.0, 0.413),)
    else:
        specs = _NATIVE_FIRE_MUZZLE_SPRITES.get(int(weapon_id), ())
    if not specs:
        return

    for speed, scale, alpha in specs:
        # Native uses raw (cos h, sin h) of the aim heading - the aim direction
        # rotated 90 degrees - matching the Fire Cough and shell-casing ports.
        state.sprite_effects.spawn(
            pos=muzzle,
            vel=Vec2.from_angle(aim_heading) * float(speed),
            scale=float(scale),
            color=RGBA(0.5, 0.5, 0.5, float(alpha)),
        )


def _native_shot_angle_with_jitter(
    *,
    aim: Vec2,
    player_pos: Vec2,
    spread_heat: float,
    rng: CrandLike,
) -> float:
    # Native gameplay fire owns two exact `player_update` draw sites for the
    # disc-spread direction and magnitude before the later projectile work.
    dir_draw = rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_SHOT_JITTER_DIR)
    mag_draw = rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_SHOT_JITTER_MAG)
    return native_shot_angle_from_jitter_draws(
        aim=aim,
        player_pos=player_pos,
        spread_heat=spread_heat,
        dir_draw=dir_draw,
        mag_draw=mag_draw,
    )


def _apply_pellet_jitter(
    *,
    shot_angle: float,
    rng: CrandLike,
    jitter_rule: ModuloCenteredJitter | MaskCenteredJitter,
    caller: int,
) -> float:
    match jitter_rule:
        case ModuloCenteredJitter(modulo=modulo, center=center, step=step):
            return float(shot_angle) + float(
                rng.rand_tagged(caller) % int(modulo) - int(center),
            ) * float(step)
        case MaskCenteredJitter(mask=mask, center=center, step=step):
            return float(shot_angle) + float(
                (rng.rand_tagged(caller) & int(mask)) - int(center),
            ) * float(step)


def _apply_speed_scale_rule(
    *,
    state: GameplayState,
    proj_id: int,
    speed_rule: NoSpeedScale | ModuloSpeedScale,
    caller: int,
) -> None:
    match speed_rule:
        case NoSpeedScale():
            return
        case ModuloSpeedScale(base=base, modulo=modulo, step=step):
            state.projectiles.entries[int(proj_id)].speed_scale = float(base) + float(
                state.rng.rand_tagged(caller) % int(modulo),
            ) * float(step)


def fire_weapon(ctx: WeaponFireCtx) -> WeaponFireResult:
    player = ctx.player
    input_state = ctx.input_state
    dt = float(ctx.dt)
    state = ctx.state
    creatures = ctx.creatures
    players = ctx.players
    force_pre_swap_fire_gate = bool(ctx.force_pre_swap_fire_gate)
    player_death_runtime = ctx.player_death_runtime
    perk_player = players[0] if state.preserve_bugs and players else player
    # `player.stats` is a per-tick cache; keep it fresh for callers (unit
    # tests, tools) that reach fire_weapon without going through WorldState.step.
    refresh_player_stats(list(players) if players else [player])

    weapon_id = player.weapon.weapon_id
    weapon = weapon_entry(weapon_id)

    if (not force_pre_swap_fire_gate) and player.weapon.shot_cooldown > 0.0:
        return WeaponFireResult(fired=False)
    if not input_state.fire_down:
        return WeaponFireResult(fired=False)

    ammo_cost = 1.0
    is_fire_bullets = float(player.fire_bullets_timer) > 0.0
    is_plasma_overload = float(player.plasma_overload_timer) > 0.0
    perk_fire_ready = (not force_pre_swap_fire_gate) and player.weapon.reload_timer > 0.0
    use_regression_bullets = False
    use_ammunition_within = False
    if perk_fire_ready:
        if player.experience <= 0:
            return WeaponFireResult(fired=False)

        use_regression_bullets = perk_active(perk_player, PerkId.REGRESSION_BULLETS)
        use_ammunition_within = (not use_regression_bullets) and perk_active(
            perk_player,
            PerkId.AMMUNITION_WITHIN,
        )
        if not (use_regression_bullets or use_ammunition_within):
            return WeaponFireResult(fired=False)

    # Native writes this after the ready/input gates, but before charging the
    # reload-bypass perk and dispatching the shot.
    state.survival_reward_fire_seen = True

    if perk_fire_ready:
        if use_regression_bullets:
            ammo_class = int(weapon.ammo_class) if weapon.ammo_class is not None else 0

            reload_time = float(weapon.reload_time)
            # Rewrite-only: the native 200x factor made this perk a trap
            # outside the 2-3 weapons that got the cheap 4x rate (e.g. a
            # Pistol shot cost 240 XP - many kills' worth). Toned down to 20x
            # so it's usable across the roster without removing the cliff
            # (ammo_class 1 weapons still fire it the cheapest).
            factor = 4.0 if ammo_class == 1 else 20.0
            player.experience = int(float(player.experience) - reload_time * factor)
            if player.experience < 0:
                player.experience = 0
        elif use_ammunition_within:
            ammo_class = int(weapon.ammo_class) if weapon.ammo_class is not None else 0

            from ..player_damage import player_take_damage

            cost = 0.15 if ammo_class == 1 else 1.0
            player_take_damage(
                state,
                player,
                cost,
                dt=dt,
                players=players,
                death_runtime=player_death_runtime,
                floor=1.0,
            )
    pellet_count = int(weapon.pellet_count)
    fire_bullets_weapon = weapon_entry_for_projectile_type_id(ProjectileTemplateId.FIRE_BULLETS)

    shot_cooldown = float(f32(float(weapon.shot_cooldown)))
    weapon_spread_heat = float(weapon.spread_heat_inc)
    fire_bullets_spread_heat = float(fire_bullets_weapon.spread_heat_inc)

    if is_fire_bullets and pellet_count == 1:
        shot_cooldown = float(f32(float(fire_bullets_weapon.shot_cooldown)))
    elif is_plasma_overload:
        # Not native: Plasma Overload bonus - every weapon fires at a fixed
        # cooldown while active, regardless of its own rate or pellet count
        # (it always converts to the fixed twin-bolt mode).
        shot_cooldown = float(f32(_PLASMA_OVERLOAD_COOLDOWN))

    if is_fire_bullets:
        spread_heat_base = fire_bullets_spread_heat
    elif is_plasma_overload:
        spread_heat_base = _PLASMA_OVERLOAD_SPREAD_HEAT
    else:
        spread_heat_base = weapon_spread_heat
    spread_inc = x87_pc24_mul(spread_heat_base, f32(1.3))

    # Fastshot (x0.88), Sharpshooter (x1.05) and any new fire-rate content are
    # folded into stats.shot_cooldown_mult by crimson.progression. A single
    # perk resolves to exactly its old constant; two now fold into one multiply.
    cooldown_mult = float(perk_player.stats.shot_cooldown_mult)
    if cooldown_mult != 1.0:
        shot_cooldown = float(f32(float(shot_cooldown) * cooldown_mult))
    player.weapon.shot_cooldown = max(0.0, float(f32(float(shot_cooldown))))

    aim = input_state.aim
    # `player_update` computes and stores aim_heading before entering the fire
    # branch; later muzzle and presentation math reload that exact float field.
    aim_heading = float(f32(player.aim_heading))

    muzzle = native_fire_muzzle_pos(player.pos, aim_heading)
    weapon_flags = int(weapon.flags or 0)
    if weapon_flags & 0x1:
        # Native gameplay fire uses four exact `player_update` RNG sites for
        # the casing effect before the later shot-angle jitter work.
        shell_casing_draws = (
            state.rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_CASING_ANGLE),
            state.rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_CASING_SPEED),
            state.rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_CASING_ROTATION),
            state.rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_CASING_ROTATION_STEP),
        )
        state.effects.spawn_shell_casing(
            pos=muzzle,
            aim_heading=aim_heading,
            draws=shell_casing_draws,
            detail_preset=int(ctx.detail_preset),
        )

    shot_angle = _native_shot_angle_with_jitter(
        aim=aim,
        player_pos=player.pos,
        spread_heat=float(player.spread_heat),
        rng=state.rng,
    )
    particle_angle = Vec2.from_heading(shot_angle).to_angle()
    if weapon_id in (WeaponId.FLAMETHROWER, WeaponId.BLOW_TORCH, WeaponId.HR_FLAMER):
        particle_angle = Vec2.from_heading(aim_heading).to_angle()

    # Native gameplay fire consumes one exact `player_update` RNG draw for shot
    # SFX variant selection on every non-Fire-Bullets shot.
    if not is_fire_bullets:
        state.rng.rand_tagged(RngCallerStatic.PLAYER_UPDATE_SHOT_SFX)

    owner = owner_ref_for_player(player.index)
    projectile_owner = owner_ref_for_player_projectiles(state, player.index)
    # Native encodes friendly fire in the owner id (-1 - player_index): with the
    # cvar enabled, primary player shots can hit other players for 10 damage.
    projectile_hits_players = bool(state.friendly_fire_enabled)
    shot_count = 1
    # Native increments the accuracy counter only inside projectile_spawn /
    # fx_spawn_secondary_projectile; particle weapons (flamethrowers, bubblegun)
    # never count toward shots fired. The per-weapon usage counter keeps
    # incrementing as the rewrite's most-used-weapon heuristic.
    counts_accuracy_shots = True
    spawn_muzzle_after_projectile = bool(is_fire_bullets) or int(weapon_id) in _NATIVE_FIRE_MUZZLE_AFTER_PROJECTILE
    if not spawn_muzzle_after_projectile:
        _spawn_native_fire_muzzle_sprites(
            state=state,
            weapon_id=int(weapon_id),
            muzzle=muzzle,
            aim_heading=float(aim_heading),
            fire_bullets_active=bool(is_fire_bullets),
        )

    recipe = resolve_fire_recipe(
        weapon_id=weapon_id,
        pellet_count=pellet_count,
        fire_bullets_active=is_fire_bullets,
        plasma_overload_active=is_plasma_overload,
    )
    ammo_cost = float(recipe.ammo_cost)

    weapon_power_up_active = float(state.bonuses.weapon_power_up) > 0.0
    reflex_boost_active = float(state.bonuses.reflex_boost) > 0.0

    # Plasma clip-heat ramp: energy damage scales up as the clip drains. Resolved
    # once here from the clip state this shot leaves behind, then stamped onto
    # every bolt it spawns. Weapon Power Up raises the floor to +H (ramping to
    # +2H over the stock clip); Reflex Boost pins it to a flat +H. Neither gives
    # plasma a fire-rate bonus (see weapon_runtime/power_up.py).
    energy_heat_mult = 1.0
    if is_plasma_heat_weapon(int(weapon_id)):
        energy_heat_mult = plasma_energy_heat_mult(
            int(weapon_id),
            clip_size=float(player.weapon.clip_size),
            ammo_after_shot=float(player.weapon.ammo) - float(ammo_cost),
            weapon_power_up=weapon_power_up_active,
            reflex_boost=reflex_boost_active,
        )

    # Rewrite-only: Death Wish / Overdue only touch the player's own direct
    # trigger-pull (PrimaryPelletsMode below), computed once per fire_weapon
    # call rather than per pellet.
    death_wish_force_crit = perk_active(perk_player, PerkId.DEATH_WISH) and float(
        player.health,
    ) <= DEATH_WISH_HEALTH_THRESHOLD
    overdue_bonus_crit_mult = 0.0
    if perk_active(perk_player, PerkId.OVERDUE):
        if int(player.overdue_streak) >= OVERDUE_STREAK_THRESHOLD:
            # Streak just broke the threshold: open (or refresh) the window
            # instead of boosting only this one roll.
            player.overdue_streak = 0
            player.overdue_window_timer = OVERDUE_WINDOW_DURATION
        if float(player.overdue_window_timer) > 0.0:
            overdue_bonus_crit_mult = OVERDUE_BONUS_CRIT_MULT

    match recipe.mode:
        case PrimaryPelletsMode(type_id=type_id, count=count, jitter=jitter_rule, speed_scale=speed_rule):
            if type_id is None:
                raise ValueError(f"missing projectile type in recipe for weapon {int(weapon_id)}")
            pellets = max(0, int(count if count is not None else 0))
            shot_count = pellets
            meta = travel_budget_for_type_id(type_id)
            pellet_jitter_caller = (
                RngCallerStatic.PLAYER_UPDATE_FIRE_BULLETS_PELLET_JITTER
                if is_fire_bullets
                else _PELLET_JITTER_CALLER_BY_WEAPON.get(WeaponId(weapon_id))
            )
            pellet_speed_caller = _PELLET_SPEED_SCALE_CALLER_BY_WEAPON.get(WeaponId(weapon_id))
            if not isinstance(speed_rule, NoSpeedScale) and pellet_speed_caller is None:
                raise ValueError(f"missing pellet speed caller for weapon {int(weapon_id)}")
            # Explosive Payload bonus (not native): every bullet becomes a rocket.
            # Multi-pellet (shotgun-style) weapons only flag their single
            # centre-most pellet - the rest of the spread stays normal.
            explosive_payload_active = float(player.explosive_payload_timer) > 0.0
            explosive_pellet_index = pellets // 2
            for pellet_index in range(pellets):
                match jitter_rule:
                    case NoJitter():
                        angle = float(shot_angle)
                    case ModuloCenteredJitter() | MaskCenteredJitter():
                        if pellet_jitter_caller is None:
                            raise ValueError(f"missing pellet jitter caller for weapon {int(weapon_id)}")
                        angle = _apply_pellet_jitter(
                            shot_angle=float(shot_angle),
                            rng=state.rng,
                            jitter_rule=jitter_rule,
                            caller=int(pellet_jitter_caller),
                        )
                spawn_pos, spawn_angle = muzzle, angle
                if weapon_id == WeaponId.TENET_GUN:
                    # Not native: Tenet Gun (tenet_gun_spawn.py) - spawns at
                    # the aim point and fires back at the muzzle instead of
                    # the usual way around; everything past this point
                    # (damage, collision, pierce, ...) is unmodified.
                    spawn_pos, spawn_angle = tenet_reverse_spawn_params(
                        origin=muzzle,
                        muzzle=muzzle,
                        aim=aim,
                        angle=angle,
                    )
                proj_id = state.projectiles.spawn(
                    pos=spawn_pos,
                    angle=spawn_angle,
                    type_id=type_id,
                    owner=projectile_owner,
                    travel_budget=meta,
                    hits_players=projectile_hits_players,
                )
                if energy_heat_mult != 1.0:
                    state.projectiles.entries[int(proj_id)].energy_heat_mult = float(energy_heat_mult)
                pellet_crit_mult, pellet_did_crit = roll_primary_crit(
                    weapon_id,
                    force_crit=death_wish_force_crit,
                    bonus_crit_mult=overdue_bonus_crit_mult,
                )
                state.projectiles.entries[int(proj_id)].crit_mult = pellet_crit_mult
                state.projectiles.entries[int(proj_id)].did_crit = pellet_did_crit
                if pellet_did_crit:
                    player.overdue_streak = 0
                else:
                    player.overdue_streak = int(player.overdue_streak) + 1
                if weapon_id == WeaponId.TENET_GUN:
                    state.projectiles.entries[int(proj_id)].tenet_reverse = True
                if explosive_payload_active and pellet_index == explosive_pellet_index:
                    state.projectiles.entries[int(proj_id)].is_rocket = True
                if isinstance(speed_rule, ModuloSpeedScale):
                    assert pellet_speed_caller is not None
                    _apply_speed_scale_rule(
                        state=state,
                        proj_id=int(proj_id),
                        speed_rule=speed_rule,
                        caller=int(pellet_speed_caller),
                    )
        case SecondaryShotMode(type_id=type_id, targeting=targeting):
            target_hint = None
            spawn_creatures = None
            match targeting:
                case UseAimTargetHint():
                    target_hint = aim
                    spawn_creatures = creatures
                case _:
                    pass
            secondary_proj_id = state.secondary_projectiles.spawn_from_spec(
                SecondarySpawnSpec(
                    pos=muzzle,
                    angle=shot_angle,
                    type_id=type_id,
                    owner=projectile_owner,
                    target_hint=target_hint,
                    creatures=spawn_creatures,
                    preserve_bugs=bool(state.preserve_bugs),
                ),
            )
            state.secondary_projectiles.entries[int(secondary_proj_id)].crit_mult = roll_crit_mult(weapon_id)
        case ParticleStreamMode(style=style, slow=slow):
            counts_accuracy_shots = False
            # WPU for a stream weapon is +30% per-particle damage (fire rate is a
            # no-op - the stream already emits every frame); see world_state.py.
            if slow:
                particle_id = state.particles.spawn_particle_slow(
                    pos=muzzle,
                    angle=Vec2.from_heading(shot_angle).to_angle(),
                    owner=owner,
                )
                state.particles.entries[particle_id].crit_mult = roll_crit_mult(weapon_id)
            else:
                particle_id = state.particles.spawn_particle(
                    pos=muzzle,
                    angle=particle_angle,
                    intensity=1.0,
                    owner=owner,
                )
                if style is not None:
                    state.particles.entries[particle_id].style_id = style
                state.particles.entries[particle_id].crit_mult = roll_crit_mult(weapon_id)
        case MultiPlasmaFanMode():
            # Multi-Plasma: 5-shot fixed spread using type 0x09 and 0x0B.
            shot_count = 5
            spread_small = f32(0.31415927)
            spread_large = f32(0.5235988)
            patterns: tuple[tuple[float, ProjectileTemplateId], ...] = (
                (x87_pc24_sub(shot_angle, spread_small), ProjectileTemplateId.PLASMA_RIFLE),
                (x87_pc24_sub(shot_angle, spread_large), ProjectileTemplateId.PLASMA_MINIGUN),
                (shot_angle, ProjectileTemplateId.PLASMA_RIFLE),
                (x87_pc24_add(shot_angle, spread_large), ProjectileTemplateId.PLASMA_MINIGUN),
                (x87_pc24_add(shot_angle, spread_small), ProjectileTemplateId.PLASMA_RIFLE),
            )
            for angle, type_id in patterns:
                fan_proj_id = state.projectiles.spawn(
                    pos=muzzle,
                    angle=angle,
                    type_id=type_id,
                    owner=projectile_owner,
                    travel_budget=travel_budget_for_type_id(type_id),
                    hits_players=projectile_hits_players,
                )
                if energy_heat_mult != 1.0:
                    state.projectiles.entries[int(fan_proj_id)].energy_heat_mult = float(energy_heat_mult)
                state.projectiles.entries[int(fan_proj_id)].crit_mult = roll_crit_mult(weapon_id)
        case PlasmaOverloadMode():
            # Not native: Plasma Overload bonus - two Plasma Rifle bolts fired
            # side-by-side on the same heading (not a fan - no angle spread).
            # Damage is flat PLASMA_RIFLE.damage_scale (resolved normally from
            # the projectile's own type at hit time); cooldown/ammo are
            # overridden above/below.
            shot_count = _PLASMA_OVERLOAD_BOLT_COUNT
            perpendicular = Vec2.from_heading(float(shot_angle) + NATIVE_HALF_PI)
            half_spacing = _PLASMA_OVERLOAD_LATERAL_SPACING * 0.5
            for bolt_index in range(_PLASMA_OVERLOAD_BOLT_COUNT):
                lateral = f32(-half_spacing + _PLASMA_OVERLOAD_LATERAL_SPACING * bolt_index)
                bolt_pos = muzzle + perpendicular * float(lateral)
                bolt_spawn_pos, bolt_angle = bolt_pos, float(shot_angle)
                if weapon_id == WeaponId.TENET_GUN:
                    # Not native: Tenet Gun (tenet_gun_spawn.py) - see the
                    # identical branch in the PrimaryPelletsMode case above.
                    bolt_spawn_pos, bolt_angle = tenet_reverse_spawn_params(
                        origin=bolt_pos,
                        muzzle=muzzle,
                        aim=aim,
                        angle=shot_angle,
                    )
                bolt_proj_id = state.projectiles.spawn(
                    pos=bolt_spawn_pos,
                    angle=bolt_angle,
                    type_id=ProjectileTemplateId.PLASMA_RIFLE,
                    owner=projectile_owner,
                    travel_budget=travel_budget_for_type_id(ProjectileTemplateId.PLASMA_RIFLE),
                    hits_players=projectile_hits_players,
                )
                if energy_heat_mult != 1.0:
                    state.projectiles.entries[int(bolt_proj_id)].energy_heat_mult = float(energy_heat_mult)
                state.projectiles.entries[int(bolt_proj_id)].crit_mult = roll_crit_mult(weapon_id)
                if weapon_id == WeaponId.TENET_GUN:
                    state.projectiles.entries[int(bolt_proj_id)].tenet_reverse = True
        case SwarmerDumpMode():
            # Mini-Rocket Swarmers -> secondary type 2 (fires the full clip in a spread).
            # Native spawns one rocket per integer counter step below the float ammo
            # value (ceil), and zero rockets when firing with an empty/negative clip
            # (reachable via Regression Bullets / Ammunition Within).
            clip_ammo = float(player.weapon.ammo)
            rocket_count = math.ceil(clip_ammo) if clip_ammo > 0.0 else 0
            preserve_swarmer_bug = bool(state.preserve_bugs)
            if preserve_swarmer_bug:
                # Native bug: step scales by ammo (`ammo * pi/3`), which aliases
                # to near-identical headings for common clip sizes.
                step = x87_pc24_mul(clip_ammo, f32(1.0471976))
                angle = x87_pc24_sub(
                    x87_pc24_sub(shot_angle, NATIVE_PI),
                    x87_pc24_mul(x87_pc24_mul(step, clip_ammo), 0.5),
                )
            else:
                spread = math.pi * (2.0 / 3.0)
                step = 0.0 if rocket_count <= 1 else spread / float(rocket_count - 1)
                angle = shot_angle - spread * 0.5
            for _ in range(rocket_count):
                swarmer_proj_id = state.secondary_projectiles.spawn_from_spec(
                    SecondarySpawnSpec(
                        pos=muzzle,
                        angle=angle,
                        type_id=SecondaryProjectileTypeId.HOMING_ROCKET,
                        owner=projectile_owner,
                        target_hint=aim,
                        creatures=creatures,
                        preserve_bugs=bool(state.preserve_bugs),
                    ),
                )
                state.secondary_projectiles.entries[int(swarmer_proj_id)].crit_mult = roll_crit_mult(weapon_id)
                angle = x87_pc24_add(angle, step) if preserve_swarmer_bug else angle + step
            # Native subtracts the full clip value, zeroing the ammo even when
            # the clip was fractional or negative.
            ammo_cost = clip_ammo
            shot_count = rocket_count
        case MeleeSweepMode():
            # Evil Scythe: no projectile - start a cone sweep on the player.
            # The clip holds two swings; they alternate direction.
            from .scythe_sweep import start_scythe_swing

            counts_accuracy_shots = False
            shots_fired_this_clip = int(player.weapon.clip_size) - int(round(float(player.weapon.ammo)))
            start_scythe_swing(
                player,
                aim,
                shots_fired_this_clip=shots_fired_this_clip,
                weapon_power_up=weapon_power_up_active,
                crit_mult=roll_crit_mult(weapon_id),
            )
        case ArcStrikeMode():
            # Arc Gun: no projectile - flag a chain-lightning strike for the
            # world step to resolve (weapon_runtime/arc_gun.py).
            from .arc_gun import start_arc_strike

            counts_accuracy_shots = False
            start_arc_strike(
                player,
                aim,
                weapon_power_up=weapon_power_up_active,
                crit_mult=roll_crit_mult(weapon_id),
            )
    if 0 <= int(player.index) < len(state.shots_fired):
        if counts_accuracy_shots:
            state.shots_fired[int(player.index)] += int(shot_count)
        if 0 <= weapon_id < WEAPON_COUNT_SIZE:
            state.weapon_shots_fired[int(player.index)][weapon_id] += int(shot_count)

    if spawn_muzzle_after_projectile:
        _spawn_native_fire_muzzle_sprites(
            state=state,
            weapon_id=int(weapon_id),
            muzzle=muzzle,
            aim_heading=float(aim_heading),
            fire_bullets_active=bool(is_fire_bullets),
        )

    if not perk_active(perk_player, PerkId.SHARPSHOOTER):
        player.spread_heat = min(f32(0.48), max(0.0, x87_pc24_add(player.spread_heat, spread_inc)))

    muzzle_inc = weapon_spread_heat
    if is_fire_bullets and pellet_count == 1:
        muzzle_inc = fire_bullets_spread_heat
    player.muzzle_flash_alpha = min(1.0, player.muzzle_flash_alpha)
    player.muzzle_flash_alpha = min(1.0, player.muzzle_flash_alpha + muzzle_inc)
    player.muzzle_flash_alpha = min(0.8, player.muzzle_flash_alpha)

    player.shot_seq += 1
    if state.bonuses.reflex_boost <= 0.0 and not is_fire_bullets and not is_plasma_overload:
        # Native allows ammo to cross below zero for reload-time firing paths
        # (for example Regression Bullets), and replay checkpoints rely on that.
        # Not native: Plasma Overload bonus also gets the free-ammo treatment,
        # same as Fire Bullets/Reflex Boost - no ammo cost, so it can never
        # trigger a reload either.
        # Rewrite-only: Free Rounds - a private roll to skip this shot's ammo
        # cost outright.
        free_round = perk_active(perk_player, PerkId.FREE_ROUNDS) and _FREE_ROUNDS_RNG.random() < FREE_ROUNDS_CHANCE
        if not free_round:
            player.weapon.ammo = float(player.weapon.ammo) - float(ammo_cost)
    reload_start_gate_open = bool(player.weapon.reload_timer <= 0.0)
    if force_pre_swap_fire_gate:
        # Alt-weapon same-tick fire uses the pre-swap gate (reload_timer==0) for
        # reload restart eligibility after ammo drains below zero.
        reload_start_gate_open = True
    if player.weapon.ammo <= 0.0 and reload_start_gate_open:
        player_start_reload(player, state, players=ctx.players)
    return WeaponFireResult(fired=True, shot_count=int(shot_count), ammo_cost=float(ammo_cost))
