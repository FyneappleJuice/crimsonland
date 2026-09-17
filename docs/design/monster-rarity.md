---
tags:
  - status-design
  - roguelite-mod
---

# Monster rarity & affixes (design)

Status: **design / not implemented.** Branch: `monster-rarity`.

Turn the survival "rare colour variant" roll (red / green / blue / purple / yellow
in `build_survival_spawn_creature`, `creatures/spawn.py`) into a Path-of-Exile /
Soulstone-style affix system: monsters roll a **rarity**, rarity grants a number
of **affixes** from weighted, level-gated pools, and the kill reward scales with
how dangerous the roll came out.

Related: [[roguelite-direction]], [`spawning.md`](../creatures/spawning.md).

---

## 1. Tiers

Replaces the current five-variant block. Colours are kept as the low tier so the
existing visual language ("uh oh, a red one") survives.

| Old variant | Tier | Affixes | Name shown | Extras |
|---|---|---|---|---|
| Red | **Tainted — aggressive** | 1 prefix (offense pool) | `Lunging Alien` | red tint |
| Green | **Tainted — feral** | 1 prefix (sustain / summon pool) | `Voracious Lizard` | green tint |
| Blue | **Tainted — warded** | 1 prefix + 1 suffix (defense / reactive pool) | `Barbed Spider of Plating` | blue tint |
| Purple | **Mutated** | 3 — up to 2 prefix + 1 suffix, no aura | `Corrosive Zombie of Warding` | purple tint, nameplate |
| Yellow | **Apex** | 5 — **max 1 aura**, keeps the +2230 HP | generated proper name — `Gutspewer, the Skittering Dark` | pulsing gold outline, nameplate, on-screen callout, guaranteed drops |

Rules:

- No duplicate affixes on one monster.
- **Auras only roll on Apex, at most one.** (`of Command`, `of Dread`, … — tagged
  below.)
- Each affix has a **min level** (like PoE's Level column) and a **spawn weight**
  and a **threat 1–4** rating. Rarity picks affixes from `{ eligible for this
  player level } ∩ { eligible for this tier }`, weighted.
- Prefix vs suffix is a naming split, not a hard mechanical one: prefixes are
  what the monster *does*, suffixes are how it *resists / reacts / dies*.

### Spawn rates (proposal)

The current variant odds (~1–3 % red/green/blue, <0.5 % purple/yellow) are too
rare for a core feature. Move to a per-spawn roll that ramps with player level:

| Tier | early (lvl < 8) | mid (8–20) | late (20+) |
|---|---|---|---|
| Tainted | 4 % | 8 % | 12 % |
| Mutated | 0.5 % | 2 % | 4 % |
| Apex | — | 0.3 % | 1 % |

Scripted milestone / den / formation spawns can also be flagged to *always* roll
at least Mutated (mini-boss waves become genuinely rare-tier).

---

## 2. Prefix pool — the monster *does* something

Format: **Name** — *Mechanical label* — (min level, threat) — effect.

### Bulk & stat
- **Brood-Fed** — *Overgrown* — (1, 1) — +60 % max HP.
- **Rampant** — *Hasted* — (1, 1) — +35 % move speed.
- **Colossal** — *Oversized* — (3, 2) — +40 % size, +50 % contact damage, +25 % knockback resist.
- **Runtish** — *Undersized* — (3, 1) — −35 % size, +60 % speed, −20 % HP.
- **Gorged** — *Heavy* — (5, 2) — +100 % HP, −20 % speed, immune to knockback.
- **Frothing** — *Berserker* — (8, 3) — scales up to +80 % speed / +60 % contact damage as HP drops.
- **Overclocked** — *Twitchy* — (10, 2) — all ability cooldowns −50 %.
- **Kinetic** — *Momentum* — (10, 2) — gains speed + contact damage the longer it moves straight; resets on turn.

### Movement & positioning
- **Lunging** — *Charger* — (5, 3) — every 3 s dashes straight at the player at 4× speed, 2× contact damage on connect.
- **Blinkspawn** — *Phase Walker* — (10, 3) — every 2.5 s teleports 200 px toward the player.
- **Skittering** — *Erratic* — (5, 2) — circle-strafes instead of closing.
- **Burrower** — *Tunneler* — (12, 3) — periodically submerges (untargetable, no contact) 1.5 s, resurfaces adjacent.
- **Unstoppable** — *Juggernaut* — (15, 3) — cannot be slowed, frozen or knocked back; ignores the Freeze bonus.
- **Relentless** — *Fixated* — (10, 2) — immune to knockback + slow within 250 px of a player.
- **Harrowing** — *Dogged* — (12, 2) — always knows the player's position; ignores decoys / stealth.
- **Titanic** — *Ground Shaker* — (15, 2) — every footfall within 200 px briefly jars the player's aim.
- **Fractured** — *Echoing* — (12, 3) — a delayed after-image trails 0.5 s behind and also deals contact damage.
- **Gravid** — *Bursting* — (15, 3) — visibly swells; if not killed in 8 s births a mid elite and resets.

### Ranged attacks
- **Spitting** — *Acid Lob* — (5, 2) — every 2 s lobs a glob → 60-px ION-acid pool for 4 s.
- **Volatile** — *Grenadier* — (10, 3) — every 3.5 s throws a grenade → EXPLOSION in 90-px radius after 1 s.
- **Arc-Charged** — *Tesla* — (12, 3) — every 2 s fires a LIGHTNING bolt that chains to 2 nearby targets.
- **Searing** — *Flamespitter* — (8, 2) — sprays a short FIRE cone every 1.5 s, igniting the player.
- **Railed** — *Sniper* — (18, 4) — every 4 s fires a full-arena ENERGY lance along its facing (0.6 s telegraph).
- **Mortaring** — *Bombardier* — (15, 3) — every 5 s drops 3 delayed fire mortars on the player's position.
- **Nova-Born** — *Pulsar* — (12, 2) — every 4 s emits an expanding damage + knockback ring.
- **Hexbeam** — *Disruptor* — (18, 4) — slow tracking orb; on hit disables the player's current weapon 2 s (forces sidearm).

### Hazards & ground
- **Molten** — *Burning Trail* — (5, 2) — leaves burning-ground trail (FIRE, 2 s per patch).
- **Cryogenic** — *Frost Trail* — (5, 2) — chilled-ground trail; player −40 % speed while stood on it.
- **Irradiated** — *Fallout Trail* — (10, 3) — ION cloud trail; stacking slow + DoT.
- **Corrosive** — *Rusting* — (12, 3) — every 2 s spawns a pool that drains 4 ammo/s from the current clip.
- **Sapper** — *Minelayer* — (12, 3) — drops proximity mines every 3 s (arm 1 s, trigger at 50 px).
- **Sundering** — *Fissure* — (15, 3) — every 5 s cracks the ground in a line toward the player; erupts 0.8 s later.
- **Miasmic** — *Gas Bag* — (10, 2) — trails a cloud that cuts player fire rate 25 % inside it.
- **Quicksand** — *Miring* — (12, 2) — slow-field patches that also block dodge / roll.

### Summoning & pack
- **Broodmother** — *Egg Layer* — (10, 3) — every 4 s lays an egg → 2 spiderlings after 2 s.
- **Necrotic** — *Reanimator* — (12, 3) — every 6 s revives the nearest corpse as a half-HP zombie.
- **Fractalizing** — *Splitter* — (10, 3) — splits into 2 on death, and each of those splits once more.
- **Hive-Linked** — *Shared Pain* — (15, 3) — distributes 40 % of incoming hit damage among the 4 nearest allies.
- **Vengeful** — *Grudge* — (12, 2) — permanent +20 % damage / +15 % speed each time a pack member dies (stacks).
- **Voracious** — *Devourer* — (10, 2) — eats nearby corpses to heal 20 % max HP each.
- **Escort** — *Bodyguarded* — (15, 2) — spawns with 3 small guards that body-block bullets aimed at it.
- **Endless** — *Tide Caller* — (18, 3) — while alive, a fresh basic copy spawns at the arena edge every 8 s.

### Contact debuffs on the player
- **Draining** — *Ammo Leech* — (10, 2) — contact empties 20 % of the current clip.
- **Enfeebling** — *Sapping* — (12, 2) — contact → −30 % weapon damage for 3 s.
- **Chilling** — *Numbing* — (10, 2) — contact → −40 % player speed for 2 s.
- **Thieving** — *Pickpocket* — (15, 3) — contact steals the player's oldest active power-up; released as a pickup on death.
- **Withering** — *Rot* — (12, 2) — contact applies a stacking player DoT that lingers 4 s.
- **Repulsive** — *Bruiser* — (8, 2) — contact knocks the player back 2× and interrupts reload.
- **Magnetic** — *Disarming* — (12, 2) — contact force-reloads the current weapon.
- **Petrifying** — *Stoning* — (18, 4) — 10 % on hit to stone the player 0.5 s (no move / shoot).

### Elemental identity (this mod's damage types)
- **Plasma-Bathed** — *Energized* — (10, 2) — releases an ENERGY nova on death.
- **Ion-Saturated** — *Contaminated* — (12, 2) — projects a 120-px ION field that slows the player while alive.
- **Storm-Touched** — *Conduit* — (12, 3) — every bullet that hits it arcs LIGHTNING to 1 nearby ally.
- **Pyroclastic** — *Everburning* — (8, 2) — permanently on fire; corpse burns as burning ground 3 s.
- **Prismatic** — *Shifting* — (15, 3) — cycles which damage type it resists every 2 s (colour-telegraphed).
- **Barbed** — *Spiked* — (8, 2) — reflects 15 % of bullet damage as a projectile at the shooter.
- **Ironhide** — *Bulwark* — (12, 3) — takes at most 8 % of its max HP from any single hit.

---

## 3. Suffix pool — the monster *resists / reacts / auras / dies loud*

### Defensive layers
- **of Plating** — *Armored* — (1, 2) — −40 % BULLET / MELEE damage taken.
- **of Warding** — *Flame-Warded* — (1, 2) — −60 % FIRE damage, immune to ignite.
- **of Grounding** — *Insulated* — (1, 2) — −60 % LIGHTNING & ENERGY damage.
- **of Absorption** — *Blast-Proof* — (1, 2) — −50 % EXPLOSION damage, immune to blast knockback.
- **of Deflection** — *Evasive* — (6, 2) — 35 % chance to fully avoid a bullet.
- **of the Turtle** — *Shelled* — (12, 3) — −75 % damage from its front 120°; must be flanked.
- **of Resilience** — *Adaptive* — (12, 3) — after a hit, +50 % resist to that damage type for 3 s.
- **of Glass** — *Volatile Frame* — (6, 2) — +40 % damage taken, +60 % move speed.
- **of Stillness** — *Hardened While Idle* — (10, 2) — −80 % damage taken while not moving.
- **of Endurance** — *Stalwart* — (12, 3) — first hit each second is reduced to 1 damage (throttles fast weapons).

### Shields & phases
- **of the Barrier** — *Overshield* — (12, 2) — shield absorbs the first 3 hits, then drops.
- **of Flickering** — *Phasing* — (18, 3) — every 5 s invulnerable for 1 s (shimmer telegraph).
- **of Recovery** — *Regenerating* — (12, 2) — regen 4 % max HP/s, interrupted 2 s by any hit.
- **of the Second Wind** — *Undying* — (18, 3) — first lethal hit leaves it at 1 HP + heals 30 % over 2 s (once).
- **of Inevitability** — *Timed* — (20, 4) — 20 s timer; if alive when it ends, full heal + gains an affix.
- **of Obscurity** — *Veiled* — (15, 2) — invisible beyond 250 px (shows when close or hit).

### Auras — buff allies  *(Apex only, max 1)*
- **of Command** — *Warlord Aura* — (15, 3) — allies within 300 px: +30 % contact damage.
- **of Swiftness** — *Haste Aura* — (15, 3) — allies within 300 px: +30 % move speed.
- **of the Vanguard** — *Guardian Aura* — (18, 3) — allies within 250 px: −30 % damage taken.
- **of Fury** — *Frenzy Aura* — (18, 3) — allies within 300 px: +25 % attack rate.
- **of Growth** — *Empower Aura* — (20, 3) — ally deaths within 300 px make survivors +10 % size / +20 % HP.
- **of the Choir** — *Regen Aura* — (18, 3) — allies within 250 px regen 3 % HP/s.
- **of Convergence** — *Homing Aura* — (20, 4) — pack projectiles gain slight homing within 350 px.

### Auras — debuff player  *(Apex only, max 1)*
- **of Dread** — *Terror Aura* — (15, 3) — screen edges darken, weapon spread +25 % within 350 px.
- **of Entropy** — *Decay Aura* — (18, 3) — player cannot regen HP within 400 px.
- **of Leeching** — *Siphon Aura* — (15, 3) — drains 3 XP/s within 300 px; drops it as an orb on death.
- **of Frost** — *Chill Aura* — (15, 3) — player −20 % speed within 250 px.
- **of Static** — *Jam Aura* — (18, 3) — player reload −30 % within 250 px.
- **of Gluttony** — *Null Aura* — (20, 4) — player power-up timers tick 3× faster within 300 px.
- **of the Leash** — *Tether* — (20, 4) — ramping damage the farther the player kites from it.

### Retaliation
- **of Thorns** — *Spiked* — (12, 2) — hit by MELEE → 15 damage back to the player.
- **of Backlash** — *Overload* — (12, 3) — hit by LIGHTNING / ENERGY → retaliatory arc at the shooter.
- **of Cinders** — *Flame Retaliation* — (12, 2) — hit by FIRE → burning patch at its feet.
- **of Fracture** — *Shrapnel* — (12, 3) — hit by EXPLOSION → 6 shrapnel projectiles.
- **of Mirrors** — *Reflective* — (15, 3) — 20 % on bullet hit → spawn a copy of that bullet at the player.
- **of Feedback** — *Kickback* — (12, 2) — player recoil / spread doubled while it's on screen.

### On-death
- **of Detonation** — *Bomber* — (12, 3) — big EXPLOSION in 110-px radius.
- **of the Pyre** — *Cinderburst* — (12, 2) — 90-px burning field for 4 s.
- **of Corrosion** — *Acid Death* — (12, 2) — ION / acid pool for 5 s.
- **of Sparks** — *Storm Death* — (12, 3) — LIGHTNING nova chaining through nearby allies (hurts player if close).
- **of Splintering** — *Frag Death* — (10, 2) — 8-bullet ring.
- **of the Swarm** — *Hatch Death* — (12, 3) — 3 small fast crawlers.
- **of Revival** — *Haunt* — (18, 3) — immortal ghost copy chases the player 4 s (no XP).
- **of Contagion** — *Plague Death* — (15, 3) — 3 nearest allies gain +50 % HP / +25 % size.
- **of the Freezer** — *Cold Snap* — (15, 3) — freezes the player 0.75 s if within 150 px.
- **of Ruin** — *Cataclysm* — (22, 4) — frag ring + burning field + knockback nova, all at once.

### Sustain & leech
- **of Feasting** — *Life Thief* — (13, 2) — heals 30 % of contact damage dealt.
- **of Congealment** — *Unleechable* — (13, 2) — player cannot lifesteal from it.
- **of the Tick** — *Bloodhungry* — (13, 2) — heals 3 % max HP/s while within 100 px of the player.
- **of Souls** — *Soul Eater* — (18, 4) — +5 % damage / +3 % size per ally death within 250 px (stacks all fight).

### Control against the player
- **of Snaring** — *Web Layer* — (15, 3) — every 3 s roots the player 0.6 s if within 200 px (telegraphed).
- **of the Vortex** — *Gravity Well* — (15, 3) — constantly pulls the player 15 % toward it.
- **of Displacement** — *Bumping* — (12, 2) — every landed hit knocks the player a fixed 120 px.
- **of Anchoring** — *Gravemark* — (15, 2) — on death, a zone pulls the player toward it for 2 s.

### Anti-build / annoyance
- **of Interference** — *Scrambler* — (15, 2) — disables the player's minimap / bonus-aim highlight while alive.
- **of Rust** — *Corroding* — (18, 3) — every 4 s permanently drops the current clip capacity by 1 until reload.
- **of Exhaustion** — *Draining Presence* — (15, 2) — player dodge / roll cooldown 2× while it lives.
- **of Silence** — *Muffling* — (18, 3) — disables the player's special / alt weapon within 250 px.
- **of the Beacon** — *Marked Prey* — (15, 3) — all ranged allies get perfect accuracy on the player while it's alive.
- **of Emptiness** — *Hollow* — (18, 2) — no corpse, no XP — but drops 2 guaranteed bonuses.

### Reward / economy
- **of Plenty** — *Bountiful* — (1, 0) — guaranteed bonus power-up on death.
- **of Riches** — *Golden* — (1, 0) — 5× XP, glows gold.
- **of Hoarding** — *Greedy* — (10, 2) — steals 10 XP per contact hit; all of it drops as orbs on death.
- **of Feralization** — *Rabid* — (12, 3) — 3× XP, but +150 % speed and +100 % contact damage.
- **of the Vault** — *Locked* — (10, 0) — guaranteed weapon pickup on death.
- **of Multiplication** — *Prolific* — (18, 4) — every other monster in the wave gets +1 minor affix while it's alive.

### Pack / formation
- **of the Phalanx** — *Linked* — (18, 3) — shares one HP pool with up to 4 pack members.
- **of Cohesion** — *Rallying Point* — (15, 2) — allies path to *it*, not the player; killing it scatters them.
- **of the Tide** — *Endless Wave* — (18, 2) — the wave doesn't count as "clear" until it dies.
- **of Stone** — *Immovable* — (12, 2) — heavy + immune to knockback — a pure wall.

**Totals:** 64 prefixes + 66 suffixes = **130 affixes** (14 of them auras).

---

## 4. Rewards — difficulty compensation

Affixed monsters are meaningfully harder, so the kill has to pay. The reward is a
function of tier and how nasty the roll actually came out (sum of affix threat).

### XP

```
reward_value = base_reward
             * tier_mult
             * (1 + 0.12 * total_affix_threat)      # threat surcharge
             * affix_reward_mult                     # 'of Riches' x5, 'of Feralization' x3, ...
```

- `base_reward` — the existing formula in `build_survival_spawn_creature`
  (`(rand%10+10) + speed*5 + contact*0.8 + health*0.4`). Drop the trailing `*0.8`;
  it becomes redundant with `tier_mult`.
- `tier_mult`: **normal ×1**, **Tainted ×3**, **Mutated ×8**, **Apex ×20**.
- `total_affix_threat` — sum of the 1–4 rating of every rolled affix. A 5-affix
  Apex at threat 3 each = 15 → `1 + 0.12*15` = **×2.8** on top of the ×20.
- Worked example: late-game normal mob ≈ 90 XP. A threat-15 Apex ≈
  `90 * 20 * 2.8` ≈ **5 000 XP** (≈ a full level). A 1-affix threat-2 Tainted ≈
  `90 * 3 * 1.24` ≈ **335 XP**.
- Numbers to expose as constants and tune: `TIER_XP_MULT`, `THREAT_XP_PER_POINT`
  (0.12), the per-affix `threat` table.

### Drops

On top of the base ~1/9 on-kill bonus roll (`try_spawn_on_kill`):

| Tier | bonus power-up | weapon / special |
|---|---|---|
| Tainted | roll bumped to ~1/5 | — |
| Mutated | **60 %**, and the *first* Mutated kill of each wave is a guaranteed drop | 10 % weapon |
| Apex | **guaranteed, 2 bonuses** | guaranteed weapon **or** relic pickup; brief hit-stop + an on-screen "SLAIN" XP popup |

- `of Plenty`, `of the Vault`, `of Emptiness` override / stack with the tier
  table (they force guaranteed drops regardless of tier).
- Feeds the roguelite meta: Apex kills are the natural drop point for relic /
  affix currency once that system exists ([[roguelite-direction]]).

### Global curve

The affix system is the difficulty lever, so **normal (unaffixed) mob rewards and
scaling stay as they are.** If affixed monsters end up common enough to raise the
baseline difficulty of a run, bump the base XP formula ×1.15–1.25 rather than
touching per-tier multipliers — keep the "rare = juicy" ratio intact.

---

## 5. Implementation hooks

- **State** — add to `CreatureState` (`creatures/runtime.py`):
  `rarity: int`, `affixes: list[int]` (affix ids), `affix_state: dict` (per-affix
  timers / shield HP / stacks), `damage_taken_mult_by_type: dict[int, float]`.
- **Roll** — in `build_survival_spawn_creature`, replace the red/green/blue/
  purple/yellow block with `resolve_monster_rarity(c, rng, player_level)`:
  roll tier → roll affixes from the level- and tier-gated weighted pool → apply
  static stat mods (bulk, resist, size, `reward_value`) immediately.
- **Static mods** (bulk / resist / size / reward / knockback-immunity) — applied
  once at spawn, no per-tick cost.
- **Dynamic mods** (auras, hazard trails, timed attacks, regen, gravity) — a new
  `update_monster_affixes(players, creatures, dt, *, rng, creature_damage_runtime)`
  called from `WorldState.step` next to `update_blade_orbits` /
  `update_scythe_swings` / `update_arc_gun`.
- **Event mods** (retaliation, on-hit contact debuffs, on-death) — hook
  `creature_apply_damage` and the death path in `creatures/runtime.py`.
- **Damage-type resist** — read `damage_taken_mult_by_type` in the per-type steps
  in `creatures/damage.py` (BULLET / MELEE / EXPLOSION / FIRE / ION / ENERGY /
  LIGHTNING already have their own steps).
- **Rendering** — `render/world/`: rarity tint / outline, a nameplate for
  Mutated + Apex, an affix-icon strip, aura radius rings under `--debug`.
- **Determinism** — every roll goes through `rng.rand_tagged` with new
  `RngCallerStatic` ids (synthetic `0xF10000xx` range, like the arc gun).
- **Scripted spawns** — `creature_spawn_template` needs a parallel
  `min_rarity` hook if den / formation / milestone monsters should roll rare.

## 6. Open questions

- Rush mode: affixes on or off? (Currently no rare variants there at all.)
- Do affixes stack across a whole *pack* (PoE "magic pack") or per-monster only?
- Aura visibility — always-on ground ring, or only under threat indicators?
- Co-op: aura radii / reward splitting.
- Relic / currency drop from Apex — depends on the meta system landing first.
