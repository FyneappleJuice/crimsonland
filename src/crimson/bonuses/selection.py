from __future__ import annotations

import random as _random
from typing import TYPE_CHECKING

from ..game_modes import GameMode
from ..perks import PerkId
from ..perks.helpers import perk_active
from ..rng_caller_static import RngCallerStatic
from .ids import BONUS_BY_ID, BonusId

if TYPE_CHECKING:
    from ..gameplay import GameplayState
    from ..sim.state_types import PlayerState
    from .pool import BonusPool


def _bonus_enabled(bonus_id: BonusId) -> bool:
    meta = BONUS_BY_ID.get(bonus_id)
    if meta is None:
        return False
    return meta.bonus_id != BonusId.UNUSED


def _bonus_pick_suppressed(
    *,
    state: GameplayState,
    players: list[PlayerState],
    bonus_id: BonusId,
    has_fire_bullets_drop: bool,
) -> bool:
    if not _bonus_enabled(bonus_id):
        return True
    # Fork: Energizer is removed from the game. The native roll that would pick
    # it still runs (its RNG draw is consumed) so the pick sequence stays
    # deterministic; the result is just rerolled to another bonus.
    if bonus_id == BonusId.ENERGIZER:
        return True
    if state.shock_chain_links_left > 0 and bonus_id == BonusId.SHOCK_CHAIN:
        return True
    if bonus_id == BonusId.FREEZE and state.bonuses.freeze > 0.0:
        return True
    # Native reads both shield slots directly, but its global perk helper only
    # reads player 0. Preserve that asymmetry even if the port has more players.
    if bonus_id == BonusId.SHIELD and any(player.shield_timer > 0.0 for player in players[:2]):
        return True
    if bonus_id == BonusId.WEAPON and has_fire_bullets_drop:
        return True
    primary_player = players[0] if players else None
    if (
        bonus_id == BonusId.WEAPON
        and primary_player is not None
        and perk_active(primary_player, PerkId.MY_FAVOURITE_WEAPON)
    ):
        return True
    if bonus_id == BonusId.MEDIKIT and primary_player is not None and perk_active(primary_player, PerkId.DEATH_CLOCK):
        return True
    level = state.quest_level
    if state.game_mode != GameMode.QUESTS or level is None or level.minor != 10:
        return False

    major = level.major
    if bonus_id == BonusId.NUKE:
        return major in (2, 4, 5) or (state.hardcore and major == 3)
    if bonus_id == BonusId.FREEZE:
        return major == 4 or (state.hardcore and major == 2)
    return False


# Rewrite-only bonuses folded into the native table's dead-space rolls. Add a
# new droppable rewrite-only bonus by appending to this tuple - nothing else
# in this file needs to change.
_NONNATIVE_BONUS_POOL: tuple[BonusId, ...] = (
    BonusId.PROJECTILE_FORK,
    BonusId.BLADE,
    BonusId.EXPLOSIVE_PAYLOAD,
    BonusId.PLASMA_OVERLOAD,
    BonusId.ION_OVERLOAD,
)

# Not native: which rewrite-only bonus fills a dead-space roll has no native
# sequence to match, so it gets its own private stream instead of consuming
# the shared lockstep rng.
_MAPS_BONUS_RNG = _random.Random(0xBADD5107)


def _resolve_native_roll(roll: int) -> BonusId | None:
    """Map one `d162` roll to a native bonus id, UNUSED for dead space, or
    None for roll 14 (Weapon-vs-Energizer needs a live sub-roll, so it's
    handled separately by the caller and never resolved statically here).

    Pure port of `bonus_pick_random_type`'s (0x412470) table-walk:
    - roll 1..13 -> Points
    - roll 14 -> caller's job (Weapon or Energizer sub-roll)
    - roll 15..162 -> ids 3 (Weapon) through 14 (Fire Bullets), 10 rolls
      each; the remaining tail (28 of the 162 rolls) was dead space in the
      original game - it always rerolled there, byte-for-byte.
    """
    if roll <= 13:
        return BonusId.POINTS
    if roll == 14:
        return None
    bucket_offset = roll - 14
    bonus_value = int(BonusId.WEAPON)
    while bucket_offset > 10:
        bucket_offset -= 10
        bonus_value += 1
        if bonus_value >= 15:
            return BonusId.UNUSED
    return BonusId(bonus_value)


# Precomputed once: rolls 1..162 (index 0..161) -> native bonus id, UNUSED for
# the 28 dead-space rolls, or None at index 13 (roll 14, resolved live by the
# caller). Same exact mapping as the old inline bucket walk, just computed
# once instead of re-walked on every single pick - and now something you can
# print and actually look at instead of having to hand-trace the loop.
_NATIVE_ROLL_TABLE: tuple[BonusId | None, ...] = tuple(_resolve_native_roll(roll) for roll in range(1, 163))


def bonus_pick_random_type(pool: BonusPool, state: GameplayState, players: list[PlayerState]) -> BonusId:
    has_fire_bullets_drop = any(entry.bonus_id == BonusId.FIRE_BULLETS and not entry.picked for entry in pool.entries)

    for _ in range(101):
        roll = state.rng.rand_tagged(RngCallerStatic.BONUS_PICK_RANDOM_TYPE_ROLL) % 162 + 1
        if roll == 14:
            if (state.rng.rand_tagged(RngCallerStatic.BONUS_PICK_RANDOM_TYPE_ENERGIZER) & 0x3F) == 0:
                bonus_id = BonusId.ENERGIZER
            else:
                bonus_id = BonusId.WEAPON
        else:
            bonus_id = _NATIVE_ROLL_TABLE[roll - 1]

        if bonus_id == BonusId.UNUSED:
            # Native always rerolls a dead-space hit (every native mode -
            # Survival, Rush, Quests - reroots byte-for-byte). The rewrite-only
            # pool opts in via `fork_bonus_in_pool` and spends that dead roll
            # on a rewrite-only bonus instead, picked uniformly - a small
            # extra rng draw with no parity requirement to preserve.
            if state.fork_bonus_in_pool:
                bonus_id = _MAPS_BONUS_RNG.choice(_NONNATIVE_BONUS_POOL)
            else:
                continue

        if _bonus_pick_suppressed(
            state=state,
            players=players,
            bonus_id=bonus_id,
            has_fire_bullets_drop=has_fire_bullets_drop,
        ):
            continue
        return bonus_id
    return BonusId.POINTS
