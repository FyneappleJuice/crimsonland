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

TICK_RANGE = 100.0
TICK_FRAC_PER_S = 0.05
LUNGE_INTERVAL_S = 3.0
LUNGE_DURATION_S = 0.4
LUNGE_SPEED_BONUS = 3.0        # +300% -> 4x total during the dash window
LUNGE_CONTACT_BONUS = 1.0      # +100% -> 2x total during the dash window
ACID_LOB_INTERVAL_S = 2.0
FEASTING_HEAL_FRACTION = 0.3


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


class AffixSpec(msgspec.Struct, frozen=True):
    id: int
    word: str          # flavour word for the generated name: a prefix, or "of X"
    label: str         # mechanical modifier name (shown in the hover tooltip)
    suffix: bool
    threat: int
    min_xp: int
    aura: bool = False


_SPECS = (
    AffixSpec(AffixId.OVERGROWN, "Brood-Fed", "Overgrown", False, 1, 0),
    AffixSpec(AffixId.HASTED, "Rampant", "Hasted", False, 1, 0),
    AffixSpec(AffixId.COLOSSAL, "Colossal", "Oversized", False, 2, 3000),
    AffixSpec(AffixId.RUNTISH, "Runtish", "Undersized", False, 1, 3000),
    AffixSpec(AffixId.GORGED, "Gorged", "Heavy", False, 2, 6000),
    AffixSpec(AffixId.ARMORED, "of Plating", "Armored", True, 2, 0),
    AffixSpec(AffixId.FLAME_WARDED, "of Warding", "Flame-Warded", True, 2, 0),
    AffixSpec(AffixId.INSULATED, "of Grounding", "Insulated", True, 2, 0),
    AffixSpec(AffixId.BLAST_PROOF, "of Absorption", "Blast-Proof", True, 2, 0),
    AffixSpec(AffixId.SHELLED, "of the Turtle", "Shelled", True, 3, 9000),
    AffixSpec(AffixId.REGENERATING, "of Recovery", "Regenerating", True, 2, 9000),
    AffixSpec(AffixId.FROTHING, "Frothing", "Berserker", False, 3, 9000),
    AffixSpec(AffixId.SWIFT_AURA, "of Swiftness", "Haste Aura", True, 3, 12000, aura=True),
    AffixSpec(AffixId.DETONATING, "of Detonation", "Bomber", True, 3, 9000),
    AffixSpec(AffixId.HATCHING, "of the Swarm", "Hatch Death", True, 3, 12000),
    AffixSpec(AffixId.BOUNTIFUL, "of Plenty", "Bountiful", True, 0, 0),
    AffixSpec(AffixId.GLASS_FRAME, "of Glass", "Volatile Frame", True, 2, 6000),
    AffixSpec(AffixId.FERALIZATION, "of Feralization", "Rabid", True, 3, 12000),
    AffixSpec(AffixId.IRONHIDE, "Ironhide", "Bulwark", False, 3, 12000),
    AffixSpec(AffixId.EVASIVE, "of Deflection", "Evasive", True, 2, 6000),
    AffixSpec(AffixId.OVERSHIELD, "of the Barrier", "Overshield", True, 2, 12000),
    AffixSpec(AffixId.FRAG_DEATH, "of Splintering", "Frag Death", True, 2, 10000),
    AffixSpec(AffixId.TICK_BLOODHUNGRY, "of the Tick", "Bloodhungry", True, 2, 13000),
    AffixSpec(AffixId.LUNGING, "Lunging", "Charger", False, 3, 5000),
    AffixSpec(AffixId.ACID_LOB, "Spitting", "Acid Lob", False, 2, 5000),
    AffixSpec(AffixId.FEASTING, "of Feasting", "Life Thief", True, 2, 13000),
)

AFFIXES: dict[int, AffixSpec] = {s.id: s for s in _SPECS}

# Affixes that trigger something at the moment of death (apply_monster_death_affixes
# below). A monster carrying any of these tints DEATH_AFFIX_COLOR instead of its
# tier colour - a "this one does something when it dies" warning independent
# of rarity tier.
DEATH_AFFIX_IDS: frozenset[int] = frozenset(
    {AffixId.DETONATING, AffixId.HATCHING, AffixId.BOUNTIFUL, AffixId.FRAG_DEATH}
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
        elif aid == AffixId.SHELLED:
            for t in _ALL_DAMAGE_TYPES:
                _resist(init, t, 0.55)
        elif aid == AffixId.GLASS_FRAME:
            for t in _ALL_DAMAGE_TYPES:
                _resist(init, t, 1.4)
            speed *= 1.6
        elif aid == AffixId.FERALIZATION:
            reward_mult *= 3.0
            speed *= 2.5
            contact *= 2.0
        # REGENERATING / FROTHING / SWIFT_AURA / DETONATING / HATCHING / BOUNTIFUL /
        # IRONHIDE / EVASIVE / OVERSHIELD / FRAG_DEATH / TICK_BLOODHUNGRY / LUNGING /
        # ACID_LOB / FEASTING are handled at runtime (update_monster_affixes /
        # monster_affix_on_hit / death path / contact path).

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

    angle = math.atan2(float(target.pos.y) - float(creature.pos.y), float(target.pos.x) - float(creature.pos.x))
    try:
        state.projectiles.spawn(
            pos=creature.pos,
            angle=angle,
            type_id=ProjectileTemplateId.ION_RIFLE,
            owner=OwnerRef.from_creature(idx),
            hits_players=True,
        )
    except Exception:
        pass


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

    for idx, c in enumerate(entries):
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

        c.move_speed = min(4.5, float(c.affix_base_move_speed) * speed_mult)
        c.contact_damage = float(c.affix_base_contact_damage) * contact_mult

        if _has(c, AffixId.REGENERATING):
            if c.affix_regen_pause > 0.0:
                c.affix_regen_pause = max(0.0, float(c.affix_regen_pause) - dt)
            elif float(c.hp) < float(c.max_hp):
                c.hp = min(float(c.max_hp), float(c.hp) + float(c.max_hp) * REGEN_FRAC_PER_S * dt)

        if (
            _has(c, AffixId.TICK_BLOODHUNGRY)
            and players
            and float(c.max_hp) > 0.0
            and float(c.hp) < float(c.max_hp)
        ):
            cx, cy = float(c.pos.x), float(c.pos.y)
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


# --- runtime: on-hit (called from creatures/damage.py) ---------------


def monster_affix_on_hit(creature, damage_type: int, damage_amount: float = 0.0) -> float:
    """Note the hit (regen pause) and return the combined resist multiplier for it."""
    if AffixId.REGENERATING in creature.affixes:
        creature.affix_regen_pause = REGEN_PAUSE_S

    mult = 1.0
    d = creature.damage_taken_mult_by_type
    if d:
        mult *= float(d.get(int(damage_type), 1.0))

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

    if AffixId.FRAG_DEATH in affixes:
        _death_frag(state, creature, idx=int(idx))


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
            # Not native: Pact of the First Strike's cost applies to this blast too.
            from ..meta.relics_impl.first_strike import incoming_damage_mult
            from ..meta.relics_impl.fortify import damage_taken_mult

            dealt = VOLATILE_DAMAGE * incoming_damage_mult(creature) * damage_taken_mult(p)
            player_take_damage(state, p, dealt, players=players)

    try:
        from grim.sfx_map import SfxId

        state.sfx_queue.append(SfxId.EXPLOSION_LARGE)
    except Exception:
        pass


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
        child.hp = 24.0
        child.max_hp = 24.0
        child.size = 34.0
        child.move_speed = min(4.5, base_speed + 1.2)
        child.contact_damage = 4.0
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
