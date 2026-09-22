from __future__ import annotations

"""Run mod -> the `StatMod`s it applies. Mirrors `progression.sources.PERK_STAT_MODS`
in shape, but every entry here is purely additive/percent - there's no
`RUN_MOD_MECHANICAL` counterpart, since run mods never do anything but nudge
a stat. Contribution scales with how many times the player has picked a given
run mod this run (see `progression.sources.collect_run_mod_stat_mods`).

The two meta slots (DAMAGE_TYPE_BOOST, WEAPON_TYPE_BOOST) map to an empty
tuple - they're never applied directly. Picking one resolves to one of the
hidden ids below instead (run_mods/selection.py's sub-roll), and that hidden
id's own entry here is what actually gets applied."""

from ..progression.modifiers import StatMod, flat, increased, more
from .ids import RunModId

RUN_MOD_STAT_MODS: dict[RunModId, tuple[StatMod, ...]] = {
    RunModId.FIRE_RATE: (more("shot_cooldown_mult", -0.02, source="run_mod:fire_rate"),),
    RunModId.RELOAD_SPEED: (more("reload_time_mult", -0.03, source="run_mod:reload_speed"),),
    RunModId.CLIP_SIZE: (increased("clip_size_mult", 0.04, source="run_mod:clip_size"),),
    RunModId.POWERUP_DURATION: (increased("bonus_duration_mult", 0.05, source="run_mod:powerup_duration"),),
    RunModId.MOVE_SPEED: (increased("move_speed_mult", 0.03, source="run_mod:move_speed"),),
    RunModId.PICKUP_RADIUS: (increased("pickup_radius_mult", 0.08, source="run_mod:pickup_radius"),),
    RunModId.XP_GAIN: (increased("xp_mult", 0.03, source="run_mod:xp_gain"),),
    RunModId.SPREAD: (more("spread_mult", -0.05, source="run_mod:spread"),),
    RunModId.PROJECTILE_SPEED: (increased("projectile_speed_mult", 0.04, source="run_mod:projectile_speed"),),
    # crit_chance's identity is 0.0 - it's a summed "increased %" applied
    # against the weapon's own base chance at the point of use
    # (weapon_runtime/crit.py), not a multiplier of a nonzero identity - so
    # this must be flat() to accumulate correctly (increased() would always
    # resolve to 0.0 * (1 + n) = 0.0 regardless of stacks).
    RunModId.CRIT_CHANCE: (flat("crit_chance", 0.05, source="run_mod:crit_chance"),),
    # crit_mult's identity is already nonzero (2.0, the base crit multiplier) -
    # a flat +0.1 per stack, same "+0.1" every time regardless of stack count.
    RunModId.CRIT_MULTIPLIER: (flat("crit_mult", 0.1, source="run_mod:crit_multiplier"),),
    # The one truly universal damage bucket - weaker than any of the
    # damage-type or weapon-type buckets below, by design.
    RunModId.ALL_DAMAGE: (increased("damage_mult", 0.015, source="run_mod:all_damage"),),
    # Meta slots - never applied directly.
    RunModId.DAMAGE_TYPE_BOOST: (),
    RunModId.WEAPON_TYPE_BOOST: (),
    # --- damage-type bucket (DAMAGE_TYPE_BOOST's sub-roll targets) -------
    RunModId.BULLET_DAMAGE: (increased("damage_mult_bullet", 0.03, source="run_mod:bullet_damage"),),
    RunModId.PLASMA_DAMAGE: (increased("damage_mult_plasma", 0.03, source="run_mod:plasma_damage"),),
    RunModId.ENERGY_DAMAGE: (increased("damage_mult_energy", 0.03, source="run_mod:energy_damage"),),
    RunModId.ION_DAMAGE: (increased("damage_mult_ion", 0.03, source="run_mod:ion_damage"),),
    RunModId.FIRE_DAMAGE: (increased("damage_mult_fire", 0.03, source="run_mod:fire_damage"),),
    # --- weapon-archetype bucket (WEAPON_TYPE_BOOST's sub-roll targets) --
    RunModId.PISTOL_DAMAGE: (increased("damage_mult_archetype_pistol", 0.05, source="run_mod:pistol_damage"),),
    RunModId.RIFLE_DAMAGE: (increased("damage_mult_archetype_rifle", 0.05, source="run_mod:rifle_damage"),),
    RunModId.SMG_DAMAGE: (increased("damage_mult_archetype_smg", 0.05, source="run_mod:smg_damage"),),
    RunModId.SHOTGUN_DAMAGE: (increased("damage_mult_archetype_shotgun", 0.05, source="run_mod:shotgun_damage"),),
    RunModId.MINIGUN_DAMAGE: (increased("damage_mult_archetype_minigun", 0.05, source="run_mod:minigun_damage"),),
    RunModId.CANNON_DAMAGE: (increased("damage_mult_archetype_cannon", 0.05, source="run_mod:cannon_damage"),),
    RunModId.FLAMETHROWER_DAMAGE: (
        increased("damage_mult_archetype_flamethrower", 0.05, source="run_mod:flamethrower_damage"),
    ),
    RunModId.ARC_DAMAGE: (increased("damage_mult_archetype_arc", 0.05, source="run_mod:arc_damage"),),
    RunModId.MELEE_DAMAGE: (increased("damage_mult_archetype_melee", 0.05, source="run_mod:melee_damage"),),
    # A generic amplifier read directly by individual perks' own formulas, not
    # by the progression pipeline - see run_mods/ids.py's PERK_EFFICACY entry.
    RunModId.PERK_EFFICACY: (increased("perk_efficacy", 0.05, source="run_mod:perk_efficacy"),),
}

if set(RUN_MOD_STAT_MODS) != set(RunModId):
    raise RuntimeError("RUN_MOD_STAT_MODS is missing an entry for some RunModId")
