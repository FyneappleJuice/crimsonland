from __future__ import annotations

"""Destructible Barrel prop (not native, rewrite-only).

A Barrel is a plain `CreatureState` entry - real HP, real collision/damage,
`move_speed` forced to 0 (same trick `creatures/dummy.py` uses for the
sandbox entities) so it never chases or attacks - flagged `is_barrel` so:
  - rendering swaps in the Barrel sprite instead of its borrowed type_id's
    native one (render/world/draw.py's `_draw_barrels`/`_draw_barrel_breaks`),
  - it never keeps a fading corpse on death (`barrel_keep_corpse`, wired the
    same way `dummy.sandbox_keep_corpse` is, at every `on_creature_lethal`),
  - death runs a loot roll (`on_barrel_broken`) instead of the ordinary
    kill-XP/bonus-chance path.

The loot roll is intentionally unconditional (no Bonus Magnet gate, no "1 in
9" base chance) - `BonusPool.try_spawn_on_kill` is tuned for "on every kill,
small chance of a bonus"; a Barrel is a payoff you had to specifically walk
up and break, so it should reliably pay off:
  - ~90%: an ordinary bonus roll at the break point (`BonusPool.spawn_at_pos`
    already weighs weapon vs. every other powerup - no separate "weapon or
    powerup" branch needed here).
  - ~8%: a monster spawns instead, as if the barrel was hiding one.
  - ~2%: a free instant perk (and paired run-mod) choice - the exact same
    `pending_count`/`choices_dirty` bump the Survival mode F3 debug cheat
    uses (see modes/survival_mode.py), so it opens through the completely
    normal level-up UI flow.
"""

import random as _random
from typing import TYPE_CHECKING

import msgspec

from grim.geom import Vec2

from .spawn import CreatureInit
from .spawn_ids import CreatureTypeId

if TYPE_CHECKING:
    from ..gameplay import GameplayState
    from ..sim.state_types import PlayerState
    from .runtime import CreaturePool, CreatureState

BARREL_HEALTH_BASE = 30.0
BARREL_HEALTH_GROWTH_PER_LEVEL = 0.02  # +2% Barrel HP per level, compounding
BARREL_SIZE = 56.0

BARREL_BASE_INTERVAL_S = 18.0
BARREL_MIN_INTERVAL_S = 6.0
BARREL_INTERVAL_DECAY_PER_LEVEL_S = 0.25
# Barrels are a reward to go find, not a threat to avoid - much closer to a
# player than a Den is ever allowed to land.
BARREL_POSITION_MARGIN = 64.0
BARREL_MIN_PLAYER_DISTANCE = 120.0
BARREL_MAX_ACTIVE = 4
_BARREL_POSITION_ATTEMPTS = 16

BARREL_MONSTER_CHANCE = 0.08
BARREL_FREE_PERK_CHANCE = 0.02

# Private RNGs (position/loot roll/monster pick) - rewrite-only content, kept
# off the shared lockstep stream the same way creatures/spawn.py's own Den
# RNGs are (see the private-RNG migration noted in math_parity.py).
_BARREL_POSITION_RNG = _random.Random(0xBA44E10C)
_BARREL_LOOT_RNG = _random.Random(0xBA44E107)
_BARREL_MONSTER_RNG = _random.Random(0xBA44E10E)

_BARREL_MONSTER_TYPES: tuple[CreatureTypeId, ...] = (
    CreatureTypeId.ZOMBIE,
    CreatureTypeId.ALIEN,
    CreatureTypeId.LIZARD,
    CreatureTypeId.SPIDER_SP1,
)


class BarrelBreakEffect(msgspec.Struct):
    pos: Vec2
    elapsed: float = 0.0


def barrel_health(player_level: int) -> float:
    level = max(0, int(player_level))
    return BARREL_HEALTH_BASE * ((1.0 + BARREL_HEALTH_GROWTH_PER_LEVEL) ** level)


def barrel_interval_s(player_level: int) -> float:
    level = max(0, int(player_level))
    return max(
        BARREL_MIN_INTERVAL_S,
        BARREL_BASE_INTERVAL_S - level * BARREL_INTERVAL_DECAY_PER_LEVEL_S,
    )


def barrel_pick_position(*, world_size: float = 1024.0, avoid: tuple[Vec2, ...] = ()) -> Vec2:
    """Random arena position for a fresh Barrel, at least
    BARREL_MIN_PLAYER_DISTANCE from every `avoid` point (falls back to the
    farthest candidate tried if the arena is too crowded for that)."""
    lo = BARREL_POSITION_MARGIN
    hi = max(lo, float(world_size) - BARREL_POSITION_MARGIN)
    best = Vec2(lo, lo)
    best_dist = -1.0
    for _ in range(_BARREL_POSITION_ATTEMPTS):
        pos = Vec2(_BARREL_POSITION_RNG.uniform(lo, hi), _BARREL_POSITION_RNG.uniform(lo, hi))
        nearest = min((pos.distance_to(p) for p in avoid), default=float("inf"))
        if nearest >= BARREL_MIN_PLAYER_DISTANCE:
            return pos
        if nearest > best_dist:
            best_dist = nearest
            best = pos
    return best


def count_active_barrels(pool: CreaturePool) -> int:
    return sum(1 for c in pool.entries if c.active and c.is_barrel)


def spawn_barrel(pool: CreaturePool, pos: Vec2, *, player_level: int = 0) -> int | None:
    if count_active_barrels(pool) >= BARREL_MAX_ACTIVE:
        return None
    health = barrel_health(player_level)
    init = CreatureInit(
        origin_template_id=0,
        pos=pos,
        heading=0.0,
        phase_seed=0,
        # Borrowed purely for damage/collision bookkeeping - never rendered as
        # a Zombie (see render/world/draw.py's iter_native_creature_sprite_pass
        # / iter_active_creature_overlay_pass, both skip is_barrel entries).
        type_id=CreatureTypeId.ZOMBIE,
        health=health,
        max_health=health,
        move_speed=0.0,
        contact_damage=0.0,
        reward_value=0.0,
        size=BARREL_SIZE,
        is_barrel=True,
    )
    idx = pool.spawn_init(init)
    if idx is None:
        return None
    # Not native: no CreatureInit.move_speed=0 shortcut exists (the alloc path
    # treats a falsy move_speed as "default to 1.0" - see CreaturePool._apply_init,
    # same reasoning dummy.py's own module docstring documents), so force it
    # directly on the materialized entry.
    pool.entries[idx].move_speed = 0.0
    return idx


def barrel_keep_corpse(entries: list[CreatureState], idx: int) -> bool:
    """Shared by every on_creature_lethal implementation, alongside
    dummy.sandbox_keep_corpse - a Barrel never keeps its (borrowed, native)
    corpse-fade sprite; on_barrel_broken queues its own break VFX instead."""
    idx = int(idx)
    if not (0 <= idx < len(entries)):
        return True
    return not entries[idx].is_barrel


def _grant_free_perk_choice(state: GameplayState) -> None:
    # Not native: the same pending_count/choices_dirty bump the Survival mode
    # F3 debug cheat uses (modes/survival_mode.py) - a real level-up bumps
    # both counters together too (gameplay.py's survival_check_level_up), so
    # this reuses the exact same, already-proven trigger instead of a new one.
    state.perk_selection.pending_count += 1
    state.perk_selection.choices_dirty = True
    state.run_mod_selection.pending_count += 1
    state.run_mod_selection.choices_dirty = True


def _spawn_loot_monster(pool: CreaturePool, pos: Vec2, *, player_level: int) -> None:
    type_id = _BARREL_MONSTER_RNG.choice(_BARREL_MONSTER_TYPES)
    level = max(0, int(player_level))
    health = 40.0 + level * 4.0
    init = CreatureInit(
        origin_template_id=0,
        pos=pos,
        heading=_BARREL_MONSTER_RNG.uniform(0.0, 6.28318),
        phase_seed=0,
        type_id=type_id,
        health=health,
        max_health=health,
        move_speed=1.6,
        reward_value=health,
        size=48.0,
    )
    pool.spawn_init(init)


def on_barrel_broken(
    pool: CreaturePool,
    creature: CreatureState,
    *,
    state: GameplayState,
    players: list[PlayerState],
    detail_preset: int = 5,
    world_width: float = 1024.0,
    world_height: float = 1024.0,
) -> None:
    pending = getattr(state, "pending_barrel_breaks", None)
    if pending is not None:
        pending.append(BarrelBreakEffect(pos=creature.pos))

    player_level = players[0].level if players else 0
    roll = _BARREL_LOOT_RNG.random()
    if roll < BARREL_FREE_PERK_CHANCE:
        _grant_free_perk_choice(state)
        return
    if roll < BARREL_FREE_PERK_CHANCE + BARREL_MONSTER_CHANCE:
        _spawn_loot_monster(pool, creature.pos, player_level=int(player_level))
        return
    state.bonus_pool.spawn_at_pos(
        creature.pos,
        state=state,
        players=players,
        world_width=world_width,
        world_height=world_height,
    )


def tick_barrel_break_effects(state: GameplayState, dt: float) -> None:
    dt = float(dt)
    if dt <= 0.0:
        return
    pending = getattr(state, "pending_barrel_breaks", None)
    if not pending:
        return
    remaining: list[BarrelBreakEffect] = []
    for effect in pending:
        effect.elapsed = float(effect.elapsed) + dt
        if effect.elapsed < 0.4:
            remaining.append(effect)
    state.pending_barrel_breaks = remaining


__all__ = [
    "BARREL_FREE_PERK_CHANCE",
    "BARREL_HEALTH_BASE",
    "BARREL_MAX_ACTIVE",
    "BARREL_MIN_PLAYER_DISTANCE",
    "BARREL_MONSTER_CHANCE",
    "BarrelBreakEffect",
    "barrel_health",
    "barrel_interval_s",
    "barrel_keep_corpse",
    "barrel_pick_position",
    "count_active_barrels",
    "on_barrel_broken",
    "spawn_barrel",
    "tick_barrel_break_effects",
]
