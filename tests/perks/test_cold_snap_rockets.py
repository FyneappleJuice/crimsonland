from __future__ import annotations

import pytest

from crimson.gameplay import GameplayState
from crimson.perks import PerkId
from crimson.projectiles.runtime import SecondaryStepCtx
from crimson.projectiles.runtime.projectile_pool import COLD_SNAP_FREEZE_DURATION
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapon_runtime import crit as crit_module
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature

_ROCKET_WEAPONS = [
    WeaponId.ROCKET_LAUNCHER,
    WeaponId.SEEKER_ROCKETS,
    WeaponId.MINI_ROCKET_SWARMERS,
    WeaponId.ROCKET_MINIGUN,
]


def _fire_rocket_until_hit(
    monkeypatch: pytest.MonkeyPatch,
    weapon_id: WeaponId,
    *,
    force_crit: bool,
    cold_snap: bool = True,
    overdue_streak: int = 0,
):
    # 0.0 always lands under any nonzero crit chance; 0.999 never does.
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 0.0 if force_crit else 0.999)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.overdue_streak = overdue_streak
    if cold_snap:
        player.perk_counts[int(PerkId.COLD_SNAP)] = 1
    player.aim_heading = 1.5707963267948966  # heading convention: 0=up, +90deg=+x
    target = _creature(pos=Vec2(60.0, 0.0), hp=1.0e9)
    # Close enough to be caught in the detonation AoE, too far for a direct hit.
    bystander = _creature(pos=Vec2(60.0, 30.0), hp=1.0e9)
    creatures = (target, bystander)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=target.pos),
            dt=0.016,
            state=state,
            creatures=creatures,
        ),
    )
    for _ in range(300):
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=creatures, runtime_state=state, players=[player]),
        )
        if target.crit_freeze_timer > 0.0 or target.hp < 1.0e9:
            break
    # Let the detonation AoE play out so the bystander gets hit too.
    for _ in range(30):
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=creatures, runtime_state=state, players=[player]),
        )
    return player, target, bystander


@pytest.mark.parametrize("weapon_id", _ROCKET_WEAPONS)
def test_crit_rocket_freezes_only_the_creature_it_hits_directly(
    monkeypatch: pytest.MonkeyPatch,
    weapon_id: WeaponId,
) -> None:
    _, target, bystander = _fire_rocket_until_hit(monkeypatch, weapon_id, force_crit=True)
    assert target.hp < 1.0e9
    assert 0.0 < target.crit_freeze_timer <= COLD_SNAP_FREEZE_DURATION
    if weapon_id == WeaponId.ROCKET_LAUNCHER:
        assert bystander.hp < 1.0e9  # caught in the (biggest) blast...
    if weapon_id != WeaponId.MINI_ROCKET_SWARMERS:
        # (A swarmer volley can home a second rocket straight into the
        # bystander - a direct hit of its own, which rightly freezes it.)
        assert bystander.crit_freeze_timer == 0.0  # ...but never frozen by it


@pytest.mark.parametrize("weapon_id", _ROCKET_WEAPONS)
def test_non_crit_rocket_does_not_freeze(monkeypatch: pytest.MonkeyPatch, weapon_id: WeaponId) -> None:
    _, target, _ = _fire_rocket_until_hit(monkeypatch, weapon_id, force_crit=False)
    assert target.hp < 1.0e9
    assert target.crit_freeze_timer == 0.0


def test_crit_rocket_does_not_freeze_without_deep_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    _, target, _ = _fire_rocket_until_hit(monkeypatch, WeaponId.ROCKET_LAUNCHER, force_crit=True, cold_snap=False)
    assert target.hp < 1.0e9
    assert target.crit_freeze_timer == 0.0


def test_rocket_hits_drive_overdue_streak(monkeypatch: pytest.MonkeyPatch) -> None:
    player, _, _ = _fire_rocket_until_hit(monkeypatch, WeaponId.ROCKET_LAUNCHER, force_crit=False, cold_snap=False)
    assert player.overdue_streak == 1

    player, _, _ = _fire_rocket_until_hit(
        monkeypatch,
        WeaponId.ROCKET_LAUNCHER,
        force_crit=True,
        cold_snap=False,
        overdue_streak=3,
    )
    assert player.overdue_streak == 0
