from __future__ import annotations

"""Monster rarity & affixes (rewrite-only, NOT native).

Layers a tiered affix system on top of the survival "rare colour variant" roll in
`build_survival_spawn_creature`. The five native variant rolls are kept byte for
byte (so the RNG stream is unchanged until a variant actually hits); their
outcome now selects a rarity tier and the affixes are rolled afterwards with
synthetic caller ids.

See docs/design/monster-rarity.md. This module ships a curated first slice of the
affix list in that doc; the rest are staged behind the same registry.
"""

import math
from enum import IntEnum

import msgspec

from ..rng_caller_static import RngCallerStatic
from .damage_types import CreatureDamageType

# When False, build_survival_spawn_creature keeps the native colour-variant stat
# overrides instead of this system (used by native-parity replay / spawn tests).
MONSTER_RARITY_ENABLED = True


def rarity_test_bias_enabled() -> bool:
    """--test-mode makes rare tiers common so affixes can be seen quickly."""
    if not MONSTER_RARITY_ENABLED:
        return False
    try:
        from ..test_mode import test_mode_enabled

        return test_mode_enabled()
    except Exception:
        return False

# --- tiers ------------------------------------------------------------------


class MonsterRarity(IntEnum):
    NORMAL = 0
    TAINTED = 1
    MUTATED = 2
    APEX = 3


RARITY_LABEL = {1: "Tainted", 2: "Mutated", 3: "Apex"}

# Outline / blend colour per tier (r, g, b).
RARITY_COLOR = {1: (120, 180, 255), 2: (200, 90, 255), 3: (255, 205, 70)}

_TIER_HP_MULT = {1: 1.5, 2: 2.5, 3: 6.0}
_TIER_HP_FLAT = {1: 0.0, 2: 40.0, 3: 600.0}
_TIER_SIZE_FLAT = {1: 0.0, 2: 10.0, 3: 18.0}
_TIER_REWARD_MULT = {1: 3.0, 2: 8.0, 3: 20.0}
_TIER_AFFIX_COUNT = {1: 1, 2: 3, 3: 5}
_THREAT_REWARD_PER_POINT = 0.12

REGEN_PAUSE_S = 1.5
REGEN_FRAC_PER_S = 0.04
FRENZY_MAX_BONUS = 0.8          # +80% speed / contact at 0 hp
SWIFT_AURA_RANGE = 320.0
SWIFT_AURA_BONUS = 0.30
VOLATILE_RADIUS = 130.0
VOLATILE_DAMAGE = 60.0
HATCHING_COUNT = 3


# --- affix registry --------------------------------------------------------


class AffixId(IntEnum):
    OVERGROWN = 1
    HASTED = 2
    COLOSSAL = 3
    RUNTISH = 4
    GORGED = 5
    ARMORED = 6
    FLAME_WARDED = 7
    INSULATED = 8
    BLAST_PROOF = 9
    SHELLED = 10
    REGENERATING = 11
    FROTHING = 12
    SWIFT_AURA = 13
    DETONATING = 15
    HATCHING = 16
    GOLDEN = 17
    BOUNTIFUL = 18


class AffixSpec(msgspec.Struct, frozen=True):
    id: int
    word: str          # display word: a prefix, or "of X" for suffixes
    suffix: bool
    threat: int
    min_xp: int
    aura: bool = False


_SPECS = (
    AffixSpec(AffixId.OVERGROWN, "Brood-Fed", False, 1, 0),
    AffixSpec(AffixId.HASTED, "Rampant", False, 1, 0),
    AffixSpec(AffixId.COLOSSAL, "Colossal", False, 2, 3000),
    AffixSpec(AffixId.RUNTISH, "Runtish", False, 1, 3000),
    AffixSpec(AffixId.GORGED, "Gorged", False, 2, 6000),
    AffixSpec(AffixId.ARMORED, "of Plating", True, 2, 0),
    AffixSpec(AffixId.FLAME_WARDED, "of Warding", True, 2, 0),
    AffixSpec(AffixId.INSULATED, "of Grounding", True, 2, 0),
    AffixSpec(AffixId.BLAST_PROOF, "of Absorption", True, 2, 0),
    AffixSpec(AffixId.SHELLED, "of the Turtle", True, 3, 9000),
    AffixSpec(AffixId.REGENERATING, "of Recovery", True, 2, 9000),
    AffixSpec(AffixId.FROTHING, "Frothing", False, 3, 9000),
    AffixSpec(AffixId.SWIFT_AURA, "of Swiftness", True, 3, 12000, aura=True),
    AffixSpec(AffixId.DETONATING, "of Detonation", True, 3, 9000),
    AffixSpec(AffixId.HATCHING, "of the Swarm", True, 3, 12000),
    AffixSpec(AffixId.GOLDEN, "of Riches", True, 0, 0),
    AffixSpec(AffixId.BOUNTIFUL, "of Plenty", True, 0, 0),
)

AFFIXES: dict[int, AffixSpec] = {s.id: s for s in _SPECS}


def _eligible(tier: int, xp: int) -> list[int]:
    out: list[int] = []
    for s in _SPECS:
        if xp < s.min_xp:
            continue
        if s.aura and tier < MonsterRarity.APEX:
            continue
        if s.threat > 2 and tier < MonsterRarity.MUTATED:
            continue
        out.append(s.id)
    return out


def roll_affixes(tier: int, xp: int, rng) -> tuple[int, ...]:
    want = _TIER_AFFIX_COUNT.get(int(tier), 0)
    pool = _eligible(int(tier), int(xp))
    chosen: list[int] = []
    have_aura = False
    guard = 0
    while len(chosen) < want and pool and guard < 64:
        guard += 1
        pick = pool[int(rng.rand_tagged(RngCallerStatic.REWRITE_MONSTER_AFFIX_PICK)) % len(pool)]
        if pick in chosen:
            continue
        spec = AFFIXES[pick]
        if spec.aura and have_aura:
            continue
        chosen.append(pick)
        have_aura = have_aura or spec.aura
    return tuple(chosen)


# --- naming --------------------------------------------------------------


def monster_display_name(type_name: str, affixes: tuple[int, ...]) -> str:
    prefix = next((AFFIXES[a].word for a in affixes if not AFFIXES[a].suffix), "")
    suffix = next((AFFIXES[a].word for a in affixes if AFFIXES[a].suffix), "")
    parts = [p for p in (prefix, type_name.capitalize(), suffix) if p]
    return " ".join(parts)


# Short effect text for the hover tooltip (creatures/render).
AFFIX_BLURB: dict[int, str] = {
    AffixId.OVERGROWN: "+60% max health",
    AffixId.HASTED: "+40% move speed",
    AffixId.COLOSSAL: "+40% size, +60% contact damage",
    AffixId.RUNTISH: "small, +70% speed, -25% health",
    AffixId.GORGED: "+120% health, -25% speed",
    AffixId.ARMORED: "-40% bullet & melee damage taken",
    AffixId.FLAME_WARDED: "-60% fire damage taken",
    AffixId.INSULATED: "-60% lightning & energy damage taken",
    AffixId.BLAST_PROOF: "-50% explosion damage taken",
    AffixId.SHELLED: "-45% damage taken from every type",
    AffixId.REGENERATING: "regenerates when not hit",
    AffixId.FROTHING: "speeds up as its health drops",
    AffixId.SWIFT_AURA: "aura: nearby allies +30% speed",
    AffixId.DETONATING: "explodes on death",
    AffixId.HATCHING: "hatches 3 crawlers on death",
    AffixId.GOLDEN: "5x experience",
    AffixId.BOUNTIFUL: "always drops a power-up",
}


def monster_tooltip_lines(type_name: str, rarity: int, affixes: tuple[int, ...]) -> list[str]:
    if not rarity:
        return []
    head = f"{RARITY_LABEL.get(int(rarity), '?')}:  {monster_display_name(type_name, affixes)}"
    lines = [head]
    for a in affixes:
        spec = AFFIXES.get(a)
        if spec is None:
            continue
        blurb = AFFIX_BLURB.get(a, "")
        lines.append(f"{spec.word} - {blurb}" if blurb else spec.word)
    return lines


# --- spawn-time application (operates on a CreatureInit) ----------------


def _resist(init, damage_type: int, mult: float) -> None:
    d = init.damage_taken_mult_by_type
    if d is None:
        d = {}
        init.damage_taken_mult_by_type = d
    d[int(damage_type)] = d.get(int(damage_type), 1.0) * mult


def apply_rarity(init, *, tier: int, player_experience: int, rng) -> None:
    """Mutate a survival CreatureInit: apply tier bump + rolled affixes."""
    tier = int(tier)
    if tier <= 0:
        return
    xp = int(player_experience)

    hp = float(init.health or 1.0)
    hp = hp * _TIER_HP_MULT[tier] + _TIER_HP_FLAT[tier]
    size = float(init.size or 50.0) + _TIER_SIZE_FLAT[tier]
    speed = float(init.move_speed or 1.0)
    contact = float(init.contact_damage or 0.0)

    affixes = roll_affixes(tier, xp, rng)
    reward_mult = _TIER_REWARD_MULT[tier]
    threat = 0
    for aid in affixes:
        spec = AFFIXES[aid]
        threat += spec.threat
        if aid == AffixId.OVERGROWN:
            hp *= 1.6
        elif aid == AffixId.HASTED:
            speed *= 1.4
        elif aid == AffixId.COLOSSAL:
            size *= 1.4
            contact *= 1.6
        elif aid == AffixId.RUNTISH:
            size *= 0.6
            speed *= 1.7
            hp *= 0.75
        elif aid == AffixId.GORGED:
            hp *= 2.2
            speed *= 0.75
        elif aid == AffixId.ARMORED:
            _resist(init, CreatureDamageType.BULLET, 0.6)
            _resist(init, CreatureDamageType.MELEE, 0.6)
        elif aid == AffixId.FLAME_WARDED:
            _resist(init, CreatureDamageType.FIRE, 0.4)
        elif aid == AffixId.INSULATED:
            _resist(init, CreatureDamageType.LIGHTNING, 0.4)
            _resist(init, CreatureDamageType.ENERGY, 0.4)
        elif aid == AffixId.BLAST_PROOF:
            _resist(init, CreatureDamageType.EXPLOSION, 0.5)
        elif aid == AffixId.SHELLED:
            for t in (
                CreatureDamageType.BULLET,
                CreatureDamageType.MELEE,
                CreatureDamageType.EXPLOSION,
                CreatureDamageType.FIRE,
                CreatureDamageType.ION,
                CreatureDamageType.ENERGY,
                CreatureDamageType.LIGHTNING,
            ):
                _resist(init, t, 0.55)
        elif aid == AffixId.GOLDEN:
            reward_mult *= 5.0
        # REGENERATING / FROTHING / SWIFT_AURA / BARBED / DETONATING / HATCHING /
        # BOUNTIFUL are handled at runtime (update_monster_affixes / death path).

    speed = min(speed, 4.5)
    reward = float(init.reward_value or 0.0) * reward_mult * (1.0 + _THREAT_REWARD_PER_POINT * threat)

    init.health = hp
    init.max_health = hp
    init.size = size
    init.move_speed = speed
    init.contact_damage = contact
    init.reward_value = reward
    init.rarity = tier
    init.affixes = affixes

    # Blend the sprite tint toward the tier colour.
    cr, cg, cb = RARITY_COLOR[tier]
    base = init.tint or (1.0, 1.0, 1.0, 1.0)
    br = base[0] if base[0] is not None else 1.0
    bg = base[1] if base[1] is not None else 1.0
    bb = base[2] if base[2] is not None else 1.0
    mix = 0.55
    init.tint = (
        br * (1.0 - mix) + (cr / 255.0) * mix,
        bg * (1.0 - mix) + (cg / 255.0) * mix,
        bb * (1.0 - mix) + (cb / 255.0) * mix,
        1.0,
    )


# --- runtime: per-tick affix update -----------------------------------


def _has(creature, aid: int) -> bool:
    return aid in creature.affixes


def update_monster_affixes(players, creatures, dt: float, *, state) -> None:
    """Advance regen / frenzy / aura affixes. Called from WorldState.step."""
    dt = float(dt)
    if dt <= 0.0:
        return

    entries = list(creatures.entries) if hasattr(creatures, "entries") else list(creatures)
    swift_sources: list[tuple[float, float]] = []
    for c in entries:
        if not c.active or not c.rarity:
            continue
        if c.affix_base_move_speed <= 0.0:
            c.affix_base_move_speed = float(c.move_speed)
            c.affix_base_contact_damage = float(c.contact_damage)
        if _has(c, AffixId.SWIFT_AURA):
            swift_sources.append((float(c.pos.x), float(c.pos.y)))

    for c in entries:
        if not c.active or not c.rarity:
            continue
        if float(c.hp) <= 0.0:
            continue

        speed_mult = 1.0
        contact_mult = 1.0

        if _has(c, AffixId.FROTHING) and float(c.max_hp) > 0.0:
            missing = max(0.0, 1.0 - float(c.hp) / float(c.max_hp))
            speed_mult += FRENZY_MAX_BONUS * missing
            contact_mult += FRENZY_MAX_BONUS * missing

        if swift_sources and not _has(c, AffixId.SWIFT_AURA):
            cx, cy = float(c.pos.x), float(c.pos.y)
            for sx, sy in swift_sources:
                if math.hypot(cx - sx, cy - sy) <= SWIFT_AURA_RANGE:
                    speed_mult += SWIFT_AURA_BONUS
                    break

        c.move_speed = min(4.5, float(c.affix_base_move_speed) * speed_mult)
        c.contact_damage = float(c.affix_base_contact_damage) * contact_mult

        if _has(c, AffixId.REGENERATING):
            if c.affix_regen_pause > 0.0:
                c.affix_regen_pause = max(0.0, float(c.affix_regen_pause) - dt)
            elif float(c.hp) < float(c.max_hp):
                c.hp = min(float(c.max_hp), float(c.hp) + float(c.max_hp) * REGEN_FRAC_PER_S * dt)


# --- runtime: on-hit (called from creatures/damage.py) ---------------


def monster_affix_on_hit(creature, damage_type: int) -> float:
    """Note the hit (regen pause) and return the resist multiplier for it."""
    if AffixId.REGENERATING in creature.affixes:
        creature.affix_regen_pause = REGEN_PAUSE_S
    d = creature.damage_taken_mult_by_type
    if not d:
        return 1.0
    return float(d.get(int(damage_type), 1.0))


# --- runtime: on-death ----------------------------------------------


def apply_monster_death_affixes(
    pool,
    idx: int,
    creature,
    *,
    state,
    players,
    rng,
    detail_preset: int,
    world_width: float,
    world_height: float,
) -> None:
    if not creature.rarity:
        return
    affixes = creature.affixes

    if AffixId.DETONATING in affixes:
        _death_explosion(pool, creature, state=state, players=players, detail_preset=int(detail_preset))

    if AffixId.HATCHING in affixes:
        _death_hatch(pool, creature, rng=rng)

    if AffixId.BOUNTIFUL in affixes and players:
        try:
            state.bonus_pool.spawn_at_pos(
                creature.pos,
                state=state,
                players=players,
                world_width=float(world_width),
                world_height=float(world_height),
            )
        except Exception:
            pass


def _death_explosion(pool, creature, *, state, players, detail_preset: int) -> None:
    from ..player_damage import player_take_damage

    try:
        state.effects.spawn_explosion_burst(
            pos=creature.pos, scale=1.4, rng=state.rng, detail_preset=int(detail_preset),
        )
    except Exception:
        pass

    cx, cy = float(creature.pos.x), float(creature.pos.y)
    for other in pool.entries:
        if not other.active or other is creature or float(other.hp) <= 0.0:
            continue
        if math.hypot(float(other.pos.x) - cx, float(other.pos.y) - cy) <= VOLATILE_RADIUS:
            other.hp = float(other.hp) - VOLATILE_DAMAGE

    for p in players:
        if float(p.health) <= 0.0:
            continue
        if math.hypot(float(p.pos.x) - cx, float(p.pos.y) - cy) <= VOLATILE_RADIUS:
            player_take_damage(state, p, VOLATILE_DAMAGE, players=players)

    try:
        from grim.sfx_map import SfxId

        state.sfx_queue.append(SfxId.EXPLOSION_LARGE)
    except Exception:
        pass


def _death_hatch(pool, creature, *, rng) -> None:
    base_speed = float(creature.affix_base_move_speed) or float(creature.move_speed)
    for i in range(HATCHING_COUNT):
        child_idx = pool._alloc_slot()
        if child_idx is None:
            return
        child = msgspec.structs.replace(creature)
        child.rarity = 0
        child.affixes = ()
        child.damage_taken_mult_by_type = {}
        child.hp = 24.0
        child.max_hp = 24.0
        child.size = 34.0
        child.move_speed = min(4.5, base_speed + 1.2)
        child.contact_damage = 4.0
        child.reward_value = 0.0
        child.affix_base_move_speed = 0.0
        child.affix_base_contact_damage = 0.0
        child.heading = float(creature.heading + (i - 1) * 0.7)
        pool._entries[child_idx] = child
        pool.spawned_count += 1
