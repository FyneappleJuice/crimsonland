from __future__ import annotations

import msgspec

from crimson.creatures.damage import creature_apply_damage
from crimson.creatures.damage_types import CreatureDamageType
from crimson.creatures.runtime import CreatureState
from crimson.creatures.spawn import CreatureFlags
from crimson.owner_ref import OwnerRef
from crimson.perks import PerkId
from crimson.sim.state_types import PlayerState
from grim.geom import Vec2
from tests.support.helpers import ScriptedCrand, assert_float_close


def test_living_fortress_scales_bullet_damage_by_stationary_timers() -> None:
    creature = CreatureState(active=True, hp=100.0, size=50.0)

    player0 = PlayerState(index=0, pos=Vec2())
    player0.perk_counts[int(PerkId.LIVING_FORTRESS)] = 1
    player0.living_fortress_timer = 10.0  # 1.5x

    player1 = PlayerState(index=1, pos=Vec2())
    player1.living_fortress_timer = 20.0  # 2.0x

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[player0, player1],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is False
    assert_float_close(creature.hp, 70.0)


def test_living_fortress_also_scales_from_the_stunt_double_clones_own_timer() -> None:
    # Not native: Stunt Double's clone ticks its own Living Fortress timer
    # (it never moves) and stacks into the same team-wide bonus, even though
    # it's a snapshot, not a real entry in the players list.
    creature = CreatureState(active=True, hp=100.0, size=50.0)

    player0 = PlayerState(index=0, pos=Vec2())
    player0.perk_counts[int(PerkId.LIVING_FORTRESS)] = 1
    player0.living_fortress_timer = 0.0  # the real player isn't contributing
    player0.hollow_form_snapshot = msgspec.structs.replace(player0, living_fortress_timer=10.0)  # 1.5x

    killed = creature_apply_damage(
        creature,
        damage_amount=10.0,
        damage_type=1,
        impulse=Vec2(),
        owner=OwnerRef.from_local_player(0),
        dt=0.016,
        players=[player0],
        rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
    )

    assert killed is False
    assert_float_close(creature.hp, 85.0)


def test_living_fortress_now_scales_melee_and_explosion_too() -> None:
    # Not native: Living Fortress moved off the Bullet/Plasma/Energy-only
    # PRE_STEPS dispatch onto the fully generic step (alongside All Damage),
    # so it now reaches every damage type, including ones with no other
    # multiplier hook at all.
    player = PlayerState(index=0, pos=Vec2())
    player.perk_counts[int(PerkId.LIVING_FORTRESS)] = 1
    player.living_fortress_timer = 10.0  # 1.5x

    for damage_type in (CreatureDamageType.MELEE, CreatureDamageType.EXPLOSION):
        creature = CreatureState(active=True, hp=100.0, max_hp=100.0, size=50.0, flags=CreatureFlags(0))
        creature_apply_damage(
            creature,
            damage_amount=10.0,
            damage_type=int(damage_type),
            impulse=Vec2(),
            owner=OwnerRef.from_local_player(0),
            dt=0.016,
            players=[player],
            rng=ScriptedCrand(0, fallback=ScriptedCrand.Fallback.REPEAT_LAST),
        )
        assert_float_close(creature.hp, 85.0)
