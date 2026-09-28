from __future__ import annotations

"""Pact of the Giant relic (not native).

A second weapon slot (player.alt_weapon) fires alongside the first, in
strict alternation, for the whole run:

    X may fire when X.shot_cooldown <= 0 AND Y.shot_cooldown <= Y.shot_cooldown_max / 2

(X, Y = the two slots, either order - see gameplay.py's dual-fire loop).
X's own solo rate is always a hard floor (the first term); if Y is empty its
shot_cooldown decays to 0 and stays there, so the second term is permanently
true and X just fires at its own unthrottled rate - no special-casing needed
for an empty partner. At most one slot fires per tick: the loop tries
player.weapon first, falling back to player.alt_weapon only if the primary
attempt didn't fire.

Both slots pay a flat 1.5x shot_cooldown multiplier (fire_rate_cost_mult,
hooked into weapon_runtime/fire.py right next to Pendulum's own
can't-fold-into-the-static-stat multiplier) as the relic's balancing cost.
Every other perk/run-mod that feeds PlayerStats (Fastshot, Fastloader, Ammo
Maniac, WPU, War Banner, ...) already applies to whichever slot is advanced,
since gameplay.py runs the ordinary single-slot advance functions against
each slot via weapon_runtime.assign.weapon_slot_active - nothing here
duplicates that math.

Reload only triggers once BOTH slots are empty (each empty slot just
silently stops firing per the math above, rather than triggering its own
solo reload); the combined duration is
max(reload_time_1, reload_time_2) + min(reload_time_1, reload_time_2) / 2,
where reload_time_N is each weapon's own fully-perk-modified reload time -
computed by calling the ordinary single-slot player_start_reload against
each slot in turn (weapon_slot_active), so Fastloader/WPU/SwarmerDumpMode/
etc. all apply exactly as they would for a single-weapon player. Both slots
are then stamped with the same combined value and decay in lockstep.

"Active slot" (giant_pact_active_slot on PlayerState) is a separate concept
from "which slot fired this tick": it's which slot a floor weapon pickup
replaces (bonuses/weapon.py), defaulting to the primary. Only a manual
Reload-key press flips it, alongside forcing an immediate full reload of
both slots regardless of current ammo.
"""

from typing import TYPE_CHECKING

from ..relics import RelicId, relic_owned
from ...weapon_runtime.assign import player_start_reload, weapon_slot_active

if TYPE_CHECKING:
    from ...sim.state_types import GameplayState, PlayerState, WeaponSlot

GIANT_PACT_FIRE_RATE_COST_MULT = 1.5


def giant_pact_active() -> bool:
    return relic_owned(RelicId.GIANT_PACT_LOW)


def dual_wielding(player: PlayerState) -> bool:
    """giant_pact_active() plus a defensive check that the player actually
    has an alt slot - every real player reset path seeds one
    (init_default_alt_weapon), but a bare PlayerState(...) built directly in
    tests/tools may not; fail closed to single-weapon behavior rather than
    crash on those."""

    return giant_pact_active() and player.alt_weapon is not None


def fire_rate_cost_mult(player: PlayerState) -> float:
    _ = player
    return GIANT_PACT_FIRE_RATE_COST_MULT if giant_pact_active() else 1.0


def active_slot(player: PlayerState) -> WeaponSlot:
    """Which slot a floor weapon pickup should replace."""

    if player.giant_pact_active_slot == 1 and player.alt_weapon is not None:
        return player.alt_weapon
    return player.weapon


def flip_active_slot(player: PlayerState) -> None:
    player.giant_pact_active_slot = 1 - int(player.giant_pact_active_slot)


def clear_alt_reload_active_if_gate_open(player: PlayerState) -> None:
    """Mirrors gameplay.py's clear_reload_active_if_gate_open for the alt
    slot, minus its Pendulum phase-flip: that's a once-per-reload-completion,
    player-global event that the primary slot's own
    clear_reload_active_if_gate_open call already owns. Running the full
    function symmetrically on both slots would double-flip it (net no-op)
    every single combined reload, since both slots' gates open on the same
    tick by construction."""

    alt = player.alt_weapon
    if alt is None:
        return
    if alt.shot_cooldown <= 0.0 and alt.reload_timer == 0.0:
        alt.reload_active = False


def start_combined_reload(
    player: PlayerState,
    state: GameplayState,
    *,
    players: list[PlayerState] | None = None,
    force: bool = False,
) -> None:
    """Reload both slots together, using max(t1,t2) + min(t1,t2)/2 as the
    shared duration. `force=True` (a manual Reload-key press) always
    restarts, even mid-reload or with a full clip."""

    primary = player.weapon
    alt = player.alt_weapon
    if alt is None:
        return

    if force:
        # Clear first so player_start_reload's own "already reloading"
        # guards (Ammunition Within / Regression Bullets) don't turn a
        # forced manual reload into a no-op.
        primary.reload_active = False
        alt.reload_active = False

    with weapon_slot_active(player, primary):
        player_start_reload(player, state, players=players)
    with weapon_slot_active(player, alt):
        player_start_reload(player, state, players=players)

    t1 = float(primary.reload_timer_max)
    t2 = float(alt.reload_timer_max)
    combined = max(t1, t2) + min(t1, t2) * 0.5

    primary.reload_timer = combined
    primary.reload_timer_max = combined
    alt.reload_timer = combined
    alt.reload_timer_max = combined


def maybe_start_combined_reload(
    player: PlayerState,
    state: GameplayState,
    *,
    players: list[PlayerState] | None = None,
) -> None:
    """Auto-trigger: only once BOTH slots are dry and neither is already
    reloading. Called unconditionally every tick from gameplay.py's dual-fire
    branch - cheap early-outs make this a no-op almost always."""

    if not dual_wielding(player):
        return
    primary, alt = player.weapon, player.alt_weapon
    assert alt is not None
    if primary.ammo > 0.0 or alt.ammo > 0.0:
        return
    if primary.reload_active or alt.reload_active:
        return
    start_combined_reload(player, state, players=players, force=False)


__all__ = [
    "GIANT_PACT_FIRE_RATE_COST_MULT",
    "active_slot",
    "clear_alt_reload_active_if_gate_open",
    "dual_wielding",
    "fire_rate_cost_mult",
    "flip_active_slot",
    "giant_pact_active",
    "maybe_start_combined_reload",
    "start_combined_reload",
]
