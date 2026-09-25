from __future__ import annotations

import math

import pytest

from crimson.creatures.runtime import CreatureState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import fortify
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature, make_projectile_update_options


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def _target(max_hp: float = 100.0, rarity: int = 0) -> CreatureState:
    return CreatureState(active=True, hp=max_hp, max_hp=max_hp, rarity=rarity)


def _gain(player: PlayerState, creature: CreatureState, damage: float, *, then: float = 0.1) -> None:
    fortify.gain_from_hit(player, creature, damage)
    fortify.tick(player, then)


@pytest.mark.parametrize(
    ("damage", "max_hp", "rarity", "stacks"),
    [
        (50.0, 100.0, 0, 1.0),  # half a normal zombie's HP = 1 stack
        (3.0, 100.0, 0, 0.06),  # tiny hits give a fraction - no minimum
        (500.0, 100.0, 0, 5.0),  # capped at 5 per hit
        (50.0, 100.0, 1, 1.5),  # Tainted x1.5
        (50.0, 100.0, 3, 3.0),  # Apex x3
    ],
)
def test_stacks_per_hit(damage: float, max_hp: float, rarity: int, stacks: float) -> None:
    assert fortify.stacks_for_hit(_target(max_hp, rarity), damage) == pytest.approx(stacks)


@pytest.mark.parametrize(("relic", "cap"), [(RelicId.FORTIFY_LOW, 12), (RelicId.FORTIFY_MEDIUM, 20), (RelicId.FORTIFY_HIGH, 30)])
def test_capped_per_tier_at_1_percent_per_stack(monkeypatch: pytest.MonkeyPatch, relic: RelicId, cap: int) -> None:
    _equip(monkeypatch, relic)
    player = PlayerState(index=0, pos=Vec2())
    for _ in range(10):
        _gain(player, _target(), 500.0)
    assert fortify.current_stacks(player) == cap
    assert fortify.damage_taken_mult(player) == pytest.approx(1.0 - cap / 100.0)
    assert fortify.fill_fraction(player) == pytest.approx(1.0)


def test_partial_stacks_add_up_and_display_rounds_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    for _ in range(7):
        _gain(player, _target(), 20.0)  # 0.4 each
    assert sum(player.fortify_stacks) == pytest.approx(2.8)
    assert fortify.current_stacks(player) == 2


def test_hits_within_a_tenth_of_a_second_pool_into_one_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    for _ in range(8):  # a shotgun blast's pellets, same frame
        fortify.gain_from_hit(player, _target(), 25.0)
    assert len(player.fortify_stacks) == 1
    assert player.fortify_stacks[0] == pytest.approx(4.0)  # nothing lost
    fortify.tick(player, 0.1)
    fortify.gain_from_hit(player, _target(), 25.0)
    assert len(player.fortify_stacks) == 2


def test_sustained_stacks_track_damage_per_second_over_target_hp(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    # 150 damage/s against 100-HP targets, as 3 hits/s, for 10s.
    for _ in range(30):
        _gain(player, _target(), 50.0, then=1.0 / 3.0)
    # ~ 2 * 4s * 1.5 = 12, minus the partial window since the last hit.
    assert 10 <= fortify.current_stacks(player) <= 12


def test_instances_expire_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    _gain(player, _target(), 250.0)  # 5 at t=0
    fortify.tick(player, 1.0)
    _gain(player, _target(), 250.0)  # ~5 more at ~t=1.1
    assert sum(player.fortify_stacks) == pytest.approx(10.0, rel=1e-3)
    fortify.tick(player, 2.9)  # the first (4s) expires, the second doesn't
    assert sum(player.fortify_stacks) == pytest.approx(5.0, rel=1e-3)
    fortify.tick(player, 1.2)
    assert fortify.current_stacks(player) == 0


@pytest.mark.parametrize(
    ("relic", "cap", "low", "high"),
    [
        (RelicId.FORTIFY_LOW, 12, 0.90, 0.98),
        (RelicId.FORTIFY_MEDIUM, 20, 0.87, 0.96),
        (RelicId.FORTIFY_HIGH, 30, 0.80, 0.92),
    ],
)
def test_fast_killer_settles_near_but_below_the_cap(
    monkeypatch: pytest.MonkeyPatch, relic: RelicId, cap: int, low: float, high: float,
) -> None:
    # Rocket Minigun-ish: 5 rockets/s, each worth ~2 stacks undiminished -
    # enough for ~40 without diminishing returns.
    _equip(monkeypatch, relic)
    player = PlayerState(index=0, pos=Vec2())
    samples = []
    for i in range(150):  # 30s of fire; average the last 20s
        _gain(player, _target(), 100.0, then=0.2)
        if i >= 50:
            samples.append(sum(player.fortify_stacks))
    held = sum(samples) / len(samples)
    assert low * cap <= held <= high * cap


def test_gains_are_barely_slowed_far_from_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2())
    _gain(player, _target(), 250.0)  # 5 of 30
    fortify.gain_from_hit(player, _target(), 250.0)  # pooled into the next window
    assert sum(player.fortify_stacks) == pytest.approx(10.0, rel=1e-3)


def test_cost_and_nothing_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_MEDIUM)
    assert fortify.speed_mult() == pytest.approx(0.90)
    _equip(monkeypatch)
    assert fortify.speed_mult() == 1.0
    player = PlayerState(index=0, pos=Vec2())
    fortify.gain_from_hit(player, _target(), 500.0)
    assert fortify.current_stacks(player) == 0
    assert fortify.damage_taken_mult(player) == 1.0


def test_bullet_hits_build_fortification(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FORTIFY_HIGH)
    player = PlayerState(index=0, pos=Vec2(100.0, 512.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    creature = _creature(pos=Vec2(400.0, 512.0), hp=1000.0)
    pool = ProjectilePool(size=0x60)
    pool.spawn(pos=Vec2(110.0, 512.0), angle=math.pi / 2, type_id=ProjectileTemplateId.PISTOL, owner=OwnerRef.from_local_player(0))
    options = make_projectile_update_options(world_size=1024.0, players=[player])
    for _ in range(40):
        pool.step(PrimaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), options=options))
    # One pistol hit on a 1000-HP target is a fraction of a stack (~0.09).
    assert 0.0 < sum(player.fortify_stacks) < 1.0
