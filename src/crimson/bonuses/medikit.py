from __future__ import annotations

from ..math_parity import f32
from ..perks.helpers import perk_active
from ..perks.ids import PerkId
from ..perks.impl.soul_tether import soul_tether_clamp_and_gain
from .apply_context import BonusApplyCtx


def apply_medikit(ctx: BonusApplyCtx) -> None:
    # Rewrite-only: Soul Tether wants the overheal even at full health, so it
    # can redirect it into shield instead of the pickup doing nothing.
    if float(ctx.player.health) >= 100.0 and not perk_active(ctx.player, PerkId.SOUL_TETHER):
        return
    ctx.player.health = soul_tether_clamp_and_gain(ctx.player, float(f32(float(ctx.player.health) + 10.0)))
