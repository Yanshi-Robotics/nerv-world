"""Manhattan environment shared by the canonical apartment.

Coordinates, public-domain aerial imagery, facade assets and time-of-day colors
are preserved from the retired apt1 scene at revision 7fb134f. No apartment floor
plan or furniture is defined here. Keep textures/house3 and h3_ as asset IDs.
"""

import os

GLASS_RGBA = (0.80, 0.88, 0.94, 0.07)

GLASS_THICK = 0.03

FLOOR_LEVEL = 62

FLOOR_TO_FLOOR = 3.75

ELEV = FLOOR_LEVEL * FLOOR_TO_FLOOR

X0, X1, X2, XB, XC, X3, X4 = -11.5, -6.4, -1.6, 0.4, 4.2, 6.2, 11.5

Y0, Y1, Y2, Y3 = -7.5, -1.2, 2.2, 7.5

SKYBOX = {
    "fileright": "textures/house3/sky_fileright.png",
    "fileleft": "textures/house3/sky_fileleft.png",
    "fileup": "textures/house3/sky_fileup.png",
    "filedown": "textures/house3/sky_filedown.png",
    "filefront": "textures/house3/sky_filefront.png",
    "fileback": "textures/house3/sky_fileback.png",
}

TEXTURES_EXTRA = [
    # 公园与城市：真实航拍（USGS NAIP，**公共领域**）。俯视贴在水平板上，投影天然正确。
    {"name": "tex_h3_park", "file": "textures/house3/park_aerial.png", "colorspace": "sRGB"},
    {"name": "tex_h3_city", "file": "textures/house3/city_ground.png", "colorspace": "sRGB"},
    # ⛔ 塔楼立面必须是 **cube** 贴图，不能是 2d。
    #    MuJoCo 的 2d 贴图在基本体上是沿**局部 Z 轴投影**的，竖着的塔楼会被拉成条纹——
    #    本仓的城市背景板 v0.6 就是栽在这（见 CHANGELOG [0.7] 第 2 条）。
    #    cube 贴图六个面各自正确映射，正是给盒子贴立面该用的工具。
    #    ⚠️ 用 3×4 的"横向十字"网格图，**顶面单独给屋顶贴图**——单文件 cube 会把窗格
    #    也贴到顶上，而这场景是从 62 层往下看，矮楼全戴着窗格当屋顶，非常刺眼。
    # 室内材质（ambientCG，CC0）。⚠️ 名字全带 h3_ 前缀，⛔ 不许和基础贴图撞
    #    （我自己已经在 mat_wall 上栽过一次，MuJoCo 当场拒绝编译）。
    # ⚠️ 贴在**水平面**上的（地面、台面、地毯）用 2d 就对；
    #    贴在**竖直面**上的（墙面）必须用 **cube**——2d 在基本体上沿局部 Z 投影，
    #    竖墙会被拉成条纹。这个坑本仓在城市背景板和塔楼立面上已经栽过两次了。
    # ⛔⛔ `type="cube"` 不是可选项（2026-08-08 补上）。上面那三行注释从 v0.8 起就写着
    #    "竖直面必须用 cube"，**而这九张一直是默认的 2d** —— 知识写下来了但没落到代码上，
    #    于是全屋的墙面、沙发、柜子侧面都被沿局部 Z 拖成竖条纹整整四版。
    #    Jeff 2026-08-08 的原话："好多 vertical 射线，而不是沙发材质的感觉"。
    #    ⚠️ 别去试 `texuniform`：实测开/关渲染出来**逐像素一样**，它管的是另一件事
    #    （texrepeat 相对 geom 还是按空间单位）。真正的旋钮只有贴图**类型**。
    #    ⭐ 水平面用 cube 也完全正确，所以九张一律 cube，不用分。
    *[
        {
            "type": "cube",
            "name": f"tex_h3_{n}",
            "file": f"textures/house3/h3_{n}.png",
            "colorspace": "sRGB",
        }
        for n in ("oak", "oak_dark", "marble", "marble_blk", "travertine", "linen", "rug")
    ],
    *[
        {
            "type": "cube",
            "name": f"tex_h3_{n}",
            "file": f"textures/house3/h3_{n}.png",
            "colorspace": "sRGB",
        }
        for n in ("plaster", "onyx")
    ],
    {
        "type": "cube",
        "name": "tex_h3_fac_glass",
        "gridsize": "3 4",
        "gridlayout": ".U..LFRB.D..",
        "file": "textures/house3/facade_glass.png",
        "colorspace": "sRGB",
    },
    {
        "type": "cube",
        "name": "tex_h3_fac_stone",
        "gridsize": "3 4",
        "gridlayout": ".U..LFRB.D..",
        "file": "textures/house3/facade_limestone.png",
        "colorspace": "sRGB",
    },
]

_FAC_TILE_M = 4 * FLOOR_TO_FLOOR

_FAC_REP = round(1.0 / _FAC_TILE_M, 5)

MATERIALS_EXTRA = [
    # ⭐ emission 让窗外的白天不被室内灯光"照暗"。
    #    ⚠️ 别给满 1.0——亮部会削顶成死白。0.45 是对着渲染结果调的。
    {
        "name": "mat_h3_park",
        "texture": "tex_h3_park",
        "texrepeat": "1 1",
        "texuniform": "false",
        "specular": "0",
        "shininess": "0",
        "reflectance": "0",
        "emission": "0.45",
    },
    {
        "name": "mat_h3_city",
        "texture": "tex_h3_city",
        "texrepeat": "1 1",
        "texuniform": "false",
        "specular": "0",
        "shininess": "0",
        "reflectance": "0",
        "emission": "0.45",
    },
    # 远处塔楼：真的贴上窗格立面（之前是纯色盒子，远看就是一堆灰乐高）。
    # rgba 仍然给着——它给贴图**染色**，让三种楼各有色调，不至于一模一样。
    {
        "name": "mat_h3_glass_cool",
        "texture": "tex_h3_fac_glass",
        "texrepeat": f"{_FAC_REP} {_FAC_REP}",
        "texuniform": "true",
        "rgba": "0.86 0.94 1.0 1",
        "specular": "0.55",
        "shininess": "0.80",
        "reflectance": "0.18",
        "emission": "0.10",
    },
    {
        "name": "mat_h3_glass_dark",
        "texture": "tex_h3_fac_glass",
        "texrepeat": f"{_FAC_REP} {_FAC_REP}",
        "texuniform": "true",
        "rgba": "0.58 0.64 0.74 1",
        "specular": "0.50",
        "shininess": "0.75",
        "reflectance": "0.15",
        "emission": "0.08",
    },
    {
        "name": "mat_h3_limestone",
        "texture": "tex_h3_fac_stone",
        "texrepeat": f"{_FAC_REP} {_FAC_REP}",
        "texuniform": "true",
        "rgba": "1.0 0.97 0.90 1",
        "specular": "0.10",
        "shininess": "0.20",
        "reflectance": "0.02",
        "emission": "0.12",
    },
    # 本楼外皮：同一套立面，色调偏中性
    {
        "name": "mat_h3_facade",
        "texture": "tex_h3_fac_stone",
        "texrepeat": f"{_FAC_REP} {_FAC_REP}",
        "texuniform": "true",
        "rgba": "0.80 0.80 0.78 1",
        "specular": "0.25",
        "shininess": "0.40",
        "reflectance": "0.05",
    },
    # ── 室内材质：ambientCG 的 CC0 照片级贴图（`python fetch_assets.py` 下载）──
    # ⚠️ texrepeat 按**物理尺度**给，不是凭眼睛调：每张贴图 1024 px 覆盖约 2 m 见方，
    #    所以 N 米的面上重复 N/2 次。房间尺寸一改，观感不会跟着变形。
    # cube 贴图配 texuniform="true" = "每 1 个空间单位重复 N 次"，
    # 所以 1/2.2 表示一张图铺 2.2 m 见方——不同大小的墙共用一张也不会变形。
    {
        "name": "mat_h3_wall",
        "texture": "tex_h3_plaster",
        "texrepeat": "2 2",
        "rgba": "1.06 1.05 1.02 1",
        "specular": "0.04",
        "shininess": "0.08",
        "reflectance": "0.01",
    },
    {
        "name": "mat_h3_oak",
        "texture": "tex_h3_oak",
        "texrepeat": "3 3",
        "specular": "0.14",
        "shininess": "0.24",
        "reflectance": "0.03",
    },
    {
        "name": "mat_h3_oak_dark",
        "texture": "tex_h3_oak_dark",
        "texrepeat": "3 3",
        "specular": "0.12",
        "shininess": "0.22",
        "reflectance": "0.02",
    },
    {
        "name": "mat_h3_marble",
        "texture": "tex_h3_marble",
        "texrepeat": "2 2",
        "specular": "0.45",
        "shininess": "0.72",
        "reflectance": "0.14",
    },
    {
        "name": "mat_h3_marble_blk",
        "texture": "tex_h3_marble_blk",
        "texrepeat": "1 1",
        "specular": "0.55",
        "shininess": "0.80",
        "reflectance": "0.18",
    },
    {
        "name": "mat_h3_travertine",
        "texture": "tex_h3_travertine",
        "texrepeat": "2 2",
        "specular": "0.22",
        "shininess": "0.38",
        "reflectance": "0.05",
    },
    {
        "name": "mat_h3_onyx",
        "texture": "tex_h3_onyx",
        "texrepeat": "2 2",
        "specular": "0.40",
        "shininess": "0.66",
        "reflectance": "0.12",
    },
    {
        "name": "mat_h3_linen",
        "texture": "tex_h3_linen",
        "texrepeat": "4 4",
        "specular": "0.05",
        "shininess": "0.10",
        "reflectance": "0.01",
    },
    {
        "name": "mat_h3_rug",
        "texture": "tex_h3_rug",
        "texrepeat": "3 3",
        "specular": "0.03",
        "shininess": "0.06",
        "reflectance": "0.0",
    },
]

PARK_NEAR_Y = 34.0

PARK_W = 800.0

PARK_L = 4110.0

CITY_SPAN = 16000.0

GROUND_SLABS = [
    {
        "name": "park_ground",
        "pos": (0.0, PARK_NEAR_Y + PARK_L / 2.0, -ELEV),
        "size": (PARK_W, PARK_L, 4.0),
        "mat": "mat_h3_park",
    },
    # 城市底图更大更低（低 0.6 m 避免和公园板 z-fighting），外圈已把地平线渐隐烤进贴图。
    # ⛔ 不用 MuJoCo 的 haze/fog：那是渲染标志不是模型状态，每个消费方都得各自设，一定有人漏。
    {
        "name": "city_ground",
        "pos": (0.0, 0.0, -ELEV - 0.6),
        "size": (CITY_SPAN, CITY_SPAN, 4.0),
        "mat": "mat_h3_city",
    },
]

_TOWERS = [
    # 名字               x       y     边长      建筑高度(m)   材质
    (
        "central_park_twr",
        -55.0,
        -120.0,
        44.0,
        44.0,
        472.4,
        "mat_h3_glass_cool",
    ),  # 中央公园大厦 217 W 57
    (
        "steinway_111w57",
        185.0,
        -110.0,
        26.0,
        26.0,
        435.3,
        "mat_h3_limestone",
    ),  # 111 West 57（施坦威大厦）
    ("one57", 150.0, -125.0, 38.0, 38.0, 306.1, "mat_h3_glass_dark"),  # One57，157 W 57
    ("w53_53", 420.0, -230.0, 40.0, 40.0, 320.0, "mat_h3_glass_dark"),  # 53 West 53
    # ⛔ 下面这几栋**必须在 y ≤ 0**（和本楼同在中央公园南沿或更南）。
    #    第一版把 220 CPS 放到了 y=+45，也就是**放进了公园里**，结果它正杵在
    #    本楼和公园之间，把大客厅望出去的左半边全挡死（渲染出来才发现）。
    #    现在 check_park_sightline 会算"本楼到公园之间有没有东西"，不用再靠肉眼。
    (
        "cps_220",
        -95.0,
        0.0,
        34.0,
        46.0,
        290.0,
        "mat_h3_limestone",
    ),  # 220 Central Park South（本楼西邻）
    (
        "deutsche_bank",
        -255.0,
        -60.0,
        60.0,
        46.0,
        229.2,
        "mat_h3_glass_dark",
    ),  # 哥伦布圆环 时代华纳中心
    ("trump_intl", -330.0, -40.0, 34.0, 34.0, 176.0, "mat_h3_glass_dark"),  # 1 Central Park West
    ("cpw_15", -362.0, -18.0, 46.0, 34.0, 168.0, "mat_h3_limestone"),  # 15 Central Park West
    ("essex_house", -190.0, 0.0, 52.0, 30.0, 138.0, "mat_h3_limestone"),  # 埃塞克斯之家 160 CPS
    (
        "hearst_tower",
        -180.0,
        -260.0,
        44.0,
        44.0,
        182.0,
        "mat_h3_glass_cool",
    ),  # 赫斯特大厦 8th Ave & 57
    ("solow_9w57", 95.0, -215.0, 62.0, 34.0, 210.0, "mat_h3_glass_dark"),  # 9 West 57（斜面楼）
    ("plaza_hotel", 25.0, -35.0, 58.0, 46.0, 76.0, "mat_h3_limestone"),  # 广场饭店（低但地标）
]


def _load_nyc_massing() -> list[tuple]:
    """载入真实曼哈顿建筑体块（`make_view.py --nyc` 生成的 nyc_massing.py）。

    ⭐ 这一层才是让窗外真的像纽约的东西。理由是像素预算算出来的：
       2 km 外一个像素 1.45 m，一层楼(3 m)只占 2.4 像素——**正好在奈奎斯特极限**，
       3 km 外更是被 mipmap 直接抹平。而同距离一栋塔楼的剪影是 27×138 像素。
       **剪影承载的信号是立面纹理的 50–100 倍**，所以力气要花在真实轮廓与真实高度上。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "nyc_massing.py")
    if not os.path.exists(path):
        print(f"⚠️ 没有 {path}——窗外将只有点名的那几栋塔楼。跑 `python make_view.py --nyc` 生成。")
        return []
    import importlib.util

    spec = importlib.util.spec_from_file_location("nyc_massing", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.MASSING)


def _park_flanks() -> list[tuple]:
    """公园东西两侧的那两排楼墙（第五大道 / 中央公园西大道）。

    ⭐ 为什么必须有：没有它们，公园贴图板的边缘就是一条**硬边**——绿色到此为止，
       再往外直接是天空，一眼假（第一版渲染出来就是这样）。
       而现实里公园两侧本来就是连续的楼墙，补上既遮住了板边、又是地理正确的。
    ⚠️ 这一排是**程序化生成的通用体量**，不是点名的具体建筑：
       高度取战前公寓楼的典型区间（55–115 m），进深按街区推。
       ⛔ 别把它和上面 _TOWERS 那份"点名 + 注明高度出处"的清单混为一谈。
    """
    rows: list[tuple] = []
    depth = 42.0  # 临街进深
    seg = 80.5  # 一个街区南北长
    n_seg = 40  # 往北铺 40 个街区 ≈ 3.2 km
    for side, sx in (("w", -PARK_W / 2.0 - depth / 2.0), ("e", PARK_W / 2.0 + depth / 2.0)):
        for i in range(n_seg):
            y = PARK_NEAR_Y + seg * (i + 0.5)
            # ⛔ 用确定性伪随机而不是 random：产物必须可复现、diff 才稳定。
            #    两个互质的乘子叠加 → 高低起伏不重复，看不出周期。
            k = (i * 37 + (0 if side == "w" else 19)) % 12
            j = (i * 23 + (7 if side == "w" else 3)) % 7
            h = 52.0 + k * 5.5 + j * 3.0  # 52 … 136 m，起伏更碎
            # ⚠️ 街墙是**连续**的：进深方向留 2 m 缝而不是 14 m，
            #    否则远看是"一排白牙齿"而不是一道楼墙（第一版就是这毛病）。
            mat = ("mat_h3_limestone", "mat_h3_facade", "mat_h3_glass_dark")[k % 3]
            rows.append((f"flank_{side}{i}", sx, y, depth, seg - 2.0, h - ELEV, mat))
    return rows


_NYC = _load_nyc_massing()

SKYLINE = [(n, x, y, sx, sy, h - ELEV, m) for n, x, y, sx, sy, h, m in _TOWERS] + (
    _NYC if _NYC else _park_flanks()
)

_TOWER_W, _TOWER_D = X4 - X0, Y3 - Y0

_TOWER_CX, _TOWER_CY = (X0 + X4) / 2.0, (Y0 + Y3) / 2.0

HOST_TOWER = [
    # 窗台线以下一直到街面的立面（与玻璃齐平）
    {
        "name": "host_facade",
        "pos": (_TOWER_CX, _TOWER_CY, -ELEV / 2.0 - 0.2),
        "size": (_TOWER_W, _TOWER_D, ELEV - 0.4),
        "mat": "mat_h3_facade",
    },
    # 窗台下一条窄挑檐：给"这是一栋楼"一个交代，但⚠️只探出 0.35 m——
    # 再宽就会在俯视镜头里挡住公园（这正是第一版的毛病）。
    {
        "name": "host_ledge",
        "pos": (_TOWER_CX, _TOWER_CY, -0.24),
        "size": (_TOWER_W + 0.70, _TOWER_D + 0.70, 0.22),
        "mat": "mat_h3_facade",
    },
]

VISUAL = {
    # ⚠️ zfar × extent 必须大于**最远那块视景几何**的距离，否则远端被裁掉，
    #    而画面上读起来像"大气雾霾"，根本想不到是裁剪 bug。
    #    实际踩过：zfar=500 → 3000 m，而公园伸到 4230 m，远半截凭空消失。
    #    现在：1600 × extent 6 = 9600 m，盖得住公园(4230)和城市底图(10000 的一半)。
    #    check_view 会算这个乘积并断言，改远景尺寸时不用再靠肉眼发现。
    "zfar": 1600,
    # ⚠️ shadowclip 默认 1 → 方向光阴影体半边长 = 1 × extent = 6 m，
    #    而公寓是 23 × 15 m，大半个屋子落在阴影视锥外、根本没影子——
    #    这就是"MuJoCo 阴影不行"的误解来源。2.5 → 15 m 半边长，30 m / 4096 ≈ 7.3 mm/纹素。
    "shadowclip": 2.5,
    # 头灯是 MuJoCo **唯一**的环境光项，也是最便宜的"北向天光"暗示。调冷、并且要够亮：
    # ⚠️ 这屋子 23×15 m 且中脊无窗，头灯给低了整层发灰、天花板发暗（第一版 0.40/0.30 就是）。
    #    ⛔ 但也别一味调高——没有全局光照，头灯过亮会把所有立体感洗平。0.56/0.44 是渲出来比的。
    "headlight_diffuse": "0.56 0.57 0.60",
    "headlight_ambient": "0.44 0.45 0.48",
    "headlight_specular": "0.08 0.08 0.08",
}

GEOM_BANDS = {
    "uws": {"prefix": "sky_nyc", "x_max": -PARK_W / 2.0, "y_min": PARK_NEAR_Y},
    "ues": {"prefix": "sky_nyc", "x_min": PARK_W / 2.0, "y_min": PARK_NEAR_Y},
    "inpark": {"prefix": "sky_nyc", "x_abs_max": PARK_W / 2.0 - 40.0, "y_min": PARK_NEAR_Y + 40.0},
    "host": {"names": ("host_facade", "host_ledge")},
    # 12 栋点名近塔（中央公园大厦、220 CPS 那批）：名单从 _TOWERS 推导，⛔ 不抄第二份
    "neartw": {"names": tuple(f"sky_{t[0]}" for t in _TOWERS)},
}

LIGHTS_BY_TIME: dict[str, dict] = {
    "day": {},
    "dusk": {
        "sky": "dusk",
        "headlight": {
            "diffuse": "0.40 0.375 0.40",
            "ambient": "0.32 0.295 0.33",
            "specular": "0.07 0.07 0.07",
        },
        "materials": {
            "mat_h3_limestone": {"emission": 0.3, "rgba": "1.00 0.90 0.74 1"},
            "mat_h3_facade": {"emission": 0.26, "rgba": "0.92 0.84 0.72 1"},
            "mat_h3_glass_dark": {"emission": 0.22, "rgba": "0.66 0.62 0.66 1"},
            "mat_h3_glass_cool": {"emission": 0.26, "rgba": "0.92 0.86 0.86 1"},
            "mat_h3_park": {"emission": 0.2, "rgba": "0.60 0.50 0.42 1"},
            "mat_h3_city": {"emission": 0.34, "rgba": "0.92 0.74 0.58 1"},
        },
        "geom_tint": (
            {"where": "uws", "rgba": (1.0, 0.66, 0.32, 1.0)},
            {"where": "ues", "rgba": (0.62, 0.56, 0.62, 1.0)},
            {"where": "neartw", "rgba": (0.46, 0.4, 0.42, 1.0)},
            {"where": "host", "rgba": (0.72, 0.68, 0.64, 1.0)},
        ),
        "glass": {
            "bind_material": "mat_glass",
            "rgba": "0.86 0.72 0.58 0.11",
            "specular": 0.75,
            "shininess": 0.9,
            "reflectance": 0.2,
            "emission": 0.03,
        },
    },
    "morning": {
        "sky": "morning",
        "headlight": {
            "diffuse": "0.42 0.45 0.52",
            "ambient": "0.34 0.37 0.44",
            "specular": "0.07 0.07 0.07",
        },
        "materials": {
            "mat_h3_limestone": {"emission": 0.16, "rgba": "1.00 0.96 0.92 1"},
            "mat_h3_glass_dark": {"emission": 0.1, "rgba": "0.54 0.62 0.76 1"},
            "mat_h3_glass_cool": {"emission": 0.12},
            "mat_h3_park": {"emission": 0.3, "rgba": "0.78 0.84 0.82 1"},
            "mat_h3_city": {"emission": 0.3, "rgba": "0.80 0.84 0.90 1"},
        },
        "glass": {
            "bind_material": "mat_glass",
            "rgba": "0.70 0.78 0.88 0.09",
            "specular": 0.6,
            "shininess": 0.85,
            "reflectance": 0.12,
            "emission": 0.02,
        },
    },
    "night": {
        "sky": "night",
        "headlight": {
            "diffuse": "0.13 0.115 0.10",
            "ambient": "0.115 0.10 0.09",
            "specular": "0.05 0.05 0.05",
        },
        "materials": {
            "mat_h3_limestone": {"emission": 0.55, "rgba": "1.00 0.86 0.62 1"},
            "mat_h3_facade": {"emission": 0.5, "rgba": "0.86 0.80 0.70 1"},
            "mat_h3_glass_dark": {"emission": 0.62, "rgba": "0.62 0.68 0.86 1"},
            "mat_h3_glass_cool": {"emission": 0.58, "rgba": "0.72 0.82 1.00 1"},
            "mat_h3_park": {"emission": 0.05, "rgba": "0.14 0.17 0.15 1"},
            "mat_h3_city": {"emission": 0.2, "rgba": "0.44 0.36 0.26 1"},
        },
        "geom_tint": (
            {"where": "inpark", "rgba": (0.1, 0.11, 0.12, 1.0)},
            {"where": "host", "rgba": (0.34, 0.32, 0.3, 1.0)},
        ),
        "textures": {
            "tex_h3_fac_glass": "facade_glass_night.png",
            "tex_h3_fac_stone": "facade_limestone_night.png",
        },
        "glass": {
            "bind_material": "mat_glass",
            "rgba": "0.62 0.66 0.76 0.16",
            "specular": 0.92,
            "shininess": 0.94,
            "reflectance": 0.3,
            "emission": 0.05,
        },
    },
}


def bands_for_building(name, x, y):
    """Classify before mesh batching, preserving the original spatial tint regions."""
    geometry_name = "sky_" + name
    result = []
    for key, band in GEOM_BANDS.items():
        if key == "host":
            continue
        if "names" in band:
            matches = geometry_name in band["names"]
        else:
            matches = geometry_name.startswith(band["prefix"])
            matches &= "x_max" not in band or x < band["x_max"]
            matches &= "x_min" not in band or x > band["x_min"]
            matches &= "x_abs_max" not in band or abs(x) < band["x_abs_max"]
            matches &= "y_min" not in band or y > band["y_min"]
        if matches:
            result.append(key)
    return tuple(result)
