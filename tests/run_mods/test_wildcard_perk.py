from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.progression import refresh_player_stats
from crimson.run_mods.ids import RunModId
from crimson.run_mods.selection import run_mod_generate_choices, run_mod_selection_pick
from crimson.run_mods.state import RunModChoice, RunModChoiceKind, RunModSelectionState
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2


def _wildcard_player() -> PlayerState:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.WILDCARD)] = 1
    return player


def _seed_primary_perk_batch(state: GameplayState, *, count: int = 7) -> None:
    # A fake but structurally realistic 7-entry primary batch (perks/selection.py
    # always rolls the full 7 regardless of how many are shown) - Wildcard's
    # "replace" outcome reads the tail past `perk_choice_count(player)`.
    candidates = [pid for pid in PerkId if pid not in (PerkId.ANTIPERK, PerkId.WILDCARD)]
    state.perk_selection.choices = candidates[:count]


# --- pick-time application (bypassing generation, mirrors the meta-slot tests) --


def test_wildcard_upgraded_choice_applies_triple_boost_and_single_penalty() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    run_mod_state = RunModSelectionState(
        pending_count=1,
        choices=[
            RunModChoice(
                kind=RunModChoiceKind.UPGRADED_RUN_MOD,
                run_mod_id=RunModId.FIRE_RATE,
                penalty_run_mod_id=RunModId.CLIP_SIZE,
            ),
        ],
        choices_dirty=False,
    )

    picked = run_mod_selection_pick(state, [player], run_mod_state, 0)

    assert picked is not None
    assert picked.kind == RunModChoiceKind.UPGRADED_RUN_MOD
    assert player.run_mod_counts[int(RunModId.FIRE_RATE)] == 3
    assert player.run_mod_penalty_counts[int(RunModId.CLIP_SIZE)] == 1
    assert player.run_mod_counts[int(RunModId.CLIP_SIZE)] == 0

    refresh_player_stats([player])
    # Fire Rate: more(shot_cooldown_mult, -0.02) x3 stacks -> (1-0.02)^3.
    assert player.stats.shot_cooldown_mult == pytest.approx(0.98**3)
    # Clip Size penalty: increased(clip_size_mult, 0.04) inverted -> -0.04, once.
    assert player.stats.clip_size_mult == pytest.approx(0.96)


def test_wildcard_perk_choice_applies_a_real_perk_not_a_run_mod() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    run_mod_state = RunModSelectionState(
        pending_count=1,
        choices=[RunModChoice(kind=RunModChoiceKind.PERK, perk_id=PerkId.FASTLOADER)],
        choices_dirty=False,
    )

    picked = run_mod_selection_pick(state, [player], run_mod_state, 0)

    assert picked is not None
    assert picked.kind == RunModChoiceKind.PERK
    assert picked.perk_id == PerkId.FASTLOADER
    assert player.perk_counts[int(PerkId.FASTLOADER)] == 1
    assert sum(player.run_mod_counts) == 0
    assert sum(player.run_mod_penalty_counts) == 0


# --- generation-time rolling ------------------------------------------------


def test_wildcard_generation_produces_all_three_outcomes_over_many_trials() -> None:
    state = GameplayState()
    player = _wildcard_player()
    _seed_primary_perk_batch(state)

    saw_perk = False
    saw_upgraded = False
    saw_plain = False
    for seed in range(500):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, player=player, players=[player])
        kinds = {c.kind for c in choices}
        saw_perk = saw_perk or RunModChoiceKind.PERK in kinds
        saw_upgraded = saw_upgraded or RunModChoiceKind.UPGRADED_RUN_MOD in kinds
        saw_plain = saw_plain or RunModChoiceKind.RUN_MOD in kinds

    assert saw_perk
    assert saw_upgraded
    assert saw_plain


def test_wildcard_upgrade_penalty_never_matches_its_own_boosted_stat() -> None:
    state = GameplayState()
    player = _wildcard_player()
    _seed_primary_perk_batch(state)

    for seed in range(500):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, player=player, players=[player])
        for choice in choices:
            if choice.kind == RunModChoiceKind.UPGRADED_RUN_MOD:
                assert choice.penalty_run_mod_id != choice.run_mod_id


def test_wildcard_offered_perk_never_duplicates_the_visible_primary_choices() -> None:
    state = GameplayState()
    player = _wildcard_player()
    _seed_primary_perk_batch(state)
    from crimson.perks.selection import perk_choice_count

    visible_primary = set(state.perk_selection.choices[: perk_choice_count(player)])

    for seed in range(500):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, player=player, players=[player])
        for choice in choices:
            if choice.kind == RunModChoiceKind.PERK:
                assert choice.perk_id not in visible_primary


def test_wildcard_replace_falls_back_to_a_plain_run_mod_with_no_spare_perks() -> None:
    # Perk Master shows all 7 batch entries - no unused tail left for
    # Wildcard's "replace" outcome to pull from.
    state = GameplayState()
    player = _wildcard_player()
    player.perk_counts[int(PerkId.PERK_MASTER)] = 1
    _seed_primary_perk_batch(state)

    for seed in range(200):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, player=player, players=[player])
        assert all(choice.kind != RunModChoiceKind.PERK for choice in choices)


def test_without_wildcard_every_choice_is_plain() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    _seed_primary_perk_batch(state)

    for seed in range(200):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, player=player, players=[player])
        assert all(choice.kind == RunModChoiceKind.RUN_MOD for choice in choices)
