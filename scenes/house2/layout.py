"""house2 —— 三层小楼，带两组真正能走的双跑楼梯。

**为什么建它**：house1 是单层大平层，没有任何高差。人形机器人的爬楼能力、跨层导航、
以及"摔在楼梯上"这类真实失败模式，在那里一个都测不到。这个场景就是为高差建的。

**和 house1 的关系**：同一套数据模型、同一个生成器。多出来的只有几样——
每间屋写 `"floor": n`、楼层高度由 `FLOOR_Z(n)` 给、外加 `STAIRS` / `LANDINGS` /
`WELL_WALLS` / `GUARDS`。单层场景没有这些，生成器里的 `_zbase()` 就恒返回 0，
所以 house1 的产物逐字节不变。

⭐⭐ **楼梯的结构是这个文件最要紧的东西，改之前先读 `楼梯设计.md`。**
   那份文档记着这套尺寸是怎么推出来的、依据哪条规范、以及两次做错的经过。
   下面只写结论。

════════════════════════════════════════════════════════════════════════
一部双跑（U 型 / 半转）楼梯 = 五段，**其中两段是平台**
════════════════════════════════════════════════════════════════════════

    北 ↑            ┌─────────────────────────┐
                    │   ③ 中间休息平台 (半层高) │  ← 在这儿转 180°
                    ├────────────┬────────────┤
                    │ ② 上行跑 ↑ │ ④ 回头跑 ↑ │  ← 中间一道梯井隔墙
                    │  (西侧)    │  (东侧)     │
                    ├────────────┴────────────┤
                    │   ① 楼层平台 (楼面标高)   │  ← ⑤ 也是上一层的楼层平台
                    └───────────┬─────────────┘
                                门

**两块平台缺一不可。** 少了中间平台，两跑接不上（人走到上行跑顶端就没路了）；
少了楼层平台，人爬上来脚下是空的。

**判断"接没接上"只看一条**：上一段的最后一块踏板，和下一段的起始平台，
**平面上首尾相接、高度上正好差一个踢面**。四个接头都满足，楼梯必然连续——
不是靠人记得对齐，是算出来必然如此。`check_scene.py` 的 `check_joints`
与 `check_route` 会各验一遍。

⛔ **踏步块数 = 踢面数 − 1**，因为最上面那一级就是平台本身。
   这是行业标准算法（"the total number of treads is always one less than the number
   of risers because the landing is never counted under tread"）。多做一块，
   就等于在平台边上叠了一块同高的板。

⛔ **回头跑的起点是中间平台的南边缘**，不是楼梯井的北墙根。
   曾经写成北墙根：回头跑于是从人身后一米多远起步、中段悬在上行跑头顶，
   从平台看过去就是一排凌空的板子。而当时的自检**全绿**——因为它只沿单独一跑
   往下打射线，绕着走确实摸得到一条路。查"存在一条路径"证明不了"这是一部楼梯"。
"""
from __future__ import annotations

import math

from scenes import furniture as F  # noqa: E402  家具零件库住 scenes/furniture.py，所有场景共用

# ────────────────────────────────────────────────────────── 构造尺度
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

# ══════════════════════════════════════════════════════════ 楼梯参数
# 依据《住宅设计规范》GB 50096-2011 §6.3：
#   踏步宽 ≥0.26 m、踢面 ≤0.175 m、梯段净宽 ≥1.10 m、
#   平台净宽 ≥ 梯段净宽且 ≥1.20 m、梯段净高 ≥2.20 m、扶手高 ≥0.90 m。
# 每一条 check_scene.py 都会复核，改坏了当场红。

STEP_RISE = 0.16       # 踢面。规范上限 0.175 以下；配 0.30 踏面得 2R+G = 0.62，
                       # 正落在"走着舒服"的 0.60–0.66 区间中央
STEP_RUN = 0.30        # 踏面。规范下限 0.26；宇树 G1 脚长约 0.25 m，必须留真余量
STEP_WIDTH = 1.20      # 梯段净宽。规范 ≥1.10
LANDING_DEPTH = 1.40   # 两块平台的进深。规范 ≥ 梯段净宽且 ≥1.20

RISERS_PER_FLIGHT = 9  # ⭐ 一跑的**踢面数**（不是踏板数！）。层高由它反推
TREADS_PER_FLIGHT = RISERS_PER_FLIGHT - 1   # = 8 块实体踏板，第 9 级就是平台

# ⭐ 梯段板厚。每一级是一块**厚板**，顶面就是踏面——不是从楼层地面填上来的实心块。
#    ⛔ 板厚必须 > 踢面，否则相邻两级不再重叠，踢面处会露出缝，脚会踩进去。
#    做成厚板后底面跟着坡度斜下去，头顶净空处处相等 = 层高 − 板厚。
STEP_SLAB = 0.25
STEP_FRICTION = 1.0    # ⭐ 有意留的旋钮：上楼滑不滑是想扫的变量
STEP_RGBA = (0.72, 0.63, 0.50, 1.0)
STEP_MAT = "mat_wood_light"
LANDING_THICK = 0.10   # 中间平台的板厚（它是块楼板，不是踏步）

RAIL_HEIGHT = 0.95     # 扶手高出踏面中线。规范 ≥0.90
RAIL_THICK = 0.06
RAIL_RGBA = (0.35, 0.26, 0.18, 1.0)

# 梯井隔墙：两跑之间那道墙。
# ⛔ 这里**不留空槽**。真实楼梯的梯井常留 0.1–0.2 m 的缝，但那种缝正好能卡住
#    机器人的脚（G1 脚宽约 0.10 m）；而且两条道高差最大到 1.28 m，一侧踏空就是摔。
#    做成实墙：既没有缝，又给扶手一个安装面。
WELL_WALL_THICK = 0.12
WELL_WALL_RGBA = (0.86, 0.84, 0.81, 1.0)
WELL_WALL_MAT = "mat_wall"

# ── 层高：从楼梯推出来，⛔ 别倒过来先定层高再配楼梯 ──────────────────
# 一层的总高 **等于** 一组楼梯（两跑）爬的高度。这样"楼梯顶正好落在上一层地面"
# 是算出来的，不是靠人记得两处对齐。
# 前作那栋两层小楼正是栽在反过来做：层高与楼梯各自定死，顶步悬空 20 cm。
STOREY_H = 2 * RISERS_PER_FLIGHT * STEP_RISE            # = 18 × 0.16 = 2.88 m
WALL_HEIGHT = STOREY_H - CEILING_THICK - FLOOR_THICK    # 室内净高 = 2.73 m

# 头顶净空 = 层高 − 梯段板厚。两跑各占一条道、上下层同一条道相隔正好一个层高，
# 所以净空处处相等，不会"越走越矮"。
STAIR_HEADROOM = STOREY_H - STEP_SLAB                   # = 2.63 m > 规范 2.20


def FLOOR_Z(floor: int) -> float:
    """第 n 层地面的世界高度（0 层 = 0.0）。生成器按这个把每层抬上去。"""
    return floor * STOREY_H


# ── 楼梯井净尺寸：也是推出来的 ────────────────────────────────────────
# 净宽 = 两条梯段 + 中间那道隔墙
# 净深 = 楼层平台 + 梯段水平投影 + 中间平台
#        ⚠️ 梯段水平投影是 **(踢面数−1) × 踏面**，因为最上面一级是平台
_SHAFT_W = 2 * STEP_WIDTH + WELL_WALL_THICK                  # = 2.52 m
_SHAFT_D = 2 * LANDING_DEPTH + TREADS_PER_FLIGHT * STEP_RUN  # = 2.80 + 2.40 = 5.20 m

# 楼梯井贴着房子东北角。外框 = 净尺寸 + 四面墙（墙心压在矩形边上，每边占一整个墙厚）
STAIR_X1 = 6.0                                          # 东外墙 = 房子东边界
STAIR_X0 = STAIR_X1 - (_SHAFT_W + 2 * WALL_THICK)       # = 3.20
STAIR_Y0 = 0.6                                          # 南隔墙 = 南北两条房间带的分界
STAIR_Y1 = STAIR_Y0 + _SHAFT_D + 2 * WALL_THICK         # = 6.08

# ⭐ 房子的北边界**由楼梯定**。一部合规双跑楼梯就是要 5.2 m 进深，房子得让位。
NORTH_Y = STAIR_Y1
SOUTH_Y = -4.5
WEST_X = -6.0
EAST_X = STAIR_X1

# 净空（内缩**整个**墙厚，不是半个：墙体占据 [边, 边±t] 一整条）
_IN_X0, _IN_X1 = STAIR_X0 + WALL_THICK, STAIR_X1 - WALL_THICK   # 3.34 … 5.86
_IN_Y0, _IN_Y1 = STAIR_Y0 + WALL_THICK, STAIR_Y1 - WALL_THICK   # 0.74 … 5.94

_UP_X = _IN_X0 + STEP_WIDTH / 2.0        # 上行跑中心线（西侧车道）= 3.94
_DOWN_X = _IN_X1 - STEP_WIDTH / 2.0      # 回头跑中心线（东侧车道）= 5.26
_WELL_X = (_IN_X0 + _IN_X1) / 2.0        # 梯井隔墙中心 = 4.60

# 三段 y 分界：楼层平台 → 梯段 → 中间平台
_FLOOR_LANDING_Y1 = _IN_Y0 + LANDING_DEPTH                       # 2.14
_MID_LANDING_Y0 = _FLOOR_LANDING_Y1 + TREADS_PER_FLIGHT * STEP_RUN  # 4.54

# 硬约束：算不上就启动即失败，宁可不生成，也别生成一部走不了的楼梯
assert abs((_MID_LANDING_Y0 + LANDING_DEPTH) - _IN_Y1) < 1e-9, "楼梯井进深和三段之和对不上"
assert LANDING_DEPTH >= max(STEP_WIDTH, 1.20), "平台进深小于梯段净宽或规范下限 1.20 m"
assert STEP_RISE <= 0.175 and STEP_RUN >= 0.26, "踏步尺寸超出 GB 50096 的范围"
assert STAIR_HEADROOM >= 2.20, f"梯段净高只有 {STAIR_HEADROOM:.2f} m，低于规范 2.20 m"

# 楼层平台的矩形（通宽一条南端带）。0 层不用它——那层整间屋都是实地；
# 1/2 层只铺这一块，其余留空给下面的梯段升上来。
# ⚠️ 三条边取**房间矩形**的边（不是净空边）：楼板本来就该压到墙心，和隔壁屋的楼板
#    严丝合缝地接上。第一版取净空边，于是门槛底下留了一条 0.14 m 宽的裂缝——
#    从楼上走出楼梯间那一步正好踩空。只有北边取净空里的梯段起跑线。
FLOOR_LANDING_RECT = (STAIR_X0, STAIR_Y0, STAIR_X1, _FLOOR_LANDING_Y1)

# ────────────────────────────────────────────────────────── 房间
# rect = (x0, y0, x1, y1)；floor = 楼层（0 底层）。
ROOMS: dict[str, dict] = {
    # ═══ 0 层：门厅 / 客厅 / 厨房 ═══
    "entry": {
        "rect": (WEST_X, SOUTH_Y, -1.5, STAIR_Y0), "label": "门厅", "floor": 0,
        "wall_rgba": (0.88, 0.86, 0.82, 1.0), "floor_rgba": (0.72, 0.70, 0.68, 1.0),
        "floor_mat": "mat_marble_grey", "wall_mat": "mat_wall",
    },
    "living_room": {
        "rect": (WEST_X, STAIR_Y0, STAIR_X0, NORTH_Y), "label": "客厅", "floor": 0,
        "wall_rgba": (0.90, 0.88, 0.84, 1.0), "floor_rgba": (0.74, 0.62, 0.48, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "kitchen": {
        "rect": (-1.5, SOUTH_Y, EAST_X, STAIR_Y0), "label": "厨房", "floor": 0,
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
    "study": {
        "rect": (WEST_X, SOUTH_Y, -1.5, STAIR_Y0), "label": "书房", "floor": 1,
        "wall_rgba": (0.84, 0.86, 0.88, 1.0), "floor_rgba": (0.70, 0.58, 0.44, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "bedroom": {
        "rect": (WEST_X, STAIR_Y0, STAIR_X0, NORTH_Y), "label": "主卧", "floor": 1,
        "wall_rgba": (0.88, 0.84, 0.80, 1.0), "floor_rgba": (0.72, 0.60, 0.46, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "bathroom": {
        "rect": (-1.5, SOUTH_Y, EAST_X, STAIR_Y0), "label": "卫生间", "floor": 1,
        "wall_rgba": (0.86, 0.89, 0.90, 1.0), "floor_rgba": (0.78, 0.80, 0.82, 1.0),
        "floor_mat": "mat_tile", "wall_mat": "mat_tile",
    },
    "stair_f1": {
        "rect": (STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "label": "二层楼梯间", "floor": 1,
        "wall_rgba": (0.84, 0.82, 0.79, 1.0), "floor_rgba": (0.70, 0.62, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
        # ⛔ 只铺**楼层平台**那一条带：整层不铺的话人从下面爬上来脚下是空的，
        #    当场掉回下一层；整层都铺又把下面的梯段封死。
        "no_ceiling": True,
        "floor_rects": [FLOOR_LANDING_RECT],
    },
    # ═══ 2 层：阁楼工作间 / 储藏 ═══
    "storage": {
        "rect": (WEST_X, SOUTH_Y, EAST_X, STAIR_Y0), "label": "储藏间", "floor": 2,
        "wall_rgba": (0.82, 0.81, 0.78, 1.0), "floor_rgba": (0.68, 0.66, 0.63, 1.0),
        "floor_mat": "mat_tile_grey", "wall_mat": "mat_wall",
    },
    "studio": {
        "rect": (WEST_X, STAIR_Y0, STAIR_X0, NORTH_Y), "label": "阁楼工作间", "floor": 2,
        "wall_rgba": (0.90, 0.89, 0.86, 1.0), "floor_rgba": (0.71, 0.59, 0.45, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "stair_f2": {
        "rect": (STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "label": "三层楼梯间", "floor": 2,
        "wall_rgba": (0.84, 0.82, 0.79, 1.0), "floor_rgba": (0.70, 0.62, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
        # ⭐ 顶层**要封顶**：上面没有梯段要升上去了，不封就是从屋里看见天。
        "floor_rects": [FLOOR_LANDING_RECT],
    },
}

# ────────────────────────────────────────────────────────── 门 / 通道
# orient: "h" = 沿 x 的水平墙（coord 是 y）；"v" = 沿 y 的竖直墙（coord 是 x）。
# kind "open" = 整段拆除的宽通道，不画门框门楣。
# ⚠️ 门宽下限：G1 站立宽度约 0.5 m，走动时手臂摆动更宽；一律 ≥1.0 m，
#    check_scene.py 会按机器人宽度复核。
_STAIR_DOOR_X = _WELL_X    # 楼梯间的门开在梯井中线：进门左手上行、右手下行
DOORS: list[dict] = [
    # 0 层
    {"orient": "v", "coord": -1.5, "center": -2.0, "width": 1.30, "note": "门厅-厨房"},
    {"orient": "h", "coord": STAIR_Y0, "center": -3.5, "width": 1.60, "kind": "open",
     "note": "门厅-客厅"},
    {"orient": "h", "coord": STAIR_Y0, "center": _STAIR_DOOR_X, "width": 1.20, "kind": "open",
     "note": "厨房-楼梯间（对着楼层平台）"},
    # 1 层
    {"orient": "v", "coord": -1.5, "center": -2.0, "width": 1.30, "note": "书房-卫生间"},
    {"orient": "h", "coord": STAIR_Y0, "center": -3.5, "width": 1.60, "kind": "open",
     "note": "书房-主卧"},
    {"orient": "h", "coord": STAIR_Y0, "center": _STAIR_DOOR_X, "width": 1.20, "kind": "open",
     "note": "卫生间-楼梯间（对着楼层平台）"},
    # 2 层
    {"orient": "h", "coord": STAIR_Y0, "center": -3.5, "width": 1.60, "kind": "open",
     "note": "储藏-工作间"},
    {"orient": "h", "coord": STAIR_Y0, "center": _STAIR_DOOR_X, "width": 1.20, "kind": "open",
     "note": "储藏-楼梯间（对着楼层平台）"},
]

# 门框 / 窗框 / 画框（纯视觉，让洞口看起来是"一扇门"而不是墙上一个豁口）
DOOR_FRAME_THICK = 0.10
DOOR_FRAME_RGBA = (0.40, 0.29, 0.20, 1.0)
WINDOW_FRAME_T = 0.08
WINDOW_FRAME_RGBA = (0.93, 0.93, 0.91, 1.0)
ART_FRAME_T = 0.06
ART_FRAME_RGBA = (0.22, 0.18, 0.15, 1.0)

# 入户门（视觉件）：门厅西外墙上。机器人在屋里活动、不出门。
FRONT_DOOR = {"pos": (WEST_X - 0.04, -3.4, 1.05), "size": (0.08, 1.20, 2.10),
              "rgba": (0.38, 0.27, 0.18, 1.0)}
FRONT_DOOR_HANDLE = {"pos": (WEST_X + 0.03, -2.95, 1.00), "size": (0.06, 0.06, 0.24),
                     "rgba": (0.72, 0.70, 0.66, 1.0)}

# ────────────────────────────────────────────────────────── 窗
# ⚠️ 楼梯间的窗开在**楼层平台**外侧那段东墙上（y 落在楼层平台的中线）。
#    早先开在梯段那一段，窗户正好被斜着升上去的踏步挡住，白开。
_STAIR_WINDOW_Y = _IN_Y0 + LANDING_DEPTH / 2.0
WINDOWS: list[dict] = [
    {"room": "living_room", "side": "n", "center": -2.0, "width": 3.0, "sill": FLOOR_WINDOW_SILL},
    {"room": "living_room", "side": "w", "center": 3.0, "width": 1.8},
    {"room": "kitchen", "side": "s", "center": 2.0, "width": 2.2},
    {"room": "entry", "side": "w", "center": -2.0, "width": 1.2},
    {"room": "bedroom", "side": "n", "center": -2.0, "width": 3.0, "sill": FLOOR_WINDOW_SILL},
    {"room": "study", "side": "w", "center": -2.0, "width": 1.6},
    {"room": "bathroom", "side": "s", "center": 2.0, "width": 1.4},
    {"room": "studio", "side": "n", "center": -2.0, "width": 3.4, "sill": FLOOR_WINDOW_SILL},
    {"room": "storage", "side": "s", "center": 0.0, "width": 1.6},
    # 楼梯间三层各开一扇，上楼时窗外掠过景色，也让人一眼看出自己在第几层
    {"room": "stair_f0", "side": "e", "center": _STAIR_WINDOW_Y, "width": 1.2},
    {"room": "stair_f1", "side": "e", "center": _STAIR_WINDOW_Y, "width": 1.2},
    {"room": "stair_f2", "side": "e", "center": _STAIR_WINDOW_Y, "width": 1.2},
]

# ────────────────────────────────────────────────────────── 出生点
# 门厅中间，朝东（+x，面向厨房与楼梯方向）。
START_POS_XY = (-3.8, -2.0)
START_YAW = 0.0

# ────────────────────────────────────────────────────────── 机器人停机位（「保姆间」）
# ⭐ Jeff 2026-08-08 定：那台当比例尺 / 待命的机器人得有个**自己的房间**，别杵在通行流线正中。
# ⛔ 它和 START_POS_XY 是**两个不同的量**，别合并：
#    · START_POS_XY = **任务出生点**，消费方（anima-zero 的 sim-house-nav）读它写 qpos；
#    · ROBOT_HOME_XY = **停机位**，`tools/walkthrough.py` 把静态机器人摆在这儿。
#    合并会悄悄改变消费方的行为，而那个仓这一轮一个字都不许动。
# 选二层储藏间：空地 54 ㎡，只有两排贴南墙的货架（y ∈ [-4.15, -3.65]）；
# 门直通楼层平台，stair_route(1) 的终点就在门口。
# ⚠️ 它在 **2 层**，和 0 层门厅的出生点不同层——这是有意的：0 层唯一的次要空间就是门厅本身，
#    而门厅是主流线。停机位的判据是"不挡路"，不是"和出生点同层"。
ROBOT_HOME_XY = (0.0, -2.0)
ROBOT_HOME_YAW = math.pi / 2        # 朝北面向门
ROBOT_HOME_FLOOR = 2                # ⚠️ 只有多层场景才有这一项（单层场景不写，消费方按 0 处理）

# ══════════════════════════════════════════════════════════ 楼梯本体
# 每一跑写三样：**起跑线 = 它下面那块平台的边缘**、前进方向、起始标高。
#   `risers` 是踢面数；生成器出 `risers − 1` 块踏板，第 risers 级由平台充当。
STAIRS: list[dict] = []
LANDINGS: list[dict] = []
GUARDS: list[dict] = []

_HALF_STOREY = RISERS_PER_FLIGHT * STEP_RISE     # 1.44 m = 中间平台的标高

for _f in range(N_FLOORS - 1):                   # 0→1、1→2 各一组
    _base = FLOOR_Z(_f)
    # ② 上行跑：从**楼层平台的北缘**起步，往北爬到中间平台
    STAIRS.append({
        "name": f"stair{_f}_up", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_UP_X, _FLOOR_LANDING_Y1), "dir": (0.0, 1.0), "base_z": _base,
        # 靠西墙，敞开侧在东边（对着梯井隔墙）→ 扶手装在 +x 侧
        "rail_side": +1,
    })
    # ③ 中间休息平台：通宽，北端，顶面标高 = 半层
    LANDINGS.append({
        "name": f"stair{_f}_mid",
        "pos": ((_IN_X0 + _IN_X1) / 2.0,
                (_MID_LANDING_Y0 + _IN_Y1) / 2.0,
                _base + _HALF_STOREY - LANDING_THICK / 2.0),
        "size": (_IN_X1 - _IN_X0, _IN_Y1 - _MID_LANDING_Y0, LANDING_THICK),
    })
    # ④ 回头跑：⛔ 从**中间平台的南缘**起步（不是北墙根！），往南爬到上一层
    STAIRS.append({
        "name": f"stair{_f}_dn", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_DOWN_X, _MID_LANDING_Y0), "dir": (0.0, -1.0),
        "base_z": _base + _HALF_STOREY,
        # 靠东墙，敞开侧在西边 → 扶手装在 -x 侧。
        # ⚠️ rail_side 是**世界坐标轴**的符号，与前进方向无关。
        "rail_side": -1,
    })

# 梯井隔墙：只在梯段那一段（两块平台之间）立墙，通高到顶层天花板。
# 平台段不立——那儿正是转身的地方。
WELL_WALLS: list[dict] = [{
    "name": "stair_well_wall",
    "pos": (_WELL_X, (_FLOOR_LANDING_Y1 + _MID_LANDING_Y0) / 2.0,
            (FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT) / 2.0),
    "size": (WELL_WALL_THICK, _MID_LANDING_Y0 - _FLOOR_LANDING_Y1,
             FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT),
}]

# ⭐ 顶层梯口护栏：顶层西侧车道上面没有梯段接上去了，那里是个直通下面的洞
#    （从顶层楼面到下面一跑的踏面差 2.7 m）。真实楼梯这儿一定是围栏。
#    东侧车道**不用**围——那是下楼的口，人就是从那儿下去的。
#
# ⛔ 做成**实心矮墙**（栏板），不是两根横杆。两个理由：
#    ① 机器人会从杆缝里钻过去/卡进去，栏板才是真拦得住的；
#    ② 自检只能横着打射线找实体，两根细杆要求射线高度正好对上杆心——
#       那等于把检查绑死在某一版护栏的造型上，换个造型检查就假绿。
GUARD_HEIGHT = 1.05        # 规范：临空处栏板/栏杆净高不低于 1.05 m
GUARD_THICK = WELL_WALL_THICK
GUARDS.append({
    "name": "stair_top_guard",
    "pos": (_UP_X, _FLOOR_LANDING_Y1 + GUARD_THICK / 2.0,
            FLOOR_Z(N_FLOORS - 1) + GUARD_HEIGHT / 2.0),
    "size": (STEP_WIDTH, GUARD_THICK, GUARD_HEIGHT),
})

# ── 四个接头的自检（几何一算就知道，不用等 MuJoCo）─────────────────────
# 上一段最后一块踏板的顶面，与下一段起始平台，必须差正好一个踢面。
_last_tread_top = TREADS_PER_FLIGHT * STEP_RISE
assert abs((_HALF_STOREY - _last_tread_top) - STEP_RISE) < 1e-9, \
    "上行跑顶端到中间平台不是一个踢面 —— 楼梯断了"
assert abs((STOREY_H - (_HALF_STOREY + _last_tread_top)) - STEP_RISE) < 1e-9, \
    "回头跑顶端到上一层楼面不是一个踢面 —— 楼梯断了"

# ────────────────────────────────────────────────────────── 家具
# ⚠️ z 写的是**该楼层内的高度**（桌面 0.75 就是 0.75），生成器加楼层基面。
# 大件（沙发/床/柜/灶台）是这个户型自己的形状，写成原始 dict；
# 小件（桌椅/灯/绿植）走 furniture.py 的零件库，那是所有场景共用的。
_WOOD = (0.55, 0.42, 0.30, 1.0)
_FABRIC = (0.62, 0.58, 0.52, 1.0)
_WHITE = (0.90, 0.90, 0.88, 1.0)

# 北侧那条房间带的"贴墙"参照线——家具跟着墙走，墙动了不用逐件手改
_N_ROOM_E = STAIR_X0 - WALL_THICK          # 东墙内表面 = 3.06
_N_ROOM_N = NORTH_Y - WALL_THICK           # 北墙内表面 = 5.94
_N_ROOM_MID_Y = (STAIR_Y0 + NORTH_Y) / 2.0  # 房间进深中线 = 3.34

FURNITURE: list[dict] = [
    # ── 0 层 · 客厅：转角沙发 + 电视柜 ──
    {"name": "h2_sofa_seat", "room": "living_room", "type": "box",
     "pos": (-4.6, _N_ROOM_MID_Y, 0.22), "size": (0.95, 2.40, 0.44),
     "rgba": _FABRIC, "mat": "mat_fabric"},
    {"name": "h2_sofa_back", "room": "living_room", "type": "box",
     "pos": (-5.2, _N_ROOM_MID_Y, 0.55), "size": (0.25, 2.40, 0.66),
     "rgba": _FABRIC, "mat": "mat_fabric"},
    {"name": "h2_tv_console", "room": "living_room", "type": "box",
     "pos": (_N_ROOM_E - 0.56, _N_ROOM_MID_Y, 0.26), "size": (0.42, 2.20, 0.52), "rgba": _WOOD},
    {"name": "h2_tv_screen", "room": "living_room", "type": "box",
     "pos": (_N_ROOM_E - 0.11, _N_ROOM_MID_Y, 1.25), "size": (0.06, 1.60, 0.92),
     "rgba": (0.05, 0.05, 0.07, 1), "mat": "mat_screen"},
    # ── 0 层 · 厨房：灶台 + 吊柜 ──
    {"name": "h2_counter", "room": "kitchen", "type": "box",
     "pos": (0.2, -4.1, 0.45), "size": (2.80, 0.62, 0.90), "rgba": _WHITE,
     "mat": "mat_marble_grey"},
    {"name": "h2_upper_cab", "room": "kitchen", "type": "box",
     "pos": (0.2, -4.2, 1.75), "size": (2.80, 0.36, 0.70), "rgba": _WHITE},
    # ── 0 层 · 门厅：鞋柜 ──
    {"name": "h2_shoe_cab", "room": "entry", "type": "box",
     "pos": (-5.6, -1.2, 0.55), "size": (0.38, 1.60, 1.10), "rgba": _WOOD},
    # ── 1 层 · 主卧：床 + 衣柜 ──
    {"name": "h2_bed", "room": "bedroom", "type": "box",
     "pos": (-4.2, _N_ROOM_MID_Y + 0.2, 0.28), "size": (2.05, 1.85, 0.56),
     "rgba": (0.78, 0.74, 0.68, 1), "mat": "mat_fabric"},
    {"name": "h2_bed_head", "room": "bedroom", "type": "box",
     "pos": (-5.4, _N_ROOM_MID_Y + 0.2, 0.62), "size": (0.14, 1.95, 1.10), "rgba": _WOOD},
    {"name": "h2_wardrobe", "room": "bedroom", "type": "box",
     "pos": (_N_ROOM_E - 0.34, _N_ROOM_MID_Y + 0.8, 1.10), "size": (0.58, 2.00, 2.20),
     "rgba": _WOOD},
    # ── 1 层 · 卫生间：台盆 + 浴缸 ──
    {"name": "h2_vanity", "room": "bathroom", "type": "box",
     "pos": (0.0, -4.1, 0.42), "size": (1.60, 0.55, 0.84), "rgba": _WHITE,
     "mat": "mat_marble_grey"},
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
    + F.round_table("h2_coffee", "living_room", -3.0, _N_ROOM_MID_Y, dia=1.05, h=0.40)
    + F.floor_lamp("h2_flamp", "living_room", -5.4, _N_ROOM_N - 0.6)
    + F.potted_plant("h2_plant_lr", "living_room", _N_ROOM_E - 0.5, _N_ROOM_N - 0.5)
    # 1 层：书房桌椅
    + F.table("h2_desk", "study", -4.4, -2.4, 1.40, 0.70, h=0.75)
    + F.chair("h2_desk_chair", "study", -4.4, -1.60, yaw=180)
    + F.table_lamp("h2_dlamp", "study", -4.9, -2.55, 0.78)
    + F.books_stack("h2_books", "study", -3.95, -2.30, 0.78)
    # 2 层：工作间长桌 + 绿植。
    # ⛔ 楼梯间不摆任何家具：那间屋的地面就是楼梯本身，摆上去就是路障。
    #    第一版在 stair_f0 放了盆栽，射线自检直接打到叶子（落差 +0.80 m）。
    + F.table("h2_studio_desk", "studio", -4.0, _N_ROOM_MID_Y, 2.00, 0.80, h=0.75)
    + F.chair("h2_studio_chair", "studio", -4.0, _N_ROOM_MID_Y - 0.85, yaw=180)
    + F.potted_plant("h2_plant_st", "studio", _N_ROOM_E - 0.5, STAIR_Y0 + 0.8)
)

WALL_ARTS: list[dict] = []

# ────────────────────────────────────────────────────────── 屋外
CITY_BACKDROP = {"dist": 46.0, "width": 130.0, "height": 34.0, "z": 12.0}
OUTDOOR_GROUND = {"size": (120.0, 120.0, 0.10), "pos": (0.0, 0.0, -0.06),
                  "rgba": (0.36, 0.46, 0.30, 1.0)}
TRUNK_RGBA = (0.36, 0.25, 0.16, 1.0)
FOLIAGE_RGBA = (0.24, 0.45, 0.22, 1.0)
TREES: list[tuple[float, float, float, float]] = [
    (-11.0, 8.0, 3.4, 1.9), (-4.0, 10.5, 4.0, 2.2), (4.0, 10.0, 3.2, 1.8),
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


# ────────────────────────────────────────────────────────── 楼梯路线（给自检与漫游用）
def stair_route(floor: int) -> list[tuple[float, float, float]]:
    """从第 `floor` 层走到第 `floor+1` 层的完整路线（世界坐标折线的拐点）。

    ⭐ 这是"楼梯到底连不连"的唯一权威描述：check_scene.py 沿着它逐点往下打射线，
    要求一路有实地、相邻高差不超过一个踢面。**别在别处再写一份**——
    上一版的 bug 正是"平台在一处、回头跑起点在另一处"，两处各写各的没人对得上。

    返回的每个点是 (x, y, 该点脚下应有的标高)。
    """
    base = FLOOR_Z(floor)
    return [
        # ① 楼层平台上，正对上行跑
        (_UP_X, _IN_Y0 + 0.25, base),
        # ② 上行跑起步线
        (_UP_X, _FLOOR_LANDING_Y1, base),
        # ③ 爬到中间平台的南缘（此处脚下已是平台标高）
        (_UP_X, _MID_LANDING_Y0, base + _HALF_STOREY),
        # ④ 在中间平台上横移到回头跑那条道（平台通宽，隔墙到此为止）
        (_UP_X, _IN_Y1 - 0.55, base + _HALF_STOREY),
        (_DOWN_X, _IN_Y1 - 0.55, base + _HALF_STOREY),
        # ⑤ 回到回头跑的起步线
        (_DOWN_X, _MID_LANDING_Y0, base + _HALF_STOREY),
        # ⑥ 爬到上一层的楼层平台
        (_DOWN_X, _FLOOR_LANDING_Y1, base + STOREY_H),
        # ⑦ 走到门口
        (_STAIR_DOOR_X, _IN_Y0 + 0.25, base + STOREY_H),
    ]


STAIR_SLOPE_DEG = math.degrees(math.atan2(STEP_RISE, STEP_RUN))
