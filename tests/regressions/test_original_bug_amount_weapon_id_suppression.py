from __future__ import annotations

from crimson.bonuses import BonusId
from crimson.bonuses.pool import BonusPool
from crimson.gameplay import GameplayState
from crimson.sim.state_types import PlayerState, WeaponSlot
from crimson.weapons import WeaponId
from grim.geom import Vec2
from grim.rand import Crand


class _SeqRng(Crand):
    def __init__(self, values: list[int]) -> None:
        super().__init__(0)
        self._values = [int(v) for v in values] or [0]
        self._idx = 0

    def _next(self) -> int:
        if self._idx >= len(self._values):
            return int(self._values[-1])
        value = int(self._values[self._idx])
        self._idx += 1
        return value

    def rand(self) -> int:
        return self._next()

    def rand_tagged(self, caller: int) -> int:
        _ = caller
        return self._next()


def test_original_amount_weapon_id_suppression_bug_is_fixed_by_default() -> None:
    # Native bug: after spawning a non-points bonus, clear it if `amount == weapon_id`.
    # Example collision: Speed uses `amount=8`, which collides with Flamethrower `weapon_id=8`.
    state = GameplayState(rng=_SeqRng([1, 114]))
    state.bonus_pool = BonusPool()

    player = PlayerState(index=0, pos=Vec2(256.0, 256.0), weapon=WeaponSlot(weapon_id=WeaponId.FLAMETHROWER))
    entry = state.bonus_pool.try_spawn_on_kill(pos=Vec2(256.0, 256.0), state=state, players=[player])
    assert entry is not None
    assert entry.bonus_id == BonusId.SPEED
