from __future__ import annotations

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.projectiles.runtime import SecondaryProjectilePool, SecondarySpawnSpec, SecondaryStepCtx
from crimson.projectiles.types import SecondaryProjectileTypeId
from crimson.run_mods.ids import RunModId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime import crit as crit_module
from crimson.weapon_runtime.fire import _BARREL_GREASER_ROCKET_WEAPON_IDS
from crimson.weapons import WeaponId
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import make_creature_state as _creature

_ROCKET_WEAPONS = [
    WeaponId.ROCKET_LAUNCHER,
    WeaponId.SEEKER_ROCKETS,
    WeaponId.MINI_ROCKET_SWARMERS,
    WeaponId.ROCKET_MINIGUN,
]


def test_barrel_greaser_rocket_weapon_set_matches_the_four_rocket_weapons() -> None:
    assert _BARREL_GREASER_ROCKET_WEAPON_IDS == frozenset(_ROCKET_WEAPONS)


def test_barrel_greaser_boosts_a_rocket_direct_hit_via_the_shared_pipeline() -> None:
    # Not a new behavior - the direct-hit half of a rocket's damage already
    # rides the shared creature-damage pipeline's is_projectile_hit branch
    # (creatures/damage.py), same bucket Doctor/Barrel Greaser feed for
    # bullets. Regression coverage for that existing wiring, isolated from
    # the rocket's own speed/flight-time noise (a rocket's direct-hit damage
    # depends on entry.speed, which decays over its flight - arriving sooner
    # or later changes the base damage independent of any perk, so this
    # exercises the damage-multiplier step directly instead of firing a
    # whole rocket through a variable-length flight).
    creature = _creature(pos=Vec2(), hp=1000.0)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 1

    creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.EXPLOSION),
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[player],
        rng=Crand(1),
        is_projectile_hit=True,
    )

    assert 1000.0 - float(creature.hp) == pytest.approx(14.0, rel=1e-5)


def test_barrel_greaser_does_not_affect_non_rocket_explosion_damage() -> None:
    # Scoping check: Man Bomb / Nuke / mines all deal CreatureDamageType.
    # EXPLOSION too, but aren't rockets (and don't set is_projectile_hit) -
    # Barrel Greaser must not leak onto them the way a blanket
    # damage_mult_explosion bonus would.
    creature = _creature(pos=Vec2(), hp=1000.0)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 1

    creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.EXPLOSION),
        impulse=Vec2(),
        owner=OwnerRef.from_player(0),
        dt=0.016,
        players=[player],
        rng=Crand(1),
    )

    assert 1000.0 - float(creature.hp) == pytest.approx(10.0, rel=1e-5)


def _step_detonation(*, barrel_greaser_rocket: bool, barrel_greaser_perk: bool) -> float:
    # Constructs a detonation entry directly (bypassing rocket flight/spawn
    # timing entirely) so the blast-tick damage multiplier can be checked in
    # isolation, with no entanglement from a rocket's own speed affecting how
    # much of its "fuel" (entry.speed) remains at hit time.
    pool = SecondaryProjectilePool()
    idx = pool.spawn_from_spec(
        SecondarySpawnSpec(
            pos=Vec2(0.0, 0.0),
            angle=0.0,
            type_id=SecondaryProjectileTypeId.DETONATION,
            owner=OwnerRef.from_local_player(0),
            time_to_live=1.0,
        ),
    )
    pool.entries[idx].barrel_greaser_rocket = barrel_greaser_rocket
    creature = _creature(pos=Vec2(0.0, 0.0), hp=1.0e9)
    player = PlayerState(index=0, pos=Vec2())
    if barrel_greaser_perk:
        player.perk_counts[int(PerkId.BARREL_GREASER)] = 1
    pool.step(SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), players=[player]))
    return 1.0e9 - float(creature.hp)


def test_barrel_greaser_boosts_rocket_blast_tick_damage() -> None:
    # This is the actual gap Barrel Greaser had for rockets: the direct hit
    # got the bonus via is_projectile_hit, but the detonation/blast tick that
    # follows had no equivalent gate (AoE/DoT ticks are deliberately excluded
    # from that bucket) - so a rocket's own splash damage was untouched.
    plain = _step_detonation(barrel_greaser_rocket=True, barrel_greaser_perk=False)
    greased = _step_detonation(barrel_greaser_rocket=True, barrel_greaser_perk=False)
    assert plain == greased  # sanity: identical inputs, identical output
    boosted = _step_detonation(barrel_greaser_rocket=True, barrel_greaser_perk=True)
    assert plain > 0.0
    assert boosted == pytest.approx(plain * 1.4, rel=1e-5)


def test_barrel_greaser_blast_bonus_is_scoped_to_rocket_weapons() -> None:
    # A DETONATION entry not stamped barrel_greaser_rocket (Explosive
    # Payload's blast off a *bullet* hit, or Man Bomb/Nuke if they ever
    # routed through this rule) must not pick up the bonus even if the perk
    # is active team-wide.
    unstamped = _step_detonation(barrel_greaser_rocket=False, barrel_greaser_perk=True)
    stamped = _step_detonation(barrel_greaser_rocket=True, barrel_greaser_perk=False)
    assert unstamped == pytest.approx(stamped)


@pytest.mark.parametrize("weapon_id", _ROCKET_WEAPONS)
def test_barrel_greaser_rocket_flag_is_stamped_regardless_of_perk_ownership(weapon_id: WeaponId) -> None:
    # The stamped flag records "this rocket came from one of the four
    # dedicated rocket weapons" (an identity, checked at spawn time) - not
    # "Barrel Greaser is currently active" (checked separately, team-wide, at
    # read time in secondary_pool.py). It's True either way; only the actual
    # speed/damage bonus is gated on the perk.
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.aim_heading = 1.5707963267948966
    target = _creature(pos=Vec2(100000.0, 0.0), hp=1.0e9)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=target.pos),
            dt=0.016,
            state=state,
            creatures=(target,),
        ),
    )
    entry = next(e for e in state.secondary_projectiles.entries if e.active)
    assert entry.barrel_greaser_rocket is True


@pytest.mark.parametrize("weapon_id", _ROCKET_WEAPONS)
def test_barrel_greaser_speeds_up_rockets(weapon_id: WeaponId, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 0.999)

    def _flight_distance(*, barrel_greaser: bool, projectile_speed_run_mod_stacks: int = 0) -> float:
        state = GameplayState()
        player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
        weapon_assign_player(player, weapon_id, state=state)
        if barrel_greaser:
            player.perk_counts[int(PerkId.BARREL_GREASER)] = 1
        player.run_mod_counts[int(RunModId.PROJECTILE_SPEED)] = projectile_speed_run_mod_stacks
        player.aim_heading = 1.5707963267948966
        target = _creature(pos=Vec2(100000.0, 0.0), hp=1.0e9)
        creatures = (target,)
        fire_weapon(
            WeaponFireCtx(
                player=player,
                input_state=PlayerInput(fire_down=True, aim=target.pos),
                dt=0.016,
                state=state,
                creatures=creatures,
            ),
        )
        entry = next(e for e in state.secondary_projectiles.entries if e.active)
        for _ in range(20):
            state.secondary_projectiles.step(
                SecondaryStepCtx(dt=1.0 / 60.0, creatures=creatures, runtime_state=state, players=[player]),
            )
        return float(entry.pos.distance_to(Vec2(0.0, 0.0)))

    plain_distance = _flight_distance(barrel_greaser=False)
    greased_distance = _flight_distance(barrel_greaser=True)
    assert greased_distance > plain_distance * 1.2


@pytest.mark.parametrize("weapon_id", _ROCKET_WEAPONS)
def test_stacked_rocket_speed_bonuses_are_capped(weapon_id: WeaponId, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Barrel Greaser (1.5x) and the Projectile Speed run mod
    # (stacks additively, unbounded over a run) both scale a rocket's per-tick
    # movement now - uncapped, a long run with enough Projectile Speed picks
    # stacked on top of Barrel Greaser could push a rocket fast enough to
    # tunnel through a creature in one tick instead of hitting it. Both
    # together must still land on the same per-tick multiplier as Barrel
    # Greaser hitting the cap alone.
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 0.999)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.perk_counts[int(PerkId.BARREL_GREASER)] = 1
    # +4% per stack (run_mods/stat_mods.py) - 20 stacks alone is +80%, already
    # past the 1.5x cap even before Barrel Greaser's own factor compounds it.
    player.run_mod_counts[int(RunModId.PROJECTILE_SPEED)] = 20
    player.aim_heading = 1.5707963267948966
    target = _creature(pos=Vec2(100000.0, 0.0), hp=1.0e9)
    creatures = (target,)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=target.pos),
            dt=0.016,
            state=state,
            creatures=creatures,
        ),
    )
    entry = next(e for e in state.secondary_projectiles.entries if e.active)
    for _ in range(3):
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=creatures, runtime_state=state, players=[player]),
        )
    stacked_distance = float(entry.pos.distance_to(Vec2(0.0, 0.0)))

    state2 = GameplayState()
    player2 = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player2, weapon_id, state=state2)
    player2.perk_counts[int(PerkId.BARREL_GREASER)] = 1
    player2.aim_heading = 1.5707963267948966
    creatures2 = (_creature(pos=Vec2(100000.0, 0.0), hp=1.0e9),)
    fire_weapon(
        WeaponFireCtx(
            player=player2,
            input_state=PlayerInput(fire_down=True, aim=creatures2[0].pos),
            dt=0.016,
            state=state2,
            creatures=creatures2,
        ),
    )
    entry2 = next(e for e in state2.secondary_projectiles.entries if e.active)
    for _ in range(3):
        state2.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=creatures2, runtime_state=state2, players=[player2]),
        )
    capped_distance = float(entry2.pos.distance_to(Vec2(0.0, 0.0)))

    assert stacked_distance == pytest.approx(capped_distance, rel=1e-5)
