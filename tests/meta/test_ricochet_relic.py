from __future__ import annotations

import math

import pytest

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.gameplay import GameplayState
from crimson.meta import relics
from crimson.meta.relics import RelicId
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool, SecondaryStepCtx
from crimson.projectiles.types import ProjectileTemplateId
from crimson.sim.input import PlayerInput
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapon_runtime import WeaponFireCtx, fire_weapon, weapon_assign_player
from crimson.weapons import WeaponId
from grim.geom import Vec2
from grim.rand import Crand
from tests.support.factories import RecordingCreatureDamageRuntime
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


@pytest.fixture(autouse=True)
def _ricochet_equipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(relics, "_ACTIVE_RELIC_IDS", (int(RelicId.RICOCHET_HIGH),))


def _fire(pool: ProjectilePool) -> None:
    pool.spawn(
        pos=Vec2(110.0, 512.0),
        angle=math.pi / 2,  # heading convention: 0=up, +90deg=+x
        type_id=ProjectileTemplateId.PISTOL,
        owner=OwnerRef.from_local_player(0),
    )


def _step(pool: ProjectilePool, creatures: tuple, *, ticks: int) -> None:
    player = PlayerState(index=0, pos=Vec2(100.0, 512.0), weapon=WeaponSlot(weapon_id=WeaponId.PISTOL))
    options = make_projectile_update_options(world_size=1024.0, players=[player])
    for _ in range(ticks):
        pool.step(PrimaryStepCtx(dt=1.0 / 60.0, creatures=creatures, options=options))


@pytest.mark.parametrize("angle_deg", range(0, 360, 30))
def test_bounce_reaches_a_target_overlapping_the_struck_creature(angle_deg: int) -> None:
    # Packed-horde case: the chain target sits inside the struck creature's own
    # hit radius, so the bounce used to re-hit the struck creature instead.
    struck = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    a = math.radians(angle_deg)
    other = _creature(pos=Vec2(400.0 + 10.0 * math.cos(a), 512.0 + 10.0 * math.sin(a)), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    _fire(pool)
    _step(pool, (struck, other), ticks=60)
    assert other.hp < 1.0e9


def test_reused_pool_slot_does_not_inherit_the_chained_flag() -> None:
    pool = ProjectilePool(size=4)
    idx = pool.spawn(pos=Vec2(0.0, 0.0), angle=0.0, type_id=ProjectileTemplateId.PISTOL, owner=OwnerRef.none())
    pool.entries[idx].ricochet_chained = True
    pool.entries[idx].ricochet_ignore_idx = 3
    pool.entries[idx].active = False

    reused = pool.spawn(pos=Vec2(0.0, 0.0), angle=0.0, type_id=ProjectileTemplateId.PISTOL, owner=OwnerRef.none())
    assert reused == idx
    assert pool.entries[reused].ricochet_chained is False
    assert pool.entries[reused].ricochet_ignore_idx == -1


def test_stop_on_hit_false_weapon_still_only_chains_once() -> None:
    # Regression: Fire Bullets / Gauss Gun / Blade Gun don't stop on hit (they
    # pierce via damage_pool depletion, not pierce_left, so the pierce_left <
    # 1.0 chain-eligibility check doesn't exclude them). The chained flag used
    # to only be set on the spawned bounce, never on the original bolt itself -
    # so a single bolt that went on to hit several more creatures in the same
    # flight re-chained on every one of them instead of just the first.
    pool = ProjectilePool(size=0x60)
    creatures = tuple(_creature(pos=Vec2(400.0 + 60.0 * i, 512.0), size=10.0, hp=1.0) for i in range(5))
    pool.spawn(
        pos=Vec2(100.0, 512.0),
        angle=math.pi / 2,
        type_id=ProjectileTemplateId.FIRE_BULLETS,
        owner=OwnerRef.from_local_player(0),
    )
    _step(pool, creatures, ticks=80)

    assert sum(1 for c in creatures if c.hp <= 0.0) >= 2, "test setup: the bolt should pierce through multiple creatures"
    bounces = [e for e in pool.entries if e.ricochet_ignore_idx != -1]
    assert len(bounces) == 1


def test_every_shot_in_sustained_fire_chains() -> None:
    struck = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    other = _creature(pos=Vec2(400.0, 650.0), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    for _ in range(40):
        before = other.hp
        _fire(pool)
        _step(pool, (struck, other), ticks=4)  # next shot fires before this one's bounce slot frees up
        _step(pool, (struck, other), ticks=20)
        assert other.hp < before


def _damage_dealt(*, crit_mult: float = 1.0) -> tuple[float, float]:
    struck = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    other = _creature(pos=Vec2(400.0, 650.0), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    _fire(pool)
    pool.entries[0].crit_mult = float(crit_mult)
    _step(pool, (struck, other), ticks=60)
    return 1.0e9 - struck.hp, 1.0e9 - other.hp


def test_bounce_deals_exactly_what_the_original_hit_dealt() -> None:
    # Regression: bullet damage falls off with distance from the shot's
    # origin, and the bounce was recomputed from its own spawn point right
    # next to its target - a point-blank hit worth ~2.4x the original shot.
    first, bounce = _damage_dealt()
    assert first > 0.0
    assert bounce == pytest.approx(first)


def test_bounce_keeps_the_parent_shots_multipliers() -> None:
    # A Domino Effect shot's 0.25x (stamped into crit_mult) carries over to its
    # bounce. (The Ricochet penalty itself is applied later, centrally, in
    # creature_apply_damage - see test_penalty_applies_to_all_player_damage.)
    from crimson.creatures.runtime import MOMENTUM_DAMAGE_MULT

    plain_first, _ = _damage_dealt()
    first, bounce = _damage_dealt(crit_mult=MOMENTUM_DAMAGE_MULT)
    assert first == pytest.approx(plain_first * MOMENTUM_DAMAGE_MULT, rel=1e-5)
    assert bounce == pytest.approx(first)


def _without_relic(monkeypatch: pytest.MonkeyPatch, fn):
    with monkeypatch.context() as m:
        m.setattr(relics, "_ACTIVE_RELIC_IDS", ())
        return fn()


def test_bullet_hit_and_its_bounce_pay_the_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    first, bounce = _damage_dealt()
    plain, _ = _without_relic(monkeypatch, _damage_dealt)
    assert first == pytest.approx(plain * 0.7, rel=1e-5)  # High tier: 30% less
    assert bounce == pytest.approx(first)


def _ion_rifle_total_damage() -> float:
    # Ion Rifle bolt + its lingering cloud, on a lone creature (no bounce).
    creature = _creature(pos=Vec2(400.0, 512.0), hp=1.0e9)
    pool = ProjectilePool(size=0x60)
    pool.spawn(
        pos=Vec2(110.0, 512.0),
        angle=math.pi / 2,
        type_id=ProjectileTemplateId.ION_RIFLE,
        owner=OwnerRef.from_local_player(0),
    )
    _step(pool, (creature,), ticks=120)
    return 1.0e9 - creature.hp


def test_ion_bolt_and_its_cloud_pay_the_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    with_relic = _ion_rifle_total_damage()
    plain = _without_relic(monkeypatch, _ion_rifle_total_damage)
    assert plain > 0.0
    assert with_relic == pytest.approx(plain * 0.7, rel=1e-4)


def test_non_projectile_damage_is_not_penalized() -> None:
    # Nuke, Man Bomb, Radioactive, flamethrower/ignite, ... all resolve through
    # creature_apply_damage directly - no projectile, so no penalty.
    for damage_type in (CreatureDamageType.EXPLOSION, CreatureDamageType.FIRE, CreatureDamageType.ION):
        creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0)
        creature_apply_damage(
            creature,
            damage_amount=10.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_player(0),
            dt=0.016,
            players=[PlayerState(index=0, pos=Vec2())],
            rng=Crand(1),
        )
        assert 1000.0 - float(creature.hp) == pytest.approx(10.0, rel=1e-5)


def _fire_rocket_into_pair(weapon_id: WeaponId) -> tuple[RecordingCreatureDamageRuntime, tuple, PlayerState]:
    state = GameplayState()
    player = PlayerState(index=0, pos=Vec2(0.0, 0.0))
    weapon_assign_player(player, weapon_id, state=state)
    player.aim_heading = math.pi / 2  # heading convention: 0=up, +90deg=+x
    struck = _creature(pos=Vec2(120.0, 0.0), hp=1.0e9)
    other = _creature(pos=Vec2(120.0, 200.0), hp=1.0e9)
    creatures = (struck, other)
    runtime = RecordingCreatureDamageRuntime(creatures=creatures)
    fire_weapon(
        WeaponFireCtx(
            player=player,
            input_state=PlayerInput(fire_down=True, aim=struck.pos),
            dt=0.016,
            state=state,
            creatures=creatures,
        ),
    )
    for _ in range(240):
        state.secondary_projectiles.step(
            SecondaryStepCtx(
                dt=1.0 / 60.0,
                creatures=creatures,
                runtime_state=state,
                players=[player],
                creature_damage_runtime=runtime,
            ),
        )
    return runtime, creatures, player


def _direct_hits(runtime: RecordingCreatureDamageRuntime) -> list:
    # A rocket's direct hit carries its full velocity as impulse (x 1/dt); the
    # detonation AoE ticks that follow carry only a tiny push.
    return [c for c in runtime.calls if c[2] == int(CreatureDamageType.EXPLOSION) and c[3].length() > 100.0]


@pytest.mark.parametrize(
    "weapon_id",
    [WeaponId.ROCKET_LAUNCHER, WeaponId.SEEKER_ROCKETS, WeaponId.ROCKET_MINIGUN],
)
def test_rocket_direct_hit_chains_to_another_creature(weapon_id: WeaponId) -> None:
    runtime, _, _ = _fire_rocket_into_pair(weapon_id)
    direct = [(idx, dmg, owner) for idx, dmg, _, impulse, owner in _direct_hits(runtime)]
    struck_hits = [d for d in direct if d[0] == 0]
    bounce_hits = [d for d in direct if d[0] == 1]
    assert struck_hits and bounce_hits
    # The bounce hits for exactly its parent's direct-hit damage, and stays
    # the player's shot (credit, and the relic's own penalty, downstream).
    assert bounce_hits[0][1] == pytest.approx(struck_hits[0][1])
    assert bounce_hits[0][2].player_index() == 0


def test_rocket_chains_only_once() -> None:
    runtime, _, _ = _fire_rocket_into_pair(WeaponId.ROCKET_LAUNCHER)
    assert len(_direct_hits(runtime)) == 2  # parent's direct hit + one bounce, no further chaining


def test_rocket_hit_and_explosion_pay_the_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    def _struck_total() -> float:
        runtime, _, _ = _fire_rocket_into_pair(WeaponId.ROCKET_LAUNCHER)
        return sum(dmg for idx, dmg, *_ in runtime.calls if idx == 0)

    with_relic = _struck_total()
    plain = _without_relic(monkeypatch, _struck_total)
    assert plain > 0.0
    assert with_relic == pytest.approx(plain * 0.7, rel=1e-3)
