#!/usr/bin/env python3
"""Generate deterministic, seam-continuous hillside sky faces offline (no network)."""

from pathlib import Path
import sys
import argparse
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes.house.time_presets import PHASES, SUN_DIRECTIONS
from tools.make_view import SKY_FACE_FOR_DIR, _equirect_face

FACE_PIXELS = 256  # Sky is distant background; keeps four phases small and fast to upload.
COLORS = {
    "day": ((0.23, 0.46, 0.72), (0.78, 0.84, 0.89)),
    "morning": ((0.20, 0.38, 0.62), (0.94, 0.73, 0.48)),
    "dusk": ((0.16, 0.20, 0.38), (0.84, 0.40, 0.24)),
    "night": ((0.009, 0.015, 0.035), (0.055, 0.065, 0.10)),
}


def generate(pixels=FACE_PIXELS):
    out = ROOT / "textures/residences/house/sky"
    out.mkdir(parents=True, exist_ok=True)
    h, w = pixels * 2, pixels * 4
    lat = np.pi / 2 - np.arange(h)[:, None] * np.pi / (h - 1)
    lon = np.arange(w)[None, :] * 2 * np.pi / (w - 1) - np.pi
    x = np.cos(lat) * np.cos(lon)
    y = np.cos(lat) * np.sin(lon)
    z = np.broadcast_to(np.sin(lat), (h, w))
    # Continuous directional texture supplies unique faces without visible cubemap seams.
    haze = np.exp(-np.abs(z) * 3.4)[..., None]
    cloud = (np.sin(9 * x + 3 * y + 4 * z) + np.sin(5 * y - 6 * z) + np.sin(13 * x - 8 * y)) / 3
    cloud = np.maximum(0, cloud - 0.2)[..., None] * np.maximum(z, 0)[..., None]
    for phase in PHASES:
        zenith, horizon = (np.array(c) for c in COLORS[phase])
        sky = zenith[None, None, :] * (1 - haze) + horizon[None, None, :] * haze
        sunlight = -np.array(SUN_DIRECTIONS[phase])
        sunlight /= np.linalg.norm(sunlight)
        dot = x * sunlight[0] + y * sunlight[1] + z * sunlight[2]
        glow = np.exp((dot - 1) * 18)[..., None]
        sky += glow * np.array((0.25, 0.16, 0.07)) * (0.08 if phase == "night" else 1)
        sky += cloud * (0.007 if phase == "night" else 0.075)
        # Directional horizon variation preserves identifiable day faces for MuJoCo matching.
        sky += ((0.5 + 0.5 * x)[..., None]) * np.array((0.012, 0.007, 0.003))
        eq = (np.clip(sky, 0, 1) * 255).astype(np.uint8)
        for direction, slot in SKY_FACE_FOR_DIR.items():
            up = (0, 1, 0) if direction[2] else (0, 0, 1)
            face = _equirect_face(eq, direction, up, pixels)
            prefix = "sky_" if phase == "day" else f"sky_{phase}_"
            Image.fromarray(face).save(out / f"{prefix}{slot}.png")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixels", type=int, default=FACE_PIXELS)
    args = parser.parse_args()
    if args.pixels < 32:
        parser.error("--pixels must be at least 32")
    print(generate(args.pixels))
