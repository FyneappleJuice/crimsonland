from __future__ import annotations

"""Not native: Harvester's Scythe.

Crits heal you. Resolved directly at the player's own crit roll
(weapon_runtime/fire.py's PrimaryPelletsMode branch, right where `did_crit`
comes back from roll_primary_crit) rather than as a periodic effects_step,
since it has to fire exactly once per crit, not once per tick.
"""

from ...math_parity import f32, x87_pc24_add
from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..impl.soul_tether import soul_tether_clamp_and_gain

HARVESTER_SCYTHE_HEAL_PER_CRIT = 1.5


def harvester_scythe_on_crit(player: PlayerState) -> None:
    if not perk_active(player, PerkId.HARVESTER_SCYTHE):
        return
    if float(player.health) <= 0.0:
        return
    player.health = soul_tether_clamp_and_gain(
        player,
        float(x87_pc24_add(f32(float(player.health)), HARVESTER_SCYTHE_HEAL_PER_CRIT)),
    )
