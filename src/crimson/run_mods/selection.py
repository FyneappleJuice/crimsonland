from __future__ import annotations

import random as _random
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..creatures.damage_types import CreatureDamageType
from ..perks.helpers import perk_active
from ..perks.ids import PerkId
from ..sim.state_types import GameplayState, PlayerState
from ..weapon_runtime.tags import WeaponArchetype, weapon_tags
from .ids import RUN_MOD_HIDDEN_FROM_POOL, RunModId
from .runtime.apply import run_mod_apply, run_mod_apply_penalty
from .state import RunModChoice, RunModChoiceKind, RunModSelectionState

if TYPE_CHECKING:
    from ..creatures.runtime import CreatureState

RUN_MOD_CHOICE_COUNT = 3
# Most choices an offer can ever show (Perk Master) - also the replay codec's
# bound on RunModPickCommand.choice_index.
RUN_MOD_MAX_CHOICE_COUNT = RUN_MOD_CHOICE_COUNT + 2

# The pool `run_mod_generate_choices` actually draws from - everything except
# the hidden sub-roll targets (see ids.py's RUN_MOD_HIDDEN_FROM_POOL).
_VISIBLE_POOL: tuple[RunModId, ...] = tuple(rid for rid in RunModId if rid not in RUN_MOD_HIDDEN_FROM_POOL)

# DAMAGE_TYPE_BOOST's sub-roll targets, and which weapon damage type each one
# matches (for the 3x current-weapon weight).
_DAMAGE_TYPE_SUB_ROLL: dict[CreatureDamageType, RunModId] = {
    CreatureDamageType.BULLET: RunModId.BULLET_DAMAGE,
    CreatureDamageType.PLASMA: RunModId.PLASMA_DAMAGE,
    CreatureDamageType.ENERGY: RunModId.ENERGY_DAMAGE,
    CreatureDamageType.ION: RunModId.ION_DAMAGE,
    CreatureDamageType.FIRE: RunModId.FIRE_DAMAGE,
    CreatureDamageType.EXPLOSION: RunModId.EXPLOSION_DAMAGE,
}

# WEAPON_TYPE_BOOST's sub-roll targets, same idea, keyed by archetype.
# Not native: SMG and MELEE are deliberately excluded - their only weapons
# (Submachine Gun, Evil Scythe) are both currently shelved/inactive, so
# rolling either one would offer a damage bonus with nothing left to apply
# to. RunModId.SMG_DAMAGE/MELEE_DAMAGE stay defined (same reason
# ANXIOUS_LOADER stays in PerkId - old replays that already resolved a pick
# to one of them must still decode), just unreachable from this pool now.
_WEAPON_TYPE_SUB_ROLL: dict[WeaponArchetype, RunModId] = {
    WeaponArchetype.PISTOL: RunModId.PISTOL_DAMAGE,
    WeaponArchetype.RIFLE: RunModId.RIFLE_DAMAGE,
    WeaponArchetype.SHOTGUN: RunModId.SHOTGUN_DAMAGE,
    WeaponArchetype.MINIGUN: RunModId.MINIGUN_DAMAGE,
    WeaponArchetype.CANNON: RunModId.CANNON_DAMAGE,
    WeaponArchetype.FLAMETHROWER: RunModId.FLAMETHROWER_DAMAGE,
    WeaponArchetype.ARC: RunModId.ARC_DAMAGE,
}

# Current-weapon bias for the sub-rolls below: the entry matching whatever
# the player is currently holding is this many times as likely as every
# other entry.
_CURRENT_WEAPON_WEIGHT_BIAS = 3.0

# Wildcard (PerkId.WILDCARD): independently, per secondary slot - not once per
# offer - a 10% chance to become a real primary-perk offer instead, else a
# 20% chance to become a 3x/-1x upgraded combo. The two are mutually
# exclusive for a given slot; different slots in the same offer can each
# land on either outcome independently.
WILDCARD_REPLACE_CHANCE = 0.10
WILDCARD_UPGRADE_CHANCE = 0.20
# The upgraded slot's own bonus applies at this many stacks worth...
WILDCARD_UPGRADE_MULTIPLIER = 3
# ...and the penalty (a different, randomly chosen run mod, inverted) at 1.


def run_mod_choice_count(player: PlayerState) -> int:
    # Mirrors perk_choice_count's non-additive shape: Perk Master overrides
    # Perk Expert's bonus rather than stacking on top of it.
    if perk_active(player, PerkId.PERK_MASTER):
        return RUN_MOD_MAX_CHOICE_COUNT
    if perk_active(player, PerkId.PERK_EXPERT):
        return RUN_MOD_CHOICE_COUNT + 1
    return RUN_MOD_CHOICE_COUNT


def _run_mod_rng_for(state: GameplayState) -> _random.Random:
    # Not native: rewrite-only content. Seeded from the shared sim RNG's
    # current state (a read, not a draw) so the result is deterministic and
    # replay-safe without perturbing the native-parity `state.rng` sequence -
    # mirrors the project's private-RNG convention for rewrite-only content
    # that still needs per-run/per-call variety (see project memory on the
    # private-RNG migration away from fake RngCallerStatic tags).
    return _random.Random(int(state.rng.state))


def _weighted_sub_roll(
    rng: _random.Random,
    candidates: dict[object, RunModId],
    current_key: object,
) -> RunModId:
    """Pick one of `candidates`' values, weighting whichever entry matches
    `current_key` (the player's current damage type or archetype) 2x over
    every other entry."""

    ids = list(candidates.values())
    weights = [_CURRENT_WEAPON_WEIGHT_BIAS if key == current_key else 1.0 for key in candidates]
    return rng.choices(ids, weights=weights, k=1)[0]


def _resolve_meta_run_mod(run_mod_id: RunModId, *, players: list[PlayerState], rng: _random.Random) -> RunModId:
    """DAMAGE_TYPE_BOOST/WEAPON_TYPE_BOOST never apply directly - resolve to
    one of their hidden sub-targets here, weighted toward whatever weapon
    `players[0]` currently has equipped. Anything else passes through
    unchanged."""

    if not players:
        return run_mod_id
    weapon_id = players[0].weapon.weapon_id
    tags = weapon_tags(weapon_id)
    if run_mod_id == RunModId.DAMAGE_TYPE_BOOST:
        return _weighted_sub_roll(rng, _DAMAGE_TYPE_SUB_ROLL, tags.damage_type)
    if run_mod_id == RunModId.WEAPON_TYPE_BOOST:
        return _weighted_sub_roll(rng, _WEAPON_TYPE_SUB_ROLL, tags.archetype)
    return run_mod_id


def _wildcard_bonus_perks(state: GameplayState, player: PlayerState) -> list[PerkId]:
    """The already-generated, already-duplicate-free tail of this level-up's
    primary perk batch. `perks/selection.py::perk_generate_choices` always
    rolls a full 7-entry batch even when only `perk_choice_count(player)` of
    them are shown - the unused tail is exactly "the next eligible perks,
    picked after the main perk pull, guaranteed not to duplicate what's
    already offered" for free, with no extra RNG draw needed here."""

    from ..perks.selection import perk_choice_count

    perk_choices = state.perk_selection.choices
    if not perk_choices:
        return []
    visible = int(perk_choice_count(player))
    return list(perk_choices[visible:7])


def run_mod_generate_choices(
    state: GameplayState,
    *,
    count: int | None = None,
    player: PlayerState | None = None,
    players: list[PlayerState] | None = None,
) -> list[RunModChoice]:
    """Generate run-mod choices. No duplicates within one offer - a run mod
    can still be picked again on a later level-up, it just won't appear twice
    in the same 3-choice list. Only draws from the visible pool - the hidden
    per-damage-type/per-archetype ids are never offered directly as their own
    pool entries.

    DAMAGE_TYPE_BOOST/WEAPON_TYPE_BOOST are resolved to a concrete hidden id
    right here, at generation time - not at pick time - so the displayed
    choice already shows the real bonus (e.g. "+3% Plasma Damage"), never a
    generic "Elemental Affinity" placeholder the player has to click to find
    out. Since DAMAGE_TYPE_BOOST/WEAPON_TYPE_BOOST each appear at most once
    per offer (sampled without replacement) and their resolved target sets
    are disjoint from each other and from the rest of the visible pool,
    resolving them can never introduce a duplicate into the same offer.

    If `player` owns Wildcard, each resolved slot independently rolls a
    replace/upgrade outcome (see the module-level WILDCARD_* constants).

    `count` wins if given; otherwise derived from `player` (Perk Expert/
    Master), falling back to the flat default with no player."""

    if count is None:
        count = run_mod_choice_count(player) if player is not None else RUN_MOD_CHOICE_COUNT
    rng = _run_mod_rng_for(state)
    raw = rng.sample(_VISIBLE_POOL, min(int(count), len(_VISIBLE_POOL)))
    resolved_ids = [_resolve_meta_run_mod(run_mod_id, players=players or [], rng=rng) for run_mod_id in raw]

    if player is None or not perk_active(player, PerkId.WILDCARD):
        return [RunModChoice(kind=RunModChoiceKind.RUN_MOD, run_mod_id=run_mod_id) for run_mod_id in resolved_ids]

    bonus_perks = iter(_wildcard_bonus_perks(state, player))
    choices: list[RunModChoice] = []
    for run_mod_id in resolved_ids:
        roll = rng.random()
        if roll < WILDCARD_REPLACE_CHANCE:
            bonus_perk_id = next(bonus_perks, None)
            if bonus_perk_id is not None:
                choices.append(RunModChoice(kind=RunModChoiceKind.PERK, perk_id=bonus_perk_id))
                continue
            # No spare perk left in this level-up's batch (e.g. Perk Master
            # already shows all 7) - fall through to a normal slot below.
        elif roll < WILDCARD_REPLACE_CHANCE + WILDCARD_UPGRADE_CHANCE:
            penalty_pool = [rid for rid in _VISIBLE_POOL if rid != run_mod_id]
            penalty_id = rng.choice(penalty_pool)
            choices.append(
                RunModChoice(
                    kind=RunModChoiceKind.UPGRADED_RUN_MOD,
                    run_mod_id=run_mod_id,
                    penalty_run_mod_id=penalty_id,
                ),
            )
            continue
        choices.append(RunModChoice(kind=RunModChoiceKind.RUN_MOD, run_mod_id=run_mod_id))
    return choices


def _run_mod_selection_prepare_if_needed(
    state: GameplayState,
    run_mod_state: RunModSelectionState,
    players: list[PlayerState] | None = None,
) -> list[RunModChoice]:
    if run_mod_state.choices_dirty or not run_mod_state.choices:
        player = players[0] if players else None
        run_mod_state.choices = run_mod_generate_choices(state, player=player, players=players)
        run_mod_state.choices_dirty = False
    return run_mod_state.choices


def run_mod_selection_prepared_choices(run_mod_state: RunModSelectionState) -> list[RunModChoice]:
    """Return already-prepared choices without mutating state."""

    if run_mod_state.choices_dirty or not run_mod_state.choices:
        return []
    return run_mod_state.choices


def run_mod_selection_open_choices(
    state: GameplayState,
    run_mod_state: RunModSelectionState,
    players: list[PlayerState] | None = None,
) -> list[RunModChoice]:
    """Prepare current run-mod choices for the selection UI and return them."""

    _run_mod_selection_prepare_if_needed(state, run_mod_state, players)
    return run_mod_selection_prepared_choices(run_mod_state)


def run_mod_selection_pick(
    state: GameplayState,
    players: list[PlayerState],
    run_mod_state: RunModSelectionState,
    choice_index: int,
    *,
    dt: float | None = None,
    creatures: Sequence["CreatureState"] | None = None,
) -> RunModChoice | None:
    """Pick a run-mod choice and apply it.

    On success, decrements `pending_count` and marks the choice list dirty,
    mirroring `perk_selection_pick`. `choices[choice_index]` is already fully
    resolved by generation time (see `run_mod_generate_choices`) - this just
    dispatches on its `kind`:

    - RUN_MOD: the normal path, one stack of `run_mod_id`.
    - UPGRADED_RUN_MOD (Wildcard): `run_mod_id` applies at 3 stacks worth,
      `penalty_run_mod_id` applies inverted (worse) at 1 stack, in one pick.
    - PERK (Wildcard): applies a real primary perk through `perk_apply`,
      entirely independent of the player's separate primary-panel pick this
      same level-up.
    """

    if run_mod_state.pending_count <= 0:
        return None
    _run_mod_selection_prepare_if_needed(state, run_mod_state, players)
    choices = run_mod_selection_prepared_choices(run_mod_state)
    if not choices:
        return None
    idx = int(choice_index)
    if idx < 0 or idx >= len(choices):
        return None
    choice = choices[idx]

    if choice.kind == RunModChoiceKind.PERK:
        from ..perks.runtime.apply import perk_apply

        assert choice.perk_id is not None
        perk_apply(state, players, choice.perk_id, perk_state=state.perk_selection, dt=dt, creatures=creatures)
    elif choice.kind == RunModChoiceKind.UPGRADED_RUN_MOD:
        assert choice.penalty_run_mod_id is not None
        run_mod_apply(players, choice.run_mod_id, amount=WILDCARD_UPGRADE_MULTIPLIER)
        run_mod_apply_penalty(players, choice.penalty_run_mod_id)
    else:
        run_mod_id = _resolve_meta_run_mod(choice.run_mod_id, players=players, rng=_run_mod_rng_for(state))
        run_mod_apply(players, run_mod_id)
        # Return what was actually applied, not the (possibly still-a-meta-
        # slot) id the caller manually seeded - normal flow never hits this
        # branch with an unresolved meta id (generate_choices resolves it
        # already), so this only matters for manually-seeded state.
        choice = RunModChoice(kind=RunModChoiceKind.RUN_MOD, run_mod_id=run_mod_id)

    assert int(run_mod_state.pending_count) > 0, "picked run mod must leave a pending run mod to resolve"
    run_mod_state.pending_count -= 1
    run_mod_state.choices_dirty = True
    return choice
