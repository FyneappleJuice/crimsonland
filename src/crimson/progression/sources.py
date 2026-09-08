from __future__ import annotations

"""Where a player's `StatMod`s come from, and how they become a `PlayerStats`.

Two registries together account for **every** perk:

- `PERK_STAT_MODS` - perks whose effect is (at least partly) a number or a
  keystone flag, expressed as data. Gameplay code reads the resolved
  `player.stats` instead of checking the perk.
- `PERK_MECHANICAL` - perks that stay hard-wired, each with a one-line reason
  (dynamic ramps, RNG rolls, one-shot pick effects, timers, conditional
  branches). A contract test asserts the two sets partition `PerkId`.

Weapon affixes, map modifiers and curses will register through the
`extra_sources` argument of `collect_player_stat_mods`; nothing else changes.
"""

from collections.abc import Iterable, Sequence
from itertools import chain
from typing import TYPE_CHECKING

from ..perks.helpers import perk_count_get
from ..perks.ids import PerkId
from .modifiers import StatMod, flag, flat, increased, more, resolve_stats
from .stats import PlayerStats

if TYPE_CHECKING:
    from ..sim.state_types import PlayerState

# Native Thick Skinned multiplies incoming damage by an f32 constant, not exact 2/3.
_THICK_SKINNED_DAMAGE_SCALE = 0.6660000085830688

# perk -> the stat changes / keystone flags it applies. Contribution scales
# with how many copies of a stackable perk the player owns.
#
# Every entry is calibrated so that, with the perk as the ONLY contributor to
# a stat, the resolved number equals the constant the original code used - so
# the existing single-perk tests still pass bit-for-bit. New content stacking
# onto the same stat then composes automatically (and combining two migrated
# perks on one stat folds into a single multiply - a deliberate, documented
# ULP change; this project no longer chases native parity for build content).
PERK_STAT_MODS: dict[PerkId, tuple[StatMod, ...]] = {
    # --- fire rate --------------------------------------------------
    # weapon_runtime/fire.py: shot_cooldown *= 0.88
    PerkId.FASTSHOT: (more("shot_cooldown_mult", -0.12, source="perk:fastshot"),),
    # weapon_runtime/fire.py: shot_cooldown *= 1.05 (aim tradeoff; laser sight
    # + spread reset stay in code - see PERK_MECHANICAL note)
    PerkId.SHARPSHOOTER: (more("shot_cooldown_mult", 0.05, source="perk:sharpshooter"),),
    # --- reload ----------------------------------------------------
    # weapon_runtime/assign.py: reload_timer = reload_time * 0.7
    PerkId.FASTLOADER: (more("reload_time_mult", -0.3, source="perk:fastloader"),),
    # --- ammo / clip ---------------------------------------------
    # weapon_runtime/assign.py: clip += max(1, floor(clip * 0.25))
    PerkId.AMMO_MANIAC: (increased("clip_size_mult", 0.25, source="perk:ammo_maniac"),),
    # weapon_runtime/assign.py: clip += 2. (Its "no more random weapon bonuses"
    # rule stays a raw perk check in bonuses/selection.py + bonuses/pool.py.)
    PerkId.MY_FAVOURITE_WEAPON: (flat("clip_size_add", 2.0, source="perk:my_favourite_weapon"),),
    # --- outgoing damage ---------------------------------------
    # creatures/damage.py: kinetic-bullet damage += itself (x2). Lead only - a
    # uranium slug is meaningless for a plasma bolt, so this does NOT touch energy.
    PerkId.URANIUM_FILLED_BULLETS: (more("damage_mult_bullet", 1.0, source="perk:uranium_filled_bullets"),),
    # creatures/damage.py: projectile damage *= 1.2. "You know where to aim" is
    # ammo-agnostic, so it rides the projectile layer (kinetic bullet + energy).
    PerkId.DOCTOR: (more("damage_mult_projectile", 0.2, source="perk:doctor"),),
    # creatures/damage.py: projectile damage *= 1.4 ; also doubles projectile step
    # count. Smoother barrel / faster shots - applies to any main-pool projectile.
    PerkId.BARREL_GREASER: (
        more("damage_mult_projectile", 0.4, source="perk:barrel_greaser"),
        flag("projectile_double_steps", source="perk:barrel_greaser"),
    ),
    # creatures/damage.py: fire damage *= 1.5
    PerkId.PYROMANIAC: (more("damage_mult_fire", 0.5, source="perk:pyromaniac"),),
    # creatures/damage.py: ion damage *= 1.2 (blast radius bump stays in code)
    PerkId.ION_GUN_MASTER: (more("damage_mult_ion", 0.2, source="perk:ion_gun_master"),),
    # --- incoming damage --------------------------------------
    # player_damage.py: incoming damage *= ~0.666 (max-HP cut on pick stays in code)
    PerkId.THICK_SKINNED: (
        more("damage_taken_mult", _THICK_SKINNED_DAMAGE_SCALE - 1.0, source="perk:thick_skinned"),
    ),
    # bonuses/apply.py: bonus timers *= 1.5
    PerkId.BONUS_ECONOMIST: (more("bonus_duration_mult", 0.5, source="perk:bonus_economist"),),
    # --- pure keystone flags ---------------------------------
    # player_damage.py: incoming hits don't jitter your heading
    PerkId.UNSTOPPABLE: (flag("no_hit_stagger", source="perk:unstoppable"),),
}

# Everything else - stays hard-wired at its call site, reason noted here so
# coverage is provable rather than "probably fine".
PERK_MECHANICAL: dict[PerkId, str] = {
    PerkId.ANTIPERK: "sentinel entry, disabled in the native metadata table",
    PerkId.BLOODY_MESS_QUICK_LEARNER: "kill XP uses int(reward*1.3) via a different accumulator than the normal f32 path",
    PerkId.LEAN_MEAN_EXP_MACHINE: "passive XP generator ticked on a timer",
    PerkId.LONG_DISTANCE_RUNNER: "move speed ramps the longer you run without stopping (dynamic)",
    PerkId.PYROKINETIC: "aiming at a creature heats it up over time",
    PerkId.INSTANT_WINNER: "one-shot +2500 XP when picked",
    PerkId.GRIM_DEAL: "one-shot: flags +18% score and kills the player",
    PerkId.ALTERNATE_WEAPON: "adds a second weapon slot and changes reload/bonus rules",
    PerkId.PLAGUEBEARER: "spreads a contagion between creatures with resistance buildup",
    PerkId.EVIL_EYES: "freezes the creature you are aiming at",
    PerkId.RADIOACTIVE: "damages creatures within a radius each tick",
    PerkId.FATAL_LOTTERY: "one-shot 50/50: die or +10000 XP",
    PerkId.RANDOM_WEAPON: "one-shot: grants a random weapon",
    PerkId.MR_MELEE: "counterattacks adjacent creatures",
    PerkId.ANXIOUS_LOADER: "reload speeds up while you mash fire (conditional)",
    PerkId.FINAL_REVENGE: "on-death hook (screen-clearing burst)",
    PerkId.TELEKINETIC: "pick up bonuses by aiming at them",
    PerkId.PERK_EXPERT: "increases how many perk choices you are offered",
    PerkId.REGRESSION_BULLETS: "firing on an empty clip drains XP",
    PerkId.INFERNAL_CONTRACT: "one-shot: +3 perks and health cut to near zero",
    PerkId.POISON_BULLETS: "applies a poison stack on hit",
    PerkId.DODGER: "RNG dodge roll (1-in-5) at damage time",
    PerkId.BONUS_MAGNET: "raises the on-kill bonus spawn rate",
    PerkId.MONSTER_VISION: "render-only: highlights creatures, disables shadows",
    PerkId.HOT_TEMPERED: "periodic area burst while standing still",
    PerkId.AMMUNITION_WITHIN: "fire while reloading by spending health",
    PerkId.VEINS_OF_POISON: "poisons creatures that bite you",
    PerkId.TOXIC_AVENGER: "contact kills weak creatures (upgrades Veins of Poison)",
    PerkId.REGENERATION: "RNG-gated +1 HP heal tick",
    PerkId.NINJA: "RNG dodge roll (1-in-3) at damage time",
    PerkId.HIGHLANDER: "RNG 1-in-10 instant death instead of taking a hit",
    PerkId.JINXED: "random creatures spontaneously die near you",
    PerkId.PERK_MASTER: "doubles the effect of the Perk Expert line",
    PerkId.REFLEX_BOOSTED: "slows global simulation time",
    PerkId.GREATER_REGENERATION: "upgrades the Regeneration heal tick",
    PerkId.BREATHING_ROOM: "one-shot: kill everything on screen, health cut to 1/3",
    PerkId.DEATH_CLOCK: "30-second countdown to a scripted death; hits do nothing until then",
    PerkId.BANDAGE: "one-shot: restore up to 50% health",
    PerkId.ANGRY_RELOADER: "fires a plasma ring partway through each reload",
    PerkId.STATIONARY_RELOADER: "3x reload speed only while completely still (conditional)",
    PerkId.MAN_BOMB: "explode after standing still for a few seconds",
    PerkId.FIRE_CAUGH: "periodic fireball cough",
    PerkId.LIVING_FORTRESS: "outgoing damage ramps the longer you stand still (dynamic)",
    PerkId.TOUGH_RELOADER: "halves incoming damage only while reloading (conditional)",
    PerkId.LIFELINE_50_50: "Typ-o-Shooter: auto-removes half the wrong targets",
}


def collect_player_stat_mods(
    player: PlayerState,
    *,
    extra_sources: Iterable[StatMod] = (),
) -> list[StatMod]:
    """Every `StatMod` currently affecting `player` (perks + `extra_sources`)."""

    mods: list[StatMod] = []
    for perk_id, perk_mods in PERK_STAT_MODS.items():
        count = perk_count_get(player, perk_id)
        if count <= 0:
            continue
        for _ in range(count):
            mods.extend(perk_mods)
    mods.extend(extra_sources)
    return mods


def resolve_player_stats(
    player: PlayerState,
    *,
    extra_sources: Iterable[StatMod] = (),
) -> PlayerStats:
    return resolve_stats(collect_player_stat_mods(player, extra_sources=extra_sources))


def resolve_team_stats(players: Sequence[PlayerState]) -> PlayerStats:
    """Resolve one block from the union of every player's mods.

    Used by the shared damage path, where the original code applies a perk if
    *any* player owns it rather than attributing the hit to one player.
    """

    return resolve_stats(chain.from_iterable(collect_player_stat_mods(p) for p in players))


def refresh_player_stats(players: Sequence[PlayerState]) -> None:
    """Recompute and store `player.stats` for every player. Called once per
    sim tick (see `WorldState.step`) and again at the few subsystem entry
    points that tests drive directly; cheap enough to run unconditionally."""

    for player in players:
        player.stats = resolve_player_stats(player)
