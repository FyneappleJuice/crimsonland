from __future__ import annotations

"""Tenet Gun - reverse-time spawn point (rewrite-only).

Extremely small by design: a Tenet Gun shot is mechanically identical to
whatever it would otherwise be (Pistol clone, Fire Bullets, Plasma Overload,
Shock Chain, Fireblast, Angry Reloader, Fire Cough, Hot Tempered, Man Bomb,
Nuke, Ion Overload, ...) - damage, collision, pierce, Fork Shot, Explosive
Payload, everything runs through the exact same unmodified code every other
bullet uses. The only thing that changes is where it spawns and which way
it's pointed: instead of firing outward toward the aim point, the shot spawns
at the aim point and fires back toward where it would otherwise have started
- `Projectile.tenet_reverse` (flagged by the caller after spawning) tells
projectile_pool.py's step() to stop it once it arrives back at its owner
instead of flying on through them.

Applies to every projectile that originates from a Tenet-Gun-wielding
player, not just their own direct trigger-pull: the check lives centrally in
`weapon_runtime/spawn.py::projectile_spawn` (and `spawn_projectile_ring`,
which wraps it), the one chokepoint that Fireblast, Nuke, Shock Chain's
opening bolt, Fire Cough, Hot Tempered, Man Bomb and Angry Reloader all fire
through. `fire.py`'s own direct fire and Ion Overload's bolt
(bonuses/ion_overload.py) spawn via `state.projectiles.spawn` directly
instead of that chokepoint, so each applies this same transform by hand.
Spawns that
re-own to something other than the triggering player once they're airborne -
Shock Chain's own relay hits, Fork Shot children - go through the pool
directly and bypass all of this, so they're unaffected by construction.
"""

import math

from grim.geom import Vec2


def tenet_reverse_spawn_params(*, origin: Vec2, muzzle: Vec2, aim: Vec2, angle: float) -> tuple[Vec2, float]:
    """Flip a normal shot's spawn point/angle so it spawns at the aim point
    (preserving `origin`'s offset from the muzzle, e.g. Plasma Overload's
    twin bolts stay side by side) and flies back the way it came."""

    reversed_pos = Vec2(
        float(aim.x) + (float(origin.x) - float(muzzle.x)),
        float(aim.y) + (float(origin.y) - float(muzzle.y)),
    )
    reversed_angle = float(angle) + math.pi
    return reversed_pos, reversed_angle


__all__ = ["tenet_reverse_spawn_params"]
