#!/usr/bin/env python3
"""生成原创草坪与泳池瓷砖基础色；不覆盖任何标准场景贴图。"""

from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RESOLUTION = 1024
SEED = 907


def main():
    out = ROOT / "textures" / "residences"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    n = RESOLUTION
    # 大范围草色变化叠加细叶纹，不在纹理上烘焙场景光照。
    low = Image.fromarray(rng.integers(60, 190, (24, 24), dtype=np.uint8)).resize(
        (n, n), Image.Resampling.BICUBIC
    )
    noise = (np.asarray(low, dtype=float) - 128) / 128
    detail = rng.normal(0, 1, (n, n))
    rgb = np.stack(
        [70 + noise * 16 + detail * 9, 96 + noise * 24 + detail * 12, 42 + noise * 11 + detail * 6],
        axis=-1,
    )
    Image.fromarray(np.uint8(np.clip(rgb, 0, 255))).save(out / "grass.png")
    yy, xx = np.mgrid[:n, :n]
    tile = n // 8
    variation = rng.uniform(-9, 9, (8, 8))[yy // tile, xx // tile]
    grout = (xx % tile < 3) | (yy % tile < 3)
    rgb = np.stack([74 + variation, 128 + variation, 134 + variation], axis=-1)
    rgb[grout] = [148, 172, 170]
    Image.fromarray(np.uint8(np.clip(rgb, 0, 255))).save(out / "pool_tile.png")
    # 2 m square of pale, straight oak planks; grain and joints have separate scales.
    yy, xx = np.mgrid[:n, :n]
    u = xx / n
    v = yy / n
    boards = 8
    board = (xx // (n // boards)).astype(int)
    tone = rng.uniform(-7, 7, boards)[board]
    grain = np.sin(u * 950 + np.sin(v * 9) * 2 + np.sin(v * 31) * 0.8) * 2.0
    grain += np.sin(u * 3400 + np.sin(v * 17) * 4) * 0.8 + rng.normal(0, 1, (n, n))
    rgb = np.stack([208 + tone + grain, 192 + tone + grain, 164 + tone + grain], axis=-1)
    joints = (xx % (n // boards) < 2) | ((yy + (board % 3) * (n // 3)) % n < 2)
    rgb[joints] *= 0.77
    Image.fromarray(np.uint8(np.clip(rgb, 0, 255))).save(out / "pale_oak.png")
    # Quiet limestone: subtle mineral variation, no large yellow veins.
    stone_noise = rng.normal(0, 1.3, (n, n)) + noise * 3
    rgb = np.stack([191 + stone_noise, 188 + stone_noise, 178 + stone_noise], axis=-1)
    Image.fromarray(np.uint8(np.clip(rgb, 0, 255))).save(out / "limestone.png")
    weave = (np.sin(xx * 2.1) + np.sin(yy * 2.1)) * 1.6 + rng.normal(0, 0.7, (n, n))
    rgb = np.stack([224 + weave, 215 + weave, 198 + weave], axis=-1)
    Image.fromarray(np.uint8(np.clip(rgb, 0, 255))).save(out / "linen.png")
    print("Generated original residence textures:", out)


if __name__ == "__main__":
    main()
