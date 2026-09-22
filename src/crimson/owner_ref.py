from __future__ import annotations

from enum import IntEnum

import msgspec

LOCAL_PLAYER_OWNER_ID = -100


class OwnerKind(IntEnum):
    NONE = 0
    PLAYER = 1
    CREATURE = 2


class OwnerRef(msgspec.Struct, frozen=True):
    kind: OwnerKind
    index: int = 0
    local_host: bool = False
    # Rewrite-only: set on the owner of a Domino Effect bonus shot specifically
    # (creatures/runtime.py's _fire_momentum_shot), so a kill credited to one
    # doesn't re-trigger another Domino Effect shot (see _start_death). Not
    # part of `to_legacy()`/`from_legacy()` - it's a same-tick anti-recursion
    # guard, not run state that needs to survive a save/replay round-trip.
    via_domino_effect: bool = False
    # Not native: set on self-contained perk-proc damage (Man Bomb, Hot
    # Tempered, Angry Reloader, Fire Cough, Mr. Melee) that spawns a canned
    # projectile/hit of a fixed damage type rather than scaling the player's
    # actual equipped weapon. Damage tagged this way is exempt from the
    # run-mod Elemental Affinity (damage_mult_bullet/plasma/energy/ion/fire)
    # and Weapon Affinity (damage_mult_archetype_*) buckets specifically -
    # see creatures/damage.py's `resolve_team_stats_perks_only` use - but
    # still gets the generic All Damage multiplier and any real native
    # perk-vs-perk interaction that happens to share the same stat field
    # (Ion Gun Master -> Man Bomb, Pyromaniac -> Fire Cough).
    no_run_mod_affinity: bool = False

    @classmethod
    def none(cls) -> OwnerRef:
        return cls(kind=OwnerKind.NONE)

    @classmethod
    def from_local_player(cls, index: int) -> OwnerRef:
        return cls(kind=OwnerKind.PLAYER, index=int(index), local_host=True)

    @classmethod
    def from_player(cls, index: int) -> OwnerRef:
        return cls(kind=OwnerKind.PLAYER, index=int(index), local_host=False)

    @classmethod
    def from_creature(cls, index: int) -> OwnerRef:
        return cls(kind=OwnerKind.CREATURE, index=int(index), local_host=False)

    @classmethod
    def from_legacy(cls, owner_id: int) -> OwnerRef:
        legacy = int(owner_id)
        if legacy == int(LOCAL_PLAYER_OWNER_ID):
            return cls.from_local_player(0)
        if legacy < 0:
            idx = -1 - legacy
            if idx >= 0:
                return cls.from_player(idx)
            return cls.none()
        return cls.from_creature(legacy)

    def to_legacy(self) -> int:
        if self.kind == OwnerKind.NONE:
            return 0
        if self.kind == OwnerKind.CREATURE:
            return int(self.index)
        if bool(self.local_host) and int(self.index) == 0:
            return int(LOCAL_PLAYER_OWNER_ID)
        return -1 - int(self.index)

    def is_player(self) -> bool:
        return self.kind == OwnerKind.PLAYER

    def player_index(self) -> int | None:
        if self.kind != OwnerKind.PLAYER:
            return None
        return int(self.index)

    def player_index_in_bounds(self, player_count: int) -> int | None:
        idx = self.player_index()
        if idx is None:
            return None
        if 0 <= idx < int(player_count):
            return int(idx)
        return None

    def creature_index(self) -> int | None:
        if self.kind != OwnerKind.CREATURE:
            return None
        return int(self.index)

    def creature_index_in_bounds(self, creature_count: int) -> int | None:
        idx = self.creature_index()
        if idx is None:
            return None
        if 0 <= idx < int(creature_count):
            return int(idx)
        return None

    def without_run_mod_affinity(self) -> OwnerRef:
        return msgspec.structs.replace(self, no_run_mod_affinity=True)

__all__ = [
    "LOCAL_PLAYER_OWNER_ID",
    "OwnerKind",
    "OwnerRef",
]
