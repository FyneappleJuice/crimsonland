from __future__ import annotations

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureFlags
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand, assert_float_close


def test_uranium_filled_bullets_boosts_bullet_damage_by_half() -> None:
    creature = CreatureState(active=True, hp=100.0, size=50.0)
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[player],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is False
    assert_float_close(creature.hp, 85.0)


def test_uranium_filled_bullets_plus_doubles_bullet_plasma_and_energy() -> None:
    # Reworked onto the shared "projectile" bucket (damage_mult_projectile) -
    # Plasma/Energy ride the same bucket as Bullet, unconditionally (Ion has
    # its own test below since it's flag-gated, like Fire/Explosion).
    for damage_type in (
        CreatureDamageType.BULLET,
        CreatureDamageType.PLASMA,
        CreatureDamageType.ENERGY,
    ):
        creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, size=50.0, flags=CreatureFlags(0))
        player = PlayerState(index=0, pos=Vec2())
        player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1
        player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS_PLUS)] = 1

        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
        )

        assert_float_close(creature.hp, 800.0)


def test_uranium_filled_bullets_boosts_fire_explosion_and_ion_only_on_the_direct_hit() -> None:
    # Fire, Explosion, and Ion each cover two events sharing one damage_type -
    # the projectile bucket only reaches the direct-hit half (is_projectile_hit),
    # never the DoT/AoE half (ignite tick, blast-radius tick, ion cloud tick).
    for damage_type in (CreatureDamageType.FIRE, CreatureDamageType.EXPLOSION, CreatureDamageType.ION):
        direct_hit = CreatureState(active=True, hp=1000.0, max_hp=1000.0, size=50.0, flags=CreatureFlags(0))
        dot_tick = CreatureState(active=True, hp=1000.0, max_hp=1000.0, size=50.0, flags=CreatureFlags(0))
        player = PlayerState(index=0, pos=Vec2())
        player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1

        creature_apply_damage(
            direct_hit,
            damage_amount=100.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
            is_projectile_hit=True,
        )
        creature_apply_damage(
            dot_tick,
            damage_amount=100.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
            is_projectile_hit=False,
        )

        assert_float_close(direct_hit.hp, 850.0)
        assert_float_close(dot_tick.hp, 900.0)


def test_uranium_filled_bullets_never_boosts_melee_or_self_tick() -> None:
    # No projectile hook exists for these at all, regardless of the flag.
    for damage_type in (CreatureDamageType.MELEE, CreatureDamageType.SELF_TICK):
        creature = CreatureState(active=True, hp=1000.0, max_hp=1000.0, size=50.0, flags=CreatureFlags(0))
        player = PlayerState(index=0, pos=Vec2())
        player.perk_counts[int(PerkId.URANIUM_FILLED_BULLETS)] = 1

        creature_apply_damage(
            creature,
            damage_amount=100.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
            is_projectile_hit=True,
        )

        assert_float_close(creature.hp, 900.0)
