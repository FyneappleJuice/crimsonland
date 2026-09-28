from __future__ import annotations

import pytest

from crimson.bonuses import BonusId
from crimson.bonuses.apply import bonus_apply
from crimson.bonuses.pool import BonusPool
from crimson.gameplay import GameplayState, player_update
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import giant_pact
from crimson.perks import PerkId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import crit as crit_module
from crimson.weapon_runtime import init_default_alt_weapon, weapon_assign_player
from crimson.weapon_runtime.availability import prepare_weapon_availability
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def _never_crit(monkeypatch: pytest.MonkeyPatch) -> None:
    # These tests fire many real shots through the ordinary fire_weapon()
    # pipeline to observe ammo/alternation behavior - crit outcome is
    # irrelevant to what's being asserted, but drawing from the shared,
    # never-reset _CRIT_RNG (weapon_runtime/crit.py, fixed-seeded once at
    # import time) would shift its state for whatever test happens to run
    # after this one in the same process. Pin it deterministically instead,
    # auto-reverted by monkeypatch teardown.
    monkeypatch.setattr(crit_module._CRIT_RNG, "random", lambda: 1.0)


def _dual_pistol_player() -> PlayerState:
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=GameplayState())
    init_default_alt_weapon(player)
    return player


def test_fire_rate_cost_mult_only_applies_when_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerState(index=0, pos=Vec2())
    _equip(monkeypatch)
    assert giant_pact.fire_rate_cost_mult(player) == 1.0
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    assert giant_pact.fire_rate_cost_mult(player) == 1.5


def test_dual_wielding_false_without_relic_or_without_an_alt_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    player = _dual_pistol_player()
    _equip(monkeypatch)
    assert not giant_pact.dual_wielding(player)
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    assert giant_pact.dual_wielding(player)
    player.alt_weapon = None
    assert not giant_pact.dual_wielding(player)


def test_both_weapons_fire_and_strictly_alternate(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    player = _dual_pistol_player()

    primary_shots = 0
    alt_shots = 0
    both_in_one_tick = 0
    dt = 0.05
    for _ in range(100):
        assert player.alt_weapon is not None
        before_primary = float(player.weapon.ammo)
        before_alt = float(player.alt_weapon.ammo)
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=dt, state=state)
        fired_primary = float(player.weapon.ammo) < before_primary
        fired_alt = float(player.alt_weapon.ammo) < before_alt
        if fired_primary:
            primary_shots += 1
        if fired_alt:
            alt_shots += 1
        if fired_primary and fired_alt:
            both_in_one_tick += 1

    # Strict alternation: never both slots in the same tick.
    assert both_in_one_tick == 0
    # Both slots actually got used - not just the primary.
    assert primary_shots > 0
    assert alt_shots > 0
    # Roughly even split (a perfect interleave for two identical weapons).
    assert abs(primary_shots - alt_shots) <= 1


def test_empty_slot_does_not_stall_the_other(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    player = _dual_pistol_player()
    assert player.alt_weapon is not None
    # Alt slot already dry and its cooldown already decayed to 0 (as if it
    # fired its last round a while ago) - it should never fire again, and
    # crucially must not block the primary from firing at its own solo rate.
    player.alt_weapon.ammo = 0.0
    player.alt_weapon.shot_cooldown = 0.0
    player.alt_weapon.shot_cooldown_max = 0.0

    primary_shots = 0
    dt = 0.05
    for _ in range(60):
        before = float(player.weapon.ammo)
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=dt, state=state)
        if float(player.weapon.ammo) < before:
            primary_shots += 1
        # Alt never fires - no ammo to lose.
        assert player.alt_weapon.ammo == 0.0

    assert primary_shots > 0


def test_both_slots_empty_auto_triggers_the_combined_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    player = _dual_pistol_player()
    assert player.alt_weapon is not None
    player.weapon.ammo = 1.0
    player.alt_weapon.ammo = 1.0

    for _ in range(80):
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=0.05, state=state)
        if player.weapon.reload_active or player.alt_weapon.reload_active:
            break
    else:
        pytest.fail("combined reload never triggered")

    # Two identical Pistols (reload_time 1.2 solo) -> max+min/2 == 1.2*1.5.
    assert player.weapon.reload_active
    assert player.alt_weapon.reload_active
    assert player.weapon.reload_timer == pytest.approx(1.2 * 1.5, abs=1e-3)
    assert player.alt_weapon.reload_timer == pytest.approx(1.2 * 1.5, abs=1e-3)


def test_combined_reload_duration_is_max_plus_half_min(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=state)  # reload_time 1.2
    player.alt_weapon = WeaponSlot(weapon_id=WeaponId.SHOTGUN, clip_size=12, ammo=0.0)  # reload_time 1.9

    giant_pact.start_combined_reload(player, state, players=[player], force=True)

    expected = max(1.2, 1.9) + min(1.2, 1.9) * 0.5
    assert player.weapon.reload_timer == pytest.approx(expected, abs=1e-4)
    assert player.weapon.reload_timer_max == pytest.approx(expected, abs=1e-4)
    assert player.alt_weapon.reload_timer == pytest.approx(expected, abs=1e-4)
    assert player.alt_weapon.reload_timer_max == pytest.approx(expected, abs=1e-4)


def test_combined_reload_reflects_a_per_weapon_perk_on_both_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.PISTOL, state=state)
    player.alt_weapon = WeaponSlot(weapon_id=WeaponId.SHOTGUN, clip_size=12, ammo=0.0)
    player.perk_counts[int(PerkId.FASTLOADER)] = 1

    giant_pact.start_combined_reload(player, state, players=[player], force=True)

    # Fastloader is x0.7 reload time - applies to both weapons' own solo
    # times before they're combined.
    expected = max(1.2, 1.9) * 0.7 + min(1.2, 1.9) * 0.7 * 0.5
    assert player.weapon.reload_timer_max == pytest.approx(expected, abs=1e-4)
    assert player.alt_weapon.reload_timer_max == pytest.approx(expected, abs=1e-4)


def test_manual_reload_forces_both_slots_full_and_flips_active_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    player = _dual_pistol_player()
    assert player.alt_weapon is not None
    player.weapon.ammo = 3.0
    player.alt_weapon.ammo = 7.0
    assert player.giant_pact_active_slot == 0

    player_update(player, PlayerInput(reload_pressed=True), dt=0.05, state=state)

    assert player.weapon.reload_active
    assert player.alt_weapon.reload_active
    assert player.weapon.reload_timer == pytest.approx(float(player.weapon.reload_timer_max))
    assert player.weapon.reload_timer_max == pytest.approx(float(player.alt_weapon.reload_timer_max))
    assert player.giant_pact_active_slot == 1


def test_weapon_pickup_targets_the_active_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    player = _dual_pistol_player()
    player.giant_pact_active_slot = 1

    bonus_apply(state, player, BonusId.WEAPON, amount=int(WeaponId.SHOTGUN), origin=player.pos, creatures=[], players=[player])

    assert player.weapon.weapon_id == WeaponId.PISTOL
    assert player.alt_weapon is not None
    assert player.alt_weapon.weapon_id == WeaponId.SHOTGUN


def test_already_carried_weapon_can_still_drop_while_dual_wielding(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same scripted RNG/player setup as
    # test_bonus_pistol_rules.py::test_weapon_drop_suppression_checks_all_carried_weapons_by_default,
    # which locks in the *without* the relic behavior (suppressed). This
    # locks in that owning Pact of the Giant makes it a no-op instead, so a
    # player can actually be offered a second copy of an already-carried gun.
    state = GameplayState()
    state.bonus_pool = BonusPool()
    prepare_weapon_availability(state)
    state.rng = ScriptedCrand([1, 13, 1, 2], fallback=ScriptedCrand.Fallback.ZERO)
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)

    player1 = PlayerState(index=0, pos=Vec2(), weapon=WeaponSlot(weapon_id=WeaponId.ASSAULT_RIFLE))
    player2 = PlayerState(index=1, pos=Vec2(500.0, 500.0), weapon=WeaponSlot(weapon_id=WeaponId.SHOTGUN))

    entry = state.bonus_pool.try_spawn_on_kill(pos=Vec2(256.0, 256.0), state=state, players=[player1, player2])

    assert entry is not None
    assert entry.bonus_id == BonusId.WEAPON
    assert entry.amount == WeaponId.SHOTGUN
