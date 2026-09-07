#!/usr/bin/env python3
"""Extract mesh-ready 2D facade/roof tiles from preserved local cube atlases. No network."""

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes.environments import manhattan  # noqa: E402
from scenes.apt.city_materials import TEXTURE_ROOT  # noqa: E402


def main():
    output = ROOT / TEXTURE_ROOT
    output.mkdir(parents=True, exist_ok=True)
    records = {}
    for kind, original, face in (
        ("glass", "tex_h3_fac_glass", "F"),
        ("stone", "tex_h3_fac_stone", "F"),
        ("roof", "tex_h3_fac_glass", "U"),
    ):
        texture = next(t for t in manhattan.TEXTURES_EXTRA if t["name"] == original)
        rows, cols = map(int, texture["gridsize"].split())
        row, col = divmod(texture["gridlayout"].index(face), cols)
        for suffix in ("", "_night"):
            source = ROOT / texture["file"]
            source = source.with_stem(source.stem + suffix)
            with Image.open(source) as image:
                width, height = image.width // cols, image.height // rows
                assert width == height
                tile = image.crop(
                    (col * width, row * height, (col + 1) * width, (row + 1) * height)
                )
                target = output / f"{kind}{suffix}.png"
                tile.save(target)
            records[str(target.relative_to(ROOT))] = dict(
                source=str(source.relative_to(ROOT)),
                face=face,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            )
    (output / "sources.json").write_text(
        json.dumps(
            dict(
                license="MIT; derived from repository-authored facade and roof textures",
                generator="tools/make_city_textures.py",
                tiles=records,
            ),
            indent=2,
        )
        + "\n"
    )
    print(f"Extracted {len(records)} tiles from preserved atlases")


if __name__ == "__main__":
    main()
