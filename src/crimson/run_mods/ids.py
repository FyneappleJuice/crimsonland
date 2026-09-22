from __future__ import annotations

"""Run mod ids and display metadata.

Not native: a rewrite-only, per-run-only pool of small numeric stat bonuses,
picked alongside every perk offer and meant to stack repeatedly over one run.
Distinct from the persistent, pre-run `crimson.meta.relics` grid system -
these two pools do not interact.

Two entries (DAMAGE_TYPE_BOOST, WEAPON_TYPE_BOOST) are "meta" slots: they're
the only ones ever drawn from the base pool for their category, but they
never reach a player - `run_mod_generate_choices` immediately resolves each
one to a concrete damage-type/archetype id (weighted 2x toward whatever the
player is currently holding - see run_mods/selection.py) before the choice
list is returned, so what's actually shown and picked already has a fixed,
known number (e.g. "+3% Plasma Damage") - there is no click-to-reveal gamble.
The specific ids they resolve into (RUN_MOD_HIDDEN_FROM_POOL) are real
RunModIds with their own StatMod entries and their own counters, but are
never drawn directly as their own pool entry.
"""

from enum import IntEnum, unique

import msgspec


@unique
class RunModId(IntEnum):
    FIRE_RATE = 0
    RELOAD_SPEED = 1
    CLIP_SIZE = 2
    POWERUP_DURATION = 3
    MOVE_SPEED = 4
    PICKUP_RADIUS = 5
    XP_GAIN = 6
    SPREAD = 7
    PROJECTILE_SPEED = 8
    CRIT_CHANCE = 9
    CRIT_MULTIPLIER = 10
    ALL_DAMAGE = 11
    DAMAGE_TYPE_BOOST = 12
    WEAPON_TYPE_BOOST = 13
    # --- hidden: only reachable via DAMAGE_TYPE_BOOST's sub-roll ---------
    BULLET_DAMAGE = 14
    PLASMA_DAMAGE = 15
    ENERGY_DAMAGE = 16
    ION_DAMAGE = 17
    FIRE_DAMAGE = 18
    # --- hidden: only reachable via WEAPON_TYPE_BOOST's sub-roll ---------
    PISTOL_DAMAGE = 19
    RIFLE_DAMAGE = 20
    SMG_DAMAGE = 21
    SHOTGUN_DAMAGE = 22
    MINIGUN_DAMAGE = 23
    CANNON_DAMAGE = 24
    FLAMETHROWER_DAMAGE = 25
    ARC_DAMAGE = 26
    MELEE_DAMAGE = 27
    PERK_EFFICACY = 28


# Never drawn directly into a choice list - only reachable through a meta
# slot's pick-time sub-roll (run_mods/selection.py).
RUN_MOD_HIDDEN_FROM_POOL: frozenset[RunModId] = frozenset(
    (
        RunModId.BULLET_DAMAGE,
        RunModId.PLASMA_DAMAGE,
        RunModId.ENERGY_DAMAGE,
        RunModId.ION_DAMAGE,
        RunModId.FIRE_DAMAGE,
        RunModId.PISTOL_DAMAGE,
        RunModId.RIFLE_DAMAGE,
        RunModId.SMG_DAMAGE,
        RunModId.SHOTGUN_DAMAGE,
        RunModId.MINIGUN_DAMAGE,
        RunModId.CANNON_DAMAGE,
        RunModId.FLAMETHROWER_DAMAGE,
        RunModId.ARC_DAMAGE,
        RunModId.MELEE_DAMAGE,
    ),
)

# The two meta slots themselves are never applied directly (run_mod_apply is
# always called with whatever they resolve to instead) - see selection.py.
RUN_MOD_META_SLOTS: frozenset[RunModId] = frozenset((RunModId.DAMAGE_TYPE_BOOST, RunModId.WEAPON_TYPE_BOOST))


class RunModMeta(msgspec.Struct, frozen=True):
    run_mod_id: RunModId
    name: str
    description: str


_RUN_MOD_TABLE: list[RunModMeta] = [
    RunModMeta(RunModId.FIRE_RATE, "Fire Rate", "+2% fire rate."),
    RunModMeta(RunModId.RELOAD_SPEED, "Reload Speed", "-3% reload time."),
    RunModMeta(RunModId.CLIP_SIZE, "Clip Size", "+4% clip size."),
    RunModMeta(RunModId.POWERUP_DURATION, "Power-up Duration", "+5% power-up duration."),
    RunModMeta(RunModId.MOVE_SPEED, "Move Speed", "+3% move speed."),
    RunModMeta(RunModId.PICKUP_RADIUS, "Pickup Radius", "+8% pickup radius."),
    RunModMeta(RunModId.XP_GAIN, "XP Gain", "+3% XP gained."),
    RunModMeta(RunModId.SPREAD, "Spread", "-5% weapon spread buildup."),
    RunModMeta(RunModId.PROJECTILE_SPEED, "Projectile Speed", "+4% projectile speed."),
    RunModMeta(RunModId.CRIT_CHANCE, "Crit Chance", "+5% increased critical strike chance."),
    RunModMeta(RunModId.CRIT_MULTIPLIER, "Crit Multiplier", "+10% crit multiplier."),
    RunModMeta(RunModId.ALL_DAMAGE, "All Damage", "+1.5% damage, all damage types."),
    RunModMeta(
        RunModId.DAMAGE_TYPE_BOOST,
        "Elemental Affinity",
        "+3% damage of one damage type (bullet/plasma/energy/ion/fire) - "
        "weighted toward whatever you're currently using.",
    ),
    RunModMeta(
        RunModId.WEAPON_TYPE_BOOST,
        "Weapon Affinity",
        "+5% damage with one weapon type (pistol/rifle/shotgun/etc.) - "
        "weighted toward whatever you're currently holding.",
    ),
    RunModMeta(RunModId.BULLET_DAMAGE, "Bullet Damage", "+3% bullet damage."),
    RunModMeta(RunModId.PLASMA_DAMAGE, "Plasma Damage", "+3% plasma damage."),
    RunModMeta(RunModId.ENERGY_DAMAGE, "Energy Damage", "+3% energy damage."),
    RunModMeta(RunModId.ION_DAMAGE, "Ion Damage", "+3% ion damage."),
    RunModMeta(RunModId.FIRE_DAMAGE, "Fire Damage", "+3% fire damage."),
    RunModMeta(RunModId.PISTOL_DAMAGE, "Pistol Damage", "+5% pistol damage."),
    RunModMeta(RunModId.RIFLE_DAMAGE, "Rifle Damage", "+5% rifle damage."),
    RunModMeta(RunModId.SMG_DAMAGE, "SMG Damage", "+5% SMG damage."),
    RunModMeta(RunModId.SHOTGUN_DAMAGE, "Shotgun Damage", "+5% shotgun damage."),
    RunModMeta(RunModId.MINIGUN_DAMAGE, "Minigun Damage", "+5% minigun damage."),
    RunModMeta(RunModId.CANNON_DAMAGE, "Cannon Damage", "+5% cannon damage."),
    RunModMeta(RunModId.FLAMETHROWER_DAMAGE, "Flamethrower Damage", "+5% flamethrower damage."),
    RunModMeta(RunModId.ARC_DAMAGE, "Arc Damage", "+5% arc damage."),
    RunModMeta(RunModId.MELEE_DAMAGE, "Melee Damage", "+5% melee damage."),
    RunModMeta(
        RunModId.PERK_EFFICACY,
        "Perk Efficacy",
        "+5% increased perk effectiveness.",
    ),
]

RUN_MOD_BY_ID: dict[RunModId, RunModMeta] = {meta.run_mod_id: meta for meta in _RUN_MOD_TABLE}

RUN_MOD_COUNT_SIZE = len(RunModId)

if set(RUN_MOD_BY_ID) != set(RunModId):
    raise RuntimeError("RUN_MOD_BY_ID is missing an entry for some RunModId")


def run_mod_display_name(run_mod_id: RunModId) -> str:
    return RUN_MOD_BY_ID[run_mod_id].name


def run_mod_display_description(run_mod_id: RunModId) -> str:
    return RUN_MOD_BY_ID[run_mod_id].description
