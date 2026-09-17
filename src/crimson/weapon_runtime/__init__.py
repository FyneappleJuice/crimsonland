from __future__ import annotations

from .assign import (
    apply_clip_stat_mods_to_current_weapon,
    init_default_alt_weapon,
    most_used_weapon_id_for_player,
    player_start_reload,
    player_swap_alt_weapon,
    weapon_assign_player,
    weapon_entry,
)
from .availability import INACTIVE_WEAPON_IDS, prepare_weapon_availability, weapon_pick_random_available
from .fire import WeaponFireCtx, WeaponFireResult, fire_weapon
from .spawn import (
    owner_ref_for_player,
    owner_ref_for_player_projectiles,
    projectile_spawn,
    spawn_projectile_ring,
    travel_budget_for_type_id,
)
from .tags import (
    WEAPON_TAGS,
    WeaponArchetype,
    WeaponDelivery,
    WeaponTags,
    weapon_tags,
    weapons_with_archetype,
    weapons_with_damage_type,
    weapons_with_delivery,
)

__all__ = [
    "INACTIVE_WEAPON_IDS",
    "WEAPON_TAGS",
    "WeaponArchetype",
    "WeaponDelivery",
    "WeaponFireCtx",
    "WeaponFireResult",
    "WeaponTags",
    "apply_clip_stat_mods_to_current_weapon",
    "fire_weapon",
    "init_default_alt_weapon",
    "most_used_weapon_id_for_player",
    "owner_ref_for_player",
    "owner_ref_for_player_projectiles",
    "player_start_reload",
    "player_swap_alt_weapon",
    "prepare_weapon_availability",
    "projectile_spawn",
    "spawn_projectile_ring",
    "travel_budget_for_type_id",
    "weapon_assign_player",
    "weapon_entry",
    "weapon_pick_random_available",
    "weapon_tags",
    "weapons_with_archetype",
    "weapons_with_damage_type",
    "weapons_with_delivery",
]
