from __future__ import annotations

import pytest

from crimson.creatures import barrels as B
from crimson.creatures.damage import creature_apply_damage_with_lethal_followup
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreaturePool, _CreaturePoolCreatureDamageRuntime
from crimson.gameplay import GameplayState
from crimson.owner_ref import OwnerRef
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import make_creature_update_options
from tests.support.helpers import ScriptedCrand


def _runtime(pool: CreaturePool, state: GameplayState, *, players: list[PlayerState]) -> _CreaturePoolCreatureDamageRuntime:
    return _CreaturePoolCreatureDamageRuntime(
        pool=pool,
        state=state,
        players=players,
        rng=Crand(1),
        dt=0.016,
        detail_preset=5,
        world_width=1024.0,
        world_height=1024.0,
        fx_queue=None,
        deaths=[],
        sfx=[],
    )


def _kill(pool: CreaturePool, idx: int, state: GameplayState, *, players: list[PlayerState]) -> bool:
    creature = pool.entries[idx]
    return creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=idx,
        damage_amount=float(creature.hp) + 10.0,
        damage_type=int(CreatureDamageType.BULLET),
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=players,
        rng=Crand(1),
        creature_damage_runtime=_runtime(pool, state, players=players),
    )


def test_spawn_barrel_has_no_move_speed_and_is_flagged() -> None:
    pool = CreaturePool()
    idx = B.spawn_barrel(pool, Vec2(10.0, 20.0), player_level=5)
    creature = pool.entries[idx]

    assert creature.is_barrel is True
    assert creature.move_speed == 0.0
    assert creature.contact_damage == 0.0
    assert creature.hp == pytest.approx(B.barrel_health(5))
    assert creature.pos == Vec2(10.0, 20.0)


def test_touching_a_barrel_does_nothing() -> None:
    """Regression test: standing on/next to a barrel used to still run the
    full player-contact interaction pipeline (bite SFX, a "blood spill" FX
    burst, attack_cooldown) even though contact_damage is 0.0, because that
    pipeline only gated on creature size (>16), not on whether it's an actual
    monster - see runtime.py's per-tick creature-interaction dispatch."""
    state = GameplayState()
    pool = CreaturePool()
    rng = ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST)
    player = PlayerState(index=0, pos=Vec2(100.0, 100.0), health=100.0)

    idx = B.spawn_barrel(pool, Vec2(100.0, 100.0))
    creature = pool.entries[idx]

    pool.update(
        1.0 / 60.0,
        options=make_creature_update_options(state=state, players=[player], rng=rng),
    )

    assert player.health == pytest.approx(100.0)
    assert creature.attack_cooldown == 0.0
    assert [r.caller for r in rng.records_since() if r.caller is not None] == []


def test_barrel_count_respects_the_active_cap() -> None:
    pool = CreaturePool()
    spawned = [B.spawn_barrel(pool, Vec2(float(i), 0.0)) for i in range(B.BARREL_MAX_ACTIVE + 2)]

    assert B.count_active_barrels(pool) == B.BARREL_MAX_ACTIVE
    assert spawned.count(None) == 2


def test_barrel_keep_corpse_is_false_only_for_barrels() -> None:
    pool = CreaturePool()
    barrel_idx = B.spawn_barrel(pool, Vec2())
    normal_idx = pool._alloc_slot()
    pool.entries[normal_idx].active = True

    assert B.barrel_keep_corpse(pool.entries, barrel_idx) is False
    assert B.barrel_keep_corpse(pool.entries, normal_idx) is True


def test_barrel_leaves_no_corpse_and_queues_break_vfx_on_death() -> None:
    pool = CreaturePool()
    idx = B.spawn_barrel(pool, Vec2(5.0, 5.0))
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())

    killed = _kill(pool, idx, state, players=[player])

    assert killed is True
    assert pool.entries[idx].active is False  # no corpse-fade - vanished immediately
    assert len(state.pending_barrel_breaks) == 1
    assert state.pending_barrel_breaks[0].pos == Vec2(5.0, 5.0)


def test_barrel_break_vfx_ages_out_after_its_strip_finishes() -> None:
    state = GameplayState()
    state.pending_barrel_breaks.append(B.BarrelBreakEffect(pos=Vec2()))

    B.tick_barrel_break_effects(state, 0.2)
    assert len(state.pending_barrel_breaks) == 1

    B.tick_barrel_break_effects(state, 0.3)
    assert state.pending_barrel_breaks == []


def test_loot_roll_common_case_spawns_an_ordinary_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(B._BARREL_LOOT_RNG, "random", lambda: 0.99)
    pool = CreaturePool()
    idx = B.spawn_barrel(pool, Vec2(500.0, 500.0))
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())

    _kill(pool, idx, state, players=[player])

    active_bonuses = state.bonus_pool.iter_active()
    assert len(active_bonuses) == 1
    assert active_bonuses[0].pos == Vec2(500.0, 500.0)
    assert state.perk_selection.pending_count == 0
    assert sum(1 for c in pool.entries if c.active and not c.is_barrel) == 0


def test_loot_roll_rare_case_spawns_a_monster_instead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(B._BARREL_LOOT_RNG, "random", lambda: B.BARREL_FREE_PERK_CHANCE + 0.001)
    pool = CreaturePool()
    idx = B.spawn_barrel(pool, Vec2(3.0, 4.0))
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())

    _kill(pool, idx, state, players=[player])

    spawned_monsters = [c for c in pool.entries if c.active and not c.is_barrel]
    assert len(spawned_monsters) == 1
    assert state.bonus_pool.iter_active() == []
    assert state.perk_selection.pending_count == 0


def test_loot_roll_very_rare_case_grants_a_free_instant_perk_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(B._BARREL_LOOT_RNG, "random", lambda: 0.0)
    pool = CreaturePool()
    idx = B.spawn_barrel(pool, Vec2())
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())

    _kill(pool, idx, state, players=[player])

    assert state.perk_selection.pending_count == 1
    assert state.perk_selection.choices_dirty is True
    assert state.run_mod_selection.pending_count == 1
    assert state.run_mod_selection.choices_dirty is True
    assert state.bonus_pool.iter_active() == []
    assert sum(1 for c in pool.entries if c.active and not c.is_barrel) == 0
