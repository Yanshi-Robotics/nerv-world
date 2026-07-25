#!/usr/bin/env python3
"""程序化生成材质贴图（PNG）→ textures/。

为什么要贴图：纯色方块看着像积木；贴上木地板纹路、卫生间瓷砖、大理石台面、地毯织物之后，
同样的几何体立刻有"室内场景"的质感。这是在 MuJoCo 里能拿到的最大一笔视觉提升。

⚠️ 能力边界（如实说）：这些是**程序化生成的漫反射贴图**，没有法线/粗糙度贴图，
   也没有全局光照——做得到"精致的风格化游戏场景"，做不到 GTA 那种美术手工资产的水平。

用法： python make_textures.py        # 生成/覆盖 textures/*.png
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "textures")

RNG = np.random.default_rng(20260725)   # 固定种子：每次生成的贴图一致，便于复现


def _save(name: str, arr: np.ndarray) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(os.path.join(OUT_DIR, name))
    print("  ", name, arr.shape[:2])


def _noise(h: int, w: int, scale: float = 1.0) -> np.ndarray:
    """低频噪声（把随机点放大插值），用来做木纹、石纹的底子。"""
    small = RNG.normal(0, 1, (max(2, int(h * scale)), max(2, int(w * scale))))
    return np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC))


def wood_floor(h=512, w=512, plank_h=64, base=(150, 108, 72)) -> np.ndarray:
    """木地板：一条条错缝铺装的板材，每块颜色略有差异 + 顺纹木纹。"""
    img = np.zeros((h, w, 3), float)
    grain = _noise(h, w, 0.35) * 9 + _noise(h, w, 0.9) * 4      # 木纹（细长方向靠下面拉伸实现）
    for row, y0 in enumerate(range(0, h, plank_h)):
        y1 = min(h, y0 + plank_h)
        offset = (row * 137) % w                                  # 错缝
        for x0 in range(-offset % 160 - 160, w, 160):             # 每块板长 160px
            x1 = min(w, x0 + 160)
            if x1 <= 0:
                continue
            tint = RNG.uniform(-16, 16)                           # 每块板深浅不同
            for c in range(3):
                img[y0:y1, max(0, x0):x1, c] = base[c] + tint
            # 板缝（暗线）
            if x1 < w:
                img[y0:y1, max(0, x1 - 2):x1] *= 0.62
        img[max(0, y1 - 2):y1] *= 0.62                            # 横向板缝
    img += grain[..., None]
    return img


def tile(h=512, w=512, n=8, base=(226, 228, 230), grout=(176, 180, 184)) -> np.ndarray:
    """瓷砖：规整方格 + 砖缝 + 轻微色差（卫生间/厨房地面墙面）。"""
    img = np.zeros((h, w, 3), float)
    step = h // n
    for i in range(n):
        for j in range(n):
            tint = RNG.uniform(-7, 7)
            img[i * step:(i + 1) * step, j * step:(j + 1) * step] = np.array(base) + tint
    g = 4
    for i in range(n + 1):
        img[max(0, i * step - g // 2): i * step + g // 2, :] = grout
        img[:, max(0, i * step - g // 2): i * step + g // 2] = grout
    return img + _noise(h, w, 0.6)[..., None] * 2.5


def marble(h=512, w=512, base=(238, 238, 240)) -> np.ndarray:
    """大理石：底色近白 + 几条走向一致的深色脉络（台面用）。"""
    img = np.full((h, w, 3), float(base[0]))
    img[..., 1], img[..., 2] = base[1], base[2]
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(7):                                            # 若干条脉络
        k = RNG.uniform(-1.6, 1.6)
        b = RNG.uniform(0, h)
        width = RNG.uniform(1.5, 5.0)
        wobble = _noise(h, w, 0.25) * 22
        d = np.abs(yy - (k * xx + b) - wobble)
        vein = np.exp(-(d / width) ** 2) * RNG.uniform(28, 60)
        img -= vein[..., None]
    return img + _noise(h, w, 0.8)[..., None] * 2


def carpet(h=256, w=256, base=(178, 150, 128)) -> np.ndarray:
    """地毯：细密绒毛感（高频噪声）+ 轻微色块起伏。"""
    fuzz = RNG.normal(0, 7.5, (h, w))
    low = _noise(h, w, 0.15) * 8
    img = np.array(base, float)[None, None, :] + (fuzz + low)[..., None]
    return img


def fabric(h=256, w=256, base=(150, 136, 116)) -> np.ndarray:
    """织物：经纬交织的细网格（沙发/床品用）。"""
    yy, xx = np.mgrid[0:h, 0:w]
    weave = (np.sin(xx * np.pi / 3) * np.sin(yy * np.pi / 3)) * 5.5
    img = np.array(base, float)[None, None, :] + weave[..., None] + RNG.normal(0, 2.5, (h, w, 1))
    return img


def wall_paint(h=256, w=256, base=(228, 220, 208)) -> np.ndarray:
    """墙面：微微的批刮质感（艺术漆），避免大白墙一片死板。"""
    img = np.array(base, float)[None, None, :] + (_noise(h, w, 0.12) * 5)[..., None]
    return img + RNG.normal(0, 1.6, (h, w, 1))


def city_skyline(h=768, w=2048) -> np.ndarray:
    """城市天际线：远处高楼剪影 + 窗格灯光 + 空气透视（越远越淡）。

    贴在屋外的"背景板"上——窗户望出去就是城市，屋子才不像孤零零一个盒子。
    这是游戏里常用的 matte painting 手法：不建真楼，用一张远景图糊住地平线。
    """
    # 天空：上深下浅的渐变
    img = np.zeros((h, w, 3), float)
    for y in range(h):
        t = y / h
        img[y] = np.array([120 + 95 * t, 155 + 75 * t, 200 + 45 * t])
    horizon = int(h * 0.78)
    # 三层楼群，越靠后越淡越矮（空气透视）
    for layer, (fade, hmin, hmax, wmin, wmax) in enumerate(
            [(0.62, 0.16, 0.42, 40, 110), (0.78, 0.22, 0.56, 50, 130), (1.0, 0.28, 0.72, 60, 160)]):
        x = 0
        while x < w:
            bw = int(RNG.integers(wmin, wmax))
            bh = int(h * RNG.uniform(hmin, hmax))
            top = horizon - bh
            base = np.array([96, 104, 118]) * fade + np.array([150, 168, 195]) * (1 - fade)
            base = base + RNG.uniform(-10, 10)
            img[top:horizon, x:min(w, x + bw)] = base
            # 窗格灯光（只给最近那层，远的看不清）
            if layer == 2 and bh > h * 0.3:
                for wy in range(top + 12, horizon - 10, 22):
                    for wx in range(x + 8, min(w, x + bw) - 8, 18):
                        if RNG.random() < 0.45:
                            img[wy:wy + 9, wx:wx + 9] = base + RNG.uniform(35, 75)
            x += bw + int(RNG.integers(4, 18))
    # 地平线以下：城市地面雾霭
    img[horizon:] = np.array([118, 128, 132]) + _noise(h - horizon, w, 0.3)[..., None] * 6
    return img


def artwork(h=512, w=512, style=0) -> np.ndarray:
    """墙上挂画：几种抽象风格。用作视觉干扰项——让 ANIMA 必须靠真正的房间特征判断，
    而不是"墙上有东西"就乱猜。"""
    img = np.full((h, w, 3), 244.0)
    if style == 0:      # 色块构成
        for _ in range(6):
            x0, y0 = RNG.integers(0, w - 120, 2)
            bw, bh = RNG.integers(90, 240, 2)
            col = RNG.uniform(40, 210, 3)
            img[y0:min(h, y0 + bh), x0:min(w, x0 + bw)] = col
    elif style == 1:    # 水墨泼染
        yy, xx = np.mgrid[0:h, 0:w]
        for _ in range(4):
            cx, cy = RNG.integers(80, w - 80), RNG.integers(80, h - 80)
            rad = RNG.uniform(50, 150)
            blob = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad ** 2)))
            img -= (blob * RNG.uniform(90, 200))[..., None]
    elif style == 2:    # 横向色带
        y = 0
        while y < h:
            bh = int(RNG.integers(30, 90))
            img[y:min(h, y + bh)] = RNG.uniform(60, 225, 3)
            y += bh
    else:               # 单色 + 细线条
        img[:] = RNG.uniform(180, 235, 3)
        for _ in range(14):
            y = int(RNG.integers(0, h))
            img[y:y + RNG.integers(2, 7)] = RNG.uniform(30, 110, 3)
    # 画框留白边
    img[:18] = img[-18:] = img[:, :18] = img[:, -18:] = 250
    return img


def oven_glass(h=256, w=256) -> np.ndarray:
    """烤箱/洗碗机的玻璃门：近黑的深色玻璃，斜向一道高光，隐约透出里面的烤架横线。

    真实烤箱门就是这个样子——正因为它又黑又亮、上面横着几道烤架，才成为厨房里
    最好认的一件东西（比清一色的柜门辨识度高得多）。
    """
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0], img[..., 1], img[..., 2] = 26, 27, 30      # 深炭灰底
    # 斜向高光带（玻璃反光）
    diag = ((xx * 0.7 + yy * 0.3) / (w * 0.7 + h * 0.3))
    glare = np.exp(-((diag - 0.32) ** 2) / 0.008) * 46
    img += glare[..., None]
    # 里面隐约的烤架：三道横线
    for frac in (0.34, 0.55, 0.76):
        band = np.exp(-((yy / h - frac) ** 2) / 2.0e-5) * 22
        img += band[..., None]
    # 玻璃边框内缘
    edge = 10
    img[:edge], img[-edge:], img[:, :edge], img[:, -edge:] = 62, 62, 62, 62
    return np.clip(img + _noise(h, w, 3.0)[..., None] * 3, 0, 255).astype(np.uint8)


def appliance_panel(h=128, w=512) -> np.ndarray:
    """家电控制面板：拉丝不锈钢底 + 一排指示灯 + 一小块显示屏。"""
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0], img[..., 1], img[..., 2] = 186, 190, 196
    img += (np.sin(xx * 1.7) * 4)[..., None]                 # 竖向拉丝
    img += _noise(h, w, 6.0)[..., None] * 5
    # 显示屏（左侧一小块深色）
    img[int(h * 0.3):int(h * 0.7), int(w * 0.08):int(w * 0.26)] = (24, 30, 34)
    # 指示灯：几个小圆点
    for i, col in enumerate([(90, 200, 120), (230, 170, 60), (210, 90, 80)]):
        cx, cy, r = int(w * (0.42 + i * 0.09)), h // 2, 7
        m = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
        img[m] = col
    return np.clip(img, 0, 255).astype(np.uint8)


def main() -> None:
    print("生成材质贴图 →", OUT_DIR)
    _save("wood_floor.png", wood_floor())
    _save("wood_floor_light.png", wood_floor(base=(186, 148, 108), plank_h=56))
    _save("tile_white.png", tile())
    _save("tile_grey.png", tile(base=(150, 152, 156), grout=(112, 115, 120)))
    _save("marble.png", marble())
    _save("marble_dark.png", marble(base=(74, 74, 80)))
    # 厨房与卫生间的地面石材（真实住宅这两处常铺大理石；用不同色号，同一套房里
    # 各房间本来就不会铺一模一样的石头）
    _save("marble_warm.png", marble(base=(226, 214, 196)))   # 暖米色 → 厨房
    _save("marble_grey.png", marble(base=(196, 200, 205)))   # 冷灰色 → 卫生间
    _save("carpet.png", carpet())
    _save("fabric.png", fabric())
    _save("fabric_blue.png", fabric(base=(104, 118, 140)))
    _save("wall_paint.png", wall_paint())
    _save("city_skyline.png", city_skyline())
    _save("oven_glass.png", oven_glass())
    _save("appliance_panel.png", appliance_panel())
    for i in range(4):
        _save(f"art{i}.png", artwork(style=i))
    print("完成。make_house.py 会把这些贴图写进 MJCF 的 <asset>。")


if __name__ == "__main__":
    main()
