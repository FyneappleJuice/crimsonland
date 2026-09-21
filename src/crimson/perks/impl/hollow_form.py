from __future__ import annotations

"""Not native: Hollow Form.

Every 4-10 seconds, a frozen snapshot of the player (weapon, perks, active
powerup timers - a full `msgspec.structs.replace(player)`) appears at the
player's current position and, for 2 real seconds, aims at whatever's
nearest and holds its trigger down exactly like a held-LMB player would:
it's fed into the real `fire_weapon()` every tick, so its own ammo/cooldown/
reload state evolves naturally and it can fire more than once in that
window if the weapon's fire rate allows. It also runs the same
periodic-perk-tick pipeline a real player's frame does (Hot Tempered, Fire
Cough, Man Bomb, Living Fortress), so it can proc those independently of
pulling the trigger - Living Fortress in particular has a real shot at
mattering now that it never moves for a full 2 seconds. It never touches
the real player's weapon/ammo/streak state. render/world/draw.py draws it
as a dimmed trooper sprite at `hollow_form_pos` for as long as
`hollow_form_active_timer > 0`.

Doesn't spawn a creature-visible world entity, so there's nothing for
creatures to aggro onto.
"""

import math
import random as _random

import msgspec

from ...math_parity import NATIVE_HALF_PI, x87_fpatan, x87_pc24_sub
from ...sim.input import PlayerInput
from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..impl.like_clockwork import like_clockwork_rate_mult
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks


def _aim_heading_toward(pos, target_pos) -> float:
    # Matches gameplay.py's _aim_heading_from_aim_point_native exactly -
    # aim_heading is NOT a plain atan2(target - pos): fire_weapon reads it
    # for muzzle position and the trooper sprite reads it for torso/gun
    # rotation (render/world/trooper.py), and both expect this specific
    # fpatan(pos - aim) - HALF_PI convention. Using plain atan2 here made the
    # clone's gun visibly point somewhere other than where its shots actually
    # flew (shot direction is computed independently, correctly, from `aim`).
    dy = x87_pc24_sub(pos.y, target_pos.y)
    dx = x87_pc24_sub(pos.x, target_pos.x)
    return x87_pc24_sub(x87_fpatan(dy, dx), NATIVE_HALF_PI)

HOLLOW_FORM_MIN_INTERVAL = 4.0
HOLLOW_FORM_MAX_INTERVAL = 10.0
HOLLOW_FORM_ACTIVE_DURATION = 2.0

# Private RNG for the trigger interval only (build-variance timing, same
# reasoning as Free Rounds/crit.py) - the shots themselves still resolve on
# the real sim RNG via fire_weapon, same as any other shot.
_HOLLOW_FORM_RNG = _random.Random(0x8011014)


def _nearest_living_creature_pos(origin, creatures):
    nearest_pos = None
    nearest_dist = None
    ox, oy = float(origin.x), float(origin.y)
    for creature in creatures:
        if not creature.active or float(creature.hp) <= 0.0:
            continue
        dist = math.hypot(float(creature.pos.x) - ox, float(creature.pos.y) - oy)
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest_pos = creature.pos
    return nearest_pos


def _spawn_hollow_form_clone(player: PlayerState) -> None:
    player.hollow_form_snapshot = msgspec.structs.replace(
        player,
        weapon=msgspec.structs.replace(
            player.weapon,
            ammo=max(1.0, float(player.weapon.clip_size)),
            reload_active=False,
            reload_timer=0.0,
            shot_cooldown=0.0,
        ),
        hollow_form_snapshot=None,
    )
    player.hollow_form_pos = player.pos
    player.hollow_form_active_timer = HOLLOW_FORM_ACTIVE_DURATION


def _advance_clone_weapon_timers(clone: PlayerState, dt: float) -> None:
    # fire_weapon() only checks shot_cooldown/reload_timer, it never
    # decrements them - that normally happens once per frame in
    # gameplay.py's player_update, which this clone never runs through.
    # Trimmed to the pieces that matter for a short-lived synthetic shooter
    # (no Stationary Reloader/Anxious Loader/WPU reload-rate nuance).
    if clone.weapon.reload_timer > 0.0:
        clone.weapon.reload_timer = max(0.0, float(clone.weapon.reload_timer) - dt)
        if clone.weapon.reload_timer <= 0.0:
            clone.weapon.reload_active = False
            clone.weapon.ammo = float(clone.weapon.clip_size)
    clone.weapon.shot_cooldown = max(0.0, float(clone.weapon.shot_cooldown) - dt)


def _tick_hollow_form_clone(ctx: PerksUpdateEffectsCtx, player: PlayerState) -> None:
    from ...weapon_runtime import (
        WeaponFireCtx,
        fire_weapon,
        owner_ref_for_player,
        owner_ref_for_player_projectiles,
        projectile_spawn,
    )
    from ..runtime.player_ticks import apply_player_perk_ticks

    clone = player.hollow_form_snapshot
    if clone is None:
        return
    target_pos = _nearest_living_creature_pos(player.hollow_form_pos, ctx.creatures or ())
    if target_pos is None:
        return
    clone.pos = player.hollow_form_pos
    clone.aim = target_pos
    clone.aim_heading = _aim_heading_toward(clone.pos, target_pos)

    # Not native: run the clone through the same periodic-perk-tick pipeline
    # a real player's frame does (Hot Tempered, Fire Cough, Man Bomb, Living
    # Fortress), same order player_update() runs it in - real players and its
    # own perks, not a copy that can only pull the trigger.
    apply_player_perk_ticks(
        player=clone,
        player_pos_before_move=clone.pos,
        dt=float(ctx.dt),
        state=ctx.state,
        players=list(ctx.players),
        owner_ref_for_player=owner_ref_for_player,
        owner_ref_for_player_projectiles=owner_ref_for_player_projectiles,
        projectile_spawn=projectile_spawn,
    )

    _advance_clone_weapon_timers(clone, float(ctx.dt))
    fire_weapon(
        WeaponFireCtx(
            player=clone,
            input_state=PlayerInput(aim=target_pos, fire_down=True),
            dt=float(ctx.dt),
            state=ctx.state,
            creatures=ctx.creatures,
            players=ctx.players,
        ),
    )


def update_hollow_form(ctx: PerksUpdateEffectsCtx) -> None:
    if ctx.creatures is None:
        return
    for player in ctx.players:
        if not perk_active(player, PerkId.HOLLOW_FORM):
            player.hollow_form_timer = 0.0
            player.hollow_form_active_timer = 0.0
            player.hollow_form_snapshot = None
            continue
        if float(player.health) <= 0.0:
            continue

        if player.hollow_form_active_timer > 0.0:
            _tick_hollow_form_clone(ctx, player)
            player.hollow_form_active_timer = float(player.hollow_form_active_timer) - float(ctx.dt)
            if player.hollow_form_active_timer <= 0.0:
                player.hollow_form_active_timer = 0.0
                player.hollow_form_snapshot = None
            continue

        if player.hollow_form_timer <= 0.0:
            player.hollow_form_timer = _HOLLOW_FORM_RNG.uniform(
                HOLLOW_FORM_MIN_INTERVAL,
                HOLLOW_FORM_MAX_INTERVAL,
            )
            _spawn_hollow_form_clone(player)
            continue

        player.hollow_form_timer = float(player.hollow_form_timer) - float(ctx.dt) * like_clockwork_rate_mult(player)


HOOKS = PerkHooks(
    perk_id=PerkId.HOLLOW_FORM,
    effects_steps=(update_hollow_form,),
)
