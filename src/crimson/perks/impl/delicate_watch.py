from __future__ import annotations

"""Not native: Delicate Watch.

+DELICATE_WATCH_BONUS damage while owned (creatures/damage.py). Dropping
below DELICATE_WATCH_BREAK_THRESHOLD health breaks it: perk_counts is zeroed
outright rather than tracking a separate "broken" flag, which piggybacks on
the existing perk-selection rule (perks/selection.py only re-offers a
non-stackable perk once its count drops back to 0) to make it offerable
again for free.
"""

from ..helpers import perk_active
from ..ids import PerkId
from ..runtime.effects_context import PerksUpdateEffectsCtx
from ..runtime.hook_types import PerkHooks

DELICATE_WATCH_BONUS = 0.30
DELICATE_WATCH_BREAK_THRESHOLD = 25.0


def update_delicate_watch_break(ctx: PerksUpdateEffectsCtx) -> None:
    for player in ctx.players:
        if float(player.health) <= 0.0:
            continue
        if not perk_active(player, PerkId.DELICATE_WATCH):
            continue
        if float(player.health) < DELICATE_WATCH_BREAK_THRESHOLD:
            player.perk_counts[int(PerkId.DELICATE_WATCH)] = 0


HOOKS = PerkHooks(
    perk_id=PerkId.DELICATE_WATCH,
    effects_steps=(update_delicate_watch_break,),
)
