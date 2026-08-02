"""house2 —— 三层小楼，带两组可通行楼梯。

**为什么建它**：house1 是单层大平层，没有任何高差。人形机器人的爬楼能力、跨层导航、
以及"摔在楼梯上"这类真实失败模式，在那里一个都测不到。这个场景就是为高差建的。

**和 house1 的关系**：同一套数据模型、同一个生成器。多出来的只有三样——
每间屋写 `"floor": n`、楼层高度由 `FLOOR_Z(n)` 给、外加 `STAIRS` 与 `LANDINGS`。
单层场景没有这三样，生成器里的 `_zbase()` 就恒返回 0，所以 house1 的产物逐字节不变。

⭐ **楼梯尺寸是这个场景最重要的参数，别随手改**：
- `STEP_RUN = 0.30 m`。宇树 G1 的脚长约 0.25 m，前作那栋两层小楼用 0.26 m 踏面，
  等于脚踩上去只剩 1 cm 余量——盲走策略稍有落点偏差就踩空。0.30 留出真余量。
  参考：国内住宅规范踏面常见 0.26–0.30 m，取上限对机器人友好且仍然真实。
- `STEP_RISE = 0.16 m`。规范常见 0.15–0.175 m；取偏低值，因为爬升本身不是要考的难点，
  能不能稳定落脚才是。
- 每级单独给摩擦系数 `STEP_FRICTION`，**这是有意留的旋钮**：上楼滑不滑是想扫的变量，
  继承 MuJoCo 默认值就没法扫了。

⛔ **踏步是实心砌上来的，不是悬空板**。悬空板下面的空洞会让摔倒的机器人卡进去，
调试时看到的是"机器人陷进楼梯里"这种莫名其妙的现象。
"""
from __future__ import annotations

import furniture as F  # noqa: E402  家具零件库住仓根，所有场景共用

# ────────────────────────────────────────────────────────── 尺度
# ⭐ 层高是从楼梯反推出来的，不是拍的。见下面「层高怎么来的」那一段——
#    先定台阶，再定层高，这样"楼梯正好走完一层"是结构性的，不是靠人记得对齐。
WALL_THICK = 0.14
DOOR_HEIGHT = 2.10
FLOOR_THICK = 0.05
CEILING_THICK = 0.10
CEILING_GROUP = 1      # ⚠️ 必须用默认可见的组（MuJoCo 默认不渲染 group 3）
CEILING_RGBA = (0.95, 0.95, 0.93, 1.0)

WINDOW_SILL_H = 0.95
WINDOW_TOP_H = 2.30
FLOOR_WINDOW_SILL = 0.06

N_FLOORS = 3

# ────────────────────────────────────────────────────────── 楼梯参数
STEP_RISE = 0.175      # 规范常见 0.15–0.175，取上限——见下面「台阶数怎么定的」
STEP_RUN = 0.30        # 见文件头：G1 脚长 ~0.25 m，必须留真余量
STEP_WIDTH = 1.20      # 单跑净宽
STEP_FRICTION = 1.0    # ⭐ 有意留的旋钮：上楼滑不滑是想扫的变量
STEP_RGBA = (0.72, 0.63, 0.50, 1.0)
STEP_MAT = "mat_wood_light"
RAIL_HEIGHT = 0.95     # 扶手高出踏面中线
RAIL_THICK = 0.06
RAIL_RGBA = (0.35, 0.26, 0.18, 1.0)

STEPS_PER_FLIGHT = 8   # U 型双跑，一层 = 2 跑

# ── 台阶数怎么定的（⛔ 不是随手取的）─────────────────────────────────
# 受两头夹：一跑的水平长度 + 休息平台进深必须塞进楼梯井净空，
# 同时层高（= 2 跑爬升）还得是能住人的高度。
#   9 级 × 0.30 = 2.70 m 跑长 → 加平台后超出净空 3.62 m，塞不下；
#   8 级 × 0.30 = 2.40 m 跑长 → 净空还剩 1.22 m 给平台，够人形转身；
#   层高 = 16 × 0.175 = 2.80 m，净高 2.65 m，正常住宅尺度。
# 第一版取 9 级 × 0.165，跑长塞不下净空，第一级直接埋进墙里。

# ── 层高怎么来的（⛔ 别倒过来先定层高再配楼梯）─────────────────────────
# 一层的总厚度 **等于** 一组楼梯爬的高度。先定台阶尺寸、再算层高，
# 这样"楼梯顶正好落在上一层地面"是算出来的，不是靠人记得两处对齐。
#
# 前作那栋两层小楼正是栽在反过来做：层高与楼梯各自定死，顶步悬空 20 cm，
# 直到滚球验证才发现。这里把它变成结构性约束，check_scene.py 还会再验一次。
STOREY_H = 2 * STEPS_PER_FLIGHT * STEP_RISE            # = 18 × 0.165 = 2.97 m
WALL_HEIGHT = STOREY_H - CEILING_THICK - FLOOR_THICK   # 净高 = 2.82 m


def FLOOR_Z(floor: int) -> float:
    """第 n 层地面的世界高度（0 层 = 0.0）。生成器按这个把每层抬上去。"""
    return floor * STOREY_H

# 楼梯井：东北角。两跑并排（各 1.2 宽）+ 北端休息平台。
# ⚠️ 尺寸要按**净空**算，不是按房间矩形：墙是往房间内侧砌的（厚 WALL_THICK，
#    中心线压在矩形边上），所以可用范围每边缩进半个墙厚。第一版直接拿矩形边当
#    楼梯起点，结果第一级踏步有一半埋在墙里——射线自检打到 stair_f1_wn0 才发现。
STAIR_X0, STAIR_X1 = 2.6, 6.0
STAIR_Y0, STAIR_Y1 = 0.6, 4.5

# ────────────────────────────────────────────────────────── 房间
# rect = (x0, y0, x1, y1)；floor = 楼层（0 底层）。楼梯井每层各占一间，
# 上面两层的楼梯井**不铺地板**（no_floor），否则楼梯顶到天花板上撞死。
ROOMS: dict[str, dict] = {
    # ═══ 0 层：门厅 / 客厅 / 厨房 ═══
    "entry": {
        "rect": (-6.0, -4.5, -1.5, 0.6), "label": "门厅", "floor": 0,
        "wall_rgba": (0.88, 0.86, 0.82, 1.0), "floor_rgba": (0.72, 0.70, 0.68, 1.0),
        "floor_mat": "mat_marble_grey", "wall_mat": "mat_wall",
    },
    "living_room": {
        "rect": (-6.0, 0.6, 2.6, 4.5), "label": "客厅", "floor": 0,
        "wall_rgba": (0.90, 0.88, 0.84, 1.0), "floor_rgba": (0.74, 0.62, 0.48, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "kitchen": {
        "rect": (-1.5, -4.5, 6.0, 0.6), "label": "厨房", "floor": 0,
        "wall_rgba": (0.86, 0.88, 0.87, 1.0), "floor_rgba": (0.76, 0.78, 0.80, 1.0),
        "floor_mat": "mat_tile", "wall_mat": "mat_tile",
    },
    "stair_f0": {
        "rect": (STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "label": "楼梯间", "floor": 0,
        "wall_rgba": (0.84, 0.82, 0.79, 1.0), "floor_rgba": (0.70, 0.62, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
        "no_ceiling": True,   # ⛔ 梯井竖着通，封了顶就从上面堵死
    },
    # ═══ 1 层：主卧 / 书房 / 卫生间 ═══
    "bedroom": {
        "rect": (-6.0, 0.6, 2.6, 4.5), "label": "主卧", "floor": 1,
        "wall_rgba": (0.88, 0.84, 0.80, 1.0), "floor_rgba": (0.72, 0.60, 0.46, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "study": {
        "rect": (-6.0, -4.5, -1.5, 0.6), "label": "书房", "floor": 1,
        "wall_rgba": (0.84, 0.86, 0.88, 1.0), "floor_rgba": (0.70, 0.58, 0.44, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "bathroom": {
        "rect": (-1.5, -4.5, 6.0, 0.6), "label": "卫生间", "floor": 1,
        "wall_rgba": (0.86, 0.89, 0.90, 1.0), "floor_rgba": (0.78, 0.80, 0.82, 1.0),
        "floor_mat": "mat_tile", "wall_mat": "mat_tile",
    },
    "stair_f1": {
        "rect": (STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "label": "二层楼梯间", "floor": 1,
        "wall_rgba": (0.84, 0.82, 0.79, 1.0), "floor_rgba": (0.70, 0.62, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
        # ⛔ 梯井竖着通：不铺地（下面的楼梯要上来）、不封顶（自己的楼梯要上去）。
        # 两个键成对，少一个就从一头被堵死，而且从截图上完全看不出来。
        "no_floor": True,
        "no_ceiling": True,
    },
    # ═══ 2 层：阁楼工作间 / 储藏 ═══
    "studio": {
        "rect": (-6.0, 0.6, 2.6, 4.5), "label": "阁楼工作间", "floor": 2,
        "wall_rgba": (0.90, 0.89, 0.86, 1.0), "floor_rgba": (0.71, 0.59, 0.45, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "storage": {
        "rect": (-6.0, -4.5, 6.0, 0.6), "label": "储藏间", "floor": 2,
        "wall_rgba": (0.82, 0.81, 0.78, 1.0), "floor_rgba": (0.68, 0.66, 0.63, 1.0),
        "floor_mat": "mat_tile_grey", "wall_mat": "mat_wall",
    },
    "stair_f2": {
        "rect": (STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "label": "三层楼梯间", "floor": 2,
        "wall_rgba": (0.84, 0.82, 0.79, 1.0), "floor_rgba": (0.70, 0.62, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
        "no_floor": True,
    },
}

# ────────────────────────────────────────────────────────── 门 / 通道
# orient: "h" = 沿 x 的水平墙（coord 是 y）；"v" = 沿 y 的竖直墙（coord 是 x）。
# kind "open" = 整段拆除的宽通道，不画门框门楣。
# ⚠️ 门宽下限：G1 站立宽度约 0.5 m，走动时手臂摆动更宽；这里一律 ≥1.0 m，
#    自检脚本 check_scene.py 会按机器人宽度复核。
DOORS: list[dict] = [
    # 0 层
    {"orient": "v", "coord": -1.5, "center": -2.0, "width": 1.30, "note": "门厅-厨房"},
    {"orient": "h", "coord": 0.6, "center": -3.5, "width": 1.60, "kind": "open", "note": "门厅-客厅"},
    {"orient": "h", "coord": 0.6, "center": 4.3, "width": 1.40, "kind": "open", "note": "厨房-楼梯间"},
    {"orient": "v", "coord": 2.6, "center": 2.5, "width": 1.20, "note": "客厅-楼梯间"},
    # 1 层
    {"orient": "v", "coord": -1.5, "center": -2.0, "width": 1.30, "note": "书房-卫生间"},
    {"orient": "h", "coord": 0.6, "center": -3.5, "width": 1.60, "kind": "open", "note": "书房-主卧"},
    {"orient": "h", "coord": 0.6, "center": 4.3, "width": 1.40, "kind": "open", "note": "卫生间-楼梯间"},
    {"orient": "v", "coord": 2.6, "center": 2.5, "width": 1.20, "note": "主卧-楼梯间"},
    # 2 层
    {"orient": "h", "coord": 0.6, "center": -3.5, "width": 1.60, "kind": "open", "note": "储藏-工作间"},
    {"orient": "h", "coord": 0.6, "center": 4.3, "width": 1.40, "kind": "open", "note": "储藏-楼梯间"},
    {"orient": "v", "coord": 2.6, "center": 2.5, "width": 1.20, "note": "工作间-楼梯间"},
]

# 门框 / 窗框 / 画框（纯视觉，让洞口看起来是"一扇门"而不是墙上一个豁口）
DOOR_FRAME_THICK = 0.10
DOOR_FRAME_RGBA = (0.40, 0.29, 0.20, 1.0)
WINDOW_FRAME_T = 0.08
WINDOW_FRAME_RGBA = (0.93, 0.93, 0.91, 1.0)
ART_FRAME_T = 0.06
ART_FRAME_RGBA = (0.22, 0.18, 0.15, 1.0)

# 入户门（视觉件）：门厅西外墙上。机器人在屋里活动、不出门。
FRONT_DOOR = {"pos": (-6.04, -3.4, 1.05), "size": (0.08, 1.20, 2.10),
              "rgba": (0.38, 0.27, 0.18, 1.0)}
FRONT_DOOR_HANDLE = {"pos": (-5.97, -2.95, 1.00), "size": (0.06, 0.06, 0.24),
                     "rgba": (0.72, 0.70, 0.66, 1.0)}

# ────────────────────────────────────────────────────────── 窗
WINDOWS: list[dict] = [
    {"room": "living_room", "side": "n", "center": -2.0, "width": 3.0, "sill": FLOOR_WINDOW_SILL},
    {"room": "living_room", "side": "w", "center": 2.5, "width": 1.8},
    {"room": "kitchen", "side": "s", "center": 2.0, "width": 2.2},
    {"room": "entry", "side": "w", "center": -2.0, "width": 1.2},
    {"room": "bedroom", "side": "n", "center": -2.0, "width": 3.0, "sill": FLOOR_WINDOW_SILL},
    {"room": "study", "side": "w", "center": -2.0, "width": 1.6},
    {"room": "bathroom", "side": "s", "center": 2.0, "width": 1.4},
    {"room": "studio", "side": "n", "center": -2.0, "width": 3.4, "sill": FLOOR_WINDOW_SILL},
    {"room": "storage", "side": "s", "center": 0.0, "width": 1.6},
    # 楼梯井三层各开一扇，上楼时窗外掠过景色，也让人一眼看出自己在第几层
    {"room": "stair_f0", "side": "e", "center": 2.5, "width": 1.2},
    {"room": "stair_f1", "side": "e", "center": 2.5, "width": 1.2},
    {"room": "stair_f2", "side": "e", "center": 2.5, "width": 1.2},
]

# ────────────────────────────────────────────────────────── 出生点
# 门厅中间，朝东（+x，面向厨房与楼梯方向）。
START_POS_XY = (-3.8, -2.0)
START_YAW = 0.0

# ────────────────────────────────────────────────────────── 楼梯
# U 型双跑：上行跑（西侧，沿 +y）→ 休息平台（北端）→ 回头跑（东侧，沿 -y）。
# start_xy = 第一级踏面前缘中心的地面投影；dir = 水平前进方向。
_FLIGHT_LEN = STEPS_PER_FLIGHT * STEP_RUN            # 2.70 m
_HALF_RISE = STEPS_PER_FLIGHT * STEP_RISE            # 1.485 m = 半层

# 净空（扣掉四面墙各半个厚度）
# ⚠️ 内缩**整个**墙厚，不是半个：生成器把墙心放在矩形边内侧 t/2 处，
#    所以墙体占据 [边, 边±t] 一整条，净空从 边±t 开始。
#    第一版按半个墙厚算，第一级踏步有一半埋在墙里（射线打到 stair_f1_wn0 才发现）。
_IN_X0, _IN_X1 = STAIR_X0 + WALL_THICK, STAIR_X1 - WALL_THICK   # 2.74 … 5.86
_IN_Y0, _IN_Y1 = STAIR_Y0 + WALL_THICK, STAIR_Y1 - WALL_THICK   # 0.74 … 4.36

_UP_X = _IN_X0 + STEP_WIDTH / 2.0                    # 上行跑中心线，贴西墙内表面
_DOWN_X = _IN_X1 - STEP_WIDTH / 2.0                  # 回头跑中心线，贴东墙内表面
_LANDING_Y0 = _IN_Y0 + _FLIGHT_LEN                   # 上行跑结束处
_LANDING_DEPTH = _IN_Y1 - _LANDING_Y0                # 休息平台进深

# 硬约束：平台至少要够人形转身。不够就是尺寸设计错了，宁可启动即失败，
# 也别生成一个"看着有楼梯、实际转不了身"的场景。
assert _LANDING_DEPTH >= 1.0, (
    f"休息平台进深只有 {_LANDING_DEPTH:.2f} m，人形转不开身；"
    f"把楼梯井的 y 跨度（现在 {STAIR_Y1 - STAIR_Y0:.2f} m）加大")
assert _IN_X1 - _IN_X0 >= 2 * STEP_WIDTH, (
    f"楼梯井净宽 {_IN_X1 - _IN_X0:.2f} m 放不下两跑各 {STEP_WIDTH} m")

STAIRS: list[dict] = []
LANDINGS: list[dict] = []
for _f in range(N_FLOORS - 1):                        # 0→1、1→2 各一组
    _base = FLOOR_Z(_f)
    STAIRS.append({
        "name": f"stair{_f}_up", "steps": STEPS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_UP_X, _IN_Y0), "dir": (0.0, 1.0), "base_z": _base,
        # 上行跑靠西墙（x=STAIR_X0），敞开侧在东边 → 扶手在 +x 侧
        "rail_side": +1,
    })
    STAIRS.append({
        "name": f"stair{_f}_dn", "steps": STEPS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_DOWN_X, _IN_Y1), "dir": (0.0, -1.0), "base_z": _base + _HALF_RISE,
        # 回头跑靠东墙（x=STAIR_X1），敞开侧在西边 → 扶手在 -x 侧。
        # ⚠️ rail_side 是**世界坐标**的符号，与前进方向无关（生成器直接按 x/y 轴偏移）。
        # 第一版按"前进方向翻转"推成 +1，结果扶手又贴到东墙上；靠打印坐标才发现。
        "rail_side": -1,
    })
    # 休息平台：连起两跑的顶。⛔ 少了它上行跑顶端就是悬空一级，
    #    前作那栋楼正是栽在这里（顶步悬空 20 cm，滚球验证时才发现）。
    LANDINGS.append({
        "name": f"stair{_f}_landing",
        "pos": (_UP_X / 2.0 + _DOWN_X / 2.0, _LANDING_Y0 + _LANDING_DEPTH / 2.0,
                _base + _HALF_RISE - 0.05),
        "size": (_DOWN_X - _UP_X + STEP_WIDTH, _LANDING_DEPTH, 0.10),
    })

# ────────────────────────────────────────────────────────── 家具
# ⚠️ z 写的是**该楼层内的高度**（桌面 0.75 就是 0.75），生成器加楼层基面。
# 大件（沙发/床/柜/灶台）是这个户型自己的形状，写成原始 dict；
# 小件（桌椅/灯/绿植）走 furniture.py 的零件库，那是所有场景共用的。
_WOOD = (0.55, 0.42, 0.30, 1.0)
_FABRIC = (0.62, 0.58, 0.52, 1.0)
_WHITE = (0.90, 0.90, 0.88, 1.0)

FURNITURE: list[dict] = [
    # ── 0 层 · 客厅：转角沙发 + 电视柜 ──
    {"name": "h2_sofa_seat", "room": "living_room", "type": "box",
     "pos": (-4.6, 2.4, 0.22), "size": (0.95, 2.40, 0.44), "rgba": _FABRIC, "mat": "mat_fabric"},
    {"name": "h2_sofa_back", "room": "living_room", "type": "box",
     "pos": (-5.2, 2.4, 0.55), "size": (0.25, 2.40, 0.66), "rgba": _FABRIC, "mat": "mat_fabric"},
    {"name": "h2_tv_console", "room": "living_room", "type": "box",
     "pos": (1.9, 2.4, 0.26), "size": (0.42, 2.20, 0.52), "rgba": _WOOD},
    {"name": "h2_tv_screen", "room": "living_room", "type": "box",
     "pos": (2.35, 2.4, 1.25), "size": (0.06, 1.60, 0.92), "rgba": (0.05, 0.05, 0.07, 1),
     "mat": "mat_screen"},
    # ── 0 层 · 厨房：灶台 + 吊柜 ──
    {"name": "h2_counter", "room": "kitchen", "type": "box",
     "pos": (0.2, -4.1, 0.45), "size": (2.80, 0.62, 0.90), "rgba": _WHITE, "mat": "mat_marble_grey"},
    {"name": "h2_upper_cab", "room": "kitchen", "type": "box",
     "pos": (0.2, -4.2, 1.75), "size": (2.80, 0.36, 0.70), "rgba": _WHITE},
    # ── 0 层 · 门厅：鞋柜 ──
    {"name": "h2_shoe_cab", "room": "entry", "type": "box",
     "pos": (-5.6, -1.2, 0.55), "size": (0.38, 1.60, 1.10), "rgba": _WOOD},
    # ── 1 层 · 主卧：床 + 衣柜 ──
    {"name": "h2_bed", "room": "bedroom", "type": "box",
     "pos": (-4.2, 2.6, 0.28), "size": (2.05, 1.85, 0.56), "rgba": (0.78, 0.74, 0.68, 1),
     "mat": "mat_fabric"},
    {"name": "h2_bed_head", "room": "bedroom", "type": "box",
     "pos": (-5.4, 2.6, 0.62), "size": (0.14, 1.95, 1.10), "rgba": _WOOD},
    {"name": "h2_wardrobe", "room": "bedroom", "type": "box",
     "pos": (1.9, 3.2, 1.10), "size": (0.58, 2.00, 2.20), "rgba": _WOOD},
    # ── 1 层 · 卫生间：台盆 + 浴缸 ──
    {"name": "h2_vanity", "room": "bathroom", "type": "box",
     "pos": (0.0, -4.1, 0.42), "size": (1.60, 0.55, 0.84), "rgba": _WHITE, "mat": "mat_marble_grey"},
    {"name": "h2_tub", "room": "bathroom", "type": "box",
     "pos": (4.4, -3.6, 0.28), "size": (1.70, 0.80, 0.56), "rgba": _WHITE},
    # ── 2 层 · 储藏：两排货架 ──
    {"name": "h2_rack_a", "room": "storage", "type": "box",
     "pos": (-4.6, -3.9, 0.95), "size": (2.40, 0.50, 1.90), "rgba": (0.58, 0.56, 0.53, 1)},
    {"name": "h2_rack_b", "room": "storage", "type": "box",
     "pos": (3.4, -3.9, 0.95), "size": (2.40, 0.50, 1.90), "rgba": (0.58, 0.56, 0.53, 1)},
]

FURNITURE += (
    # 0 层：餐桌四椅 + 客厅茶几与落地灯
    F.table("h2_dining", "kitchen", 3.2, -2.2, 1.40, 0.90, h=0.75)
    + F.chair("h2_dc_n1", "kitchen", 2.75, -1.45, yaw=-90)
    + F.chair("h2_dc_n2", "kitchen", 3.65, -1.45, yaw=-90)
    + F.chair("h2_dc_s1", "kitchen", 2.75, -2.95, yaw=90)
    + F.chair("h2_dc_s2", "kitchen", 3.65, -2.95, yaw=90)
    + F.round_table("h2_coffee", "living_room", -3.0, 2.4, dia=1.05, h=0.40)
    + F.floor_lamp("h2_flamp", "living_room", -5.4, 4.0)
    + F.potted_plant("h2_plant_lr", "living_room", 1.9, 4.0)
    # 1 层：书房桌椅
    + F.table("h2_desk", "study", -4.4, -2.4, 1.40, 0.70, h=0.75)
    + F.chair("h2_desk_chair", "study", -4.4, -1.60, yaw=180)
    + F.table_lamp("h2_dlamp", "study", -4.9, -2.55, 0.78)
    + F.books_stack("h2_books", "study", -3.95, -2.30, 0.78)
    # 2 层：工作间长桌 + 绿植。
    # ⛔ 楼梯间不摆任何家具：那间屋的地面就是楼梯本身，摆上去就是路障。
    #    第一版在 stair_f0 放了盆栽，射线自检直接打到叶子（落差 +0.80 m）。
    + F.table("h2_studio_desk", "studio", -4.0, 2.4, 2.00, 0.80, h=0.75)
    + F.chair("h2_studio_chair", "studio", -4.0, 1.55, yaw=180)
    + F.potted_plant("h2_plant_st", "studio", 1.9, 1.4)
)

WALL_ARTS: list[dict] = []

# ────────────────────────────────────────────────────────── 屋外
CITY_BACKDROP = {"dist": 46.0, "width": 130.0, "height": 34.0, "z": 12.0}
OUTDOOR_GROUND = {"size": (120.0, 120.0, 0.10), "pos": (0.0, 0.0, -0.06),
                  "rgba": (0.36, 0.46, 0.30, 1.0)}
TRUNK_RGBA = (0.36, 0.25, 0.16, 1.0)
FOLIAGE_RGBA = (0.24, 0.45, 0.22, 1.0)
TREES: list[tuple[float, float, float, float]] = [
    (-11.0, 7.0, 3.4, 1.9), (-4.0, 9.5, 4.0, 2.2), (4.0, 9.0, 3.2, 1.8),
    (11.0, 5.0, 3.8, 2.1), (11.5, -6.0, 3.0, 1.7), (-11.5, -6.5, 3.6, 2.0),
]
# (x, y, 宽sx, 深sy, 高h, rgba) —— 与 house1 同一个元组格式，生成器按 6 项解包
BUILDINGS: list[tuple] = [
    (-34.0, 40.0, 10.0, 10.0, 26.0, (0.55, 0.57, 0.60, 1.0)),
    (-10.0, 46.0, 14.0, 12.0, 32.0, (0.50, 0.52, 0.56, 1.0)),
    (18.0, 42.0, 12.0, 11.0, 24.0, (0.58, 0.60, 0.62, 1.0)),
    (40.0, 38.0, 11.0, 13.0, 30.0, (0.52, 0.54, 0.58, 1.0)),
]

# ────────────────────────────────────────────────────────── 房间归属判定
_FLOOR_EPS = 0.30   # 站在楼梯上时，用脚下略微下探的容差判楼层


def floor_at(z: float) -> int:
    """世界高度 z 落在第几层。楼梯中途按**已经踏上的那一层**算。"""
    n = int((z + _FLOOR_EPS) // STOREY_H)
    return max(0, min(N_FLOORS - 1, n))


def room_at(x: float, y: float, z: float | None = None) -> str | None:
    """(x, y[, z]) 在哪间屋。

    ⚠️ 多层场景**必须给 z**：三层的平面轮廓是重叠的，只给 (x, y) 无法区分
    "一层客厅"和"三层工作间"。不给 z 时按 0 层算，并且这是个有意的保守默认——
    宁可答错成底层，也不猜。
    """
    floor = 0 if z is None else floor_at(z)
    for key, room in ROOMS.items():
        if room.get("floor", 0) != floor:
            continue
        x0, y0, x1, y1 = room["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return key
    return None


def room_label(key: str | None) -> str:
    if key is None:
        return "屋外"
    return ROOMS[key]["label"]
