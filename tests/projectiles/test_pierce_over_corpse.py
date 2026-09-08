from __future__ import annotations

import math

from crimson.creatures.damage_runtime import DirectCreatureDamageRuntime
from crimson.owner_ref import OwnerRef
from crimson.projectiles.runtime import PrimaryStepCtx, ProjectilePool
from crimson.projectiles.types import ProjectileTemplateId
from grim.geom import Vec2
from tests.support.factories import make_creature_state as _creature
from tests.support.factories import make_projectile_update_options


class _KillingRuntime(DirectCreatureDamageRuntime):
    def apply_creature_damage(self, ci: int, dmg: float, dtype: int, impulse: Vec2, owner: OwnerRef) -> None:  # noqa: ANN001
        c = self.creatures[int(ci)]
        c.hp -= float(dmg)
        if c.hp <= 0.0:
            c.active = False


def test_piercing_projectile_over_a_fresh_corpse_does_not_crash() -> None:
    # Regression: the WPU-pierce `did_pierce` flag was only bound inside the
    # `damage_amount > 0 and creature.hp > 0` branch, so a piercing round
    # (Fire Bullets / Gauss) re-touching a creature it just killed raised
    # UnboundLocalError.
    c0 = _creature(pos=Vec2(20.0, 0.0), hp=1.0, size=40.0)
    c1 = _creature(pos=Vec2(26.0, 0.0), hp=1.0, size=40.0)
    pool = ProjectilePool(size=1)
    pool.spawn(
        pos=Vec2(),
        angle=math.pi / 2.0,
        type_id=ProjectileTemplateId.FIRE_BULLETS,
        owner=OwnerRef.from_local_player(0),
        travel_budget=60.0,
    )
    hits = pool.step(
        PrimaryStepCtx(
            dt=0.1,
            creatures=[c0, c1],
            options=make_projectile_update_options(
                world_size=1024.0,
                creature_damage_runtime=_KillingRuntime(creatures=[c0, c1]),
            ),
        ),
    )
    assert hits is not None  # got here without raising
    assert c0.hp <= 0.0
