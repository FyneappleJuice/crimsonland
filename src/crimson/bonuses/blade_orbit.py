from __future__ import annotations

"""Blade bonus - an original addition, not present in the native game.

Five blades ride a circle centred on the player, making BLADE_REVOLUTIONS
full clockwise turns over BLADE_DURATION_S, then the effect ends.

Geometry, per blade ``k`` at elapsed time ``t`` (screen space, y-down, so a
positive angular rate reads as clockwise):

    theta_k = theta0 + OMEGA*t + k * (2*pi / BLADE_COUNT)
    world   = player.pos + (R*cos theta_k, R*sin theta_k)

The blades deal contact damage with a short per-creature cooldown so a single
enemy parked in the ring is not deleted in one tick.
"""

import math

from grim.geom import Vec2
from grim.sfx_map import SfxId

from ..creatures.damage_types import CreatureDamageType
from ..owner_ref import OwnerRef
from ..sim.state_types import BladeOrbitState, PlayerState
from ..test_mode import test_mode_enabled
from .apply_context import BonusApplyCtx

BLADE_COUNT = 5
BLADE_REVOLUTIONS = 2.0
BLADE_DURATION_S = 5.0
BLADE_RADIUS = 130.0

# Full orbital sweep is BLADE_REVOLUTIONS turns over BLADE_DURATION_S.
BLADE_OMEGA = BLADE_REVOLUTIONS * math.tau / BLADE_DURATION_S

# Contact reach = BLADE_HIT_RADIUS (the blade's own body, sprite ~20 px) plus a
# fraction of the creature's own footprint, so bigger aliens/spiders connect
# from further out - closer to what the sprites look like they should do than
# the very tight native `size/7 + 3` margin.
BLADE_HIT_RADIUS = 20.0
BLADE_CREATURE_RADIUS_FACTOR = 0.45
BLADE_HIT_COOLDOWN_S = 0.2
BLADE_HIT_DAMAGE = 22.0
_BLADE_KNOCKBACK = 2.0

# Looping whir: re-trigger the blade-gun launch sample this often while active.
BLADE_SOUND_LOOP_S = 0.45
BLADE_SOUND_VOLUME = 0.35
BLADE_SOUND = SfxId.SHOCK_FIRE_ALT

_PHASE_STEP = math.tau / float(BLADE_COUNT)


def blade_orbit_offsets(orbit: BladeOrbitState) -> list[Vec2]:
    """Player-relative positions of the blades at the orbit's current elapsed time."""

    if not orbit.active:
        return []
    swept = BLADE_OMEGA * float(orbit.elapsed)
    offsets: list[Vec2] = []
    for k in range(BLADE_COUNT):
        theta = float(orbit.theta0) + swept + k * _PHASE_STEP
        offsets.append(Vec2(BLADE_RADIUS * math.cos(theta), BLADE_RADIUS * math.sin(theta)))
    return offsets


def blade_orbit_progress(orbit: BladeOrbitState) -> float:
    """0.0 at pickup, 1.0 when the revolution is done."""

    if not orbit.active:
        return 1.0
    return min(1.0, float(orbit.elapsed) / BLADE_DURATION_S)


def blade_sound_loop_index(elapsed: float) -> int:
    """Which whir repetition the orbit is on - used to re-trigger the loop."""

    return int(max(0.0, float(elapsed)) / BLADE_SOUND_LOOP_S)


def apply_blade(ctx: BonusApplyCtx) -> None:
    orbit = ctx.player.blade_orbit
    was_active = orbit.active
    orbit.active = True
    orbit.elapsed = 0.0
    # A fresh random start angle so repeat pickups don't line up identically.
    orbit.theta0 = float(ctx.state.rng.rand() % 628) * 0.01
    orbit.phi0 = 0.0
    orbit.hit_cooldowns = {}
    if not was_active:
        ctx.register_player("blade_orbit")


def update_blade_orbits(
    players: list[PlayerState],
    creatures,
    dt: float,
    *,
    creature_damage_runtime,
) -> None:
    """Advance every active blade orbit and apply contact damage. Not native."""

    dt = float(dt)
    if dt <= 0.0:
        return

    # Test mode: keep the Blade bonus permanently on so it can be tuned / seen
    # without chasing pickups. Not native, not reachable outside --test-mode.
    force_on = test_mode_enabled()

    for player in players:
        orbit = player.blade_orbit
        if not orbit.active:
            if not force_on:
                continue
            orbit.active = True
            orbit.elapsed = 0.0
            orbit.theta0 = 0.0
            orbit.phi0 = 0.0
            orbit.hit_cooldowns = {}

        orbit.elapsed = float(orbit.elapsed) + dt
        if orbit.hit_cooldowns:
            orbit.hit_cooldowns = {
                idx: remaining - dt for idx, remaining in orbit.hit_cooldowns.items() if remaining - dt > 0.0
            }

        if orbit.elapsed >= BLADE_DURATION_S:
            orbit.hit_cooldowns = {}
            if force_on:
                # OMEGA*DURATION is exactly BLADE_REVOLUTIONS full turns, so
                # wrapping elapsed keeps the blade angles continuous and resets
                # the render fade - a seamless infinite orbit.
                orbit.elapsed -= BLADE_DURATION_S
            else:
                orbit.active = False
                continue

        if creature_damage_runtime is None or not creatures:
            continue

        owner = OwnerRef.from_local_player(0)
        for offset in blade_orbit_offsets(orbit):
            bx = float(player.pos.x) + float(offset.x)
            by = float(player.pos.y) + float(offset.y)
            for idx, creature in enumerate(creatures):
                if not creature.active or float(creature.hp) <= 0.0:
                    continue
                if idx in orbit.hit_cooldowns:
                    continue
                reach = BLADE_HIT_RADIUS + float(creature.size) * BLADE_CREATURE_RADIUS_FACTOR
                cdx = float(creature.pos.x) - bx
                cdy = float(creature.pos.y) - by
                dist_sq = cdx * cdx + cdy * cdy
                if dist_sq > reach * reach:
                    continue
                orbit.hit_cooldowns[idx] = BLADE_HIT_COOLDOWN_S
                inv = 1.0 / math.sqrt(dist_sq) if dist_sq > 0.0 else 0.0
                impulse = Vec2(-cdx * inv * _BLADE_KNOCKBACK, -cdy * inv * _BLADE_KNOCKBACK)
                creature_damage_runtime.apply_creature_damage(
                    idx,
                    BLADE_HIT_DAMAGE,
                    int(CreatureDamageType.MELEE),
                    impulse,
                    owner,
                )
