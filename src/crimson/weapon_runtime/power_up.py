from __future__ import annotations

"""Weapon Power Up - normalized to ~+30% sustained DPS for every weapon.

Native WPU was fire-rate x1.5 + reload x0.6 (~+55% DPS) and the rewrite piled
per-class riders on top (2x flame particles, +2 chain links, ...) that pushed
some weapons past +100%. Now it is one lever per weapon, all tuned to ~+30%:

    most weapons  -> fire rate x1.30, reload x0.80          (gameplay.py / assign.py)
    fire (stream) -> +30% per-particle damage; fire rate is a no-op for a stream
    scythe        -> swing damage x1.30 (no fire-rate; in WPU_NO_RATE)

Plasma / ion / kinetic bullet keep only the normalized fire-rate lever - their
identity mechanics (clip-heat ramp, lingering cloud, pierce weapons) are
always-on, not WPU riders.
"""

from ..weapons import WeaponId

# Weapons whose WPU bonus is a damage buff, so the fire-rate/reload speed-up is
# suppressed to avoid double-dipping past +30%.
WPU_NO_RATE_WEAPON_IDS: frozenset[WeaponId] = frozenset({WeaponId.EVIL_SCYTHE})

# fire: per-flame-particle damage multiplier while WPU is active. Fire weapons
# get nothing from the fire-rate lever (the stream already emits every frame),
# so this is their whole +30%.
WPU_FLAME_DAMAGE_MULT = 1.30


def wpu_boosts_fire_rate(weapon_id: int) -> bool:
    try:
        return WeaponId(int(weapon_id)) not in WPU_NO_RATE_WEAPON_IDS
    except ValueError:
        return True


__all__ = [
    "WPU_FLAME_DAMAGE_MULT",
    "WPU_NO_RATE_WEAPON_IDS",
    "wpu_boosts_fire_rate",
]
