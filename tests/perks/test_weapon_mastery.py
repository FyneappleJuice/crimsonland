from __future__ import annotations

from crimson.game_modes import GameMode
from crimson.gameplay import GameplayState
from crimson.perks.availability import build_perk_availability, perk_can_offer, prepare_perk_availability
from crimson.perks.ids import PERK_MASTERY_CONCRETE_IDS, PerkId
from crimson.perks.selection import perk_generate_choices
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _player(weapon_id: WeaponId) -> PlayerState:
    return PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=weapon_id))


def _prepared_state() -> GameplayState:
    state = GameplayState()
    prepare_perk_availability(state)
    return state


def test_concrete_masteries_are_never_offered_directly() -> None:
    available = build_perk_availability(status=None)
    for concrete_id in PERK_MASTERY_CONCRETE_IDS:
        assert not available[int(concrete_id)]


def test_weapon_mastery_generation_never_yields_the_meta_id_itself() -> None:
    state = _prepared_state()
    player = _player(WeaponId.ASSAULT_RIFLE)
    for seed in range(100):
        state.rng.srand(seed)
        choices = perk_generate_choices(state, player, game_mode=GameMode.SURVIVAL, player_count=1, count=7)
        assert PerkId.WEAPON_MASTERY not in choices


def test_weapon_mastery_resolution_is_biased_toward_the_currently_equipped_weapon() -> None:
    # Plasma Rifle deals Plasma damage - Plasma Mastery should come up
    # noticeably more often than the other three across many independent offers.
    state = _prepared_state()
    player = _player(WeaponId.PLASMA_RIFLE)
    counts = dict.fromkeys(PERK_MASTERY_CONCRETE_IDS, 0)
    trials = 400
    for seed in range(trials):
        state.rng.srand(seed)
        player.perk_counts[:] = [0] * len(player.perk_counts)
        choices = perk_generate_choices(state, player, game_mode=GameMode.SURVIVAL, player_count=1, count=7)
        for perk_id in choices:
            if perk_id in PERK_MASTERY_CONCRETE_IDS:
                counts[perk_id] += 1

    other_avg = sum(v for k, v in counts.items() if k != PerkId.PLASMA_MASTERY) / (len(counts) - 1)
    assert counts[PerkId.PLASMA_MASTERY] > other_avg


def test_weapon_mastery_never_resolves_to_an_already_owned_mastery() -> None:
    state = _prepared_state()
    player = _player(WeaponId.PLASMA_RIFLE)
    player.perk_counts[int(PerkId.PLASMA_MASTERY)] = 1
    player.perk_counts[int(PerkId.ION_GUN_MASTER)] = 1
    player.perk_counts[int(PerkId.ROCKET_MASTERY)] = 1

    for seed in range(100):
        state.rng.srand(seed)
        choices = perk_generate_choices(state, player, game_mode=GameMode.SURVIVAL, player_count=1, count=7)
        for perk_id in choices:
            if perk_id == PerkId.BULLET_MASTERY:
                # The only remaining unowned concrete - fine to appear.
                continue
            assert perk_id not in (PerkId.PLASMA_MASTERY, PerkId.ION_GUN_MASTER, PerkId.ROCKET_MASTERY)


def test_weapon_mastery_is_not_offerable_once_all_four_are_owned() -> None:
    state = _prepared_state()
    player = _player(WeaponId.ASSAULT_RIFLE)
    for concrete_id in PERK_MASTERY_CONCRETE_IDS:
        player.perk_counts[int(concrete_id)] = 1

    assert not perk_can_offer(state, player, PerkId.WEAPON_MASTERY, game_mode=GameMode.SURVIVAL, player_count=1)

    for seed in range(50):
        state.rng.srand(seed)
        choices = perk_generate_choices(state, player, game_mode=GameMode.SURVIVAL, player_count=1, count=7)
        assert not (set(choices) & PERK_MASTERY_CONCRETE_IDS)
