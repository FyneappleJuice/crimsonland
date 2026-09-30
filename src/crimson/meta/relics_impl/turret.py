from __future__ import annotations

"""Relic of the Turret (not native).

While equipped, the player can never fire their own weapon - Reload is
repurposed into "build a turret" instead. Holding/pressing Reload starts a
build lasting 5x the player's current weapon's fully perk-modified reload
time (computed once, via the ordinary `player_start_reload`); the player is
rooted in place for the whole window, and a second Reload press cancels it.
Up to TURRET_RELIC_MAX_PER_PLAYER turrets can exist at once - building past
the cap silently evicts the oldest one first.

A turret is a plain `CreatureState` (see `creatures/barrels.py`'s identical
trick for a destructible, non-hostile prop) - real HP, `ai_mode=HOLD_TIMER`
so the generic AI movement/turn code never drives it, `is_turret=True` for
render-suppression and the creature-vs-turret contact-damage pass (see
`creatures/runtime.py`). Unlike a Barrel, it has its own weapon
(`turret_weapon`, a persistent `WeaponSlot`) and fires on its own.

Every tick, `tick_turret` rebuilds a *fresh* (not frozen) shooter view of the
player - `msgspec.structs.replace(player, pos=<turret's position>, ...)` -
so `shooter.stats`/`shooter.perk_counts` always reflect whatever the real
player currently has, satisfying "any perk/powerup picked up after the
turret is built still applies to it". This is the opposite of Hollow Form's
one-shot frozen snapshot (perks/impl/hollow_form.py), which is otherwise the
closest precedent: both reuse `advance_weapon_shot_cooldown`/
`advance_weapon_reload`/`fire_weapon` verbatim so every real weapon/perk
interaction applies for free, and both tag their spawned projectiles
(`OwnerRef.via_turret`, parallel to `via_hollow_form`) so kill/XP still
credits the real player.

The turret picks a target from living creatures within its weapon's
effective range: the single nearest one if within TURRET_TARGET_OVERRIDE_RADIUS
(deterministic), otherwise a weighted random pick biased toward whichever
candidate is closer (see `_select_turret_target`). It holds its trigger down
(`PlayerInput.fire_down=True`) the entire time it has a target - same as
Hollow Form's clone always holding fire_down - while its gun turns to face
that target at a capped TURRET_TURN_RATE_RAD_S via
`creatures.runtime._angle_approach` (the same turn-rate-limited
interpolation every other creature in the game uses); shots fired while
still turning simply fly wherever the gun currently points, same as a real
turret spinning up. Its shots deal TURRET_DAMAGE_MULT of what the player's
own would (scaled via each spawned projectile's `crit_mult`, which the real
damage formula already multiplies in - correct for both crit and non-crit
shots since it's a proportional scale) - fire rate and reload otherwise
match the player's own fully perk-modified values exactly, no separate
penalty on either.

If the player is also dual-wielding (Pact of the Giant), the turret
dual-wields too: it keeps its own persistent copy of the alt weapon slot
(`turret_alt_weapon`, synced from the player's own alt_weapon the same way
`turret_weapon` mirrors the primary) and its own alternation-turn tracker
(`turret_giant_pact_next_slot`), and fires through the exact same
`giant_pact_dual_fire` the player and Hollow Form's clone use - see that
function's docstring in gameplay.py.

`turret_weapon_effective_range` is currently a flat placeholder
(TURRET_DEFAULT_RANGE) - `travel_budget` (weapons.py) does not cleanly
convert to a world-units range analytically (it's consumed as a per-tick
sub-step count in projectiles/runtime/projectile_pool.py, not a lifetime
distance budget), so a real per-weapon table needs an empirical measurement
pass (spawn a projectile into an empty arena and measure how far it actually
travels) rather than a hand-derived formula. Flagged as a follow-up, not
blocking - every weapon gets the same conservative range until then.

Turrets are run-scoped: they persist across level/wave transitions within a
run (nothing here clears them on those transitions) and are expected to be
cleared on player death/run end by whatever the Survival session's existing
run-end/death cleanup path is - not implemented here (see the open item in
the design plan).
"""

import math
import random as _random
from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

from ...math_parity import heading_from_delta_f32, heading_to_direction_f32
from ...sim.input import PlayerInput
from ...sim.state_types import WeaponSlot
from ..relics import RelicId, relic_owned
from . import giant_pact as relic_giant_pact
from . import leech

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...creatures.damage_runtime import CreatureDamageRuntime
    from ...creatures.runtime import CreaturePool, CreatureState
    from ...sim.state_types import GameplayState, PlayerState

TURRET_RELIC_MAX_PER_PLAYER = 2
TURRET_BUILD_DURATION_MULT = 5.0
TURRET_SPAWN_OFFSET = 60.0
TURRET_SIZE = 48.0
# Unsupported placeholder - no HP number was specified. Could reasonably
# scale with player level like Barrel's own barrel_health() instead of a flat
# constant.
TURRET_MAX_HP = 150.0
# 55% less damage than the player's own shot (compensates for the turret
# having no fire-rate/reload penalty - it's otherwise a full-uptime copy).
TURRET_DAMAGE_MULT = 0.45
# 180 degrees per 0.5s == 360 deg/s == tau rad/s exactly.
TURRET_TURN_RATE_RAD_S = math.tau
TURRET_TARGET_OVERRIDE_RADIUS = 75.0
# A turret has no AI movement of its own but can still be shoved by knockback
# impulses (creatures/damage.py's creature_apply_damage writes to vel on
# every hit) - this is the exponential decay-per-second rate that impulse
# bleeds off at once applied. Integrated here (tick_turret), not in
# creatures/runtime.py's shared per-creature loop, so it isn't silently
# skipped while the Freeze bonus is active (that loop short-circuits for
# every creature during Freeze; tick_turret always runs).
TURRET_KNOCKBACK_DRAG_PER_S = 4.0
# How often a turret re-rolls its target (see the module docstring) - not
# every tick, so the turn-rate-limited gun gets a real chance to catch up
# before the target changes again.
TURRET_RETARGET_INTERVAL_S = 0.75
# Placeholder until the real per-weapon measurement pass exists (see the
# module docstring) - conservative flat range, same for every weapon.
TURRET_DEFAULT_RANGE = 700.0

# Private RNG for target-choice randomness only - not the lockstep sim RNG,
# same reasoning as Free Rounds/Hollow Form's own private RNGs.
_TURRET_TARGET_RNG = _random.Random(0x71127E7)


def turret_relic_active() -> bool:
    return relic_owned(RelicId.TURRET_LOW)


def can_fire_own_weapon(player: PlayerState) -> bool:
    _ = player
    return not turret_relic_active()


def turret_weapon_effective_range(weapon_id: int) -> float:
    """A turret's target-search radius. Currently a flat placeholder for
    every weapon - see the module docstring for why `travel_budget` can't be
    converted to this analytically."""
    _ = weapon_id
    return TURRET_DEFAULT_RANGE


def handle_reload_key(
    player: PlayerState,
    input_state: PlayerInput,
    dt: float,
    state: GameplayState,
) -> None:
    """Edge-press toggle: cancel an in-progress build, or start a new one.
    Takes priority over every other Reload-key consumer (normal reload,
    Pact of the Giant) while this relic is active - see gameplay.py's
    reload-key branch."""

    _ = dt
    if not input_state.reload_pressed:
        return

    # Not native: Pact of the Giant - this relic's own Reload-key handling
    # (start_combined_reload + flip_active_slot) never runs while Turret is
    # equipped, since this branch always wins the priority race in
    # gameplay.py. Flipping the active slot here preserves the one piece of
    # that behavior still meaningful for a player who can't fire: which slot
    # a floor weapon pickup replaces.
    if relic_giant_pact.dual_wielding(player):
        relic_giant_pact.flip_active_slot(player)

    if player.turret_relic_building:
        player.turret_relic_building = False
        player.turret_build_timer = 0.0
        player.turret_build_duration = 0.0
        return

    from ...weapon_runtime.assign import player_start_reload

    # Calling the real player_start_reload purely to read the fully
    # perk-modified reload_timer_max (Fastloader, WPU, ...), then immediately
    # undoing its reload_active/reload_timer side effects - the player's own
    # weapon must never show (or actually run) a reload while this relic is
    # equipped; only turret_build_timer/turret_build_duration drive the UI.
    player_start_reload(player, state, players=[player])
    duration = TURRET_BUILD_DURATION_MULT * float(player.weapon.reload_timer_max)
    player.weapon.reload_active = False
    player.weapon.reload_timer = 0.0
    player.turret_relic_building = True
    player.turret_build_timer = duration
    player.turret_build_duration = duration


def tick_build(player: PlayerState, dt: float) -> None:
    """Counts the build timer down. No spawn side effect here - that needs a
    CreaturePool handle, see maybe_spawn_ready_turret."""

    if not player.turret_relic_building:
        return
    player.turret_build_timer = max(0.0, float(player.turret_build_timer) - float(dt))


def maybe_spawn_ready_turret(
    player: PlayerState,
    pool: CreaturePool | None,
    *,
    player_index: int,
) -> None:
    if pool is None:
        return
    if not player.turret_relic_building or player.turret_build_timer > 0.0:
        return
    player.turret_relic_building = False
    player.turret_build_duration = 0.0
    if len(player.turret_indices) >= TURRET_RELIC_MAX_PER_PLAYER:
        oldest = player.turret_indices.pop(0)
        if 0 <= oldest < len(pool.entries):
            pool.entries[oldest].active = False
    idx = spawn_turret(pool, player, player_index=player_index)
    if idx is not None:
        player.turret_indices.append(idx)


def spawn_turret(pool: CreaturePool, player: PlayerState, *, player_index: int) -> int | None:
    from ...creatures.spawn import CreatureInit
    from ...creatures.spawn_ids import CreatureAiMode, CreatureTypeId

    direction = heading_to_direction_f32(float(player.aim_heading))
    pos = Vec2(
        float(player.pos.x) + float(direction.x) * TURRET_SPAWN_OFFSET,
        float(player.pos.y) + float(direction.y) * TURRET_SPAWN_OFFSET,
    )
    idx = pool.spawn_init(
        CreatureInit(
            origin_template_id=0,
            pos=pos,
            heading=float(player.aim_heading),
            phase_seed=0,
            # Borrowed purely for HP/collision bookkeeping - never rendered as
            # a Zombie (is_turret suppresses native creature-sprite rendering,
            # see render/world/draw.py).
            type_id=CreatureTypeId.ZOMBIE,
            ai_mode=CreatureAiMode.HOLD_TIMER,
            health=TURRET_MAX_HP,
            max_health=TURRET_MAX_HP,
            move_speed=0.0,
            contact_damage=0.0,
            reward_value=0.0,
            size=TURRET_SIZE,
            is_turret=True,
        ),
    )
    if idx is None:
        return None
    entry = pool.entries[idx]
    # Not native: no CreatureInit.move_speed=0 shortcut exists (falsy ->
    # defaults to 1.0 - see barrels.py's identical force-set), so force it
    # directly on the materialized entry.
    entry.move_speed = 0.0
    # Not native: creatures/ai.py's HOLD_TIMER handling (without the AI7 flag)
    # reuses orbit_radius as a countdown - it decrements every tick and once
    # it reaches 0, ai_mode reverts to ORBIT_PLAYER. A turret needs to hold
    # forever, so this is set far larger than any run could last.
    entry.orbit_radius = 1.0e9
    entry.turret_owner_player_index = int(player_index)
    entry.turret_weapon = WeaponSlot(
        weapon_id=player.weapon.weapon_id,
        clip_size=int(player.weapon.clip_size),
        ammo=float(player.weapon.clip_size),
    )
    entry.turret_target_index = -1
    entry.turret_retarget_timer = 0.0
    pool.entries[idx] = entry
    return idx


def _sync_weapon_slot(tw: WeaponSlot, source: WeaponSlot) -> None:
    """Live "current weapon" inheritance for one slot: if the source weapon
    changed since last synced, switch too - a fresh clip, cleared
    cooldown/reload. A clip-size perk picked up after the fact (Ammo Maniac,
    My Favourite Weapon) just grows the clip in place, without resetting
    ammo/cooldown."""

    if int(tw.weapon_id) != int(source.weapon_id):
        tw.weapon_id = source.weapon_id
        tw.clip_size = int(source.clip_size)
        tw.ammo = float(tw.clip_size)
        tw.reload_active = False
        tw.reload_timer = 0.0
        tw.reload_timer_max = 0.0
        tw.shot_cooldown = 0.0
        tw.shot_cooldown_max = 0.0
    elif int(tw.clip_size) != int(source.clip_size):
        tw.clip_size = int(source.clip_size)


def _sync_turret_weapon_from_player(creature: CreatureState, player: PlayerState) -> None:
    """Primary-slot sync (see _sync_weapon_slot), plus Pact of the Giant's
    alt slot: created fresh (full clip) the moment the player starts
    dual-wielding, torn down the moment they stop, kept in sync with the
    player's own alt weapon while it exists."""

    tw = creature.turret_weapon
    if tw is None:
        return
    _sync_weapon_slot(tw, player.weapon)

    if relic_giant_pact.dual_wielding(player):
        assert player.alt_weapon is not None
        if creature.turret_alt_weapon is None:
            creature.turret_alt_weapon = WeaponSlot(
                weapon_id=player.alt_weapon.weapon_id,
                clip_size=int(player.alt_weapon.clip_size),
                ammo=float(player.alt_weapon.clip_size),
            )
        else:
            _sync_weapon_slot(creature.turret_alt_weapon, player.alt_weapon)
    else:
        creature.turret_alt_weapon = None


def _select_turret_target(
    pos: Vec2,
    creatures: Sequence[CreatureState],
    *,
    max_range: float,
) -> tuple[int, CreatureState] | None:
    """Weighted-random target pick, biased toward the nearest candidate, with
    a hard deterministic override at TURRET_TARGET_OVERRIDE_RADIUS."""

    candidates: list[tuple[int, CreatureState, float]] = []
    for i, c in enumerate(creatures):
        if not c.active or c.is_barrel or c.is_turret or float(c.hp) <= 0.0:
            continue
        dist = pos.distance_to(c.pos)
        if dist <= max_range:
            candidates.append((i, c, dist))
    if not candidates:
        return None

    nearest_i, nearest_c, nearest_dist = min(candidates, key=lambda t: t[2])
    if nearest_dist <= TURRET_TARGET_OVERRIDE_RADIUS:
        return nearest_i, nearest_c

    # Inverse-distance weighting, normalized to 1.0 at the override boundary
    # so the bias strictly increases as a candidate closes in.
    weights = [TURRET_TARGET_OVERRIDE_RADIUS / max(d, TURRET_TARGET_OVERRIDE_RADIUS) for _, _, d in candidates]
    picked_i, picked_c, _ = _TURRET_TARGET_RNG.choices(candidates, weights=weights, k=1)[0]
    return picked_i, picked_c


def turret_leech_heal_on_hit(creature: CreatureState, damage_dealt: float) -> None:
    """The turret's own mirror of meta/relics_impl/leech.py's heal_on_hit,
    operating on the turret's own hp instead of a PlayerState's health - no
    Soul Tether/Death Clock interaction (those are player-only, never given
    to the turret). Called from creatures/damage.py's shooter-perk block
    alongside (not instead of) the real player's own heal_on_hit, per the
    owner's explicit call that a turret's hits heal both."""

    if float(damage_dealt) <= 0.0:
        return
    heal_pct = leech.active_heal_pct()
    if heal_pct is None:
        return
    if len(creature.turret_leech_pending_timers) >= leech.LEECH_MAX_INSTANCES:
        return
    total_heal = float(damage_dealt) * heal_pct
    if total_heal <= 0.0:
        return
    creature.turret_leech_pending_heal.append(total_heal)
    creature.turret_leech_pending_timers.append(leech.LEECH_HEAL_DURATION)


def turret_leech_tick(creature: CreatureState, dt: float) -> None:
    """Drips the turret's own pending Leech instances into its own hp,
    capped at max_hp (no shield-conversion - Soul Tether isn't given to the
    turret). Called unconditionally every tick, same as the player's own
    relic_leech.tick."""

    if not creature.turret_leech_pending_timers:
        return
    dt = float(dt)
    kept_heal: list[float] = []
    kept_timers: list[float] = []
    for total_heal, remaining in zip(creature.turret_leech_pending_heal, creature.turret_leech_pending_timers):
        tick_heal = float(total_heal) * dt / leech.LEECH_HEAL_DURATION
        creature.hp = min(float(creature.max_hp), float(creature.hp) + tick_heal)
        remaining -= dt
        if remaining > 0.0:
            kept_heal.append(total_heal)
            kept_timers.append(remaining)
    creature.turret_leech_pending_heal = kept_heal
    creature.turret_leech_pending_timers = kept_timers


def turret_leech_hp_cost_on_kill(creature: CreatureState) -> None:
    """The turret's own mirror of relic_leech.hp_cost_on_kill, called
    alongside (not instead of) the real player's own cost, per the owner's
    explicit call that a turret kill costs both."""

    if leech.active_heal_pct() is None:
        return
    cost = float(creature.hp) * leech.LEECH_HP_COST_PER_KILL
    creature.hp = max(0.0, float(creature.hp) - cost)


def _apply_knockback(creature: CreatureState, dt: float) -> None:
    """A turret never moves under its own power (ai_mode=HOLD_TIMER), but a
    hit still writes a knockback impulse into creature.vel
    (creatures/damage.py's creature_apply_damage) - integrate it here and let
    it decay, since nothing else ever will."""

    if creature.vel.length_sq() <= 1e-6:
        return
    creature.pos = Vec2(
        float(creature.pos.x) + float(creature.vel.x) * dt,
        float(creature.pos.y) + float(creature.vel.y) * dt,
    )
    drag = max(0.0, 1.0 - TURRET_KNOCKBACK_DRAG_PER_S * dt)
    creature.vel = Vec2(float(creature.vel.x) * drag, float(creature.vel.y) * drag)
    if creature.vel.length_sq() < 1.0:
        creature.vel = Vec2()


def tick_turret(
    creature: CreatureState,
    creature_index: int,
    *,
    player: PlayerState,
    state: GameplayState,
    players: list[PlayerState],
    creatures: Sequence[CreatureState],
    dt: float,
    creature_damage_runtime: CreatureDamageRuntime | None = None,
) -> None:
    """Per-tick turret AI: resync weapon, (re-)pick a target, turn toward it,
    fire once aligned. Called once per active turret index from
    sim/world_state.py's step(), after every player's own frame has updated."""

    if creature.turret_weapon is None:
        return

    # Not native: Leech's own heal-over-time drip for this turret's
    # instances - unconditional every tick, same as the real player's.
    turret_leech_tick(creature, dt)
    _apply_knockback(creature, dt)
    _sync_turret_weapon_from_player(creature, player)
    max_range = turret_weapon_effective_range(int(creature.turret_weapon.weapon_id))

    creature.turret_retarget_timer = float(creature.turret_retarget_timer) - float(dt)
    target: CreatureState | None = None
    if 0 <= creature.turret_target_index < len(creatures):
        candidate = creatures[creature.turret_target_index]
        if candidate.active and float(candidate.hp) > 0.0 and creature.pos.distance_to(candidate.pos) <= max_range:
            target = candidate
    if target is None or creature.turret_retarget_timer <= 0.0:
        picked = _select_turret_target(creature.pos, creatures, max_range=max_range)
        creature.turret_retarget_timer = TURRET_RETARGET_INTERVAL_S
        if picked is not None:
            creature.turret_target_index, target = picked
        else:
            creature.turret_target_index = -1
            target = None

    if target is not None:
        target_pos = target.pos
        target_angle = heading_from_delta_f32(
            dx=float(target_pos.x) - float(creature.pos.x),
            dy=float(target_pos.y) - float(creature.pos.y),
        )
        creature.target_heading = target_angle

        # Lazy import: creatures/runtime.py imports gameplay.py at module
        # level, and gameplay.py imports this module - a module-level import
        # here would be a real circular import.
        from ...creatures.runtime import _angle_approach

        creature.heading = _angle_approach(
            float(creature.heading), float(creature.target_heading), TURRET_TURN_RATE_RAD_S, float(dt),
        )
    else:
        target_pos = creature.pos

    # Lazy import for the same reason as above.
    from ...gameplay import advance_weapon_reload, advance_weapon_shot_cooldown, clear_reload_active_if_gate_open
    from ...perks.runtime.player_ticks import apply_player_perk_ticks
    from ...weapon_runtime import (
        WeaponFireCtx,
        fire_weapon,
        owner_ref_for_player,
        owner_ref_for_player_projectiles,
        projectile_spawn,
    )

    dual_wielding = creature.turret_alt_weapon is not None
    shooter = msgspec.structs.replace(
        player,
        pos=creature.pos,
        heading=float(creature.heading),
        aim=target_pos,
        aim_heading=float(creature.heading),
        weapon=creature.turret_weapon,
        alt_weapon=creature.turret_alt_weapon,
        hollow_form_snapshot=None,
        hollow_form_active_timer=0.0,
        turret_indices=[],
        # Not native: the turret's own independent cycle for these 4
        # periodic self-triggered perks (see the CreatureState field
        # comments) - never the real player's current progress, which would
        # otherwise be clobbered every tick by this throwaway clone.
        man_bomb_timer=creature.turret_man_bomb_timer,
        hot_tempered_timer=creature.turret_hot_tempered_timer,
        fire_cough_timer=creature.turret_fire_cough_timer,
        living_fortress_timer=creature.turret_living_fortress_timer,
        # Not native: the turret's own independent Seeker Rounds dedup
        # counter, Pendulum phase, and Pact of the Giant alternation turn -
        # see the CreatureState field comments.
        shot_seq=creature.turret_shot_seq,
        pendulum_phase=creature.turret_pendulum_phase,
        pendulum_snapshot_phase=creature.turret_pendulum_snapshot_phase,
        giant_pact_next_slot=creature.turret_giant_pact_next_slot,
    )
    # Not native: simulate the turret holding its trigger down the whole time
    # it has a target - same as Hollow Form's clone always holding fire_down
    # (perks/impl/hollow_form.py) - rather than gating on exact alignment;
    # shots fired while still turning onto target simply fly wherever the gun
    # currently points, the same way a real turret spinning up would.
    input_state = PlayerInput(aim=target_pos, fire_down=target is not None)

    # Not native: run the turret through the same periodic-perk-tick pipeline
    # a real player's frame does (Man Bomb, Hot Tempered, Fire Cough, Living
    # Fortress - see perks/runtime/manifest.py's player_tick_steps), same as
    # Hollow Form's clone does for its own (much shorter) lifetime. A turret
    # never moves under its own power, so it's unconditionally "stationary"
    # for Living Fortress's purposes.
    apply_player_perk_ticks(
        player=shooter,
        player_pos_before_move=shooter.pos,
        dt=dt,
        state=state,
        players=players,
        owner_ref_for_player=owner_ref_for_player,
        owner_ref_for_player_projectiles=owner_ref_for_player_projectiles,
        projectile_spawn=projectile_spawn,
        aim=target_pos,
        creatures=creatures,
        creature_damage_runtime=creature_damage_runtime,
    )
    creature.turret_man_bomb_timer = float(shooter.man_bomb_timer)
    creature.turret_hot_tempered_timer = float(shooter.hot_tempered_timer)
    creature.turret_fire_cough_timer = float(shooter.fire_cough_timer)
    creature.turret_living_fortress_timer = float(shooter.living_fortress_timer)

    advance_weapon_shot_cooldown(shooter, state, dt, reload_stationary=True)
    advance_weapon_reload(shooter, shooter, input_state, dt, state, players, reload_stationary=True)
    if dual_wielding:
        # Not native: Pact of the Giant - tick the alt slot's own
        # shot_cooldown/reload_timer too, exactly like Hollow Form's clone
        # does for its own dual-wielding.
        from ...gameplay import advance_giant_pact_alt_slot

        advance_giant_pact_alt_slot(shooter, shooter, input_state, dt, state, players, reload_stationary=True)
    clear_reload_active_if_gate_open(shooter)
    if dual_wielding:
        relic_giant_pact.clear_alt_reload_active_if_gate_open(shooter)
    creature.turret_pendulum_phase = bool(shooter.pendulum_phase)
    creature.turret_pendulum_snapshot_phase = bool(shooter.pendulum_snapshot_phase)

    primary_before = {i for i, e in enumerate(state.projectiles.entries) if e.active}
    secondary_before = {i for i, e in enumerate(state.secondary_projectiles.entries) if e.active}

    if dual_wielding:
        # Not native: Pact of the Giant - the turret dual-wields too, through
        # the exact same alternating dual-fire the player/Hollow Form use.
        from ...gameplay import giant_pact_dual_fire

        giant_pact_dual_fire(
            shooter,
            input_state,
            dt,
            state,
            detail_preset=5,
            creatures=creatures,
            players=players,
            suppress_empty_clip_self_cost_perks=True,
        )
    else:
        fire_weapon(
            WeaponFireCtx(
                player=shooter,
                input_state=input_state,
                dt=dt,
                state=state,
                creatures=creatures,
                players=players,
                # shooter is a disposable per-tick clone - Ammunition Within's
                # self-cost would call player_take_damage on it, which still
                # leaks a real pain SFX into the shared queue even though no
                # real player loses health. A turret just waits out its own
                # reload instead, like any weapon without those perks.
                suppress_empty_clip_self_cost_perks=True,
                # Not native: Pact of the Giant's 1.5x fire-rate tax
                # (fire_rate_cost_mult) is gated on the relic being equipped
                # at all, not on actually dual-wielding - a real player never
                # hits that gap since their alt slot is always seeded
                # whenever the relic is active, but a turret with no alt
                # weapon genuinely never dual-wields. Without this, it would
                # eat the tax for a second weapon it can't fire.
                giant_pact_partner_dry=True,
            ),
        )
    creature.turret_shot_seq = int(shooter.shot_seq)
    creature.turret_giant_pact_next_slot = int(shooter.giant_pact_next_slot)

    fired_any = False
    for entries, before in (
        (state.projectiles.entries, primary_before),
        (state.secondary_projectiles.entries, secondary_before),
    ):
        for i, entry in enumerate(entries):
            if entry.active and i not in before:
                entry.crit_mult = float(entry.crit_mult) * TURRET_DAMAGE_MULT
                entry.owner = msgspec.structs.replace(
                    entry.owner, via_turret=True, turret_creature_index=int(creature_index),
                )
                fired_any = True
    if fired_any:
        player.turret_last_fire_pos = creature.pos


__all__ = [
    "TURRET_BUILD_DURATION_MULT",
    "TURRET_DAMAGE_MULT",
    "TURRET_DEFAULT_RANGE",
    "TURRET_FIRE_RATE_MULT",
    "TURRET_MAX_HP",
    "TURRET_RELIC_MAX_PER_PLAYER",
    "TURRET_RELOAD_MULT",
    "TURRET_RETARGET_INTERVAL_S",
    "TURRET_SIZE",
    "TURRET_SPAWN_OFFSET",
    "TURRET_TARGET_OVERRIDE_RADIUS",
    "TURRET_TURN_RATE_RAD_S",
    "can_fire_own_weapon",
    "handle_reload_key",
    "maybe_spawn_ready_turret",
    "spawn_turret",
    "tick_build",
    "tick_turret",
    "turret_relic_active",
    "turret_weapon_effective_range",
]
