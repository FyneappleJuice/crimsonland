from __future__ import annotations

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureFlags
from crimson.effects import FxQueue
from crimson.gameplay import GameplayState, player_update
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.perks.runtime.effects import perks_update_effects
from crimson.progression import refresh_player_stats
from crimson.projectiles.runtime import ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.run_mods.ids import RunModId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime.crit import DIAMOND_FLASK_BASE_POWER, roll_primary_crit
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand


def _player_with(*, perks: dict[PerkId, int] | None = None, efficacy_stacks: int = 0, **kwargs) -> PlayerState:
    kwargs.setdefault("weapon", WeaponSlot(weapon_id=WeaponId.PISTOL, ammo=5))
    player = PlayerState(index=0, pos=Vec2(), **kwargs)
    for perk_id, count in (perks or {}).items():
        player.perk_counts[int(perk_id)] = count
    if efficacy_stacks:
        player.run_mod_counts[int(RunModId.PERK_EFFICACY)] = efficacy_stacks
    refresh_player_stats([player])
    return player


def test_perk_efficacy_run_mod_moves_its_stat() -> None:
    player = _player_with(efficacy_stacks=1)
    assert player.stats.perk_efficacy == pytest.approx(1.05)


def test_perk_efficacy_defaults_to_identity_with_no_stacks() -> None:
    player = _player_with()
    assert player.stats.perk_efficacy == 1.0


# --- two-pass PERK_STAT_MODS scaling --------------------------------------


def test_fastshot_cooldown_reduction_deepens_with_efficacy() -> None:
    base = _player_with(perks={PerkId.FASTSHOT: 1})
    boosted = _player_with(perks={PerkId.FASTSHOT: 1}, efficacy_stacks=1)
    assert boosted.stats.shot_cooldown_mult < base.stats.shot_cooldown_mult < 1.0


def test_sharpshooter_penalty_shrinks_with_efficacy() -> None:
    base = _player_with(perks={PerkId.SHARPSHOOTER: 1})
    boosted = _player_with(perks={PerkId.SHARPSHOOTER: 1}, efficacy_stacks=1)
    # Sharpshooter's cooldown penalty is a MORE term > 1.0 - efficacy should
    # shrink it back toward 1.0, the opposite direction from every other
    # scaled perk above.
    assert 1.0 < boosted.stats.shot_cooldown_mult < base.stats.shot_cooldown_mult


def test_uranium_filled_bullets_multiplier_grows_with_efficacy() -> None:
    base = _player_with(perks={PerkId.URANIUM_FILLED_BULLETS: 1})
    boosted = _player_with(perks={PerkId.URANIUM_FILLED_BULLETS: 1}, efficacy_stacks=1)
    assert boosted.stats.damage_mult_projectile > base.stats.damage_mult_projectile


def test_my_favourite_weapon_flat_add_scales_with_efficacy() -> None:
    base = _player_with(perks={PerkId.MY_FAVOURITE_WEAPON: 1})
    boosted = _player_with(perks={PerkId.MY_FAVOURITE_WEAPON: 1}, efficacy_stacks=1)
    assert boosted.stats.clip_size_add == pytest.approx(2.0 * 1.05)
    assert base.stats.clip_size_add == pytest.approx(2.0)


# --- shooter-perk block (creatures/damage.py) -----------------------------


def _hit_with(player: PlayerState, *, damage_type: int = CreatureDamageType.BULLET, hp: float = 1000.0) -> float:
    creature = CreatureState(active=True, hp=hp, max_hp=hp, size=50.0, flags=CreatureFlags(0), heading=0.0)
    creature_apply_damage(
        creature,
        damage_amount=100.0,
        damage_type=int(damage_type),
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )
    return hp - float(creature.hp)


def test_bane_of_legends_penalty_shrinks_and_kill_bonus_grows_with_efficacy() -> None:
    base_penalty_only = _player_with(perks={PerkId.BANE_OF_LEGENDS: 1})
    boosted_penalty_only = _player_with(perks={PerkId.BANE_OF_LEGENDS: 1}, efficacy_stacks=1)
    # Outside the kill window: base multiplier is (1 - 0.10) = 0.90; efficacy
    # should make the penalty smaller, i.e. more damage dealt.
    assert _hit_with(boosted_penalty_only) > _hit_with(base_penalty_only)

    base_bonus = _player_with(perks={PerkId.BANE_OF_LEGENDS: 1}, bane_of_legends_timer=5.0)
    boosted_bonus = _player_with(
        perks={PerkId.BANE_OF_LEGENDS: 1},
        efficacy_stacks=1,
        bane_of_legends_timer=5.0,
    )
    # Inside the kill window: efficacy should grow the +30% bonus.
    assert _hit_with(boosted_bonus) > _hit_with(base_bonus)


def test_cold_snap_frozen_target_bonus_grows_with_efficacy() -> None:
    def _hit_frozen(player: PlayerState) -> float:
        creature = CreatureState(
            active=True,
            hp=1000.0,
            max_hp=1000.0,
            size=50.0,
            flags=CreatureFlags(0),
            heading=0.0,
            is_frozen=True,
        )
        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(),
            owner=OwnerRef.from_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
        )
        return 1000.0 - float(creature.hp)

    base = _player_with(perks={PerkId.COLD_SNAP: 1})
    boosted = _player_with(perks={PerkId.COLD_SNAP: 1}, efficacy_stacks=1)
    assert _hit_frozen(boosted) > _hit_frozen(base)


def test_coup_de_grace_execute_threshold_widens_with_efficacy() -> None:
    # hp_frac lands between the base 7% threshold and a widened one - only
    # the efficacy-boosted player should execute it.
    hp = 1000.0
    creature_hp = 72.0  # 7.2% of max hp - above the native 7% threshold, below the boosted one

    base = _player_with(perks={PerkId.COUP_DE_GRACE: 1})
    boosted = _player_with(perks={PerkId.COUP_DE_GRACE: 1}, efficacy_stacks=1)

    def _damage_at(player: PlayerState) -> float:
        creature = CreatureState(active=True, hp=creature_hp, max_hp=hp, size=50.0, flags=CreatureFlags(0))
        creature_apply_damage(
            creature,
            damage_amount=1.0,
            damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(),
            owner=OwnerRef.from_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
        )
        return creature_hp - float(creature.hp)

    assert _damage_at(base) == pytest.approx(1.0)  # no execute, plain 1 damage
    assert _damage_at(boosted) == pytest.approx(creature_hp)  # executed


# --- odds-based perks (player_damage.py) ----------------------------------


def test_highlander_death_chance_lowers_with_efficacy() -> None:
    from crimson.player_damage import player_take_damage

    def _highlander_death_rate(efficacy_stacks: int, trials: int = 300) -> float:
        deaths = 0
        for seed in range(trials):
            player = _player_with(perks={PerkId.HIGHLANDER: 1}, efficacy_stacks=efficacy_stacks, health=100.0)
            state = GameplayState(rng=ScriptedCrand(seed, fallback=ScriptedCrand.Fallback.REPEAT_LAST))
            player_take_damage(state, player, 10.0, dt=0.016, players=[player])
            if player.health <= 0.0:
                deaths += 1
        return deaths / trials

    base_rate = _highlander_death_rate(0)
    boosted_rate = _highlander_death_rate(4)  # +20% efficacy -> chance / 1.2
    assert boosted_rate < base_rate


def test_dodger_chance_raises_with_efficacy() -> None:
    from crimson.player_damage import player_take_damage

    def _dodge_rate(efficacy_stacks: int, trials: int = 300) -> float:
        dodges = 0
        for seed in range(trials):
            player = _player_with(perks={PerkId.DODGER: 1}, efficacy_stacks=efficacy_stacks, health=100.0)
            health_before = float(player.health)
            state = GameplayState(rng=ScriptedCrand(seed, fallback=ScriptedCrand.Fallback.REPEAT_LAST))
            player_take_damage(state, player, 10.0, dt=0.016, players=[player])
            if player.health == health_before:
                dodges += 1
        return dodges / trials

    base_rate = _dodge_rate(0)
    boosted_rate = _dodge_rate(4)
    assert boosted_rate > base_rate


# --- Diamond Flask's 1-(1-x)^power formula ---------------------------------


def test_diamond_flask_power_scales_with_efficacy() -> None:
    from crimson.weapon_runtime.crit import crit_chance_for_weapon

    base = _player_with(perks={PerkId.DIAMOND_FLASK: 1})
    boosted = _player_with(perks={PerkId.DIAMOND_FLASK: 1}, efficacy_stacks=1)
    assert boosted.stats.perk_efficacy > base.stats.perk_efficacy

    chance = crit_chance_for_weapon(WeaponId.PISTOL)
    base_power = DIAMOND_FLASK_BASE_POWER * base.stats.perk_efficacy
    boosted_power = DIAMOND_FLASK_BASE_POWER * boosted.stats.perk_efficacy
    assert boosted_power > base_power

    base_effective_chance = 1.0 - (1.0 - chance) ** base_power
    boosted_effective_chance = 1.0 - (1.0 - chance) ** boosted_power
    assert boosted_effective_chance > base_effective_chance

    # roll_primary_crit actually consumes lucky_power in this formula, not
    # just as a pass-through - force_crit sidesteps the private RNG entirely
    # so this assertion is deterministic.
    assert roll_primary_crit(WeaponId.PISTOL, force_crit=True, lucky_power=boosted_power)[1] is True


# --- proc-damage perks (Perk Efficacy is their only new boost) ------------


def test_man_bomb_projectiles_carry_perk_efficacy_damage_mult() -> None:
    pool = ProjectilePool(size=32)
    state = GameplayState(projectiles=pool, rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST))
    player = _player_with(perks={PerkId.MAN_BOMB: 1}, efficacy_stacks=1, man_bomb_timer=3.9)

    player_update(player, PlayerInput(aim=Vec2(101.0, 100.0)), 0.2, state)

    active = [entry for entry in pool.entries if entry.active]
    assert len(active) == 8
    assert all(entry.perk_damage_mult == pytest.approx(1.05) for entry in active)


def test_angry_reloader_ring_carries_perk_efficacy_damage_mult() -> None:
    pool = ProjectilePool(size=64)
    state = GameplayState(projectiles=pool)
    player = _player_with(
        perks={PerkId.ANGRY_RELOADER: 1},
        efficacy_stacks=1,
        weapon=WeaponSlot(
            weapon_id=WeaponId.PISTOL,
            clip_size=10,
            ammo=0,
            reload_active=True,
            reload_timer=1.1,
            reload_timer_max=2.0,
        ),
    )

    player_update(player, PlayerInput(aim=Vec2(101.0, 100.0)), 0.2, state)

    active = [entry for entry in pool.entries if entry.active]
    assert active
    assert all(entry.perk_damage_mult == pytest.approx(1.05) for entry in active)
    assert all(entry.type_id == ProjectileTemplateId.PLASMA_MINIGUN for entry in active)


def test_pyrokinetic_particles_carry_perk_efficacy_damage_mult() -> None:
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    state = GameplayState(rng=rng)
    player = _player_with(perks={PerkId.PYROKINETIC: 1}, efficacy_stacks=1, aim=Vec2(100.0, 200.0))

    creature = CreatureState()
    creature.active = True
    creature.pos = Vec2(100.0, 200.0)
    creature.lifecycle_stage = 16.0
    creature.collision_timer = 0.1

    fx_queue = FxQueue(capacity=8, max_count=8)
    perks_update_effects(state, [player], 0.2, creatures=[creature], fx_queue=fx_queue)

    particles = [entry for entry in state.particles.entries if entry.active]
    assert len(particles) == 5
    assert all(entry.perk_damage_mult == pytest.approx(1.05) for entry in particles)
