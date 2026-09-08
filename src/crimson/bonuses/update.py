from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from grim.geom import Vec2

from ..creatures.damage_runtime import CreatureDamageRuntime
from ..math_parity import f32, x87_pc24_sub
from ..perks.helpers import perk_active
from ..sim.state_types import BonusPickupEvent, GameplayState, PlayerState
from ..test_mode import test_mode_enabled
from ..weapons import WeaponId
from .apply import bonus_apply
from .hud import bonus_hud_update
from .ids import BonusId
from .pool import BONUS_PICKUP_LINGER, BONUS_SPAWN_MARGIN, BONUS_SPAWN_MIN_DISTANCE, BONUS_TELEKINETIC_PICKUP_MS, bonus_find_aim_hover_entry

if TYPE_CHECKING:
    from ..creatures.runtime import CreatureState

_TEST_MODE_BONUS_SPAWN_INTERVAL = 5.0
# Rewrite-only bonuses under active test, spawned round-robin so each can be
# tried in turn. Empty = no auto-spawned bonuses. Add / remove ids here to
# change what --test-mode auto-spawns.
_TEST_MODE_BONUS_CYCLE: tuple[BonusId, ...] = ()
# Weapons dropped once near spawn on a fresh test run. Empty = none.
_TEST_MODE_WEAPON_DROPS: tuple[tuple[float, WeaponId], ...] = ()


def update_test_mode_fork_spawner(
    state: GameplayState,
    dt: float,
    *,
    world_width: float = 1024.0,
    world_height: float = 1024.0,
) -> None:
    """Test mode only: force-spawn one rewrite-only bonus every few seconds,
    cycling through them (`_TEST_MODE_BONUS_CYCLE`).

    Not native. Spawns at world center by default; if the center is already
    occupied by an active, unpicked bonus, falls back to a random spot instead.
    """

    if not test_mode_enabled() or dt <= 0.0:
        return

    # One-time: drop a couple of test weapons near the world-centre start spot
    # so a fresh run has something better than the pistol to try things with.
    if not state.test_mode_shotgun_dropped:
        state.test_mode_shotgun_dropped = True
        cx, cy = world_width * 0.5, world_height * 0.5
        for offset, weapon_id in _TEST_MODE_WEAPON_DROPS:
            drop = state.bonus_pool.spawn_forced_at_pos(Vec2(cx, cy - offset), bonus_id=BonusId.WEAPON)
            drop.amount = int(weapon_id)

    if not _TEST_MODE_BONUS_CYCLE:
        return

    state.test_mode_fork_spawn_timer -= float(dt)
    if state.test_mode_fork_spawn_timer > 0.0:
        return
    state.test_mode_fork_spawn_timer += _TEST_MODE_BONUS_SPAWN_INTERVAL

    bonus_id = _TEST_MODE_BONUS_CYCLE[state.test_mode_bonus_cycle % len(_TEST_MODE_BONUS_CYCLE)]
    state.test_mode_bonus_cycle += 1

    center = Vec2(world_width * 0.5, world_height * 0.5)

    def _occupied(pos: Vec2) -> bool:
        for entry in state.bonus_pool.entries:
            if entry.bonus_id == BonusId.UNUSED or entry.picked:
                continue
            if pos.distance_to(entry.pos) < BONUS_SPAWN_MIN_DISTANCE:
                return True
        return False

    spawn_pos = center
    if _occupied(spawn_pos):
        margin = BONUS_SPAWN_MARGIN
        rng = state.rng
        spawn_pos = Vec2(
            float(rng.rand() % max(1, int(world_width - 2.0 * margin))) + margin,
            float(rng.rand() % max(1, int(world_height - 2.0 * margin))) + margin,
        )

    state.bonus_pool.spawn_forced_at_pos(spawn_pos, bonus_id=bonus_id)


def bonus_telekinetic_update(
    state: GameplayState,
    players: list[PlayerState],
    dt: float,
    *,
    creatures: Sequence[CreatureState],
    detail_preset: int = 5,
    defer_freeze_corpse_fx: bool = False,
    freeze_corpse_indices: set[int] | None = None,
    creature_damage_runtime: CreatureDamageRuntime | None = None,
) -> list[BonusPickupEvent]:
    """Allow Telekinetic perk owners to pick up bonuses by aiming at them."""
    from ..perks import PerkId

    if dt <= 0.0:
        return []

    pickups: list[BonusPickupEvent] = []
    dt_ms = float(dt) * 1000.0

    for player in players:
        if player.health <= 0.0:
            continue

        hovered = bonus_find_aim_hover_entry(player, state.bonus_pool)
        if hovered is None:
            player.bonus_aim_hover_index = -1
            player.bonus_aim_hover_timer_ms = 0.0
            continue

        idx, entry = hovered
        player.bonus_aim_hover_index = int(idx)
        player.bonus_aim_hover_timer_ms += dt_ms

        if player.bonus_aim_hover_timer_ms <= BONUS_TELEKINETIC_PICKUP_MS:
            continue
        # Native calls the singleton perk_count_get here, so player zero owns
        # the perk gate even though the iterated player receives the pickup.
        perk_player = players[0] if state.preserve_bugs and players else player
        if not perk_active(perk_player, PerkId.TELEKINETIC):
            continue
        if entry.picked or entry.bonus_id == BonusId.UNUSED:
            continue

        bonus_apply(
            state,
            player,
            entry.bonus_id,
            amount=int(entry.amount),
            origin=entry.pos,
            creatures=creatures,
            players=players,
            detail_preset=int(detail_preset),
            defer_freeze_corpse_fx=bool(defer_freeze_corpse_fx),
            freeze_corpse_indices=freeze_corpse_indices,
            creature_damage_runtime=creature_damage_runtime,
        )
        entry.picked = True
        entry.time_left = BONUS_PICKUP_LINGER
        pickups.append(
            BonusPickupEvent(
                player_index=int(player.index),
                bonus_id=entry.bonus_id,
                amount=int(entry.amount),
                pos=entry.pos,
            ),
        )

        # Match the exe: after a telekinetic pickup, reset the hover accumulator.
        player.bonus_aim_hover_index = -1
        player.bonus_aim_hover_timer_ms = 0.0
        break

    return pickups


def bonus_update(
    state: GameplayState,
    players: list[PlayerState],
    dt: float,
    *,
    creatures: Sequence[CreatureState],
    update_hud: bool = True,
    detail_preset: int = 5,
    defer_freeze_corpse_fx: bool = False,
    freeze_corpse_indices: set[int] | None = None,
    creature_damage_runtime: CreatureDamageRuntime | None = None,
    world_width: float = 1024.0,
    world_height: float = 1024.0,
) -> list[BonusPickupEvent]:
    """Advance world bonuses and global timers (subset of `bonus_update`)."""

    update_test_mode_fork_spawner(state, dt, world_width=world_width, world_height=world_height)

    pickups = bonus_telekinetic_update(
        state,
        players,
        dt,
        creatures=creatures,
        detail_preset=int(detail_preset),
        defer_freeze_corpse_fx=bool(defer_freeze_corpse_fx),
        freeze_corpse_indices=freeze_corpse_indices,
        creature_damage_runtime=creature_damage_runtime,
    )
    pickups.extend(
        state.bonus_pool.update(
            dt,
            state=state,
            players=players,
            creatures=creatures,
            detail_preset=int(detail_preset),
            defer_freeze_corpse_fx=bool(defer_freeze_corpse_fx),
            freeze_corpse_indices=freeze_corpse_indices,
            creature_damage_runtime=creature_damage_runtime,
        ),
    )

    if dt > 0.0:
        # Native `bonus_update` decrements Freeze + Double XP here; other global
        # timers are advanced earlier in the gameplay loop.
        double_xp = float(state.bonuses.double_experience)
        if double_xp <= 0.0:
            state.bonuses.double_experience = 0.0
        else:
            state.bonuses.double_experience = float(f32(float(double_xp) - float(dt)))

        freeze = float(state.bonuses.freeze)
        if freeze <= 0.0:
            state.bonuses.freeze = 0.0
        else:
            state.bonuses.freeze = float(f32(float(freeze) - float(dt)))

    if update_hud:
        bonus_hud_update(state, players, dt=dt)

    return pickups


def bonus_update_pre_pickup_timers(state: GameplayState, dt: float) -> None:
    """Advance global timers that native decrements before `bonus_update`."""

    if dt <= 0.0:
        return
    if float(state.bonuses.weapon_power_up) > 0.0:
        state.bonuses.weapon_power_up = float(f32(float(state.bonuses.weapon_power_up) - float(dt)))
    if float(state.bonuses.energizer) > 0.0:
        state.bonuses.energizer = float(f32(float(state.bonuses.energizer) - float(dt)))
    if float(state.bonuses.reflex_boost) > 0.0:
        state.bonuses.reflex_boost = float(
            x87_pc24_sub(
                state.bonuses.reflex_boost,
                dt,
            ),
        )
