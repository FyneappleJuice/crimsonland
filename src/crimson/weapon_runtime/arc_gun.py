from __future__ import annotations

"""Arc Gun - chain lightning (rewrite-only).

Firing does not spawn a projectile. Each shot arcs from the muzzle to the enemy
nearest the cursor (within ``ARC_MAX_RANGE`` of the player and ``ARC_CURSOR_SNAP``
of the cursor), then jumps to a random nearby enemy for ``ARC_CHAIN_LINKS`` more
hops, each within ``ARC_CHAIN_RANGE`` of the previous strike. Damage falls off
per hop. Weapon Power Up adds hops, range and damage.

The fire path just flags ``ArcGunState.pending``; the world-step updater picks
the targets, applies the ION damage and freezes the polyline into
``ArcGunState.chain`` (flat ``[x, y, ...]`` world points, first point = muzzle)
for the renderer to draw for ``ARC_BOLT_LIFETIME`` seconds.
"""

import math

from grim.geom import Vec2
from grim.sfx_map import SfxId

from ..creatures.damage_types import CreatureDamageType
from ..math_parity import native_fire_muzzle_pos
from ..owner_ref import OwnerRef
from ..rng_caller_static import RngCallerStatic
from ..sim.state_types import ArcGunState, PlayerState

ARC_MAX_RANGE = 430.0
# The primary target must be this close to the cursor - the arc "forms near the
# cursor", it does not just snap to whatever is on screen.
ARC_CURSOR_SNAP = 140.0
ARC_CHAIN_LINKS = 3
ARC_CHAIN_RANGE = 190.0
# Small per-link hit; the chain *builds* as it jumps, so a longer chain pays off.
ARC_DAMAGE = 7.5
ARC_CHAIN_GROWTH = 1.2  # damage *= this per hop (link 0 = base, link 1 = 1.2x, ...)
ARC_KNOCKBACK = 0.7
ARC_BOLT_LIFETIME = 0.10

# Looping crackle while the gun is firing. The sample is ~1.77s; re-trigger a
# touch sooner so there is no gap. Volume is scaled down (soft sfx).
ARC_SOUND = SfxId.ARC_LIGHTNING
ARC_SOUND_LOOP_S = 1.6
ARC_SOUND_VOLUME = 0.6

# Weapon Power Up: ~+30% DPS. The arc gun keeps the normalized fire-rate lever
# (faster re-strike), so its WPU specials are identity - no extra chain links,
# no damage/range multiplier.
ARC_WPU_EXTRA_LINKS = 0
ARC_WPU_RANGE_MULT = 1.0
ARC_WPU_DAMAGE_MULT = 1.0


def start_arc_strike(player: PlayerState, aim_world: Vec2, *, weapon_power_up: bool = False) -> None:
    arc = player.arc_gun
    arc.pending = True
    arc.aim_x = float(aim_world.x)
    arc.aim_y = float(aim_world.y)
    arc.weapon_power_up = bool(weapon_power_up)
    arc.seed = int(arc.seed) + 1


def arc_sound_loop_index(elapsed: float) -> int:
    """Which crackle repetition the firing run is on - used to re-trigger the loop."""

    return int(max(0.0, float(elapsed)) / ARC_SOUND_LOOP_S)


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _pick_primary(creatures, *, cursor: Vec2, player_pos: Vec2, max_range: float) -> int:
    best_idx = -1
    best_d = ARC_CURSOR_SNAP
    for idx, creature in enumerate(creatures):
        if not creature.active or float(creature.hp) <= 0.0:
            continue
        cx, cy = float(creature.pos.x), float(creature.pos.y)
        if _dist(cx, cy, float(player_pos.x), float(player_pos.y)) > max_range:
            continue
        d = _dist(cx, cy, float(cursor.x), float(cursor.y))
        if d < best_d:
            best_d = d
            best_idx = idx
    return best_idx


def _pick_chain(creatures, *, from_x: float, from_y: float, used: set[int], rng) -> int:
    candidates: list[int] = []
    for idx, creature in enumerate(creatures):
        if idx in used or not creature.active or float(creature.hp) <= 0.0:
            continue
        if _dist(float(creature.pos.x), float(creature.pos.y), from_x, from_y) <= ARC_CHAIN_RANGE:
            candidates.append(idx)
    if not candidates:
        return -1
    pick = int(rng.rand_tagged(RngCallerStatic.REWRITE_ARC_GUN_CHAIN_PICK)) % len(candidates)
    return candidates[pick]


def update_arc_gun(
    players: list[PlayerState],
    creatures,
    dt: float,
    *,
    rng,
    creature_damage_runtime,
) -> None:
    dt = float(dt)
    for player in players:
        arc = player.arc_gun

        if float(arc.bolt_timer) > 0.0:
            # Firing: keep the crackle-loop clock running.
            arc.sound_elapsed = float(arc.sound_elapsed) + dt
            arc.bolt_timer = float(arc.bolt_timer) - dt
            if float(arc.bolt_timer) <= 0.0:
                arc.bolt_timer = 0.0
                arc.chain = []
                arc.sound_elapsed = 0.0
        elif not arc.pending:
            arc.sound_elapsed = 0.0

        if not arc.pending:
            continue
        arc.pending = False

        wpu = bool(arc.weapon_power_up)
        max_range = ARC_MAX_RANGE * (ARC_WPU_RANGE_MULT if wpu else 1.0)
        links = ARC_CHAIN_LINKS + (ARC_WPU_EXTRA_LINKS if wpu else 0)
        dmg_mult = ARC_WPU_DAMAGE_MULT if wpu else 1.0

        muzzle = native_fire_muzzle_pos(player.pos, float(player.aim_heading))
        cursor = Vec2(float(arc.aim_x), float(arc.aim_y))
        chain: list[float] = [float(muzzle.x), float(muzzle.y)]

        primary = _pick_primary(creatures, cursor=cursor, player_pos=player.pos, max_range=max_range)
        if primary < 0:
            # Fizzle toward the cursor, capped at max range - visual only.
            dx, dy = float(cursor.x) - float(player.pos.x), float(cursor.y) - float(player.pos.y)
            d = math.hypot(dx, dy) or 1.0
            reach = min(d, max_range)
            chain += [float(player.pos.x) + dx / d * reach, float(player.pos.y) + dy / d * reach]
            arc.chain = chain
            arc.bolt_timer = ARC_BOLT_LIFETIME
            continue

        owner = OwnerRef.from_local_player(0)
        used: set[int] = set()
        cur = primary
        prev_x, prev_y = float(muzzle.x), float(muzzle.y)
        for hop in range(links + 1):
            if cur < 0:
                break
            creature = creatures[cur]
            cx, cy = float(creature.pos.x), float(creature.pos.y)
            chain += [cx, cy]
            used.add(cur)

            if creature_damage_runtime is not None:
                dmg = ARC_DAMAGE * dmg_mult * (ARC_CHAIN_GROWTH ** hop)
                inv = 1.0 / (math.hypot(cx - prev_x, cy - prev_y) or 1.0)
                impulse = Vec2((cx - prev_x) * inv * ARC_KNOCKBACK, (cy - prev_y) * inv * ARC_KNOCKBACK)
                creature_damage_runtime.apply_creature_damage(
                    cur, float(dmg), int(CreatureDamageType.LIGHTNING), impulse, owner,
                )

            prev_x, prev_y = cx, cy
            cur = _pick_chain(creatures, from_x=cx, from_y=cy, used=used, rng=rng)

        arc.chain = chain
        arc.bolt_timer = ARC_BOLT_LIFETIME


def arc_chain_points(arc: ArcGunState) -> list[Vec2]:
    """Flat chain list -> list of world points, for the renderer."""

    c = arc.chain
    return [Vec2(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
