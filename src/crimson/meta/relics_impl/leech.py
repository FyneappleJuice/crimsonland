from __future__ import annotations

"""Leech relic (not native).

Every hit heals you a % of the damage it dealt; every kill costs you a flat
% of your *current* HP, unconditionally (no rate limit - a multi-kill AoE/
pierce hit costs once per kill it scores, on purpose). Current HP rather than
max HP so the cost is self-limiting instead of a flat number that can chain
into a death spiral.

The kill cost is a straight HP loss, not damage taken - it deliberately
bypasses player_take_damage, so nothing that reacts to a hit (Thick Skinned,
dodge, shields, Highlander's roll, Gathering Winds' stack loss, pain SFX /
aim jitter) fires once per kill. The heal-per-hit is the only tier-scaled side; the kill
cost is a fixed constant at every tier - same "constant cost, scaling
reward" shape as every other pact relic, so High always beats Low.
"""

from ...math_parity import f32, x87_pc24_add, x87_pc24_mul, x87_pc24_sub
from ...perks.impl.soul_tether import soul_tether_clamp_and_gain
from ...sim.state_types import PlayerState
from ..relics import RelicId, relic_owned

LEECH_HP_COST_PER_KILL = 0.05  # 5% of current HP, fixed at every tier

_HEAL_PCT_BY_RELIC: dict[int, float] = {
    RelicId.LEECH_LOW: 0.0084,
    RelicId.LEECH_MEDIUM: 0.014,
    RelicId.LEECH_HIGH: 0.021,
}


def _active_relic_id() -> int | None:
    for rid in _HEAL_PCT_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def heal_on_hit(player: PlayerState, damage_dealt: float) -> None:
    """Called from creatures/damage.py's shooter-perk block, after the final
    resolved damage is known (post-variance), once per damage instance."""
    relic_id = _active_relic_id()
    if relic_id is None or float(damage_dealt) <= 0.0:
        return
    heal = float(x87_pc24_mul(f32(float(damage_dealt)), _HEAL_PCT_BY_RELIC[relic_id]))
    player.health = soul_tether_clamp_and_gain(
        player, float(x87_pc24_add(f32(float(player.health)), heal)),
    )


def hp_cost_on_kill(player: PlayerState) -> None:
    """Called from creatures/runtime.py's kill-confirmation hook."""
    if _active_relic_id() is None:
        return
    cost = float(x87_pc24_mul(f32(float(player.health)), LEECH_HP_COST_PER_KILL))
    player.health = max(0.0, float(x87_pc24_sub(f32(float(player.health)), cost)))


__all__ = ["LEECH_HP_COST_PER_KILL", "heal_on_hit", "hp_cost_on_kill"]
