from __future__ import annotations

"""Plasma clip-heat ramp (rewrite-only).

Plasma / energy weapons build "heat" as their clip drains: the outgoing energy
damage scales linearly from ``+0`` on a fresh clip to ``+PLASMA_HEAT_H`` on the
last round of the weapon's *stock* clip. The denominator is the original table
clip size, so a wider clip from perks / relics keeps the ramp climbing past
``H`` - e.g. a +20% clip peaks at ``1.2 * H``. Reloading resets it (the next
clip starts cold).

This ramp is always-on. Weapon Power Up does not touch it - plasma's WPU is just
the normalized fire-rate lever (see weapon_runtime/power_up.py).

The resolved multiplier is stamped onto each plasma bolt at spawn
(``Projectile.energy_heat_mult``) so a shot's damage reflects the clip state
when it was fired, not when it lands.
"""

from ..weapons import WEAPON_BY_ID, WeaponId

# Energy-damage bonus fraction at the last round of a stock clip.
PLASMA_HEAT_H = 0.5

# Weapons whose bolts carry the clip-heat ramp. Multi-Plasma / Plasma Shotgun
# spawn PLASMA_RIFLE / PLASMA_MINIGUN templates but are driven by their own
# weapon id here.
PLASMA_HEAT_WEAPON_IDS: frozenset[WeaponId] = frozenset(
    {
        WeaponId.PLASMA_RIFLE,
        WeaponId.MULTI_PLASMA,
        WeaponId.PLASMA_MINIGUN,
        WeaponId.PLASMA_SHOTGUN,
        WeaponId.SPIDER_PLASMA,
        WeaponId.PLASMA_CANNON,
    }
)


def is_plasma_heat_weapon(weapon_id: int) -> bool:
    try:
        return WeaponId(int(weapon_id)) in PLASMA_HEAT_WEAPON_IDS
    except ValueError:
        return False


def plasma_heat_fraction(
    weapon_id: int,
    *,
    clip_size: float,
    ammo_after_shot: float,
) -> float:
    """Heat bonus fraction for the shot that leaves ``ammo_after_shot`` in the clip."""

    if not is_plasma_heat_weapon(weapon_id):
        return 0.0
    base = float(WEAPON_BY_ID[WeaponId(int(weapon_id))].clip_size)
    if base <= 0.0:
        return 0.0
    shots_fired = float(clip_size) - float(ammo_after_shot)
    if shots_fired < 0.0:
        shots_fired = 0.0
    return PLASMA_HEAT_H * shots_fired / base


def plasma_energy_heat_mult(
    weapon_id: int,
    *,
    clip_size: float,
    ammo_after_shot: float,
) -> float:
    """Outgoing energy-damage multiplier (``1.0`` = no ramp)."""

    return 1.0 + plasma_heat_fraction(
        weapon_id,
        clip_size=clip_size,
        ammo_after_shot=ammo_after_shot,
    )


__all__ = [
    "PLASMA_HEAT_H",
    "PLASMA_HEAT_WEAPON_IDS",
    "is_plasma_heat_weapon",
    "plasma_energy_heat_mult",
    "plasma_heat_fraction",
]
