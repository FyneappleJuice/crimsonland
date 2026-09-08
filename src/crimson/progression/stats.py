from __future__ import annotations

"""`PlayerStats` - the resolved stat block read by gameplay code.

Every field is a plain number with an identity default (``1.0`` for
multipliers, ``0.0`` for additive terms) so an all-default block changes
nothing. `flags` is the escape hatch for genuinely mechanical toggles that
are not a number ("projectiles chain instead of pierce").

Keep this module dependency-free (only `msgspec`): it is imported by
`crimson.sim.state_types`.
"""

import msgspec

# Field name -> the value that means "no effect". Used by the resolver as the
# starting point and by tests to assert an untouched block. Every field on
# PlayerStats MUST appear here.
STAT_IDENTITIES: dict[str, float] = {
    # --- offense -------------------------------------------------------
    "damage_mult": 1.0,          # every outgoing hit, all damage types
    "damage_mult_projectile": 1.0,  # any main-pool projectile hit (kinetic bullet + energy/plasma)
    "damage_mult_bullet": 1.0,   # kinetic lead only (not plasma)
    "damage_mult_fire": 1.0,
    "damage_mult_ion": 1.0,
    "damage_mult_energy": 1.0,   # plasma / energy weapons only
    "damage_mult_lightning": 1.0,  # chain lightning (Arc Gun) only
    "damage_mult_explosion": 1.0,
    "shot_cooldown_mult": 1.0,   # <1.0 = fires faster (multiplies the cooldown)
    "reload_time_mult": 1.0,     # <1.0 = reloads faster
    "clip_size_mult": 1.0,
    "clip_size_add": 0.0,
    "projectile_count_add": 0.0,
    "pierce_add": 0.0,
    "projectile_speed_mult": 1.0,
    "spread_mult": 1.0,
    "crit_chance": 0.0,          # 0..1
    "crit_mult": 2.0,
    # --- defense ------------------------------------------------------
    "damage_taken_mult": 1.0,
    "max_health_mult": 1.0,
    "health_regen_per_sec": 0.0,
    "dodge_chance": 0.0,         # 0..1
    "move_speed_mult": 1.0,
    # --- utility ----------------------------------------------------
    "xp_mult": 1.0,
    "bonus_duration_mult": 1.0,  # timed power-up duration
    "pickup_radius_mult": 1.0,
    "luck": 0.0,                 # generic "better rolls" knob for new content
}


class PlayerStats(msgspec.Struct, frozen=True):
    # offense
    damage_mult: float = 1.0
    damage_mult_projectile: float = 1.0
    damage_mult_bullet: float = 1.0
    damage_mult_fire: float = 1.0
    damage_mult_ion: float = 1.0
    damage_mult_energy: float = 1.0
    damage_mult_lightning: float = 1.0
    damage_mult_explosion: float = 1.0
    shot_cooldown_mult: float = 1.0
    reload_time_mult: float = 1.0
    clip_size_mult: float = 1.0
    clip_size_add: float = 0.0
    projectile_count_add: float = 0.0
    pierce_add: float = 0.0
    projectile_speed_mult: float = 1.0
    spread_mult: float = 1.0
    crit_chance: float = 0.0
    crit_mult: float = 2.0
    # defense
    damage_taken_mult: float = 1.0
    max_health_mult: float = 1.0
    health_regen_per_sec: float = 0.0
    dodge_chance: float = 0.0
    move_speed_mult: float = 1.0
    # utility
    xp_mult: float = 1.0
    bonus_duration_mult: float = 1.0
    pickup_radius_mult: float = 1.0
    luck: float = 0.0
    # mechanical toggles (keystones / curses); empty by default
    flags: frozenset[str] = frozenset()

    def has(self, flag: str) -> bool:
        return flag in self.flags


DEFAULT_PLAYER_STATS = PlayerStats()

# Sanity: the struct and the identity table must not drift apart.
_STRUCT_FIELDS = set(PlayerStats.__struct_fields__) - {"flags"}
if _STRUCT_FIELDS != set(STAT_IDENTITIES):
    missing = _STRUCT_FIELDS - set(STAT_IDENTITIES)
    extra = set(STAT_IDENTITIES) - _STRUCT_FIELDS
    raise RuntimeError(f"STAT_IDENTITIES out of sync with PlayerStats (missing={missing}, extra={extra})")
