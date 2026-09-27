from __future__ import annotations

import pytest

from crimson.creatures import dummy as D
from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreaturePool
from crimson.owner_ref import OwnerRef
from grim.geom import Vec2
from grim.rand import Crand


def test_spawn_test_dummy_has_huge_health_and_does_not_move() -> None:
    pool = CreaturePool()
    idx = D.spawn_test_dummy(pool, Vec2(100.0, 200.0))
    assert idx is not None
    c = pool.entries[idx]

    assert c.active is True
    assert c.is_test_dummy is True
    assert c.hp == pytest.approx(D.DUMMY_HEALTH)
    assert c.max_hp == pytest.approx(D.DUMMY_HEALTH)
    assert c.move_speed == 0.0
    assert c.pos == Vec2(100.0, 200.0)


def test_spawn_stationary_test_monster_has_one_hp_and_does_not_move() -> None:
    pool = CreaturePool()
    idx = D.spawn_stationary_test_monster(pool, Vec2(50.0, 60.0))
    assert idx is not None
    c = pool.entries[idx]

    assert c.is_test_dummy is False
    assert c.hp == pytest.approx(1.0)
    assert c.max_hp == pytest.approx(1.0)
    assert c.move_speed == 0.0


def test_stationary_test_monster_dies_normally_on_a_single_hit() -> None:
    pool = CreaturePool()
    idx = D.spawn_stationary_test_monster(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[],
        rng=Crand(1),
    )

    assert killed is True
    assert creature.hp <= 0.0


def test_damage_dummy_never_dies_to_realistic_hits() -> None:
    pool = CreaturePool()
    idx = D.spawn_test_dummy(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]

    for _ in range(50):
        killed = creature_apply_damage(
            creature,
            damage_amount=10_000.0,
            damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[],
            rng=Crand(1),
        )
        assert killed is False
    assert creature.hp > 0.0


def test_damage_dummy_tracks_damage_dps_and_last_hit_matching_the_worked_example() -> None:
    """10 shots x 100 damage spread over 5 real seconds -> damage=1000,
    dps~=200, last hit=100 (the owner's own worked example)."""
    pool = CreaturePool()
    idx = D.spawn_test_dummy(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]

    dt_between_shots = 5.0 / 9.0  # 10 shots -> 9 gaps spanning 5s
    for i in range(10):
        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[],
            rng=Crand(1),
        )
        if i < 9:
            D.update_test_dummies(pool, dt_between_shots)

    assert creature.dummy_damage_total == pytest.approx(1000.0)
    assert creature.dummy_last_hit_amount == pytest.approx(100.0)
    assert D.dummy_dps(creature) == pytest.approx(1000.0 / 5.0, rel=0.05)


def test_damage_resets_after_five_seconds_of_silence() -> None:
    pool = CreaturePool()
    idx = D.spawn_test_dummy(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]

    creature_apply_damage(
        creature, damage_amount=250.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert creature.dummy_damage_total == pytest.approx(250.0)

    D.update_test_dummies(pool, 4.0)
    assert creature.dummy_damage_total == pytest.approx(250.0)  # not reset yet

    D.update_test_dummies(pool, 1.5)  # crosses the 5s mark
    assert creature.dummy_damage_total == 0.0
    assert creature.dummy_last_hit_amount == 0.0

    # A fresh hit after the reset starts a brand new streak.
    creature_apply_damage(
        creature, damage_amount=42.0, damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(), owner=OwnerRef.from_local_player(0), dt=0.016, players=[], rng=Crand(1),
    )
    assert creature.dummy_damage_total == pytest.approx(42.0)
    assert D.dummy_dps(creature) == pytest.approx(42.0)  # only one hit so far - no elapsed span yet


def test_a_dummy_is_a_legal_target_for_nearest_enemy_scans() -> None:
    """Domino Effect / Stunt Double style scans only check active + hp>0 -
    verify a spawned dummy and stationary monster satisfy that with no extra
    tagging, per creatures/runtime.py's _fire_momentum_shot and
    perks/impl/hollow_form.py's _nearest_living_creature_pos."""
    pool = CreaturePool()
    dummy_idx = D.spawn_test_dummy(pool, Vec2(10.0, 10.0))
    monster_idx = D.spawn_stationary_test_monster(pool, Vec2(20.0, 20.0))

    for idx in (dummy_idx, monster_idx):
        c = pool.entries[idx]
        assert c.active is True
        assert float(c.hp) > 0.0
