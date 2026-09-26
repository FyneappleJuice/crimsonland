from __future__ import annotations

"""Not native: Kinetic Discipline.

A continuous (not discrete) charge, 0-1, that ramps up while the player is
moving in a sustained, roughly-straight line and ramps back down the instant
that's interrupted (stopping, or turning sharply). The damage bonus this buys
(creatures/damage.py) scales with the charge itself, so there's no "free"
always-on bonus and no separate standing-still penalty - holding a straight
line near a horde is the actual risk being paid for it.
"""

import math
from typing import TYPE_CHECKING

from ...math_parity import f32
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

if TYPE_CHECKING:
    from ...sim.state_types import PlayerState

MOVE_EPSILON = 0.05
TURN_RATE_LIMIT = math.radians(120.0)  # faster pivots than this break the ramp
RAMP_UP_SECONDS = 3.0  # sustained straight-line movement to reach full charge
RAMP_DOWN_SECONDS = 1.0  # decays to 0 this fast once interrupted


def update_kinetic_discipline(ctx: PerksUpdateEffectsCtx) -> None:
    dt = float(ctx.dt)
    for player in ctx.players:
        heading = float(player.heading)
        if not perk_active(player, PerkId.KINETIC_DISCIPLINE):
            player.kinetic_charge = 0.0
            player.kinetic_prev_heading = heading
            continue

        delta = (heading - float(player.kinetic_prev_heading) + math.pi) % math.tau - math.pi
        turn_rate = abs(delta) / dt if dt > 0.0 else 0.0
        player.kinetic_prev_heading = heading

        is_moving = float(player.move_speed) > MOVE_EPSILON
        if is_moving and turn_rate <= TURN_RATE_LIMIT:
            player.kinetic_charge = min(1.0, float(player.kinetic_charge) + dt / RAMP_UP_SECONDS)
        else:
            player.kinetic_charge = max(0.0, float(player.kinetic_charge) - dt / RAMP_DOWN_SECONDS)
        player.kinetic_charge = float(f32(player.kinetic_charge))


def fill_fraction(player: PlayerState) -> float:
    """0.0..1.0 of the max damage bonus, for the direction-arrow overlay.

    Not raw charge - Perk Efficacy scales the actual bonus too
    (creatures/damage.py), so a stacked-efficacy build reaching the full 30%
    bonus at a lower charge should still read as a fully-filled arrow.
    """

    if not perk_active(player, PerkId.KINETIC_DISCIPLINE):
        return 0.0
    fraction = float(player.kinetic_charge) * float(player.stats.perk_efficacy)
    return max(0.0, min(1.0, fraction))


HOOKS = PerkHooks(
    perk_id=PerkId.KINETIC_DISCIPLINE,
    effects_steps=(update_kinetic_discipline,),
)
