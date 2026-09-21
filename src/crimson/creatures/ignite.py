from __future__ import annotations

"""Flamethrower ignite DoT - an original addition, not in the native game.

Modelled on the poison DoT (Veins of Poison / Poison Bullets): the actual
damage tick rides `creature_apply_damage_with_lethal_followup` exactly like
`_apply_self_damage_tick` does, so kills go through the normal XP / corpse /
SFX pipeline. Two things the flag-based poison DoT doesn't have and this
does: an accumulator (flame hits build `ignite_flammability` toward a
threshold - named to not collide with the unrelated plasma clip-heat system,
weapon_runtime/plasma_heat.py) and an expiry (`ignite_timer`), so a creature
can only be ignited once until the burn wears off.
"""

from typing import TYPE_CHECKING

from grim.geom import Vec2
from grim.rand import CrandLike

from ..math_parity import f32, x87_pc24_mul, x87_pc24_sub
from .damage_types import CreatureDamageType

if TYPE_CHECKING:
    from ..creatures.damage_runtime import CreatureDamageRuntime
    from ..gameplay import GameplayState
    from ..sim.state_types import PlayerState
    from .runtime import CreatureState

# Flammability a full-intensity flame hit adds; scaled by the particle's
# intensity at the call site, so grazing embers count for less than a
# point-blank blast.
IGNITE_FLAMMABILITY_PER_HIT = 12.0
# Flammability needed to ignite (~9 point-blank hits).
IGNITE_FLAMMABILITY_THRESHOLD = 100.0
# Flammability lost per second while not burning, so a brief graze cools off
# instead of eventually igniting a passer-by.
IGNITE_FLAMMABILITY_DECAY_PER_S = 40.0
# Burn length and its per-second fire damage. FIRE-typed, so Pyromaniac (and
# any fire affix) scale it; separate from the flame particle's direct hit.
IGNITE_DURATION_S = 3.0
IGNITE_DPS = 60.0


def flame_ignite_accumulate(creature: CreatureState, flammability_gain: float) -> None:
    """Add flammability to a creature and ignite it once it crosses the threshold.

    A creature already burning ignores further flammability until its burn expires.
    """

    if float(creature.ignite_timer) > 0.0:
        return
    creature.ignite_flammability = float(f32(float(creature.ignite_flammability) + float(flammability_gain)))
    if float(creature.ignite_flammability) >= IGNITE_FLAMMABILITY_THRESHOLD:
        creature.ignite_timer = IGNITE_DURATION_S
        creature.ignite_flammability = 0.0


def ignite_tick(
    creature: CreatureState,
    *,
    creature_index: int,
    dt: float,
    state: GameplayState,
    players: list[PlayerState],
    rng: CrandLike,
    detail_preset: int,
    creature_damage_runtime: CreatureDamageRuntime | None,
) -> bool:
    """Advance a creature's ignite burn one tick. Returns True if it was killed."""

    if dt <= 0.0 or float(state.bonuses.freeze) > 0.0:
        return False

    if float(creature.ignite_timer) <= 0.0:
        if float(creature.ignite_flammability) > 0.0:
            creature.ignite_flammability = max(
                0.0,
                float(
                    x87_pc24_sub(
                        f32(float(creature.ignite_flammability)),
                        x87_pc24_mul(f32(dt), f32(IGNITE_FLAMMABILITY_DECAY_PER_S)),
                    ),
                ),
            )
        return False

    creature.ignite_timer = max(0.0, float(x87_pc24_sub(f32(float(creature.ignite_timer)), f32(dt))))

    from .damage import creature_apply_damage_with_lethal_followup

    return creature_apply_damage_with_lethal_followup(
        creature,
        creature_index=int(creature_index),
        damage_amount=float(x87_pc24_mul(f32(dt), f32(IGNITE_DPS))),
        damage_type=int(CreatureDamageType.FIRE),
        impulse=Vec2(),
        owner=creature.last_hit_owner,
        dt=float(dt),
        players=players,
        rng=rng,
        effects=state.effects,
        detail_preset=int(detail_preset),
        creature_damage_runtime=creature_damage_runtime,
    )
