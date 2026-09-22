from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState, award_experience, award_experience_from_reward
from crimson.progression import refresh_player_stats
from crimson.run_mods.ids import RUN_MOD_META_SLOTS, RunModId
from crimson.run_mods.stat_mods import RUN_MOD_STAT_MODS
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon
from crimson.weapons import WeaponId
from grim.geom import Vec2


def _player_with_run_mods(*run_mod_ids: RunModId) -> PlayerState:
    player = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL, ammo=5))
    for run_mod_id in run_mod_ids:
        player.run_mod_counts[int(run_mod_id)] += 1
    refresh_player_stats([player])
    return player


def test_every_run_mod_id_has_a_stat_mod_entry() -> None:
    for run_mod_id in RunModId:
        assert run_mod_id in RUN_MOD_STAT_MODS
        if run_mod_id in RUN_MOD_META_SLOTS:
            continue  # meta slots resolve to a real id before ever applying
        assert RUN_MOD_STAT_MODS[run_mod_id]


def test_run_mod_counts_start_at_zero_and_leave_stats_untouched() -> None:
    player = _player_with_run_mods()
    assert player.stats.shot_cooldown_mult == 1.0
    assert player.stats.xp_mult == 1.0


def test_picking_a_run_mod_moves_its_stat() -> None:
    player = _player_with_run_mods(RunModId.FIRE_RATE)
    assert player.stats.shot_cooldown_mult == pytest.approx(0.98)


def test_picking_the_same_run_mod_twice_stacks_additively() -> None:
    player = _player_with_run_mods(RunModId.CLIP_SIZE, RunModId.CLIP_SIZE, RunModId.CLIP_SIZE)
    # increased() sums before scaling: 3 * 0.04 = 0.12 -> 1.12x
    assert player.stats.clip_size_mult == pytest.approx(1.12)


def test_run_mod_and_perk_on_the_same_stat_compose() -> None:
    from crimson.perks.ids import PerkId

    player = _player_with_run_mods(RunModId.FIRE_RATE)
    player.perk_counts[int(PerkId.FASTSHOT)] = 1
    refresh_player_stats([player])
    # Fastshot: more(-0.12); run mod: more(-0.02) -> (1-0.12)*(1-0.02)
    assert player.stats.shot_cooldown_mult == pytest.approx(0.88 * 0.98)


def test_run_mod_and_relic_extra_source_both_apply() -> None:
    from crimson.progression.modifiers import more
    from crimson.progression.sources import resolve_player_stats

    player = _player_with_run_mods(RunModId.RELOAD_SPEED)
    stats = resolve_player_stats(player, extra_sources=[more("reload_time_mult", -0.05, source="relic:test")])
    assert stats.reload_time_mult == pytest.approx(0.97 * 0.95)


# --- integration: fire rate + spread actually reach fire_weapon --------


def _fire_once(player: PlayerState) -> PlayerState:
    fire_weapon(
        WeaponFireCtx(player=player, input_state=PlayerInput(fire_down=True), dt=0.1, state=GameplayState()),
    )
    return player


def test_fire_rate_run_mod_speeds_up_the_weapon() -> None:
    base_player = _fire_once(_player_with_run_mods())
    modded_player = _fire_once(_player_with_run_mods(RunModId.FIRE_RATE))
    assert float(modded_player.weapon.shot_cooldown) < float(base_player.weapon.shot_cooldown)


def test_spread_run_mod_reduces_spread_heat_buildup() -> None:
    base_player = _fire_once(_player_with_run_mods())
    modded_player = _fire_once(_player_with_run_mods(RunModId.SPREAD))
    assert float(modded_player.spread_heat) < float(base_player.spread_heat)


# --- integration: XP gain -----------------------------------------------


def test_xp_gain_run_mod_scales_award_experience() -> None:
    base = _player_with_run_mods()
    modded = _player_with_run_mods(RunModId.XP_GAIN)
    state = GameplayState()
    base_gained = award_experience(state, base, int(100 * base.stats.xp_mult))
    modded_gained = award_experience(state, modded, int(100 * modded.stats.xp_mult))
    assert modded_gained > base_gained


def test_xp_gain_run_mod_scales_award_experience_from_reward() -> None:
    base = _player_with_run_mods()
    modded = _player_with_run_mods(RunModId.XP_GAIN)
    state = GameplayState()
    award_experience_from_reward(state, base, 100.0 * base.stats.xp_mult)
    award_experience_from_reward(state, modded, 100.0 * modded.stats.xp_mult)
    assert modded.experience > base.experience


# --- new axis: crit chance -----------------------------------------------


def test_crit_chance_run_mod_moves_its_stat() -> None:
    player = _player_with_run_mods(RunModId.CRIT_CHANCE)
    assert player.stats.crit_chance == pytest.approx(0.05)


# --- new axis: crit multiplier --------------------------------------------


def test_crit_multiplier_run_mod_moves_its_stat() -> None:
    player = _player_with_run_mods(RunModId.CRIT_MULTIPLIER)
    assert player.stats.crit_mult == pytest.approx(2.1)


def test_crit_multiplier_run_mod_stacks_flat() -> None:
    player = _player_with_run_mods(RunModId.CRIT_MULTIPLIER, RunModId.CRIT_MULTIPLIER, RunModId.CRIT_MULTIPLIER)
    assert player.stats.crit_mult == pytest.approx(2.3)


def test_crit_multiplier_run_mod_reaches_roll_crit_mult() -> None:
    from crimson.weapon_runtime.crit import roll_crit_mult

    player = _player_with_run_mods(RunModId.CRIT_MULTIPLIER)
    # A huge increased_chance drives chance well past 1.0, forcing a guaranteed
    # crit so the resolved crit_mult value can be asserted deterministically.
    boosted = roll_crit_mult(WeaponId.PISTOL, increased_chance=1000.0, crit_mult=float(player.stats.crit_mult))
    base = roll_crit_mult(WeaponId.PISTOL, increased_chance=1000.0)
    assert boosted == pytest.approx(2.1)
    assert base == pytest.approx(2.0)


def test_crit_chance_run_mod_scales_the_weapons_own_base_chance() -> None:
    from crimson.weapon_runtime.crit import crit_chance_for_weapon

    player = _player_with_run_mods(RunModId.CRIT_CHANCE)
    base = crit_chance_for_weapon(WeaponId.PISTOL)
    boosted = crit_chance_for_weapon(WeaponId.PISTOL, increased_chance=float(player.stats.crit_chance))
    assert base == pytest.approx(0.10)
    assert boosted == pytest.approx(0.105)  # 10% * 1.05, not 10% + 5%


def test_crit_chance_run_mod_does_nothing_on_a_zero_base_chance_weapon() -> None:
    from crimson.weapon_runtime.crit import crit_chance_for_weapon

    player = _player_with_run_mods(RunModId.CRIT_CHANCE, RunModId.CRIT_CHANCE, RunModId.CRIT_CHANCE)
    boosted = crit_chance_for_weapon(WeaponId.FLAMETHROWER, increased_chance=float(player.stats.crit_chance))
    assert boosted == 0.0


# --- new axis: all damage (generic) --------------------------------------


def test_all_damage_run_mod_moves_its_stat() -> None:
    player = _player_with_run_mods(RunModId.ALL_DAMAGE)
    assert player.stats.damage_mult == pytest.approx(1.015)


def test_all_damage_run_mod_applies_to_melee_and_explosion_which_have_no_other_hook() -> None:
    from crimson.creatures.damage import creature_apply_damage
    from crimson.creatures.damage_types import CreatureDamageType
    from crimson.creatures.runtime import CreatureState
    from crimson.creatures.spawn import CreatureFlags
    from crimson.owner_ref import OwnerRef
    from grim.rand import Crand

    def _hit(player: PlayerState, damage_type: CreatureDamageType) -> float:
        creature = CreatureState(
            active=True,
            hp=1000.0,
            max_hp=1000.0,
            size=50.0,
            flags=CreatureFlags(0),
            heading=0.0,
        )
        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_player(0),
            dt=0.1,
            players=[player],
            rng=Crand(1),
        )
        return 1000.0 - float(creature.hp)

    base = _player_with_run_mods()
    modded = _player_with_run_mods(RunModId.ALL_DAMAGE)
    for damage_type in (CreatureDamageType.MELEE, CreatureDamageType.EXPLOSION):
        assert _hit(modded, damage_type) > _hit(base, damage_type)


# --- new axis: weapon-archetype damage -----------------------------------


def test_pistol_damage_run_mod_moves_its_own_archetype_stat_only() -> None:
    player = _player_with_run_mods(RunModId.PISTOL_DAMAGE)
    assert player.stats.damage_mult_archetype_pistol == pytest.approx(1.05)
    assert player.stats.damage_mult_archetype_rifle == 1.0


# --- new axis: projectile speed -------------------------------------------


def test_projectile_speed_run_mod_moves_its_stat() -> None:
    player = _player_with_run_mods(RunModId.PROJECTILE_SPEED)
    assert player.stats.projectile_speed_mult == pytest.approx(1.04)
