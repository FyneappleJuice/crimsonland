from __future__ import annotations

import math

import msgspec
import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import impaler
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool, SecondaryStepCtx
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import RecordingCreatureDamageRuntime, make_projectile_update_options
from tests.support.factories import make_creature_state as _creature

_TIERS = [(RelicId.IMPALER_LOW, 1.12), (RelicId.IMPALER_MEDIUM, 1.20), (RelicId.IMPALER_HIGH, 1.30)]


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


def _hit_totals(hits: int) -> list[float]:
    """Total damage (direct + burst) each of `hits` 100-damage hits deals to
    one creature, relative to an un-relicked 100."""
    creature = CreatureState(active=True, hp=1.0e9, max_hp=1.0e9)
    out = []
    for _ in range(hits):
        direct = 100.0 * impaler.IMPALER_DIRECT_MULT
        burst = impaler.on_direct_hit(creature, direct)
        out.append((direct + burst) / 100.0)
    return out


@pytest.mark.parametrize(("relic", "steady"), _TIERS)
def test_ramps_from_minus_20_to_the_tier_value(monkeypatch: pytest.MonkeyPatch, relic: RelicId, steady: float) -> None:
    _equip(monkeypatch, relic)
    totals = _hit_totals(10)
    assert totals[0] == pytest.approx(0.80)
    assert totals == sorted(totals)
    for total in totals[5:]:  # 6th hit onward: 5 Impales up
        assert total == pytest.approx(steady)


def test_each_impale_lasts_five_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.IMPALER_HIGH)
    creature = CreatureState(active=True, hp=1.0e9, max_hp=1.0e9)
    for _ in range(12):
        impaler.on_direct_hit(creature, 80.0)
        assert len(creature.impale_stored) <= impaler.IMPALER_MAX_HITS
    assert len(creature.impale_stored) == impaler.IMPALER_MAX_HITS
    assert sorted(creature.impale_hits_left) == [1, 2, 3, 4, 5]


def test_fresh_impale_refreshes_the_stack_and_it_expires_unhit(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.IMPALER_HIGH)
    creature = CreatureState(active=True, hp=1.0e9, max_hp=1.0e9)
    impaler.on_direct_hit(creature, 80.0)
    impaler.tick(creature, 7.0)
    impaler.on_direct_hit(creature, 80.0)  # refreshes the whole stack...
    assert creature.impale_timer == pytest.approx(impaler.IMPALER_DURATION)
    impaler.tick(creature, 7.0)
    assert len(creature.impale_stored) == 2  # ...so the first one is still up at 14s
    impaler.tick(creature, 1.5)  # 8.5s since the last hit
    assert creature.impale_stored == []
    assert creature.impale_timer == 0.0


def test_nothing_happens_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch)
    assert not impaler.impaler_active_for(OwnerRef.from_local_player(0))
    _equip(monkeypatch, RelicId.IMPALER_HIGH)
    assert impaler.impaler_active_for(OwnerRef.from_local_player(0))
    assert not impaler.impaler_active_for(OwnerRef.from_creature(2))
    burst_owner = msgspec.structs.replace(OwnerRef.from_local_player(0), via_impale=True)
    assert not impaler.impaler_active_for(burst_owner)


def test_bullets_ramp_up_on_one_target(monkeypatch: pytest.MonkeyPatch) -> None:
    def _per_hit_damage() -> list[float]:
        creature = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
        player = PlayerState(index=0, pos=Vec2(100.0, 512.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
        options = make_projectile_update_options(world_size=1024.0, players=[player])
        pool = ProjectilePool(size=0x60)
        out = []
        for _ in range(8):
            before = creature.hp
            pool.spawn(
                pos=Vec2(110.0, 512.0),
                angle=math.pi / 2,
                type_id=ProjectileTemplateId.PISTOL,
                owner=OwnerRef.from_local_player(0),
            )
            for _ in range(40):
                pool.step(PrimaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), options=options))
            out.append(before - creature.hp)
        return out

    _equip(monkeypatch)
    plain = _per_hit_damage()
    _equip(monkeypatch, RelicId.IMPALER_HIGH)
    impaled = _per_hit_damage()
    assert impaled[0] == pytest.approx(plain[0] * 0.80, rel=1e-4)
    # (Pistol damage varies a hair with the exact hit point, so the stored
    # Impales from earlier shots don't match the last shot to the digit.)
    assert impaled[-1] == pytest.approx(plain[-1] * 1.30, rel=5e-3)


def test_rocket_impact_impales_but_its_blast_ticks_dont(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.IMPALER_HIGH)
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2())
    weapon_assign_player(player, WeaponId.ROCKET_LAUNCHER, state=state)
    player.aim_heading = math.pi / 2
    creature = _creature(pos=Vec2(120.0, 0.0), hp=1.0e9)
    runtime = RecordingCreatureDamageRuntime(creatures=(creature,))
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=creature.pos),
            dt=0.016,
            state=state,
            creatures=(creature,),
        ),
    )
    for _ in range(120):
        state.secondary_projectiles.step(
            SecondaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), runtime_state=state, players=[player], creature_damage_runtime=runtime),
        )
    # One Impale from the single impact - dozens of blast ticks added none.
    assert len(creature.impale_stored) == 1


def test_impale_burst_does_not_heal_through_leech(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.LEECH_HIGH)
    player = PlayerState(index=0, pos=Vec2(), health=50.0)

    def _dealt(owner: OwnerRef) -> None:
        creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0)
        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(CreatureDamageType.BULLET),
            impulse=Vec2(),
            owner=owner,
            dt=0.016,
            players=[player],
            rng=Crand(1),
        )

    _dealt(msgspec.structs.replace(OwnerRef.from_player(0), via_impale=True))
    assert float(player.health) == 50.0
    _dealt(OwnerRef.from_player(0))
    assert float(player.health) > 50.0
