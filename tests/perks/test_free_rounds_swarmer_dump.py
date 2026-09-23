from __future__ import annotations

from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2

TARGET_POS = Vec2(300.0, 0.0)


def _fire(player: PlayerState, state: GameplayState) -> None:
    player.weapon.shot_cooldown = 0.0
    player.weapon.reload_timer = 0.0
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=TARGET_POS),
            dt=0.016,
            state=state,
            creatures=(),
        ),
    )


def test_free_rounds_proc_grants_plus_one_ammo_on_a_swarmer_dump_weapon(monkeypatch) -> None:
    # Regression: Free Rounds skipping a shot's ammo cost normally just means
    # "the clip lasts one shot longer" - meaningless for Mini-Rocket Swarmers,
    # since the whole clip fires every trigger pull regardless, and (once
    # shot_cooldown/reload_timer decay in lockstep for this weapon) skipping
    # the reload no longer even saves time. Give it a real payoff instead:
    # +1 round in the next dump.
    import crimson.weapon_runtime.fire as fire_module

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=state)
    player.aim_heading = 1.5707963267948966
    player.perk_counts[int(PerkId.FREE_ROUNDS)] = 1
    base_clip = player.weapon.clip_size

    monkeypatch.setattr(fire_module._FREE_ROUNDS_RNG, "random", lambda: 0.0)  # always proc
    _fire(player, state)

    assert player.weapon.reload_timer == 0.0  # no reload started - the clip wasn't spent
    assert player.weapon.ammo == float(base_clip) + 1.0


def test_free_rounds_plus_one_stacks_and_resets_on_a_normal_reload(monkeypatch) -> None:
    import crimson.weapon_runtime.fire as fire_module

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.MINI_ROCKET_SWARMERS, state=state)
    player.aim_heading = 1.5707963267948966
    player.perk_counts[int(PerkId.FREE_ROUNDS)] = 1
    base_clip = float(player.weapon.clip_size)

    rolls = iter([0.0, 0.0, 0.99])
    monkeypatch.setattr(fire_module._FREE_ROUNDS_RNG, "random", lambda: next(rolls))

    _fire(player, state)
    assert player.weapon.ammo == base_clip + 1.0
    _fire(player, state)
    assert player.weapon.ammo == base_clip + 2.0
    _fire(player, state)  # this one misses - the whole (now-bigger) clip is spent normally
    assert player.weapon.ammo == 0.0
    assert player.weapon.reload_timer > 0.0


def test_free_rounds_does_not_grant_bonus_ammo_on_a_normal_weapon(monkeypatch) -> None:
    # The +1 payoff is specific to whole-clip "dump" weapons - a normal weapon
    # should keep Free Rounds' native behavior (skip this one shot's cost).
    import crimson.weapon_runtime.fire as fire_module

    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    player.aim_heading = 1.5707963267948966
    player.perk_counts[int(PerkId.FREE_ROUNDS)] = 1
    ammo_before = player.weapon.ammo

    monkeypatch.setattr(fire_module._FREE_ROUNDS_RNG, "random", lambda: 0.0)
    _fire(player, state)

    assert player.weapon.ammo == ammo_before
