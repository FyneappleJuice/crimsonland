from __future__ import annotations

"""Leech relic (not native).

Every hit leeches a % of the damage it dealt, healed as a drip over
LEECH_HEAL_DURATION seconds rather than all at once; every kill costs you a
flat % of your *current* HP, unconditionally (no rate limit - a multi-kill
AoE/pierce hit costs once per kill it scores, on purpose). Current HP rather
than max HP so the cost is self-limiting instead of a flat number that can
chain into a death spiral.

Each hit's leech is its own independent instance (its own total amount, its
own LEECH_HEAL_DURATION-second timer) - instances never pool into or refresh
each other, so a burst of hits (a shotgun blast, a piercing bolt through a
pack) queues up several drips ticking down in parallel, same shape as
Fortify's stack instances but without the pooling window.

The kill cost is a straight HP loss, not damage taken - it deliberately
bypasses player_take_damage, so nothing that reacts to a hit (Thick Skinned,
dodge, shields, Highlander's roll, Gathering Winds' stack loss, pain SFX /
aim jitter) fires once per kill.
"""

from ...math_parity import f32, x87_pc24_mul, x87_pc24_sub
from ...perks.impl.death_clock import blocks_health_change as _death_clock_blocks_health_change
from ...perks.impl.soul_tether import soul_tether_clamp_and_gain
from ...sim.state_types import PlayerState
from ..relics import RelicId, relic_owned

LEECH_HP_COST_PER_KILL = 0.05  # 5% of current HP
LEECH_HEAL_DURATION = 5.0  # seconds each hit's leeched heal drips over

_HEAL_PCT_BY_RELIC: dict[int, float] = {
    RelicId.LEECH_LOW: 0.00756,
}


def _active_relic_id() -> int | None:
    for rid in _HEAL_PCT_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def heal_on_hit(player: PlayerState, damage_dealt: float) -> None:
    """Called from creatures/damage.py's shooter-perk block, after the final
    resolved damage is known (post-variance), once per damage instance.
    Queues a new heal-over-time instance rather than healing immediately -
    see tick()."""
    relic_id = _active_relic_id()
    if relic_id is None or float(damage_dealt) <= 0.0:
        return
    total_heal = float(x87_pc24_mul(f32(float(damage_dealt)), _HEAL_PCT_BY_RELIC[relic_id]))
    if total_heal <= 0.0:
        return
    player.leech_pending_heal.append(total_heal)
    player.leech_pending_timers.append(LEECH_HEAL_DURATION)


def tick(player: PlayerState, dt: float) -> None:
    """Drip every active leech instance's share of its total heal for this
    tick, and drop instances once their timer runs out. Called unconditionally
    every tick (relics aren't gated behind perk_active), same as Fortify's own
    tick - so an instance queued while the relic was owned keeps draining even
    if the relic is somehow unequipped mid-run."""
    if not player.leech_pending_timers:
        return
    dt = float(dt)
    kept_heal: list[float] = []
    kept_timers: list[float] = []
    for total_heal, remaining in zip(player.leech_pending_heal, player.leech_pending_timers):
        tick_heal = float(total_heal) * dt / LEECH_HEAL_DURATION
        player.health = soul_tether_clamp_and_gain(
            player, float(f32(float(player.health) + tick_heal)),
        )
        remaining -= dt
        if remaining > 0.0:
            kept_heal.append(total_heal)
            kept_timers.append(remaining)
    player.leech_pending_heal = kept_heal
    player.leech_pending_timers = kept_timers


def hp_cost_on_kill(player: PlayerState) -> None:
    """Called from creatures/runtime.py's kill-confirmation hook."""
    if _active_relic_id() is None:
        return
    if _death_clock_blocks_health_change(player):
        # Not native: this is a direct subtraction, not routed through
        # soul_tether_clamp_and_gain like the heal above - Death Clock has to
        # guard it separately so its own drain stays the only thing moving
        # health while it's active (a "lifeloss not from Death Clock" is
        # exactly what it's meant to block, same as a lifegain).
        return
    cost = float(x87_pc24_mul(f32(float(player.health)), LEECH_HP_COST_PER_KILL))
    player.health = max(0.0, float(x87_pc24_sub(f32(float(player.health)), cost)))


__all__ = ["LEECH_HEAL_DURATION", "LEECH_HP_COST_PER_KILL", "heal_on_hit", "hp_cost_on_kill", "tick"]
