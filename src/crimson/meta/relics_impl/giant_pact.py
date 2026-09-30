from __future__ import annotations

"""Pact of the Giant relic (not native).

A second weapon slot (player.alt_weapon) fires alongside the first, in
strict alternation, for the whole run. The slots take turns
(player.giant_pact_next_slot flips after every shot), and the slot whose
turn it is, X, fires when

    X.shot_cooldown <= 0 AND Y.shot_cooldown <= Y.shot_cooldown_max / 2

(Y = the other slot - see gameplay.py's dual-fire loop). X's own solo rate is
always a hard floor (the first term), and the turn means a fast weapon waits
for a slow partner's next shot instead of firing again - the half-cooldown
gate alone let e.g. a Jackhammer fire ~3 times per Pistol shot. A dry slot
passes its turn and never makes the other wait, so an empty partner doesn't
stall anything. At most one slot fires per tick.

Both slots pay a flat 1.5x shot_cooldown multiplier - except a weapon
firing alone because the other slot is out of ammo, which fires at its own
normal rate (WeaponFireCtx.giant_pact_partner_dry) - (fire_rate_cost_mult,
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
# The native "force a weapon drop on kills while you only have a Pistol" rule
# (bonuses/pool.py) runs for at most this many drops per run while
# dual-wielding - enough to arm both slots, not an endless reroll.
GIANT_PACT_FORCED_WEAPON_DROPS = 2
# The second forced drop leans toward the first one: weapons sharing its
# weapon class (archetype) or its ammo/damage type are each this many times
# as likely, multiplicatively - so the same weapon (both) is the likeliest.
GIANT_PACT_SIMILAR_WEAPON_WEIGHT = 3.0


def giant_pact_active() -> bool:
    return relic_owned(RelicId.GIANT_PACT_LOW)


def dual_wielding(player: PlayerState) -> bool:
    """giant_pact_active() plus a defensive check that the player actually
    has an alt slot - every real player reset path seeds one
    (init_default_alt_weapon), but a bare PlayerState(...) built directly in
    tests/tools may not; fail closed to single-weapon behavior rather than
    crash on those."""

    return giant_pact_active() and player.alt_weapon is not None


def pick_similar_weapon(state: GameplayState, first_weapon_id: int) -> int:
    """The second forced drop's weapon, weighted toward `first_weapon_id`:
    x GIANT_PACT_SIMILAR_WEAPON_WEIGHT for the same weapon class, and again for
    the same damage type (a Plasma Rifle favours other rifles and other
    plasma guns, and another Plasma Rifle most of all). Draws only from the
    currently droppable weapons, from a private RNG seeded off the sim RNG's
    state (same convention as run_mods/selection.py), so the native-parity
    rng sequence isn't disturbed."""

    import random as _random

    from ...weapon_runtime.availability import WEAPON_DROP_ID_COUNT
    from ...weapon_runtime.tags import weapon_tags
    from ...weapons import WeaponId

    first = weapon_tags(WeaponId(first_weapon_id))
    candidates: list[int] = []
    weights: list[float] = []
    for weapon_id in range(1, WEAPON_DROP_ID_COUNT + 1):
        if weapon_id >= len(state.weapon_available) or not state.weapon_available[weapon_id]:
            continue
        if weapon_id == int(WeaponId.PISTOL):
            continue
        tags = weapon_tags(WeaponId(weapon_id))
        weight = 1.0
        if tags.archetype == first.archetype:
            weight *= GIANT_PACT_SIMILAR_WEAPON_WEIGHT
        if tags.damage_type == first.damage_type:
            weight *= GIANT_PACT_SIMILAR_WEAPON_WEIGHT
        candidates.append(weapon_id)
        weights.append(weight)
    if not candidates:
        return int(first_weapon_id)
    rng = _random.Random(int(state.rng.state))
    return int(rng.choices(candidates, weights=weights, k=1)[0])


def wielded_slots(player: PlayerState) -> list[WeaponSlot]:
    """Every weapon slot the player is actually firing: just the primary,
    or both while dual-wielding. For anything that applies a weapon effect
    "to your weapon" (clip size perks, current-weapon biases) so it reaches
    both guns instead of only player.weapon."""

    if dual_wielding(player) and player.alt_weapon is not None:
        return [player.weapon, player.alt_weapon]
    return [player.weapon]


def refill_wielded_slots(player: PlayerState, *, reset_shot_cooldown: bool) -> None:
    """A power-up's "instant full clip" (Reflex Boost, Weapon Power Up, Fire
    Bullets, Plasma Overload): refill every wielded weapon - both slots while
    dual-wielding - and cut any reload short. `reset_shot_cooldown` also
    readies the next shot, for the pickups that do that natively."""

    for slot in wielded_slots(player):
        slot.ammo = float(slot.clip_size)
        slot.reload_timer = 0.0
        if reset_shot_cooldown:
            slot.shot_cooldown = 0.0


def fire_rate_cost_mult(player: PlayerState) -> float:
    _ = player
    return GIANT_PACT_FIRE_RATE_COST_MULT if giant_pact_active() else 1.0


def dual_fire_suppressed(player: PlayerState) -> bool:
    """Fire Bullets and Plasma Overload (bonuses/fire_bullets.py,
    bonuses/plasma_overload.py) override *every* wielded weapon's fire
    recipe to the exact same fixed-rate, zero-ammo-cost shot - so while
    dual-wielding, "alternating" between the two slots is no longer
    alternating between two distinct real guns (where a slow partner
    naturally rate-limits a fast one, e.g. Mini-Rocket Swarmers paired with
    anything else still fires at its own normal pace regardless of the
    other slot). Both slots being identically fast lets the turn-based
    alternation (gameplay.py's giant_pact_dual_fire) clear a shot every
    0.75x a single weapon's cooldown instead of every 1x, netting a ~33%
    "free" DPS bump - free because neither bonus costs ammo - that a real
    weapon pair never gets. Suppressing dual-fire while either bonus is
    active - fire from the primary slot alone, at the bonus's own normal
    rate, exactly like a solo (non-dual-wielding) player - removes that
    free bump without touching either bonus's own tuning or the relic's
    ordinary (real-weapon) behavior."""

    return float(player.fire_bullets_timer) > 0.0 or float(player.plasma_overload_timer) > 0.0


def active_slot(player: PlayerState) -> WeaponSlot:
    """Which slot a floor weapon pickup should replace."""

    if player.giant_pact_active_slot == 1 and player.alt_weapon is not None:
        return player.alt_weapon
    return player.weapon


def holding_starter_pistol(player: PlayerState) -> bool:
    """Whether the player is still on a starter Pistol - the native "force a
    weapon drop on kills while you only have a pistol" rule keys off this.
    While dual-wielding, either slot counts, so a run starts with the drops
    arming *both* slots instead of stopping after the first pickup."""

    from ...weapons import WeaponId

    if player.weapon.weapon_id == WeaponId.PISTOL:
        return True
    return dual_wielding(player) and player.alt_weapon is not None and player.alt_weapon.weapon_id == WeaponId.PISTOL


def pickup_target_slot(player: PlayerState) -> WeaponSlot:
    """Which slot a weapon pickup replaces while dual-wielding: the active
    slot, except that a leftover starter Pistol in the other slot is filled
    first - so the first two pickups of a run give two real weapons instead
    of the second one overwriting the first."""

    from ...weapons import WeaponId

    target = active_slot(player)
    other = player.alt_weapon if target is player.weapon else player.weapon
    if (
        other is not None
        and target.weapon_id != WeaponId.PISTOL
        and other.weapon_id == WeaponId.PISTOL
    ):
        return other
    return target


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
    "GIANT_PACT_FORCED_WEAPON_DROPS",
    "active_slot",
    "clear_alt_reload_active_if_gate_open",
    "dual_fire_suppressed",
    "dual_wielding",
    "fire_rate_cost_mult",
    "flip_active_slot",
    "giant_pact_active",
    "holding_starter_pistol",
    "maybe_start_combined_reload",
    "pick_similar_weapon",
    "pickup_target_slot",
    "refill_wielded_slots",
    "start_combined_reload",
    "wielded_slots",
]
