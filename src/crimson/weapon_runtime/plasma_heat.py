from __future__ import annotations

"""Plasma clip-heat ramp (rewrite-only).

Plasma / energy weapons build "heat" as their clip drains: the outgoing energy
damage scales linearly from ``+0`` on a fresh clip to ``+PLASMA_HEAT_H`` on the
last round of the weapon's *stock* clip. The denominator is the original table
clip size, so a wider clip from perks / relics keeps the ramp climbing past
``H`` - e.g. a +20% clip peaks at ``1.2 * H``. Reloading resets it (the next
clip starts cold).

The base ramp is always-on. Two power-ups reshape it for plasma instead of
giving a fire-rate bonus:

* **Weapon Power Up** raises the floor: the ramp starts at ``+H`` and climbs to
  ``+2H`` by the stock clip's last round (still climbing past ``2H`` with a
  wider clip).
* **Reflex Boost** pins it to a flat ``+H`` for the whole duration - ammo is
  not spent under Reflex Boost, so there is no clip to ramp against.

Reflex Boost takes precedence when both are active.

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
    },
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
    weapon_power_up: bool = False,
    reflex_boost: bool = False,
) -> float:
    """Heat bonus fraction for the shot that leaves ``ammo_after_shot`` in the clip.

    ``reflex_boost`` pins the result to a flat ``+H``; ``weapon_power_up`` adds a
    ``+H`` floor to the clip-drain ramp (so it runs ``+H -> +2H`` over the stock
    clip). Reflex Boost wins when both are set.
    """

    if not is_plasma_heat_weapon(weapon_id):
        return 0.0
    if reflex_boost:
        return PLASMA_HEAT_H
    base = float(WEAPON_BY_ID[WeaponId(int(weapon_id))].clip_size)
    if base <= 0.0:
        return PLASMA_HEAT_H if weapon_power_up else 0.0
    shots_fired = float(clip_size) - float(ammo_after_shot)
    if shots_fired < 0.0:
        shots_fired = 0.0
    ramp = PLASMA_HEAT_H * shots_fired / base
    if weapon_power_up:
        return PLASMA_HEAT_H + ramp
    return ramp


def plasma_energy_heat_mult(
    weapon_id: int,
    *,
    clip_size: float,
    ammo_after_shot: float,
    weapon_power_up: bool = False,
    reflex_boost: bool = False,
) -> float:
    """Outgoing energy-damage multiplier (``1.0`` = no ramp)."""

    return 1.0 + plasma_heat_fraction(
        weapon_id,
        clip_size=clip_size,
        ammo_after_shot=ammo_after_shot,
        weapon_power_up=weapon_power_up,
        reflex_boost=reflex_boost,
    )


__all__ = [
    "PLASMA_HEAT_H",
    "PLASMA_HEAT_WEAPON_IDS",
    "is_plasma_heat_weapon",
    "plasma_energy_heat_mult",
    "plasma_heat_fraction",
]
