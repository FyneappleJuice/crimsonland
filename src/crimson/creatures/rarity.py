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
import random
from enum import IntEnum

import msgspec

from grim.color import RGBA
from grim.geom import Vec2

from ..math_parity import NATIVE_HALF_PI, f32
from ..perks.impl.death_clock import blocks_health_change as _death_clock_blocks_health_change
from .damage_types import CreatureDamageType

# All resistable damage types, for affixes that touch every bucket at once
# (Shelled, Glass).
_ALL_DAMAGE_TYPES: tuple[int, ...] = (
    CreatureDamageType.BULLET,
    CreatureDamageType.MELEE,
    CreatureDamageType.EXPLOSION,
    CreatureDamageType.FIRE,
    CreatureDamageType.ION,
    CreatureDamageType.PLASMA,
    CreatureDamageType.LIGHTNING,
    CreatureDamageType.ENERGY,
)

# Presentation/build-variance roll, not core sim state - a private RNG so it
# never shifts the replay-tracked state.rng stream (see the Tenet Gun /
# crit.py precedent).
_EVASION_RNG = random.Random(0x1D0DE)
# Not native: which affixes a monster rolls is new content with no native
# sequence to match, so it gets its own private stream instead of consuming
# the shared lockstep rng (see docs/design/monster-rarity.md).
_AFFIX_PICK_RNG = random.Random(0xA5717)
EVASIVE_DODGE_CHANCE = 0.35
IRONHIDE_CAP_FRACTION = 0.08
OVERSHIELD_HIT_COUNT = 3
FRAG_DEATH_COUNT = 8

# When False, build_survival_spawn_creature keeps the native colour-variant stat
# overrides instead of this system (used by native-parity replay / spawn tests).
MONSTER_RARITY_ENABLED = True

# --- tiers ------------------------------------------------------------------


class MonsterRarity(IntEnum):
    NORMAL = 0
    TAINTED = 1
    MUTATED = 2
    APEX = 3


RARITY_LABEL = {1: "Tainted", 2: "Mutated", 3: "Apex"}

# Outline / blend colour per tier (r, g, b).
RARITY_COLOR = {1: (120, 180, 255), 2: (200, 90, 255), 3: (255, 205, 70)}

# Warning tint for any monster carrying an on-death affix, overriding the tier
# colour below (r, g, b).
DEATH_AFFIX_COLOR = (230, 30, 30)

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
# Not native: Bomber (Detonating) affix - the blast is nerfed from the old
# flat VOLATILE_DAMAGE and no longer lands the instant the creature dies; it
# fuses for BOMBER_FUSE_DELAY_S first (see PendingMonsterDetonation /
# _queue_detonation / _tick_pending_detonations below) with a warning ring
# drawn by render/world/draw.py's draw_pending_detonation_warnings.
BOMBER_DAMAGE_MULT = 0.6
BOMBER_FUSE_DELAY_S = 0.75

TICK_RANGE = 100.0
TICK_FRAC_PER_S = 0.05
LUNGE_INTERVAL_S = 3.0
LUNGE_DURATION_S = 0.4
LUNGE_SPEED_BONUS = 3.0        # +300% -> 4x total during the dash window
LUNGE_CONTACT_BONUS = 1.0      # +100% -> 2x total during the dash window
ACID_LOB_INTERVAL_S = 2.0
# Not native: Acid Lob affix deals no direct hit damage (see the
# ACID_LOB-specific branch in projectiles/runtime/projectile_pool.py's
# step()) - instead it queues this damage as a drip over
# ACID_LOB_DOT_DURATION_S, the inverse of the Leech relic's heal-over-time
# instance (meta/relics_impl/leech.py).
ACID_LOB_DOT_TOTAL_DAMAGE = 18.0
ACID_LOB_DOT_DURATION_S = 4.0
FEASTING_HEAL_FRACTION = 0.3

# --- new modifier tunables (all not native) --------------------------------

WARDING_GROUND_RANGE = 160.0
WARDING_GROUND_MULT = 0.75          # -25% damage taken by nearby allies

VANGUARD_AURA_RANGE = 250.0
VANGUARD_AURA_MULT = 0.70           # -30% damage taken by nearby allies

COMMAND_AURA_RANGE = 300.0
COMMAND_AURA_CONTACT_BONUS = 0.30   # +30% contact damage for nearby allies

CHOIR_AURA_RANGE = 250.0
CHOIR_AURA_HEAL_FRAC_PER_S = 0.03   # nearby allies regen 3% max HP/s

GROWTH_TRIGGER_RANGE = 300.0
GROWTH_SIZE_BONUS_PER_STACK = 0.10
GROWTH_HP_BONUS_PER_STACK = 0.20

DREAD_AURA_RANGE = 350.0
DREAD_SPREAD_HEAT_RATE = 0.35       # extra spread_heat/s applied to a player in range

STATIC_AURA_RANGE = 250.0
STATIC_JAM_EXTRA_RATE = 0.43        # extends an in-progress reload by this much per second

GLUTTONY_AURA_RANGE = 300.0
GLUTTONY_EXTRA_DECAY_MULT = 2.0     # active power-up timers drain at 3x (1 + this) while in range

PYRE_FUSE_DELAY_S = 0.6
PYRE_RADIUS = 90.0
PYRE_DURATION_S = 4.0
PYRE_DAMAGE_PER_S = 22.0

SOUL_STACK_RANGE = 250.0
SOUL_DAMAGE_PER_STACK = 0.05
SOUL_SIZE_PER_STACK = 0.03

VORTEX_RANGE = 300.0
VORTEX_PULL_FRAC_PER_S = 0.15

ANCHORING_FUSE_DELAY_S = 0.4
ANCHORING_RADIUS = 200.0
ANCHORING_DURATION_S = 2.0
ANCHORING_PULL_FRAC_PER_S = 0.5

PHALANX_RANGE = 150.0
PHALANX_REDUCTION_PER_ALLY = 0.10
PHALANX_MAX_ALLIES = 3               # caps the stack at -30% (a squad of 4)

ENDURANCE_WINDOW_S = 1.0
ENDURANCE_CAP_DAMAGE = 1.0            # first hit each window is capped to this

FLICKER_INTERVAL_S = 5.0
FLICKER_DURATION_S = 1.0
FLICKER_TELEGRAPH_S = 0.4             # shimmer window right before it phases

SECOND_WIND_HEAL_FRACTION = 0.30
SECOND_WIND_HEAL_DURATION_S = 2.0

INEVITABILITY_INTERVAL_S = 20.0

OBSCURITY_RANGE = 250.0

CAMOUFLAGE_RANGE = 250.0             # full blend at/beyond this distance

# Shelled (of the Turtle): upgraded from a flat resist to the doc's
# directional "must be flanked" version - a front-facing 120 degree cone
# takes -75%, everything else takes normal damage.
TURTLE_FRONT_HALF_ANGLE_RAD = math.radians(60.0)
TURTLE_FRONT_RESIST_MULT = 0.25


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
    BOUNTIFUL = 18
    GLASS_FRAME = 19
    FERALIZATION = 20
    IRONHIDE = 21
    EVASIVE = 22
    OVERSHIELD = 23
    FRAG_DEATH = 24
    TICK_BLOODHUNGRY = 26
    LUNGING = 28
    ACID_LOB = 29
    FEASTING = 30
    WARDING_GROUND = 31
    CAMOUFLAGED = 32
    FLICKERING = 33
    SECOND_WIND = 34
    INEVITABILITY = 35
    OBSCURITY = 36
    COMMAND = 37
    VANGUARD = 38
    GROWTH = 39
    CHOIR = 40
    DREAD = 41
    STATIC = 42
    GLUTTONY = 43
    PYRE = 44
    SOULS = 45
    VORTEX = 46
    ANCHORING = 47
    PHALANX = 48
    ENDURANCE = 49


class AffixSpec(msgspec.Struct, frozen=True):
    id: int
    word: str          # flavour word woven into the generated name
    label: str         # mechanical modifier name (shown in the hover tooltip)
    threat: int
    min_xp: int
    aura: bool = False


# Not native: modifiers used to be split into "prefix" (the monster *does*
# something) and "suffix" (how it resists/reacts/dies) pools, each capped to
# one per monster. That mechanical split is gone now - every entry below is
# just a modifier, and `roll_affixes` below picks freely from one shared pool
# (still respecting tier affix-count / threat gating / the one-aura cap).
# `monster_display_name` still uses each `word`'s own text to decide whether
# it reads before or after the type name, but that's cosmetic only now.
_SPECS = (
    AffixSpec(AffixId.OVERGROWN, "Brood-Fed", "Overgrown", 1, 0),
    AffixSpec(AffixId.HASTED, "Rampant", "Hasted", 1, 0),
    AffixSpec(AffixId.COLOSSAL, "Colossal", "Oversized", 2, 3000),
    AffixSpec(AffixId.RUNTISH, "Runtish", "Undersized", 1, 3000),
    AffixSpec(AffixId.GORGED, "Gorged", "Heavy", 2, 6000),
    AffixSpec(AffixId.ARMORED, "of Plating", "Armored", 2, 0),
    AffixSpec(AffixId.FLAME_WARDED, "of Warding", "Flame-Warded", 2, 0),
    AffixSpec(AffixId.INSULATED, "of Grounding", "Insulated", 2, 0),
    AffixSpec(AffixId.BLAST_PROOF, "of Absorption", "Blast-Proof", 2, 0),
    AffixSpec(AffixId.SHELLED, "of the Turtle", "Shelled", 3, 9000),
    AffixSpec(AffixId.REGENERATING, "of Recovery", "Regenerating", 2, 9000),
    AffixSpec(AffixId.FROTHING, "Frothing", "Berserker", 3, 9000),
    AffixSpec(AffixId.SWIFT_AURA, "of Swiftness", "Haste Aura", 3, 12000, aura=True),
    AffixSpec(AffixId.DETONATING, "of Detonation", "Bomber", 3, 9000),
    AffixSpec(AffixId.HATCHING, "of the Swarm", "Hatch Death", 3, 12000),
    AffixSpec(AffixId.BOUNTIFUL, "of Plenty", "Bountiful", 0, 0),
    AffixSpec(AffixId.GLASS_FRAME, "of Glass", "Volatile Frame", 2, 6000),
    AffixSpec(AffixId.FERALIZATION, "of Feralization", "Rabid", 3, 12000),
    AffixSpec(AffixId.IRONHIDE, "Ironhide", "Bulwark", 3, 12000),
    AffixSpec(AffixId.EVASIVE, "of Deflection", "Evasive", 2, 6000),
    AffixSpec(AffixId.OVERSHIELD, "of the Barrier", "Overshield", 2, 12000),
    AffixSpec(AffixId.FRAG_DEATH, "of Splintering", "Frag Death", 2, 10000),
    AffixSpec(AffixId.TICK_BLOODHUNGRY, "of the Tick", "Bloodhungry", 2, 13000),
    AffixSpec(AffixId.LUNGING, "Lunging", "Charger", 3, 5000),
    AffixSpec(AffixId.ACID_LOB, "Spitting", "Acid Lob", 2, 5000),
    AffixSpec(AffixId.FEASTING, "of Feasting", "Life Thief", 2, 13000),
    AffixSpec(AffixId.WARDING_GROUND, "Warding Ground", "Ally Shield", 2, 8000),
    AffixSpec(AffixId.CAMOUFLAGED, "Camouflaged", "Chameleon", 1, 4000),
    AffixSpec(AffixId.FLICKERING, "of Flickering", "Phasing", 3, 16000),
    AffixSpec(AffixId.SECOND_WIND, "of the Second Wind", "Undying", 3, 16000),
    AffixSpec(AffixId.INEVITABILITY, "of Inevitability", "Timed", 4, 20000),
    AffixSpec(AffixId.OBSCURITY, "of Obscurity", "Veiled", 2, 13000),
    AffixSpec(AffixId.COMMAND, "of Command", "Warlord Aura", 3, 15000, aura=True),
    AffixSpec(AffixId.VANGUARD, "of the Vanguard", "Guardian Aura", 3, 16000, aura=True),
    AffixSpec(AffixId.GROWTH, "of Growth", "Empower Aura", 3, 18000, aura=True),
    AffixSpec(AffixId.CHOIR, "of the Choir", "Regen Aura", 3, 16000, aura=True),
    AffixSpec(AffixId.DREAD, "of Dread", "Terror Aura", 3, 14000, aura=True),
    AffixSpec(AffixId.STATIC, "of Static", "Jam Aura", 3, 16000, aura=True),
    AffixSpec(AffixId.GLUTTONY, "of Gluttony", "Null Aura", 4, 18000, aura=True),
    AffixSpec(AffixId.PYRE, "of the Pyre", "Cinderburst", 2, 10000),
    AffixSpec(AffixId.SOULS, "of Souls", "Soul Eater", 4, 17000),
    AffixSpec(AffixId.VORTEX, "of the Vortex", "Gravity Well", 3, 13000),
    AffixSpec(AffixId.ANCHORING, "of Anchoring", "Gravemark", 2, 13000),
    AffixSpec(AffixId.PHALANX, "of the Phalanx", "Linked", 2, 11000),
    AffixSpec(AffixId.ENDURANCE, "of Endurance", "Stalwart", 3, 14000),
)

AFFIXES: dict[int, AffixSpec] = {s.id: s for s in _SPECS}

# Affixes that trigger something at the moment of death (apply_monster_death_affixes
# below). A monster carrying any of these tints DEATH_AFFIX_COLOR instead of its
# tier colour - a "this one does something when it dies" warning independent
# of rarity tier.
DEATH_AFFIX_IDS: frozenset[int] = frozenset(
    {
        AffixId.DETONATING,
        AffixId.HATCHING,
        AffixId.BOUNTIFUL,
        AffixId.FRAG_DEATH,
        AffixId.PYRE,
        AffixId.ANCHORING,
    }
)

# Not native: affixes whose only mechanical effect is a static stat bump
# applied once at spawn (in apply_rarity's per-affix loop below, which writes
# onto a CreatureInit-shaped object) rather than something read live off
# `creature.affixes` every tick/hit. Inevitability's re-roll (below) grants a
# fresh affix onto an already-materialized CreatureState - it can't re-run
# that spawn-time loop (different field names, no CreatureInit to write to),
# so it draws only from affixes outside this set.
_STATIC_STAT_ONLY_AFFIX_IDS: frozenset[int] = frozenset(
    {
        AffixId.OVERGROWN,
        AffixId.HASTED,
        AffixId.COLOSSAL,
        AffixId.RUNTISH,
        AffixId.GORGED,
        AffixId.FERALIZATION,
        AffixId.GLASS_FRAME,
    }
)


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


def roll_affixes(tier: int, xp: int) -> tuple[int, ...]:
    want = _TIER_AFFIX_COUNT.get(int(tier), 0)
    pool = _eligible(int(tier), int(xp))
    chosen: list[int] = []
    have_aura = False
    guard = 0
    while len(chosen) < want and pool and guard < 64:
        guard += 1
        pick = _AFFIX_PICK_RNG.choice(pool)
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
    """Not native: with the prefix/suffix mechanical split gone, word
    placement is now a pure text heuristic - a word already written as
    "of X" reads after the type name, everything else reads before it. No cap
    on how many of each show: an Apex with 5 modifiers just gets a long name."""
    before: list[str] = []
    after: list[str] = []
    for a in affixes:
        spec = AFFIXES.get(a)
        if spec is None:
            continue
        if spec.word.startswith("of "):
            after.append(spec.word)
        else:
            before.append(spec.word)
    parts = [*before, type_name.capitalize(), *after]
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
    AffixId.BOUNTIFUL: "always drops a power-up",
    AffixId.GLASS_FRAME: "+40% damage taken, +60% move speed",
    AffixId.FERALIZATION: "3x experience, +150% speed, +100% contact damage",
    AffixId.IRONHIDE: "no single hit deals more than 8% of its max health",
    AffixId.EVASIVE: "35% chance to fully dodge a bullet",
    AffixId.OVERSHIELD: "shields the first 3 hits it takes",
    AffixId.FRAG_DEATH: "fires a ring of shrapnel on death",
    AffixId.TICK_BLOODHUNGRY: "heals while close to a player",
    AffixId.LUNGING: "periodically dashes at 4x speed and 2x contact damage",
    AffixId.ACID_LOB: "periodically lobs a projectile at a player",
    AffixId.FEASTING: "heals from the contact damage it deals",
    AffixId.WARDING_GROUND: "nearby allies take 25% less damage",
    AffixId.CAMOUFLAGED: "blends in at range, clear up close",
    AffixId.FLICKERING: "briefly invulnerable every few seconds (shimmers first)",
    AffixId.SECOND_WIND: "survives a lethal hit at 1 HP once, then heals",
    AffixId.INEVITABILITY: "fully heals and gains a modifier if it survives long enough",
    AffixId.OBSCURITY: "invisible at range unless close, hit, or Monster Vision is active",
    AffixId.COMMAND: "aura: nearby allies +30% contact damage",
    AffixId.VANGUARD: "aura: nearby allies take 30% less damage",
    AffixId.GROWTH: "every nearby ally death permanently grows it",
    AffixId.CHOIR: "aura: nearby allies regen 3% max health/s",
    AffixId.DREAD: "aura: your weapon spread creeps up while close",
    AffixId.STATIC: "aura: your reload drags out while close",
    AffixId.GLUTTONY: "aura: your power-ups burn out 3x faster while close",
    AffixId.PYRE: "leaves a burning field on death (delayed)",
    AffixId.SOULS: "every nearby ally death permanently strengthens it",
    AffixId.VORTEX: "constantly pulls you toward it",
    AffixId.ANCHORING: "leaves a pulling zone on death (delayed)",
    AffixId.PHALANX: "takes less damage for every linked ally nearby",
    AffixId.ENDURANCE: "the first hit each second is capped to 1 damage",
}


def monster_tooltip_lines(type_name: str, rarity: int, affixes: tuple[int, ...]) -> list[str]:
    if not rarity:
        return []
    lines = [RARITY_LABEL.get(int(rarity), "?")]
    for a in affixes:
        spec = AFFIXES.get(a)
        if spec is None:
            continue
        blurb = AFFIX_BLURB.get(a, "")
        lines.append(f"{spec.label} - {blurb}" if blurb else spec.label)
    return lines


# --- spawn-time application (operates on a CreatureInit) ----------------


def _resist(init, damage_type: int, mult: float) -> None:
    d = init.damage_taken_mult_by_type
    if d is None:
        d = {}
        init.damage_taken_mult_by_type = d
    d[int(damage_type)] = d.get(int(damage_type), 1.0) * mult


def apply_rarity(init, *, tier: int, player_experience: int) -> None:
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

    affixes = roll_affixes(tier, xp)
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
            _resist(init, CreatureDamageType.PLASMA, 0.4)
        elif aid == AffixId.BLAST_PROOF:
            _resist(init, CreatureDamageType.EXPLOSION, 0.5)
        # SHELLED (of the Turtle) is directional now - handled per-hit in
        # monster_affix_on_hit using the hit's impulse angle, not a flat
        # spawn-time resist.
        elif aid == AffixId.GLASS_FRAME:
            for t in _ALL_DAMAGE_TYPES:
                _resist(init, t, 1.4)
            speed *= 1.6
        elif aid == AffixId.FERALIZATION:
            reward_mult *= 3.0
            speed *= 2.5
            contact *= 2.0
        # Everything else (REGENERATING / FROTHING / SWIFT_AURA / DETONATING /
        # HATCHING / BOUNTIFUL / IRONHIDE / EVASIVE / OVERSHIELD / FRAG_DEATH /
        # TICK_BLOODHUNGRY / LUNGING / ACID_LOB / FEASTING / SHELLED /
        # WARDING_GROUND / CAMOUFLAGED / FLICKERING / SECOND_WIND /
        # INEVITABILITY / OBSCURITY / COMMAND / VANGUARD / GROWTH / CHOIR /
        # DREAD / STATIC / GLUTTONY / PYRE / SOULS / VORTEX / ANCHORING /
        # PHALANX / ENDURANCE) is handled at runtime (update_monster_affixes /
        # monster_affix_on_hit / death path / contact path / rendering).

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

    # Blend the sprite tint toward the tier colour - unless it rolled an
    # on-death affix, in which case red overrides the tier colour entirely.
    if any(a in DEATH_AFFIX_IDS for a in affixes):
        cr, cg, cb = DEATH_AFFIX_COLOR
    else:
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


def _nearest_player(pos, players):
    best = None
    best_dist = math.inf
    for p in players:
        if float(p.health) <= 0.0:
            continue
        d = math.hypot(float(p.pos.x) - float(pos.x), float(p.pos.y) - float(pos.y))
        if d < best_dist:
            best_dist = d
            best = p
    return best


def _fire_acid_lob(state, creature, target, idx: int) -> None:
    from ..owner_ref import OwnerRef
    from ..projectiles.types import ProjectileTemplateId

    # Movement in this codebase's projectile pool always reads `angle - HALF_PI`
    # as the actual travel direction (see projectile_pool.py's step(), and
    # creature_update_all's own `creature.heading` convention) - a raw
    # atan2(dy, dx) is off by 90 degrees unless HALF_PI is added back in. This
    # was the "fires weird, not towards the player" bug.
    angle = math.atan2(
        float(target.pos.y) - float(creature.pos.y),
        float(target.pos.x) - float(creature.pos.x),
    ) + NATIVE_HALF_PI
    try:
        state.projectiles.spawn(
            pos=creature.pos,
            angle=angle,
            type_id=ProjectileTemplateId.ACID_LOB,
            owner=OwnerRef.from_creature(idx),
            hits_players=True,
        )
    except Exception:
        pass


def queue_acid_dot(player, total_damage: float) -> None:
    """Acid Lob affix (not native): queue a damage-over-time instance on the
    struck player instead of a direct hit - the inverse of Leech's heal-over-
    time instance (meta/relics_impl/leech.py), same independent-instance
    shape (its own total, its own timer, never pooled with another instance).
    Called from projectiles/runtime/projectile_pool.py's step() on an Acid
    Lob hit."""
    total_damage = float(total_damage)
    if total_damage <= 0.0:
        return
    player.acid_dot_pending_damage.append(total_damage)
    player.acid_dot_pending_timers.append(ACID_LOB_DOT_DURATION_S)


def tick_acid_dot(player, dt: float) -> None:
    """Drip every active Acid Lob DoT instance's share of its total damage for
    this tick, and drop instances once their timer runs out. Called
    unconditionally every tick, mirroring relic_leech.tick's own shape."""
    if not player.acid_dot_pending_timers:
        return
    if _death_clock_blocks_health_change(player):
        return
    dt = float(dt)
    kept_damage: list[float] = []
    kept_timers: list[float] = []
    for total_damage, remaining in zip(player.acid_dot_pending_damage, player.acid_dot_pending_timers):
        tick_damage = float(total_damage) * dt / ACID_LOB_DOT_DURATION_S
        player.health = max(0.0, float(f32(float(player.health) - tick_damage)))
        remaining -= dt
        if remaining > 0.0:
            kept_damage.append(total_damage)
            kept_timers.append(remaining)
    player.acid_dot_pending_damage = kept_damage
    player.acid_dot_pending_timers = kept_timers


def update_monster_affixes(players, creatures, dt: float, *, state) -> None:
    """Advance regen / frenzy / aura affixes. Called from WorldState.step."""
    dt = float(dt)
    if dt <= 0.0:
        return

    entries = list(creatures.entries) if hasattr(creatures, "entries") else list(creatures)
    swift_sources: list[tuple[float, float]] = []
    command_sources: list[tuple[float, float]] = []
    choir_sources: list[tuple[float, float]] = []
    warding_sources: list[tuple[float, float, float]] = []  # x, y, mult
    phalanx_sources: list[tuple[int, float, float]] = []  # entry index, x, y
    for i, c in enumerate(entries):
        if not c.active or not c.rarity:
            continue
        if c.affix_base_move_speed <= 0.0:
            c.affix_base_move_speed = float(c.move_speed)
            c.affix_base_contact_damage = float(c.contact_damage)
        if c.affix_base_size <= 0.0:
            c.affix_base_size = float(c.size)
        cx, cy = float(c.pos.x), float(c.pos.y)
        if _has(c, AffixId.SWIFT_AURA):
            swift_sources.append((cx, cy))
        if _has(c, AffixId.COMMAND):
            command_sources.append((cx, cy))
        if _has(c, AffixId.CHOIR):
            choir_sources.append((cx, cy))
        if _has(c, AffixId.WARDING_GROUND):
            warding_sources.append((cx, cy, WARDING_GROUND_MULT))
        if _has(c, AffixId.VANGUARD):
            warding_sources.append((cx, cy, VANGUARD_AURA_MULT))
        if _has(c, AffixId.PHALANX):
            phalanx_sources.append((i, cx, cy))

    for idx, c in enumerate(entries):
        if not c.active or not c.rarity:
            continue
        if float(c.hp) <= 0.0:
            continue

        speed_mult = 1.0
        contact_mult = 1.0
        cx, cy = float(c.pos.x), float(c.pos.y)

        if _has(c, AffixId.FROTHING) and float(c.max_hp) > 0.0:
            missing = max(0.0, 1.0 - float(c.hp) / float(c.max_hp))
            speed_mult += FRENZY_MAX_BONUS * missing
            contact_mult += FRENZY_MAX_BONUS * missing

        if swift_sources and not _has(c, AffixId.SWIFT_AURA):
            for sx, sy in swift_sources:
                if math.hypot(cx - sx, cy - sy) <= SWIFT_AURA_RANGE:
                    speed_mult += SWIFT_AURA_BONUS
                    break

        if command_sources and not _has(c, AffixId.COMMAND):
            for sx, sy in command_sources:
                if math.hypot(cx - sx, cy - sy) <= COMMAND_AURA_RANGE:
                    contact_mult += COMMAND_AURA_CONTACT_BONUS
                    break

        if _has(c, AffixId.LUNGING):
            if c.affix_lunge_active > 0.0:
                c.affix_lunge_active = max(0.0, float(c.affix_lunge_active) - dt)
                speed_mult += LUNGE_SPEED_BONUS
                contact_mult += LUNGE_CONTACT_BONUS
            else:
                c.affix_lunge_timer = float(c.affix_lunge_timer) - dt
                if c.affix_lunge_timer <= 0.0:
                    c.affix_lunge_timer = LUNGE_INTERVAL_S
                    c.affix_lunge_active = LUNGE_DURATION_S

        # Not native: Growth aura / Soul Eater - permanent per-stack size (and,
        # for Soul Eater, contact damage) scaling recomputed fresh each tick
        # from a stable baseline, same shape as move_speed/contact_damage
        # above. Growth's HP bonus can't work this way (max_hp is mutable
        # state, not something to reset to a baseline every tick without
        # erasing damage already taken) - it's applied once, directly, at the
        # moment a stack is gained (see the death-broadcast code below).
        contact_mult *= 1.0 + SOUL_DAMAGE_PER_STACK * int(c.affix_soul_stacks)
        size_scale = (
            1.0
            + GROWTH_SIZE_BONUS_PER_STACK * int(c.affix_growth_stacks)
            + SOUL_SIZE_PER_STACK * int(c.affix_soul_stacks)
        )
        if float(c.affix_base_size) > 0.0:
            c.size = float(c.affix_base_size) * size_scale

        c.move_speed = min(4.5, float(c.affix_base_move_speed) * speed_mult)
        c.contact_damage = float(c.affix_base_contact_damage) * contact_mult

        if _has(c, AffixId.REGENERATING):
            if c.affix_regen_pause > 0.0:
                c.affix_regen_pause = max(0.0, float(c.affix_regen_pause) - dt)
            elif float(c.hp) < float(c.max_hp):
                c.hp = min(float(c.max_hp), float(c.hp) + float(c.max_hp) * REGEN_FRAC_PER_S * dt)

        if choir_sources and not _has(c, AffixId.CHOIR) and float(c.max_hp) > 0.0 and float(c.hp) < float(c.max_hp):
            for sx, sy in choir_sources:
                if math.hypot(cx - sx, cy - sy) <= CHOIR_AURA_RANGE:
                    c.hp = min(float(c.max_hp), float(c.hp) + float(c.max_hp) * CHOIR_AURA_HEAL_FRAC_PER_S * dt)
                    break

        if (
            _has(c, AffixId.TICK_BLOODHUNGRY)
            and players
            and float(c.max_hp) > 0.0
            and float(c.hp) < float(c.max_hp)
        ):
            for p in players:
                if float(p.health) <= 0.0:
                    continue
                if math.hypot(cx - float(p.pos.x), cy - float(p.pos.y)) <= TICK_RANGE:
                    c.hp = min(float(c.max_hp), float(c.hp) + float(c.max_hp) * TICK_FRAC_PER_S * dt)
                    break

        if _has(c, AffixId.ACID_LOB) and players:
            c.affix_lob_timer = float(c.affix_lob_timer) - dt
            if c.affix_lob_timer <= 0.0:
                c.affix_lob_timer = ACID_LOB_INTERVAL_S
                target = _nearest_player(c.pos, players)
                if target is not None:
                    _fire_acid_lob(state, c, target, idx)

        # Not native: Warding Ground / Vanguard aura / Phalanx - precompute the
        # combined "damage taken" multiplier from every nearby ally source, for
        # monster_affix_on_hit to just read at hit time.
        incoming_mult = 1.0
        for sx, sy, source_mult in warding_sources:
            if math.hypot(cx - sx, cy - sy) <= max(WARDING_GROUND_RANGE, VANGUARD_AURA_RANGE):
                incoming_mult *= source_mult
        if _has(c, AffixId.PHALANX) and phalanx_sources:
            nearby_allies = 0
            for other_idx, sx, sy in phalanx_sources:
                if other_idx == idx:
                    continue
                if math.hypot(cx - sx, cy - sy) <= PHALANX_RANGE:
                    nearby_allies += 1
                    if nearby_allies >= PHALANX_MAX_ALLIES:
                        break
            incoming_mult *= 1.0 - PHALANX_REDUCTION_PER_ALLY * nearby_allies
        c.affix_incoming_damage_mult = incoming_mult

        # Not native: Flickering (Phasing) - counts down to its next invuln
        # window; the last FLICKER_TELEGRAPH_S seconds of the countdown are the
        # shimmer warning (read by the renderer straight off the timer).
        if _has(c, AffixId.FLICKERING):
            if c.affix_flicker_active > 0.0:
                c.affix_flicker_active = max(0.0, float(c.affix_flicker_active) - dt)
                if c.affix_flicker_active <= 0.0:
                    c.affix_flicker_timer = FLICKER_INTERVAL_S
            else:
                c.affix_flicker_timer = float(c.affix_flicker_timer) - dt
                if c.affix_flicker_timer <= 0.0:
                    c.affix_flicker_active = FLICKER_DURATION_S

        # Not native: Second Wind (Undying) - drips its one-time post-save heal.
        if c.affix_second_wind_heal_timer > 0.0:
            heal_this_tick = float(c.affix_second_wind_heal_remaining) * dt / max(
                1e-6, float(c.affix_second_wind_heal_timer),
            )
            c.hp = min(float(c.max_hp), float(c.hp) + heal_this_tick)
            c.affix_second_wind_heal_remaining = max(0.0, float(c.affix_second_wind_heal_remaining) - heal_this_tick)
            c.affix_second_wind_heal_timer = max(0.0, float(c.affix_second_wind_heal_timer) - dt)

        # Not native: Inevitability (Timed) - full heal + a fresh modifier if
        # it survives the whole window; repeats for as long as it lives.
        if _has(c, AffixId.INEVITABILITY):
            c.affix_inevitability_timer = float(c.affix_inevitability_timer) - dt
            if c.affix_inevitability_timer <= 0.0:
                c.affix_inevitability_timer = INEVITABILITY_INTERVAL_S
                c.hp = float(c.max_hp)
                xp = int(players[0].experience) if players else 0
                pool = [
                    a
                    for a in _eligible(int(c.rarity), xp)
                    if a not in c.affixes and a not in _STATIC_STAT_ONLY_AFFIX_IDS
                ]
                if pool:
                    c.affixes = (*c.affixes, _AFFIX_PICK_RNG.choice(pool))

        # Not native: Endurance (Stalwart) window - just counts down here;
        # the actual damage cap is applied in monster_affix_on_hit.
        if c.affix_endurance_window > 0.0:
            c.affix_endurance_window = max(0.0, float(c.affix_endurance_window) - dt)

        if players:
            for p in players:
                if float(p.health) <= 0.0:
                    continue
                px, py = float(p.pos.x), float(p.pos.y)
                if _has(c, AffixId.VORTEX) and math.hypot(px - cx, py - cy) <= VORTEX_RANGE:
                    frac = min(1.0, VORTEX_PULL_FRAC_PER_S * dt)
                    p.pos = Vec2(px + (cx - px) * frac, py + (cy - py) * frac)
                if _has(c, AffixId.DREAD) and math.hypot(px - cx, py - cy) <= DREAD_AURA_RANGE:
                    p.spread_heat = min(f32(0.48), float(p.spread_heat) + DREAD_SPREAD_HEAT_RATE * dt)
                if (
                    _has(c, AffixId.STATIC)
                    and float(p.weapon.reload_timer) > 0.0
                    and math.hypot(px - cx, py - cy) <= STATIC_AURA_RANGE
                ):
                    p.weapon.reload_timer = float(p.weapon.reload_timer) + STATIC_JAM_EXTRA_RATE * dt
                if _has(c, AffixId.GLUTTONY) and math.hypot(px - cx, py - cy) <= GLUTTONY_AURA_RANGE:
                    extra = GLUTTONY_EXTRA_DECAY_MULT * dt
                    if state.bonuses.weapon_power_up > 0.0:
                        state.bonuses.weapon_power_up = max(0.0, float(state.bonuses.weapon_power_up) - extra)
                    if state.bonuses.reflex_boost > 0.0:
                        state.bonuses.reflex_boost = max(0.0, float(state.bonuses.reflex_boost) - extra)
                    if state.bonuses.energizer > 0.0:
                        state.bonuses.energizer = max(0.0, float(state.bonuses.energizer) - extra)
                    if state.bonuses.double_experience > 0.0:
                        state.bonuses.double_experience = max(0.0, float(state.bonuses.double_experience) - extra)
                    if state.bonuses.freeze > 0.0:
                        state.bonuses.freeze = max(0.0, float(state.bonuses.freeze) - extra)

    _tick_pending_detonations(players, creatures, dt, state=state)
    _tick_pending_area_effects(players, dt, state=state)


# --- runtime: on-hit (called from creatures/damage.py) ---------------


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % math.tau - math.pi


def monster_affix_on_hit(creature, damage_type: int, damage_amount: float = 0.0, *, impulse=None) -> float:
    """Note the hit (regen pause) and return the combined resist multiplier for it.

    `impulse`: the hit's knockback vector (Vec2-like, optional) - only needed
    for Shelled's directional flank check below. Callers that can't supply it
    (a DoT tick with no originating projectile) just skip that check."""
    if AffixId.REGENERATING in creature.affixes:
        creature.affix_regen_pause = REGEN_PAUSE_S

    # Not native: Flickering (Phasing) - fully invulnerable during its window.
    if AffixId.FLICKERING in creature.affixes and float(creature.affix_flicker_active) > 0.0:
        return 0.0

    mult = 1.0
    d = creature.damage_taken_mult_by_type
    if d:
        mult *= float(d.get(int(damage_type), 1.0))

    # Not native: Warding Ground / Vanguard aura / Phalanx - precomputed once
    # per tick in update_monster_affixes.
    mult *= float(getattr(creature, "affix_incoming_damage_mult", 1.0))

    # Not native: Shelled (of the Turtle), upgraded to the doc's directional
    # version - a hit landing through its front 120 degree cone (roughly
    # "where it's facing", which is usually toward whoever it's chasing) is
    # heavily resisted; anything else (flanked or from behind) is not.
    if AffixId.SHELLED in creature.affixes and impulse is not None:
        ix, iy = float(impulse.x), float(impulse.y)
        if ix != 0.0 or iy != 0.0:
            # impulse points away from the shooter (it's the hit's knockback
            # direction), so the shooter's bearing from the creature is the
            # opposite of that.
            angle_to_shooter = math.atan2(-iy, -ix)
            front_angle = float(creature.heading) - NATIVE_HALF_PI
            if abs(_wrap_angle(angle_to_shooter - front_angle)) <= TURTLE_FRONT_HALF_ANGLE_RAD:
                mult *= TURTLE_FRONT_RESIST_MULT

    if AffixId.OVERSHIELD in creature.affixes:
        if creature.affix_shield_hits < 0:
            creature.affix_shield_hits = OVERSHIELD_HIT_COUNT
        if creature.affix_shield_hits > 0:
            creature.affix_shield_hits -= 1
            return 0.0

    if AffixId.EVASIVE in creature.affixes and int(damage_type) == int(CreatureDamageType.BULLET):
        if _EVASION_RNG.random() < EVASIVE_DODGE_CHANCE:
            return 0.0

    if AffixId.IRONHIDE in creature.affixes and float(creature.max_hp) > 0.0 and damage_amount > 0.0:
        cap = float(creature.max_hp) * IRONHIDE_CAP_FRACTION
        effective = float(damage_amount) * mult
        if effective > cap:
            mult = cap / float(damage_amount)

    # Not native: Endurance (Stalwart) - the first hit each ENDURANCE_WINDOW_S
    # window is capped to ENDURANCE_CAP_DAMAGE; every other hit that window is
    # untouched by this (throttles rapid-fire weapons without nerfing slow ones).
    if AffixId.ENDURANCE in creature.affixes and damage_amount > 0.0 and float(creature.affix_endurance_window) <= 0.0:
        effective = float(damage_amount) * mult
        if effective > ENDURANCE_CAP_DAMAGE:
            mult = ENDURANCE_CAP_DAMAGE / float(damage_amount)
        creature.affix_endurance_window = ENDURANCE_WINDOW_S

    # Not native: Second Wind (Undying) - the first hit that would otherwise
    # be lethal instead leaves it at 1 HP and starts a heal-over-time. Checked
    # last so it clamps whatever the final effective damage would have been.
    if (
        AffixId.SECOND_WIND in creature.affixes
        and not creature.affix_second_wind_used
        and damage_amount > 0.0
        and float(creature.hp) > 1.0
    ):
        effective = float(damage_amount) * mult
        if effective >= float(creature.hp):
            mult = max(0.0, (float(creature.hp) - 1.0) / float(damage_amount))
            creature.affix_second_wind_used = True
            creature.affix_second_wind_heal_remaining = float(creature.max_hp) * SECOND_WIND_HEAL_FRACTION
            creature.affix_second_wind_heal_timer = SECOND_WIND_HEAL_DURATION_S

    return mult


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
    # Not native: Growth aura / Soul Eater both trigger off *any* nearby ally
    # death, not just deaths of rarity-affixed monsters - so this has to run
    # before the early return below (which only gates the dying creature's
    # own affixes).
    _broadcast_death_to_nearby_stacks(pool, creature)

    if not creature.rarity:
        return
    affixes = creature.affixes

    if AffixId.DETONATING in affixes:
        _queue_detonation(creature, state=state, detail_preset=int(detail_preset))

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

    if AffixId.FRAG_DEATH in affixes:
        _death_frag(state, creature, idx=int(idx))

    if AffixId.PYRE in affixes:
        _queue_area_effect(
            state,
            kind=_AreaEffectKind.PYRE,
            pos=creature.pos,
            fuse=PYRE_FUSE_DELAY_S,
            radius=PYRE_RADIUS,
            duration=PYRE_DURATION_S,
            detail_preset=int(detail_preset),
        )

    if AffixId.ANCHORING in affixes:
        _queue_area_effect(
            state,
            kind=_AreaEffectKind.ANCHOR,
            pos=creature.pos,
            fuse=ANCHORING_FUSE_DELAY_S,
            radius=ANCHORING_RADIUS,
            duration=ANCHORING_DURATION_S,
            detail_preset=int(detail_preset),
        )


def _broadcast_death_to_nearby_stacks(pool, dying_creature) -> None:
    """Growth aura (Empower) / Soul Eater (not native): every OTHER active
    creature within range of the dying one gets a permanent stack if it
    carries the matching affix. Growth's HP share is applied directly here
    (max_hp/hp can't be recomputed from a baseline like size/speed can - see
    update_monster_affixes); its size share, and Soul Eater's damage/size
    share, are picked up from affix_growth_stacks/affix_soul_stacks there."""
    # Defensive: some unit tests pass a minimal stand-in pool (only `_alloc_slot`/
    # `_entries`, or no creature list at all) - this must no-op rather than
    # raise when there's nothing to scan.
    if hasattr(pool, "entries"):
        entries = list(pool.entries)
    elif hasattr(pool, "_entries"):
        entries = list(pool._entries)
    else:
        try:
            entries = list(pool)
        except TypeError:
            return
    dx, dy = float(dying_creature.pos.x), float(dying_creature.pos.y)
    for other in entries:
        if other is dying_creature or not other.active or float(other.hp) <= 0.0:
            continue
        ox, oy = float(other.pos.x), float(other.pos.y)
        dist = math.hypot(ox - dx, oy - dy)
        if AffixId.GROWTH in other.affixes and dist <= GROWTH_TRIGGER_RANGE:
            other.affix_growth_stacks = int(other.affix_growth_stacks) + 1
            gained = float(other.max_hp) * GROWTH_HP_BONUS_PER_STACK
            other.max_hp = float(other.max_hp) + gained
            other.hp = float(other.hp) + gained
        if AffixId.SOULS in other.affixes and dist <= SOUL_STACK_RANGE:
            other.affix_soul_stacks = int(other.affix_soul_stacks) + 1


def _death_frag(state, creature, *, idx: int) -> None:
    from ..owner_ref import OwnerRef
    from ..projectiles.types import ProjectileTemplateId

    step = math.tau / FRAG_DEATH_COUNT
    for i in range(FRAG_DEATH_COUNT):
        try:
            state.projectiles.spawn(
                pos=creature.pos,
                angle=i * step,
                type_id=ProjectileTemplateId.PISTOL,
                owner=OwnerRef.from_creature(idx),
                hits_players=True,
            )
        except Exception:
            pass


class PendingMonsterDetonation(msgspec.Struct):
    """Bomber (Detonating) affix (not native): the creature already died, but
    its blast doesn't land until BOMBER_FUSE_DELAY_S later, giving players a
    window to get clear once they see the warning ring (render/world/draw.py's
    draw_pending_detonation_warnings). Damage is snapshotted at death time
    (the creature itself may be long gone - reused by another spawn - by the
    time this actually goes off)."""

    pos: Vec2
    timer: float
    radius: float
    creature_damage: float
    player_damage: float
    detail_preset: int


def _queue_detonation(creature, *, state, detail_preset: int) -> None:
    try:
        from ..meta.relics_impl.first_strike import incoming_damage_mult

        player_damage = VOLATILE_DAMAGE * BOMBER_DAMAGE_MULT * incoming_damage_mult(creature)
        state.pending_monster_detonations.append(
            PendingMonsterDetonation(
                pos=Vec2(float(creature.pos.x), float(creature.pos.y)),
                timer=BOMBER_FUSE_DELAY_S,
                radius=VOLATILE_RADIUS,
                creature_damage=VOLATILE_DAMAGE * BOMBER_DAMAGE_MULT,
                player_damage=player_damage,
                detail_preset=int(detail_preset),
            ),
        )
        state.effects.spawn_ring(
            pos=creature.pos, detail_preset=int(detail_preset), color=RGBA(0.95, 0.4, 0.15, 1.0),
        )
    except Exception:
        pass


def _detonate_now(det: PendingMonsterDetonation, *, state, players, creatures) -> None:
    from ..meta.relics_impl.fortify import damage_taken_mult
    from ..player_damage import player_take_damage

    try:
        state.effects.spawn_explosion_burst(
            pos=det.pos, scale=1.2, rng=state.rng, detail_preset=int(det.detail_preset),
        )
    except Exception:
        pass

    cx, cy = float(det.pos.x), float(det.pos.y)
    for other in creatures.entries:
        if not other.active or float(other.hp) <= 0.0:
            continue
        if math.hypot(float(other.pos.x) - cx, float(other.pos.y) - cy) <= float(det.radius):
            other.hp = float(other.hp) - float(det.creature_damage)

    for p in players:
        if float(p.health) <= 0.0:
            continue
        if math.hypot(float(p.pos.x) - cx, float(p.pos.y) - cy) <= float(det.radius):
            dealt = float(det.player_damage) * damage_taken_mult(p)
            player_take_damage(state, p, dealt, players=players)

    try:
        from grim.sfx_map import SfxId

        state.sfx_queue.append(SfxId.EXPLOSION_LARGE)
    except Exception:
        pass


def _tick_pending_detonations(players, creatures, dt: float, *, state) -> None:
    # Defensive getattr: some unit tests call update_monster_affixes with a
    # bare stub `state` that only carries what that specific test touches -
    # this must no-op rather than raise when there's nothing queued to tick.
    pending = getattr(state, "pending_monster_detonations", None)
    if not pending:
        return
    remaining: list[PendingMonsterDetonation] = []
    for det in pending:
        det.timer = float(det.timer) - float(dt)
        if det.timer > 0.0:
            remaining.append(det)
        else:
            _detonate_now(det, state=state, players=players, creatures=creatures)
    state.pending_monster_detonations = remaining


class _AreaEffectKind(IntEnum):
    PYRE = 1
    ANCHOR = 2


class PendingMonsterAreaEffect(msgspec.Struct):
    """Pyre (Cinderburst) / Anchoring (Gravemark) affixes (not native): like
    PendingMonsterDetonation, the effect fuses for a beat before it starts -
    but unlike a one-shot explosion, once triggered it then persists for
    `duration` seconds (a burning field / a pull zone) before it's removed.
    `triggered` distinguishes the two phases within one instance instead of
    replacing it with a second struct."""

    kind: int
    pos: Vec2
    fuse: float
    radius: float
    duration: float
    detail_preset: int
    triggered: bool = False


def _queue_area_effect(
    state, *, kind: int, pos, fuse: float, radius: float, duration: float, detail_preset: int,
) -> None:
    try:
        pending = state.pending_monster_area_effects
    except AttributeError:
        return
    try:
        pending.append(
            PendingMonsterAreaEffect(
                kind=int(kind),
                pos=Vec2(float(pos.x), float(pos.y)),
                fuse=float(fuse),
                radius=float(radius),
                duration=float(duration),
                detail_preset=int(detail_preset),
            ),
        )
        color = RGBA(0.95, 0.35, 0.1, 1.0) if kind == _AreaEffectKind.PYRE else RGBA(0.6, 0.25, 0.85, 1.0)
        state.effects.spawn_ring(pos=pos, detail_preset=int(detail_preset), color=color)
    except Exception:
        pass


def _trigger_area_effect(effect: PendingMonsterAreaEffect, *, state) -> None:
    try:
        color = RGBA(1.0, 0.5, 0.15, 1.0) if effect.kind == _AreaEffectKind.PYRE else RGBA(0.7, 0.3, 0.95, 1.0)
        state.effects.spawn_ring(pos=effect.pos, detail_preset=int(effect.detail_preset), color=color)
    except Exception:
        pass


def _apply_area_effect_tick(effect: PendingMonsterAreaEffect, dt: float, *, state, players) -> None:
    from ..player_damage import player_take_damage

    cx, cy = float(effect.pos.x), float(effect.pos.y)
    for p in players:
        if float(p.health) <= 0.0:
            continue
        px, py = float(p.pos.x), float(p.pos.y)
        if math.hypot(px - cx, py - cy) > float(effect.radius):
            continue
        if effect.kind == _AreaEffectKind.PYRE:
            player_take_damage(state, p, PYRE_DAMAGE_PER_S * dt, players=players)
        elif effect.kind == _AreaEffectKind.ANCHOR:
            frac = min(1.0, ANCHORING_PULL_FRAC_PER_S * dt)
            p.pos = Vec2(px + (cx - px) * frac, py + (cy - py) * frac)


def _tick_pending_area_effects(players, dt: float, *, state) -> None:
    pending = getattr(state, "pending_monster_area_effects", None)
    if not pending:
        return
    remaining: list[PendingMonsterAreaEffect] = []
    for effect in pending:
        if not effect.triggered:
            effect.fuse = float(effect.fuse) - float(dt)
            if effect.fuse > 0.0:
                remaining.append(effect)
                continue
            effect.triggered = True
            _trigger_area_effect(effect, state=state)
        effect.duration = float(effect.duration) - float(dt)
        _apply_area_effect_tick(effect, dt, state=state, players=players)
        if effect.duration > 0.0:
            remaining.append(effect)
    state.pending_monster_area_effects = remaining


def _death_hatch(pool, creature, *, rng) -> None:
    from .lifecycle import CREATURE_LIFECYCLE_ALIVE

    base_speed = float(creature.affix_base_move_speed) or float(creature.move_speed)
    for i in range(HATCHING_COUNT):
        child_idx = pool._alloc_slot()
        if child_idx is None:
            return
        child = msgspec.structs.replace(creature)
        child.rarity = 0
        child.affixes = ()
        child.damage_taken_mult_by_type = {}
        # Not native: buffed from the original 24/34/4.0 - the old crawlers
        # died to a stray contact hit and barely tickled the player.
        child.hp = 45.0
        child.max_hp = 45.0
        child.size = 38.0
        child.move_speed = min(4.5, base_speed + 1.2)
        child.contact_damage = 8.0
        child.reward_value = 0.0
        child.affix_base_move_speed = 0.0
        child.affix_base_contact_damage = 0.0
        child.heading = float(creature.heading + (i - 1) * 0.7)
        # The dying parent's lifecycle_stage is already decaying toward the
        # corpse-fade/despawn state (see creature_handle_death); without this
        # reset the copied child inherits that and is treated as an
        # already-dead corpse the instant it spawns. Native's own
        # split-on-death code (SPIDER_SP2, above) resets this the same way.
        child.lifecycle_stage = CREATURE_LIFECYCLE_ALIVE
        pool._entries[child_idx] = child
        pool.spawned_count += 1
