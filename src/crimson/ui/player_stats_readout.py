from __future__ import annotations

"""Not native: a live readout of the player's actual combat stats, drawn in
the bottom half of the level-up screen's run-mod panel (modes/components/
run_mod_menu_controller.py) - the exact numbers every perk, run mod and relic
has resolved to, rather than the list of bonuses that produced them.

With Pact of the Giant, per-weapon stats (crit chance, reload time) list both
weapons, comma-separated, first slot first.
"""

from ..meta.relics_impl import fortify as relic_fortify
from ..meta.relics_impl import gathering_winds as relic_gathering_winds
from ..meta.relics_impl import giant_pact as relic_giant_pact
from ..meta.relics_impl import warbanner as relic_warbanner
from ..sim.state_types import PlayerState
from ..weapon_runtime.crit import crit_chance_for_weapon
from ..weapons import WEAPON_BY_ID, WeaponId

# player.speed_multiplier's resting value - movement speed reads as a % of it.
_BASE_SPEED_MULTIPLIER = 2.0


def _reload_seconds(player: PlayerState, weapon_id: int) -> float:
    return float(WEAPON_BY_ID[WeaponId(weapon_id)].reload_time) * float(player.stats.reload_time_mult)


def player_stat_lines(player: PlayerState) -> list[tuple[str, str]]:
    """(label, value) rows, in display order."""

    stats = player.stats
    slots = relic_giant_pact.wielded_slots(player)

    crit = ", ".join(
        f"{crit_chance_for_weapon(WeaponId(slot.weapon_id), increased_chance=float(stats.crit_chance)) * 100.0:.1f}%"
        for slot in slots
    )

    speed_bonus = 1.0 if float(player.speed_bonus_timer) > 0.0 else 0.0
    speed = (
        (float(player.speed_multiplier) + speed_bonus)
        / _BASE_SPEED_MULTIPLIER
        * float(stats.move_speed_mult)
        * relic_gathering_winds.speed_mult(player)
        * relic_fortify.speed_mult()
        * relic_warbanner.move_speed_mult(player)
    )

    reload = ", ".join(f"{_reload_seconds(player, slot.weapon_id):.2f}s" for slot in slots)

    return [
        ("HP", f"{float(player.health):.1f} / 100"),
        ("Crit chance", crit),
        ("Crit multiplier", f"{float(stats.crit_mult):.2f}x"),
        ("Move speed", f"{speed * 100.0:.1f}%"),
        ("Reload time", reload),
    ]


__all__ = ["player_stat_lines"]
