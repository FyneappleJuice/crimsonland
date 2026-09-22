from __future__ import annotations

"""Not native: Pendulum.

Alternates a +10% damage / +10% fire-rate bonus every clip, flipping
whenever a reload completes (natural empty-clip reload and a forced manual
reload both funnel through the same `reload_active` transition in
gameplay.py, so either one flips the phase).

Fire Bullets and Weapon Power Up temporarily change what a shot's damage or
fire rate actually is; snapshotting the phase at the moment either is granted
means reloading mid-buff can't retroactively change what that buff is worth.
"""

from ...sim.state_types import GameplayState, PlayerState
from ..helpers import perk_active
from ..ids import PerkId

PENDULUM_DAMAGE_BONUS = 0.10
PENDULUM_FIRE_RATE_BONUS = 0.10


def pendulum_snapshot_on_bonus_pickup(player: PlayerState) -> None:
    """Call when Fire Bullets or Weapon Power Up is granted/refreshed."""
    if perk_active(player, PerkId.PENDULUM):
        player.pendulum_snapshot_phase = bool(player.pendulum_phase)


def pendulum_effective_phase(state: GameplayState, player: PlayerState) -> bool:
    """False = damage phase active, True = fire-rate phase active."""
    if float(player.fire_bullets_timer) > 0.0 or float(state.bonuses.weapon_power_up) > 0.0:
        return bool(player.pendulum_snapshot_phase)
    return bool(player.pendulum_phase)


def pendulum_damage_mult(state: GameplayState, player: PlayerState) -> float:
    if not perk_active(player, PerkId.PENDULUM) or pendulum_effective_phase(state, player):
        return 1.0
    # Not native: Perk Efficacy scales both of Pendulum's phases.
    return 1.0 + PENDULUM_DAMAGE_BONUS * float(player.stats.perk_efficacy)


def pendulum_fire_rate_mult(state: GameplayState, player: PlayerState) -> float:
    if not perk_active(player, PerkId.PENDULUM) or not pendulum_effective_phase(state, player):
        return 1.0
    return 1.0 - PENDULUM_FIRE_RATE_BONUS * float(player.stats.perk_efficacy)
