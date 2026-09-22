from __future__ import annotations

import random as _random

from ..game_modes import GameMode
from ..persistence.save_status import GameStatus
from ..quests.level import QuestLevel
from ..rng_caller_static import RngCallerStatic
from ..sim.state_types import GameplayState
from ..weapon_usage import weapon_usage_slot_for_weapon_id
from ..weapons import WEAPON_TABLE, WeaponId

WEAPON_DROP_ID_COUNT = 0x21  # weapon ids 1..33
WEAPON_AVAILABLE_COUNT = max(int(entry.weapon_id) for entry in WEAPON_TABLE) + 1

# Rewrite-only: Tenet Gun is a meme weapon (weapons.py) - its id (54) sits
# well outside the 1-33 range native `weapon_pick_random_available` rolls
# over, so instead of being "just another weapon" like Evil Scythe/Raygun, it
# gets one extra, extremely unlikely, separately-rolled chance to preempt
# whatever that roll would have picked. Rolled on a private RNG (not
# `state.rng`), same reasoning as the crit roll in weapon_runtime/crit.py -
# purely cosmetic build variance, not run state, so it must not perturb
# replay determinism or the RNG-trace tests that script the sim stream's
# exact draw sequence.
_TENET_GUN_RARE_DROP_CHANCE = 1.0 / 400.0
_TENET_GUN_RARE_RNG = _random.Random(0x7E7E7)

# Fork: the rewrite-only weapons, folded into the main roster - always
# available in every mode so they drop from the normal Weapon bonus.
# Evil Scythe/Arc Gun (RAYGUN) are temporarily pulled out via INACTIVE_WEAPON_IDS
# below while they get balanced further - only Tenet Gun needs to stay here,
# since its id sits outside the 1-33 range the second loop below covers.
_FORK_ROSTER_WEAPON_IDS: tuple[WeaponId, ...] = (WeaponId.TENET_GUN,)

# Weapons kept out of the normal Weapon-bonus drop pool entirely, regardless
# of unlock progress:
#   - Shrinkifier 5K / Blade Gun are native special-handout weapons. Survival
#     hands these out itself via scripted triggers (idling too long, dying
#     near your own graveyard - see gameplay.py::survival_update_weapon_handouts)
#     and immediately revokes them back to Pistol if they show up any other
#     way (gameplay.py::survival_enforce_reward_weapon_guard). Letting them
#     roll from a normal Weapon bonus just means an instant, confusing revert.
#   - Spider Plasma is an enemy-only weapon stat block (the Spider Plasma
#     Shooter creature's own attack, weapons.py:505) - never meant to be a
#     player pickup at all.
_NON_PLAYER_WEAPON_IDS: tuple[WeaponId, ...] = (
    WeaponId.SHRINKIFIER_5K,
    WeaponId.BLADE_GUN,
    WeaponId.SPIDER_PLASMA,
)

# Rewrite-only: weapons shelved out of the active roster while the crit/build
# design settles (redundant Flamethrower reskins, novelty/no-damage guns, and
# the plain SMG). Not deleted - still in WEAPON_TABLE, still fireable via the
# debug weapon cycle (modes/survival_mode.py, modes/quest_mode.py) - just
# excluded from drops/unlocks and, for Shrinkifier 5K, its native scripted
# Survival handout (see gameplay.py::survival_update_weapon_handouts). Move an
# id back out of this tuple to reactivate it.
#
# Evil Scythe and Arc Gun (RAYGUN) are here temporarily while they get
# balanced further - move them back to _FORK_ROSTER_WEAPON_IDS to reactivate.
INACTIVE_WEAPON_IDS: tuple[WeaponId, ...] = (
    WeaponId.SUBMACHINE_GUN,
    WeaponId.BLOW_TORCH,
    WeaponId.HR_FLAMER,
    WeaponId.SHRINKIFIER_5K,
    WeaponId.PLAGUE_SPREADER_GUN,
    WeaponId.BUBBLEGUN,
    WeaponId.RAINBOW_GUN,
    WeaponId.EVIL_SCYTHE,
    WeaponId.RAYGUN,
)


def build_weapon_availability(
    *,
    status: GameStatus | None,
    game_mode: GameMode,
) -> list[bool]:
    """Every droppable weapon is unlocked, regardless of quest progress or mode.

    Not native: the mod's roguelite direction drops native quest-gated weapon
    unlocks entirely - `status`/`game_mode` are kept in the signature for
    existing callers but no longer gate anything here.
    """
    _ = status, game_mode
    available = [False] * WEAPON_AVAILABLE_COUNT

    for weapon_id in _FORK_ROSTER_WEAPON_IDS:
        if 0 <= int(weapon_id) < len(available):
            available[int(weapon_id)] = True

    # Skip the cut / unimplemented stubs (e.g. Flameburst) that would crash when fired.
    from .fire_recipes import fireable_weapon_ids

    fireable = fireable_weapon_ids()
    for weapon_id in range(1, min(WEAPON_DROP_ID_COUNT + 1, WEAPON_AVAILABLE_COUNT)):
        wid = WeaponId(weapon_id)
        if wid in fireable and wid not in _NON_PLAYER_WEAPON_IDS and wid not in INACTIVE_WEAPON_IDS:
            available[weapon_id] = True
    return available


def prepare_weapon_availability(state: GameplayState) -> None:
    state.weapon_available[:] = build_weapon_availability(
        status=state.status,
        game_mode=state.game_mode,
    )


def weapon_pick_random_available(state: GameplayState) -> WeaponId:
    """Select a random available weapon id.

    Port of `weapon_pick_random_available` (0x00452cd0).
    """

    status = state.status
    suppress_ion_cannon = state.game_mode == GameMode.QUESTS and state.quest_level == QuestLevel(5, 10)
    has_eligible_weapon = any(
        weapon_id < len(state.weapon_available)
        and state.weapon_available[weapon_id]
        and not (suppress_ion_cannon and weapon_id == WeaponId.ION_CANNON)
        for weapon_id in range(1, WEAPON_DROP_ID_COUNT + 1)
    )
    if not has_eligible_weapon:
        raise RuntimeError("weapon availability has no eligible drop; call prepare_weapon_availability()")

    tenet_gun_id = int(WeaponId.TENET_GUN)
    if tenet_gun_id < len(state.weapon_available) and state.weapon_available[tenet_gun_id]:
        if _TENET_GUN_RARE_RNG.random() < _TENET_GUN_RARE_DROP_CHANCE:
            return WeaponId.TENET_GUN

    while True:
        base_rand = state.rng.rand_tagged(RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_PICK)
        weapon_id = WeaponId(base_rand % WEAPON_DROP_ID_COUNT + 1)

        # Bias: used weapons have a 50% chance to reroll once.
        if status is not None:
            usage_slot = weapon_usage_slot_for_weapon_id(weapon_id)
            if (  # noqa: SIM102 - preserve the native reroll gate and RNG draw shape
                usage_slot is not None and status.weapon_usage_count_slot(usage_slot) != 0
            ):
                if (state.rng.rand_tagged(RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_REROLL_GATE) & 1) == 0:
                    base_rand = state.rng.rand_tagged(RngCallerStatic.WEAPON_PICK_RANDOM_AVAILABLE_REROLL_PICK)
                    weapon_id = WeaponId(base_rand % WEAPON_DROP_ID_COUNT + 1)

        if not (0 <= weapon_id < len(state.weapon_available)):
            continue
        if not state.weapon_available[weapon_id]:
            continue

        # Quest 5-10 special-case: suppress Ion Cannon.
        if suppress_ion_cannon and weapon_id == WeaponId.ION_CANNON:
            continue

        return weapon_id
