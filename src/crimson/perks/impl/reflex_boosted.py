from __future__ import annotations

from ...math_parity import f32, x87_pc24_mul
from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.hook_types import PerkHooks


def apply_reflex_boosted_dt(*, dt: float, players: list[PlayerState]) -> float:
    """Apply Reflex Boosted dt scaling from perk effects."""
    if float(dt) <= 0.0:
        return float(dt)
    if not players:
        return float(dt)
    if not perk_active(players[0], PerkId.REFLEX_BOOSTED):
        return float(dt)
    # Not native: Perk Efficacy deepens the slowdown (a smaller multiplier),
    # floored well short of 0 so time never fully stops.
    efficacy = float(players[0].stats.perk_efficacy)
    slow_mult = max(0.1, 1.0 - 0.1 * efficacy)
    return float(x87_pc24_mul(f32(float(dt)), f32(slow_mult)))


HOOKS = PerkHooks(
    perk_id=PerkId.REFLEX_BOOSTED,
    world_dt_step=apply_reflex_boosted_dt,
)
