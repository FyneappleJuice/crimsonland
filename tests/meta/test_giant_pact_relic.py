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


@pytest.mark.parametrize(
    ("primary", "alt"),
    [(WeaponId.JACKHAMMER, WeaponId.PISTOL), (WeaponId.PISTOL, WeaponId.JACKHAMMER)],
)
def test_fast_weapon_waits_for_a_slow_partner(monkeypatch: pytest.MonkeyPatch, primary: WeaponId, alt: WeaponId) -> None:
    # Regression: the half-cooldown gate alone let a fast weapon (Jackhammer)
    # fire ~3 times per slow partner (Pistol) shot once the partner was past
    # its halfway point. Turns make every shot wait for the other weapon's.
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, alt, state=state)
    init_default_alt_weapon(player)
    assert player.alt_weapon is not None
    player.alt_weapon, player.weapon = player.weapon, player.alt_weapon
    weapon_assign_player(player, primary, state=state)
    player.weapon.ammo = 1000.0
    player.alt_weapon.ammo = 1000.0

    order: list[int] = []
    for _ in range(400):
        before = (float(player.weapon.ammo), float(player.alt_weapon.ammo))
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=1.0 / 60.0, state=state)
        if float(player.weapon.ammo) < before[0]:
            order.append(0)
        if float(player.alt_weapon.ammo) < before[1]:
            order.append(1)

    assert len(order) >= 6
    assert all(a != b for a, b in zip(order, order[1:])), order


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


def test_dual_wielding_costs_ten_percent_move_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Run enough ticks for move_speed's own accel ramp and turn-alignment
    # scale to settle, so the comparison isn't muddied by first-tick
    # transients - aim is set dead ahead of pos so heading needs no turning.
    dt = 1.0 / 60.0
    ticks = 90

    def run(pos: Vec2) -> float:
        state = GameplayState()
        player = _dual_pistol_player()
        player.pos = pos
        input_state = PlayerInput(move=Vec2(1.0, 0.0), aim=Vec2(pos.x + 100.0, pos.y))
        for _ in range(ticks):
            player_update(player, input_state, dt, state)
        return float(player.pos.x) - float(pos.x)

    _equip(monkeypatch)
    baseline_delta = run(Vec2(500.0, 500.0))
    assert baseline_delta > 0.0

    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    dual_delta = run(Vec2(500.0, 500.0))

    assert dual_delta == pytest.approx(baseline_delta * 0.9, rel=0.02)


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


def test_first_two_pickups_fill_both_starter_pistols(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    player = _dual_pistol_player()
    assert giant_pact.holding_starter_pistol(player)
    state = GameplayState()

    bonus_apply(state, player, BonusId.WEAPON, amount=int(WeaponId.JACKHAMMER), origin=player.pos, creatures=[], players=[player])
    assert player.weapon.weapon_id == WeaponId.JACKHAMMER
    assert player.alt_weapon is not None and player.alt_weapon.weapon_id == WeaponId.PISTOL
    # The alt slot's Pistol keeps the "starter pistol" forced drops going...
    assert giant_pact.holding_starter_pistol(player)

    # ...and the next pickup fills it, instead of replacing the Jackhammer.
    bonus_apply(state, player, BonusId.WEAPON, amount=int(WeaponId.ASSAULT_RIFLE), origin=player.pos, creatures=[], players=[player])
    assert player.weapon.weapon_id == WeaponId.JACKHAMMER
    assert player.alt_weapon.weapon_id == WeaponId.ASSAULT_RIFLE
    assert not giant_pact.holding_starter_pistol(player)

    # With no pistol left, pickups go back to the active slot.
    bonus_apply(state, player, BonusId.WEAPON, amount=int(WeaponId.SHOTGUN), origin=player.pos, creatures=[], players=[player])
    assert player.weapon.weapon_id == WeaponId.SHOTGUN


def test_starter_pistol_rule_ignores_the_alt_slot_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch)
    player = _dual_pistol_player()
    weapon_assign_player(player, WeaponId.JACKHAMMER, state=GameplayState())
    assert not giant_pact.holding_starter_pistol(player)  # native: primary only


@pytest.mark.parametrize("with_relic", [True, False])
def test_starter_pistol_forced_drops_stop_after_two_while_dual_wielding(
    monkeypatch: pytest.MonkeyPatch, with_relic: bool,
) -> None:
    from grim.rand import Crand

    if with_relic:
        _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    else:
        _equip(monkeypatch)
    state = GameplayState()
    state.bonus_pool = BonusPool()
    prepare_weapon_availability(state)
    state.rng = Crand(12345)
    player = _dual_pistol_player()  # never picks anything up - still all pistols

    for _ in range(300):
        state.bonus_pool.try_spawn_on_kill(pos=Vec2(256.0, 256.0), state=state, players=[player])
        for entry in state.bonus_pool.entries:  # nothing ever gets picked up
            state.bonus_pool._clear_entry(entry)

    expected = giant_pact.GIANT_PACT_FORCED_WEAPON_DROPS if with_relic else 0
    assert state.giant_pact_forced_weapon_drops == expected


def _dual_player(primary: WeaponId, alt: WeaponId) -> tuple[GameplayState, PlayerState]:
    from crimson.weapon_runtime.assign import weapon_slot_active

    state = GameplayState()
    player = _dual_pistol_player()
    assert player.alt_weapon is not None
    weapon_assign_player(player, primary, state=state)
    with weapon_slot_active(player, player.alt_weapon):
        weapon_assign_player(player, alt, state=state)
    return state, player


@pytest.mark.parametrize("perk", [PerkId.AMMO_MANIAC, PerkId.MY_FAVOURITE_WEAPON])
def test_clip_perks_apply_to_both_weapons(monkeypatch: pytest.MonkeyPatch, perk: PerkId) -> None:
    from crimson.perks.runtime.apply import perk_apply

    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.SHOTGUN)
    assert player.alt_weapon is not None
    before = (player.weapon.clip_size, player.alt_weapon.clip_size)
    perk_apply(state, [player], perk)
    assert player.weapon.clip_size > before[0]
    assert player.alt_weapon.clip_size > before[1]


def test_shots_carry_the_weapon_that_fired_them(monkeypatch: pytest.MonkeyPatch) -> None:
    # Weapon Affinity's damage bucket reads this at hit time - it used to use
    # the primary weapon for every shot, including the alt weapon's.
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.SHOTGUN)
    seen: set[int] = set()
    for _ in range(60):
        player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=1.0 / 60.0, state=state)
        seen |= {int(p.owner.weapon_id) for p in state.projectiles.entries if p.active}
    assert {int(WeaponId.ASSAULT_RIFLE), int(WeaponId.SHOTGUN)} <= seen


@pytest.mark.parametrize(
    "bonus_id",
    [BonusId.REFLEX_BOOST, BonusId.WEAPON_POWER_UP, BonusId.FIRE_BULLETS, BonusId.PLASMA_OVERLOAD],
)
def test_ammo_refilling_power_ups_refill_both_weapons(monkeypatch: pytest.MonkeyPatch, bonus_id: BonusId) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.SHOTGUN)
    assert player.alt_weapon is not None
    player.weapon.ammo = 0.0
    player.alt_weapon.ammo = 0.0
    player.alt_weapon.reload_timer = 1.5

    bonus_apply(state, player, bonus_id, amount=5, origin=player.pos, creatures=[], players=[player])

    assert player.weapon.ammo == float(player.weapon.clip_size)
    assert player.alt_weapon.ammo == float(player.alt_weapon.clip_size)
    assert player.alt_weapon.reload_timer == 0.0


def _fire_once(state: GameplayState, player: PlayerState) -> None:
    player_update(player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=1.0 / 60.0, state=state)


def test_a_weapon_firing_alone_uses_its_normal_fire_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)

    def _alt_cooldown(primary_ammo: float) -> float:
        state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.SHOTGUN)
        assert player.alt_weapon is not None
        player.weapon.ammo = primary_ammo
        player.giant_pact_next_slot = 1  # the Shotgun's turn
        _fire_once(state, player)
        return float(player.alt_weapon.shot_cooldown_max)

    both_loaded = _alt_cooldown(10.0)
    partner_dry = _alt_cooldown(0.0)
    assert both_loaded == pytest.approx(partner_dry * giant_pact.GIANT_PACT_FIRE_RATE_COST_MULT, rel=1e-4)


def test_plasma_overload_suppresses_dual_fire_to_the_normal_solo_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: Plasma Overload overrides every wielded weapon to the same
    # fixed-rate, zero-ammo-cost shot - before this fix, alternating between
    # two now-identical "weapons" cleared shots ~33% faster than a solo
    # player, a free DPS bump neither bonus is tuned for (unlike a real
    # weapon pair, e.g. Mini-Rocket Swarmers, whose own cooldown is untouched
    # by dual-wielding). Confirm the alt slot never fires while it's active,
    # and the shot count over time matches a solo player with the same bonus.
    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    _never_crit(monkeypatch)
    dt = 1.0 / 60.0
    ticks = 300

    dual_state = GameplayState()
    dual_player = _dual_pistol_player()
    dual_player.plasma_overload_timer = 1000.0
    assert dual_player.alt_weapon is not None
    alt_ammo_before = float(dual_player.alt_weapon.ammo)
    for _ in range(ticks):
        player_update(dual_player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=dt, state=dual_state)
    assert float(dual_player.alt_weapon.ammo) == pytest.approx(alt_ammo_before)
    dual_bolts = len([p for p in dual_state.projectiles.entries if p.active])

    # Baseline: a genuinely solo player, relic unequipped entirely - not just
    # "equipped but no alt_weapon", since giant_pact.fire_rate_cost_mult only
    # checks whether the relic is owned at all, not whether this particular
    # player is actually dual-wielding (a separate, pre-existing gap outside
    # this fix's scope).
    _equip(monkeypatch)
    solo_state = GameplayState()
    solo_player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(solo_player, WeaponId.PISTOL, state=solo_state)
    solo_player.plasma_overload_timer = 1000.0
    for _ in range(ticks):
        player_update(solo_player, PlayerInput(aim=Vec2(100.0, 0.0), fire_down=True), dt=dt, state=solo_state)
    solo_bolts = len([p for p in solo_state.projectiles.entries if p.active])

    assert dual_bolts > 0
    assert dual_bolts == solo_bolts


def test_second_forced_drop_leans_toward_the_first_weapon() -> None:
    from collections import Counter

    from crimson.weapon_runtime.tags import weapon_tags

    state = GameplayState()
    prepare_weapon_availability(state)
    first = WeaponId.PLASMA_RIFLE
    counts: Counter[int] = Counter()
    for seed in range(4000):
        state.rng.srand(seed)
        counts[giant_pact.pick_similar_weapon(state, int(first))] += 1

    tags = weapon_tags(first)
    same_class = [w for w in counts if weapon_tags(WeaponId(w)).archetype == tags.archetype and w != first]
    same_ammo = [w for w in counts if weapon_tags(WeaponId(w)).damage_type == tags.damage_type and w != first]
    unrelated = [
        w for w in counts
        if weapon_tags(WeaponId(w)).archetype != tags.archetype and weapon_tags(WeaponId(w)).damage_type != tags.damage_type
    ]
    assert counts.most_common(1)[0][0] == int(first)  # the same weapon is likeliest
    avg = lambda ids: sum(counts[w] for w in ids) / max(1, len(ids))  # noqa: E731
    assert avg(same_class) > 2 * avg(unrelated)
    assert avg(same_ammo) > 2 * avg(unrelated)
    assert int(WeaponId.PISTOL) not in counts


def test_fire_sound_and_pickup_popup_follow_the_actual_weapon(monkeypatch: pytest.MonkeyPatch) -> None:
    from crimson.sim.presentation_step import plan_player_audio_sfx
    from crimson.weapons import WEAPON_BY_ID

    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.ION_RIFLE)
    assert player.aux_weapon_id == int(WeaponId.ION_RIFLE)  # the popup names the alt pickup

    player.last_fired_weapon_id = int(WeaponId.ION_RIFLE)
    player.shot_seq = 1
    sfx = plan_player_audio_sfx(player, prev_shot_seq=0, prev_reload_active=False, prev_reload_timer=0.0)
    assert WEAPON_BY_ID[WeaponId.ION_RIFLE].fire_sound in sfx
    assert WEAPON_BY_ID[WeaponId.ASSAULT_RIFLE].fire_sound not in sfx


def test_ammo_shield_pays_from_the_fuller_weapon(monkeypatch: pytest.MonkeyPatch) -> None:
    from crimson.player_damage import AMMO_SHIELD_AMMO_COST, player_take_damage

    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state, player = _dual_player(WeaponId.ASSAULT_RIFLE, WeaponId.SHOTGUN)
    assert player.alt_weapon is not None
    player.perk_counts[int(PerkId.AMMO_SHIELD)] = 1
    player.weapon.ammo = 0.0
    player.alt_weapon.ammo = 8.0
    player_take_damage(state, player, 5.0, players=[player])
    assert player.weapon.ammo == 0.0
    assert player.alt_weapon.ammo == pytest.approx(8.0 - AMMO_SHIELD_AMMO_COST)


def test_random_weapon_perk_replaces_the_pickup_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    from crimson.perks.runtime.apply import perk_apply

    _equip(monkeypatch, RelicId.GIANT_PACT_LOW)
    state = GameplayState()
    prepare_weapon_availability(state)
    player = _dual_pistol_player()
    weapon_assign_player(player, WeaponId.ASSAULT_RIFLE, state=state)
    perk_apply(state, [player], PerkId.RANDOM_WEAPON)
    assert player.weapon.weapon_id == WeaponId.ASSAULT_RIFLE  # untouched...
    assert player.alt_weapon is not None and player.alt_weapon.weapon_id != WeaponId.PISTOL  # ...pistol replaced
