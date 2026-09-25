from __future__ import annotations

from ..game_modes import GameMode
from ..persistence.save_status import GameStatus
from ..quests.level import QuestLevel
from ..sim.state_types import PERK_COUNT_SIZE, GameplayState, PlayerState
from .helpers import perk_count_get
from .ids import PERK_BY_ID, PERK_MASTERY_CONCRETE_IDS, PerkFlags, PerkId


def build_perk_availability(*, status: GameStatus | None) -> list[bool]:
    """Every perk is unlocked, regardless of quest progress.

    Not native: the mod's roguelite direction drops native quest-gated perk
    unlocks entirely - `status` is kept in the signature for existing callers
    but no longer gates anything here. `ANTIPERK` stays excluded - it's a
    hidden placeholder, not real content. `ANXIOUS_LOADER` and `FINAL_REVENGE`
    are disabled by design decision (weak/unfun, needs a rework), and
    `BANE_OF_LEGENDS` because Pact of the Slayer (meta/relics_impl/
    slayer_pact.py) now provides it as a relic - all kept in the enum/tables
    so existing picks in old saves/replays still resolve, just never offered
    again. The four concrete masteries (`PERK_MASTERY_CONCRETE_IDS`)
    are excluded the same way - they're only reachable through WEAPON_MASTERY's
    own resolution (perks/selection.py), never offered as their own pool entry.
    """
    _ = status
    available = [False] * PERK_COUNT_SIZE
    for perk_id in PERK_BY_ID:
        available[int(perk_id)] = True
    available[int(PerkId.ANTIPERK)] = False
    available[int(PerkId.ANXIOUS_LOADER)] = False
    available[int(PerkId.FINAL_REVENGE)] = False
    available[int(PerkId.BANE_OF_LEGENDS)] = False
    for concrete_id in PERK_MASTERY_CONCRETE_IDS:
        available[int(concrete_id)] = False
    return available


def prepare_perk_availability(state: GameplayState) -> None:
    state.perk_available[:] = build_perk_availability(status=state.status)


def perk_can_offer(
    state: GameplayState, player: PlayerState, perk_id: PerkId, *, game_mode: GameMode, player_count: int,
) -> bool:
    """Return whether `perk_id` is eligible for selection.

    Modeled after `perk_can_offer` (0x0042fb10).
    """

    # Hardcore quest 2-10 blocks poison-related perks.
    if (
        game_mode == GameMode.QUESTS
        and state.hardcore
        and state.quest_level == QuestLevel(2, 10)
        and perk_id in (PerkId.POISON_BULLETS, PerkId.VEINS_OF_POISON, PerkId.PLAGUEBEARER)
    ):
        return False

    # Not native: Weapon Mastery has nothing left to resolve into once the
    # player owns all four concrete masteries.
    if perk_id == PerkId.WEAPON_MASTERY and all(
        perk_count_get(player, concrete_id) > 0 for concrete_id in PERK_MASTERY_CONCRETE_IDS
    ):
        return False

    meta = PERK_BY_ID.get(perk_id)
    if meta is None:
        return False

    flags = meta.flags
    # Native `perk_can_offer` treats these metadata bits as allow-lists for
    # specific runtime modes, not "only in this mode":
    # - in quest mode, offered perks must have bit 0x1 set
    # - in multiplayer, offered perks must have bit 0x2 set
    # The native branch is specifically `player_count == 2`; unsupported
    # higher counts fall through without applying the two-player allow-list.
    if game_mode == GameMode.QUESTS and (flags & PerkFlags.QUEST_MODE_ALLOWED) == 0:
        return False
    if player_count == 2 and (flags & PerkFlags.MULTIPLAYER_ALLOWED) == 0:
        return False

    return not (meta.prereq and any(perk_count_get(player, req) <= 0 for req in meta.prereq))
