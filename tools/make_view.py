#!/usr/bin/env python3
"""生成 apt1 的窗景贴图（俯瞰中央公园 + 曼哈顿街网）→ textures/house3/。

⚠️ 贴图目录沿用场景最早的名字 house3（见下面 TEX_SUBDIR 的注释），场景 key 是 apt1。

为什么窗景要用**几何 + 俯视贴图**，不用一张平视照片：

  1. ⛔ 全网不存在一张宽松许可的、从高层俯瞰中央公园的 360° 全景图。查穷尽了：
     Wikimedia 的"等距柱状投影全景"分类共 543 张，没有一张美国大城市；
     `360° panoramas of New York City` 这个分类根本不存在。
  2. ⭐ 照片**没有视差**。相机在屋里一走动，贴片的假立刻穿帮——而这是个物理仿真，
     相机一定会动。
  3. ⭐ 照片的**俯角是错的**。酒店楼层拍的全景对不上 62 层的俯角，属于"看着挺好其实是错的"。
     水平地面板的俯角是**由几何天然保证**的。
  4. ⭐ 水平板是 MuJoCo 给基本体贴 2D 图**唯一投影正确**的朝向——它沿几何体局部 Z 轴投影，
     所以只有法线朝 Z 的面才对。本仓的地板一直是对的、城市背景板一直是条纹，就是这个原因。

⚠️ MuJoCo 的贴图只吃 **PNG / KTX / 自有格式，而且是 8 位**（`tex_data` 是 `mjtByte*`，
   PNG 加载器写死 `bitdepth = 8`）。**没有 HDR、没有 EXR、没有 JPEG。**

用法：
    python tools/make_view.py --naip            # ⭐ 抓真实航拍（USGS NAIP，公共领域）—— 效果最好
    python tools/make_view.py --procedural      # 程序化生成（不联网，NAIP 抓不到时的兜底）
    python tools/make_view.py --facades         # 塔楼立面贴图（窗格），不联网
    python tools/make_view.py --calib           # 生成天空盒六面标定图（每面一个大字母）

⛔ 关于 ODbL 防火墙（将来接 OSM / NYC Open Data 时必读）：
   提交进仓的只能是**渲染出来的图片**（ODbL §4.3 的"产出作品"，只需署名、没有 share-alike）
   和**生成脚本**。⛔ 绝不把从 OSM 抽出来的几何数据入库——那可能构成"派生数据库"，
   会把 share-alike 传染进这个 MIT 仓。将来若有人想"把几何缓存下来加快构建"，就是踩这条线。
   用 NYC Open Data 当主源可以连这层顾虑都省掉（纽约市 Local Law 11 没有 share-alike 概念）。
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
#    这条规矩是为了 review 时一眼看得出有没有漏改：任何落点错误都会在
#    tools/ 下长出一个目录（`ls tools/ | grep -v '\.py$'` 必须为空）。

# 这个脚本只服务一个场景，名字散在四五处过，提成常量。
SCENE_KEY = "apt1"       # `scenes/<这里>/nyc_massing.py` 的落点
# ⛔ 贴图目录**有意**沿用它最早的名字 `house3`：那 9 张材质的文件名本身就叫 `h3_oak.png`，
#    只改目录会造出 `textures/apt1/h3_oak.png` 这种新的不一致。它是这个场景的
#    **资产命名空间**，不是场景 key。详见 README「建造顺序」那一节。
TEX_SUBDIR = "house3"

OUT_DIR = os.path.join(ROOT, "textures", TEX_SUBDIR)

RNG = np.random.default_rng(20260805)   # 固定种子：每次生成一致，便于复现和 diff

# ---------------------------------------------------------------- 真实地理尺寸
# 曼哈顿网格的真实尺寸，公园里每一处地物的位置都由这几个数推出来，不写死像素坐标。
BLOCK_NS_M = 80.5          # 一个街区南北向长度（20 个街区 = 1 英里）
AVENUE_EW_M = 274.0        # 相邻两条大道的东西向间距（曼哈顿"长街区"）
PARK_W_M = 800.0           # 中央公园东西宽（五大道 ↔ 中央公园西大道）
PARK_L_M = 4110.0          # 中央公园南北长（59 街 ↔ 110 街 = 51 个街区）

# 公园里各处地物：(名字, 南起第几街, 北至第几街, 东西向中心占比, 东西向宽占比)
# 街号以 59 街（公园南界）为 0 起算，往北递增。
PARK_FEATURES = [
    # 水面
    ("pond",      1,   3,  +0.33, 0.26, "water"),   # 东南角的 The Pond
    ("lake",     12,  19,  -0.05, 0.62, "water"),   # The Lake（71–78 街）
    ("reservoir", 27,  37,  0.00, 0.78, "water"),   # 肯尼迪水库（86–96 街）
    ("meer",     46,  50,  +0.20, 0.44, "water"),   # 北端的 Harlem Meer
    # 草坪
    ("sheep",     7,  10,  -0.22, 0.40, "lawn"),    # Sheep Meadow（66–69 街）
    ("greatlawn",20,  26,  -0.02, 0.46, "lawn"),    # Great Lawn（79–85 街）
    ("northmdw", 40,  45,  -0.10, 0.50, "lawn"),    # North Meadow
]
# 横穿公园的四条下沉式横道（真实存在：65 / 79 / 86 / 97 街）
TRANSVERSE_STREETS = (6, 20, 27, 38)

# 配色（俯视图观感；不是随手取的，都对着航拍照片调过）
C_CANOPY = (58, 84, 46)        # 树冠
C_CANOPY2 = (74, 100, 58)      # 树冠亮部
C_LAWN = (108, 138, 72)        # 草坪
C_WATER = (52, 78, 92)         # 水面
C_PATH = (150, 142, 126)       # 园路
C_ROAD = (86, 86, 90)          # 车行道
C_ROOF = (128, 126, 124)       # 屋顶灰
C_STREET = (62, 62, 66)        # 城市街道


def _noise(h: int, w: int, scale: float = 1.0) -> np.ndarray:
    """低频噪声（把随机点放大插值）—— 和 make_textures.py 同一套手法，保持观感一致。"""
    small = RNG.normal(0, 1, (max(2, int(h * scale)), max(2, int(w * scale))))
    return np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC))


def _save(name: str, arr: np.ndarray) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path)
    print(f"   {name:22s} {arr.shape[1]}×{arr.shape[0]}")


# ---------------------------------------------------------------- 公园俯视图
def park_aerial(px_per_m: float = 1.0) -> np.ndarray:
    """中央公园的俯视贴图。贴在窗外脚下那块**水平**板上。

    ⭐ 每一处地物的位置都从 `PARK_FEATURES` 的真实街号算出来，不写死像素。
       改公园长宽只改上面的常量，这里跟着变。
    """
    w = int(PARK_W_M * px_per_m)
    h = int(PARK_L_M * px_per_m)
    # 底子：树冠 —— 两级噪声叠出"一片一片的树"而不是均匀绿
    img = np.zeros((h, w, 3), float)
    blob = _noise(h, w, 0.03) * 1.0 + _noise(h, w, 0.10) * 0.6
    t = np.clip((blob - blob.min()) / (blob.ptp() + 1e-9), 0, 1)[..., None]
    img = np.array(C_CANOPY) * (1 - t) + np.array(C_CANOPY2) * t
    img += _noise(h, w, 0.5)[..., None] * 7          # 细颗粒，远看是树的质感

    def _rect(street_a, street_b, cx_frac, w_frac):
        """把"第几街到第几街 + 东西向占比"换算成像素矩形。"""
        y0 = int(street_a * BLOCK_NS_M * px_per_m)
        y1 = int(street_b * BLOCK_NS_M * px_per_m)
        cw = w_frac * w
        x0 = int(w / 2 + cx_frac * w - cw / 2)
        return max(0, x0), max(0, y0), min(w, int(x0 + cw)), min(h, y1)

    yy, xx = np.mgrid[0:h, 0:w]
    # 边缘噪声：让水面/草坪的轮廓不规则，否则一眼是"贴上去的椭圆"
    wobble = _noise(h, w, 0.08) * 0.10
    water_mask = np.zeros((h, w))                    # 记下哪里是水——园路不许画到水上
    for name, sa, sb, cxf, wf, kind in PARK_FEATURES:
        x0, y0, x1, y1 = _rect(sa, sb, cxf, wf)
        if x1 <= x0 or y1 <= y0:
            continue
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        d2 = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 + wobble
        # ⚠️ 边缘收窄到 0.06：先前用 0.3，水面糊成一团光晕、不像水
        a = np.clip((1.0 - d2) / 0.06, 0, 1)
        col = np.array(C_WATER if kind == "water" else C_LAWN, float)
        img = img * (1 - a[..., None]) + col * a[..., None]
        if kind == "water":
            water_mask = np.maximum(water_mask, a)
            img += (a * _noise(h, w, 0.3) * 6)[..., None]   # 水面的细碎反光

    land = 1.0 - water_mask                          # 只有陆地才有园路

    # 园路：画到独立的 alpha 层上，再乘以陆地掩码合成。
    # ⚠️ 先前直接往画布上画长直线，结果是几十道横穿全园、还压过湖面的"划痕"。
    #    真实园路是短的、绕的、不进水的。
    paths = Image.new("L", (w, h), 0)
    pd = ImageDraw.Draw(paths)
    seg = max(1, int(28 * px_per_m))                 # 一步走多远（米→像素）
    for _ in range(150):
        px, py = RNG.integers(0, w), RNG.integers(0, h)
        ang = RNG.uniform(0, 2 * np.pi)
        pts = [(int(px), int(py))]
        for _ in range(RNG.integers(4, 9)):          # 每条路 4–8 段，走走停停
            ang += RNG.uniform(-0.9, 0.9)            # 缓慢转向 → 曲线而不是折线
            px += np.cos(ang) * seg
            py += np.sin(ang) * seg
            if not (0 <= px < w and 0 <= py < h):
                break
            pts.append((int(px), int(py)))
        if len(pts) > 1:
            pd.line(pts, fill=255, width=max(1, int(2.5 * px_per_m)))
    pa = (np.asarray(paths).astype(float) / 255.0) * land * 0.85
    img = img * (1 - pa[..., None]) + np.array(C_PATH, float) * pa[..., None]

    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(canvas)
    # 四条横穿公园的下沉式横道（真实存在：65 / 79 / 86 / 97 街）
    for s in TRANSVERSE_STREETS:
        y = int(s * BLOCK_NS_M * px_per_m)
        d.line([(0, y), (w, y)], fill=C_ROAD, width=max(2, int(11 * px_per_m)))
    # 环园车道（那条著名的跑步/骑行环线）：沿公园内缘一圈
    inset = int(0.10 * w)
    d.rounded_rectangle([inset, inset, w - inset, h - inset],
                        radius=int(0.30 * w), outline=C_ROAD,
                        width=max(2, int(9 * px_per_m)))
    return np.asarray(canvas).astype(float)


# ---------------------------------------------------------------- 城市底图
def city_ground(size_px: int = 2048, span_m: float = 8000.0) -> np.ndarray:
    """公园之外的曼哈顿街网底图，铺在更大更低的一块板上。

    ⭐ 地平线的渐隐**烤进贴图外圈**，不靠 MuJoCo 的 haze/fog——
       那是 `mjRND_*` 渲染标志、不是模型状态，每个消费方（配图脚本、漫游、大脑的相机）
       都得各自去设，一定有人漏。烤进贴图则处处生效、无条件。
    """
    n = size_px
    m_per_px = span_m / n
    img = np.full((n, n, 3), 0.0)
    img[:] = np.array(C_ROOF) + _noise(n, n, 0.06)[..., None] * 26   # 一片屋顶灰，深浅不一

    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(canvas)
    # 街道网格：南北向大道间距 AVENUE_EW_M，东西向街道间距 BLOCK_NS_M
    for x in np.arange(0, span_m, AVENUE_EW_M):
        px = int(x / m_per_px)
        d.line([(px, 0), (px, n)], fill=C_STREET, width=max(1, int(22 / m_per_px)))
    for y in np.arange(0, span_m, BLOCK_NS_M):
        py = int(y / m_per_px)
        d.line([(0, py), (n, py)], fill=C_STREET, width=max(1, int(14 / m_per_px)))
    img = np.asarray(canvas).astype(float)

    # 楼顶明暗：每个街区一块，随机深浅，远看就是密密麻麻的楼群
    bx, by = int(AVENUE_EW_M / m_per_px), int(BLOCK_NS_M / m_per_px)
    for y0 in range(0, n, by):
        for x0 in range(0, n, bx):
            img[y0:y0 + by, x0:x0 + bx] += RNG.uniform(-24, 24)

    # ⭐ 地平线渐隐烤进外圈：离中心越远越淡，融进天空色
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 2)
    haze = np.clip((r - 0.55) / 0.45, 0, 1)[..., None]
    sky = np.array([176.0, 196.0, 214.0])            # 和天空盒底色接得上的雾色
    img = img * (1 - haze) + sky * haze
    return img


# ---------------------------------------------------------------- 真实航拍（NAIP）
# USGS NAIP 正射影像：**美国联邦政府作品，公共领域**，纽约州自 2015 年起 0.5 米/像素。
# ⭐ 这是本方案里唯一"真照片"的部分，而且它是**俯视**的——正好是我们唯一需要照片的朝向，
#    也正好是许可最干净的那一类（公共领域，连署名都不是法律义务）。
NAIP_URL = ("https://imagery.nationalmap.gov/arcgis/rest/services/"
            "USGSNAIPImagery/ImageServer/exportImage")
# ⚠️ 服务自报的硬上限（问 ?f=json 得到）：maxImageWidth/Height = 4000，源像元 0.3 m。
#    超过就返回一段错误 JSON 而不是图片——PIL 会以 UnidentifiedImageError 炸掉，
#    错误信息完全看不出是"尺寸超限"。第一版请求 4096 就栽在这。
NAIP_MAX_PX = 4000

# 中央公园的真实地理事实（南北界中点的经纬度）。⛔ 别写死像素坐标，一切从这里推。
PARK_S_LATLON = (40.7662, -73.9776)     # 南界中点，59 街
PARK_N_LATLON = (40.7987, -73.9538)     # 北界中点，110 街
# ⚠️ 曼哈顿街网偏东约 29°，公园在正射影像里是**斜的**。直接裁会歪，必须先把影像转正。
#    这个角度不是拍脑袋：由上面两个经纬度算出来的（见 _park_axis），和 layout 的
#    VIEW_BEARING_DEG 互为交叉验证。


def _park_axis() -> tuple[float, float, tuple[float, float]]:
    """从两端经纬度算出公园的 (长度 m, 方位角°偏东, 中心经纬度)。"""
    lat0 = (PARK_S_LATLON[0] + PARK_N_LATLON[0]) / 2.0
    m_lat = 111132.0
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    dy = (PARK_N_LATLON[0] - PARK_S_LATLON[0]) * m_lat
    dx = (PARK_N_LATLON[1] - PARK_S_LATLON[1]) * m_lon
    center = (lat0, (PARK_S_LATLON[1] + PARK_N_LATLON[1]) / 2.0)
    return math.hypot(dx, dy), math.degrees(math.atan2(dx, dy)), center


def _merc(lon: float, lat: float) -> tuple[float, float]:
    """经纬度 → Web Mercator（EPSG:3857），NAIP 服务要这个。"""
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.34 / 180.0


def _naip_square(center_latlon: tuple[float, float], span_m: float, px: int) -> Image.Image:
    """抓一块以 center 为中心、边长 span_m 的正方形正射影像。"""
    cx, cy = _merc(center_latlon[1], center_latlon[0])
    # ⚠️ Web Mercator 在高纬度会放大距离，纬度 40.8° 的缩放因子是 1/cos(lat)。
    #    不补这一下，抓下来的范围会比要的小 ~24%，公园会被裁短。
    k = 1.0 / math.cos(math.radians(center_latlon[0]))
    h = span_m * k / 2.0
    if px > NAIP_MAX_PX:
        raise ValueError(f"请求 {px} px 超过服务上限 {NAIP_MAX_PX}——它会返回错误 JSON 而不是图片")
    url = (f"{NAIP_URL}?bbox={cx - h},{cy - h},{cx + h},{cy + h}"
           f"&bboxSR=3857&imageSR=3857&size={px},{px}&format=png&f=image")
    with urllib.request.urlopen(url, timeout=180) as r:
        data = r.read()
    if not data[:8].startswith((b"\x89PNG", b"\xff\xd8\xff")):
        raise RuntimeError(f"NAIP 没返回图片，前 300 字节：{data[:300]!r}")
    return Image.open(io.BytesIO(data)).convert("RGB")


def naip_park(px: int = NAIP_MAX_PX) -> tuple[np.ndarray, np.ndarray]:
    """抓真实航拍并转正，切出 (公园条带, 城市底图) 两张。

    ⭐ 转正是关键：影像里的公园是斜的（曼哈顿街网偏东 29°），而场景里公园是正南北。
       不转正，窗外那条绿带会是歪的，而且和两侧街墙的几何对不上。
    """
    park_l, bearing, center = _park_axis()
    # 源正方形必须装得下**转正后**的公园长方形，所以边长取它的对角线（再留 2% 余量）。
    span_m = math.hypot(PARK_W_M, park_l) * 1.02
    print(f"   公园：长 {park_l:.0f} m，方位角 {bearing:.2f}° 偏东，中心 {center[0]:.4f},{center[1]:.4f}")
    print(f"   抓 NAIP {span_m:.0f} m 见方 → {px}×{px}（{span_m / px:.2f} m/像素）…")
    src = _naip_square(center, span_m, px)
    # PIL 的 rotate 是**逆时针**。公园指向"上偏右 29°"，逆时针转 29° 正好扳正。
    rot = src.rotate(bearing, resample=Image.BICUBIC, expand=False)
    m_per_px = span_m / px

    def _crop(w_m: float, l_m: float) -> np.ndarray:
        w, h = int(w_m / m_per_px), int(l_m / m_per_px)
        cx, cy = px // 2, px // 2
        return np.asarray(rot.crop((cx - w // 2, cy - h // 2,
                                    cx - w // 2 + w, cy - h // 2 + h))).astype(float)

    park = _crop(PARK_W_M, park_l)
    # 城市底图：另抓一张更大范围的（NAIP 覆盖整个纽约州，够用）
    print(f"   抓 NAIP 16000 m 见方 → 2048×2048（7.81 m/像素）…")
    wide = _naip_square(center, 16000.0, 2048).rotate(bearing, resample=Image.BICUBIC)
    city = np.asarray(wide).astype(float)
    # ⭐ 地平线渐隐照旧烤进外圈（理由见 city_ground 的说明：不能靠渲染标志）
    # ⚠️ 而且必须在**板子边缘之前**就渐隐到位：地面板 16 km 见方，但从 232 m 高看真地平线在
    #    54 km 外，板子边缘是一条**硬边**。让雾在 r=0.75 处就完全变成天空色，
    #    外圈那 25% 是纯天空色，边缘就看不见了。（第一版 0.50→1.00 正好在边缘才满，所以露边。）
    n = city.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 2)
    haze = np.clip((r - 0.32) / 0.43, 0, 1)[..., None]
    city = city * (1 - haze) + _horizon_color() * haze
    return park, city


def _horizon_color() -> np.ndarray:
    """雾色 —— ⭐ 从**已生成的天空盒**里取，不写死。

    写死的雾色换一张天空就对不上，接缝立刻显形，而且那是"看起来只是有点怪"的那类问题。
    取朝北那一面（filefront，实测对应世界 +Y）靠近地平线那一条带的平均色。
    天空还没生成时退回一个中性的浅蓝灰。
    """
    p = os.path.join(OUT_DIR, "sky_filefront.png")
    if not os.path.exists(p):
        print("   ⚠️ 天空盒还没生成，雾色用退化值（先跑 make_view.py --sky 效果更好）")
        return np.array([176.0, 196.0, 214.0])
    im = np.asarray(Image.open(p).convert("RGB")).astype(float)
    h = im.shape[0]
    band = im[int(h * 0.49):int(h * 0.53)]            # 地平线正上方那一条
    col = band.reshape(-1, 3).mean(axis=0)
    print(f"   雾色取自天空盒地平线：rgb=({col[0]:.0f}, {col[1]:.0f}, {col[2]:.0f})")
    return col


# ---------------------------------------------------------------- 塔楼立面
def facade(kind: str, px: int = 512, floors: int = 4, night: bool = False) -> np.ndarray:
    """塔楼的立面贴图（一块 = floors 层楼高）。

    ⛔ 这张必须当 **cube 贴图**用，不能当 2d：MuJoCo 的 2d 贴图在基本体上是沿局部 Z 投影的，
       竖着的塔楼会被拉成条纹（本仓的城市背景板当年就栽在这）。
       cube 贴图则六个面各自正确映射——这正是给盒子贴立面该用的工具。

    night=True：夜间版——墙体和竖挺压黑，窗格随机点亮（暖黄住宅光为主、少量冷白
    办公层）。⭐ 夜里整城只靠材质 emission 均匀提亮会变成「均匀发灰的积木」，
    真实感全在「哪些窗亮哪些窗黑」的随机性里。⛔ 固定种子：产物必须可复现。
    """
    img = np.zeros((px, px, 3), float)
    if kind == "glass":
        base, win, mull = (108, 122, 136), (58, 78, 96), (150, 158, 166)
        cols, rows = 10, floors * 2
    else:                                   # limestone：石材 + 打孔窗
        base, win, mull = (176, 168, 154), (72, 74, 78), (196, 190, 178)
        cols, rows = 7, floors * 2
    if night:
        # 夜壳：墙体近黑（被城市辉光勾出一点轮廓即可），窗默认灭
        base = (16, 16, 20) if kind == "glass" else (24, 22, 20)
        mull = (26, 26, 30)
        win_off = (13, 15, 20) if kind == "glass" else (14, 14, 16)
        lit_warm = (236, 206, 150)          # 住宅暖黄
        lit_cool = (168, 188, 214)          # 办公冷白
        p_lit = 0.34 if kind == "glass" else 0.22
        RN = np.random.default_rng(11)      # ⛔ 固定种子
    img[:] = base
    img += _noise(px, px, 0.25)[..., None] * (2 if night else 6)
    cw, rh = px / cols, px / rows
    for r in range(rows):
        for c in range(cols):
            y0, x0 = int(r * rh), int(c * cw)
            # 窗洞占开间的中间一块，四周留窗间墙
            iy, ix = int(rh * 0.22), int(cw * 0.18)
            y1, x1 = int(y0 + rh - iy), int(x0 + cw - ix)
            if night:
                if RN.random() < p_lit:
                    tone = lit_cool if RN.random() < 0.15 else lit_warm
                    img[y0 + iy:y1, x0 + ix:x1] = np.array(tone) * RN.uniform(0.70, 1.15)
                else:
                    img[y0 + iy:y1, x0 + ix:x1] = win_off
            else:
                shade = 1.0 + 0.16 * math.sin(c * 1.7 + r * 0.9)   # 每格反射不同，免得死板
                img[y0 + iy:y1, x0 + ix:x1] = np.array(win) * shade
    # 楼层线 / 竖挺
    for r in range(rows):
        img[int(r * rh):int(r * rh) + max(1, px // 256)] = mull
    for c in range(cols):
        img[:, int(c * cw):int(c * cw) + max(1, px // 340)] = mull
    return img


def roof(px: int = 512, night: bool = False) -> np.ndarray:
    """屋顶：砾石 + 设备层 + 女儿墙。night=True 压黑并加几粒红色航空障碍灯。"""
    tone = np.array([22.0, 22.0, 26.0]) if night else np.array([116.0, 114.0, 110.0])
    img = np.full((px, px, 3), 0.0) + tone
    img += _noise(px, px, 0.35)[..., None] * (4 if night else 16)   # 砾石颗粒
    c = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(c)
    b = px // 22
    line = (34, 34, 38) if night else (146, 143, 138)
    d.rectangle([0, 0, px - 1, px - 1], outline=line, width=b)      # 女儿墙
    RR = np.random.default_rng(7)                          # ⛔ 固定种子：产物要可复现
    for _ in range(6):                                     # 冷却塔/机房/水箱
        x, y = RR.integers(b * 2, px - b * 5, 2)
        w, h = RR.integers(px // 12, px // 5, 2)
        fill = (30, 30, 34) if night else (96, 96, 100)
        d.rectangle([x, y, x + w, y + h], fill=fill,
                    outline=(44, 44, 48) if night else (140, 140, 144))
    if night:
        for _ in range(4):                                 # 航空障碍灯
            x, y = RR.integers(b * 2, px - b * 2, 2)
            r = max(2, px // 200)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 62, 54))
    return np.asarray(c).astype(float)


def facade_cube(kind: str, px: int = 512, night: bool = False) -> np.ndarray:
    """把立面 + 屋顶拼成 MuJoCo 的 cube 网格图（gridsize="3 4"，layout ".U..LFRB.D.."）。

    ⛔ 为什么非拼不可：`type="cube"` 只给一个 `file` 时，MuJoCo 把**同一张图贴到六个面，
       包括顶面**。而这套场景是从 **62 层往下看**——比我们矮的楼**每一栋都戴着窗格当屋顶**，
       这比任何贴图精度问题都刺眼。给 U 面单独一张屋顶图就解决了。
    ⚠️ 网格按**行优先**读，字符只能取自 `.RLUDFB`；3×4 = 12 个字符，正好是"横向十字"。
    """
    f, rf = facade(kind, px, night=night), roof(px, night=night)
    grid = np.zeros((px * 3, px * 4, 3), float)
    layout = ".U..LFRB.D.."                    # 行优先：第0行 .U.. / 第1行 LFRB / 第2行 .D..
    for i, ch in enumerate(layout):
        if ch == ".":
            continue
        r, c = divmod(i, 4)
        grid[r * px:(r + 1) * px, c * px:(c + 1) * px] = rf if ch in "UD" else f
    return grid


# ---------------------------------------------------------------- 真实纽约建筑群
# 来源：**NYC Open Data 建筑轮廓**（数据集 5zhs-2jue，DoITT 航测）。
# 许可：纽约市 Local Law 11 of 2012（Admin Code §23-502(d)）——"数据集必须无注册、无许可、
#      无使用限制"，**没有 share-alike**。唯一要求是再发布时注明来源/版本/改动。
# ⛔ 为什么不用 OpenStreetMap：覆盖率其实相当（98.4% 有 height，因为 OSM 的曼哈顿建筑本来
#    就是从这份数据导入的），但 OSM 是 ODbL——**把 2700 栋的坐标表提交进 MIT 仓构成
#    "派生数据库"，share-alike 会附着到那个文件上**。渲染图不受影响，但坐标表受影响。
NYC_FOOTPRINTS = "https://data.cityofnewyork.us/resource/5zhs-2jue.geojson"
FT_TO_M = 0.3048

# 本楼（观察点）的经纬度：公园南界中点再往南 PARK_NEAR_M（沿公园长轴方向）
PARK_NEAR_M = 34.0         # ⚠️ 必须和 layout 的 PARK_NEAR_Y 一致
# 视野相关的取景框（不对称：观察者在南边往北看，所以往北要得多）
NYC_BBOX = (40.8300, -74.0000, 40.7620, -73.9250)    # nwLat, nwLon, seLat, seLon
NYC_MIN_HEIGHT_FT = 100    # ⛔ 别放宽到 60：那是 9389 栋，同时爆编译和 maxgeom


def _anchor_latlon() -> tuple[float, float]:
    """本楼的经纬度 = 公园南界中点沿长轴往南 PARK_NEAR_M。"""
    _, bearing, _ = _park_axis()
    b = math.radians(bearing)
    lat0 = PARK_S_LATLON[0]
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    return (lat0 - PARK_NEAR_M * math.cos(b) / 111132.0,
            PARK_S_LATLON[1] - PARK_NEAR_M * math.sin(b) / m_lon)


def _to_scene(lon: float, lat: float, anchor, bearing_deg: float) -> tuple[float, float]:
    """经纬度 → 场景坐标（+y = 公园长轴方向，和 NAIP 那张图用的是**同一个**旋转）。"""
    m_lon = 111320.0 * math.cos(math.radians(anchor[0]))
    dn = (lat - anchor[0]) * 111132.0
    de = (lon - anchor[1]) * m_lon
    b = math.radians(bearing_deg)
    return (-dn * math.sin(b) + de * math.cos(b),      # x
            dn * math.cos(b) + de * math.sin(b))       # y


def nyc_massing() -> list[tuple]:
    """抓建筑轮廓，转成场景坐标系里的体块 (名字, x, y, sx, sy, 楼顶标高, 材质)。

    ⭐ **只存包围盒，不存多边形**：把轮廓转到场景坐标后取 AABB。因为场景已经跟着曼哈顿街网
       转正了（同一个 29.05°），而曼哈顿的楼绝大多数是**顺着街网的矩形**，所以
       **旋转后轮廓的 AABB 就是它的有向包围盒**——通常"AABB 高估旋转矩形"的误差不发生。
       多边形用完即弃，入库的只有五个数。
    ⚠️ 而且这个精度绰绰有余：2 km 外一个像素是 1.45 m，轮廓相对包围盒的凹进
       （退线、采光井）本来就是亚像素的。
    """
    _, bearing, _ = _park_axis()
    anchor = _anchor_latlon()
    where = (f"within_box(the_geom, {NYC_BBOX[0]},{NYC_BBOX[1]}, {NYC_BBOX[2]},{NYC_BBOX[3]}) "
             f"AND height_roof > {NYC_MIN_HEIGHT_FT} "
             # ⛔ 必须含 'Merged'：111 West 57th 继承了 1924 年 Steinway Hall 的记录，
             #    状态就是 Merged。漏掉它，亿万富翁街的剪影就少一根针。
             f"AND last_status_type in('Constructed','Alteration','Merged')")
    url = (f"{NYC_FOOTPRINTS}?$select=bin,height_roof,ground_elevation,the_geom"
           f"&$where={urllib.parse.quote(where)}&$order=bin&$limit=50000")
    print(f"   本楼锚点 {anchor[0]:.5f},{anchor[1]:.5f}；取景框 {NYC_BBOX}，>{NYC_MIN_HEIGHT_FT} ft")
    with urllib.request.urlopen(url, timeout=300) as r:
        fc = json.load(r)
    feats = fc.get("features", [])
    print(f"   拿到 {len(feats)} 栋")

    anchor_ground_ft = None
    rows = []
    for f in feats:
        p = f["properties"]
        try:
            h_ft = float(p["height_roof"])
            g_ft = float(p.get("ground_elevation") or 0.0)
        except (TypeError, ValueError):
            continue
        pts = []
        for poly in f["geometry"]["coordinates"]:
            for ring in poly:
                pts.extend(_to_scene(lon, lat, anchor, bearing) for lon, lat in ring)
        if not pts:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # ⛔ 丢掉盖住原点的那栋——那是本楼自己（或者会把公寓包在里面）
        if x0 <= 0 <= x1 and y0 <= 0 <= y1:
            anchor_ground_ft = g_ft
            continue
        rows.append((p["bin"], cx, cy, max(x1 - x0, 6.0), max(y1 - y0, 6.0), g_ft, h_ft))

    # ⚠️ 高度必须用 **ground_elevation + height_roof**：曼哈顿地面标高从 −6 ft 到 80+ ft，
    #    忽略它最多差 26 m，在这个距离上看得出来。基准取本楼所在地的地面标高。
    base_ft = anchor_ground_ft if anchor_ground_ft is not None else 40.0
    out = []
    for i, (bin_, cx, cy, sx, sy, g_ft, h_ft) in enumerate(rows):
        top_m = (g_ft + h_ft - base_ft) * FT_TO_M - ELEV_M
        # 材质按高度和确定性伪随机分配（⛔ 不用 random：产物必须可复现、diff 稳定）
        k = (int(bin_) + i) % 3
        mat = ("mat_h3_glass_dark", "mat_h3_limestone", "mat_h3_facade")[k]
        if h_ft > 600:                       # 超高层基本都是玻璃幕墙
            mat = "mat_h3_glass_cool"
        out.append((f"nyc{bin_}", round(cx, 1), round(cy, 1),
                    round(sx, 1), round(sy, 1), round(top_m, 1), mat))
    print(f"   转成体块 {len(out)} 个（已剔除盖住原点的本楼）；本楼地面标高 {base_ft:g} ft")
    return out


# ⚠️ 和 layout 的 ELEV 必须一致（62 层 × 3.75 m）。两处各写一份迟早对不上，
#    所以这里注明来源；check_scene 会核对。
ELEV_M = 62 * 3.75


# ---------------------------------------------------------------- 天空（真实 HDRI）
# Poly Haven 的 HDRI 全部 CC0，而且**每一张都有现成的 8 位色调映射 JPG**——
# ⭐ 这意味着不用解 Radiance .hdr、不用自己 tonemap、不用调曝光。
#    （MuJoCo 的贴图只吃 8 位 PNG/KTX，HDR/EXR 一概不认，所以这一步本来是躲不掉的。）
PH_TONEMAPPED = "https://dl.polyhaven.org/file/ph-assets/HDRIs/extra/Tonemapped%20JPG/{id}.jpg"

# ⛔⛔ 天空盒六个面到世界方向的映射 —— **实测得出，六个面全是反的**。
#
#    2026-08-06 用 calib_*.png（六个纯色面）架六台 100° 视场的相机实测，零误差：
#        相机朝 +X(东)  → 看到 L 面        相机朝 −X(西)  → 看到 R 面
#        相机朝 +Y(北)  → 看到 F 面        相机朝 −Y(南)  → 看到 B 面
#        相机朝 +Z(天顶)→ 看到 D 面        相机朝 −Z(地面)→ 看到 U 面
#
#    也就是说 up↔down、left↔right 全部对调。照 MuJoCo 文档的字面命名去填，
#    天空会上下翻转 + 左右镜像，**而渲染出来照样很好看**，只有对着实景才看得出不对。
#    ⛔ 别"优化"掉这张表，也别照字面重排——要改先重跑 --calib。
# ⛔ 键是**显示方向**：朝这个世界方向看时，MuJoCo 画的是哪个文件槽。
#    2026-08-09 用字母标定图 + 彩色方位探针实测重定（旧表四个侧面配反了 180°，
#    造成两个一直没人发现的 bug：① 白天太阳其实在北边——roll=180 特意躲的东西
#    被表的 180° 转回来了；② 朝西北看天空有一条脸缝硬边，黄昏光下特别扎眼。
#    旧表当年只朝北目检过，北面"看着对"是两个错互相抵消的假象）。
#    面内取向的镜像补偿在 _equirect_face 里（right 取反），两处配套，⛔ 别只改一处。
SKY_FACE_FOR_DIR = {
    (+1, 0, 0): "fileright",    (-1, 0, 0): "fileleft",
    (0, +1, 0): "fileback",     (0, -1, 0): "filefront",
    (0, 0, +1): "fileup",       (0, 0, -1): "filedown",
}


def _equirect_face(eq: np.ndarray, forward, up, px: int) -> np.ndarray:
    """从等距柱状全景里切出一个 90° 视场、朝向 `forward` 的正方形面。

    自己算而不是用 py360convert，是因为它的 dice/上轴约定和 MuJoCo 不一致，
    拼起来还得再猜一层；这里直接按世界方向采样，方向由上面那张实测表定死。
    """
    h, w = eq.shape[:2]
    f = np.array(forward, float); f /= np.linalg.norm(f)
    u = np.array(up, float); u -= f * (u @ f); u /= np.linalg.norm(u)
    # ⛔ right 取反 = 镜像补偿：MuJoCo 把天空盒每面**水平镜像**着画（cube 贴图按
    #    "从外面看"制作）。2026-08-09 彩色方位探针实测：取反后北红/东绿/南蓝/西黄/
    #    天顶白五向逐位全对。与 SKY_FACE_FOR_DIR 的显示方向表配套，⛔ 别只改一处。
    r = -np.cross(f, u)
    # 面内网格：[-1,1]²，正好张成 90°
    t = (np.arange(px) + 0.5) / px * 2.0 - 1.0
    gx, gy = np.meshgrid(t, -t)
    d = f[None, None, :] + gx[..., None] * r[None, None, :] + gy[..., None] * u[None, None, :]
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    lon = np.arctan2(d[..., 1], d[..., 0])          # 世界 z 朝上
    lat = np.arcsin(np.clip(d[..., 2], -1, 1))
    px_u = ((lon + np.pi) / (2 * np.pi) * w).astype(int) % w
    px_v = np.clip(((np.pi / 2 - lat) / np.pi * h).astype(int), 0, h - 1)
    return eq[px_v, px_u]


def sky_faces(hdri_id: str, px: int = 2048, roll_deg: float = 180.0) -> dict[str, np.ndarray]:
    """下载 Poly Haven 的色调映射全景，切成六面。

    ⛔ `roll_deg=180` 不是随手填的：候选的几张（kloofendal / qwantani / drakensberg）
       **都是南半球拍的**，而南半球正午太阳在**北**。本场景朝北看公园，直接用会在中央公园
       正上方挂一个 40.77°N 任何时刻都不可能出现的太阳。横向旋转 180° 把它摆回南边。
    """
    url = PH_TONEMAPPED.format(id=hdri_id)
    print(f"   下载 {hdri_id}（Poly Haven, CC0, 色调映射 JPG）…")
    with urllib.request.urlopen(url, timeout=300) as r:
        eq = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(float)
    print(f"   等距柱状 {eq.shape[1]}×{eq.shape[0]}，横向旋转 {roll_deg:g}°（太阳摆到南边）")
    eq = np.roll(eq, int(eq.shape[1] * roll_deg / 360.0), axis=1)
    out = {}
    for d, attr in SKY_FACE_FOR_DIR.items():
        up = (0, 0, 1) if d[2] == 0 else (0, 1, 0)   # 朝天/朝地时另选一个上方向
        out[attr] = _equirect_face(eq, d, up, px)
    return out



# ---------------------------------------------------------------- 程序化夜空
def night_sky_faces(px: int = 2048) -> dict[str, np.ndarray]:
    """曼哈顿的夜空——**不用 HDRI**，程序化合成。三条理由（都实测/物理）：
    ① 8-bit 色调映射的野外夜空几乎全是 0–8 的死黑，切面后天顶必出 banding；
    ② 多数夜景 HDRI 带一轮很亮的月亮，落在北边就是「中央公园上空不可能的月亮」；
    ③ ⭐ 曼哈顿的夜空不是黑的，是被城市照亮的橙灰——野外 HDRI 拍出来像沙漠不像纽约。

    做法：合成等距柱状图（天顶深蓝黑 → 地平线橙灰，南边中城方向最亮），
    ⛔ 量化前加噪声抖动（否则 8-bit 渐变必 banding），少量高纬星星，
    再走 `_equirect_face` 同一条切面管线（方向约定与 HDRI 路径逐位一致）。
    """
    H, W = 1024, 2048
    lon = (np.arange(W) + 0.5) / W * 2 * np.pi - np.pi      # lon = atan2(y, x)
    lat = np.pi / 2 - (np.arange(H) + 0.5) / H * np.pi
    LT = np.repeat(lat[:, None], W, axis=1)
    LN = np.repeat(lon[None, :], H, axis=0)
    zenith = np.array([8.0, 10.0, 16.0])
    horizon = np.array([58.0, 44.0, 32.0])
    south_boost = np.array([18.0, 12.0, 6.0])               # 中城方向（南）的辉光
    # 高度混合：地平线附近权重大，sin^2.2 压向低空
    t = np.clip(1.0 - np.abs(LT) / (np.pi / 2), 0, 1) ** 2.2
    # 方位：南 = lon -π/2 最亮
    az_w = (np.cos(LN + np.pi / 2) * 0.5 + 0.5) ** 1.5
    eq = zenith[None, None, :] + t[..., None] * (
        horizon - zenith)[None, None, :] + (t * az_w)[..., None] * south_boost[None, None, :]
    # 地平线下（贴图上其实被楼和地面挡住）延续地平线色，免得切面边缘出黑边
    hrow = eq[np.argmin(np.abs(lat))]                       # (W, 3) 地平线那一行
    eq = np.where((LT < 0)[..., None], hrow[None, :, :], eq)
    # 星星：只在高纬（城市光害下低空看不到星）
    RS = np.random.default_rng(20260809)
    n_star = 400
    si = RS.integers(0, H // 3, n_star)                     # lat > ~30°
    sj = RS.integers(0, W, n_star)
    eq[si, sj] = np.minimum(eq[si, sj] + RS.uniform(50, 100, (n_star, 1)), 255)
    # ⛔ 抖动再量化：8-bit 深色渐变不抖必 banding
    eq += np.random.default_rng(3).normal(0, 1.2, eq.shape)
    eq = np.clip(eq, 0, 255)
    out = {}
    for d, attr in SKY_FACE_FOR_DIR.items():
        up = (0, 0, 1) if d[2] == 0 else (0, 1, 0)
        out[attr] = _equirect_face(eq, d, up, px)
    return out


# ---------------------------------------------------------------- 天空盒标定
def calib_faces(face_px: int = 512) -> dict[str, np.ndarray]:
    """六张标定图：每面一个大字母 + 一个向上的箭头。

    ⛔ 为什么必须实测标定、不许靠推理：MuJoCo 的天空盒坐标系是**反常的**——
       它按 Y 轴朝上制作、渲染时故意绕 +X 转 90°，而且默认相机看的是 **B（Back）面**。
       一个被镜像或转了 90° 的天空盒**渲染出来很漂亮**、读起来就是"一座城市"，
       只有懂纽约的人才会发现中央公园大厦在公园的错误一侧。
       载进去看一眼字母，五分钟就定死了。
    """
    cols = {"R": (200, 70, 70), "L": (70, 120, 200), "U": (220, 200, 90),
            "D": (110, 110, 120), "F": (80, 180, 110), "B": (190, 100, 190)}
    out = {}
    for k, c in cols.items():
        im = Image.new("RGB", (face_px, face_px), c)
        d = ImageDraw.Draw(im)
        s = face_px
        # 大字母（用矩形拼，免得依赖字体）
        d.rectangle([s * 0.30, s * 0.30, s * 0.70, s * 0.70], fill=(255, 255, 255))
        d.rectangle([s * 0.36, s * 0.36, s * 0.64, s * 0.64], fill=c)
        # 向上的箭头：告诉你这一面的"上"在哪
        d.polygon([(s * 0.50, s * 0.10), (s * 0.42, s * 0.24), (s * 0.58, s * 0.24)],
                  fill=(255, 255, 255))
        try:
            from PIL import ImageFont
            f = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(s * 0.28))
            d.text((s * 0.5, s * 0.5), k, font=f, fill=(255, 255, 255), anchor="mm")
        except Exception:
            pass                                     # 没字体也行，方框+箭头已经够判方向
        out[k] = np.asarray(im).astype(float)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--naip", action="store_true",
                    help="⭐ 抓 USGS NAIP 真实航拍（公共领域）—— 效果最好，需联网")
    ap.add_argument("--procedural", action="store_true",
                    help="程序化生成公园与城市贴图（不联网的兜底）")
    ap.add_argument("--nyc", action="store_true",
                    help=f"⭐ 抓 NYC Open Data 建筑轮廓 → scenes/{SCENE_KEY}/nyc_massing.py")
    ap.add_argument("--sky", action="store_true",
                    help="⭐ 抓 Poly Haven 的 CC0 实景天空 → 天空盒六面")
    ap.add_argument("--sky-id", default="kloofendal_48d_partly_cloudy_puresky",
                    help="用哪张 HDRI（Poly Haven 的 pure skies 系列，全 CC0）")
    ap.add_argument("--sky-phase", default="day", choices=("day", "morning", "dusk", "night"),
                    help="出哪个时段的天空盒。⭐ day 不带后缀（现有引用零改动）；"
                         "其它时段落成 sky_<时段>_file*.png，供渲染期换装（LIGHTS_BY_TIME）")
    ap.add_argument("--sky-roll", type=float, default=180.0,
                    help="等距柱状横向旋转角（度）。⛔ 默认 180 是为南半球 HDRI 定的"
                         "（太阳摆回南边）；换 HDRI 要按太阳/月亮实际方位重定，别盲用默认")
    ap.add_argument("--facades", action="store_true", help="生成塔楼立面贴图")
    ap.add_argument("--calib", action="store_true",
                    help="生成天空盒六面标定图（每面一个大字母 + 向上箭头）")
    ap.add_argument("--all", action="store_true", help="NAIP + 立面，一次做完")
    ap.add_argument("--park-px-per-m", type=float, default=1.0,
                    help="程序化公园贴图的分辨率（像素/米）")
    a = ap.parse_args()
    if a.calib:
        print("生成天空盒标定图 →", OUT_DIR)
        for k, arr in calib_faces().items():
            _save(f"calib_{k}.png", arr)
        return
    if a.nyc or a.all:
        print("抓真实纽约建筑群（NYC Open Data，Local Law 11：无使用限制）")
        rows = nyc_massing()
        dst = os.path.join(ROOT, "scenes", SCENE_KEY, "nyc_massing.py")
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write('"""曼哈顿真实建筑体块 —— ⛔ 本文件由 `python tools/make_view.py --nyc` 生成，请勿手改。\n\n'
                     "来源：NYC Open Data 建筑轮廓（数据集 5zhs-2jue，DoITT 航测）。\n"
                     "许可：纽约市 Local Law 11 of 2012（Admin Code §23-502(d)）——无注册/无许可/\n"
                     "      无使用限制，**没有 share-alike**；再发布须注明来源、版本与改动。\n"
                     "加工：经纬度 → 以本楼为原点的场景坐标，按公园长轴方位角 29.05° 旋转转正，\n"
                     "      取轮廓的轴对齐包围盒；高度 = (ground_elevation + height_roof) 英尺换算成米\n"
                     "      再减去本层离街面的高度。多边形用完即弃，只留五个数。\n"
                     '"""\n\n')
            fh.write("# (名字, x, y, 东西向边长, 南北向边长, 楼顶相对本层地面的标高, 材质)\n")
            fh.write("MASSING = [\n")
            for r in rows:
                fh.write(f"    ({r[0]!r}, {r[1]}, {r[2]}, {r[3]}, {r[4]}, {r[5]}, {r[6]!r}),\n")
            fh.write("]\n")
        print(f"   写入 {dst}（{len(rows)} 栋）")
        if not a.all:
            return
    if a.sky or a.all:
        suffix = "" if a.sky_phase == "day" else f"_{a.sky_phase}"
        if a.sky_phase == "night":
            print(f"生成天空盒六面（程序化曼哈顿夜空，不联网）→", OUT_DIR)
            faces = night_sky_faces()
        else:
            print(f"生成天空盒六面（Poly Haven 实景天空，CC0，时段={a.sky_phase}）→", OUT_DIR)
            faces = sky_faces(a.sky_id, roll_deg=a.sky_roll)
        for attr, arr in faces.items():
            _save(f"sky{suffix}_{attr}.png", arr)
        if not a.all:
            return
    if a.facades or a.all:
        print("生成塔楼立面贴图 →", OUT_DIR)
        for kind in ("glass", "limestone"):
            _save(f"facade_{kind}.png", facade_cube(kind))
            _save(f"facade_{kind}_night.png", facade_cube(kind, night=True))
        if not a.all:
            return
    if a.naip or a.all:
        print("抓真实航拍（USGS NAIP，公共领域）→", OUT_DIR)
        park, city = naip_park()
        _save("park_aerial.png", park)
        _save("city_ground.png", city)
        return
    print(f"程序化生成 {SCENE_KEY} 窗景贴图 →", OUT_DIR)
    _save("park_aerial.png", park_aerial(a.park_px_per_m))
    _save("city_ground.png", city_ground())


if __name__ == "__main__":
    main()
