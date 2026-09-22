from __future__ import annotations

"""Player damage intake helpers.

This is a minimal, rewrite-focused port of `player_take_damage` (0x00425e50).
See: `docs/crimsonland-exe/player-damage.md`.
"""

from collections.abc import Sequence

import msgspec

from grim.sfx_map import SfxId

from .math_parity import f32, x87_pc24_add, x87_pc24_mul, x87_pc24_sub
from .perks import PerkId
from .perks.helpers import perk_active
from .perks.impl.soul_tether import soul_tether_absorb
from .progression import refresh_player_stats
from .rng_caller_static import RngCallerStatic
from .sim.state_types import GameplayState, PlayerState

__all__ = ["PlayerDeathRuntime", "player_take_damage", "player_take_projectile_damage"]
_PLAYER_PAIN_SFX: tuple[SfxId, ...] = (
    SfxId.TROOPER_INPAIN_01,
    SfxId.TROOPER_INPAIN_02,
    SfxId.TROOPER_INPAIN_03,
)
_PLAYER_DEATH_SFX: tuple[SfxId, ...] = (SfxId.TROOPER_DIE_01, SfxId.TROOPER_DIE_02)

# Rewrite-only: new perk tuning (weapon_runtime research batch).
DESPERATION_MAX_REDUCTION = 0.5
AMMO_SHIELD_DAMAGE_REDUCTION = 0.3
AMMO_SHIELD_AMMO_COST = 1.0
ADRENALINE_RUSH_WINDOW_DURATION = 5.0


class PlayerDeathRuntime(msgspec.Struct):
    def on_player_lethal(self, player: PlayerState, *, dt: float) -> None:
        _ = player, dt


def player_take_damage(
    state: GameplayState,
    player: PlayerState,
    damage: float,
    *,
    dt: float | None = None,
    players: Sequence[PlayerState] | None = None,
    death_runtime: PlayerDeathRuntime | None = None,
    floor: float = 0.0,
) -> float:
    """Apply damage to a player, returning the actual damage applied.

    `floor` lower-bounds the resulting health (e.g. 1.0 for self-inflicted,
    non-enemy costs like Ammunition Within, which must never be lethal on
    their own). Real enemy damage always leaves it at the default of 0.0.
    """

    raw_damage = float(f32(damage))
    if state.debug_god_mode:
        return 0.0

    perk_player = player
    refresh_player_stats(list(players) if players else [player])

    if perk_active(perk_player, PerkId.DEATH_CLOCK):
        return 0.0

    # Not native: Perk Efficacy scales most of the perks below at their own
    # call site - see run_mods/ids.py's PERK_EFFICACY entry for the survey.
    efficacy = float(perk_player.stats.perk_efficacy)

    damage_scaled = float(raw_damage)
    if player.weapon.reload_active:
        # Rewrite-only: Tough Reloader++ cuts reload-time damage further, from
        # half down to a quarter. Efficacy deepens whichever cut is active.
        if perk_active(perk_player, PerkId.TOUGH_RELOADER_PLUS):
            damage_scaled = x87_pc24_mul(damage_scaled, f32(0.25 / efficacy))
        elif perk_active(perk_player, PerkId.TOUGH_RELOADER):
            damage_scaled = x87_pc24_mul(damage_scaled, f32(0.5 / efficacy))
    spread_heat_damage = float(damage_scaled)

    state.survival_reward_damage_seen = True

    if float(player.shield_timer) > 0.0:
        return 0.0

    was_alive = float(perk_player.health) > 0.0

    # Thick Skinned feeds stats.damage_taken_mult; alone it resolves to the
    # same f32 ~0.666 constant the perk used directly.
    damage_taken_mult = float(perk_player.stats.damage_taken_mult)
    if damage_taken_mult != 1.0:
        damage_scaled = float(f32(float(damage_scaled) * damage_taken_mult))

    # Rewrite-only: Desperation - incoming damage drops as current health
    # drops (health is a 0-100 value), up to DESPERATION_MAX_REDUCTION at 0 HP.
    if perk_active(perk_player, PerkId.DESPERATION):
        missing_frac = max(0.0, 1.0 - float(perk_player.health) / 100.0)
        damage_scaled = float(
            f32(float(damage_scaled) * (1.0 - DESPERATION_MAX_REDUCTION * efficacy * missing_frac)),
        )

    # Rewrite-only: Ammo Shield - trades a flat ammo cost per hit for a cut to
    # that hit's damage. The ammo cost floors at 0 regardless, so running dry
    # doesn't cancel the damage reduction.
    if perk_active(perk_player, PerkId.AMMO_SHIELD):
        reduction = min(1.0, AMMO_SHIELD_DAMAGE_REDUCTION * efficacy)
        damage_scaled = float(f32(float(damage_scaled) * (1.0 - reduction)))
        perk_player.weapon.ammo = max(0.0, float(perk_player.weapon.ammo) - AMMO_SHIELD_AMMO_COST)

    dodged = False
    if perk_active(perk_player, PerkId.NINJA):
        if perk_active(perk_player, PerkId.DODGER):
            # Rewrite-only: Ninja composes with Dodger (its prereq) instead of
            # replacing it. Both roll at 1-in-5; combined miss chance for two
            # independent "chance to dodge" rolls is 1 - (1-1/5)*(1-1/5) =
            # 9/25 - reinterprets one roll (mod 25) rather than drawing twice,
            # so the RNG stream still advances exactly once per hit either way.
            # Not native: Perk Efficacy raises this at efficacy != 1.0 by
            # reinterpreting the same roll over a finer (mod 100) range - the
            # exact mod-25 native shape is kept bit-for-bit at efficacy==1.0.
            ninja_roll = state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_NINJA)
            if efficacy == 1.0:
                dodged = (ninja_roll % 25) < 9
            else:
                dodged = (ninja_roll % 100) < min(100, round(36.0 * efficacy))
        else:
            dodger_roll = state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_NINJA)
            if efficacy == 1.0:
                dodged = (dodger_roll % 5) == 0
            else:
                dodged = (dodger_roll % 100) < min(100, round(20.0 * efficacy))
    elif perk_active(perk_player, PerkId.DODGER):
        dodger_roll = state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_DODGER)
        if efficacy == 1.0:
            dodged = (dodger_roll % 5) == 0
        else:
            dodged = (dodger_roll % 100) < min(100, round(20.0 * efficacy))

    health_before = float(player.health)
    if not dodged:
        if perk_active(perk_player, PerkId.HIGHLANDER):
            # Not native: Perk Efficacy lowers this chance instead of raising
            # it - a more "efficacious" Highlander means dying less often to
            # its own gamble, not more.
            highlander_roll = state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_HIGHLANDER)
            if efficacy == 1.0:
                highlander_death = (highlander_roll % 10) == 0
            else:
                highlander_death = (highlander_roll % 100) < min(100, round(10.0 / efficacy))
            if highlander_death:
                player.health = 0.0
        else:
            # Rewrite-only: Soul Tether's shield absorbs before health does.
            remaining_damage = soul_tether_absorb(player, float(damage_scaled))
            player.health = x87_pc24_sub(f32(player.health), f32(remaining_damage))

        if floor > 0.0:
            player.health = max(float(floor), float(player.health))

        # Rewrite-only: Adrenaline Rush - any actual health loss opens (or
        # refreshes) a timed bonus-damage window.
        if health_before - float(player.health) > 0.0 and perk_active(player, PerkId.ADRENALINE_RUSH):
            player.adrenaline_rush_window_timer = ADRENALINE_RUSH_WINDOW_DURATION

    # Native routes exact-zero Highlander kills through the pain branch; this
    # rewrite treats `health == 0` as lethal here.
    lethal_hit = float(player.health) <= 0.0
    # Native's dodge proc jumps past the damage stores but still runs the
    # health branch: a dodged hit on an already-dead player keeps decrementing
    # the death-animation timer.
    if lethal_hit and dt is not None and float(dt) > 0.0:
        player.death_timer = x87_pc24_sub(
            f32(player.death_timer),
            x87_pc24_mul(f32(dt), f32(28.0)),
        )

    # Native emits pain/death VO before heading jitter + low-health timer RNG work.
    if not lethal_hit:
        state.sfx_queue.append(
            _PLAYER_PAIN_SFX[state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_PAIN_SFX) % len(_PLAYER_PAIN_SFX)],
        )
        if not was_alive:
            return max(0.0, health_before - float(player.health))
    else:
        if not was_alive:
            return max(0.0, health_before - float(player.health))
        if not perk_active(perk_player, PerkId.FINAL_REVENGE):
            state.sfx_queue.append(_PLAYER_DEATH_SFX[state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_DEATH_SFX) & 1])
        elif death_runtime is not None:
            death_runtime.on_player_lethal(player, dt=0.0 if dt is None else float(dt))

    if not dodged:
        if not perk_player.stats.has("no_hit_stagger"):  # Unstoppable
            heading_jitter = x87_pc24_mul(
                float((state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_HEADING) % 100) - 50),
                f32(0.04),
            )
            player.heading = x87_pc24_add(f32(player.heading), heading_jitter)
            # Native uses post-Tough-Reloader damage (before Thick Skinned) for spread heat growth.
            player.spread_heat = min(
                f32(0.48),
                x87_pc24_add(
                    player.spread_heat,
                    x87_pc24_mul(spread_heat_damage, f32(0.01)),
                ),
            )

        if player.health <= 20.0 and (state.rng.rand_tagged(RngCallerStatic.PLAYER_TAKE_DAMAGE_LOW_HEALTH) & 7) == 3:
            player.low_health_timer = 0.0

    return max(0.0, health_before - float(player.health))


def player_take_projectile_damage(state: GameplayState, player: PlayerState, damage: float) -> float:
    """Apply projectile damage to a player (modeled after `projectile_update` player-hit logic).

    Native `projectile_update` does not call `player_take_damage` for projectile hits: it sets
    `projectile.life_timer = 0.25` and subtracts a fixed amount (usually 10.0) if shield is down.
    """

    dmg = float(damage)
    if dmg <= 0.0:
        return 0.0
    if state.debug_god_mode:
        return 0.0
    if float(player.shield_timer) > 0.0:
        return 0.0

    # Rewrite-only: Soul Tether's shield absorbs before health does.
    dmg = soul_tether_absorb(player, dmg)
    player.health -= dmg
    return dmg
