from __future__ import annotations

"""Not native: Harvester's Scythe.

Crits heal you. Resolved directly at the player's own crit roll
(weapon_runtime/fire.py's PrimaryPelletsMode branch, right where `did_crit`
comes back from roll_primary_crit) rather than as a periodic effects_step,
since it has to fire exactly once per crit, not once per tick.

The heal itself is small enough (0.5 HP) to be invisible against a 100-HP
ring, so a crit-heal also opens a short flash window
(harvester_scythe_flash_timer) purely so the player can *see* the perk
proc - render/world/player_status.py pulses the health ring green while it's
counted down; update_harvester_scythe_flash (below) ticks it back to 0.
"""

from ...math_parity import f32, x87_pc24_add, x87_pc24_sub
from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..impl.soul_tether import soul_tether_clamp_and_gain
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

HARVESTER_SCYTHE_HEAL_PER_CRIT = 0.5
HARVESTER_SCYTHE_FLASH_DURATION = 0.35


def harvester_scythe_on_crit(player: PlayerState) -> None:
    if not perk_active(player, PerkId.HARVESTER_SCYTHE):
        return
    if float(player.health) <= 0.0:
        return
    # Not native: Perk Efficacy scales the heal-per-crit.
    heal = HARVESTER_SCYTHE_HEAL_PER_CRIT * float(player.stats.perk_efficacy)
    player.health = soul_tether_clamp_and_gain(
        player,
        float(x87_pc24_add(f32(float(player.health)), heal)),
    )
    player.harvester_scythe_flash_timer = HARVESTER_SCYTHE_FLASH_DURATION


def update_harvester_scythe_flash(ctx: PerksUpdateEffectsCtx) -> None:
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if player.harvester_scythe_flash_timer > 0.0:
            player.harvester_scythe_flash_timer = max(
                0.0, float(x87_pc24_sub(f32(player.harvester_scythe_flash_timer), dt)),
            )


HOOKS = PerkHooks(
    perk_id=PerkId.HARVESTER_SCYTHE,
    effects_steps=(update_harvester_scythe_flash,),
)
