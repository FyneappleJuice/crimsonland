from __future__ import annotations

"""Not native: The Hit List.

Marks exactly one living Apex-tier monster at a time (a single shared
`CreatureState.hit_list_marked` flag - simplest thing that works, see
[[feedback_simplicity-beats-cleverness]]). Killing the marked monster grants
the killer a small permanent damage bonus, capped. A fresh mark is rolled as
soon as none is active and an Apex monster exists to pick from.

The kill-side bonus increment lives in creatures/runtime.py's death handler
(same hook Momentum/Bane of Legends use); this file only rolls the mark.
"""

from ...creatures.rarity import MonsterRarity
from ...rng_caller_static import RngCallerStatic
from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

HIT_LIST_BONUS_PER_KILL = 0.01
HIT_LIST_MAX_BONUS = 0.30


def update_hit_list_mark(ctx: PerksUpdateEffectsCtx) -> None:
    if ctx.creatures is None or not ctx.players:
        return
    if not any(perk_active(player, PerkId.HIT_LIST) for player in ctx.players):
        return

    candidates: list = []
    for creature in ctx.creatures:
        if not creature.active or float(creature.hp) <= 0.0:
            continue
        if creature.hit_list_marked:
            return  # already have a live mark
        if int(creature.rarity) == int(MonsterRarity.APEX):
            candidates.append(creature)

    if candidates:
        roll = ctx.state.rng.rand_tagged(RngCallerStatic.REWRITE_HIT_LIST_MARK_PICK)
        candidates[roll % len(candidates)].hit_list_marked = True


HOOKS = PerkHooks(
    perk_id=PerkId.HIT_LIST,
    effects_steps=(update_hit_list_mark,),
)
