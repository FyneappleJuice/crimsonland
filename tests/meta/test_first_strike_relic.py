from __future__ import annotations

import math

import msgspec
import pytest

from crimson.creatures.runtime import CreatureState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.meta.relics_impl import first_strike
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature, make_projectile_update_options

PLAYER = OwnerRef.from_local_player(0)


def _equip(monkeypatch: pytest.MonkeyPatch, *relic_ids: RelicId) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", tuple(int(r) for r in relic_ids))


@pytest.mark.parametrize(("relic", "opener"), [(RelicId.FIRST_STRIKE_LOW, 1.60)])
def test_only_the_very_first_hit_gets_the_bonus(monkeypatch: pytest.MonkeyPatch, relic: RelicId, opener: float) -> None:
    _equip(monkeypatch, relic)
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    assert first_strike.opening_hit_mult(creature, PLAYER) == pytest.approx(opener)
    assert creature.struck is True
    # The rest of a shotgun blast landing the same frame, and every later shot.
    for _ in range(7):
        assert first_strike.opening_hit_mult(creature, PLAYER) == 1.0


def test_only_player_hits_strike(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FIRST_STRIKE_LOW)
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    assert first_strike.opening_hit_mult(creature, OwnerRef.from_creature(4)) == 1.0
    assert first_strike.opening_hit_mult(creature, msgspec.structs.replace(PLAYER, via_impale=True)) == 1.0
    assert creature.struck is False


def test_unstruck_creatures_hit_harder(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch, RelicId.FIRST_STRIKE_LOW)
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    assert first_strike.incoming_damage_mult(creature) == pytest.approx(1.40)
    first_strike.opening_hit_mult(creature, PLAYER)
    assert first_strike.incoming_damage_mult(creature) == 1.0
    assert first_strike.incoming_damage_mult(None) == 1.0


def test_nothing_happens_without_the_relic(monkeypatch: pytest.MonkeyPatch) -> None:
    _equip(monkeypatch)
    creature = CreatureState(active=True, hp=100.0, max_hp=100.0)
    assert first_strike.incoming_damage_mult(creature) == 1.0
    assert first_strike.opening_hit_mult(creature, PLAYER) == 1.0


def test_bullets_open_big_then_deal_normal_damage(monkeypatch: pytest.MonkeyPatch) -> None:
    def _per_hit_damage() -> list[float]:
        creature = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
        player = PlayerState(index=0, pos=Vec2(100.0, 512.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
        options = make_projectile_update_options(world_size=1024.0, players=[player])
        pool = ProjectilePool(size=0x60)
        out = []
        for _ in range(3):
            before = creature.hp
            pool.spawn(pos=Vec2(110.0, 512.0), angle=math.pi / 2, type_id=ProjectileTemplateId.PISTOL, owner=PLAYER)
            for _ in range(40):
                pool.step(PrimaryStepCtx(dt=1.0 / 60.0, creatures=(creature,), options=options))
            out.append(before - creature.hp)
        return out

    _equip(monkeypatch)
    plain = _per_hit_damage()
    _equip(monkeypatch, RelicId.FIRST_STRIKE_LOW)
    struck = _per_hit_damage()
    assert struck[0] == pytest.approx(plain[0] * 1.60, rel=1e-4)
    assert struck[1] == pytest.approx(plain[1], rel=1e-4)
    assert struck[2] == pytest.approx(plain[2], rel=1e-4)
