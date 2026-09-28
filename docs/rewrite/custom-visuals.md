---
tags:
  - rewrite
  - rendering
  - modules
---

# Custom visuals (rewrite-only content)

How to change or add visuals for the rewrite's own content (relics, monster
affixes, perk indicators): where they're drawn, how to add a sprite, how to
animate it, and how to turn a downloaded GIF into something the game can use.
It ends with the Cinderburst flame experiment as a worked example.

## Where things are drawn

Almost every rewrite-only world visual lives in
`src/crimson/render/world/draw.py`. `draw_world()` calls the passes in this
order (later draws on top):

1. `background`: ground texture (`grim/terrain_render.py`)
2. dead players, `creatures` (+ Hit List marker, Impale tally, First Strike marks)
3. freeze overlay
4. ground-level indicators: Critical Mass radius, Deadeye ring,
   `draw_warbanners`, `draw_pending_detonation_warnings` (Bomber),
   `draw_pending_area_effect_warnings` (Cinderburst / Gravemark), vortex trails
5. living players, projectiles and effects, blade orbits, scythe swings, arc bolts
6. bonuses, aim indicators, hover tooltips

To restyle an existing effect, find its `draw_*` function; its tuning
constants sit just above it (colours, alphas, sizes). For example:

| Effect | Function | Constants |
| --- | --- | --- |
| Bomber / Cinderburst / Gravemark warning ring | `_draw_fuse_countdown_ring` | `_FUSE_RING_*`, `_FUSE_ZONE_*` |
| Cinderburst live zone (orange disc + outline) | `draw_pending_area_effect_warnings` | `_AREA_EFFECT_COLORS`, `_FUSE_ZONE_TRIGGERED_*` |
| Gravemark live zone (radial fade) | `_draw_radial_fade_fill` | `_GRAVEMARK_FADE_*` |
| War Banner | `draw_warbanners` | `_WARBANNER_*` |

Gameplay numbers (radius, duration, damage) are **not** here; they live with
the mechanic, e.g. `PYRE_RADIUS` / `PYRE_DURATION_S` in
`src/crimson/creatures/rarity.py`. Renderers read them; never duplicate them.

## Coordinates and alpha

- Game state is in **world units** (the arena is 1024 x 1024). Convert with
  `render_ctx._world_to_screen_with(pos, camera=ctx.camera, view_scale=ctx.view_scale)`.
- Sizes: multiply world-unit sizes by `ctx.scale` to get screen pixels.
- Multiply every alpha by `ctx.entity_alpha` (the world fades out behind
  menus through it).
- Screen size and mouse come from `rl.get_screen_width()` /
  `rl.get_mouse_position()` as usual; `grim/letterbox.py` makes those report
  the logical layout size, so draw code never deals with the real window size.

## Adding a sprite

Rewrite-only textures aren't in the original game's `.paq` files; they're
committed PNGs with a fallback loader.

1. Put the PNG in `src/grim/optional_textures/` (e.g. `my_effect.png`).
2. Add an id to `TextureId` in `src/grim/assets.py` (next to `WARBANNER`),
   with a comment saying what uses it.
3. Register it in `OPTIONAL_TEXTURE_SPECS`:
   `TextureId.MY_EFFECT: TextureSpec("game/my_effect.png", clamp=True, point_filter=True)`.
   The loader matches on the **file name**, so the `game/` prefix is just the
   path it would have inside a `.paq`.
   - `point_filter=True` for pixel art (keeps pixels sharp when scaled);
     leave it off for smooth/painted art.
   - `clamp=True` stops edge pixels bleeding from the opposite side.
4. In the draw function:
   `texture = render_ctx.frame.resources.texture_optional(TextureId.MY_EFFECT)`,
   and skip drawing when it's `None` (a stripped build or a test without
   assets).
5. Draw with `rl.draw_texture_pro(texture, src_rect, dst_rect, rl.Vector2(0, 0), 0.0, tint)`,
   putting the alpha in `tint`.

The alpha-tester exe build bundles everything under `src/grim` (PyInstaller
`--collect-all grim`), so new PNGs ship automatically.

## Animating a sprite

- Pack frames **side by side** in one PNG (a horizontal strip); frame `i`'s
  source rect is `x = i * frame_w`.
- Drive the frame from **game time**, not the wall clock, so pausing and
  slow-motion work: e.g. an effect's own elapsed time
  (`DURATION - effect.duration`). `frame = int(elapsed / frame_s) % frame_count`.
- When drawing many copies, give each its own frame offset (`phase`) so they
  don't flicker in lockstep.
- Keep per-instance placement **deterministic** (seed a local
  `random.Random` from the effect's position) so things don't jump around
  between frames. Never draw from the sim RNG (`state.rng`) in render code;
  it would desync replays.
- A short fade-in/out (multiply alpha by `min(1, elapsed / t_in, remaining / t_out)`)
  hides pop-in.

## Turning a GIF into a sprite strip

Pillow is already a dependency. The checks worth doing on any downloaded GIF:

```python
from PIL import Image
im = Image.open("fire.gif")
print(im.size, im.n_frames, im.info.get("duration"), im.info.get("transparency"))
im.seek(0); print(im.convert("RGBA").getpixel((0, 0)))   # alpha 0 => real transparency
```

- **Frame timing:** `duration` is milliseconds per frame; use it as `frame_s`.
- **Upscaled pixel art:** most pixel-art GIFs are scaled up (e.g. every art
  pixel is a 6x6 or 32x32 block). Find the block size (run lengths of equal
  pixels along a row), crop to the union bounding box of the sprite across
  **all** frames (snapped to the block grid), then shrink with
  `Image.NEAREST` by the block size. Round-trip back up and compare to prove
  it's lossless. The game rescales it with `point_filter`, so nothing is lost.
- **Fake transparency:** if the "transparent" background is a baked-in grey
  checkerboard (corner pixel has alpha 255), key it out by colour. For fire,
  "keep saturated warm pixels" works well:
  `r > g and r >= b and (r - min(g, b)) > 40`. That keeps outlines and embers
  and drops every grey.
- **Limitation:** semi-transparent parts drawn over a baked checkerboard
  (smoke, glows) can't be recovered cleanly; you can only keep or drop them.
  Prefer assets with real transparency (PNG sheets / GIFs whose background
  alpha is 0).
- Look at the result before wiring it in: composite the frames on a dark
  background, scale up 5x with `NEAREST`, save a PNG and open it.

## Checking a change

- **In game:** `CRIMSON_RUNTIME_DIR="$PWD/artifacts/runtime" uv run crimson --test-mode --no-intro`,
  then **Sandbox**. The debug panel's **Monster Mods** tab picks a rarity and
  exact affixes for the next F7/F8 spawn (e.g. Cinderburst), and time scale
  0.1x helps with fast effects.
- **Offline preview:** render the layout with Pillow using the same helper
  the draw code uses (e.g. the spot generator), so you can iterate without
  launching.
- **Tests:** `uv run pytest -q tests`. Tests run without a window, so raylib
  **draw and render-target calls in shared paths crash** (access violation)
  unless guarded. Guard GPU-only work with `rl.is_window_ready()`, and keep
  new draw paths behind conditions that tests don't hit by accident.

## Worked example: Cinderburst flames (tried, reverted)

Goal: replace Cinderburst's flat orange disc with animated fire. What was
tried (September 2026):

1. `fire.gif`: 4-frame 8x11 pixel flame (32x32 blocks, real transparency),
   10 flames placed on the circle (7 near the edge, 3 inside), 55% alpha,
   looping at 170 ms. Verdict: too low-detail.
2. `betterfire.gif` (2nd fire of 5): 8-frame 31x44 flame (6x6 blocks,
   baked checkerboard keyed out as above, smoke dropped), 100 ms frames,
   28 world units tall.
3. Disc and outline removed; the whole 90-unit zone filled with ~92 flames in
   a jittered honeycomb (18 x 14 spacing, 4-unit jitter), 50% alpha, each
   flame's base placed so its body stays inside the circle. Verdict: still
   read as rows of identical sprites; reverted to the disc pending better art.

The code shape that worked, for reuse:

```python
# in draw_pending_area_effect_warnings, live phase:
if int(effect.kind) == int(monster_rarity._AreaEffectKind.PYRE):
    _draw_cinderburst_flames(render_ctx, ctx=ctx, effect=effect)
    continue

def _draw_cinderburst_flames(render_ctx, *, ctx, effect):
    texture = render_ctx.frame.resources.texture_optional(TextureId.CINDERBURST_FIRE)
    if texture is None:
        return
    elapsed = max(0.0, monster_rarity.PYRE_DURATION_S - float(effect.duration))
    fade = min(1.0, elapsed / FADE_IN_S, max(0.0, float(effect.duration)) / FADE_OUT_S)
    tint = rl.Color(255, 255, 255, int(clamp(ALPHA * fade * ctx.entity_alpha, 0.0, 1.0) * 255))
    frame_w = texture.width / FRAME_COUNT
    flame_h = FLAME_H * ctx.scale
    flame_w = flame_h * frame_w / texture.height
    tick = int(elapsed / FRAME_S)
    for off_x, off_y, phase in flame_spots(effect):   # cached, seeded from effect.pos
        frame = (tick + phase) % FRAME_COUNT
        base = render_ctx._world_to_screen_with(
            Vec2(effect.pos.x + off_x, effect.pos.y + off_y), camera=ctx.camera, view_scale=ctx.view_scale,
        )
        dst = rl.Rectangle(base.x - flame_w / 2, base.y - flame_h, flame_w, flame_h)   # anchored at its base
        src = rl.Rectangle(frame_w * frame, 0, frame_w, texture.height)
        rl.draw_texture_pro(texture, src, dst, rl.Vector2(0, 0), 0.0, tint)
```

Ideas not yet tried: a single larger fire sheet designed as an area (not
tiled copies); fewer flames with random size and flip; a radial fade fill
under a handful of flames; embers as particles instead of sprites.
