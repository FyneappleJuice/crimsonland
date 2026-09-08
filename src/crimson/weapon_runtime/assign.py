from __future__ import annotations

from collections.abc import Callable, Sequence

import msgspec

from ..math_parity import f32, x87_pc24_mul
from ..perks import PerkId
from ..perks.helpers import perk_active
from ..progression import refresh_player_stats
from ..sim.state_types import GameplayState, PlayerState, WeaponSlot
from ..weapon_usage import weapon_usage_slot_for_weapon_id
from ..weapons import WEAPON_BY_ID, Weapon, WeaponId
from .power_up import wpu_boosts_fire_rate


def weapon_entry(weapon_id: WeaponId) -> Weapon:
    return WEAPON_BY_ID[weapon_id]


class _WeaponAssignCtx(msgspec.Struct):
    player: PlayerState
    clip_size: int


_WeaponAssignClipModifier = Callable[[_WeaponAssignCtx], None]


def _weapon_assign_clip_stats(ctx: _WeaponAssignCtx) -> None:
    """Clip-size perks, via crimson.progression stats.

    Ammo Maniac feeds `clip_size_mult` (+25%); with only that perk the term is
    exactly 0.25, so `+= max(1, floor(clip * 0.25))` is unchanged. My Favourite
    Weapon feeds `clip_size_add` (+2). Percent applies before the flat add,
    matching the original modifier order.
    """

    stats = ctx.player.stats
    inc = float(stats.clip_size_mult) - 1.0
    if inc != 0.0:
        ctx.clip_size += max(1, int(float(ctx.clip_size) * inc))
    add = int(stats.clip_size_add)
    if add != 0:
        ctx.clip_size += add


_WEAPON_ASSIGN_CLIP_MODIFIERS: tuple[_WeaponAssignClipModifier, ...] = (_weapon_assign_clip_stats,)


def init_default_alt_weapon(player: PlayerState) -> None:
    """Initialize native reset-time alternate weapon slot state."""

    player.alt_weapon = WeaponSlot(
        weapon_id=WeaponId.PISTOL,
        clip_size=12,
        ammo=12.0,
        reload_active=False,
        reload_timer=0.0,
        reload_timer_max=1.2,
        shot_cooldown=0.0,
    )


def weapon_assign_player(player: PlayerState, weapon_id: WeaponId, *, state: GameplayState) -> None:
    """Assign weapon and reset per-weapon runtime state (ammo/cooldowns)."""

    weapon_id = WeaponId(weapon_id)
    refresh_player_stats([player])
    if state.status is not None and not state.demo_mode_active:
        usage_slot = weapon_usage_slot_for_weapon_id(int(weapon_id))
        if usage_slot is not None:
            state.status.increment_weapon_usage_slot(usage_slot)

    weapon = weapon_entry(weapon_id)
    player.weapon.weapon_id = weapon_id

    clip_size = int(weapon.clip_size)
    clip_ctx = _WeaponAssignCtx(player=player, clip_size=max(0, clip_size))
    for modifier in _WEAPON_ASSIGN_CLIP_MODIFIERS:
        modifier(clip_ctx)
    player.weapon.clip_size = max(0, int(clip_ctx.clip_size))
    player.weapon.ammo = float(player.weapon.clip_size)
    player.weapon_reset_latch = 0
    # Native resets only ammo, the reset latch, shot cooldown, reload timer,
    # and aux timer; reload_active and reload_timer_max keep their previous
    # values across a weapon pickup mid-reload.
    player.weapon.reload_timer = 0.0
    player.weapon.shot_cooldown = 0.0
    player.aux_timer = 2.0

    if state is not None:
        state.sfx_queue.append(weapon.reload_sound)


def most_used_weapon_id_for_player(
    state: GameplayState,
    *,
    player_index: int,
    fallback_weapon_id: WeaponId,
) -> WeaponId:
    """Return native's most-used weapon from the global equipped-time table."""

    _ = player_index
    times = state.weapon_usage_time
    if len(times) < 2:
        return WeaponId(fallback_weapon_id)

    def signed_time(weapon_id: int) -> int:
        value = int(times[weapon_id]) & 0xFFFFFFFF
        return value - 0x100000000 if value & 0x80000000 else value

    best = 1
    for weapon_id in range(2, min(len(times), 64)):
        if signed_time(weapon_id) > signed_time(best):
            best = weapon_id
    try:
        return WeaponId(best)
    except ValueError:
        return WeaponId(fallback_weapon_id)


def player_swap_alt_weapon(player: PlayerState) -> bool:
    """Swap primary and alternate weapon runtime blocks (Alternate Weapon perk)."""

    if player.alt_weapon is None:
        return False
    player.weapon, player.alt_weapon = player.alt_weapon, player.weapon
    return True


def player_start_reload(
    player: PlayerState,
    state: GameplayState,
    *,
    players: Sequence[PlayerState] | None = None,
) -> None:
    """Start or refresh a reload timer (`player_start_reload` @ 0x00413430)."""

    # Native queries the global perk table through `perk_count_get` (and reads
    # Fastloader directly from slot zero) even while mutating another overlay
    # player. Corrected mode keeps the intuitive per-player policy.
    perk_player = players[0] if state.preserve_bugs and players else player
    refresh_player_stats(list(players) if players else [player])

    if player.weapon.reload_active and (
        perk_active(perk_player, PerkId.AMMUNITION_WITHIN) or perk_active(perk_player, PerkId.REGRESSION_BULLETS)
    ):
        return

    weapon = weapon_entry(player.weapon.weapon_id)
    reload_time = f32(weapon.reload_time)

    if not player.weapon.reload_active:
        player.weapon.reload_active = True

    player.weapon.reload_timer = reload_time
    # Fastloader feeds stats.reload_time_mult (x0.7 alone).
    reload_mult = float(perk_player.stats.reload_time_mult)
    if reload_mult != 1.0:
        player.weapon.reload_timer = x87_pc24_mul(reload_time, f32(reload_mult))
    if state.bonuses.weapon_power_up > 0.0 and wpu_boosts_fire_rate(int(player.weapon.weapon_id)):
        # Normalized WPU (~+30% DPS): reload x0.8 alongside the x1.3 fire rate.
        player.weapon.reload_timer = x87_pc24_mul(player.weapon.reload_timer, f32(0.8))

    player.weapon.reload_timer_max = player.weapon.reload_timer
