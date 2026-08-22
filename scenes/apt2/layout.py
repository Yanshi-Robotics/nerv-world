"""apt2 —— 曼哈顿 62–63 层复式顶层豪宅（双高客厅 + 真能坐的家具）。

**为什么建它**：house1 考平地动线、house2 考高差、apt1 考"够不着的强视觉信号"。
apt2 考的是前三个都没有的那件事——**屋里的东西真的会动、真的坐得下**，
再加上一部要爬的楼梯。

**它和 apt1 的关系**：同一栋楼、同一片窗外景色（`SKYBOX` / `SKYLINE` / `GROUND_SLABS`
直接借 apt1 的，⛔ 绝不重跑 `make_view.py --nyc`——那会联网重抓 NYC Open Data，
2716 栋楼的坐标可能全变，那不叫复用，叫换内容）。
不同的是：apt1 是一层大平层，apt2 是复式两层，而且家具有**真碰撞**。

════════════════════════════════════════════════════════════════════════
⭐ 竖向尺寸是**算出来的**，而且推导方向和 house2 相反 —— 这一点必须写明白
════════════════════════════════════════════════════════════════════════

house2 的规矩是「先定台阶 → 推层高」。apt2 有一个外部硬约束把方向掉了个个儿：

    **层高必须等于 apt1 的 FLOOR_TO_FLOOR = 3.75 m。**

因为 62 层那套外景全按它算：`ELEV = 62 × 3.75 = 232.5`，`GROUND_SLABS` 落在 −232.5，
`SKYLINE` 里 2716 栋楼的高度也全是 `h − ELEV`。层高一改，窗外整片城市就错位。

⇒ 所以这里是**固定层高、反推踢面高**，自由变量只剩「一层几个踢面」这个整数。
   这仍然是「算出来的，不是选出来的」，只是被钉死的那一端换了。

    踢面数/层   踢面高     一跑   踏板   跑长    坡度      判定
        20      0.18750    10     9     2.70   32.01°   ❌ 超规范上限 0.175
        22      0.17045    11    10     3.00   29.60°   ✅ 但贴着上限
     ⭐ 24      0.15625    12    11     3.30   27.51°   ✅ 取它
        26      0.14423    13    12     3.60   25.68°   ✅ 跑更长，占地更大

⛔ **不能抄 house2 的 0.16 / 9 踢面 / 2.88 层高** —— 那套是它自己反推出来的。
"""
from __future__ import annotations

import math

from scenes import furniture as F        # noqa: E402  家具零件库，所有场景共用
from scenes import manifest as _SCENES   # noqa: E402  借 apt1 的窗外景色

# ⭐ 只读地借 apt1 的外景。`load_layout` 会缓存，重复调用不会重复执行那 2729 行体块表。
# ⚠️ 它加载期间会把仓根塞进 sys.path，而调用方（make_house / check_scene）本来就已经
#    塞过了；那个函数只在**不存在时**才插入、结束再删，所以嵌套调用是安全的。
_A1 = _SCENES.load_layout("apt1")

# ────────────────────────────────────────────────────────── 构造尺度
WALL_THICK = 0.14
FLOOR_THICK = 0.05
CEILING_THICK = 0.10
CEILING_GROUP = 1                        # ⚠️ 必须用默认可见的组
CEILING_RGBA = (0.95, 0.95, 0.93, 1.0)
DOOR_HEIGHT = 2.45                       # 顶层豪宅的门比常规高

DOOR_FRAME_THICK = 0.05
DOOR_FRAME_RGBA = (0.62, 0.52, 0.32, 1.0)
WINDOW_FRAME_T = 0.05
WINDOW_FRAME_RGBA = (0.30, 0.30, 0.32, 1.0)
ART_FRAME_T = 0.05
ART_FRAME_RGBA = (0.20, 0.18, 0.16, 1.0)

WINDOW_SILL_H = 0.95                     # 普通窗（apt2 全是落地窗，这两个只为满足契约）
WINDOW_TOP_H = 2.30

# ── 这栋楼在哪一层：⚠️ 三个数必须和 apt1 逐位一致，外景才对得上 ──────────
FLOOR_LEVEL = _A1.FLOOR_LEVEL            # 62
FLOOR_TO_FLOOR = _A1.FLOOR_TO_FLOOR      # 3.75
ELEV = _A1.ELEV                          # 232.5
assert FLOOR_TO_FLOOR == 3.75 and abs(ELEV - FLOOR_LEVEL * FLOOR_TO_FLOOR) < 1e-9, \
    "层高/标高和 apt1 对不上，窗外那片城市会整体错位"

N_FLOORS = 2

# ══════════════════════════════════════════════════════════ 楼梯参数
# 依据《住宅设计规范》GB 50096-2011 §6.3，每一条 check_scene.py 都会复核。
RISERS_PER_STOREY = 24                   # ⭐ 唯一的自由变量，且必须是偶数（双跑各一半）
RISERS_PER_FLIGHT = RISERS_PER_STOREY // 2          # 12
TREADS_PER_FLIGHT = RISERS_PER_FLIGHT - 1           # ⛔ 踏板 = 踢面 − 1，最上一级是平台
STEP_RISE = FLOOR_TO_FLOOR / RISERS_PER_STOREY      # 0.15625
STEP_RUN = 0.30                          # 规范下限 0.26；G1 脚长约 0.25，必须留真余量
STEP_WIDTH = 1.20                        # 规范 ≥1.10
LANDING_DEPTH = 1.40                     # 规范 ≥ 梯段净宽且 ≥1.20
STEP_SLAB = 0.25                         # ⛔ 板厚必须 > 踢面，否则踢面处露缝
STEP_FRICTION = 1.0                      # ⭐ 有意留的旋钮：上楼滑不滑是想扫的变量
STEP_RGBA = (0.78, 0.74, 0.68, 1.0)
STEP_MAT = "mat_h3_travertine"
LANDING_THICK = 0.10
RAIL_HEIGHT = 0.95
RAIL_THICK = 0.06
RAIL_RGBA = (0.24, 0.22, 0.20, 1.0)
WELL_WALL_THICK = 0.12
WELL_WALL_RGBA = (0.90, 0.89, 0.86, 1.0)
WELL_WALL_MAT = "mat_h3_wall"

STOREY_H = FLOOR_TO_FLOOR                                # 3.75
WALL_HEIGHT = STOREY_H - CEILING_THICK - FLOOR_THICK     # 3.60（比 apt1 的 3.30 更高敞）
STAIR_HEADROOM = STOREY_H - STEP_SLAB                    # 3.50

FLOOR_WINDOW_SILL = 0.05
FLOOR_WINDOW_TOP = WALL_HEIGHT - 0.12                    # 3.48

# ⛔ 算不上就 import 期失败：宁可不生成，也别生成一部走不了的楼梯
assert RISERS_PER_STOREY % 2 == 0, "踢面数必须是偶数，双跑才分得均"
assert STEP_RISE <= 0.175 and STEP_RUN >= 0.26, "踏步尺寸超出 GB 50096"
assert STEP_RUN >= 0.25 + 0.03, "踏面没给 G1 的脚（0.25 m）留够余量"
assert 0.60 <= 2 * STEP_RISE + STEP_RUN <= 0.66, "2R+G 不在走着舒服的区间"
assert STEP_SLAB > STEP_RISE, "梯段板厚必须大于踢面，否则踢面处露缝"
assert LANDING_DEPTH >= max(STEP_WIDTH, 1.20), "平台进深不够"
assert STAIR_HEADROOM >= 2.20, f"梯段净高 {STAIR_HEADROOM:.2f} m 低于规范 2.20"
assert abs(RISERS_PER_STOREY * STEP_RISE - STOREY_H) < 1e-9, "踢面数 × 踢面高 ≠ 层高"


def FLOOR_Z(floor: int) -> float:
    """第 n 层地面的世界高度。⭐ 62 层仍然是 z=0——「在 232 米高」只体现在窗外几何被压低。"""
    return floor * STOREY_H


# ══════════════════════════════════════════ 楼梯井净尺寸（由上面推出来）
# ⚠️ 梯段水平投影是 **(踢面数−1) × 踏面**，因为最上面一级是平台
_SHAFT_W = 2 * STEP_WIDTH + WELL_WALL_THICK                     # 2.52（沿 y）
_SHAFT_D = 2 * LANDING_DEPTH + TREADS_PER_FLIGHT * STEP_RUN     # 6.10（沿 x）

# ────────────────────────────────────────────────────────── 平面网格
# ⭐ 外轮廓和 apt1 逐位相同（23.0 × 15.0 m）——这样 `HOST_TOWER` 的立面尺寸、
#    `check_park_sightline` 的 `PARK_WALL_Y` 全部直接复用，不用重算。
X0, X4 = -11.5, 11.5
Y0, Y3 = -7.5, 7.5

# 楼梯间贴西墙，横躺在中间带（长边 6.38 沿 x，短边 2.80 沿 y）
STAIR_X0 = X0
STAIR_X1 = STAIR_X0 + _SHAFT_D + 2 * WALL_THICK                 # -5.12
STAIR_Y0 = -_SHAFT_W / 2 - WALL_THICK                           # -1.40
STAIR_Y1 = +_SHAFT_W / 2 + WALL_THICK                           # +1.40
Y1, Y2 = STAIR_Y0, STAIR_Y1                                     # 中间带 = 楼梯间的进深

XS = STAIR_X1                                                   # 楼梯间东墙
XA, XB = -0.5, 5.5                                              # 大客厅东西边
ENFILADE_X = (XA + XB) / 2.0                                    # 2.5 —— 大客厅中轴 = 玄关中心
PARK_WALL_Y = Y3                                                # 观景墙（check_park_sightline 用）

# 净空（内缩**整个**墙厚）
_IN_X0, _IN_X1 = STAIR_X0 + WALL_THICK, STAIR_X1 - WALL_THICK   # -11.36 … -5.26
_IN_Y0, _IN_Y1 = STAIR_Y0 + WALL_THICK, STAIR_Y1 - WALL_THICK   # -1.26 … +1.26
_UP_Y = _IN_Y0 + STEP_WIDTH / 2.0        # 上行跑中心线（南侧车道）= -0.66
_DN_Y = _IN_Y1 - STEP_WIDTH / 2.0        # 回头跑中心线（北侧车道）= +0.66
_WELL_Y = (_IN_Y0 + _IN_Y1) / 2.0        # 梯井隔墙中心 = 0.0

# 三段 x 分界：楼层平台 → 梯段 → 中间平台（往东爬）
_FLOOR_LANDING_X1 = _IN_X0 + LANDING_DEPTH                          # -9.96
_MID_LANDING_X0 = _FLOOR_LANDING_X1 + TREADS_PER_FLIGHT * STEP_RUN  # -6.66
assert abs((_MID_LANDING_X0 + LANDING_DEPTH) - _IN_X1) < 1e-9, "楼梯井进深和三段之和对不上"

# 楼层平台的矩形。⚠️ 三条边取**房间矩形**的边（不是净空边）：楼板本来就该压到墙心，
#    和隔壁屋的楼板严丝合缝接上；house2 第一版取净空边，门槛底下留了 0.14 m 裂缝。
#    只有东边取净空里的梯段起跑线。
FLOOR_LANDING_RECT = (STAIR_X0, STAIR_Y0, _FLOOR_LANDING_X1, STAIR_Y1)

# ── 双高客厅的挑空 ──────────────────────────────────────────────────
# 上层只铺南侧一条环廊，中间留空通到下层。⛔ 整层不铺 = 从上面走出楼梯就掉下去；
# 整层都铺 = 双高客厅被封死，那就不叫双高了。
MEZZ_WALK_D = 1.60                                              # 环廊进深
MEZZ_WALK_RECT = (XA, Y2, XB, Y2 + MEZZ_WALK_D)                 # (-0.5, 1.4, 5.5, 3.0)

_W_WARM = (0.92, 0.90, 0.87, 1.0)
_W_COOL = (0.89, 0.90, 0.91, 1.0)
_F_OAK = (0.55, 0.42, 0.30, 1.0)
_F_STONE = (0.78, 0.76, 0.73, 1.0)


def _room(rect, label, floor, *, warm=True, stone=False, **extra) -> dict:
    d = {"rect": rect, "label": label, "floor": floor,
         "wall_rgba": _W_WARM if warm else _W_COOL, "wall_mat": "mat_h3_wall",
         "floor_rgba": _F_STONE if stone else _F_OAK,
         "floor_mat": "mat_h3_travertine" if stone else "mat_h3_oak"}
    d.update(extra)
    return d


ROOMS: dict[str, dict] = {
    # ═══════════════ 62 层（下层）═══════════════
    "kitchen":    _room((X0, Y2, XS, Y3), "厨房", 0, warm=False, stone=True),
    "dining":     _room((XS, Y2, XA, Y3), "餐厅", 0),
    # ⭐ 双高大客厅：不封顶，竖着通到 63 层
    "great_room": _room((XA, Y2, XB, Y3), "双高大客厅", 0, no_ceiling=True),
    "library":    _room((XB, Y2, X4, Y3), "图书室", 0),
    "stair_f62":  _room((STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "楼梯间", 0,
                        stone=True, no_ceiling=True),   # ⛔ 梯井竖着通，封顶就堵死
    "gallery":    _room((XS, Y1, XB, Y2), "画廊", 0, stone=True),
    "east_hall":  _room((XB, Y1, X4, Y2), "东过厅", 0, stone=True),
    "guest_bed":  _room((X0, Y0, XS, Y1), "客卧", 0),
    "guest_bath": _room((XS, Y0, -1.5, Y1), "客卫", 0, warm=False, stone=True),
    "laundry":    _room((-1.5, Y0, 1.5, Y1), "洗衣房", 0, warm=False, stone=True),
    "foyer":      _room((1.5, Y0, 6.5, Y1), "入户玄关", 0, stone=True),
    "media":      _room((6.5, Y0, X4, Y1), "影音室", 0, warm=False),

    # ═══════════════ 63 层（上层）═══════════════
    "primary_bed":  _room((X0, Y2, XS, Y3), "主卧", 1),
    "study":        _room((XS, Y2, XA, Y3), "书房", 1),
    # ⭐ 挑空环廊：只铺南侧一条，其余留空
    "mezzanine":    _room((XA, Y2, XB, Y3), "挑空环廊", 1,
                          floor_rects=[MEZZ_WALK_RECT]),
    "sitting":      _room((XB, Y2, X4, Y3), "起居厅", 1),
    # ⭐ 顶层楼梯间**要封顶**：上面没有梯段要升上去了，不封就是从屋里看见天
    "stair_f63":    _room((STAIR_X0, STAIR_Y0, STAIR_X1, STAIR_Y1), "上层楼梯间", 1,
                          stone=True, floor_rects=[FLOOR_LANDING_RECT]),
    "upper_hall":   _room((XS, Y1, XB, Y2), "上层过厅", 1, stone=True),
    "dressing":     _room((XB, Y1, X4, Y2), "衣帽间", 1),
    "primary_bath": _room((X0, Y0, XS, Y1), "主卫", 1, warm=False, stone=True),
    "closet":       _room((XS, Y0, -1.5, Y1), "储物间", 1, warm=False, stone=True),
    "gym":          _room((-1.5, Y0, 1.5, Y1), "健身房", 1, warm=False, stone=True),
    "family":       _room((1.5, Y0, 6.5, Y1), "家庭厅", 1),
    "terrace_room": _room((6.5, Y0, X4, Y1), "阳光厅", 1, warm=False, stone=True),
}

# ────────────────────────────────────────────────────────── 门 / 通道
# orient: "h" = 门在水平墙上（y = coord）；"v" = 竖直墙（x = coord）
# kind="open" = 整段墙拆掉的通道
DOORS: list[dict] = [
    # ═══ 62 层 ═══
    # ⭐ 贯通轴线：玄关 → 画廊 → 双高大客厅，三个洞口全部对齐在 ENFILADE_X
    {"orient": "h", "coord": Y1, "center": ENFILADE_X, "width": 2.60, "kind": "open",
     "floor": 0, "note": "玄关→画廊（贯通轴线第一道）"},
    {"orient": "h", "coord": Y2, "center": ENFILADE_X, "width": 4.00, "kind": "open",
     "floor": 0, "note": "画廊→双高大客厅（贯通轴线第二道）"},
    {"orient": "v", "coord": XS, "center": 0.0, "width": 1.30, "floor": 0,
     "note": "画廊→楼梯间"},
    {"orient": "h", "coord": Y2, "center": -8.0, "width": 1.60, "kind": "open", "floor": 0,
     "note": "楼梯间→厨房"},
    {"orient": "v", "coord": XA, "center": 4.6, "width": 1.80, "kind": "open", "floor": 0,
     "note": "餐厅→大客厅"},
    {"orient": "v", "coord": XB, "center": 4.6, "width": 1.60, "kind": "open", "floor": 0,
     "note": "大客厅→图书室"},
    {"orient": "v", "coord": XB, "center": 0.0, "width": 1.40, "kind": "open", "floor": 0,
     "note": "画廊→东过厅"},
    {"orient": "h", "coord": Y1, "center": -8.6, "width": 1.10, "floor": 0,
     "note": "楼梯间→客卧"},
    {"orient": "v", "coord": -1.5, "center": -4.4, "width": 0.95, "floor": 0,
     "note": "客卫→洗衣房"},
    {"orient": "h", "coord": Y1, "center": -3.4, "width": 1.00, "floor": 0,
     "note": "画廊→客卫"},
    {"orient": "v", "coord": 6.5, "center": -4.4, "width": 1.20, "floor": 0,
     "note": "玄关→影音室"},
    {"orient": "v", "coord": 1.5, "center": -4.4, "width": 1.00, "floor": 0,
     "note": "洗衣房→玄关"},
    # ═══ 63 层 ═══
    {"orient": "v", "coord": XS, "center": 0.0, "width": 1.30, "floor": 1,
     "note": "上层过厅→楼梯间"},
    {"orient": "h", "coord": Y2, "center": ENFILADE_X, "width": 3.20, "kind": "open",
     "floor": 1, "note": "上层过厅→挑空环廊"},
    {"orient": "h", "coord": Y2, "center": -2.8, "width": 1.30, "floor": 1,
     "note": "上层过厅→书房"},
    {"orient": "h", "coord": Y2, "center": -8.0, "width": 1.30, "floor": 1,
     "note": "楼梯间→主卧"},
    {"orient": "v", "coord": XB, "center": 0.0, "width": 1.40, "kind": "open", "floor": 1,
     "note": "上层过厅→衣帽间"},
    {"orient": "v", "coord": XB, "center": 4.6, "width": 1.60, "kind": "open", "floor": 1,
     "note": "挑空环廊→起居厅"},
    {"orient": "h", "coord": Y1, "center": -8.6, "width": 1.20, "floor": 1,
     "note": "楼梯间→主卫"},
    {"orient": "h", "coord": Y1, "center": -3.4, "width": 1.00, "floor": 1,
     "note": "上层过厅→储物间"},
    {"orient": "h", "coord": Y1, "center": 0.0, "width": 1.20, "floor": 1,
     "note": "上层过厅→健身房"},
    {"orient": "h", "coord": Y1, "center": 4.0, "width": 1.60, "kind": "open", "floor": 1,
     "note": "上层过厅→家庭厅"},
    {"orient": "v", "coord": 6.5, "center": -4.4, "width": 1.60, "kind": "open", "floor": 1,
     "note": "家庭厅→阳光厅"},
]


# ────────────────────────────────────────────────────────── 落地窗
def _glass_wall(room: str, side: str, a: float, b: float, n: int, *,
                pier: float = 0.42, mullion: float = 0.34) -> list[dict]:
    """把一段外墙切成 n 个玻璃开间：两端留墙垛、格间留竖挺。

    ⛔ 为什么不许整段开窗：`make_house._solid_runs()` 在开口铺满整条边时返回**空列表**，
       门楣梁下面就一个支点都没有了。真实幕墙本来也有墙垛和竖挺，切开既对又好看。

    ⚠️ 这个函数是**从 apt1 抄过来的，有意不共用**：它闭包着本场景自己的
       `FLOOR_WINDOW_SILL / FLOOR_WINDOW_TOP`（apt2 层高更高，窗顶到 3.48 而不是 3.18）。
       ⛔ 别为了"去重"把它提到 `scenes/furniture.py` 里——那会把 apt2 的窗高
       悄悄绑到 apt1 的常量上，改一边坏另一边。
    """
    span = (b - a) - 2 * pier - (n - 1) * mullion
    if span <= 0:
        raise ValueError(f"{room} 的 {side} 墙放不下 {n} 个开间（净长 {b - a:.2f} m）")
    bw = span / n
    return [{"room": room, "side": side,
             "center": round(a + pier + bw / 2 + i * (bw + mullion), 4),
             "width": round(bw, 4), "sill": FLOOR_WINDOW_SILL, "top": FLOOR_WINDOW_TOP,
             "glass": True} for i in range(n)]


WINDOWS = (
    # ── 62 层北面观景墙：整排朝中央公园 ─────────────────────────────
    _glass_wall("kitchen", "n", X0, XS, 2)
    + _glass_wall("dining", "n", XS, XA, 2)
    + _glass_wall("great_room", "n", XA, XB, 3)     # ⭐ 中间那扇正对贯通轴线
    + _glass_wall("library", "n", XB, X4, 2)
    # ── 62 层西 / 东 / 南 ──────────────────────────────────────
    + _glass_wall("kitchen", "w", Y2, Y3, 1)
    + _glass_wall("library", "e", Y2, Y3, 1)
    + _glass_wall("guest_bed", "s", X0, XS, 2)
    + _glass_wall("guest_bed", "w", Y0, Y1, 1)
    + _glass_wall("media", "s", 6.5, X4, 1)
    + _glass_wall("media", "e", Y0, Y1, 1)
    # ── 63 层北面：双高客厅的上半段也是玻璃 ───────────────────────
    + _glass_wall("primary_bed", "n", X0, XS, 2)
    + _glass_wall("study", "n", XS, XA, 2)
    + _glass_wall("mezzanine", "n", XA, XB, 3)      # ⭐ 与下层三扇对齐 = 7.35 m 通高幕墙
    + _glass_wall("sitting", "n", XB, X4, 2)
    # ── 63 层西 / 东 / 南 ──────────────────────────────────────
    + _glass_wall("primary_bed", "w", Y2, Y3, 1)
    + _glass_wall("sitting", "e", Y2, Y3, 1)
    + _glass_wall("primary_bath", "w", Y0, Y1, 1)
    + _glass_wall("terrace_room", "s", 6.5, X4, 1)
    + _glass_wall("terrace_room", "e", Y0, Y1, 1)
    # ⛔ 画廊 / 过厅 / 客卫 / 洗衣 / 玄关 / 储物 / 健身**永不开窗**：
    #    那一带是楼栋核心筒，外面是 232 米空气。
)

GLASS_RGBA = _A1.GLASS_RGBA
GLASS_THICK = _A1.GLASS_THICK
WALL_FACE_FIX = True

# 入户门：玄关南墙。⛔ 不写厚度、不写 pos——门厚由生成器从 WALL_THICK 推
FRONT_DOOR = {
    "room": "foyer", "side": "s", "center": 4.0, "width": 1.30, "height": DOOR_HEIGHT,
    "mat": "mat_h3_oak_dark", "rgba": (0.22, 0.20, 0.18, 1.0),
    "casing_rgba": (0.62, 0.52, 0.32, 1.0), "handle_rgba": (0.72, 0.63, 0.40, 1.0),
    "handle_side": 1,
}

# ══════════════════════════════════════════════════════════ 楼梯本体
STAIRS: list[dict] = []
LANDINGS: list[dict] = []
GUARDS: list[dict] = []

_HALF_STOREY = RISERS_PER_FLIGHT * STEP_RISE          # 1.875 m = 中间平台标高

for _f in range(N_FLOORS - 1):
    _base = FLOOR_Z(_f)
    # ② 上行跑：从楼层平台的东缘起步，往东爬到中间平台
    STAIRS.append({
        "name": f"stair{_f}_up", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_FLOOR_LANDING_X1, _UP_Y), "dir": (1.0, 0.0), "base_z": _base,
        "rail_side": -1,      # ⚠️ rail_side 是**世界轴**的符号，与前进方向无关
    })
    # ③ 中间休息平台：通宽，东端，顶面 = 半层
    LANDINGS.append({
        "name": f"stair{_f}_mid",
        "pos": ((_MID_LANDING_X0 + _IN_X1) / 2.0, _WELL_Y,
                _base + _HALF_STOREY - LANDING_THICK / 2.0),
        "size": (_IN_X1 - _MID_LANDING_X0, _IN_Y1 - _IN_Y0, LANDING_THICK),
    })
    # ④ 回头跑：⛔ 从**中间平台的西缘**起步（不是东墙根！），往西爬到上一层
    STAIRS.append({
        "name": f"stair{_f}_dn", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_MID_LANDING_X0, _DN_Y), "dir": (-1.0, 0.0),
        "base_z": _base + _HALF_STOREY,
        "rail_side": +1,
    })

# 梯井隔墙：只在梯段那一段（两块平台之间）立墙，通高到顶层天花板
WELL_WALLS: list[dict] = [{
    "name": "stair_well_wall",
    "pos": ((_FLOOR_LANDING_X1 + _MID_LANDING_X0) / 2.0, _WELL_Y,
            (FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT) / 2.0),
    "size": (_MID_LANDING_X0 - _FLOOR_LANDING_X1, WELL_WALL_THICK,
             FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT),
}]

# ⭐ 护栏一律做**实心矮墙**（栏板），不是两根横杆：① 机器人会从杆缝里钻/卡；
#    ② 自检只能横着打射线找实体，细杆要求射线高度正好对上杆心 = 把检查绑死在造型上。
GUARD_HEIGHT = 1.05        # 规范：临空处栏板净高 ≥1.05
GUARD_THICK = WELL_WALL_THICK

# 顶层梯口护栏：上层的楼层平台到此为止，**上行跑那条道**往东就是直通下层的洞。
# ⛔ 它只封「平台东缘 × 上行车道」这一小段，**绝不能顺着整跑铺过去**：
#    铺过去就等于在上行跑正上方架了一道 1.05 m 高的墙，`check_headroom` 立刻红
#    （实测第 11 级头顶只剩 2.01 m < 2.20）。第一版就是这么写的。
# ⚠️ 回头跑那条道（_DN_Y）**不许封**——人正是从那儿走上来的。
GUARDS.append({
    "name": "stair_top_guard",
    "pos": (_FLOOR_LANDING_X1 + GUARD_THICK / 2.0, _UP_Y,
            FLOOR_Z(1) + GUARD_HEIGHT / 2.0),
    "size": (GUARD_THICK, STEP_WIDTH, GUARD_HEIGHT),
})
# ⭐ 挑空环廊的临空边：这是双高客厅那个"井"的护栏，掉下去就是 3.75 m
GUARDS.append({
    "name": "mezz_void_guard",
    "pos": ((XA + XB) / 2.0, Y2 + MEZZ_WALK_D - GUARD_THICK / 2.0,
            FLOOR_Z(1) + GUARD_HEIGHT / 2.0),
    "size": (XB - XA, GUARD_THICK, GUARD_HEIGHT),
})

# ── 四个接头的自检（几何一算就知道）─────────────────────────────────
_last_tread_top = TREADS_PER_FLIGHT * STEP_RISE
assert abs((_HALF_STOREY - _last_tread_top) - STEP_RISE) < 1e-9, \
    "上行跑顶端到中间平台不是一个踢面 —— 楼梯断了"
assert abs((STOREY_H - (_HALF_STOREY + _last_tread_top)) - STEP_RISE) < 1e-9, \
    "回头跑顶端到上一层楼面不是一个踢面 —— 楼梯断了"

# ────────────────────────────────────────────────────────── 家具
_LINEN = (0.82, 0.80, 0.76, 1.0)
_WOOD = (0.48, 0.36, 0.26, 1.0)

FURNITURE: list[dict] = []

# ═══ 双高大客厅：⭐ 本场景的主角——一张 G1 真坐得下的沙发 ═══
# 座面 0.35（实测上限），朝北（+y）对着中央公园。⛔ 别抬高，见 furniture.sofa 的注释。
# ⚠️ yaw=90 之后局部轴换了向：`width`（2.40）沿 **x**、进深沿 **y**。
#    第一版就是按局部轴摆的，结果沙发和茶几插在一起 35 cm。
GR_SOFA_XY = (2.50, 3.20)
FURNITURE += F.sofa("gr_sofa", "great_room", *GR_SOFA_XY, yaw=90.0,
                    width=2.40, rgba=_LINEN, mat="mat_h3_linen")
# 茶几：⭐ 上真碰撞——底下要能穿过去
FURNITURE += F.mesh_piece("gr_coffee", "great_room", 2.50, 4.50,
                          size=(1.30, 1.30, 0.49), mesh="coffee_table", collide=True)
# 两把单椅摆在窗前、隔着茶几与沙发对坐：⭐ 也上真碰撞
# ⚠️ **别放在 x=XA / x=XB 附近**：那两条线上各有一个通往餐厅/图书室的洞口，
#    `check_door_passable` 要求洞口内侧 0.6 m 里净通行宽 ≥0.60 m，
#    单椅往那儿一摆只剩 0.49 m，当场红（第一版就是这么摆的）。
FURNITURE += F.mesh_piece("gr_ch1", "great_room", 1.30, 6.30,
                          size=(0.82, 0.99, 1.02), mesh="armchair", yaw=180.0,
                          collide=True)
FURNITURE += F.mesh_piece("gr_ch2", "great_room", 3.70, 6.30,
                          size=(0.82, 0.99, 1.02), mesh="armchair", yaw=0.0,
                          collide=True)
FURNITURE += F.potted_plant("gr_plant", "great_room", 5.00, 7.00)

# ═══ 餐厅：长桌 + 6 把真碰撞餐椅 ═══
_DN_CX, _DN_CY = -2.80, 4.60
FURNITURE += F.table("dn_table", "dining", _DN_CX, _DN_CY, 1.10, 2.40, h=0.75,
                     rgba=_WOOD, mat="mat_h3_oak_dark")
# ⚠️ 餐椅网格的靠背在局部 +y（实测俯视高度图：座面在 y∈[−26,0] cm、靠背在 y∈[+13,+26] cm），
#    所以它**朝 −y 坐**。要让西侧那排面朝 +x（对着桌子），得 yaw=+90；东侧那排 yaw=−90。
DN_CHAIR_SIZE = (0.434, 0.576, 0.973)
for _i, _dy in enumerate((-0.80, 0.0, 0.80)):
    FURNITURE += F.mesh_piece(f"dn_w{_i}", "dining", _DN_CX - 0.86, _DN_CY + _dy,
                              size=DN_CHAIR_SIZE, mesh="dining_chair",
                              yaw=90.0, collide=True)
    FURNITURE += F.mesh_piece(f"dn_e{_i}", "dining", _DN_CX + 0.86, _DN_CY + _dy,
                              size=DN_CHAIR_SIZE, mesh="dining_chair",
                              yaw=-90.0, collide=True)

# ═══ 厨房 ═══
FURNITURE += [
    F._p("kt_island", "kitchen", "box", (-8.40, 4.20, 0.46), (2.60, 1.10, 0.92),
         _F_STONE, mat="mat_h3_marble"),
    F._p("kt_run", "kitchen", "box", (-8.40, 7.00, 0.46), (5.20, 0.65, 0.92),
         _F_STONE, mat="mat_h3_marble"),
]
FURNITURE += F.stool("kt_st0", "kitchen", -9.20, 3.30, h=0.68)
FURNITURE += F.stool("kt_st1", "kitchen", -7.60, 3.30, h=0.68)

# ═══ 图书室 / 东过厅 / 影音室 ═══
FURNITURE += [
    F._p("lb_shelf", "library", "box", (10.90, 4.40, 1.10), (0.42, 4.20, 2.20),
         _WOOD, mat="mat_h3_oak_dark"),
    F._p("md_screen", "media", "box", (11.10, -4.40, 1.30), (0.14, 2.60, 1.50),
         (0.10, 0.10, 0.11, 1.0)),
]
FURNITURE += F.sofa("md_sofa", "media", 8.40, -4.40, yaw=0.0, width=2.00,
                    rgba=(0.32, 0.31, 0.33, 1.0))

# ═══ 客卧（62 层）/ 主卧（63 层）═══
FURNITURE += [
    F._p("gb_bed", "guest_bed", "box", (-8.60, -5.20, 0.28), (1.60, 2.05, 0.56),
         _LINEN, mat="mat_h3_linen"),
    F._p("pb_bed", "primary_bed", "box", (-8.60, 4.60, 0.30), (1.90, 2.15, 0.60),
         _LINEN, mat="mat_h3_linen"),
]

# ═══ 书房 / 家庭厅（63 层）═══
FURNITURE += F.table("st_desk", "study", -2.80, 5.60, 1.60, 0.75, h=0.75,
                     rgba=_WOOD, mat="mat_h3_oak_dark")
FURNITURE += F.mesh_piece("st_chair", "study", -2.80, 4.60,
                          size=(0.434, 0.576, 0.973), mesh="dining_chair",
                          yaw=90.0, collide=True)
FURNITURE += F.sofa("fm_sofa", "family", 4.00, -5.60, yaw=90.0, width=2.00,
                    rgba=_LINEN, mat="mat_h3_linen")

# ────────────────────────────────────────────────────────── 能坐的家具
# ⭐ 给 `check_seat_reachable` 用：这几件声明"能坐"，自检就**用射线去量**
#    座面高度和上方净空，不看任何声明数字。
# ⚠️ `under_clear` 只给"要把脚往里收"的餐椅开；沙发整体软包到地是合法做法，别开。
# ⛔⛔ `at` / `span` 描述的是**座垫那一小块**，而且是**世界轴**的尺寸，不是家具局部轴。
#    自检在这块区域里取**最高**的实体面当座面高——区域一旦盖到靠背，量到的就是靠背顶
#    （第一版沙发因此报 90 cm = 座面 0.35 + 靠背 0.55，直接判红）。
#    ⚠️ yaw=90 的沙发：`width` 沿 x、进深沿 y，所以 span 也要跟着换过来。
SEATS: list[dict] = [
    {"name": "gr_sofa", "room": "great_room", "at": GR_SOFA_XY, "span": (1.60, 0.24)},
    {"name": "md_sofa", "room": "media", "at": (8.40, -4.40), "span": (0.24, 1.40)},
    {"name": "fm_sofa", "room": "family", "at": (4.00, -5.60), "span": (1.40, 0.24)},
]

# ⭐⭐ 为什么名单里**只有沙发** —— 这是量出来的结论，不是漏写：
#
#     沙发 gr_sofa / md_sofa 座面   35.0 cm（手写基本体，按 G1 腿长定的）✅
#     Poly Haven 餐椅 座面          42.3 – 46.1 cm    ❌ 超 G1 上限 0.36
#     Poly Haven 单椅 座面          53.0 – 70.9 cm    ❌ 超得更多
#
# ⇒ **市面上的真家具是给人用的，对 1.32 m 高的 G1 全都太高。**
#    实测坐姿保持 3 秒：0.40 m 就滑落、0.45 m 直接倒——42 cm 和 55 cm 都在失败带里。
# ⛔ 别为了让它们"能坐"去缩放资产：`_fit_scale` 是**均匀缩放**，把座面压到 0.35
#    会连着把整把椅子缩成玩具尺寸，摆在人尺度的餐桌旁边一眼就露馅。
# ⭐ 这正是 `furniture.sofa()` 用手写基本体的理由：**尺寸由机器人定的那件家具，
#    就不该让资产来定它的尺寸**。餐椅和单椅照旧是给"人"用的陈设（也照旧有真碰撞，
#    机器人撞得到、脚伸得进椅子腿之间），只是不进"能坐"名单。

# ────────────────────────────────────────────────────────── 坐姿
# ⭐ 按**关节名**声明，不按下标 —— 换机器人时对不上的名字会被安静跳过，
#    而下标会静默错位。装配与沉降走 `scenes/apply_pose.py`（那里写了为什么）。
# ⚠️ 这组角度是量出来的：髋 −1.57 / 膝 +1.57 / 踝 0 让大腿正好水平、小腿正好竖直
#    （实测膝与髋同高、踝在膝正下方，误差 0.000 m）。
# ⚠️ `base_xyz` 的 z = 座面 0.35 + 骨盆半厚 ≈ 0.104。这是**入场姿态**，不是稳态——
#    推 3 秒物理后机器人会往靠背里靠、骨盆再抬 4.6 cm。出图和自检都要先 settle。
_SIT_JOINTS = {
    "left_hip_pitch_joint": -1.57, "right_hip_pitch_joint": -1.57,
    "left_knee_joint": 1.57, "right_knee_joint": 1.57,
    "left_ankle_pitch_joint": 0.0, "right_ankle_pitch_joint": 0.0,
    "left_shoulder_pitch_joint": 0.22, "right_shoulder_pitch_joint": 0.22,
    "left_elbow_joint": 0.55, "right_elbow_joint": 0.55,
}
SIT_POSES: dict[str, dict] = {
    "gr_sofa": {
        "seat": "gr_sofa", "room": "great_room",
        "base_xyz": (GR_SOFA_XY[0], GR_SOFA_XY[1], F.SOFA_SEAT_H + 0.104),
        "base_yaw": math.pi / 2,          # 朝北，看中央公园
        "joints": _SIT_JOINTS,
    },
}

WALL_ARTS: list[dict] = []

# ────────────────────────────────────────────────────────── 窗外（借 apt1）
# ⛔ 一律**只读引用**，绝不重跑 make_view.py --nyc（见文件抬头）
SKYBOX = dict(_A1.SKYBOX)
TEXTURES_EXTRA = list(_A1.TEXTURES_EXTRA)
MATERIALS_EXTRA = list(_A1.MATERIALS_EXTRA)
GROUND_SLABS = list(_A1.GROUND_SLABS)
SKYLINE = list(_A1.SKYLINE)
PARK_NEAR_Y, PARK_W, PARK_L, CITY_SPAN = _A1.PARK_NEAR_Y, _A1.PARK_W, _A1.PARK_L, _A1.CITY_SPAN

# 本楼的外皮：apt1 那两件照搬，另加两圈**环形**的立面构件。
#
# ⛔⛔ 这两圈必须是「四条边框」，**绝不能做成一整块板**（第一版就是这么错的）。
#    一块 23×15 的实心板横在 z=3.60–3.75，会同时干掉两样东西：
#      ① `check_route`：楼梯上方往下打的射线**先打到板底**，第 9 级的"地面"从 3.28 变成 3.60，
#         报"有一步要抬 0.319 m"——而 0.319 = 3.60 − 3.28125，正是板底减踏面；
#      ② `check_headroom`：回头跑第 11 级头顶只剩 0.14 m。
#    ⭐ 一个错、两处红，而且报出来的症状（"楼梯断了"）离真因（"外墙装饰板"）很远。
# ⭐ 做成环、且**摆在外轮廓之外**（像 apt1 的 `host_ledge` 那样往外挑），
#    就永远不会伸进任何房间或梯井。
_TOP_Z = FLOOR_Z(1) + WALL_HEIGHT
_ENV_X, _ENV_Y = 23.0, 15.0          # 外轮廓（= X4−X0 / Y3−Y0，和 apt1 逐位相同）
_BAND_T = 0.20                       # 环形构件往外挑出多少


def _facade_ring(name: str, z_center: float, height: float) -> list[dict]:
    """沿外轮廓**外侧**做一圈边框（南/北/东/西四条），中间留空。"""
    hx, hy, t = _ENV_X / 2.0, _ENV_Y / 2.0, _BAND_T
    return [
        {"name": f"{name}_n", "pos": (0.0, hy + t / 2, z_center),
         "size": (_ENV_X + 2 * t, t, height), "mat": "mat_h3_facade"},
        {"name": f"{name}_s", "pos": (0.0, -hy - t / 2, z_center),
         "size": (_ENV_X + 2 * t, t, height), "mat": "mat_h3_facade"},
        {"name": f"{name}_e", "pos": (hx + t / 2, 0.0, z_center),
         "size": (t, _ENV_Y, height), "mat": "mat_h3_facade"},
        {"name": f"{name}_w", "pos": (-hx - t / 2, 0.0, z_center),
         "size": (t, _ENV_Y, height), "mat": "mat_h3_facade"},
    ]


HOST_TOWER = (
    list(_A1.HOST_TOWER)
    # 62/63 之间的层间实腹带：两层玻璃之间那道楼板边
    + _facade_ring("host_spandrel", (WALL_HEIGHT + STOREY_H) / 2.0, STOREY_H - WALL_HEIGHT)
    # 女儿墙：屋顶那一圈
    + _facade_ring("host_parapet", _TOP_Z + 0.30, 0.60)
)

# 旧屋外契约：⛔ 不是忘了填 —— 窗景走上面那四层，这几个名字留着只因契约要求它们存在
CITY_BACKDROP: dict = {}
OUTDOOR_GROUND: dict = {}
TREES: list = []
BUILDINGS: list = []
TRUNK_RGBA = (0.0, 0.0, 0.0, 0.0)
FOLIAGE_RGBA = (0.0, 0.0, 0.0, 0.0)

# ────────────────────────────────────────────────────────── 灯光
# ⛔⛔ **最多 7 盏**：`check_lights_render` 判的是 场景灯 + 机器人自带 1 盏 ≤ 8
#    （MuJoCo 渲染器上限）。超了的**静默不亮**，不报错、图上也看不出少了哪盏。
#    ⚠️ apt1 现在就是红的（声明了 10 盏）——⛔ 别把它那份抄过来。
LIGHT_BUDGET = 7
LIGHT0_IS_ROBOT_LIGHT = True
LIGHTS: list[dict] = [
    {"name": "sun_sw", "pos": "-26 -30 30", "dir": "0.50 0.58 -0.65", "directional": "true",
     "diffuse": "0.52 0.50 0.46", "specular": "0.10 0.10 0.10", "castshadow": "true"},
    {"name": "sky_park_w", "pos": "-6.0 6.9 3.0", "dir": "0.10 -0.80 -0.59",
     "diffuse": "0.78 0.82 0.88", "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": 88, "attenuation": "0.40 0.03 0.004"},
    {"name": "sky_park_e", "pos": "6.0 6.9 3.0", "dir": "-0.10 -0.80 -0.59",
     "diffuse": "0.78 0.82 0.88", "specular": "0.03 0.03 0.03", "castshadow": "false",
     "cutoff": 88, "attenuation": "0.40 0.03 0.004"},
    # ⭐ 双高中庭顶光：全场唯一照得亮那 7.35 m 挑空的一盏，挂在 63 层标高往下打
    {"name": "gr_void", "pos": f"{ENFILADE_X} 5.2 {FLOOR_Z(1) + 3.2:.2f}", "dir": "0 -0.15 -0.99",
     "diffuse": "0.62 0.60 0.56", "specular": "0.05 0.05 0.05", "castshadow": "false",
     "cutoff": 80, "attenuation": "0.50 0.05 0.006"},
    {"name": "amb_gallery", "pos": "1.0 0.0 3.3", "dir": "0 0 -1",
     "diffuse": "0.42 0.41 0.39", "specular": "0.02 0.02 0.02", "castshadow": "false",
     "cutoff": 85, "attenuation": "0.60 0.06 0.008"},
    {"name": "amb_upper", "pos": f"1.0 0.0 {FLOOR_Z(1) + 3.3:.2f}", "dir": "0 0 -1",
     "diffuse": "0.42 0.41 0.39", "specular": "0.02 0.02 0.02", "castshadow": "false",
     "cutoff": 85, "attenuation": "0.60 0.06 0.008"},
    {"name": "amb_stair", "pos": f"-8.4 0.0 {FLOOR_Z(1) + 3.2:.2f}", "dir": "0 0 -1",
     "diffuse": "0.46 0.45 0.43", "specular": "0.02 0.02 0.02", "castshadow": "false",
     "cutoff": 85, "attenuation": "0.50 0.05 0.006"},
]
assert len(LIGHTS) <= LIGHT_BUDGET, f"声明了 {len(LIGHTS)} 盏灯，超过 {LIGHT_BUDGET}"

STATISTIC = {"center": "0 0 2.0", "extent": 8}
VISUAL = dict(_A1.VISUAL)

# ────────────────────────────────────────────────────────── 出生点
# ⭐ 玄关，正对贯通轴线朝北（走进去就是画廊 → 双高大客厅 → 中央公园）
START_POS_XY = (4.0, -6.6)
START_YAW = math.pi / 2
# 机器人自己的位置：画廊东段，离楼梯口和大客厅都近
ROBOT_HOME_XY = (3.0, 0.0)
ROBOT_HOME_YAW = math.pi / 2
ROBOT_HOME_FLOOR = 0

# ────────────────────────────────────────────────────────── 房间归属判定
_FLOOR_EPS = 0.30   # 站在楼梯上时，用脚下略微下探的容差判楼层


def floor_at(z: float) -> int:
    """世界高度 z 落在第几层。楼梯中途按**已经踏上的那一层**算。"""
    n = int((z + _FLOOR_EPS) // STOREY_H)
    return max(0, min(N_FLOORS - 1, n))


def room_at(x: float, y: float, z: float | None = None) -> str | None:
    """(x, y[, z]) 在哪间屋。

    ⚠️ 多层场景**必须给 z**：两层的平面轮廓是重叠的，只给 (x, y) 分不出
    "62 层餐厅"和"63 层书房"。不给 z 时按 0 层算——宁可答错成底层，也不猜。
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
    return "屋外" if key is None else ROOMS[key]["label"]


# ──────────────────────────────────────────────── 楼梯路线（唯一权威描述）
def stair_route(floor: int) -> list[tuple[float, float, float]]:
    """从第 `floor` 层走到第 `floor+1` 层的完整路线（世界坐标折线的拐点）。

    ⭐ 这是"楼梯到底连不连"的唯一权威描述：`check_scene.py` 沿着它逐点往下打射线，
    要求一路有实地、相邻高差不超过一个踢面。**⛔ 别在别处再写一份**——
    house2 上一版的 bug 正是"平台在一处、回头跑起点在另一处"，两处各写各的没人对得上。
    """
    base = FLOOR_Z(floor)
    return [
        (_IN_X0 + 0.25, _UP_Y, base),                              # ① 楼层平台，正对上行跑
        (_FLOOR_LANDING_X1, _UP_Y, base),                          # ② 上行跑起步线
        (_MID_LANDING_X0, _UP_Y, base + _HALF_STOREY),             # ③ 爬到中间平台西缘
        (_IN_X1 - 0.55, _UP_Y, base + _HALF_STOREY),               # ④ 在平台上横移换道
        (_IN_X1 - 0.55, _DN_Y, base + _HALF_STOREY),
        (_MID_LANDING_X0, _DN_Y, base + _HALF_STOREY),             # ⑤ 回头跑起步线
        (_FLOOR_LANDING_X1, _DN_Y, base + STOREY_H),               # ⑥ 爬到上一层平台
        (_IN_X0 + 0.35, _DN_Y, base + STOREY_H),                   # ⑦ 走到门口那一侧
    ]


STAIR_SLOPE_DEG = math.degrees(math.atan2(STEP_RISE, STEP_RUN))
