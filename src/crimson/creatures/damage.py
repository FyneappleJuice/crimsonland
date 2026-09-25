from __future__ import annotations

import random as _random
from collections.abc import Callable

import msgspec

from grim.color import RGBA
from grim.geom import Vec2
from grim.rand import CrandLike
from grim.sfx_map import SfxId

from ..effects import EffectPool
from ..effects_atlas import EffectId
from ..math_parity import NATIVE_HALF_PI, f32, x87_pc24_add, x87_pc24_div, x87_pc24_mul, x87_pc24_sub
from ..owner_ref import OwnerRef
from ..perks import PerkId
from ..perks.helpers import perk_active
from ..perks.impl.bane_of_legends import BANE_OF_LEGENDS_KILL_BONUS, BANE_OF_LEGENDS_PENALTY
from ..perks.impl.delicate_watch import DELICATE_WATCH_BONUS
from ..meta.relics_impl import leech as relic_leech
from ..meta.relics_impl import slayer_pact as relic_slayer_pact
from ..progression import PlayerStats, resolve_team_stats, resolve_team_stats_perks_only
from ..rng_caller_static import RngCallerStatic
from ..sim.state_types import PlayerState
from ..weapon_runtime.tags import WeaponArchetype, weapon_tags
from .damage_runtime import CreatureDamageRuntime
from .damage_types import CreatureDamageType
from .runtime import CreatureState
from .spawn import CreatureFlags, CreatureTypeId


# Rewrite-only: new shooter-perk tuning (weapon_runtime research batch).
COUP_DE_GRACE_HP_FRACTION = 0.07
STEADY_HANDS_HP_FRACTION = 0.90
STEADY_HANDS_BONUS = 0.50
# Kinetic Discipline's continuous charge (perks/impl/kinetic_discipline.py,
# 0-1) scales up to this much bonus damage at full charge.
KINETIC_DISCIPLINE_MAX_BONUS = 0.30
# Adrenaline Rush's timed window (opened in player_damage.py whenever the
# player actually loses health) grants this flat bonus while it's open.
ADRENALINE_RUSH_BONUS = 0.25
# Overdue's timed window (opened in weapon_runtime/fire.py once a non-crit
# streak hits OVERDUE_STREAK_THRESHOLD - see that module for the streak/window
# mechanics) grants this flat bonus to *every* hit while it's open, not just
# crits - was a crit-multiplier-only bonus (crit_mult *= 1.5), which capped
# out mathematically tiny at these weapons' 5-15% base crit chances however
# much you stacked crit chance/multiplier. A flat all-damage bonus isn't
# bottlenecked by crit chance at all.
OVERDUE_BONUS_DAMAGE = 0.20
# Deep Freeze (Cold Snap): bonus damage a shooter deals to any target that is
# currently frozen, regardless of what froze it - their own crit-freeze
# (creature.crit_freeze_timer) or the native Evil Eyes perk's aim-lock. This
# is Deep Freeze's actual payoff now - the freeze itself was never going to
# out-compete Evil Eyes' unconditional, permanent freeze on CC alone.
COLD_SNAP_FROZEN_TARGET_BONUS = 0.30

# Loose Cannon: every non-DoT hit rolls a multiplier in this range instead of
# dealing its flat value. Average of [-1, 4] is 1.5, i.e. +50% average damage -
# the same "presentation/build variance, not run state" reasoning as
# weapon_runtime/crit.py's own private RNG applies here too: this fires on
# essentially every hit in the game once owned, so it needs a long-lived,
# continuously-advancing RNG (not a fresh reseed per hit, which would give
# every hit within the same tick the identical roll whenever nothing else
# happened to advance the shared sim RNG in between).
LOOSE_CANNON_MIN_MULT = -1.0
LOOSE_CANNON_MAX_MULT = 4.0
_LOOSE_CANNON_RNG = _random.Random(0x100CA33)

# Not native: run mods (crimson.run_mods) - per-weapon-archetype damage bonus,
# independent of damage_mult_* (damage TYPE). No UTILITY entry (no direct damage).
_ARCHETYPE_DAMAGE_STAT: dict[WeaponArchetype, str] = {
    WeaponArchetype.PISTOL: "damage_mult_archetype_pistol",
    WeaponArchetype.RIFLE: "damage_mult_archetype_rifle",
    WeaponArchetype.SMG: "damage_mult_archetype_smg",
    WeaponArchetype.SHOTGUN: "damage_mult_archetype_shotgun",
    WeaponArchetype.MINIGUN: "damage_mult_archetype_minigun",
    WeaponArchetype.CANNON: "damage_mult_archetype_cannon",
    WeaponArchetype.FLAMETHROWER: "damage_mult_archetype_flamethrower",
    WeaponArchetype.ARC: "damage_mult_archetype_arc",
    WeaponArchetype.MELEE: "damage_mult_archetype_melee",
}


def _any_player_has_perk(players: list[PlayerState], perk_id: PerkId) -> bool:
    return any(perk_active(player, perk_id) for player in players)


def _damage_perk_active(ctx: _CreatureDamageCtx, perk_id: PerkId) -> bool:
    return _any_player_has_perk(ctx.players, perk_id)


class _CreatureDamageCtx(msgspec.Struct):
    creature: CreatureState
    damage: float
    damage_type: int
    impulse: Vec2
    owner: OwnerRef
    dt: float
    players: list[PlayerState]
    rng: CrandLike
    # Resolved once per hit from the union of every relevant player's perks /
    # affixes (crimson.progression). Reads perk_counts directly, so it is
    # correct without depending on the per-tick player.stats cache.
    team_stats: PlayerStats = PlayerStats()
    # Not native: same as `team_stats`, but with run-mod contributions
    # excluded when `owner.no_run_mod_affinity` is set (see OwnerRef). Used
    # only by the per-damage-type multiplier functions and the weapon-
    # archetype block below - everything else (generic All Damage, the
    # shooter build-perk block) still reads the full `team_stats`.
    elemental_type_stats: PlayerStats = PlayerStats()
    # Not native: Fire, Explosion, and Ion each cover two distinct damage
    # events under one damage_type - only the direct-hit half is a genuine
    # "projectile" hit. Call sites set this True only for that half; Bullet/
    # Plasma/Energy have no second event to distinguish from, so their
    # projectile-mult step is unconditional (no flag needed).
    is_projectile_hit: bool = False


_CreatureDamageStep = Callable[[_CreatureDamageCtx], None]


_CREATURE_DEATH_SFX: dict[CreatureTypeId, tuple[SfxId, ...]] = {
    CreatureTypeId.ZOMBIE: (
        SfxId.ZOMBIE_DIE_01,
        SfxId.ZOMBIE_DIE_02,
        SfxId.ZOMBIE_DIE_03,
        SfxId.ZOMBIE_DIE_04,
    ),
    CreatureTypeId.LIZARD: (
        SfxId.LIZARD_DIE_01,
        SfxId.LIZARD_DIE_02,
        SfxId.LIZARD_DIE_03,
        SfxId.LIZARD_DIE_04,
    ),
    CreatureTypeId.ALIEN: (
        SfxId.ALIEN_DIE_01,
        SfxId.ALIEN_DIE_02,
        SfxId.ALIEN_DIE_03,
        SfxId.ALIEN_DIE_04,
    ),
    CreatureTypeId.SPIDER_SP1: (
        SfxId.SPIDER_DIE_01,
        SfxId.SPIDER_DIE_02,
        SfxId.SPIDER_DIE_03,
        SfxId.SPIDER_DIE_04,
    ),
    CreatureTypeId.SPIDER_SP2: (
        SfxId.SPIDER_DIE_01,
        SfxId.SPIDER_DIE_02,
        SfxId.SPIDER_DIE_03,
        SfxId.SPIDER_DIE_04,
    ),
}

_TROOPER_DEATH_SFX: tuple[SfxId, ...] = (
    SfxId.TROOPER_DIE_01,
    SfxId.TROOPER_DIE_02,
    SfxId.TROOPER_DIE_03,
)


def creature_death_sfx_for_slot(type_id: CreatureTypeId, sound_slot: int) -> SfxId | None:
    options = _TROOPER_DEATH_SFX if type_id == CreatureTypeId.TROOPER else _CREATURE_DEATH_SFX.get(type_id)
    slot = int(sound_slot)
    if options is None or not (0 <= slot < len(options)):
        return None
    return options[slot]


def _damage_generic_damage_mult(ctx: _CreatureDamageCtx) -> None:
    """Not native: run mods' "All-Damage" bucket (stats.damage_mult) - the one
    truly universal multiplier, applied regardless of damage_type (unlike
    every damage_mult_* bucket below, which is dispatched per-type and so
    never reaches MELEE/EXPLOSION/SELF_TICK hits)."""

    mult = float(ctx.team_stats.damage_mult)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _is_dot_damage(ctx: _CreatureDamageCtx) -> bool:
    """True for a ticking DoT/AoE event, as opposed to a discrete hit -
    Self-tick (poison) is always a DoT; Fire/Explosion/Ion are a DoT only on
    their non-direct-hit half (ignite tick, blast-radius tick, ion cloud
    tick - see is_projectile_hit). Everything else (Bullet/Plasma/Energy/
    Lightning/Melee, and any direct hit at all) is a discrete hit."""

    if ctx.damage_type == CreatureDamageType.SELF_TICK:
        return True
    if ctx.damage_type in (CreatureDamageType.FIRE, CreatureDamageType.EXPLOSION, CreatureDamageType.ION):
        return not ctx.is_projectile_hit
    return False


def _damage_variance_mult(ctx: _CreatureDamageCtx) -> None:
    """Loose Cannon: every non-DoT hit rolls a multiplier in
    [LOOSE_CANNON_MIN_MULT, LOOSE_CANNON_MAX_MULT] instead of dealing its
    flat value. This can roll negative - a "hit" that heals the target."""

    if not _damage_perk_active(ctx, PerkId.LOOSE_CANNON):
        return
    if _is_dot_damage(ctx):
        return
    mult = _LOOSE_CANNON_RNG.uniform(LOOSE_CANNON_MIN_MULT, LOOSE_CANNON_MAX_MULT)
    ctx.damage = f32(float(ctx.damage) * mult)


def _damage_projectile_damage_mult(ctx: _CreatureDamageCtx) -> None:
    """Outgoing multiplier for any main-pool projectile hit (kinetic + energy).

    Doctor (x1.2) and Barrel Greaser (x1.4) feed stats.damage_mult_projectile -
    they are about aim / barrel, not the ammo, so they apply to plasma too.
    """

    mult = float(ctx.team_stats.damage_mult_projectile)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_kinetic_bullet_damage_mult(ctx: _CreatureDamageCtx) -> None:
    """Outgoing multiplier for kinetic lead only (Uranium Filled Bullets, x2).

    Feeds stats.damage_mult_bullet. Does NOT touch energy/plasma.
    """

    mult = float(ctx.elemental_type_stats.damage_mult_bullet)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_plasma_damage_mult(ctx: _CreatureDamageCtx) -> None:
    """Outgoing multiplier for plasma hits (stats.damage_mult_plasma).

    Fed by future plasma perks and by relic / map affixes. The per-shot clip-heat
    ramp is applied earlier, on the projectile itself (energy_heat_mult).
    """

    mult = float(ctx.elemental_type_stats.damage_mult_plasma)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_energy_damage_mult(ctx: _CreatureDamageCtx) -> None:
    """Outgoing multiplier for Gauss hits (stats.damage_mult_energy).

    Fed by future perks and by relic / map affixes. Gauss Gun / Gauss Shotgun
    only - its own bucket, separate from plasma.
    """

    mult = float(ctx.elemental_type_stats.damage_mult_energy)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_living_fortress_mult(ctx: _CreatureDamageCtx) -> None:
    """Not native/generic: Living Fortress now applies to every damage type,
    not just Bullet/Plasma/Energy - "you deal more damage" shouldn't stop
    working just because you're punching or standing in an explosion."""

    if not _damage_perk_active(ctx, PerkId.LIVING_FORTRESS):
        return
    for player in ctx.players:
        if float(player.health) <= 0.0:
            continue
        timer = float(player.living_fortress_timer)
        if timer > 0.0:
            scale = x87_pc24_add(x87_pc24_mul(timer, f32(0.05)), 1.0)
            ctx.damage = x87_pc24_mul(ctx.damage, scale)
        # Not native: Stunt Double's clone ticks its own Living Fortress timer
        # (it never moves for its whole active window) but isn't itself a
        # real player in ctx.players - fold its timer in as one more source
        # of the same team-wide stack, same as a second real player would.
        snapshot = player.hollow_form_snapshot
        if snapshot is not None:
            snapshot_timer = float(snapshot.living_fortress_timer)
            if snapshot_timer > 0.0:
                snapshot_scale = x87_pc24_add(x87_pc24_mul(snapshot_timer, f32(0.05)), 1.0)
                ctx.damage = x87_pc24_mul(ctx.damage, snapshot_scale)


def _damage_type1_heading_jitter(ctx: _CreatureDamageCtx) -> None:
    creature = ctx.creature
    if (creature.flags & CreatureFlags.ANIM_PING_PONG) != 0:
        return
    jitter = x87_pc24_mul(
        float((ctx.rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_HEADING_JITTER) & 0x7F) - 0x40),
        f32(0.002),
    )
    size = max(1e-6, float(creature.size))
    turn = x87_pc24_div(jitter, x87_pc24_mul(size, f32(0.025)))
    # Native clamps against the f32 literal 1.5707964 and stores the sum f32.
    turn = min(float(NATIVE_HALF_PI), turn)
    creature.heading = x87_pc24_add(turn, creature.heading)


def _damage_type7_ion_damage_mult(ctx: _CreatureDamageCtx) -> None:
    # Ion Mastery's damage bump (x1.5). Its ion blast-radius bump stays in
    # projectile_pool.py.
    mult = float(ctx.elemental_type_stats.damage_mult_ion)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_explosion_damage_mult(ctx: _CreatureDamageCtx) -> None:
    # Not native: Rocket Mastery. Unconditional for the whole type (both the
    # direct impact and the blast-radius tick), same shape as Ion Mastery/
    # Pyromaniac boosting all of their type - no run-mod bucket exists for
    # Explosion, so there's nothing here to exempt from.
    mult = float(ctx.team_stats.damage_mult_explosion)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_lightning_damage_mult(ctx: _CreatureDamageCtx) -> None:
    # Chain lightning (Arc Gun) - its own scaling line (crimson.progression).
    # Not part of the run-mod Elemental Affinity exemption (no perk in that
    # set deals lightning damage), so this deliberately still reads
    # team_stats, not elemental_type_stats.
    mult = float(ctx.team_stats.damage_mult_lightning)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_type4_fire_damage_mult(ctx: _CreatureDamageCtx) -> None:
    # Pyromaniac (x1.5). Reads elemental_type_stats (not team_stats) so Fire
    # Cough's own canned burst can be exempted from the run-mod Fire Damage
    # bucket while Pyromaniac's real perk-vs-perk interaction still applies.
    mult = float(ctx.elemental_type_stats.damage_mult_fire)
    if mult != 1.0:
        ctx.damage = x87_pc24_mul(ctx.damage, f32(mult))


def _damage_lethal_ranged_shock_burst(
    *,
    creature: CreatureState,
    rng: CrandLike,
    effects: EffectPool | None,
    detail_preset: int,
) -> None:
    """Port the `creature_apply_damage` lethal branch for `flags & 0x10`."""
    if (creature.flags & CreatureFlags.RANGED_ATTACK_SHOCK) == 0:
        return
    for _ in range(5):
        rotation = (
            float(rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_ROTATION) & 0x7F) * 0.049087387
        )
        vel = Vec2(
            float((rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_VEL_X) & 0x7F) - 0x40),
            float((rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_VEL_Y) & 0x7F) - 0x40),
        )
        scale_step = (
            float(rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_SHOCK_BURST_SCALE_STEP) % 140) * 0.01 + 0.3
        )
        if effects is None:
            continue
        effects.spawn(
            effect_id=int(EffectId.BURST),
            pos=creature.pos,
            vel=vel,
            rotation=rotation,
            scale=1.0,
            half_width=36.0,
            half_height=36.0,
            age=0.0,
            lifetime=0.7,
            flags=0x1D,
            color=RGBA(0.8, 0.8, 0.3, 0.5),
            rotation_step=0.0,
            scale_step=scale_step,
            detail_preset=int(detail_preset),
        )


def resolve_native_death_sfx(
    creature: CreatureState,
    *,
    rng: CrandLike,
) -> tuple[SfxId, ...]:
    """Resolve the native `creature_apply_damage` death sound, if this path owns one."""
    if (creature.flags & CreatureFlags.RANGED_ATTACK_SHOCK) != 0:
        return ()
    roll = rng.rand_tagged(RngCallerStatic.CREATURE_APPLY_DAMAGE_DEATH_SFX)
    if creature.type_id == CreatureTypeId.TROOPER:
        return (_TROOPER_DEATH_SFX[roll % len(_TROOPER_DEATH_SFX)],)
    options = _CREATURE_DEATH_SFX.get(creature.type_id)
    if options is None:
        return ()
    return (options[roll & 3],)


_CREATURE_DAMAGE_PRE_STEPS: dict[int, tuple[_CreatureDamageStep, ...]] = {
    CreatureDamageType.BULLET: (
        _damage_kinetic_bullet_damage_mult,
        _damage_projectile_damage_mult,
    ),
    CreatureDamageType.PLASMA: (
        _damage_projectile_damage_mult,
        _damage_plasma_damage_mult,
    ),
    CreatureDamageType.ENERGY: (
        _damage_projectile_damage_mult,
        _damage_energy_damage_mult,
    ),
}

_CREATURE_DAMAGE_GLOBAL_PRE_STEPS: dict[int, tuple[_CreatureDamageStep, ...]] = {
    # Ion Mastery's own bump applies unconditionally to every ion hit - both
    # the direct bolt impact and the lingering AoE cloud tick (behaviors.py's
    # _linger_ion_aoe). The projectile bucket does not: see is_projectile_hit's
    # gated check below, which only the direct impact sets.
    CreatureDamageType.ION: (_damage_type7_ion_damage_mult,),
    CreatureDamageType.LIGHTNING: (_damage_lightning_damage_mult,),
    # Rocket Mastery, same unconditional shape - both the direct impact and
    # the blast-radius tick. The projectile bucket is still separately gated
    # by is_projectile_hit below (direct impact only).
    CreatureDamageType.EXPLOSION: (_damage_explosion_damage_mult,),
}


_CREATURE_DAMAGE_ALIVE_STEPS: dict[int, tuple[_CreatureDamageStep, ...]] = {
    CreatureDamageType.FIRE: (_damage_type4_fire_damage_mult,),
}


def creature_apply_damage(
    creature: CreatureState,
    *,
    damage_amount: float,
    damage_type: int,
    impulse: Vec2,
    owner: OwnerRef,
    dt: float,
    players: list[PlayerState],
    rng: CrandLike,
    is_projectile_hit: bool = False,
) -> bool:
    """Apply damage to a creature, returning True if the hit killed it.

    This is a partial port of `creature_apply_damage`.

    Notes:
    - Death side-effects (handle_death, doubled lethal impulse, then shock burst /
      death SFX) are handled by the caller in native order.
    - `damage_type` is a native integer category; call sites must supply it.
    - `is_projectile_hit`: not native. Only meaningful for FIRE, EXPLOSION,
      and ION, which each cover two distinct damage events sharing one
      damage_type - set True only for the "direct hit" half (flame particle
      contact, rocket impact, ion bolt impact), never the DoT/AoE half
      (ignite tick, blast-radius tick, lingering ion cloud tick).
    """

    creature.last_hit_owner = owner
    creature.hit_flash_timer = f32(0.2)

    team_stats = resolve_team_stats(players)
    ctx = _CreatureDamageCtx(
        creature=creature,
        damage=f32(damage_amount),
        damage_type=int(damage_type),
        impulse=Vec2(f32(impulse.x), f32(impulse.y)),
        owner=owner,
        dt=f32(dt),
        players=players,
        is_projectile_hit=bool(is_projectile_hit),
        rng=rng,
        # Native applies these damage perks if *any* player owns them, not
        # attributed to the shooter.
        team_stats=team_stats,
        elemental_type_stats=(resolve_team_stats_perks_only(players) if owner.no_run_mod_affinity else team_stats),
    )

    _damage_generic_damage_mult(ctx)
    _damage_living_fortress_mult(ctx)

    for step in _CREATURE_DAMAGE_GLOBAL_PRE_STEPS.get(ctx.damage_type, ()):
        step(ctx)

    for step in _CREATURE_DAMAGE_PRE_STEPS.get(ctx.damage_type, ()):
        step(ctx)

    # Not native: Fire, Explosion, and Ion each cover two distinct damage
    # events sharing one damage_type (Fire: particle hit + ignite DoT;
    # Explosion: direct impact + blast-radius tick; Ion: direct bolt impact +
    # lingering AoE cloud tick) - only the direct-hit half, not its DoT/AoE
    # sibling, gets the projectile bucket (Doctor/Barrel Greaser/Uranium
    # Filled Bullets). Bullet/Plasma/Energy have no second event to
    # distinguish from, so they stay unconditional in the PRE_STEPS dict above.
    if ctx.is_projectile_hit and ctx.damage_type in (
        CreatureDamageType.FIRE,
        CreatureDamageType.EXPLOSION,
        CreatureDamageType.ION,
    ):
        _damage_projectile_damage_mult(ctx)

    # Rewrite-only: monster rarity affix resistances + regen-pause bookkeeping.
    if creature.rarity:
        from .rarity import monster_affix_on_hit

        resist = monster_affix_on_hit(creature, int(ctx.damage_type), float(ctx.damage))
        if resist != 1.0:
            ctx.damage = f32(float(ctx.damage) * resist)

    # Rewrite-only: shooter build-perk dynamic damage adjustments. Resolved to
    # the actual firing player (not the "any player owns it" native-quirk
    # pattern above) since none of these are ported native content.
    if float(ctx.damage) > 0.0 and float(creature.max_hp) > 0.0:
        shooter_idx = ctx.owner.player_index()
        shooter = ctx.players[shooter_idx] if shooter_idx is not None and 0 <= shooter_idx < len(ctx.players) else None
        if shooter is not None:
            # Not native: run mods' "Weapon Type" bucket - keyed off the
            # shooter's currently-equipped weapon (not the weapon that
            # actually fired this specific shot, matching how the rest of
            # this shooter-perk block already resolves "the shooter" at hit
            # time). Value is read team-wide, same sharing rule as every
            # damage_mult_* bucket above. Reads elemental_type_stats so this
            # bucket can be exempted the same way as the per-type multipliers.
            archetype_stat = _ARCHETYPE_DAMAGE_STAT.get(weapon_tags(shooter.weapon.weapon_id).archetype)
            if archetype_stat is not None:
                archetype_mult = float(getattr(ctx.elemental_type_stats, archetype_stat))
                if archetype_mult != 1.0:
                    ctx.damage = f32(float(ctx.damage) * archetype_mult)
            hp_frac = float(creature.hp) / float(creature.max_hp)
            # Not native: Perk Efficacy scales each of these shooter-perk
            # bonuses at its own call site - see run_mods/ids.py's
            # PERK_EFFICACY entry for the full survey of what each one means.
            efficacy = float(shooter.stats.perk_efficacy)
            if perk_active(shooter, PerkId.COUP_DE_GRACE) and hp_frac <= COUP_DE_GRACE_HP_FRACTION * efficacy:
                ctx.damage = f32(max(float(ctx.damage), float(creature.hp)))
            elif perk_active(shooter, PerkId.STEADY_HANDS) and hp_frac >= STEADY_HANDS_HP_FRACTION:
                ctx.damage = f32(float(ctx.damage) * (1.0 + STEADY_HANDS_BONUS * efficacy))
            if perk_active(shooter, PerkId.KINETIC_DISCIPLINE) and float(shooter.kinetic_charge) > 0.0:
                ctx.damage = f32(
                    float(ctx.damage)
                    * (1.0 + KINETIC_DISCIPLINE_MAX_BONUS * efficacy * float(shooter.kinetic_charge)),
                )
            if (
                perk_active(shooter, PerkId.ADRENALINE_RUSH)
                and float(shooter.adrenaline_rush_window_timer) > 0.0
            ):
                ctx.damage = f32(float(ctx.damage) * (1.0 + ADRENALINE_RUSH_BONUS * efficacy))
            if (
                perk_active(shooter, PerkId.OVERDUE)
                and float(shooter.overdue_window_timer) > 0.0
            ):
                ctx.damage = f32(float(ctx.damage) * (1.0 + OVERDUE_BONUS_DAMAGE * efficacy))
            if perk_active(shooter, PerkId.BANE_OF_LEGENDS):
                bane_mult = 1.0 - BANE_OF_LEGENDS_PENALTY / efficacy
                if float(shooter.bane_of_legends_timer) > 0.0:
                    bane_mult *= 1.0 + BANE_OF_LEGENDS_KILL_BONUS * efficacy
                ctx.damage = f32(float(ctx.damage) * bane_mult)
            slayer_pact_mult = relic_slayer_pact.damage_mult(shooter)
            if slayer_pact_mult != 1.0:
                ctx.damage = f32(float(ctx.damage) * slayer_pact_mult)
            if perk_active(shooter, PerkId.DELICATE_WATCH):
                ctx.damage = f32(float(ctx.damage) * (1.0 + DELICATE_WATCH_BONUS * efficacy))
            if perk_active(shooter, PerkId.HIT_LIST) and float(shooter.hit_list_bonus) > 0.0:
                ctx.damage = f32(float(ctx.damage) * (1.0 + float(shooter.hit_list_bonus) * efficacy))
            if perk_active(shooter, PerkId.COLD_SNAP) and creature.is_frozen:
                ctx.damage = f32(float(ctx.damage) * (1.0 + COLD_SNAP_FROZEN_TARGET_BONUS * efficacy))

    if ctx.damage_type in (
        CreatureDamageType.BULLET,
        CreatureDamageType.PLASMA,
        CreatureDamageType.LIGHTNING,
        CreatureDamageType.ION,
        CreatureDamageType.ENERGY,
    ):
        _damage_type1_heading_jitter(ctx)

    if creature.hp <= 0.0:
        if ctx.dt > 0.0:
            creature.lifecycle_stage = x87_pc24_sub(
                creature.lifecycle_stage,
                x87_pc24_mul(ctx.dt, 15.0),
            )
        return True

    for step in _CREATURE_DAMAGE_ALIVE_STEPS.get(ctx.damage_type, ()):
        step(ctx)

    # Not native: Loose Cannon - applied last, against the fully resolved
    # damage, so it varies whatever every prior bonus/multiplier landed on.
    _damage_variance_mult(ctx)

    # Not native: Leech relic - heal off the fully resolved damage (post
    # variance), resolved fresh rather than reusing the shooter-perk block's
    # own `shooter` local, since that block doesn't always run (its own
    # ctx.damage > 0.0 guard may have been false).
    leech_shooter_idx = ctx.owner.player_index()
    leech_shooter = (
        ctx.players[leech_shooter_idx]
        if leech_shooter_idx is not None and 0 <= leech_shooter_idx < len(ctx.players)
        else None
    )
    if leech_shooter is not None and not ctx.owner.via_impale:
        relic_leech.heal_on_hit(leech_shooter, float(ctx.damage))

    creature.hp = x87_pc24_sub(creature.hp, ctx.damage)
    creature.vel = Vec2(
        x87_pc24_sub(creature.vel.x, ctx.impulse.x),
        x87_pc24_sub(creature.vel.y, ctx.impulse.y),
    )

    if creature.hp <= 0.0:
        if ctx.dt > 0.0:
            creature.lifecycle_stage = x87_pc24_sub(creature.lifecycle_stage, ctx.dt)
        else:
            creature.lifecycle_stage = x87_pc24_sub(creature.lifecycle_stage, f32(0.001))
        return True

    return False


def creature_apply_damage_with_lethal_followup(
    creature: CreatureState,
    *,
    creature_index: int,
    damage_amount: float,
    damage_type: int,
    impulse: Vec2,
    owner: OwnerRef,
    dt: float,
    players: list[PlayerState],
    rng: CrandLike,
    effects: EffectPool | None = None,
    detail_preset: int = 5,
    creature_damage_runtime: CreatureDamageRuntime,
    is_projectile_hit: bool = False,
) -> bool:
    """Apply damage and run a required lethal follow-up exactly on death transition.

    This helper keeps lethal bookkeeping adjacent to damage application so runtime
    call sites cannot accidentally skip death handling side effects.
    """

    # Native gates the lethal branch purely on entry health; a creature whose
    # death was already handled with hp still positive (shrinkifier shrink-death,
    # energizer eat) re-enters the full lethal follow-up on a later killing hit.
    death_start_needed = float(creature.hp) > 0.0
    native_impulse = Vec2(f32(impulse.x), f32(impulse.y))
    killed = creature_apply_damage(
        creature,
        damage_amount=float(damage_amount),
        damage_type=int(damage_type),
        impulse=native_impulse,
        owner=owner,
        dt=float(dt),
        players=players,
        rng=rng,
        is_projectile_hit=is_projectile_hit,
    )
    if killed and death_start_needed:

        def _resolve_damage_followup() -> tuple[SfxId, ...]:
            # Native lethal order: `creature_handle_death` runs first, the current
            # source-slot record receives a second 2x impulse, then either the
            # shock-burst rand loop (`flags & 0x10`) or the death-SFX rand draw.
            creature.vel = Vec2(
                x87_pc24_sub(creature.vel.x, x87_pc24_mul(native_impulse.x, 2.0)),
                x87_pc24_sub(creature.vel.y, x87_pc24_mul(native_impulse.y, 2.0)),
            )
            _damage_lethal_ranged_shock_burst(
                creature=creature,
                rng=rng,
                effects=effects,
                detail_preset=int(detail_preset),
            )
            return resolve_native_death_sfx(creature, rng=rng)

        creature_damage_runtime.on_creature_lethal(int(creature_index), _resolve_damage_followup)
        return True
    return False
