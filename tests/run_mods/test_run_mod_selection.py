from __future__ import annotations

from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.run_mods.ids import RUN_MOD_HIDDEN_FROM_POOL, RunModId
from crimson.run_mods.selection import (
    RUN_MOD_CHOICE_COUNT,
    run_mod_choice_count,
    run_mod_generate_choices,
    run_mod_selection_open_choices,
    run_mod_selection_pick,
    run_mod_selection_prepared_choices,
)
from crimson.run_mods.state import RunModChoice, RunModChoiceKind, RunModSelectionState
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _plain(run_mod_id: RunModId) -> RunModChoice:
    return RunModChoice(kind=RunModChoiceKind.RUN_MOD, run_mod_id=run_mod_id)


def test_run_mod_choice_count_is_always_three() -> None:
    player = PlayerState(index=0, pos=Vec2())
    assert run_mod_choice_count(player) == RUN_MOD_CHOICE_COUNT == 3


def test_run_mod_choice_count_perk_expert_adds_one() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.PERK_EXPERT)] = 1
    assert run_mod_choice_count(player) == 4


def test_run_mod_choice_count_perk_master_adds_two_not_additive_with_expert() -> None:
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.PERK_EXPERT)] = 1
    player.perk_counts[int(PerkId.PERK_MASTER)] = 1
    assert run_mod_choice_count(player) == 5


def test_run_mod_generate_choices_uses_player_choice_count_when_given() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.PERK_MASTER)] = 1
    assert len(run_mod_generate_choices(state, player=player)) == 5


def test_run_mod_generate_choices_returns_exactly_count_entries() -> None:
    state = GameplayState()
    choices = run_mod_generate_choices(state)
    assert len(choices) == 3
    assert all(isinstance(c, RunModChoice) for c in choices)
    assert all(c.kind == RunModChoiceKind.RUN_MOD for c in choices)


def test_run_mod_generate_choices_is_deterministic_for_a_fixed_rng_state() -> None:
    state_a = GameplayState()
    state_b = GameplayState()
    assert run_mod_generate_choices(state_a) == run_mod_generate_choices(state_b)


def test_run_mod_generate_choices_never_duplicates_within_one_offer() -> None:
    state = GameplayState()
    for _ in range(50):
        state.rng.rand()  # advance the shared rng so each call reseeds differently
        choices = run_mod_generate_choices(state, count=3)
        assert len({c.run_mod_id for c in choices}) == len(choices)


def test_run_mod_selection_pick_applies_and_marks_dirty() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    run_mod_state = RunModSelectionState(
        pending_count=1,
        choices=[_plain(RunModId.FIRE_RATE), _plain(RunModId.CLIP_SIZE), _plain(RunModId.SPREAD)],
        choices_dirty=False,
    )

    picked = run_mod_selection_pick(state, [player], run_mod_state, 1)

    assert picked == _plain(RunModId.CLIP_SIZE)
    assert run_mod_state.pending_count == 0
    assert run_mod_state.choices_dirty is True
    assert player.run_mod_counts[int(RunModId.CLIP_SIZE)] == 1


def test_run_mod_selection_pick_returns_none_when_nothing_pending() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    run_mod_state = RunModSelectionState(pending_count=0, choices=[_plain(RunModId.FIRE_RATE)], choices_dirty=False)

    assert run_mod_selection_pick(state, [player], run_mod_state, 0) is None


def test_run_mod_selection_pick_can_pick_the_same_run_mod_twice_across_calls() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    run_mod_state = RunModSelectionState(pending_count=2, choices=[_plain(RunModId.FIRE_RATE)], choices_dirty=False)

    run_mod_selection_pick(state, [player], run_mod_state, 0)
    run_mod_state.pending_count = 1
    run_mod_state.choices = [_plain(RunModId.FIRE_RATE)]
    run_mod_state.choices_dirty = False
    run_mod_selection_pick(state, [player], run_mod_state, 0)

    assert player.run_mod_counts[int(RunModId.FIRE_RATE)] == 2


def test_run_mod_selection_open_choices_generates_then_prepared_reads_without_regenerating() -> None:
    state = GameplayState()
    run_mod_state = RunModSelectionState()

    opened = run_mod_selection_open_choices(state, run_mod_state)
    assert len(opened) == 3
    assert run_mod_state.choices_dirty is False

    # A second read without marking dirty must return the same list, not reroll.
    again = run_mod_selection_prepared_choices(run_mod_state)
    assert again == opened


def test_run_mod_selection_pick_syncs_run_mod_counts_across_players() -> None:
    state = GameplayState()
    p1 = PlayerState(index=0, pos=Vec2())
    p2 = PlayerState(index=1, pos=Vec2())
    run_mod_state = RunModSelectionState(pending_count=1, choices=[_plain(RunModId.MOVE_SPEED)], choices_dirty=False)

    picked = run_mod_selection_pick(state, [p1, p2], run_mod_state, 0)

    assert picked == _plain(RunModId.MOVE_SPEED)
    assert p1.run_mod_counts[int(RunModId.MOVE_SPEED)] == 1
    assert p2.run_mod_counts[int(RunModId.MOVE_SPEED)] == 1


# --- meta slots: DAMAGE_TYPE_BOOST / WEAPON_TYPE_BOOST --------------------

_DAMAGE_TYPE_TARGETS = {
    RunModId.BULLET_DAMAGE,
    RunModId.PLASMA_DAMAGE,
    RunModId.ENERGY_DAMAGE,
    RunModId.ION_DAMAGE,
    RunModId.FIRE_DAMAGE,
    RunModId.EXPLOSION_DAMAGE,
}
_WEAPON_TYPE_TARGETS = {
    RunModId.PISTOL_DAMAGE,
    RunModId.RIFLE_DAMAGE,
    RunModId.SMG_DAMAGE,
    RunModId.SHOTGUN_DAMAGE,
    RunModId.MINIGUN_DAMAGE,
    RunModId.CANNON_DAMAGE,
    RunModId.FLAMETHROWER_DAMAGE,
    RunModId.ARC_DAMAGE,
    RunModId.MELEE_DAMAGE,
}


def test_run_mod_generate_choices_never_offers_a_hidden_id_without_players() -> None:
    # With no players to resolve a meta slot against, DAMAGE_TYPE_BOOST/
    # WEAPON_TYPE_BOOST pass through unresolved (still not a hidden id).
    state = GameplayState()
    for _ in range(50):
        state.rng.rand()
        choices = run_mod_generate_choices(state, count=3)
        assert not ({c.run_mod_id for c in choices} & RUN_MOD_HIDDEN_FROM_POOL)


def test_run_mod_generate_choices_resolves_meta_slots_immediately_when_players_given() -> None:
    # Not a click-to-reveal gamble: when players are known, a meta slot is
    # resolved to its concrete hidden id right here at generation time, so
    # the displayed choice already shows the real bonus.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PLASMA_RIFLE))
    saw_literal_meta_id = False
    saw_resolved_hidden_id = False
    for seed in range(200):
        state.rng.srand(seed)
        choices = run_mod_generate_choices(state, count=3, players=[player])
        ids = {c.run_mod_id for c in choices}
        if {RunModId.DAMAGE_TYPE_BOOST, RunModId.WEAPON_TYPE_BOOST} & ids:
            saw_literal_meta_id = True
        if (_DAMAGE_TYPE_TARGETS | _WEAPON_TYPE_TARGETS) & ids:
            saw_resolved_hidden_id = True
    assert saw_literal_meta_id is False
    assert saw_resolved_hidden_id is True


def test_damage_type_boost_resolves_to_one_of_the_hidden_damage_type_ids() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    run_mod_state = RunModSelectionState(
        pending_count=1,
        choices=[_plain(RunModId.DAMAGE_TYPE_BOOST)],
        choices_dirty=False,
    )

    picked = run_mod_selection_pick(state, [player], run_mod_state, 0)

    assert picked is not None
    assert picked.run_mod_id in _DAMAGE_TYPE_TARGETS
    assert player.run_mod_counts[int(picked.run_mod_id)] == 1
    # The meta slot itself never accumulates a count - only what it resolved to.
    assert player.run_mod_counts[int(RunModId.DAMAGE_TYPE_BOOST)] == 0


def test_weapon_type_boost_resolves_to_one_of_the_hidden_archetype_ids() -> None:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.SHOTGUN))
    run_mod_state = RunModSelectionState(
        pending_count=1,
        choices=[_plain(RunModId.WEAPON_TYPE_BOOST)],
        choices_dirty=False,
    )

    picked = run_mod_selection_pick(state, [player], run_mod_state, 0)

    assert picked is not None
    assert picked.run_mod_id in _WEAPON_TYPE_TARGETS
    assert player.run_mod_counts[int(picked.run_mod_id)] == 1


def test_damage_type_boost_is_biased_toward_the_currently_equipped_weapon() -> None:
    # Plasma Rifle deals PLASMA damage - it should come up roughly twice as
    # often as any other single damage type across many independent rolls.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PLASMA_RIFLE))
    counts = dict.fromkeys(_DAMAGE_TYPE_TARGETS, 0)
    trials = 400
    for i in range(trials):
        state.rng.srand(i)  # vary the seed each trial so the roll actually varies
        run_mod_state = RunModSelectionState(
            pending_count=1,
            choices=[_plain(RunModId.DAMAGE_TYPE_BOOST)],
            choices_dirty=False,
        )
        picked = run_mod_selection_pick(state, [player], run_mod_state, 0)
        assert picked is not None
        counts[picked.run_mod_id] += 1

    other_avg = sum(v for k, v in counts.items() if k != RunModId.PLASMA_DAMAGE) / (len(counts) - 1)
    assert counts[RunModId.PLASMA_DAMAGE] > other_avg
