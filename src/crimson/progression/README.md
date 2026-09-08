# `crimson.progression` — data-driven build stats

The original game hard-wires every perk effect at its point of use
(`if perk_active(player, PerkId.X): value *= 1.4`). There are ~80 such
branches. That does not scale to a roguelite with hundreds of perks /
affixes / curses, and nothing composes (two sources touching the same
number don't know about each other).

This package is the replacement layer. It runs **alongside** the native
perk code — it does not delete it — so migration is incremental and native
modes keep working the whole way.

## The three pieces

| Module | What it is |
|---|---|
| `stats.py` | `PlayerStats` — a frozen struct of ~25 named numbers (`damage_mult`, `shot_cooldown_mult`, `move_speed_mult`, …) each with an identity default, plus `flags: frozenset[str]` for non-numeric keystone toggles. |
| `modifiers.py` | `StatMod(stat, op, value)` where `op` is `FLAT` / `INC` / `MORE` / `OVERRIDE` / `FLAG`. `resolve_stats(mods)` folds a list into a `PlayerStats`. |
| `sources.py` | `PERK_STAT_MODS` maps a `PerkId` to its `StatMod`s; `PERK_MECHANICAL` lists every perk that stays hard-wired, with a reason. A contract test asserts the two partition `PerkId`. `refresh_player_stats(players)` recomputes `player.stats` (once per sim tick from `WorldState.step`, and again at a few subsystem entry points that tests drive directly). `resolve_team_stats(players)` resolves one block from every player's mods, for the shared damage path. |

### Resolution formula (per numeric stat, PoE-style)

```
final = (identity + Σ FLAT) * (1 + Σ INC) * Π (1 + MORE_i)
```

`OVERRIDE` short-circuits (last one wins). `INC` values stack additively
with each other and scale once; `MORE` values each apply as their own
multiplier. Order of mods never changes the result.

## What's migrated

Stat perks (read `player.stats` / `team_stats`): Fastshot, Sharpshooter
(fire rate), Fastloader, Ammo Maniac, My Favourite Weapon (clip), Uranium
Filled Bullets (kinetic-lead damage), Doctor, Barrel Greaser (projectile
damage - kinetic + energy), Pyromaniac, Ion Gun Master (damage), Thick
Skinned (damage taken), Bonus Economist.

### Damage-type layers

Outgoing weapon damage splits into a small taxonomy so plasma can scale on
its own line (like ion and fire already do):

| Stat | Applies to | Fed by |
|---|---|---|
| `damage_mult_projectile` | any main-pool projectile hit (`BULLET` + `ENERGY`) | Doctor, Barrel Greaser |
| `damage_mult_bullet` | kinetic lead only (`BULLET`) | Uranium Filled Bullets |
| `damage_mult_energy` | plasma / energy only (`ENERGY`) | future plasma perks, relics |
| `damage_mult_fire` / `damage_mult_ion` | `FIRE` / `ION` | Pyromaniac / Ion Gun Master |

Plasma weapons deal `CreatureDamageType.ENERGY` (see
`projectiles/types.py::ENERGY_PROJECTILE_TEMPLATE_IDS`) and additionally get
the per-shot clip-heat ramp (`weapon_runtime/plasma_heat.py`), stamped onto
each bolt as `Projectile.energy_heat_mult`.

Keystone flags: Unstoppable (`no_hit_stagger`), Barrel Greaser
(`projectile_double_steps`).

Everything else is in `PERK_MECHANICAL` with a one-line reason - dynamic
ramps (Long Distance Runner, Living Fortress), RNG rolls (Dodger, Ninja,
Highlander, Regeneration), one-shot pick effects (Instant Winner, Bandage,
Infernal Contract), timers (Death Clock, Man Bomb) and conditional branches
(Stationary Reloader, Tough Reloader). Those stay hard-wired; the value of
moving them to data does not cover a rules engine.

## Reading stats from gameplay code

`player.stats` is a **cache resolved at the top of every sim tick** and at
the entry of `fire_weapon`, `weapon_assign_player`, `player_start_reload`,
`player_take_damage` and `bonus_apply` (for tests / tools that reach those
without `WorldState.step`). The shared damage path uses
`resolve_team_stats(players)` instead, which reads `perk_counts` directly and
needs no cache. If you add a new consumer reached by unit tests, either add a
`refresh_player_stats` call at its entry or have the test call it.

```python
mult = perk_player.stats.shot_cooldown_mult
if mult != 1.0:
    shot_cooldown = f32(shot_cooldown * mult)
```

## Migrating a hard-wired perk (the procedure)

Do one perk (or one stat) per change. Example — `Fastshot`:

1. **Pick / add the stat.** `shot_cooldown_mult` already exists in
   `stats.py`. If you need a new one, add the field *and* its identity to
   `STAT_IDENTITIES` (a sanity check enforces they stay in sync).

2. **Register the mod** in `PERK_STAT_MODS` (`sources.py`):

   ```python
   PerkId.FASTSHOT: (more("shot_cooldown_mult", -0.12, source="perk:fastshot"),),
   ```

   Choose `op` so that, **with this perk as the only contributor**, the
   resolved number equals the old hard-coded constant. `more(-0.12)` →
   `1 * (1 - 0.12)` = `0.88`, i.e. the old `* 0.88`.

3. **Replace the branch** at the call site with a read of the resolved
   stat, keeping the same arithmetic op (`x87_pc24_mul` / `f32(...)` /
   whatever the surrounding parity code uses) so the number is bit-identical
   while the perk is alone.

4. **Lock it with a test** in `tests/progression/test_migrated_perks.py`:
   one assertion that the perk alone reproduces the old value, one that a
   second synthetic source on the same stat composes correctly.

5. When two migrated perks feed one stat (Fastshot + Sharpshooter →
   `shot_cooldown_mult`, or Doctor + Barrel Greaser + Uranium →
   `damage_mult_bullet`), they fold into a single multiply instead of the
   original sequential ones — a deliberate, documented ULP change. Update
   the one combo test that asserted the old chained value; the single-perk
   tests stay green.

6. A perk that is *only* mechanical goes in `PERK_MECHANICAL` (a
   `PerkId -> reason` dict) instead. The `test_perk_coverage` contract test
   fails if a perk is in neither registry or both.

## Escape hatch: mechanical effects

Most Crimsonland perks aren't a flat number — dynamic ramps, RNG rolls,
one-shot pick effects, timers, conditional branches. Those stay hard-wired
and are listed in `PERK_MECHANICAL`. Genuinely mechanical *keystones* that
new content wants to branch on ("projectiles chain instead of pierce") use a
flag instead:

```python
PerkId.SOME_KEYSTONE: (flag("projectiles_chain", source="perk:some_keystone"),)
# ... in the projectile code:
if owner_player.stats.has("projectiles_chain"):
    ...
```

## Not yet wired (future source registration)

`collect_player_stat_mods(player, extra_sources=...)` already takes an
`extra_sources` iterable. Weapon affixes, map modifiers and curses will
build their `StatMod` lists and pass them in there; nothing else about the
resolver changes.
