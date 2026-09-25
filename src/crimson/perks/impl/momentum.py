from __future__ import annotations

"""Not native: Domino Effect (Momentum) - internal cooldown.

A kill fires a free shot at the nearest other creature (creatures/runtime.py's
_fire_momentum_shot). On its own that procs on every single kill, which in a
dense horde is a near-constant stream of free shots however hard each one is
penalized - so after a shot fires, further kills don't fire another until
MOMENTUM_COOLDOWN has passed.

The player and their Hollow Form clone each have their own cooldown - the
clone is its own shooter, so its kills don't lock out the player's and vice
versa. Both timers live on the player (the clone's snapshot is rebuilt on
every spawn, so it can't hold state across clones). This file decays them;
the death handler checks and starts them.
"""

from ...math_parity import f32, x87_pc24_sub
from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

MOMENTUM_COOLDOWN = 0.4


def momentum_cooldown_remaining(player: PlayerState, *, by_clone: bool) -> float:
    if by_clone:
        return float(player.hollow_form_momentum_cooldown_timer)
    return float(player.momentum_cooldown_timer)


def start_momentum_cooldown(player: PlayerState, *, by_clone: bool) -> None:
    if by_clone:
        player.hollow_form_momentum_cooldown_timer = MOMENTUM_COOLDOWN
    else:
        player.momentum_cooldown_timer = MOMENTUM_COOLDOWN


def _decay(timer: float, dt: float) -> float:
    if timer <= 0.0:
        return timer
    return max(0.0, float(x87_pc24_sub(f32(timer), dt)))


def update_momentum_cooldown(ctx: PerksUpdateEffectsCtx) -> None:
    dt = f32(float(ctx.dt))
    for player in ctx.players:
        if not perk_active(player, PerkId.MOMENTUM):
            player.momentum_cooldown_timer = 0.0
            player.hollow_form_momentum_cooldown_timer = 0.0
            continue
        player.momentum_cooldown_timer = _decay(player.momentum_cooldown_timer, dt)
        player.hollow_form_momentum_cooldown_timer = _decay(player.hollow_form_momentum_cooldown_timer, dt)


HOOKS = PerkHooks(
    perk_id=PerkId.MOMENTUM,
    effects_steps=(update_momentum_cooldown,),
)
