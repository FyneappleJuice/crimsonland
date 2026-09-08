from __future__ import annotations

import pytest

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.gameplay import GameplayState
from crimson.math_parity import f32
from crimson.perks import PerkId
from crimson.progression import PERK_STAT_MODS, PlayerStats, refresh_player_stats, resolve_player_stats
from crimson.progression.modifiers import more
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import assert_float_close


def _player_with(*perks: PerkId) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL, ammo=5))
    for perk_id in perks:
        player.perk_counts[int(perk_id)] = 1
    refresh_player_stats([player])
    return player


# --- Fastshot -> shot_cooldown_mult ------------------------------------


def _fire_cooldown(player: PlayerState) -> float:
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True), dt=0.1, state=GameplayState()),
    )
    return float(player.weapon.shot_cooldown)


def test_fastshot_alone_is_numerically_identical_to_the_old_08_multiply() -> None:
    base = _fire_cooldown(_player_with())
    fastshot = _fire_cooldown(_player_with(PerkId.FASTSHOT))
    assert_float_close(fastshot, float(f32(float(base) * 0.88)))


def test_extra_fire_rate_source_stacks_multiplicatively_with_fastshot() -> None:
    player = _player_with(PerkId.FASTSHOT)
    # simulate a future map affix / weapon mod feeding the same stat
    stats = resolve_player_stats(player, extra_sources=[more("shot_cooldown_mult", -0.25, source="affix:rapid")])
    assert stats.shot_cooldown_mult == pytest.approx(0.88 * 0.75)


# --- Bonus Economist -> bonus_duration_mult ---------------------------


def test_bonus_economist_alone_still_gives_exactly_1_5x_duration() -> None:
    plain_state = GameplayState()
    plain = _player_with()
    bonus_apply(plain_state, plain, BonusId.DOUBLE_EXPERIENCE, amount=10, origin=plain.pos, creatures=[], players=[plain])

    perk_state = GameplayState()
    perk = _player_with(PerkId.BONUS_ECONOMIST)
    bonus_apply(perk_state, perk, BonusId.DOUBLE_EXPERIENCE, amount=10, origin=perk.pos, creatures=[], players=[perk])

    assert plain_state.bonuses.double_experience == 6.0
    assert perk_state.bonuses.double_experience == 9.0  # 6.0 * 1.5


def test_stacked_bonus_duration_sources_compose() -> None:
    player = _player_with(PerkId.BONUS_ECONOMIST)
    stats = resolve_player_stats(player, extra_sources=[more("bonus_duration_mult", 0.5, source="affix:lingering")])
    # 1.5 (economist) * 1.5 (affix) = 2.25
    assert stats.bonus_duration_mult == pytest.approx(2.25)


# --- damage perks -> projectile / kinetic layers --------------------


def test_single_damage_perks_match_their_old_constants() -> None:
    # Doctor / Barrel Greaser are about aim + barrel, not the ammo, so they feed
    # the projectile layer (kinetic bullet + energy/plasma).
    assert _player_with(PerkId.DOCTOR).stats.damage_mult_projectile == pytest.approx(1.2)
    assert _player_with(PerkId.BARREL_GREASER).stats.damage_mult_projectile == pytest.approx(1.4)
    # Uranium slugs are kinetic lead only.
    assert _player_with(PerkId.URANIUM_FILLED_BULLETS).stats.damage_mult_bullet == pytest.approx(2.0)
    assert _player_with(PerkId.DOCTOR).stats.damage_mult_bullet == pytest.approx(1.0)
    assert _player_with(PerkId.URANIUM_FILLED_BULLETS).stats.damage_mult_projectile == pytest.approx(1.0)


def test_stacked_damage_perks_fold_per_layer() -> None:
    stats = _player_with(PerkId.DOCTOR, PerkId.BARREL_GREASER, PerkId.URANIUM_FILLED_BULLETS).stats
    assert stats.damage_mult_projectile == pytest.approx(1.2 * 1.4)
    assert stats.damage_mult_bullet == pytest.approx(2.0)


def test_fire_and_ion_damage_perks_feed_their_own_stats() -> None:
    assert _player_with(PerkId.PYROMANIAC).stats.damage_mult_fire == pytest.approx(1.5)
    assert _player_with(PerkId.ION_GUN_MASTER).stats.damage_mult_ion == pytest.approx(1.2)


# --- clip perks ----------------------------------------------------


def test_clip_perks_feed_mult_and_add_stats() -> None:
    ammo = _player_with(PerkId.AMMO_MANIAC).stats
    assert ammo.clip_size_mult == pytest.approx(1.25)
    fav = _player_with(PerkId.MY_FAVOURITE_WEAPON).stats
    assert fav.clip_size_add == pytest.approx(2.0)


# --- keystone flags ---------------------------------------------


def test_keystone_flags_resolve_onto_the_stat_block() -> None:
    assert _player_with(PerkId.UNSTOPPABLE).stats.has("no_hit_stagger")
    assert _player_with(PerkId.BARREL_GREASER).stats.has("projectile_double_steps")
    assert not _player_with().stats.has("no_hit_stagger")


# --- defense -----------------------------------------------------


def test_thick_skinned_alone_matches_the_native_f32_scale() -> None:
    assert _player_with(PerkId.THICK_SKINNED).stats.damage_taken_mult == 0.6660000085830688


# --- registry sanity ------------------------------------------------


def test_every_registered_perk_id_is_real() -> None:
    for perk_id in PERK_STAT_MODS:
        assert isinstance(perk_id, PerkId)


def test_a_player_with_only_mechanical_perks_resolves_to_defaults() -> None:
    from crimson.progression import PERK_MECHANICAL

    player = _player_with(PerkId.REGENERATION, PerkId.JINXED, PerkId.PLAGUEBEARER)
    assert PerkId.REGENERATION in PERK_MECHANICAL
    assert resolve_player_stats(player) == PlayerStats()
