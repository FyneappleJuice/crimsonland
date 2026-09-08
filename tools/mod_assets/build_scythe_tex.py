"""Inject the Evil Scythe blade sprite into the runtime PAQ.

The scythe render (`crimson.render.world.scythe`) loads `game/scythe.tga` from
`crimson.paq` as an *optional* texture - if it is missing the weapon falls back
to a procedural blue arc. This script builds the tinted sprite from
`scythe_source.png` (a 4-wide strip; the rightmost blade is used) and writes it
into the PAQ.

Usage (from the repo root, with the package importable):

    python tools/mod_assets/build_scythe_tex.py [path/to/crimson.paq]

If no PAQ path is given it looks for `../runtime/crimson.paq` relative to the
repo, then `$CRIMSON_RUNTIME_DIR/crimson.paq`.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from PIL import Image

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
sys.path.insert(0, str(_REPO / "src"))

from grim import paq  # noqa: E402

SOURCE = _HERE / "scythe_source.png"
ENTRY = "game/scythe.tga"


def _resolve_paq(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    candidates = [
        _REPO.parent / "runtime" / "crimson.paq",
        Path(os.environ.get("CRIMSON_RUNTIME_DIR", "")) / "crimson.paq",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise SystemExit("could not find crimson.paq - pass its path as an argument")


def build_sprite() -> Image.Image:
    src = Image.open(SOURCE).convert("RGBA")
    cell = src.width // 4
    sprite = src.crop((3 * cell, 0, 4 * cell, src.height))  # rightmost blade

    bbox = sprite.getchannel("A").getbbox()
    sprite = sprite.crop(bbox)
    side = max(sprite.size) + 4
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, ((side - sprite.width) // 2, (side - sprite.height) // 2))

    # ghoulish: spectral teal, see-through
    px = canvas.load()
    for y in range(canvas.height):
        for x in range(canvas.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            lum = (r + g + b) / 3.0
            px[x, y] = (
                min(255, int(lum * 0.16 + 6)),
                min(255, int(lum * 0.78 + 55)),
                min(255, int(lum * 0.72 + 60)),
                int(a * 0.52),
            )
    return canvas.resize((canvas.width * 4, canvas.height * 4), Image.NEAREST)


def main() -> None:
    paq_path = _resolve_paq(sys.argv)
    sprite = build_sprite()
    buf = io.BytesIO()
    sprite.save(buf, format="TGA")
    entries = dict(paq.iter_entries(paq_path))
    was = ENTRY in entries
    entries[ENTRY] = buf.getvalue()
    paq.write_paq(str(paq_path), list(entries.items()))
    print(f"{'replaced' if was else 'added'} {ENTRY} in {paq_path} ({len(buf.getvalue())} bytes, {sprite.size})")


if __name__ == "__main__":
    main()
