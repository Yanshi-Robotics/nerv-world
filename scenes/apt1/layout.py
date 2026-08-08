"""apt1 布局 —— 曼哈顿高层豪宅大平层，落地窗外是中央公园。

坐标系：MuJoCo 世界系，x 向东、y 向北、z 向上，单位米。
⚠️ 本文件的尺寸一律写**全长**；MJCF 要半长，折半只在 make_house.py 做一次。

═══ 这个场景要解决什么 ═══

house1 是平层、house2 是三层带楼梯，两个都在"屋里"。apt1 加的是**窗外**：
一套 62 层的满层大平层，北面整墙落地窗正对中央公园。它要考的是
"机器人在一个视觉信息极强、且**窗外是 232 米空气**的环境里还站不站得住"。

═══ 户型（单层满层大平层，23.0 × 15.0 m 毛尺寸，13 个空间，净面积约 345 ㎡）═══

⭐ **整层一户**是曼哈顿豪宅最典型的形态（220 CPS、15 CPW 都是），而且它让
   所有主要房间都能贴着同一面观景墙。

                                    北 = 公园 (y+)
  ┌──────────┬──────────┬────────────────────┬──────────┐ y=7.5  ← 观景墙，整面落地窗
  │  主 卧    │  餐 厅    │      大 客 厅        │  厨 房    │
  │          │          │   ★ 三开间落地窗      │          │
  ├──────────┼──────────┴────────────────────┼──────────┤ y=2.2
  │ 衣帽/更衣 │            画  廊               │  东过厅   │  ← 中脊，无窗
  ├──────────┼──────────┬────┬────────┬───────┼──────────┤ y=-1.2
  │          │          │客卫 │        │ 洗衣  │          │
  │  主 卫    │  客 卧    │    │ 玄 关   │       │  书 房    │
  │ (独立浴缸) │          │    │  ▲入户  │       │          │
  └──────────┴──────────┴────┴────────┴───────┴──────────┘ y=-7.5
  x=-11.5    -6.4      -1.6  0.4      4.2    6.2       11.5

⭐ **贯通轴线（作品集第一张图）**：玄关 → 画廊 → 大客厅的门洞全部对齐在 x = 2.3，
   而那正好是大客厅中间那扇落地窗的中心。站在入户门口往北看，视线穿过三个房间，
   直接落到中央公园上方 232 米的空气里。

⭐ **核心筒的处理**：house1/house2 的大门都开在外墙上、门外是草地。这里门外是
   **232 米的空气**。所以南带中间三间（客卫 / 玄关 / 洗衣）就是楼栋核心筒，⛔ 永不开窗；
   入户门是玄关南墙上的一块门板，两侧配两扇私人电梯门（当家具做）。
   这样"门外"永远不会被看见，也就不用编造一个不存在的走廊。

═══ 窗外那 232 米 ═══

见 `make_view.py` 的文件头：为什么用几何 + 俯视贴图而不是一张平视照片
（一句话：照片没有视差，而这是个物理仿真，相机一定会动；照片的俯角也对不上 62 层）。

⚠️ **室内一切照旧从 z = 0 起算**——出生高度、statistic、消费方全都不用改。
   "62 层"只体现为**窗外那些几何体被压到 −232.5 m**。⛔ 别把室内抬上去。
"""
from __future__ import annotations

import math
import os

from scenes import furniture as F  # noqa: E402

# ---------------------------------------------------------------- 建筑尺度
WALL_HEIGHT = 3.30     # 层高(m)。曼哈顿高端公寓 10'8" ≈ 3.25，取 3.30
WALL_THICK = 0.14
DOOR_HEIGHT = 2.40     # 门洞净高，比 house1 高一点（层高更高，门也该更高）
FLOOR_THICK = 0.05
CEILING_THICK = 0.10

CEILING_GROUP = 1      # ⚠️ 必须用默认可见的组（MuJoCo 默认不渲染 group ≥3）
CEILING_RGBA = (0.96, 0.96, 0.94, 1.0)

WINDOW_SILL_H = 0.95           # 普通窗（本场景其实没有普通窗，留着满足契约）
WINDOW_TOP_H = 2.35
FLOOR_WINDOW_SILL = 0.05       # 落地窗：贴地，只留一条压条
FLOOR_WINDOW_TOP = WALL_HEIGHT - 0.12   # 顶上留一条窗帘盒/幕墙收口

DOOR_FRAME_THICK = 0.05
DOOR_FRAME_RGBA = (0.20, 0.19, 0.18, 1.0)      # 深色金属门套（高端住宅常见）
WINDOW_FRAME_T = 0.05
WINDOW_FRAME_RGBA = (0.16, 0.16, 0.17, 1.0)    # 幕墙竖挺，深灰
ART_FRAME_T = 0.05
ART_FRAME_RGBA = (0.16, 0.14, 0.12, 1.0)

# ⛔ 落地窗必须有**可碰撞**的玻璃。见 make_house._glazing() 的说明：
#    没有它，walkthrough 的胸高射线打不到东西，人和机器人会直接从 232 米走出去。
# ⭐ 墙面朝向修正：把竖着的墙板转到"局部 +Z = 法线"，2D 贴图才不会被拉成条纹。
#    ⛔ 这个开关会改变产物，house1/house2 不开（它们的程序化噪点贴图看不出条纹）。
WALL_FACE_FIX = True

GLASS_RGBA = (0.80, 0.88, 0.94, 0.07)
GLASS_THICK = 0.03

# ---------------------------------------------------------------- 楼层高度
FLOOR_LEVEL = 62               # 第几层
FLOOR_TO_FLOOR = 3.75          # 层高（含楼板），曼哈顿高端住宅的常见值
ELEV = FLOOR_LEVEL * FLOOR_TO_FLOOR    # 232.5 m —— 窗台离街面的高度

# ---------------------------------------------------------------- 平面网格
X0, X1, X2, XB, XC, X3, X4 = -11.5, -6.4, -1.6, 0.4, 4.2, 6.2, 11.5
Y0, Y1, Y2, Y3 = -7.5, -1.2, 2.2, 7.5

ENFILADE_X = (XB + XC) / 2.0   # 2.3 —— 玄关中心 = 画廊门 = 大客厅中间那扇窗
PARK_WALL_Y = Y3               # 观景墙

# 配色：高端住宅的中性色调（暖白墙 + 木/石地）
W_WARM = (0.93, 0.91, 0.88, 1.0)       # 暖白
W_STONE = (0.86, 0.85, 0.83, 1.0)      # 石灰岩色
W_DARK = (0.32, 0.31, 0.30, 1.0)       # 深色调（影音室/衣帽间）

ROOMS = {
    # ── 北带：全部朝公园 ──────────────────────────────────────────────
    "primary_bed": {"rect": (X0, Y2, X1, Y3), "label": "主卧",
                    "wall_rgba": W_WARM, "floor_rgba": (0.55, 0.42, 0.30, 1.0),
                    "floor_mat": "mat_h3_oak", "wall_mat": "mat_h3_wall"},
    "dining": {"rect": (X1, Y2, X2, Y3), "label": "餐厅",
               "wall_rgba": W_WARM, "floor_rgba": (0.55, 0.42, 0.30, 1.0),
               "floor_mat": "mat_h3_oak", "wall_mat": "mat_h3_wall"},
    "great_room": {"rect": (X2, Y2, X3, Y3), "label": "大客厅",
                   "wall_rgba": W_WARM, "floor_rgba": (0.55, 0.42, 0.30, 1.0),
                   "floor_mat": "mat_h3_oak", "wall_mat": "mat_h3_wall"},
    "kitchen": {"rect": (X3, Y2, X4, Y3), "label": "厨房",
                "wall_rgba": W_STONE, "floor_rgba": (0.80, 0.79, 0.77, 1.0),
                "floor_mat": "mat_h3_travertine", "wall_mat": "mat_h3_wall"},
    # ── 中脊：无窗 ───────────────────────────────────────────────────
    "dressing": {"rect": (X0, Y1, X1, Y2), "label": "衣帽间",
                 "wall_rgba": W_DARK, "floor_rgba": (0.50, 0.38, 0.27, 1.0),
                 "floor_mat": "mat_h3_oak_dark"},
    "gallery": {"rect": (X1, Y1, X3, Y2), "label": "画廊",
                "wall_rgba": W_WARM, "floor_rgba": (0.78, 0.77, 0.75, 1.0),
                "floor_mat": "mat_h3_marble", "wall_mat": "mat_h3_wall"},
    "east_hall": {"rect": (X3, Y1, X4, Y2), "label": "东过厅",
                  "wall_rgba": W_STONE, "floor_rgba": (0.78, 0.77, 0.75, 1.0),
                  "floor_mat": "mat_h3_travertine"},
    # ── 南带 ────────────────────────────────────────────────────────
    "suite_bath": {"rect": (X0, Y0, X1, Y1), "label": "主卫（独立浴缸）",
                   "wall_rgba": (0.90, 0.90, 0.89, 1.0), "floor_rgba": (0.85, 0.85, 0.84, 1.0),
                   "floor_mat": "mat_h3_marble", "wall_mat": "mat_h3_onyx"},
    "guest_bed": {"rect": (X1, Y0, X2, Y1), "label": "客卧",
                  "wall_rgba": W_WARM, "floor_rgba": (0.55, 0.42, 0.30, 1.0),
                  "floor_mat": "mat_h3_oak", "wall_mat": "mat_h3_wall"},
    "guest_bath": {"rect": (X2, Y0, XB, Y1), "label": "客卫",
                   "wall_rgba": (0.88, 0.88, 0.87, 1.0), "floor_rgba": (0.82, 0.82, 0.81, 1.0),
                   "floor_mat": "mat_tile_grey"},
    "foyer": {"rect": (XB, Y0, XC, Y1), "label": "入户玄关",
              "wall_rgba": W_STONE, "floor_rgba": (0.80, 0.79, 0.77, 1.0),
              "floor_mat": "mat_h3_travertine", "wall_mat": "mat_h3_wall"},
    "laundry": {"rect": (XC, Y0, X3, Y1), "label": "洗衣房",
                "wall_rgba": (0.88, 0.88, 0.87, 1.0), "floor_rgba": (0.80, 0.80, 0.79, 1.0),
                "floor_mat": "mat_tile"},
    "study": {"rect": (X3, Y0, X4, Y1), "label": "书房",
              "wall_rgba": (0.36, 0.34, 0.32, 1.0), "floor_rgba": (0.45, 0.33, 0.23, 1.0),
              "floor_mat": "mat_h3_oak_dark"},
}

# ---------------------------------------------------------------- 门 / 通道
# orient: "h" = 门开在一条水平墙上（y = coord），"v" = 竖直墙（x = coord）
# kind="open" = 整段墙拆掉的通道，没有门楣也没有门框
DOORS = [
    # ⭐ 贯通轴线：玄关 → 画廊 → 大客厅，三个洞口全部对齐在 ENFILADE_X
    {"orient": "h", "coord": Y1, "center": ENFILADE_X, "width": 2.60, "kind": "open",
     "note": "玄关→画廊（贯通轴线第一道）"},
    {"orient": "h", "coord": Y2, "center": ENFILADE_X, "width": 4.00, "kind": "open",
     "note": "画廊→大客厅（贯通轴线第二道）"},
    # 北带其余
    {"orient": "h", "coord": Y2, "center": -4.00, "width": 2.60, "kind": "open",
     "note": "画廊→餐厅"},
    {"orient": "v", "coord": X1, "center": 0.50, "width": 1.20, "note": "画廊→衣帽间"},
    {"orient": "h", "coord": Y2, "center": -9.00, "width": 1.20, "note": "衣帽间→主卧"},
    {"orient": "v", "coord": X3, "center": 0.50, "width": 1.30, "kind": "open",
     "note": "画廊→东过厅"},
    {"orient": "h", "coord": Y2, "center": 8.85, "width": 1.40, "kind": "open",
     "note": "东过厅→厨房"},
    # 南带
    {"orient": "h", "coord": Y1, "center": -9.00, "width": 1.10, "note": "衣帽间→主卫"},
    {"orient": "h", "coord": Y1, "center": -4.00, "width": 1.10, "note": "画廊→客卧"},
    {"orient": "h", "coord": Y1, "center": -0.60, "width": 0.95, "note": "画廊→客卫"},
    {"orient": "h", "coord": Y1, "center": 5.20, "width": 0.95, "note": "画廊→洗衣房"},
    {"orient": "h", "coord": Y1, "center": 8.85, "width": 1.20, "note": "东过厅→书房"},
]


# ---------------------------------------------------------------- 落地窗
def _glass_wall(room: str, side: str, a: float, b: float, n: int, *,
                pier: float = 0.42, mullion: float = 0.34) -> list[dict]:
    """把一段外墙切成 n 个玻璃开间：两端留墙垛、格间留竖挺。

    ⛔ 为什么不许整段开窗：`make_house._solid_runs()` 在开口铺满整条边时返回**空列表**，
       门楣梁下面就一个支点都没有了。真实的幕墙本来也有墙垛和竖挺，切开既对又好看。
    ⚠️ 开间宽是**推出来的**（把总长扣掉墙垛和竖挺再均分），不写死数字——
       改房间宽度或开间数，这里自动跟着变。
    """
    span = (b - a) - 2 * pier - (n - 1) * mullion
    if span <= 0:
        raise ValueError(f"{room} 的 {side} 墙放不下 {n} 个开间（净长 {b - a:.2f} m）")
    bw = span / n
    out = []
    for i in range(n):
        c = a + pier + bw / 2 + i * (bw + mullion)
        out.append({"room": room, "side": side, "center": round(c, 4), "width": round(bw, 4),
                    "sill": FLOOR_WINDOW_SILL, "top": FLOOR_WINDOW_TOP, "glass": True})
    return out


WINDOWS = (
    # ── 北面观景墙：整排朝中央公园 ─────────────────────────────────
    _glass_wall("primary_bed", "n", X0, X1, 2)
    + _glass_wall("dining", "n", X1, X2, 2)
    + _glass_wall("great_room", "n", X2, X3, 3)      # ⭐ 中间那扇正对贯通轴线
    + _glass_wall("kitchen", "n", X3, X4, 2)
    # ── 西面：主卧转角 + 主卫（浴缸就摆在这扇窗前）────────────────────
    + _glass_wall("primary_bed", "w", Y2, Y3, 1)
    + _glass_wall("suite_bath", "w", Y0, Y1, 1)
    # ── 东面：厨房转角 + 书房 ────────────────────────────────────
    + _glass_wall("kitchen", "e", Y2, Y3, 1)
    + _glass_wall("study", "e", Y0, Y1, 1)
    # ── 南面：客卧与书房（望中城）────────────────────────────────
    + _glass_wall("guest_bed", "s", X1, X2, 2)
    + _glass_wall("study", "s", X3, X4, 2)
    # ⛔ 客卫 / 玄关 / 洗衣房**永不开窗**：那一段是楼栋核心筒，外面是 232 米空气。
)

# 入户门：玄关南墙上的门板（纯视觉）。门外就是核心筒，永远看不到。
FRONT_DOOR = {"pos": (ENFILADE_X, Y0 + 0.02, 1.20), "size": (1.30, 0.06, 2.40),
              "rgba": (0.22, 0.20, 0.18, 1.0)}
FRONT_DOOR_HANDLE = {"pos": (ENFILADE_X + 0.52, Y0 + 0.08, 1.10), "size": (0.04, 0.04, 0.34),
                     "rgba": (0.72, 0.68, 0.58, 1.0)}

# ---------------------------------------------------------------- 出生点
# ⚠️ 站在入户门内侧，正对贯通轴线朝北——一开局就是那张 15 米穿透三个房间的画面。
# ⛔ 不许踩在地毯上：house1 2026-07-25 的教训（生在门厅垫子上，机器人 156° 翻了）。
START_POS_XY = (ENFILADE_X, Y0 + 0.90)
START_YAW = math.pi / 2

# ---------------------------------------------------------------- 机器人停机位（「保姆间」）
# ⭐ 这是 Jeff 2026-08-08 定的：那台当比例尺 / 待命的机器人得有个**自己的房间**，
#    别杵在通行流线正中挡路。
# ⛔ 它和 START_POS_XY 是**两个不同的量**，别合并：
#    · START_POS_XY = **任务出生点**，消费方（anima-zero 的 sim-house-nav）读它写 qpos，
#      导航任务从那儿起步；
#    · ROBOT_HOME_XY = **停机位**，`tools/walkthrough.py` 把静态机器人摆在这儿。
#    合并会悄悄改变消费方的行为，而那个仓这一轮一个字都不许动。
# 选洗衣房：净空 1.72 × 6.02，三件设备全挤在南端（y ≤ -6.73），北面 9.3 ㎡ 全空；
# 一道 0.95 m 的门直通画廊主流线，而它本身**不在任何必经动线上**。
ROBOT_HOME_XY = (5.20, -4.60)
ROBOT_HOME_YAW = -math.pi / 2       # 朝南面向门

# ---------------------------------------------------------------- 挂画
# ⛔ 挂画不许压在门洞/窗洞上 —— 会变成一块悬在过道正中间的板子，而且**从代码上完全看不出来**，
#    只有渲染了才发现。第一版就把一幅画挂到了贯通轴线的门洞里（渲染出来是一块大黑板挡着公园）。
#    现在 check_scene 的 `check_art_clear` 会算重叠并当场报错，改画位不用再靠肉眼。
#    画廊南北墙的空档（扣掉门洞后）：
#      北墙 y=Y2：-6.4…-5.3 / -2.7…0.3 / 4.3…6.2
#      南墙 y=Y1：-6.4…-4.55 / -3.45…-1.075 / -0.125…1.0 / 3.6…4.725 / 5.675…6.2
WALL_ARTS = [
    # 画廊两侧的长墙就是为挂画留的（12.6 m 的展线）
    {"room": "gallery", "side": "n", "center": -1.20, "z": 1.75, "w": 1.80, "h": 1.25, "tex": "art0"},
    {"room": "gallery", "side": "n", "center": 5.25, "z": 1.75, "w": 1.40, "h": 1.10, "tex": "art2"},
    {"room": "gallery", "side": "s", "center": -2.25, "z": 1.75, "w": 1.60, "h": 1.15, "tex": "art1"},
    {"room": "gallery", "side": "s", "center": 4.16, "z": 1.75, "w": 0.95, "h": 1.05, "tex": "art3"},
    {"room": "great_room", "side": "e", "center": 4.60, "z": 1.80, "w": 1.70, "h": 1.20, "tex": "art2"},
    {"room": "dining", "side": "w", "center": 5.00, "z": 1.80, "w": 1.40, "h": 1.00, "tex": "art1"},
    {"room": "foyer", "side": "e", "center": -4.20, "z": 1.75, "w": 1.20, "h": 0.90, "tex": "art3"},
    {"room": "study", "side": "n", "center": 7.20, "z": 1.75, "w": 1.30, "h": 0.95, "tex": "art0"},
]

# ================================================================
#                        窗  外  的  232  米
# ================================================================

# ---------------------------------------------------------------- 天空盒
# 目前是程序化渐变（干净、无许可负担）。将来换成 make_view.py --fetch 渲染出的六面实景。
# 实景天空：Poly Haven `kloofendal_48d_partly_cloudy_puresky`（**CC0**）的色调映射全景
# 切成六面，2048 px/面。生成命令 `python make_view.py --sky`。
# ⛔ 六个文件名到世界方向的对应是**实测**的，不是照字面命名填的——见 make_view.SKY_FACE_FOR_DIR：
#    up↔down、left↔right 全部对调。照字面填天空会上下翻转+左右镜像，而且照样"挺好看"。
# ⛔ 那张 HDRI 是南非拍的，南半球正午太阳在**北**；生成时已横向旋转 180° 把太阳摆到南边，
#    否则中央公园正上方会挂一个 40.77°N 不可能出现的太阳。
SKYBOX = {
    "fileright": "textures/house3/sky_fileright.png",
    "fileleft": "textures/house3/sky_fileleft.png",
    "fileup": "textures/house3/sky_fileup.png",
    "filedown": "textures/house3/sky_filedown.png",
    "filefront": "textures/house3/sky_filefront.png",
    "fileback": "textures/house3/sky_fileback.png",
}

# ---------------------------------------------------------------- 额外贴图/材质
# ⛔ 名字一律带 h3_ 前缀，不和 make_textures.py 那 20 张基础贴图撞 —— 不撞 = 老场景零回归面。
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
    *[{"name": f"tex_h3_{n}", "file": f"textures/house3/h3_{n}.png", "colorspace": "sRGB"}
      for n in ("oak", "oak_dark", "marble", "marble_blk", "travertine", "linen", "rug")],
    *[{"name": f"tex_h3_{n}", "file": f"textures/house3/h3_{n}.png",
       "colorspace": "sRGB"} for n in ("plaster", "onyx")],
    {"type": "cube", "name": "tex_h3_fac_glass", "gridsize": "3 4", "gridlayout": ".U..LFRB.D..",
     "file": "textures/house3/facade_glass.png", "colorspace": "sRGB"},
    {"type": "cube", "name": "tex_h3_fac_stone", "gridsize": "3 4", "gridlayout": ".U..LFRB.D..",
     "file": "textures/house3/facade_limestone.png", "colorspace": "sRGB"},
]

# 一块立面贴图 = 4 层楼高。texuniform="true" 的含义是"每 1 个空间单位重复 N 次"，
# 所以 texrepeat = 1/(4 层 × 层高)，不同大小的楼共用一张图也不会被拉伸变形。
_FAC_TILE_M = 4 * FLOOR_TO_FLOOR        # 15.0 m
_FAC_REP = round(1.0 / _FAC_TILE_M, 5)
MATERIALS_EXTRA = [
    # ⭐ emission 让窗外的白天不被室内灯光"照暗"。
    #    ⚠️ 别给满 1.0——亮部会削顶成死白。0.45 是对着渲染结果调的。
    {"name": "mat_h3_park", "texture": "tex_h3_park", "texrepeat": "1 1", "texuniform": "false",
     "specular": "0", "shininess": "0", "reflectance": "0", "emission": "0.45"},
    {"name": "mat_h3_city", "texture": "tex_h3_city", "texrepeat": "1 1", "texuniform": "false",
     "specular": "0", "shininess": "0", "reflectance": "0", "emission": "0.45"},
    # 远处塔楼：真的贴上窗格立面（之前是纯色盒子，远看就是一堆灰乐高）。
    # rgba 仍然给着——它给贴图**染色**，让三种楼各有色调，不至于一模一样。
    {"name": "mat_h3_glass_cool", "texture": "tex_h3_fac_glass",
     "texrepeat": f"{_FAC_REP} {_FAC_REP}", "texuniform": "true", "rgba": "0.86 0.94 1.0 1",
     "specular": "0.55", "shininess": "0.80", "reflectance": "0.18", "emission": "0.10"},
    {"name": "mat_h3_glass_dark", "texture": "tex_h3_fac_glass",
     "texrepeat": f"{_FAC_REP} {_FAC_REP}", "texuniform": "true", "rgba": "0.58 0.64 0.74 1",
     "specular": "0.50", "shininess": "0.75", "reflectance": "0.15", "emission": "0.08"},
    {"name": "mat_h3_limestone", "texture": "tex_h3_fac_stone",
     "texrepeat": f"{_FAC_REP} {_FAC_REP}", "texuniform": "true", "rgba": "1.0 0.97 0.90 1",
     "specular": "0.10", "shininess": "0.20", "reflectance": "0.02", "emission": "0.12"},
    # 本楼外皮：同一套立面，色调偏中性
    {"name": "mat_h3_facade", "texture": "tex_h3_fac_stone",
     "texrepeat": f"{_FAC_REP} {_FAC_REP}", "texuniform": "true", "rgba": "0.80 0.80 0.78 1",
     "specular": "0.25", "shininess": "0.40", "reflectance": "0.05"},
    # ── 室内材质：ambientCG 的 CC0 照片级贴图（`python fetch_assets.py` 下载）──
    # ⚠️ texrepeat 按**物理尺度**给，不是凭眼睛调：每张贴图 1024 px 覆盖约 2 m 见方，
    #    所以 N 米的面上重复 N/2 次。房间尺寸一改，观感不会跟着变形。
    # cube 贴图配 texuniform="true" = "每 1 个空间单位重复 N 次"，
    # 所以 1/2.2 表示一张图铺 2.2 m 见方——不同大小的墙共用一张也不会变形。
    {"name": "mat_h3_wall", "texture": "tex_h3_plaster", "texrepeat": "2 2",
     "rgba": "1.06 1.05 1.02 1",
     "specular": "0.04", "shininess": "0.08", "reflectance": "0.01"},
    {"name": "mat_h3_oak", "texture": "tex_h3_oak", "texrepeat": "3 3",
     "specular": "0.14", "shininess": "0.24", "reflectance": "0.03"},
    {"name": "mat_h3_oak_dark", "texture": "tex_h3_oak_dark", "texrepeat": "3 3",
     "specular": "0.12", "shininess": "0.22", "reflectance": "0.02"},
    {"name": "mat_h3_marble", "texture": "tex_h3_marble", "texrepeat": "2 2",
     "specular": "0.45", "shininess": "0.72", "reflectance": "0.14"},
    {"name": "mat_h3_marble_blk", "texture": "tex_h3_marble_blk", "texrepeat": "1 1",
     "specular": "0.55", "shininess": "0.80", "reflectance": "0.18"},
    {"name": "mat_h3_travertine", "texture": "tex_h3_travertine", "texrepeat": "2 2",
     "specular": "0.22", "shininess": "0.38", "reflectance": "0.05"},
    {"name": "mat_h3_onyx", "texture": "tex_h3_onyx", "texrepeat": "2 2",
     "specular": "0.40", "shininess": "0.66", "reflectance": "0.12"},
    {"name": "mat_h3_linen", "texture": "tex_h3_linen", "texrepeat": "4 4",
     "specular": "0.05", "shininess": "0.10", "reflectance": "0.01"},
    {"name": "mat_h3_rug", "texture": "tex_h3_rug", "texrepeat": "3 3",
     "specular": "0.03", "shininess": "0.06", "reflectance": "0.0"},
]

# ---------------------------------------------------------------- C 层：脚下的地面
# ⭐ 水平板是 MuJoCo 给基本体贴 2D 图**唯一投影正确**的朝向（本仓的地板就是活证据）。
#    而且从 62 层往外看，视线大部分是往下往外扫的，**俯角由几何天然保证**——
#    这是任何一张平视照片都给不了的。
# ⚠️ 本楼**贴着中央公园南沿**（像 220 CPS 那样），这个数就是中央公园南路的路宽。
#    第一版写 120 m，那大约是 57 街——**和公园之间隔着 59 街整整一排楼**，
#    新自检 check_park_sightline 用真实建筑数据当场把这个错抓了出来。
PARK_NEAR_Y = 34.0             # 公园南界（59 街）离本楼北立面的距离 = 路宽
PARK_W = 800.0                 # 公园东西宽（五大道 ↔ 中央公园西大道）
PARK_L = 4110.0                # 公园南北长（59 街 ↔ 110 街 = 51 个街区）

# ⚠️ 这个数必须和 `make_view.naip_park()` 抓城市底图时用的范围**一致**，
#    否则贴图会被拉伸或压缩（板子 20000 m、贴图只抓 16000 m，第一版就是这样）。
#    两边都硬写一次迟早对不上，所以这里注明来源，改一处必须改另一处。
CITY_SPAN = 16000.0            # ← make_view.py 里 _naip_square(center, 16000.0, 2048)

GROUND_SLABS = [
    {"name": "park_ground", "pos": (0.0, PARK_NEAR_Y + PARK_L / 2.0, -ELEV),
     "size": (PARK_W, PARK_L, 4.0), "mat": "mat_h3_park"},
    # 城市底图更大更低（低 0.6 m 避免和公园板 z-fighting），外圈已把地平线渐隐烤进贴图。
    # ⛔ 不用 MuJoCo 的 haze/fog：那是渲染标志不是模型状态，每个消费方都得各自设，一定有人漏。
    {"name": "city_ground", "pos": (0.0, 0.0, -ELEV - 0.6),
     "size": (CITY_SPAN, CITY_SPAN, 4.0), "mat": "mat_h3_city"},
]

# ---------------------------------------------------------------- B 层：中景塔楼
# (名字, x, y, 东西向边长, 南北向边长, 楼顶相对本层地面的标高, 材质)
#
# ⭐ 高度是**公开事实**（各楼的建筑高度），逐条注明。事实不受著作权保护，
#    十几条也构不成任何数据库的实质性提取 —— 这是本方案的许可防火墙，
#    ⛔ 别为了省事把这一层和将来 make_view.py --fetch 的自动抓取混在一起。
# ⚠️ 平面位置是**按曼哈顿街网估算的近似值**（街区南北 80.5 m、大道间距 274 m），
#    不是测绘坐标。如实登记：它保证"亿万富翁街那一排在正确的方位和相对高低"，
#    不保证米级精度。
_TOWERS = [
    # 名字               x       y     边长      建筑高度(m)   材质
    ("central_park_twr", -55.0, -120.0, 44.0, 44.0, 472.4, "mat_h3_glass_cool"),  # 中央公园大厦 217 W 57
    ("steinway_111w57",  185.0, -110.0, 26.0, 26.0, 435.3, "mat_h3_limestone"),   # 111 West 57（施坦威大厦）
    ("one57",            150.0, -125.0, 38.0, 38.0, 306.1, "mat_h3_glass_dark"),  # One57，157 W 57
    ("w53_53",           420.0, -230.0, 40.0, 40.0, 320.0, "mat_h3_glass_dark"),  # 53 West 53
    # ⛔ 下面这几栋**必须在 y ≤ 0**（和本楼同在中央公园南沿或更南）。
    #    第一版把 220 CPS 放到了 y=+45，也就是**放进了公园里**，结果它正杵在
    #    本楼和公园之间，把大客厅望出去的左半边全挡死（渲染出来才发现）。
    #    现在 check_park_sightline 会算"本楼到公园之间有没有东西"，不用再靠肉眼。
    ("cps_220",          -95.0,    0.0, 34.0, 46.0, 290.0, "mat_h3_limestone"),   # 220 Central Park South（本楼西邻）
    ("deutsche_bank",   -255.0,  -60.0, 60.0, 46.0, 229.2, "mat_h3_glass_dark"),  # 哥伦布圆环 时代华纳中心
    ("trump_intl",      -330.0,  -40.0, 34.0, 34.0, 176.0, "mat_h3_glass_dark"),  # 1 Central Park West
    ("cpw_15",          -362.0,  -18.0, 46.0, 34.0, 168.0, "mat_h3_limestone"),   # 15 Central Park West
    ("essex_house",     -190.0,    0.0, 52.0, 30.0, 138.0, "mat_h3_limestone"),   # 埃塞克斯之家 160 CPS
    ("hearst_tower",    -180.0, -260.0, 44.0, 44.0, 182.0, "mat_h3_glass_cool"),  # 赫斯特大厦 8th Ave & 57
    ("solow_9w57",        95.0, -215.0, 62.0, 34.0, 210.0, "mat_h3_glass_dark"),  # 9 West 57（斜面楼）
    ("plaza_hotel",       25.0,  -35.0, 58.0, 46.0,  76.0, "mat_h3_limestone"),   # 广场饭店（低但地标）
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
        print(f"⚠️ 没有 {path}——窗外将只有点名的那几栋塔楼。"
              f"跑 `python make_view.py --nyc` 生成。")
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
    depth = 42.0                       # 临街进深
    seg = 80.5                         # 一个街区南北长
    n_seg = 40                         # 往北铺 40 个街区 ≈ 3.2 km
    for side, sx in (("w", -PARK_W / 2.0 - depth / 2.0), ("e", PARK_W / 2.0 + depth / 2.0)):
        for i in range(n_seg):
            y = PARK_NEAR_Y + seg * (i + 0.5)
            # ⛔ 用确定性伪随机而不是 random：产物必须可复现、diff 才稳定。
            #    两个互质的乘子叠加 → 高低起伏不重复，看不出周期。
            k = (i * 37 + (0 if side == "w" else 19)) % 12
            j = (i * 23 + (7 if side == "w" else 3)) % 7
            h = 52.0 + k * 5.5 + j * 3.0             # 52 … 136 m，起伏更碎
            # ⚠️ 街墙是**连续**的：进深方向留 2 m 缝而不是 14 m，
            #    否则远看是"一排白牙齿"而不是一道楼墙（第一版就是这毛病）。
            mat = ("mat_h3_limestone", "mat_h3_facade", "mat_h3_glass_dark")[k % 3]
            rows.append((f"flank_{side}{i}", sx, y, depth, seg - 2.0, h - ELEV, mat))
    return rows


# 换算成"楼顶相对本层地面的标高"：建筑高度减去本层离街面的高度。
# ⭐ `_park_flanks()` 那 80 栋程序化街墙**已退役**——真实数据覆盖了同一片区域而且准确得多。
#    函数保留是为了不联网时还有个兜底（`nyc_massing.py` 缺失时自动启用）。
_NYC = _load_nyc_massing()
SKYLINE = ([(n, x, y, sx, sy, h - ELEV, m) for n, x, y, sx, sy, h, m in _TOWERS]
           + (_NYC if _NYC else _park_flanks()))

# ---------------------------------------------------------------- D 层：本楼外皮
# ⛔ 没有它，这套公寓在外景镜头里是**飘在天上**的，从玻璃往正下方看也是一片虚空。
# ⚠️ 立面必须**和窗墙齐平**，不能往外凸。第一版给了 +2.4 m 的富余，结果立面比玻璃还往外
#    探出 1.2 m，从窗边往下看整个画面被自家的墙堵死（渲染出来才发现）。
#    玻璃就是建筑外壳，外壳不该跑到玻璃外面去。
_TOWER_W, _TOWER_D = X4 - X0, Y3 - Y0
_TOWER_CX, _TOWER_CY = (X0 + X4) / 2.0, (Y0 + Y3) / 2.0
HOST_TOWER = [
    # 窗台线以下一直到街面的立面（与玻璃齐平）
    {"name": "host_facade", "pos": (_TOWER_CX, _TOWER_CY, -ELEV / 2.0 - 0.2),
     "size": (_TOWER_W, _TOWER_D, ELEV - 0.4), "mat": "mat_h3_facade"},
    # 窗台下一条窄挑檐：给"这是一栋楼"一个交代，但⚠️只探出 0.35 m——
    # 再宽就会在俯视镜头里挡住公园（这正是第一版的毛病）。
    {"name": "host_ledge", "pos": (_TOWER_CX, _TOWER_CY, -0.24),
     "size": (_TOWER_W + 0.70, _TOWER_D + 0.70, 0.22), "mat": "mat_h3_facade"},
]

# ---------------------------------------------------------------- 灯光
# ⭐ **朝北**。朝北的曼哈顿公寓永远没有直射阳光——柔和均匀的冷色天光。
#    这既符合 57 街往北看公园的真实情况，又正好是**没有全局光照也扛得住**的那种光照条件。
#    唯一那盏方向光放在南偏东，让真阳光只落进书房、客卧、主卫。
# ⚠️ 灯数没有"8 盏上限"那回事——实测 mjMAXLIGHT = 100，house1 的 14 盏一直正常。
#    这里排 10 盏是**为了好看**（一房一盏太平），不是被上限逼的。
# ⚠️ MuJoCo 的**非方向光默认 cutoff = 45°**，也就是说它是一盏 45° 的聚光灯、不是全向光。
#    第一版没设 cutoff，十盏 45° 的锥子照不满 23×15 m 的楼面，整层是暗的——
#    而人的第一反应会是"加灯"或"调高环境光"，那样只会把画面调糊。根因是光锥太窄。
#    ⛔ OpenGL 的聚光上限是 90°，别写更大的数。
_WIDE = 88                     # 用来做泛光的宽锥
_SKY = "0.78 0.82 0.88"        # 冷色天光（比第一版提亮，北向天光本来就该是主光）
_WARM = "0.86 0.80 0.71"       # 室内暖光
LIGHTS = [
    # 唯一的方向光 = 南偏东的低角度阳光。⛔ 它不穿过任何一块玻璃（见下面的玻璃/阴影陷阱）
    {"name": "sun_sse", "pos": "14 -34 26", "dir": "-0.30 0.62 -0.72", "directional": "true",
     "diffuse": "0.50 0.48 0.44", "specular": "0.10 0.10 0.10", "castshadow": "true"},
    # 沿观景墙内侧一排"天光"：⚠️ 放在玻璃**里面**，光线不穿玻璃，绕开阴影贴图的坑
    {"name": "sky_park_w", "pos": "-8.0 6.9 2.9", "dir": "0.10 -0.80 -0.59",
     "diffuse": _SKY, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.40 0.03 0.004"},
    {"name": "sky_park_c", "pos": "2.3 6.9 2.9", "dir": "0 -0.80 -0.59",
     "diffuse": _SKY, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.34 0.02 0.003"},
    {"name": "sky_park_e", "pos": "9.0 6.9 2.9", "dir": "-0.10 -0.80 -0.59",
     "diffuse": _SKY, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.40 0.03 0.004"},
    {"name": "sky_west", "pos": "-11.0 4.5 2.9", "dir": "0.80 -0.20 -0.56",
     "diffuse": _SKY, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.45 0.04 0.006"},
    # 无窗区靠灯：画廊两盏、玄关一盏、核心筒一盏
    {"name": "amb_gallery_w", "pos": "-3.0 0.5 3.1", "dir": "0 0 -1",
     "diffuse": _WARM, "specular": "0.04 0.04 0.04", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.50 0.05 0.008"},
    {"name": "amb_gallery_e", "pos": "3.6 0.5 3.1", "dir": "0 0 -1",
     "diffuse": _WARM, "specular": "0.04 0.04 0.04", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.50 0.05 0.008"},
    {"name": "amb_foyer", "pos": f"{ENFILADE_X} -4.4 3.1", "dir": "0 0 -1",
     "diffuse": _WARM, "specular": "0.04 0.04 0.04", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.50 0.05 0.008"},
    {"name": "amb_core", "pos": "-0.6 -4.4 3.1", "dir": "0 0 -1",
     "diffuse": _WARM, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.60 0.07 0.012"},
    {"name": "amb_dressing", "pos": "-9.0 0.5 3.1", "dir": "0 0 -1",
     "diffuse": _WARM, "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": _WIDE, "attenuation": "0.60 0.07 0.012"},
]

# ---------------------------------------------------------------- 渲染参数
STATISTIC = {"center": f"{(X0 + X4) / 2.0:g} {(Y0 + Y3) / 2.0:g} 1.4", "extent": 6}
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

# ---------------------------------------------------------------- 旧屋外契约
# ⛔ 不是忘了填。窗景走上面的 SKYBOX + GROUND_SLABS + SKYLINE + HOST_TOWER 四层；
#    这几个名字留着是因为 check_scene 的契约要求它们存在，空值 = 生成器什么也不出。
#    （高层公寓脚下没有草地和行道树。）
CITY_BACKDROP: dict = {}
OUTDOOR_GROUND: dict = {}
TREES: list = []
BUILDINGS: list = []
TRUNK_RGBA = (0.0, 0.0, 0.0, 0.0)
FOLIAGE_RGBA = (0.0, 0.0, 0.0, 0.0)

# ---------------------------------------------------------------- 家具
# ⚠️ 阶段 1 先用基本体把体量摆到位（比例、动线、遮挡关系都要对）；
#    阶段 3 再给英雄三间（大客厅 / 餐厅 / 主卧）换成真网格外衣，碰撞盒仍是这些盒子。
_OAK = (0.52, 0.40, 0.28, 1.0)
_LINEN = (0.78, 0.75, 0.70, 1.0)
_CHAR = (0.28, 0.28, 0.30, 1.0)
_BRASS = (0.72, 0.62, 0.38, 1.0)
_STONE = (0.86, 0.85, 0.82, 1.0)
_CLOSET = (0.40, 0.37, 0.34, 1.0)       # 衣帽间通柜的深色柜门

# ⭐ 条案/餐边柜的碰撞盒尺寸 = `console` 网格（Poly Haven modern_wooden_cabinet）
#    在 decor.lock.json 里的真实跨度 2.44 × 0.52 × 0.68 m（长 × 深 × 高）。
#    ⚠️ 写成一个常量而不是三处各填一遍：缩放按三轴最紧的一比取值，比例一偏就白缩，
#    所以这三处必须同步。资产换了就改这一行，别去各处凑数。
#    ⛔ 别拿它当"美术尺寸"随手调小——那会让网格填不满盒子，盒子里空一大截。
_CREDENZA = (2.44, 0.52, 0.68)


def _p(name, room, typ, pos, size, rgba, mat="", yaw=0.0):
    """本文件内摆件用的小助手（和 furniture._p 同构，避免为一块板去调整个家具函数）。"""
    d = {"name": name, "room": room, "type": typ, "pos": pos, "size": size, "rgba": rgba}
    if mat:
        d["mat"] = mat
    if abs(yaw) > 1e-6:
        a = math.radians(yaw) / 2.0
        d["quat"] = (math.cos(a), 0.0, 0.0, math.sin(a))
    return d


FURNITURE: list[dict] = []

# ── 大客厅：转角沙发朝着落地窗，地毯，茶几，两把单椅 ──────────────────
FURNITURE += [
    _p("gr_rug", "great_room", "box", (2.30, 4.60, 0.012), (5.20, 3.60, 0.024), (0.62, 0.58, 0.52, 1.0), mat="mat_h3_rug"),
    # ⛔⛔ 沙发组 + 抱枕 + 茶几 + 木碗**整组北移 0.20**（2026-08-08）。⚠️ 要么一起挪，要么都别挪：
    #    只挪沙发不挪茶几，沙发↔茶几会从 0.425 掉到 0.225。
    #    根因：大客厅只有**一个**出入口——「画廊→大客厅」那个 4.00 m 的 kind="open" 洞口
    #    （x∈[0.30,4.30]），而沙发组含扶手横跨 x∈[0.42,4.18]，把洞口塞掉 3.76 m，
    #    穿过去只落进一条 0.44 m 深的窄缝。实测 **G1 只能到达大客厅 2%**（0.52/37.8 ㎡），
    #    北半区 10.4 ㎡ 连落地窗带茶几整块是**孤岛**——那正是作品集封面那个机位。
    #    ⛔ 而 48 项自检全绿，因为 check_door_passable 当时会跳过 kind="open"（已同轮修掉）。
    #    +0.16 就够到 0.60，取 +0.20 留 4 cm 余量；改完沙发背↔南墙 0.44 → 0.64。
    _p("gr_sofa_base", "great_room", "box", (2.30, 3.50, 0.21), (3.60, 1.00, 0.42), _LINEN, mat="mat_h3_linen"),
    _p("gr_sofa_back", "great_room", "box", (2.30, 3.10, 0.55), (3.60, 0.24, 0.68), _LINEN, mat="mat_h3_linen"),
    _p("gr_sofa_armL", "great_room", "box", (0.55, 3.50, 0.34), (0.26, 1.00, 0.68), _LINEN, mat="mat_h3_linen"),
    _p("gr_sofa_armR", "great_room", "box", (4.05, 3.50, 0.34), (0.26, 1.00, 0.68), _LINEN, mat="mat_h3_linen"),
    # ⚠️ 贵妃榻**不跟着北移**：它和 armL、gr_ch2 本来就各贴着 0（转角沙发的正常搭法，
    #    多出的重叠藏在沙发内部看不出来），跟着挪反而会撞上 gr_ch2。
    _p("gr_chaise", "great_room", "box", (0.10, 4.60, 0.21), (0.95, 1.90, 0.42), _LINEN, mat="mat_h3_linen"),
    # ⭐ 茶几换成真网格：碰撞仍是这个盒子，网格只是套在里面的外衣
    #    （mesh_piece 返回的就是一个普通 box 零件，多带一个 mesh 字段而已）
]
FURNITURE += F.mesh_piece("gr_coffee", "great_room", 2.30, 5.10,   # 跟沙发一起 +0.20
                          size=(1.35, 1.35, 0.50), mesh="coffee_table")
# ⚠️ gr_ch1 西南移 0.30/0.20：它离盆栽只有 **9 mm**、离条案 51 mm，渲染出来就是
#    「椅子压着盆栽」。不是通行必经，纯观感，顺手修。
FURNITURE += F.mesh_piece("gr_ch1", "great_room", 4.60, 6.00, yaw=200,
                          size=(0.90, 1.06, 1.10), mesh="armchair")
FURNITURE += F.mesh_piece("gr_ch2", "great_room", -0.40, 6.20, yaw=-20,
                          size=(0.90, 1.06, 1.10), mesh="armchair")
# 沙发上的抱枕（真网格）
FURNITURE += F.mesh_piece("gr_pillows", "great_room", 1.20, 3.25, z=0.72, yaw=8,   # 跟沙发一起 +0.20
                          size=(1.02, 0.52, 0.50), mesh="pillows")
# 大客厅其余真网格
# ⭐ 三处条案/餐边柜（这里、餐厅 dn_sideboard、玄关 fy_console）共用同一件真木柜网格。
#    ⚠️ 碰撞盒一律按网格自己的比例写 `_CREDENZA`，再用 yaw 转到该靠的那面墙上——
#    缩放是均匀的、按三轴最紧的一比取值，盒子比例偏了就会白缩一大截。
#    （旧值 0.38×1.40×0.84 的玄关条案实测只能填到网格的 57%。）
FURNITURE += F.mesh_piece("gr_console", "great_room", 5.80, 4.60, yaw=90,
                          size=_CREDENZA, mesh="console", rgba=_OAK, mat="mat_h3_oak_dark")
FURNITURE += F.mesh_piece("gr_plant", "great_room", 5.70, 6.60,
                          size=(0.66, 0.70, 1.38), mesh="plant_a")
# ⚠️ x 从 -0.90 挪到 -1.23（贴西墙，2026-08-08）：落地灯直径 0.46，原位置在西墙内表面
#    (-1.46) 与贵妃榻西缘 (-0.375) 之间**正中**，把这条 1.09 m 的走道劈成 0.33 + 0.30 两半，
#    两边都过不去 —— 大客厅西侧 1.27 ㎡ 因此成了走不进去的孤岛。
#    贴墙之后东侧留 0.625 m 的净通道。⭐ 这块是 check_reachability 照出来的，肉眼看图看不出来。
FURNITURE += F.mesh_piece("gr_lamp", "great_room", -1.23, 3.00,
                          size=(0.46, 0.46, 0.98), mesh="floor_lamp")

# ── 餐厅：长桌八椅 + 吊灯下的餐边柜 ────────────────────────────────
FURNITURE += F.table("dn_table", "dining", -4.00, 5.00, 2.40, 1.10, h=0.75)
# ⭐ 餐椅八把全换真网格（每把 5k 面，八把 4 万面——纯视觉不算凸包，编译代价可忽略）
for i, dx in enumerate((-0.80, 0.00, 0.80)):
    FURNITURE += F.mesh_piece(f"dn_n{i}", "dining", -4.00 + dx, 5.85, yaw=-90,
                              size=(0.46, 0.60, 1.00), mesh="dining_chair")
    FURNITURE += F.mesh_piece(f"dn_s{i}", "dining", -4.00 + dx, 4.15, yaw=90,
                              size=(0.46, 0.60, 1.00), mesh="dining_chair")
FURNITURE += F.mesh_piece("dn_e", "dining", -2.75, 5.00, yaw=180,
                          size=(0.46, 0.60, 1.00), mesh="dining_chair")
FURNITURE += F.mesh_piece("dn_w", "dining", -5.25, 5.00, yaw=0,
                          size=(0.46, 0.60, 1.00), mesh="dining_chair")
FURNITURE += F.mesh_piece("dn_chand", "dining", -4.00, 5.00, z=2.72,
                          size=(0.70, 0.66, 0.88), mesh="chandelier")
# ⭐ 餐边柜：同一件真木柜网格，贴餐厅西墙（净空 x ≥ -6.26），yaw=90 转成南北向
FURNITURE += F.mesh_piece("dn_sideboard", "dining", -6.00, 5.00, yaw=90,
                          size=_CREDENZA, mesh="console", rgba=_OAK)
# ⭐ 全屋花瓶摆件换成真网格（Poly Haven CC0，约 4k 面，Jeff 点名要真的）
# ⚠️ z 是**柜面高**（_CREDENZA[2] = 0.68）加上花瓶自身半高，改柜子要连着改这里
FURNITURE += F.mesh_piece("dn_vase", "dining", -6.00, 5.00, z=0.89,
                          size=(0.22, 0.22, 0.42), mesh="vase_a")

# ── 厨房：中岛 + 沿墙操作台 ──────────────────────────────────────
FURNITURE += [
    _p("kt_island", "kitchen", "box", (8.85, 4.60, 0.46), (2.60, 1.10, 0.92), _STONE, mat="mat_h3_marble"),
    _p("kt_island_top", "kitchen", "box", (8.85, 4.60, 0.945), (2.76, 1.26, 0.05), _STONE, mat="mat_h3_marble_blk"),
    _p("kt_counter", "kitchen", "box", (8.85, 7.10, 0.46), (5.00, 0.68, 0.92), _STONE, mat="mat_h3_travertine"),
    _p("kt_counter_top", "kitchen", "box", (8.85, 7.10, 0.945), (5.10, 0.74, 0.05), _STONE, mat="mat_h3_marble_blk"),
    _p("kt_upper", "kitchen", "box", (8.85, 7.28, 2.05), (5.00, 0.34, 0.80), (0.90, 0.89, 0.87, 1.0)),
]
# ⭐ 四件电器换成 RoboCasa 的真网格（NVIDIA HuggingFace 镜像，CC-BY-4.0）。
#    走的还是普通 `mesh_piece`——碰撞真相仍是这里的盒子，网格只是外衣，
#    所以包含性缩放 / calibrate 标定 / 射线不变性自检全部照常生效。
#    ⚠️ 只搬了视觉网格：门和抽屉打不开，灶具的 `<site>` 也没搬（见 decor/robocasa.py 的说明）。
# ⛔ 冰箱这里曾有一个 `_FRIDGE_SHRINK = 0.85` 的额外收缩系数，2026-08-07 删除。
#    它的理由（"9 个材质组的残差互相叠加"）是假的：真因是标定漏转了一次旋转 +
#    摆位多加了一份重心，修完之后冰箱一点都不用收。别照那个理由把它加回来。
FURNITURE += F.mesh_piece("kt_fridge", "kitchen", 11.05, 3.10,
                          size=(0.94, 0.88, 1.90), mesh="rc_fridge", yaw=-90)
FURNITURE += F.mesh_piece("kt_range", "kitchen", 7.20, 7.10,
                          size=(0.78, 0.72, 1.14), mesh="rc_stove", yaw=180)
FURNITURE += F.mesh_piece("kt_sink", "kitchen", 10.10, 7.10, z=1.06,
                          size=(0.80, 0.46, 0.42), mesh="rc_sink", yaw=180)
FURNITURE += F.mesh_piece("kt_hood", "kitchen", 7.20, 7.28, z=1.95,
                          size=(0.98, 0.32, 0.90), mesh="rc_hood", yaw=180)
for i, dx in enumerate((-0.80, 0.00, 0.80)):
    FURNITURE += F.stool(f"kt_st{i}", "kitchen", 8.85 + dx, 3.80, h=0.68)

# ── 主卧：大床 + 两个床头柜 + 长凳 ───────────────────────────────
FURNITURE += [
    _p("pb_bench", "primary_bed", "box", (-8.95, 5.90, 0.23), (1.50, 0.42, 0.46), _OAK),
]
# ⭐ 主卧大床换成 Objaverse @elba 的软包床（CC-BY，逐件核过许可）
# ⛔ yaw=180 不能省：这张网格自带的朝向是**床头朝 +y**，不转的话床头板落在 y=5.44（北），
#    而两个床头柜在 y=3.55（南）——床头柜就摆到床尾去了，pb_bench 这只床尾凳也变成
#    「贴在床头后 25 cm 的怪盒子」。2026-08-08 Jeff 实地走进去才发现，
#    因为**自检里没有任何一项管家具的朝向**（只管位置、碰撞、通行）。
#    转正之后躺床上朝北看落地窗与中央公园，观景公寓本来就该这么摆。
FURNITURE += F.mesh_piece("pb_bed", "primary_bed", -8.95, 4.40, yaw=180,
                          size=(1.74, 2.10, 0.82), mesh="bed")
# ⭐ 床头柜（@elba Tumb Astrid，CC-BY）2026-08-07 复活。
#    ⚠️ 它当年被撤的理由（"5 个材质组的残差互相叠加，收到 0.78 仍有一组探出"）是**假的**：
#    真因是摆位时给每个部件又加了一份它自己的重心（MuJoCo 早已补偿过），
#    于是 5 组各往外飞自己的重心那么远。修完之后它一点都不用收。
#    盒子按网格真实跨度 0.500 × 0.516 × 0.721 写。
FURNITURE += F.mesh_piece("pb_nsL", "primary_bed", -10.40, 3.55,
                          size=(0.50, 0.52, 0.72), mesh="nightstand")
FURNITURE += F.mesh_piece("pb_nsR", "primary_bed", -7.50, 3.55,
                          size=(0.50, 0.52, 0.72), mesh="nightstand")
FURNITURE += F.table_lamp("pb_lampL", "primary_bed", -10.40, 3.55, 0.72, shade_d=0.30)
FURNITURE += F.table_lamp("pb_lampR", "primary_bed", -7.50, 3.55, 0.72, shade_d=0.30)

# ── 主卫：独立浴缸摆在西窗前 + 双台盆 ─────────────────────────────
FURNITURE += [
    _p("sb_tub", "suite_bath", "box", (-10.30, -3.20, 0.30), (0.85, 1.80, 0.60), (0.96, 0.96, 0.95, 1.0)),
    _p("sb_tub_inner", "suite_bath", "box", (-10.30, -3.20, 0.46), (0.65, 1.58, 0.32), (0.88, 0.91, 0.92, 1.0)),
    _p("sb_vanity", "suite_bath", "box", (-8.20, -7.00, 0.42), (2.60, 0.58, 0.84), _STONE, mat="mat_marble"),
    _p("sb_vanity_top", "suite_bath", "box", (-8.20, -7.00, 0.865), (2.72, 0.64, 0.05), _STONE, mat="mat_h3_marble_blk"),
    _p("sb_mirror", "suite_bath", "box", (-8.20, -7.33, 1.75), (2.40, 0.03, 1.30), (0.80, 0.86, 0.90, 1.0), mat="mat_mirror"),
    _p("sb_shower_glass", "suite_bath", "box", (-6.90, -4.60, 1.05), (0.03, 1.60, 2.10), (0.82, 0.90, 0.94, 0.14)),
    _p("sb_wc", "suite_bath", "box", (-7.05, -6.90, 0.21), (0.40, 0.62, 0.42), (0.97, 0.97, 0.96, 1.0)),
]

# ── 画廊：只放两件落地摆件，其余留白（展线要干净）────────────────────
# ⭐ 画廊绿植：真发财树网格（Poly Haven pachira_aquatica_01，CC0）。
#    ⚠️ 那个资产一个文件里装了四棵并排的树，`parts=(3, 7)` 取的是 x≈-3.06 那棵
#    （冠 + 盆，跨度 0.744 × 0.647 × 1.302 m）——尺度正好配画廊，比原来那株
#    "三个绿球拼的" `potted_plant()` 像样得多。选哪棵见 decor/manifest.py 的对照表。
#    ⚠️ y 往北挪到 1.62：门「画廊→衣帽间」在 x=X1 竖墙、y∈[-0.10, 1.10]，
#    这里必须让开门前 0.6 m 的净空区（判据是 check_door_passable）。
FURNITURE += F.mesh_piece("gl_plant1", "gallery", -5.72, 1.62,
                          size=(0.75, 0.65, 1.31), mesh="plant_b", parts=(3, 7))
# ⛔ 走廊/画廊里不放任何落地家具（Jeff 2026-08-08 定）：这条 12.6 m 的贯通轴线是全屋主动线，
#    机器人、机器狗、扫地机都要从这儿过。这里曾有一只 gl_bench 长凳，正卡在世界原点上，
#    而产物里的机器人恰恰站在原点（摆位是运行期的事，见 AGENTS.md）——两者穿模 22.7 cm。
#    ⭐ 展品柱 gl_pedestal 贴着北墙（y=1.50，墙内表面 2.13），不占通行带，留。
FURNITURE += [
    _p("gl_pedestal", "gallery", "box", (5.40, 1.50, 0.50), (0.36, 0.36, 1.00), (0.92, 0.91, 0.89, 1.0)),
]
FURNITURE += F.mesh_piece("gl_bust", "gallery", 5.40, 1.50, z=1.28,
                          size=(0.30, 0.32, 0.55), mesh="bust")

# ── 玄关：条案 + 两扇私人电梯门（当家具做，纯视觉）────────────────────
# ⭐ 玄关条案：同一件真木柜网格，贴玄关西墙（净空 x ≥ 0.54）
FURNITURE += F.mesh_piece("fy_console", "foyer", 0.80, -4.20, yaw=90,
                          size=_CREDENZA, mesh="console", rgba=_OAK)
FURNITURE += [
    _p("fy_lift_l", "foyer", "box", (ENFILADE_X - 1.15, Y0 + 0.05, 1.15), (0.90, 0.05, 2.30),
       (0.66, 0.64, 0.60, 1.0), mat="mat_steel"),
    _p("fy_lift_r", "foyer", "box", (ENFILADE_X + 1.15, Y0 + 0.05, 1.15), (0.90, 0.05, 2.30),
       (0.66, 0.64, 0.60, 1.0), mat="mat_steel"),
    # ⚠️ y 从 -4.40 北移到 -4.00（2026-08-08）：旧位置的南端在 -6.70，而 START_POS_XY 是
    #    (2.30, -6.60)——出生点整只脚都在毯子上，正好违反上面那条「⛔ 不许踩在地毯上」。
    #    注释和代码自相矛盾了整整一版，因为没有任何一项自检拿出生点和家具对过账。
    #    北移后毯边到出生点 0.30 m（G1 脚长 0.25，前脚尖离毯还有 5 cm），北端离玄关北墙
    #    内表面仍有 0.36 m，不压「玄关→画廊」的洞口。⭐ 出生点与英雄镜头一个字没改。
    _p("fy_runner", "foyer", "box", (ENFILADE_X, -4.00, 0.008), (1.10, 4.60, 0.016), (0.44, 0.40, 0.36, 1.0)),
]
FURNITURE += F.mesh_piece("fy_vase", "foyer", 0.80, -4.20, z=0.845,
                          size=(0.24, 0.24, 0.33), mesh="vase_b")
FURNITURE += F.mesh_piece("gr_vase", "great_room", 5.80, 4.60, z=0.86,
                          size=(0.20, 0.20, 0.36), mesh="vase_c", yaw=25)
# ⭐ 木碗的碰撞盒按网格自己的真实尺寸写（0.313 × 0.309 × 0.093，见 decor.lock.json）。
#    ⚠️ 这里曾经是 0.20×0.20×0.11 —— 那是为了迁就旧的缩放 bug 收窄的，
#    结果碗只有真尺寸的三分之一。盒子比例贴合网格，缩放才不会白缩。
FURNITURE += F.mesh_piece("gr_bowl", "great_room", 2.30, 5.10, z=0.55,   # 跟茶几一起 +0.20
                          size=(0.32, 0.32, 0.10), mesh="bowl")

# ── 客卧 ────────────────────────────────────────────────────────
FURNITURE += [
    _p("gb_bed", "guest_bed", "box", (-4.00, -5.30, 0.26), (1.60, 2.05, 0.52), (0.50, 0.48, 0.46, 1.0)),
    _p("gb_mattress", "guest_bed", "box", (-4.00, -5.30, 0.63), (1.52, 1.96, 0.22), (0.90, 0.89, 0.86, 1.0)),
    _p("gb_headboard", "guest_bed", "box", (-4.00, -6.35, 0.78), (1.75, 0.12, 1.00), (0.44, 0.40, 0.36, 1.0)),
    _p("gb_ns", "guest_bed", "box", (-5.15, -6.10, 0.26), (0.44, 0.40, 0.52), _OAK),
    _p("gb_wardrobe", "guest_bed", "box", (-1.95, -3.60, 1.10), (0.60, 2.20, 2.20), (0.86, 0.84, 0.80, 1.0)),
]
FURNITURE += F.table_lamp("gb_lamp", "guest_bed", -5.15, -6.10, 0.52, shade_d=0.26)

# ── 书房 ────────────────────────────────────────────────────────
FURNITURE += F.table("st_desk", "study", 8.85, -3.40, 1.80, 0.85, h=0.75)
FURNITURE += F.chair("st_chair", "study", 8.85, -4.40, yaw=90, seat_w=0.52, seat_d=0.52)
FURNITURE += [
    _p("st_shelf", "study", "box", (6.55, -3.40, 1.10), (0.36, 3.20, 2.20), (0.30, 0.27, 0.24, 1.0)),
    _p("st_armchair", "study", "box", (10.30, -6.20, 0.34), (0.86, 0.86, 0.68), (0.36, 0.34, 0.36, 1.0)),
]
FURNITURE += F.books_stack("st_books", "study", 8.85, -3.40, 0.75)

# ── 衣帽间 / 客卫 / 洗衣房 / 东过厅：功能件，简单摆到位 ──────────────
FURNITURE += [
    # ⛔ 东墙这排柜子 2026-08-07 拆成门两侧两段。原来是一只 y∈[-1.00, 2.00] 的通柜，
    #    而「画廊→衣帽间」的门开在 x=X1 竖墙、y∈[-0.10, 1.10] —— 柜子把门**整个封死**，
    #    衣帽间/主卧/主卫整个西翼从画廊走不进来，而当时 48 项自检全绿
    #    （没有任何一项拿门和家具对过账，现在有了：check_door_passable）。
    # ⚠️ 三只柜子都从墙面内缩 1 cm：原来 dr_closet_w/e 各**穿墙 12 cm**。
    #    衣帽间净空 x∈[-11.36, -6.54]、y∈[-1.06, 2.06]（rect 内缩一个 WALL_THICK）。
    _p("dr_closet_w", "dressing", "box", (-11.05, 0.50, 1.10), (0.60, 3.10, 2.20), _CLOSET),
    _p("dr_closet_en", "dressing", "box", (-6.84, 1.66, 1.10), (0.58, 0.76, 2.20), _CLOSET),
    _p("dr_closet_es", "dressing", "box", (-6.84, -0.66, 1.10), (0.58, 0.76, 2.20), _CLOSET),
    # 北墙东段补一节，把东墙让出去的储物量找回来（避开主卧门 x∈[-9.60, -8.40]）
    _p("dr_closet_n", "dressing", "box", (-7.75, 1.75, 1.10), (1.00, 0.58, 2.20), _CLOSET),
    _p("dr_island", "dressing", "box", (-9.00, 0.50, 0.44), (1.20, 0.70, 0.88), _OAK),
    _p("gt_vanity", "guest_bath", "box", (-0.60, -7.10, 0.42), (1.60, 0.52, 0.84), _STONE, mat="mat_marble_grey"),
    _p("gt_mirror", "guest_bath", "box", (-0.60, -7.36, 1.70), (1.40, 0.03, 1.10), (0.80, 0.86, 0.90, 1.0), mat="mat_mirror"),
    _p("gt_wc", "guest_bath", "box", (-1.30, -2.20, 0.21), (0.40, 0.62, 0.42), (0.97, 0.97, 0.96, 1.0)),
    _p("ld_washer", "laundry", "box", (4.75, -7.05, 0.44), (0.62, 0.64, 0.88), (0.82, 0.82, 0.83, 1.0), mat="mat_steel"),
    _p("ld_dryer", "laundry", "box", (5.50, -7.05, 0.44), (0.62, 0.64, 0.88), (0.82, 0.82, 0.83, 1.0), mat="mat_steel"),
    _p("ld_counter", "laundry", "box", (5.15, -7.05, 0.90), (1.70, 0.66, 0.05), _STONE),
]  # ⛔ east_hall 是厨房↔书房的过厅，同样不放落地家具（原有的 eh_bench 已删）

# ---------------------------------------------------------------- 房间查询
_ORDER = list(ROOMS.keys())


def room_at(x: float, y: float, z: float | None = None) -> str | None:
    """(x, y) 落在哪间屋。单层场景忽略 z，但保留三参数签名——
    walkthrough 和世界服务先试三参数、失败才退回两参数。"""
    for key in _ORDER:
        x0, y0, x1, y1 = ROOMS[key]["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return key
    return None


def room_label(key: str | None) -> str:
    return ROOMS[key]["label"] if key in ROOMS else "屋外"
