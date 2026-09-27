from __future__ import annotations

from crimson.creatures import dummy as D
from crimson.creatures.damage import creature_apply_damage_with_lethal_followup
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreaturePool, _CreaturePoolCreatureDamageRuntime
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from grim.geom import Vec2
from grim.rand import Crand


def _runtime(pool: CreaturePool, state: GameplayState) -> _CreaturePoolCreatureDamageRuntime:
    return _CreaturePoolCreatureDamageRuntime(
        pool=pool,
        state=state,
        players=[],
        rng=Crand(1),
        dt=0.016,
        detail_preset=5,
        world_width=1024.0,
        world_height=1024.0,
        fx_queue=None,
        deaths=[],
        sfx=[],
    )


def test_stationary_test_monster_leaves_no_corpse_on_death() -> None:
    """Regression test for the owner's ask: no corpse/death animation on
    sandbox test entities - a normal creature keeps its lifecycle_stage
    corpse-fade, but these should just vanish (active=False immediately)."""
    pool = CreaturePool()
    idx = D.spawn_stationary_test_monster(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]
    state = GameplayState()

    killed = creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=idx,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[],
        rng=Crand(1),
        creature_damage_runtime=_runtime(pool, state),
    )

    assert killed is True
    assert creature.active is False  # no corpse - instantly removed from the pool


def test_a_normal_creature_still_keeps_its_corpse_fade() -> None:
    """Sanity check that the no-corpse behavior is scoped to sandbox
    entities only - an ordinary creature's death still fades out normally."""
    pool = CreaturePool()
    idx = pool._alloc_slot()
    creature = pool.entries[idx]
    creature.active = True
    creature.hp = 10.0
    creature.max_hp = 10.0
    creature.pos = Vec2(0.0, 0.0)
    state = GameplayState()

    killed = creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=idx,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[],
        rng=Crand(1),
        creature_damage_runtime=_runtime(pool, state),
    )

    assert killed is True
    assert creature.active is True  # still corpse-fading, not instantly removed


def test_stationary_test_monster_auto_respawns_after_five_seconds() -> None:
    pool = CreaturePool()
    idx = D.spawn_stationary_test_monster(pool, Vec2(40.0, 60.0))
    creature = pool.entries[idx]
    state = GameplayState()

    creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=idx,
        damage_amount=10.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[],
        rng=Crand(1),
        creature_damage_runtime=_runtime(pool, state),
    )

    assert len(state.pending_test_monster_respawns) == 1
    assert sum(1 for c in pool.entries if c.active) == 0

    # Not enough time yet.
    D.tick_test_monster_respawns(pool, state, D.STATIONARY_MONSTER_RESPAWN_DELAY_S - 0.5)
    assert sum(1 for c in pool.entries if c.active) == 0

    # Fuse runs out - a fresh stationary monster appears at the same spot.
    D.tick_test_monster_respawns(pool, state, 1.0)
    assert state.pending_test_monster_respawns == []
    respawned = [c for c in pool.entries if c.active]
    assert len(respawned) == 1
    assert respawned[0].pos == Vec2(40.0, 60.0)
    assert respawned[0].hp == D.STATIONARY_MONSTER_HEALTH


def test_damage_dummy_death_never_queues_a_respawn() -> None:
    # The damage dummy has huge HP and never realistically dies, but if it
    # somehow did, it shouldn't queue the stationary-monster respawn timer.
    pool = CreaturePool()
    idx = D.spawn_test_dummy(pool, Vec2(0.0, 0.0))
    creature = pool.entries[idx]
    state = GameplayState()

    creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=idx,
        damage_amount=D.DUMMY_HEALTH * 2.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[],
        rng=Crand(1),
        creature_damage_runtime=_runtime(pool, state),
    )

    assert state.pending_test_monster_respawns == []
