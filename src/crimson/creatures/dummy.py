from __future__ import annotations

"""Sandbox test entities (not native, rewrite-only). See modes/maps_mode.py.

Two entity kinds for the Maps sandbox mode:
  - a "damage dummy": spawned with huge health so it never realistically
    dies, tracking damage/dps/last-hit stats for the floating text drawn by
    render/world/dummy_stats.py.
  - a "stationary test monster": 1 HP, dies through the completely normal
    damage/death path - the point is to trigger on-death procs (Domino
    Effect, Frag Death, ...) on demand with a single hit.

Both are ordinary CreatureState entries - any active, hp>0 creature is
already a legal target for every nearest-enemy scan in this codebase (see
_fire_momentum_shot in creatures/runtime.py, hollow_form.py's
_nearest_living_creature_pos - both only check `active`/`hp > 0`) - so
neither needs any special tagging beyond existing as a real pool entry.
`move_speed` is forced to 0 directly on the materialized CreatureState right
after spawning (not via CreatureInit.move_speed, which the alloc path treats
as "falsy -> default 1.0" - see CreaturePool._apply_init) so both hold still
until dragged.
"""

from typing import TYPE_CHECKING

import msgspec
from grim.geom import Vec2

from . import rarity as _rarity
from .spawn import CreatureInit
from .spawn_ids import CreatureTypeId

if TYPE_CHECKING:
    # Deferred: creatures/runtime.py imports sandbox_keep_corpse from this
    # module, so a module-level import back the other way would cycle.
    from .runtime import CreaturePool

DUMMY_HEALTH = 1_000_000_000.0
DUMMY_DAMAGE_RESET_S = 5.0
STATIONARY_MONSTER_HEALTH = 1.0
# Not native: the stationary test monster auto-respawns this many seconds
# after it dies to a hit, so it's ready for another on-death-proc test
# without needing to place a fresh one every time (see
# queue_stationary_monster_respawn / tick_test_monster_respawns below). A
# deliberate RMB delete (modes/maps_mode.py) is a separate path and never
# queues this - only an actual combat death does.
STATIONARY_MONSTER_RESPAWN_DELAY_S = 5.0


class PendingTestMonsterRespawn(msgspec.Struct):
    pos: Vec2
    timer: float
    # Not native: carries the rarity tier/affixes the monster had when it
    # died, so an auto-respawn reproduces the same test setup instead of
    # losing it - the sandbox debug panel's own current selection may have
    # moved on to preparing something else by the time this fires.
    tier: int = 0
    affixes: tuple[int, ...] = ()


def _spawn_single(
    pool: CreaturePool,
    pos: Vec2,
    *,
    health: float,
    is_test_dummy: bool,
    tier: int = 0,
    forced_affixes: tuple[int, ...] = (),
) -> int | None:
    init = CreatureInit(
        origin_template_id=0,
        pos=pos,
        heading=0.0,
        phase_seed=0,
        type_id=CreatureTypeId.ZOMBIE,
        health=health,
        max_health=health,
        is_test_dummy=is_test_dummy,
        # Not native: no corpse/death animation for either sandbox entity - if
        # the stationary 1hp monster dies (the whole point), it should just
        # vanish cleanly, not linger as a fading corpse.
        sandbox_no_corpse=True,
    )
    # Not native: sandbox debug panel's Monster Mods tab (see
    # ui/sandbox_debug_panel.py) - a picked tier > 0 applies the exact same
    # rarity system real monsters get (HP/size/reward scaling + the chosen
    # affixes), just with an explicit affix list instead of a random roll.
    # Picking Normal (tier 0, the default) leaves the dummy/monster exactly
    # as before this feature existed.
    if int(tier) > 0:
        _rarity.apply_rarity(init, tier=int(tier), player_experience=0, forced_affixes=tuple(forced_affixes))
    idx = pool.spawn_init(init)
    if idx is None:
        return None
    # Force-still: see the module docstring for why this can't go through
    # CreatureInit.move_speed.
    pool.entries[idx].move_speed = 0.0
    return idx


def spawn_test_dummy(
    pool: CreaturePool, pos: Vec2, *, tier: int = 0, forced_affixes: tuple[int, ...] = (),
) -> int | None:
    return _spawn_single(pool, pos, health=DUMMY_HEALTH, is_test_dummy=True, tier=tier, forced_affixes=forced_affixes)


def spawn_stationary_test_monster(
    pool: CreaturePool, pos: Vec2, *, tier: int = 0, forced_affixes: tuple[int, ...] = (),
) -> int | None:
    return _spawn_single(
        pool, pos, health=STATIONARY_MONSTER_HEALTH, is_test_dummy=False, tier=tier, forced_affixes=forced_affixes,
    )


def dummy_on_hit(creature, damage: float) -> None:
    """Called from creatures/damage.py's creature_apply_damage once the final
    resolved damage is known. Only records event deltas - all elapsed-time
    bookkeeping happens in update_test_dummies, since this call site has no
    clean "current elapsed seconds" reference of its own to hand in."""
    damage = float(damage)
    if damage <= 0.0:
        return
    if creature.dummy_damage_total <= 0.0:
        # First hit of a fresh streak (either the very first ever, or the
        # first after a 5s-silence reset already zeroed the total).
        creature.dummy_streak_elapsed_s = 0.0
    creature.dummy_no_hit_timer = 0.0
    creature.dummy_damage_total = float(creature.dummy_damage_total) + damage
    creature.dummy_last_hit_amount = damage
    creature.dummy_last_hit_elapsed_s = float(creature.dummy_streak_elapsed_s)


def update_test_dummies(creatures, dt: float) -> None:
    """Advance dummy timers. Called once per tick, same family as
    creatures/rarity.py's update_monster_affixes."""
    dt = float(dt)
    if dt <= 0.0:
        return
    entries = list(creatures.entries) if hasattr(creatures, "entries") else list(creatures)
    for c in entries:
        if not c.active or not c.is_test_dummy:
            continue
        c.dummy_no_hit_timer = float(c.dummy_no_hit_timer) + dt
        if c.dummy_no_hit_timer >= DUMMY_DAMAGE_RESET_S:
            if c.dummy_damage_total > 0.0:
                c.dummy_damage_total = 0.0
                c.dummy_last_hit_amount = 0.0
        else:
            c.dummy_streak_elapsed_s = float(c.dummy_streak_elapsed_s) + dt


def sandbox_keep_corpse(entries, idx: int, state) -> bool:
    """Shared by every on_creature_lethal implementation (creatures/runtime.py,
    sim/world_state.py): returns whether creature `idx` should keep its normal
    corpse-fade death. False for both sandbox test entities; for the
    stationary test monster specifically (not the damage dummy, which never
    realistically dies anyway) this also queues its 5s auto-respawn."""
    idx = int(idx)
    if not (0 <= idx < len(entries)):
        return True
    creature = entries[idx]
    if not creature.sandbox_no_corpse:
        return True
    if not creature.is_test_dummy:
        queue_stationary_monster_respawn(
            state, creature.pos, tier=int(creature.rarity), affixes=tuple(creature.affixes),
        )
    return False


def queue_stationary_monster_respawn(
    state, pos: Vec2, *, tier: int = 0, affixes: tuple[int, ...] = (),
) -> None:
    """Called from the on_creature_lethal call sites (creatures/runtime.py,
    sim/world_state.py) right before a stationary test monster's death goes
    through, if it's actually dying to a hit (not an RMB delete)."""
    pending = getattr(state, "pending_test_monster_respawns", None)
    if pending is None:
        return
    pending.append(
        PendingTestMonsterRespawn(
            pos=Vec2(float(pos.x), float(pos.y)), timer=STATIONARY_MONSTER_RESPAWN_DELAY_S,
            tier=int(tier), affixes=tuple(affixes),
        ),
    )


def tick_test_monster_respawns(pool: CreaturePool, state, dt: float) -> None:
    """Advance pending respawns. Called once per tick alongside
    update_test_dummies (see sim/world_state.py)."""
    dt = float(dt)
    if dt <= 0.0:
        return
    pending = getattr(state, "pending_test_monster_respawns", None)
    if not pending:
        return
    remaining: list[PendingTestMonsterRespawn] = []
    for respawn in pending:
        respawn.timer = float(respawn.timer) - dt
        if respawn.timer > 0.0:
            remaining.append(respawn)
        else:
            spawn_stationary_test_monster(pool, respawn.pos, tier=respawn.tier, forced_affixes=respawn.affixes)
    state.pending_test_monster_respawns = remaining


def dummy_dps(creature) -> float:
    """DPS over the current unbroken hit streak: total damage divided by the
    time between the streak's first hit and its most recent hit. Reads as the
    single most-recent hit's damage until a second hit actually lands (no
    elapsed span yet to divide by)."""
    span = float(creature.dummy_last_hit_elapsed_s)
    if span <= 0.0:
        return float(creature.dummy_last_hit_amount)
    return float(creature.dummy_damage_total) / span


__all__ = [
    "DUMMY_DAMAGE_RESET_S",
    "DUMMY_HEALTH",
    "STATIONARY_MONSTER_HEALTH",
    "STATIONARY_MONSTER_RESPAWN_DELAY_S",
    "PendingTestMonsterRespawn",
    "dummy_dps",
    "dummy_on_hit",
    "queue_stationary_monster_respawn",
    "sandbox_keep_corpse",
    "spawn_stationary_test_monster",
    "spawn_test_dummy",
    "tick_test_monster_respawns",
    "update_test_dummies",
]
