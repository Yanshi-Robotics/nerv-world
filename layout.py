"""屋子布局 —— 单一真相源。

生成场景（make_house.py → house-<机器人>.xml）和世界服务判断「机器人现在在哪间屋」都读这里，
避免同一组坐标在两处各写一遍、改了一处忘另一处。

坐标系：MuJoCo 世界系，x 向东、y 向北、z 向上，单位米。

═══ 户型：照 Jeff 提供的沪上豪宅大平层户型图复刻（17 个空间，约 360 ㎡）═══

⚠️ 忠实度说明（如实登记，别当成毫米级还原）：房间**构成、相对位置、邻接关系、动线**照图复刻；
   但原图是一张 JPEG，墙线精确尺寸无法读出，**每间屋的具体尺寸是按比例估算的**，并按 Jeff 要求
   整体放大了尺度（门洞加宽），保证四足机器狗（身长 0.7m）能顺畅走动转弯。

原图编号 → 本布局房间：
  ①客厅 ②餐厅 ③西厨中岛 ④入户玄关 ⑤鞋帽间 ⑥中厨 ⑦晾晒区 ⑧洗衣
  ⑩次卧 ⑪客卫 ⑫过道1 ⑮小孩卧 ⑯小孩卫 ⑰主卧 ⑱衣帽间 ⑲过道2 ⑳主卫（带独立浴缸）

                                     北 (y+)
  ┌──────────┬─────────────┬─────────────┬──────────────────┐ y=10
  │          │             │             │                  │
  │ ⑳主 卫    │             │  ③西厨/中岛  │                  │
  │ (独立浴缸) │   ⑰主 卧     │             │                  │
  ├──────────┤             ├─────────────┤    ①客  厅        │
  │ ⑱衣帽间   │             │             │  转角沙发/圆地毯    │
  ├──────────┼─────────────┤   ②餐 厅     │   电视墙/落地窗    │
  │          │   ⑲过道2     │  长桌八椅    │                  │
  │ ⑯小孩卫   ├─────────────┼─────────────┼──────────────────┤
  │          │             │             │                  │
  ├──────────┤   ⑫过道1     │  ⑤鞋帽间     │   ④入户玄关       │◀入户门
  │          │             │             │                  │
  │ ⑮小孩卧   ├──────┬──────┼─────────────┼──────────────────┤
  │          │      │      │             │                  │
  │          │⑪客卫  │⑩次卧  │   ⑥中 厨     │    ⑧洗 衣        │
  │          │      │      ├─────────────┼──────────────────┘
  └──────────┴──────┴──────┤   ⑦晾晒区    │        ◣缺角
                            └─────────────┘  y=-10
  x=-9.5    -5.5         -0.5           4.0              9.5

⚠️ 单位约定：本文件里的尺寸一律写**全长**（人的直觉）；MJCF 的 <geom type="box" size=...>
要的是**半长**，转换只在 make_house.py 里做一次，别在这里预先除 2。
"""
from __future__ import annotations

# ---------------------------------------------------------------- 建筑尺度
WALL_HEIGHT = 3.0      # 墙高(m)，豪宅大平层层高
WALL_THICK = 0.14      # 墙厚(m)
DOOR_HEIGHT = 2.30     # 门洞净高(m)；门楣 = 门顶到墙顶那一截
FLOOR_THICK = 0.05
CEILING_THICK = 0.10

# ⛔ 有天花板 = 狗抬头看到的是屋顶，不是天空。天花板单独归组，出俯视写真时整层关掉。
CEILING_GROUP = 1      # ⚠️ 必须用默认可见的组：MuJoCo 默认不渲染 group 3（menagerie 拿它放碰撞体）
CEILING_RGBA = (0.95, 0.95, 0.93, 1.0)

WINDOW_SILL_H = 0.95
WINDOW_TOP_H = 2.35
FLOOR_WINDOW_SILL = 0.06   # 落地窗：基本贴地，只留一条压条

# ---------------------------------------------------------------- 房间矩形
# 每间屋 = (x0, y0, x1, y1)，左下角→右上角（净空范围，不含墙体本身）。
ROOMS: dict[str, dict] = {
    # ═══ 西列：主卧套间（上）+ 小孩房区（下）═══
    "master_bath": {                                           # ⑳ 主卫（独立浴缸）
        "rect": (-9.5, 4.5, -5.5, 10.0), "label": "主卫",       # 4.0 × 5.5 = 22㎡
        "wall_rgba": (0.86, 0.88, 0.86, 1.0), "floor_rgba": (0.77, 0.79, 0.81, 1.0),
        "floor_mat": "mat_marble_grey", "wall_mat": "mat_tile",
    },
    "closet": {                                                # ⑱ 衣帽间
        "rect": (-9.5, 1.0, -5.5, 4.5), "label": "衣帽间",      # 4.0 × 3.5 = 14㎡
        "wall_rgba": (0.80, 0.74, 0.66, 1.0), "floor_rgba": (0.70, 0.58, 0.44, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "kid_bedroom": {                                           # ⑮+⑯ 小孩卧并入小孩卫（套房）
        "rect": (-9.5, -10.0, -5.5, 1.0), "label": "小孩房",    # 4.0 × 11.0 = 44㎡
        "wall_rgba": (0.88, 0.78, 0.74, 1.0), "floor_rgba": (0.76, 0.64, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    # ═══ 中西列：主卧 + 两条过道 + 客卫/次卧 ═══
    "master_bedroom": {                                        # ⑰ 主卧
        "rect": (-5.5, 3.0, -0.5, 10.0), "label": "主卧",       # 5.0 × 7.0 = 35㎡
        "wall_rgba": (0.60, 0.66, 0.80, 1.0), "floor_rgba": (0.70, 0.58, 0.44, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    "corridor": {                                              # ⑫+⑲ 合并成一条主过道
        "rect": (-5.5, -6.0, -0.5, 3.0), "label": "过道",       # 5.0 × 9.0 = 45㎡
        "wall_rgba": (0.88, 0.86, 0.82, 1.0), "floor_rgba": (0.60, 0.48, 0.36, 1.0),
        "floor_mat": "mat_wood", "wall_mat": "mat_wall",
    },
    "guest_bath": {                                            # ⑪ 客卫
        "rect": (-5.5, -10.0, -3.0, -6.0), "label": "客卫",     # 2.5 × 4.0 = 10㎡
        "wall_rgba": (0.78, 0.86, 0.90, 1.0), "floor_rgba": (0.77, 0.79, 0.81, 1.0),
        "floor_mat": "mat_marble_grey", "wall_mat": "mat_tile",
    },
    "second_bedroom": {                                        # ⑩ 次卧
        "rect": (-3.0, -10.0, -0.5, -6.0), "label": "次卧",     # 2.5 × 4.0 = 10㎡
        "wall_rgba": (0.85, 0.80, 0.62, 1.0), "floor_rgba": (0.76, 0.64, 0.50, 1.0),
        "floor_mat": "mat_wood_light", "wall_mat": "mat_wall",
    },
    # ═══ 中东列：西厨 / 餐厅 / 鞋帽间 / 中厨 / 晾晒 ═══
    "dining_room": {                                           # ②+③ 餐厅与西厨中岛开放连通
        "rect": (-0.5, 0.0, 4.0, 10.0), "label": "餐厅",        # 4.5 × 10.0 = 45㎡
        "wall_rgba": (0.89, 0.85, 0.78, 1.0), "floor_rgba": (0.60, 0.45, 0.31, 1.0),
        "floor_mat": "mat_wood", "wall_mat": "mat_wall",
    },
    "chinese_kitchen": {                                       # ⑤+⑥+⑦ 中厨并入储物与晾晒
        "rect": (-0.5, -10.0, 4.0, 0.0), "label": "中厨",       # 4.5 × 10.0 = 45㎡
        "wall_rgba": (0.76, 0.86, 0.76, 1.0), "floor_rgba": (0.89, 0.84, 0.77, 1.0),
        "floor_mat": "mat_marble_warm", "wall_mat": "mat_tile",
    },
    # ═══ 东列：客厅 / 玄关 / 洗衣（东南是缺角，不建）═══
    "living_room": {                                           # ① 客厅
        "rect": (4.0, 2.0, 9.5, 10.0), "label": "客厅",         # 5.5 × 8.0 = 44㎡
        "wall_rgba": (0.89, 0.85, 0.78, 1.0), "floor_rgba": (0.60, 0.45, 0.31, 1.0),
        "floor_mat": "mat_wood", "wall_mat": "mat_wall",
    },
    "entry": {                                                 # ④ 入户玄关
        "rect": (4.0, -3.0, 9.5, 2.0), "label": "玄关",         # 5.5 × 5.0 = 27.5㎡
        "wall_rgba": (0.85, 0.80, 0.73, 1.0), "floor_rgba": (0.72, 0.70, 0.67, 1.0),
        "floor_mat": "mat_marble", "wall_mat": "mat_wall",
    },
    "laundry": {                                               # ⑧ 洗衣
        "rect": (4.0, -7.0, 9.5, -3.0), "label": "洗衣房",      # 5.5 × 4.0 = 22㎡
        "wall_rgba": (0.86, 0.88, 0.90, 1.0), "floor_rgba": (0.80, 0.80, 0.78, 1.0),
        "floor_mat": "mat_tile_grey", "wall_mat": "mat_tile",
    },
}

# ---------------------------------------------------------------- 门 / 通道
# 每项 = dict(orient h=沿x/v=沿y, coord 墙所在的另一轴坐标, center 门中心, width 净宽, note)
# ⚠️ 门洞按 Jeff 要求加宽（≥1.0m），保证四足狗顺畅通过与转弯。
DOORS: list[dict] = [
    # ── 主卧套间（⑰主卧 → ⑱衣帽间 → ⑳主卫）──
    {"orient": "v", "coord": -5.5, "center": 6.2, "width": 1.10, "note": "主卧-衣帽间（套内）"},
    {"orient": "h", "coord": 4.5, "center": -7.5, "width": 1.10, "note": "衣帽间-主卫（套内）"},
    # ── 过道2 ⑲ 串主卧与衣帽间 ──
    {"orient": "h", "coord": 3.0, "center": -3.0, "width": 1.40, "note": "过道-主卧"},
    {"orient": "v", "coord": -5.5, "center": 2.0, "width": 1.10, "note": "过道-衣帽间"},
    # ── 过道1 ⑫ 主动线，串起小孩区/客卫/次卧/鞋帽间，并与过道2 连通 ──
    {"orient": "h", "coord": 0.0, "center": -3.0, "width": 2.00, "note": "过道-过道2（宽通道）"},
    {"orient": "v", "coord": -5.5, "center": -4.2, "width": 1.10, "note": "过道-小孩卧"},
    {"orient": "h", "coord": -6.0, "center": -4.3, "width": 1.10, "note": "过道-客卫"},
    {"orient": "h", "coord": -6.0, "center": -1.8, "width": 1.10, "note": "过道-次卧"},
    {"orient": "v", "coord": -0.5, "center": -1.5, "width": 1.40, "note": "过道-鞋帽间"},
    # ── 公共区动线：玄关④ → 餐厅② / 客厅① ──
    {"orient": "v", "coord": 4.0, "center": 0.0, "width": 1.60, "note": "玄关-鞋帽间/餐厅侧"},
    {"orient": "h", "coord": 2.0, "center": 6.5, "width": 2.40, "note": "玄关-客厅（宽通道）"},
    # 客厅与餐厅之间那道墙**整段拆除**（大平层的客餐一体），不是开个门——所以 kind="open"
    {"orient": "v", "coord": 4.0, "center": 6.0, "width": 8.00, "kind": "open",
     "note": "客厅-餐厅：整面墙拆除，客餐完全打通"},
    {"orient": "h", "coord": 4.5, "center": 1.8, "width": 2.60, "note": "餐厅-西厨（开放式）"},
    # ── 服务区动线：鞋帽间⑤ → 中厨⑥ → 晾晒⑦ / 洗衣⑧ ──
    {"orient": "v", "coord": 4.0, "center": -5.0, "width": 1.10, "note": "中厨-洗衣房"},
    {"orient": "v", "coord": 4.0, "center": -1.8, "width": 1.10, "note": "玄关-洗衣房侧门"},
]

DOOR_FRAME_THICK = 0.10
DOOR_FRAME_RGBA = (0.40, 0.29, 0.20, 1.0)

# 入户门（玄关东外墙，纯视觉、不开洞——狗在屋里活动，不出门）
FRONT_DOOR = {"pos": (9.42, -0.6, 1.18), "size": (0.08, 1.40, 2.35),
              "rgba": (0.30, 0.21, 0.14, 1.0)}
FRONT_DOOR_HANDLE = {"pos": (9.35, -1.15, 1.10), "size": (0.06, 0.06, 0.26),
                     "rgba": (0.78, 0.72, 0.45, 1.0)}

# ---------------------------------------------------------------- 窗
WINDOWS: list[dict] = [
    # 客厅：两面落地窗（转角采光，对应效果图的通透感）
    {"room": "living_room", "side": "e", "center": 6.0, "width": 3.4, "sill": FLOOR_WINDOW_SILL},
    {"room": "living_room", "side": "n", "center": 6.8, "width": 3.0, "sill": FLOOR_WINDOW_SILL},
    # 西厨 / 餐厅
    {"room": "dining_room", "side": "n", "center": 1.8, "width": 2.4, "sill": FLOOR_WINDOW_SILL},
    # 主卧套间
    {"room": "master_bedroom", "side": "n", "center": -3.0, "width": 2.6, "sill": FLOOR_WINDOW_SILL},
    {"room": "master_bath", "side": "n", "center": -7.5, "width": 1.6},
    {"room": "master_bath", "side": "w", "center": 7.5, "width": 1.2},
    {"room": "closet", "side": "w", "center": 2.8, "width": 1.0},
    # 小孩区
    {"room": "kid_bedroom", "side": "w", "center": -0.8, "width": 1.0},
    {"room": "kid_bedroom", "side": "w", "center": -6.0, "width": 2.0},
    {"room": "kid_bedroom", "side": "s", "center": -7.5, "width": 1.8},
    # 次卧 / 客卫
    {"room": "second_bedroom", "side": "s", "center": -1.8, "width": 1.6},
    {"room": "guest_bath", "side": "s", "center": -4.3, "width": 0.9},
    # 服务区
    {"room": "chinese_kitchen", "side": "e", "center": -5.0, "width": 1.2},
    {"room": "chinese_kitchen", "side": "s", "center": 1.8, "width": 2.4},
    {"room": "laundry", "side": "e", "center": -5.0, "width": 1.4},
    {"room": "entry", "side": "e", "center": 1.2, "width": 1.2},
]
WINDOW_FRAME_RGBA = (0.93, 0.93, 0.91, 1.0)
WINDOW_FRAME_T = 0.08

# ---------------------------------------------------------------- 出生点
# 站在玄关、刚进门的姿态（朝西看向屋内）。厨房/卧室从这里都看不见，必须自己一间间找。
# ⚠️ 出生点必须避开地垫/地毯这类薄片家具：机器人生成时脚会嵌进去，接触力一冲就把它掀翻
#    （2026-07-25 实测：原来站在玄关地垫上，一起服务就倒立，倾角 156°）。
START_POS_XY = (7.30, -0.60)
START_YAW = 3.14159            # 朝西（-x）
# ⚠️ 出生**高度**不在这儿——那是机器人的事（四足狗 0.445 m、人形 0.80 m），
#    住在 robots/manifest.py 的 start_height。这里只管"这套房子里从哪儿开始"。

# ---------------------------------------------------------------- 家具
# 家具 = 房间的"身份标志"，ANIMA 全靠看见它们认出这是哪间屋。
# ⛔ **按真实做，不为某一种机器人定制**（Jeff 2026-07-25 校正）。早先这里写的是"识别特征必须铺在
#    狗视高 0.3–0.9m"——那是拿一台特定机器人（四足狗，相机 0.5m）的视角当设计目标，方向错了：
#    人形眼高 1.25m，为狗压低家具换成人形就得全部重做。看不见高处是**机器人侧**的局限，
#    该用环视/抬头/换机位解决，不是把抽油烟机装到膝盖上。详见仓根 README「设计原则」。
FURNITURE: list[dict] = [
    # ═══════ ①客厅：转角沙发 / 圆地毯 / 电视墙 / 落地灯 / 挂画 ═══════
    {"name": "tv_wall", "room": "living_room", "type": "box",
     "pos": (4.15, 6.6, 1.45), "size": (0.12, 4.20, 2.90), "rgba": (0.86, 0.83, 0.78, 1)},
    {"name": "tv_screen", "room": "living_room", "type": "box",
     "pos": (4.24, 6.6, 1.35), "size": (0.06, 2.20, 1.25), "rgba": (0.05, 0.05, 0.07, 1), "mat": "mat_screen"},
    {"name": "tv_console", "room": "living_room", "type": "box",
     "pos": (4.38, 6.6, 0.24), "size": (0.45, 3.00, 0.48), "rgba": (0.28, 0.21, 0.15, 1)},
    {"name": "rug", "room": "living_room", "type": "cylinder",
     "pos": (6.6, 6.3, 0.005), "size": (4.00, 4.00, 0.01), "rgba": (0.78, 0.70, 0.60, 1), "mat": "mat_carpet"},
    {"name": "sofa_seat_e", "room": "living_room", "type": "box",
     "pos": (8.55, 6.3, 0.22), "size": (1.00, 3.40, 0.44), "rgba": (0.62, 0.55, 0.46, 1), "mat": "mat_fabric"},
    {"name": "sofa_back_e", "room": "living_room", "type": "box",
     "pos": (9.02, 6.3, 0.58), "size": (0.24, 3.40, 0.72), "rgba": (0.58, 0.51, 0.42, 1), "mat": "mat_fabric"},
    {"name": "sofa_seat_s", "room": "living_room", "type": "box",
     "pos": (7.30, 4.75, 0.22), "size": (1.60, 1.00, 0.44), "rgba": (0.62, 0.55, 0.46, 1), "mat": "mat_fabric"},
    {"name": "sofa_back_s", "room": "living_room", "type": "box",
     "pos": (7.30, 4.32, 0.58), "size": (1.60, 0.24, 0.72), "rgba": (0.58, 0.51, 0.42, 1), "mat": "mat_fabric"},
    {"name": "cushion_a", "room": "living_room", "type": "box",
     "pos": (8.92, 7.2, 0.62), "size": (0.16, 0.52, 0.52), "rgba": (0.82, 0.76, 0.66, 1), "mat": "mat_fabric"},
    {"name": "cushion_b", "room": "living_room", "type": "box",
     "pos": (8.92, 5.3, 0.62), "size": (0.16, 0.52, 0.52), "rgba": (0.72, 0.62, 0.54, 1), "mat": "mat_fabric"},
    {"name": "wall_art", "room": "living_room", "type": "box",
     "pos": (4.24, 9.0, 1.80), "size": (0.06, 1.40, 1.05), "rgba": (0.90, 0.88, 0.84, 1)},
    {"name": "wall_art_ink", "room": "living_room", "type": "cylinder",
     "pos": (4.28, 9.0, 1.80), "size": (0.55, 0.55, 0.02), "rgba": (0.18, 0.18, 0.20, 1)},
    {"name": "armchair", "room": "living_room", "type": "box",
     "pos": (5.6, 3.5, 0.24), "size": (0.85, 0.85, 0.48), "rgba": (0.55, 0.48, 0.42, 1), "mat": "mat_fabric"},

    # ═══════ ②餐厅：长餐桌 + 八椅 + 餐边柜 ═══════
    {"name": "sideboard", "room": "dining_room", "type": "box",
     "pos": (-0.18, 2.2, 0.42), "size": (0.45, 2.20, 0.84), "rgba": (0.46, 0.33, 0.22, 1)},

    # ═══════ ③西厨/中岛：开放式，大理石中岛 + 吧椅 ═══════
    {"name": "island", "room": "dining_room", "type": "box",
     "pos": (1.7, 6.4, 0.45), "size": (3.00, 1.10, 0.90), "rgba": (0.88, 0.86, 0.82, 1)},
    {"name": "island_top", "room": "dining_room", "type": "box",
     "pos": (1.7, 6.4, 0.93), "size": (3.20, 1.26, 0.07), "rgba": (0.24, 0.24, 0.27, 1), "mat": "mat_marble_dark"},
    {"name": "island_panel", "room": "dining_room", "type": "box",
     "pos": (1.7, 5.82, 0.46), "size": (2.80, 0.04, 0.78), "rgba": (0.74, 0.71, 0.66, 1)},
    {"name": "wk_counter", "room": "dining_room", "type": "box",
     "pos": (1.7, 9.35, 0.45), "size": (3.60, 0.65, 0.90), "rgba": (0.88, 0.86, 0.82, 1)},
    {"name": "wk_counter_top", "room": "dining_room", "type": "box",
     "pos": (1.7, 9.35, 0.93), "size": (3.70, 0.72, 0.07), "rgba": (0.24, 0.24, 0.27, 1), "mat": "mat_marble_dark"},
    {"name": "wk_oven", "room": "dining_room", "type": "box",
     "pos": (0.55, 9.00, 0.50), "size": (0.64, 0.04, 0.58), "rgba": (0.13, 0.13, 0.15, 1)},
    {"name": "wk_oven_handle", "room": "dining_room", "type": "box",
     "pos": (0.55, 8.97, 0.74), "size": (0.60, 0.05, 0.05), "rgba": (0.78, 0.80, 0.83, 1)},
    {"name": "wk_sink", "room": "dining_room", "type": "box",
     "pos": (2.70, 9.35, 0.96), "size": (0.76, 0.50, 0.10), "rgba": (0.78, 0.80, 0.82, 1), "mat": "mat_porcelain"},
    {"name": "wk_faucet", "room": "dining_room", "type": "cylinder",
     "pos": (2.70, 9.58, 1.14), "size": (0.05, 0.05, 0.34), "rgba": (0.80, 0.82, 0.84, 1), "mat": "mat_chrome"},
    {"name": "wk_upper", "room": "dining_room", "type": "box",
     "pos": (1.7, 9.55, 1.95), "size": (2.60, 0.36, 0.70), "rgba": (0.80, 0.76, 0.70, 1)},
    {"name": "wk_fridge", "room": "dining_room", "type": "box",
     "pos": (-0.05, 8.30, 0.95), "size": (0.80, 0.85, 1.90), "rgba": (0.86, 0.87, 0.90, 1), "mat": "mat_steel"},
    {"name": "wk_fridge_handle", "room": "dining_room", "type": "box",
     "pos": (0.32, 7.95, 1.42), "size": (0.05, 0.05, 0.60), "rgba": (0.55, 0.57, 0.60, 1), "mat": "mat_steel"},

    # ═══════ ④入户玄关：鞋柜 / 换鞋凳 / 挂衣 / 地垫 / 端景台 ═══════
    {"name": "entry_mat", "room": "entry", "type": "box",
     "pos": (8.7, -0.6, 0.005), "size": (0.90, 1.60, 0.01), "rgba": (0.33, 0.31, 0.30, 1)},
    {"name": "shoe_cabinet", "room": "entry", "type": "box",
     "pos": (9.30, 1.20, 1.10), "size": (0.45, 1.80, 2.20), "rgba": (0.72, 0.63, 0.52, 1)},
    {"name": "shoe_cab_handle", "room": "entry", "type": "box",
     "pos": (9.05, 0.75, 1.05), "size": (0.05, 0.05, 0.28), "rgba": (0.55, 0.56, 0.58, 1)},
    {"name": "bench", "room": "entry", "type": "box",
     "pos": (9.20, -2.20, 0.23), "size": (0.50, 1.30, 0.46), "rgba": (0.52, 0.38, 0.25, 1), "mat": "mat_fabric"},
    {"name": "coat_board", "room": "entry", "type": "box",
     "pos": (9.42, -2.20, 1.55), "size": (0.06, 1.40, 0.85), "rgba": (0.66, 0.56, 0.44, 1)},
    {"name": "console_entry", "room": "entry", "type": "box",
     "pos": (4.35, 0.60, 0.42), "size": (0.40, 1.60, 0.84), "rgba": (0.48, 0.35, 0.24, 1)},

    # ═══════ ⑤⑥ 中厨（并入鞋帽间储物）—— 沿墙布置，中间留通行区 ═══════
    # ⛔ 2026-07-25 重排：原先是 12 空间合并时留下的烂摊子——鞋帽间那组 2.3m 高的整墙柜
    #    横在房间正中（还正好堵住西墙那扇门），厨房操作台也悬在房间中央，结果 4.5×10m 的
    #    大房间被切成三块、只靠 54cm 和 90cm 两条缝连通。真实住宅不会这样：橱柜沿墙走、
    #    中间是通行区。这次按真实厨房重排（修的是"摆位不真实"，不是为了迁就哪种机器人）。
    #
    #    布局：主操作台一字型贴【西墙】(x=-0.5)，从 y=-2.6 到 -7.0，避开西墙那扇门(y -2.2..-0.8)；
    #         储物高柜与冰箱贴【北墙】(y=0)；中间 x 0.3~3.5 全是通行区（宽 3.2m）。

    # ── 贴北墙：冰箱（落地大件，从东门进来正对着它）+ 储物高柜（原鞋帽间那组）──
    {"name": "ck_fridge", "room": "chinese_kitchen", "type": "box",
     "pos": (0.05, -0.36, 0.93), "size": (0.90, 0.72, 1.85), "rgba": (0.88, 0.89, 0.91, 1), "mat": "mat_steel"},
    {"name": "ck_fridge_seam", "room": "chinese_kitchen", "type": "box",     # 上下门缝
     "pos": (0.05, -0.72, 1.20), "size": (0.88, 0.02, 0.02), "rgba": (0.55, 0.56, 0.58, 1)},
    {"name": "ck_fridge_handle_u", "room": "chinese_kitchen", "type": "box",
     "pos": (0.42, -0.73, 1.45), "size": (0.04, 0.04, 0.42), "rgba": (0.62, 0.64, 0.67, 1), "mat": "mat_chrome"},
    {"name": "ck_fridge_handle_l", "room": "chinese_kitchen", "type": "box",
     "pos": (0.42, -0.73, 0.90), "size": (0.04, 0.04, 0.38), "rgba": (0.62, 0.64, 0.67, 1), "mat": "mat_chrome"},
    {"name": "sr_cab_n", "room": "chinese_kitchen", "type": "box",
     "pos": (2.00, -0.21, 1.15), "size": (2.40, 0.42, 2.30), "rgba": (0.74, 0.66, 0.55, 1)},

    # ── 贴西墙：一字型主操作台（北→南：洗碗机 · 水槽 · 灶台 · 烤箱）──
    {"name": "ck_counter", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.175, -4.80, 0.45), "size": (0.65, 4.40, 0.90), "rgba": (0.84, 0.84, 0.80, 1)},
    {"name": "ck_counter_top", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.16, -4.80, 0.93), "size": (0.72, 4.50, 0.07), "rgba": (0.22, 0.22, 0.25, 1), "mat": "mat_marble_dark"},
    # 洗碗机：嵌在台面下（真实厨房就是这么装的），正面朝东——站在房间里一眼能看到
    {"name": "ck_dishwasher", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.17, -3.00, 0.44), "size": (0.62, 0.60, 0.80), "rgba": (0.88, 0.89, 0.91, 1), "mat": "mat_steel"},
    {"name": "ck_dw_door", "room": "chinese_kitchen", "type": "box",        # 整扇不锈钢门（一眼认得出是台家电）
     "pos": (0.145, -3.00, 0.40), "size": (0.02, 0.58, 0.62), "rgba": (0.86, 0.88, 0.90, 1),
     "mat": "mat_steel"},
    {"name": "ck_dw_panel", "room": "chinese_kitchen", "type": "box",        # 门顶上的控制面板（有屏有灯）
     "pos": (0.15, -3.00, 0.76), "size": (0.02, 0.58, 0.11), "mat": "mat_appliance_panel",
     "rgba": (0.85, 0.86, 0.88, 1)},
    {"name": "ck_dw_handle", "room": "chinese_kitchen", "type": "box",
     "pos": (0.17, -3.00, 0.68), "size": (0.05, 0.52, 0.05), "rgba": (0.62, 0.64, 0.67, 1), "mat": "mat_chrome"},
    {"name": "ck_sink", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.19, -4.00, 0.96), "size": (0.50, 0.76, 0.10), "rgba": (0.78, 0.80, 0.82, 1), "mat": "mat_porcelain"},
    {"name": "ck_faucet", "room": "chinese_kitchen", "type": "cylinder",
     "pos": (-0.40, -4.00, 1.15), "size": (0.05, 0.05, 0.36), "rgba": (0.86, 0.88, 0.90, 1), "mat": "mat_chrome"},
    {"name": "ck_stove", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.19, -5.30, 0.98), "size": (0.58, 0.80, 0.04), "rgba": (0.10, 0.10, 0.12, 1)},
    {"name": "ck_burner_a", "room": "chinese_kitchen", "type": "cylinder",
     "pos": (-0.19, -5.08, 1.01), "size": (0.26, 0.26, 0.03), "rgba": (0.45, 0.12, 0.10, 1)},
    {"name": "ck_burner_b", "room": "chinese_kitchen", "type": "cylinder",
     "pos": (-0.19, -5.52, 1.01), "size": (0.26, 0.26, 0.03), "rgba": (0.45, 0.12, 0.10, 1)},
    {"name": "ck_hood", "room": "chinese_kitchen", "type": "box",            # 抽油烟机在灶台正上方（真实高度）
     "pos": (-0.24, -5.30, 1.80), "size": (0.55, 1.00, 0.36), "rgba": (0.70, 0.72, 0.74, 1), "mat": "mat_steel"},
    # 烤箱：嵌在台面下，黑玻璃门 + 控制面板 + 横把手——厨房里最好认的一件
    {"name": "ck_oven", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.17, -6.40, 0.42), "size": (0.62, 0.62, 0.76), "rgba": (0.30, 0.31, 0.33, 1), "mat": "mat_steel"},
    {"name": "ck_oven_glass", "room": "chinese_kitchen", "type": "box",
     "pos": (0.145, -6.40, 0.40), "size": (0.02, 0.52, 0.50), "mat": "mat_oven_glass",
     "rgba": (0.14, 0.15, 0.17, 1)},
    {"name": "ck_oven_panel", "room": "chinese_kitchen", "type": "box",
     "pos": (0.145, -6.40, 0.73), "size": (0.02, 0.58, 0.11), "mat": "mat_appliance_panel",
     "rgba": (0.85, 0.86, 0.88, 1)},
    {"name": "ck_oven_handle", "room": "chinese_kitchen", "type": "box",
     "pos": (0.17, -6.40, 0.66), "size": (0.05, 0.56, 0.05), "rgba": (0.62, 0.64, 0.67, 1), "mat": "mat_chrome"},
    {"name": "ck_upper", "room": "chinese_kitchen", "type": "box",           # 吊柜（真实高度，贴西墙）
     "pos": (-0.32, -4.30, 1.95), "size": (0.36, 2.60, 0.70), "rgba": (0.78, 0.74, 0.68, 1)},

    # ── 贴东墙：储物矮柜（原鞋帽间中央矮柜，挪到两扇门之间）+ 穿衣镜 ──
    {"name": "sr_island", "room": "chinese_kitchen", "type": "box",
     "pos": (3.74, -3.40, 0.42), "size": (0.52, 1.60, 0.84), "rgba": (0.52, 0.40, 0.28, 1)},
    {"name": "sr_mirror", "room": "chinese_kitchen", "type": "box",
     "pos": (3.95, -6.60, 1.35), "size": (0.05, 1.10, 1.90), "rgba": (0.74, 0.82, 0.87, 1), "mat": "mat_mirror"},

    # ── 中央备餐台（真实中厨常见的中岛，只有 0.88m 高，不挡视线）──
    {"name": "ck_prep_table", "room": "chinese_kitchen", "type": "box",
     "pos": (1.90, -4.60, 0.44), "size": (1.60, 0.90, 0.88), "rgba": (0.82, 0.82, 0.80, 1)},

    # ═══════ ⑦晾晒区：晾衣杆 + 挂着的衣物 ═══════
    {"name": "dry_rail_a", "room": "chinese_kitchen", "type": "box",
     "pos": (1.7, -8.2, 2.10), "size": (3.40, 0.06, 0.06), "rgba": (0.75, 0.76, 0.78, 1)},
    {"name": "dry_rail_b", "room": "chinese_kitchen", "type": "box",
     "pos": (1.7, -8.9, 2.10), "size": (3.40, 0.06, 0.06), "rgba": (0.75, 0.76, 0.78, 1)},
    {"name": "dry_cloth_a", "room": "chinese_kitchen", "type": "box",
     "pos": (0.6, -8.2, 1.55), "size": (0.50, 0.05, 1.05), "rgba": (0.86, 0.88, 0.92, 1)},
    {"name": "dry_cloth_b", "room": "chinese_kitchen", "type": "box",
     "pos": (1.6, -8.2, 1.60), "size": (0.55, 0.05, 0.95), "rgba": (0.62, 0.70, 0.84, 1)},
    {"name": "dry_cloth_c", "room": "chinese_kitchen", "type": "box",
     "pos": (2.7, -8.9, 1.58), "size": (0.52, 0.05, 1.00), "rgba": (0.88, 0.76, 0.70, 1)},
    {"name": "dry_basket", "room": "chinese_kitchen", "type": "cylinder",
     "pos": (3.3, -7.6, 0.26), "size": (0.62, 0.62, 0.52), "rgba": (0.80, 0.78, 0.72, 1)},
    {"name": "dry_rack", "room": "chinese_kitchen", "type": "box",
     "pos": (-0.15, -8.5, 0.85), "size": (0.35, 1.60, 1.70), "rgba": (0.72, 0.72, 0.70, 1)},

    # ═══════ ⑧洗衣房：洗衣机 + 烘干机 + 水槽 + 置物架 ═══════
    {"name": "washer", "room": "laundry", "type": "box",
     "pos": (4.60, -6.30, 0.45), "size": (0.68, 0.70, 0.90), "rgba": (0.92, 0.92, 0.94, 1), "mat": "mat_steel"},
    {"name": "washer_door", "room": "laundry", "type": "cylinder",
     "pos": (4.95, -6.30, 0.55), "size": (0.44, 0.44, 0.04), "rgba": (0.30, 0.34, 0.40, 1), "mat": "mat_steel"},
    {"name": "dryer", "room": "laundry", "type": "box",
     "pos": (4.60, -5.50, 0.45), "size": (0.68, 0.70, 0.90), "rgba": (0.92, 0.92, 0.94, 1), "mat": "mat_steel"},
    {"name": "dryer_door", "room": "laundry", "type": "cylinder",
     "pos": (4.95, -5.50, 0.55), "size": (0.44, 0.44, 0.04), "rgba": (0.30, 0.34, 0.40, 1), "mat": "mat_steel"},
    {"name": "laundry_counter", "room": "laundry", "type": "box",
     "pos": (4.70, -5.90, 0.94), "size": (0.90, 2.00, 0.06), "rgba": (0.60, 0.55, 0.48, 1), "mat": "mat_marble_dark"},
    {"name": "laundry_sink", "room": "laundry", "type": "box",
     "pos": (4.70, -4.30, 0.90), "size": (0.70, 0.60, 0.30), "rgba": (0.90, 0.91, 0.92, 1), "mat": "mat_porcelain"},
    {"name": "laundry_shelf", "room": "laundry", "type": "box",
     "pos": (9.25, -5.20, 1.05), "size": (0.45, 2.60, 2.10), "rgba": (0.72, 0.70, 0.66, 1)},
    {"name": "laundry_basket", "room": "laundry", "type": "cylinder",
     "pos": (7.20, -6.30, 0.28), "size": (0.66, 0.66, 0.56), "rgba": (0.78, 0.74, 0.66, 1)},

    # ═══════ ⑩次卧：单人床 + 书桌 + 衣柜 ═══════
    {"name": "sbed_frame", "room": "second_bedroom", "type": "box",
     "pos": (-2.10, -8.20, 0.18), "size": (1.30, 2.10, 0.36), "rgba": (0.48, 0.34, 0.22, 1)},
    {"name": "sbed_mattress", "room": "second_bedroom", "type": "box",
     "pos": (-2.10, -8.20, 0.45), "size": (1.20, 2.00, 0.22), "rgba": (0.94, 0.92, 0.88, 1), "mat": "mat_fabric"},
    {"name": "sbed_pillow", "room": "second_bedroom", "type": "box",
     "pos": (-2.10, -9.30, 0.62), "size": (0.95, 0.45, 0.15), "rgba": (0.98, 0.98, 0.96, 1)},
    {"name": "sbed_blanket", "room": "second_bedroom", "type": "box",
     "pos": (-2.10, -7.65, 0.59), "size": (1.20, 1.15, 0.09), "rgba": (0.28, 0.50, 0.42, 1)},
    {"name": "sbed_headboard", "room": "second_bedroom", "type": "box",
     "pos": (-2.10, -9.62, 0.58), "size": (1.30, 0.10, 1.16), "rgba": (0.42, 0.30, 0.20, 1)},
    {"name": "sdesk", "room": "second_bedroom", "type": "box",
     "pos": (-0.85, -7.10, 0.75), "size": (0.60, 1.30, 0.06), "rgba": (0.55, 0.40, 0.27, 1)},
    {"name": "swardrobe", "room": "second_bedroom", "type": "box",
     "pos": (-0.80, -8.90, 1.05), "size": (0.58, 1.60, 2.10), "rgba": (0.80, 0.74, 0.62, 1)},

    # ═══════ ⑪客卫：马桶 + 台盆 + 淋浴 ═══════
    {"name": "gtoilet", "room": "guest_bath", "type": "box",
     "pos": (-3.45, -6.60, 0.20), "size": (0.44, 0.64, 0.40), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "gtoilet_tank", "room": "guest_bath", "type": "box",
     "pos": (-3.23, -6.60, 0.55), "size": (0.18, 0.54, 0.70), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "gvanity", "room": "guest_bath", "type": "box",
     "pos": (-5.10, -6.70, 0.40), "size": (0.55, 1.10, 0.80), "rgba": (0.58, 0.53, 0.48, 1)},
    {"name": "gbasin", "room": "guest_bath", "type": "box",
     "pos": (-5.10, -6.70, 0.86), "size": (0.50, 0.95, 0.12), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "gmirror", "room": "guest_bath", "type": "box",
     "pos": (-5.38, -6.70, 1.60), "size": (0.04, 1.00, 0.90), "rgba": (0.74, 0.82, 0.87, 1), "mat": "mat_mirror"},
    {"name": "gshower_tray", "room": "guest_bath", "type": "box",
     "pos": (-4.25, -9.00, 0.05), "size": (2.20, 1.60, 0.10), "rgba": (0.90, 0.91, 0.92, 1), "mat": "mat_porcelain"},
    {"name": "gshower_glass", "room": "guest_bath", "type": "box",
     "pos": (-4.25, -8.18, 1.05), "size": (2.20, 0.05, 2.00), "rgba": (0.75, 0.86, 0.90, 0.42), "mat": "mat_glass"},
    {"name": "gshower_head", "room": "guest_bath", "type": "cylinder",
     "pos": (-4.25, -9.60, 2.10), "size": (0.20, 0.20, 0.06), "rgba": (0.80, 0.82, 0.84, 1), "mat": "mat_chrome"},

    # ═══════ ⑫过道1：端景柜 + 挂画 + 绿植（主动线，别一片白）═══════
    {"name": "c1_console", "room": "corridor", "type": "box",
     "pos": (-5.20, -3.0, 0.42), "size": (0.36, 1.60, 0.84), "rgba": (0.48, 0.36, 0.25, 1)},
    {"name": "c1_art", "room": "corridor", "type": "box",
     "pos": (-5.38, -3.0, 1.80), "size": (0.05, 1.40, 0.95), "rgba": (0.62, 0.54, 0.66, 1)},

    # ═══════ ⑮小孩卧：儿童床 + 书桌 + 玩具收纳 ═══════
    {"name": "kbed_frame", "room": "kid_bedroom", "type": "box",
     "pos": (-8.10, -4.60, 0.18), "size": (1.30, 2.10, 0.36), "rgba": (0.62, 0.44, 0.30, 1)},
    {"name": "kbed_mattress", "room": "kid_bedroom", "type": "box",
     "pos": (-8.10, -4.60, 0.45), "size": (1.20, 2.00, 0.22), "rgba": (0.95, 0.93, 0.90, 1), "mat": "mat_fabric"},
    {"name": "kbed_pillow", "room": "kid_bedroom", "type": "box",
     "pos": (-8.10, -3.70, 0.62), "size": (0.95, 0.45, 0.15), "rgba": (0.98, 0.98, 0.96, 1)},
    {"name": "kbed_blanket", "room": "kid_bedroom", "type": "box",
     "pos": (-8.10, -5.20, 0.59), "size": (1.20, 1.20, 0.09), "rgba": (0.92, 0.62, 0.36, 1)},
    {"name": "kbed_headboard", "room": "kid_bedroom", "type": "box",
     "pos": (-8.10, -3.38, 0.55), "size": (1.30, 0.10, 1.10), "rgba": (0.55, 0.40, 0.26, 1)},
    {"name": "kdesk", "room": "kid_bedroom", "type": "box",
     "pos": (-6.10, -7.60, 0.72), "size": (0.60, 1.40, 0.06), "rgba": (0.66, 0.50, 0.34, 1)},
    {"name": "ktoy_shelf", "room": "kid_bedroom", "type": "box",
     "pos": (-9.20, -8.20, 0.60), "size": (0.40, 2.00, 1.20), "rgba": (0.82, 0.72, 0.55, 1)},
    {"name": "ktoy_box_a", "room": "kid_bedroom", "type": "box",
     "pos": (-8.95, -7.60, 0.30), "size": (0.42, 0.50, 0.36), "rgba": (0.85, 0.45, 0.40, 1)},
    {"name": "ktoy_box_b", "room": "kid_bedroom", "type": "box",
     "pos": (-8.95, -8.80, 0.30), "size": (0.42, 0.50, 0.36), "rgba": (0.40, 0.62, 0.82, 1)},
    {"name": "kball", "room": "kid_bedroom", "type": "cylinder",
     "pos": (-6.60, -5.80, 0.16), "size": (0.32, 0.32, 0.32), "rgba": (0.90, 0.75, 0.28, 1)},

    # ═══════ ⑯小孩卫：矮台盆 + 马桶 + 浴缸（儿童尺度）═══════
    {"name": "kb_vanity", "room": "kid_bedroom", "type": "box",
     "pos": (-9.10, -0.30, 0.35), "size": (0.55, 1.20, 0.70), "rgba": (0.72, 0.66, 0.56, 1)},
    {"name": "kb_basin", "room": "kid_bedroom", "type": "box",
     "pos": (-9.10, -0.30, 0.76), "size": (0.50, 1.00, 0.12), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "kb_mirror", "room": "kid_bedroom", "type": "box",
     "pos": (-9.38, -0.30, 1.45), "size": (0.04, 1.10, 0.90), "rgba": (0.74, 0.82, 0.87, 1), "mat": "mat_mirror"},
    {"name": "kb_toilet", "room": "kid_bedroom", "type": "box",
     "pos": (-9.05, -1.90, 0.18), "size": (0.42, 0.60, 0.36), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "kb_tub", "room": "kid_bedroom", "type": "box",
     "pos": (-6.60, 0.10, 0.26), "size": (1.40, 0.75, 0.52), "rgba": (0.96, 0.96, 0.95, 1), "mat": "mat_porcelain"},
    {"name": "kb_tub_inner", "room": "kid_bedroom", "type": "box",
     "pos": (-6.60, 0.10, 0.46), "size": (1.24, 0.60, 0.14), "rgba": (0.80, 0.90, 0.94, 1), "mat": "mat_porcelain"},
    {"name": "kb_duck", "room": "kid_bedroom", "type": "cylinder",
     "pos": (-6.60, 0.10, 0.58), "size": (0.22, 0.22, 0.16), "rgba": (0.96, 0.82, 0.22, 1)},

    # ═══════ ⑰主卧：大床 / 床头柜 / 床尾凳 ═══════
    {"name": "mbed_frame", "room": "master_bedroom", "type": "box",
     "pos": (-3.00, 7.60, 0.19), "size": (2.10, 2.25, 0.38), "rgba": (0.40, 0.29, 0.19, 1)},
    {"name": "mbed_mattress", "room": "master_bedroom", "type": "box",
     "pos": (-3.00, 7.60, 0.47), "size": (2.00, 2.15, 0.24), "rgba": (0.94, 0.92, 0.88, 1), "mat": "mat_fabric"},
    {"name": "mbed_pillow_l", "room": "master_bedroom", "type": "box",
     "pos": (-3.50, 8.50, 0.65), "size": (0.82, 0.46, 0.16), "rgba": (0.98, 0.98, 0.96, 1)},
    {"name": "mbed_pillow_r", "room": "master_bedroom", "type": "box",
     "pos": (-2.50, 8.50, 0.65), "size": (0.82, 0.46, 0.16), "rgba": (0.98, 0.98, 0.96, 1)},
    {"name": "mbed_blanket", "room": "master_bedroom", "type": "box",
     "pos": (-3.00, 6.95, 0.62), "size": (2.00, 1.40, 0.10), "rgba": (0.34, 0.32, 0.48, 1), "mat": "mat_fabric_blue"},
    {"name": "mbed_headboard", "room": "master_bedroom", "type": "box",
     "pos": (-3.00, 8.86, 0.72), "size": (2.20, 0.12, 1.44), "rgba": (0.52, 0.44, 0.36, 1)},
    {"name": "mnight_l", "room": "master_bedroom", "type": "box",
     "pos": (-4.45, 8.62, 0.27), "size": (0.55, 0.50, 0.54), "rgba": (0.40, 0.29, 0.19, 1)},
    {"name": "mnight_r", "room": "master_bedroom", "type": "box",
     "pos": (-1.55, 8.62, 0.27), "size": (0.55, 0.50, 0.54), "rgba": (0.40, 0.29, 0.19, 1)},
    {"name": "mbench", "room": "master_bedroom", "type": "box",
     "pos": (-3.00, 6.20, 0.25), "size": (1.80, 0.52, 0.50), "rgba": (0.55, 0.47, 0.38, 1), "mat": "mat_fabric"},
    {"name": "m_armchair", "room": "master_bedroom", "type": "box",
     "pos": (-1.30, 4.20, 0.24), "size": (0.85, 0.85, 0.48), "rgba": (0.52, 0.46, 0.40, 1), "mat": "mat_fabric"},

    # ═══════ ⑱衣帽间：两侧衣柜 + 中央岛柜 + 挂衣杆 ═══════
    {"name": "cl_w", "room": "closet", "type": "box",
     "pos": (-9.20, 2.75, 1.15), "size": (0.58, 3.20, 2.30), "rgba": (0.72, 0.63, 0.52, 1)},
    {"name": "cl_e", "room": "closet", "type": "box",
     "pos": (-5.80, 2.75, 1.15), "size": (0.58, 3.20, 2.30), "rgba": (0.72, 0.63, 0.52, 1)},
    {"name": "cl_rail_w", "room": "closet", "type": "box",
     "pos": (-8.88, 2.75, 1.12), "size": (0.05, 3.00, 0.05), "rgba": (0.60, 0.60, 0.62, 1)},
    {"name": "cl_clothes_w", "room": "closet", "type": "box",
     "pos": (-8.88, 2.75, 0.70), "size": (0.24, 2.80, 0.80), "rgba": (0.42, 0.45, 0.55, 1)},
    {"name": "cl_clothes_e", "room": "closet", "type": "box",
     "pos": (-6.12, 2.75, 0.70), "size": (0.24, 2.80, 0.80), "rgba": (0.56, 0.48, 0.44, 1)},
    {"name": "cl_island", "room": "closet", "type": "box",
     "pos": (-7.50, 2.75, 0.44), "size": (1.30, 0.80, 0.88), "rgba": (0.55, 0.45, 0.34, 1)},

    # ═══════ ⑳主卫：独立浴缸 + 双台盆 + 马桶 + 淋浴 ═══════
    {"name": "tub_body", "room": "master_bath", "type": "box",
     "pos": (-7.40, 8.60, 0.30), "size": (1.85, 0.92, 0.60), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "tub_inner", "room": "master_bath", "type": "box",
     "pos": (-7.40, 8.60, 0.54), "size": (1.65, 0.74, 0.18), "rgba": (0.84, 0.90, 0.93, 1), "mat": "mat_porcelain"},
    {"name": "tub_faucet", "room": "master_bath", "type": "cylinder",
     "pos": (-8.35, 8.60, 0.78), "size": (0.06, 0.06, 0.36), "rgba": (0.80, 0.82, 0.84, 1), "mat": "mat_chrome"},
    {"name": "mb_vanity", "room": "master_bath", "type": "box",
     "pos": (-9.10, 6.30, 0.40), "size": (0.60, 2.30, 0.80), "rgba": (0.45, 0.38, 0.32, 1)},
    {"name": "mb_basin_a", "room": "master_bath", "type": "box",
     "pos": (-9.10, 6.90, 0.86), "size": (0.52, 0.66, 0.12), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "mb_basin_b", "room": "master_bath", "type": "box",
     "pos": (-9.10, 5.70, 0.86), "size": (0.52, 0.66, 0.12), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "mb_mirror", "room": "master_bath", "type": "box",
     "pos": (-9.38, 6.30, 1.72), "size": (0.04, 2.20, 1.05), "rgba": (0.74, 0.82, 0.87, 1), "mat": "mat_mirror"},
    {"name": "mb_toilet", "room": "master_bath", "type": "box",
     "pos": (-5.90, 5.20, 0.20), "size": (0.44, 0.64, 0.40), "rgba": (0.97, 0.97, 0.96, 1), "mat": "mat_porcelain"},
    {"name": "mb_shower_tray", "room": "master_bath", "type": "box",
     "pos": (-6.30, 7.20, 0.05), "size": (1.60, 1.60, 0.10), "rgba": (0.90, 0.91, 0.92, 1), "mat": "mat_porcelain"},
    {"name": "mb_shower_glass", "room": "master_bath", "type": "box",
     "pos": (-7.13, 7.20, 1.05), "size": (0.05, 1.60, 2.00), "rgba": (0.75, 0.86, 0.90, 0.42), "mat": "mat_glass"},
    {"name": "mb_shower_head", "room": "master_bath", "type": "cylinder",
     "pos": (-5.75, 7.20, 2.20), "size": (0.22, 0.22, 0.06), "rgba": (0.80, 0.82, 0.84, 1), "mat": "mat_chrome"},

    # ═══════ ⑲过道2：端景 + 绿植 ═══════
    {"name": "c2_console", "room": "corridor", "type": "box",
     "pos": (-0.80, 1.5, 0.42), "size": (0.36, 1.60, 0.84), "rgba": (0.48, 0.36, 0.25, 1)},
    {"name": "c2_art", "room": "corridor", "type": "box",
     "pos": (-0.62, 1.5, 1.80), "size": (0.05, 1.30, 0.90), "rgba": (0.58, 0.60, 0.52, 1)},
]

# ═══════════ 精致家具（由 furniture.py 参数化生成：有腿、有横撑、有底盘、有器型）═══════════
# 手写基本体拼出来的家具一眼假（椅子没腿、落地灯就一根杆、花瓶是个圆柱）；
# 这些用构件库生成，一件家具由五到十个零件组成。
import os as _os, sys as _sys                                    # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # 被动态加载时也找得到同目录模块
import furniture as F                                              # noqa: E402

FURNITURE += (
    # 餐桌 + 六把带腿的椅子（长边各三把，面朝餐桌）
    F.table("dining", "dining_room", 1.7, 2.2, 2.60, 1.15, h=0.76)
    + F.chair("dchair_n1", "dining_room", 0.85, 3.10, yaw=-90)
    + F.chair("dchair_n2", "dining_room", 1.70, 3.10, yaw=-90)
    + F.chair("dchair_n3", "dining_room", 2.55, 3.10, yaw=-90)
    + F.chair("dchair_s1", "dining_room", 0.85, 1.30, yaw=90)
    + F.chair("dchair_s2", "dining_room", 1.70, 1.30, yaw=90)
    + F.chair("dchair_s3", "dining_room", 2.55, 1.30, yaw=90)
    # 中岛吧椅（带底盘和脚踏环）
    + F.stool("bstool_a", "dining_room", 0.90, 5.45)
    + F.stool("bstool_b", "dining_room", 2.50, 5.45)
    # 客厅：圆茶几（三段式）+ 落地灯（五件套）+ 茶几上的摆件
    + F.round_table("coffee", "living_room", 6.5, 6.3, dia=1.25, h=0.42)
    + F.floor_lamp("flamp", "living_room", 5.0, 9.1)
    + F.books_stack("cbooks", "living_room", 6.28, 6.55, 0.455)
    + F.tray_set("ctray", "living_room", 6.72, 6.05, 0.455)
    + F.potted_plant("lplant", "living_room", 8.9, 3.4)
    # 玄关端景：花瓶（底足-鼓腹-收颈-瓶口 + 插花）
    + F.vase("evase", "entry", 4.35, 0.60, 0.84)
    # 过道绿植
    + F.potted_plant("cplant", "corridor", -1.10, -5.30)
    # 主卧床头两盏台灯
    + F.table_lamp("mlamp_l", "master_bedroom", -4.45, 8.62, 0.54)
    + F.table_lamp("mlamp_r", "master_bedroom", -1.55, 8.62, 0.54)
    # 书桌椅（次卧）与小孩房的椅子，也换成带腿的
    + F.chair("sdchair", "second_bedroom", -1.55, -7.10, yaw=180, seat_w=0.42, seat_d=0.42)
    + F.chair("kchair", "kid_bedroom", -7.00, -7.60, yaw=0, seat_w=0.42, seat_d=0.42,
              rgba=(0.55, 0.70, 0.62, 1.0))
)

# ---------------------------------------------------------------- 墙上挂画（视觉干扰项）
# 让 ANIMA 必须靠**真正的房间特征**（床/灶台/马桶/沙发）判断在哪间屋，
# 而不是"墙上有东西"就乱猜。每项 = dict(room, side 贴哪面墙 n/s/e/w,
#   center 沿墙方向中心, z 画心高度, w 画宽, h 画高, tex 用第几张画 art0..art3)
WALL_ARTS: list[dict] = [
    {"room": "living_room", "side": "n", "center": 6.5, "z": 1.75, "w": 1.6, "h": 1.1, "tex": "art0"},
    {"room": "living_room", "side": "e", "center": 3.2, "z": 1.70, "w": 1.2, "h": 0.9, "tex": "art3"},
    {"room": "dining_room", "side": "w", "center": 2.5, "z": 1.70, "w": 1.4, "h": 1.0, "tex": "art2"},
    {"room": "dining_room", "side": "n", "center": 1.8, "z": 1.75, "w": 1.3, "h": 0.95, "tex": "art1"},
    {"room": "corridor", "side": "w", "center": -3.0, "z": 1.80, "w": 1.5, "h": 1.05, "tex": "art1"},
    {"room": "corridor", "side": "e", "center": 1.0, "z": 1.75, "w": 1.2, "h": 0.9, "tex": "art0"},
    {"room": "master_bedroom", "side": "e", "center": 6.5, "z": 1.75, "w": 1.4, "h": 1.0, "tex": "art3"},
    {"room": "entry", "side": "w", "center": -1.0, "z": 1.70, "w": 1.1, "h": 0.85, "tex": "art2"},
    {"room": "second_bedroom", "side": "e", "center": -8.0, "z": 1.65, "w": 0.9, "h": 0.7, "tex": "art0"},
    {"room": "kid_bedroom", "side": "e", "center": -6.5, "z": 1.55, "w": 1.0, "h": 0.8, "tex": "art2"},
    {"room": "chinese_kitchen", "side": "e", "center": -8.5, "z": 1.70, "w": 1.0, "h": 0.75, "tex": "art3"},
]
ART_FRAME_RGBA = (0.22, 0.18, 0.15, 1.0)   # 画框深木色
ART_FRAME_T = 0.06

# ---------------------------------------------------------------- 城市背景板
# 屋外四周立几面大背景板，贴城市天际线贴图 —— 任何一扇窗望出去都是城市。
# 这是游戏常用的 matte painting：不建真城市，用远景图糊住地平线（省算力、效果好）。
CITY_BACKDROP = {"dist": 46.0, "width": 130.0, "height": 34.0, "z": 12.0}

# ---------------------------------------------------------------- 窗外景色
OUTDOOR_GROUND = {"size": (120.0, 120.0, 0.10), "pos": (0.0, 0.0, -0.06),
                  "rgba": (0.42, 0.55, 0.30, 1.0)}

TREES: list[tuple[float, float, float, float]] = [
    (-14.0, 8.0, 3.0, 3.8), (-13.0, 2.0, 2.6, 3.2), (-14.5, -4.0, 2.8, 3.4),
    (-13.0, -10.0, 2.4, 3.0), (-6.0, -14.0, 2.8, 3.6), (1.0, -14.5, 2.6, 3.2),
    (8.0, -12.0, 3.0, 3.8), (14.0, -6.0, 2.6, 3.2), (14.5, 2.0, 2.8, 3.4),
    (13.5, 9.0, 2.4, 3.0), (6.0, 14.0, 3.0, 3.8), (-2.0, 14.5, 2.6, 3.2),
    (-10.0, 13.5, 2.8, 3.4),
]
TRUNK_RGBA = (0.36, 0.25, 0.16, 1.0)
FOLIAGE_RGBA = (0.24, 0.45, 0.22, 1.0)

BUILDINGS: list[tuple] = [
    (-38.0, 30.0, 12.0, 12.0, 20.0, (0.68, 0.66, 0.63, 1.0)),
    (-16.0, 38.0, 11.0, 11.0, 26.0, (0.60, 0.62, 0.66, 1.0)),
    (24.0, 34.0, 13.0, 11.0, 22.0, (0.70, 0.67, 0.62, 1.0)),
    (40.0, -12.0, 12.0, 15.0, 18.0, (0.64, 0.63, 0.60, 1.0)),
    (-34.0, -26.0, 13.0, 12.0, 16.0, (0.66, 0.64, 0.62, 1.0)),
    (8.0, -38.0, 14.0, 11.0, 19.0, (0.69, 0.66, 0.62, 1.0)),
]


def room_at(x: float, y: float) -> str | None:
    """(x, y) 落在哪间屋里 → 房间 key；都不在（墙里/屋外）→ None。

    世界服务的 /status（上帝视角，仅供人验收）用它回答「狗到底走到哪间屋了」。
    ⛔ 结果绝不进大脑的观测——ANIMA 认房间必须靠看画面。
    """
    for key, room in ROOMS.items():
        x0, y0, x1, y1 = room["rect"]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return key
    return None


def room_label(key: str | None) -> str:
    """房间 key → 中文名（给人看的）。"""
    if key is None:
        return "（不在任何房间内）"
    return ROOMS[key]["label"]
