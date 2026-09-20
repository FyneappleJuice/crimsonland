from __future__ import annotations

"""Not native: Soul Tether.

Any heal that would push health past 100 instead redirects the overflow into
a shield (render/world/player_status.py draws it as a blue overlay on the
health ring). The shield absorbs incoming damage before health does
(player_damage.py), and degenerates at SOUL_TETHER_DECAY_RATE/s starting
SOUL_TETHER_DECAY_DELAY seconds after it was last topped up.
"""

from ...sim.state_types import PlayerState
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

SOUL_TETHER_DECAY_DELAY = 5.0
SOUL_TETHER_DECAY_RATE = 20.0


def soul_tether_clamp_and_gain(player: PlayerState, raw_new_health: float) -> float:
    """Clamp a heal result to 100, same as every existing heal call site, but
    redirect any overflow into the shield instead of discarding it when Soul
    Tether is active. Callers pass the *unclamped* would-be health."""
    if perk_active(player, PerkId.SOUL_TETHER) and raw_new_health > 100.0:
        overflow = raw_new_health - 100.0
        player.soul_tether_shield = float(player.soul_tether_shield) + overflow
        player.soul_tether_decay_delay_timer = SOUL_TETHER_DECAY_DELAY
        return 100.0
    return min(100.0, raw_new_health)


def soul_tether_absorb(player: PlayerState, damage: float) -> float:
    """Take `damage` off the shield first, returning whatever's left to hit
    health. A no-op (returns damage unchanged) without the perk or shield."""
    if not perk_active(player, PerkId.SOUL_TETHER):
        return damage
    shield = float(player.soul_tether_shield)
    if shield <= 0.0 or damage <= 0.0:
        return damage
    absorbed = min(shield, damage)
    player.soul_tether_shield = shield - absorbed
    return damage - absorbed


def update_soul_tether_decay(ctx: PerksUpdateEffectsCtx) -> None:
    dt = float(ctx.dt)
    for player in ctx.players:
        if not perk_active(player, PerkId.SOUL_TETHER):
            player.soul_tether_shield = 0.0
            player.soul_tether_decay_delay_timer = 0.0
            continue
        if player.soul_tether_shield <= 0.0:
            continue

        remaining_dt = dt
        if player.soul_tether_decay_delay_timer > 0.0:
            consumed = min(float(player.soul_tether_decay_delay_timer), remaining_dt)
            player.soul_tether_decay_delay_timer = float(player.soul_tether_decay_delay_timer) - consumed
            remaining_dt -= consumed

        # A large single dt can exhaust the delay and still have time left over
        # to actually decay the shield in the same tick - carry it through
        # instead of only ever consuming the delay.
        if remaining_dt > 0.0 and player.soul_tether_decay_delay_timer <= 0.0:
            player.soul_tether_shield = max(
                0.0,
                float(player.soul_tether_shield) - SOUL_TETHER_DECAY_RATE * remaining_dt,
            )


HOOKS = PerkHooks(
    perk_id=PerkId.SOUL_TETHER,
    effects_steps=(update_soul_tether_decay,),
)
