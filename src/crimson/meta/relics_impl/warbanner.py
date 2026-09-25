from __future__ import annotations

"""War Banner relic (not native, modelled on Risk of Rain 2's Warbanner).

Every level up plants a banner where the player stands; banners stay for the
rest of the run. While inside any of their banners' radius (75/125/175 for
Low/Medium/High) the player gets +30% attack speed and +30% movement speed,
each its own multiplicative bucket. Overlapping banners don't stack.

No downside: the upside is only worth anything while you hold ground next to
your banners, which is the cost.

Attack speed scales shot_cooldown's decay (gameplay.py's
advance_weapon_shot_cooldown); for whole-clip dump weapons (Mini-Rocket
Swarmers), whose next volley is gated by the reload, it scales the reload's
decay too (advance_weapon_reload). Banners live on the PlayerState, so a
Hollow Form clone - a snapshot of the player - gets the buff standing in them.
"""

from typing import TYPE_CHECKING

from grim.geom import Vec2

from ..relics import RelicId, relic_owned

if TYPE_CHECKING:
    from ...sim.state_types import PlayerState

WARBANNER_ATTACK_SPEED_MULT = 1.30
WARBANNER_MOVE_SPEED_MULT = 1.30

_RADIUS_BY_RELIC: dict[int, float] = {
    RelicId.WARBANNER_LOW: 75.0,
    RelicId.WARBANNER_MEDIUM: 125.0,
    RelicId.WARBANNER_HIGH: 175.0,
}


def _active_relic_id() -> int | None:
    for rid in _RADIUS_BY_RELIC:
        if relic_owned(rid):
            return rid
    return None


def radius() -> float:
    relic_id = _active_relic_id()
    return 0.0 if relic_id is None else _RADIUS_BY_RELIC[relic_id]


def plant_on_level_up(player: PlayerState) -> None:
    """Called from gameplay.py's survival_check_level_up on every level gained."""
    if _active_relic_id() is None:
        return
    player.warbanner_positions.append(Vec2(float(player.pos.x), float(player.pos.y)))


def in_banner(player: PlayerState) -> bool:
    r = radius()
    if r <= 0.0 or not player.warbanner_positions:
        return False
    r_sq = r * r
    px, py = float(player.pos.x), float(player.pos.y)
    for pos in player.warbanner_positions:
        dx = float(pos.x) - px
        dy = float(pos.y) - py
        if dx * dx + dy * dy <= r_sq:
            return True
    return False


def attack_speed_mult(player: PlayerState) -> float:
    return WARBANNER_ATTACK_SPEED_MULT if in_banner(player) else 1.0


def move_speed_mult(player: PlayerState) -> float:
    return WARBANNER_MOVE_SPEED_MULT if in_banner(player) else 1.0


__all__ = [
    "WARBANNER_ATTACK_SPEED_MULT",
    "WARBANNER_MOVE_SPEED_MULT",
    "attack_speed_mult",
    "in_banner",
    "move_speed_mult",
    "plant_on_level_up",
    "radius",
]
