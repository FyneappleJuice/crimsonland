# SETUP — roguelite mod fork (laptop / second machine)

This is the **`FyneappleJuice/crimsonland`** fork of `banteg/crimson` — a Crimsonland
1.9.93 reimplementation (Python + raylib) being modded into a roguelite. This file
is the starting point for a fresh session on another machine: install, run, test,
and stay in sync with the other checkout.

Canonical branch: **`feat/roguelite-weapons`** (identical to `master` right now).
Latest commit as of writing: `1257383c2` — "tune(evil scythe): heavier, slower swings".

---

## 1. Prerequisites

- **git**
- **uv** — the project's package manager. Install (Windows PowerShell):
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
  (macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Python 3.13+ is pulled in by `uv` automatically; you don't need it preinstalled.

No copying of assets or virtualenvs between machines — see §3.

---

## 2. Clone and run

```bash
git clone https://github.com/FyneappleJuice/crimsonland.git
cd crimsonland
uv run crimson --test-mode --no-intro
```

First launch does three things on its own:

1. `uv` builds the venv and installs dependencies from `uv.lock`.
2. The game downloads the base-game asset archives (`crimson.paq`, `music.paq`,
   `sfx.paq`) from `https://paq.crimson.banteg.xyz/v1.9.93` into its runtime dir.
3. It boots into a test-mode Survival run.

To keep saves / logs / downloaded assets inside the checkout instead of your
per-user data dir:

```powershell
$env:CRIMSON_RUNTIME_DIR = "$PWD\artifacts\runtime"
uv run crimson --test-mode --no-intro
```

### What `--test-mode` does here

- No auto-spawned bonuses and no forced weapon drop (both `_TEST_MODE_*`
  hooks in `bonuses/update.py` are empty).
- Unlocks the whole fireable weapon set for drops (`weapon_runtime/availability.py`),
  so every weapon can turn up on a Weapon bonus without grinding quest unlocks.

`--debug` adds gameplay cheats: `[` / `]` cycle weapons, `F2` god mode,
`F3` grant a perk, `X` +5000 XP. Other flags: `--seed N` (deterministic),
`--no-intro` (skip logos).

---

## 3. Why nothing needs copying

The mod is self-contained in git:

- **Base-game PAQ assets** are *not* in the repo (they're the original game's
  copyrighted data) — they auto-download on first launch, per machine.
- **Mod-added assets** *are* in the repo as best-effort fallbacks that the loader
  uses when the PAQ has no such entry:
  - `src/grim/optional_textures/scythe.tga` — the Evil Scythe sprite
  - `src/grim/optional_sfx/lightning_sound.ogg` — the Arc Gun lightning crackle

So a clean `git clone` + `uv run` is a fully working build.

---

## 4. Tests

```bash
uv run pytest -q
```

**Known pre-existing failures — not caused by the mod, always ignore:**

- Anything under `tests/native/`, `tests/grim/test_zig_*`, `tests/replay/cli/test_zig_*`,
  `test_match.py`, `test_mod_sdk.py`, `test_library_*.py` — these need a
  capstone / `crimsonland.exe` / zig toolchain that isn't set up here.
- `tests/replay/cli/test_list.py::test_replay_list_shows_replays_under_base_dir` —
  a Windows path-display quirk, unrelated.

A focused run that should be **fully green**:

```bash
uv run pytest tests/weapons tests/sim tests/bonuses tests/render tests/progression tests/projectiles -q
```

Lint / typecheck (optional): `uv run ruff check .` · `uv run ty check src`

---

## 5. Two-machine workflow

Each machine has its **own** clone and its **own** Claude Code session — sessions
don't share history or execution. Git is the only sync layer.

```bash
# before starting work on a machine
git pull

# after making changes
git add -A
git commit -m "..."
git push
```

Both `master` and `feat/roguelite-weapons` are kept pointing at the same commit;
push both if you move one:

```bash
git branch -f master HEAD && git push origin feat/roguelite-weapons master
```

Commit trailer used in this project:

```
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

---

## 6. What's in this branch (mod content so far)

All parity-breaking, all in `src/crimson/`:

| Area | What |
|---|---|
| **Damage types** | Added `ENERGY` (plasma) and `LIGHTNING` (arc gun) as first-class `CreatureDamageType`s with their own scaling lines (`damage_mult_energy`, `damage_mult_lightning`) alongside FIRE / ION. |
| **Plasma clip-heat** | Energy damage ramps 0→+H as the stock clip drains (past +H with a wider clip). WPU raises the floor: +H→+2H over the stock clip (no fire-rate bonus for plasma). Reflex Boost pins it to a flat +H. Bolts glow from base colour at 0 heat to white-hot at +H. `weapon_runtime/plasma_heat.py`, `render/projectile_draw/primary_plasma.py`. |
| **Fire weapons** | WPU gives +30% per-particle damage instead of a no-op fire-rate bump. |
| **WPU** | Normalized to ~+30% DPS across every weapon (native fire-rate ×1.3 / reload ×0.8; scythe = +30% swing damage, plasma = the clip-heat floor, both in `WPU_NO_RATE_WEAPON_IDS`). |
| **Evil Scythe** (`WeaponId.EVIL_SCYTHE`, id 27) | Rewrite-only melee cone sweep on cut content. Heavy/slow: 91.2 dmg/swing, 0.6s cooldown, 1.0s reload, 0.56s sweep. Silent swing. Teal ghoul sprite. WPU widens arc + hardens hit. In the main weapon roster. Code: `weapon_runtime/scythe_sweep.py`, `render/world/scythe.py`. |
| **Arc Gun** (`WeaponId.RAYGUN`, id 33) | Rewrite-only chain lightning. Forms near the cursor, chains to random nearby enemies, damage builds +20% per hop. Fully procedural VFX (`render/world/arc_gun.py`). Own LIGHTNING damage type. Crackle sound once per shot. In the main weapon roster. Code: `weapon_runtime/arc_gun.py`. |
| **Fork Shot / Blade bonuses** | Folded into the normal drop pool in every mode (`fork_bonus_in_pool` default on). Both draw their own icon on the ground and in the HUD (`render/world/bonus_icons.py`) - Fork Shot procedurally, Blade from the orbiting-blade sprite. |
| **Energizer bonus** | Removed - never selected (`bonuses/selection.py`) and no apply handler. The inert flee/eat mechanic code stays. |
| **Character-anchored HUD** | Health as a depleting red ring around the player, clip ammo as a number at its upper-right, active power-ups as a FIFO icon stack at its upper-left with per-icon seconds. Top-bar heart / health bar / ammo pips and the sliding bonus panel are suppressed. `render/world/player_status.py`, flags in `ui/hud.py`. |
| **Window** | Renders to a virtual resolution that tracks the window aspect and blits full-screen - resizable / maximise / fullscreen with no bars or distortion. `grim/letterbox.py`, `grim/app.py`. |
| **Progression** | `crimson.progression` composable stat/modifier layer (`PlayerStats`, `StatMod`, `resolve_stats`), the hook for perks / relics / affixes. |
| **Test / debug** | `--test-mode`: no forced spawns, unlocks every fireable weapon for drops. `--debug`: `[`/`]` cycle fireable weapons, `F2` god, `F3` +perk, `X` +5000 XP. |

The "no projectile, flag on player, resolve in `WorldState.step`" pattern backs
both new weapons (see `bonuses/blade_orbit.py` for the original precedent).

---

## 7. If the game won't launch

- **Asset download fails / offline** — you need network on first launch. Once the
  PAQs are in the runtime dir they're cached.
- **Wayland (Linux)** — raylib wheels are X11-oriented; you may need
  `xwayland` + `libX11`.
- **`uv` not found after install** — restart the shell so PATH updates.
