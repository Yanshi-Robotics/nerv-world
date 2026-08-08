#!/usr/bin/env python3
"""场景自检 —— 生成之后、用之前跑一遍。

    python check_scene.py                 # 检查全部已登记场景
    python check_scene.py --scene house2

**为什么要有它**：这个仓和它的前身都没有任何自动检查，全靠人看截图。
结果是同一类错误反复出现，而且都是"看起来没问题"的那种：

- 前作那栋两层小楼，层高与楼梯各自定死，**顶步悬空 20 cm**——直到用滚球做物理验证
  才发现。这里第 3 项检查用算术直接判死。
- 目录一动，`make_docs_images.py` 的相对路径失效，配图写到仓库外面，
  脚本照常打印「完成」（本仓 2026-07-26 踩过）。**"脚本没报错"不等于"产物到位"。**
- 生成器对 layout 有一份**隐式契约**（要 DOOR_FRAME_RGBA、FRONT_DOOR 之类），
  从没写在任何地方；写 house2 时是靠一个个 AttributeError 撞出来的。
  第 1 项检查把这份契约变成显式的。
- ⛔ **2026-08-02 最贵的一次**：house2 的回头跑起点写在了楼梯井北墙根而不是
  中间平台的南缘，于是两跑根本没接上（从平台看过去是一排凌空的板子）。
  **当时七项检查全绿**——因为它们只沿**单独一跑**往下打射线，绕着走确实摸得到
  一条路。查"存在一条路径"证明不了"这是一部楼梯"。`check_route` 与 `check_joints`
  就是补这个洞的：一个走完整条路线，一个逐个核接头。

- ⛔ **2026-08-07 最贵的一次**：真家具网格被系统性缩小 1.0–4.2 倍（床成了 0.56×0.68×0.26 m
  的玩具床，还悬空 29 cm），而**当时全部自检都是绿的**。根因是 `decor/calibrate.py` 漏转了
  一次旋转、摆位又多加了一份重心——两处都**编译不报错、渲染看着也正常**。
  它能活一整版，是因为 `decor.lock.json` 里同一个尺寸存了两份（整件 `size` 与各部件
  `offset±half`），而**从来没有一道闸门逼这两份对账**。`check_lock_reconciles` 就是补这个洞的。
  同轮还发现：`check_decor_ray_invariance` 打的全是**水平**射线，网格往地板里钻它一条都测不出来
  （`check_decor_inside_box` 补这个洞）；以及没有任何一项拿**门**和**家具**对过账，
  于是"柜子沿墙一拉到底、正好压死那面墙上的门"这种错在三个场景里躺了很久
  （`check_door_passable` 补这个洞）。
  **教训：一个量在两个地方各存了一份，就必须有闸门逼它们对账；没对账的冗余不是冗余，是雷。**

**检查项的权威清单是文件末尾的 `CHECKS`，别在这里再抄一份，也别在这里写项数**——
抄两份必然对不上（这段注释在 0.8 那一版就一直写着"8 项"而实际有 16 项）。
任一不过 → 退出码 1。

⛔ **新加一项检查时的规矩：必须做故障注入验证**——把它该抓的那个 bug 注回去，
它得**当场变红**；拔掉之后回绿。抓不到旧 bug 的新检查等于没加。
"""
from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from scenes import manifest as SCENES  # noqa: E402

# 生成器会读的 layout 顶层名字。少一个就是运行到一半炸，而不是启动时说清楚。
REQUIRED_NAMES = [
    "WALL_HEIGHT", "WALL_THICK", "DOOR_HEIGHT", "FLOOR_THICK", "CEILING_THICK",
    "CEILING_GROUP", "CEILING_RGBA", "WINDOW_SILL_H", "WINDOW_TOP_H",
    "DOOR_FRAME_THICK", "DOOR_FRAME_RGBA", "WINDOW_FRAME_T", "WINDOW_FRAME_RGBA",
    "ART_FRAME_T", "ART_FRAME_RGBA", "FRONT_DOOR", "FRONT_DOOR_HANDLE",
    "ROOMS", "DOORS", "WINDOWS", "FURNITURE", "WALL_ARTS",
    "START_POS_XY", "START_YAW",
    "CITY_BACKDROP", "OUTDOOR_GROUND", "TRUNK_RGBA", "FOLIAGE_RGBA", "TREES", "BUILDINGS",
    "room_at", "room_label",
]

# 多层场景额外要有的。`stair_route` 在里面是有意的：楼梯到底怎么走，
# 必须由 layout 给出**唯一**一份权威描述，检查照着它走。两处各写一份就是上次
# 那个 bug 的温床（平台在一处、回头跑起点在另一处，谁也没跟谁对过）。
MULTIFLOOR_NAMES = ["FLOOR_Z", "STOREY_H", "N_FLOORS", "STEP_RISE", "STEP_RUN",
                    "STAIRS", "LANDINGS", "stair_route"]

# 机器人的通行尺寸。⚠️ 不是从 robots/manifest.py 读的：那里是资产事实
# （模型在哪、出生多高），不含"这台机器人多宽、脚多长"。这两个数只在这里用来做
# 通行性判断，所以就地具名 + 写清出处，而不是散在检查代码里当魔法数。
ROBOT_CLEARANCE = {
    # key: (通行宽度 m, 脚长 m, 出处)
    "g1": (0.60, 0.25, "宇树 G1 肩宽约 0.45 m，走动时手臂摆动取 0.60；脚长实测约 0.25"),
    "go2": (0.40, 0.10, "宇树 Go2 机身宽约 0.31 m，取 0.40 留余量；足端接近点接触"),
}

MIN_TREAD_MARGIN = 0.03     # 踏面至少比脚长多这么多，否则盲走一偏就踩空
MAX_STAIR_SLOPE_DEG = 38.0  # 超过这个坡度人形基本上不去（住宅规范上限约 33–38°）

# ── 《住宅设计规范》GB 50096-2011 §6.3 的硬指标 ───────────────────────────
# 写在这里而不是散在检查里：它们是**外部依据**，改动必须有出处。
CODE_MAX_RISE = 0.175       # 踏步高度不应大于 0.175 m
CODE_MIN_RUN = 0.26         # 踏步宽度不应小于 0.26 m
CODE_MIN_FLIGHT_W = 1.10    # 梯段净宽不应小于 1.10 m
CODE_MIN_LANDING = 1.20     # 平台净宽不应小于梯段净宽，且不得小于 1.20 m
MIN_HEADROOM_M = 2.20       # 梯段净高不宜小于 2.20 m（平台下为 2.00，这里从严取梯段值）

# 一个踢面的浮点容差：几何全是 0.16 这类有限小数，1e-6 足够，同时能抓住真错位
EPS = 1e-6


def _fail(msgs: list[str], text: str) -> None:
    msgs.append(text)


def check_contract(key: str, layout) -> list[str]:
    errs: list[str] = []
    for name in REQUIRED_NAMES:
        if not hasattr(layout, name):
            _fail(errs, f"layout 缺少 `{name}` —— 生成器会读它")
    floors = {r.get("floor", 0) for r in getattr(layout, "ROOMS", {}).values()}
    if len(floors) > 1:
        for name in MULTIFLOOR_NAMES:
            if not hasattr(layout, name):
                _fail(errs, f"多层场景缺少 `{name}`")
    return errs


def check_loads(key: str, layout) -> list[str]:
    """产物能不能被 MuJoCo 真正编译 —— 不是"文件存在"。"""
    try:
        import mujoco
    except ImportError:
        return ["(跳过) 没装 mujoco，无法验证产物能否加载"]
    errs: list[str] = []
    for robot in ROBOT_CLEARANCE:
        path = os.path.join(HERE, SCENES.scene_filename(key, robot))
        if not os.path.exists(path):
            _fail(errs, f"产物不存在：{os.path.basename(path)}（跑 make_house.py --scene {key}）")
            continue
        try:
            mujoco.MjModel.from_xml_path(path)
        except Exception as exc:  # noqa: BLE001 - 报告任何编译失败
            _fail(errs, f"{os.path.basename(path)} 无法被 MuJoCo 加载：{exc}")
    return errs


def check_stairs(key: str, layout) -> list[str]:
    """⭐ 顶步悬空防线 + 规范尺寸复核。

    "每组楼梯正好爬满一层"必须是**算出来**的：前作那栋两层小楼把层高和楼梯各自定死，
    顶步悬空 20 cm，直到滚球验证才发现。
    """
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
        return []
    errs: list[str] = []
    rise, run = layout.STEP_RISE, layout.STEP_RUN
    storey = layout.STOREY_H

    # 按起点高度分组：同一层的两跑加起来应等于层高。
    # ⚠️ 用 `risers`（踢面数）而不是踏板数——爬升是踢面攒出来的，
    #    最上面那一级由平台充当，它照样贡献一个踢面的高度。
    climbed: dict[float, float] = {}
    for flight in stairs:
        base = round(flight["base_z"], 6)
        climbed[base] = climbed.get(base, 0.0) + flight["risers"] * rise

    for floor in range(layout.N_FLOORS - 1):
        z0 = round(layout.FLOOR_Z(floor), 6)
        total = sum(v for b, v in climbed.items()
                    if z0 - EPS <= b < z0 + storey - EPS)
        if abs(total - storey) > 1e-3:
            _fail(errs, f"{floor}→{floor + 1} 层楼梯爬升 {total:.4f} m ≠ 层高 {storey:.4f} m "
                        f"（差 {total - storey:+.4f} m）—— 顶步悬空/顶到天花板")

    slope = math.degrees(math.atan2(rise, run))
    if slope > MAX_STAIR_SLOPE_DEG:
        _fail(errs, f"坡度 {slope:.1f}° 超过 {MAX_STAIR_SLOPE_DEG}°，人形基本上不去")

    foot = max(f for _w, f, _n in ROBOT_CLEARANCE.values())
    if run < foot + MIN_TREAD_MARGIN:
        _fail(errs, f"踏面 {run:.3f} m 对最长的脚（{foot:.2f} m）只剩 "
                    f"{run - foot:.3f} m 余量，低于 {MIN_TREAD_MARGIN} m")

    # ── 规范复核（GB 50096-2011 §6.3）──
    if rise > CODE_MAX_RISE + EPS:
        _fail(errs, f"踢面 {rise:.3f} m > 规范上限 {CODE_MAX_RISE} m")
    if run < CODE_MIN_RUN - EPS:
        _fail(errs, f"踏面 {run:.3f} m < 规范下限 {CODE_MIN_RUN} m")
    widths = {f["width"] for f in stairs}
    for w in widths:
        if w < CODE_MIN_FLIGHT_W - EPS:
            _fail(errs, f"梯段净宽 {w:.2f} m < 规范下限 {CODE_MIN_FLIGHT_W} m")
    depth = getattr(layout, "LANDING_DEPTH", None)
    if depth is not None:
        need = max(max(widths), CODE_MIN_LANDING)
        if depth < need - EPS:
            _fail(errs, f"平台进深 {depth:.2f} m < 需要的 {need:.2f} m"
                        f"（规范：不小于梯段净宽，且不小于 {CODE_MIN_LANDING} m）")
    return errs


def check_joints(key: str, layout) -> list[str]:
    """⭐⭐ 四个接头逐个核 —— **这一项是 2026-08-02 那个 bug 的直接防线**。

    一部双跑楼梯 = 楼层平台 → 上行跑 → 中间平台 → 回头跑 → 上一层楼层平台。
    判断"接没接上"只看一条：**上一段的最后一块踏板，和下一段的起始平台，
    平面上首尾相接、高度上正好差一个踢面。**

    当时的错法是把回头跑的起点放在楼梯井北墙根（而不是中间平台的南缘），
    于是回头跑既不挨着平台、中段还悬在上行跑头顶。这一项用几何直接判死，
    连 MuJoCo 都不用起。
    """
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
        return []
    errs: list[str] = []
    rise, run = layout.STEP_RISE, layout.STEP_RUN
    landings = {lg["name"]: lg for lg in getattr(layout, "LANDINGS", [])}

    def plane_gap(a0: float, a1: float, b0: float, b1: float) -> float:
        """两段区间在同一根轴上的缝隙（重叠算 0）。"""
        return max(0.0, max(a0, b0) - min(a1, b1))

    for flight in stairs:
        n = flight["risers"] - 1                 # 实体踏板数
        sx, sy = flight["start_xy"]
        dx, dy = flight["dir"]
        # 这一跑最后一块踏板的顶面高度与它的远端坐标
        top_tread_z = flight["base_z"] + n * rise
        far = (sy + dy * n * run) if dy else (sx + dx * n * run)
        # 它上面应该接的那块平台：高度 = base + risers × 踢面
        want_z = flight["base_z"] + flight["risers"] * rise
        across = sx if dy else sy                # 这一跑所在的那条道（另一根轴上的坐标）

        # 候选 = 标高对得上、且横向盖得住这一跑的所有平面。挑缝隙最小的那个来报，
        # 免得同层别的房间抢先匹配、报出一个牛头不对马嘴的"缝 1.54 m"。
        cands: list[tuple[float, str, float, float, float]] = []
        for lg in landings.values():             # ③ 中间平台
            z_top = lg["pos"][2] + lg["size"][2] / 2.0
            if abs(z_top - want_z) > EPS:
                continue
            ai, bi = (1, 0) if dy else (0, 1)
            lo, hi = lg["pos"][ai] - lg["size"][ai] / 2.0, lg["pos"][ai] + lg["size"][ai] / 2.0
            o0, o1 = lg["pos"][bi] - lg["size"][bi] / 2.0, lg["pos"][bi] + lg["size"][bi] / 2.0
            if o0 - EPS <= across <= o1 + EPS:
                cands.append((plane_gap(far, far, lo, hi), "平台 " + lg["name"], z_top, lo, hi))
        for rkey, room in layout.ROOMS.items():  # ①⑤ 楼层平台（局部楼板）
            if abs(layout.FLOOR_Z(room.get("floor", 0)) - want_z) > EPS:
                continue
            for rect in (room.get("floor_rects") or [room["rect"]]):
                lo, hi = (rect[1], rect[3]) if dy else (rect[0], rect[2])
                o0, o1 = (rect[0], rect[2]) if dy else (rect[1], rect[3])
                if o0 - EPS <= across <= o1 + EPS:
                    cands.append((plane_gap(far, far, lo, hi),
                                  f"楼层平台 {rkey}", want_z, lo, hi))
        if not cands:
            _fail(errs, f"{flight['name']}：顶上找不到标高 {want_z:.3f} m、"
                        f"又盖得住这条道的平台 —— 这一跑走完没有落脚点")
            continue
        gap, name, z_top, lo, hi = min(cands)
        if gap > EPS:
            _fail(errs, f"{flight['name']} → {name}：末级远端在 {far:.3f}，"
                        f"平台却从 {lo:.3f} 才开始（缝 {gap:.3f} m）—— **两段没接上**")
        if abs((z_top - top_tread_z) - rise) > EPS:
            _fail(errs, f"{flight['name']} → {name}：末级踏面 {top_tread_z:.3f} m 到平台 "
                        f"{z_top:.3f} m 差 {z_top - top_tread_z:+.3f} m，应正好一个踢面 {rise}")
    return errs


def check_doors(key: str, layout) -> list[str]:
    errs: list[str] = []
    need = max(w for w, _f, _n in ROBOT_CLEARANCE.values())
    for door in layout.DOORS:
        if door["width"] < need:
            _fail(errs, f"门 {door.get('note', '?')} 净宽 {door['width']:.2f} m "
                        f"< 需要的 {need:.2f} m")
    return errs


# 门洞前后必须留出的净空进深。0.60 m ≈ 一个身位，够机器人转身进门。
DOOR_CLEAR_M = 0.60
# 比这矮的东西不算挡路：地毯、地垫、门槛。G1 抬脚约 0.25 m。
DOOR_STEPOVER_M = 0.25


def check_door_passable(key: str, layout) -> list[str]:
    """⭐⭐ 门要**真的走得过去**：两侧都得是房间，且门前后 0.6 m 的净通行宽够机器人过。

    ⛔ 为什么单开一项（2026-08-07 在 apt1 抓到的）：`dr_closet_e` 是一只
       0.56 × 3.00 × 2.20 的通柜，沿衣帽间东墙一拉到底，正好把「画廊→衣帽间」那道
       1.2 m 的门**整个封死**——穿过门一步撞进实心柜子，衣帽间/主卧/主卫整个西翼
       从画廊走不进来。当时全部自检都是绿的，因为 `check_doors` 只量门自己的净宽，
       **从没有任何一项拿门和家具对过账**。

    ⚠️ 判据是**净通行宽**，不是"有没有重叠"：真实住宅里家具本来就贴着洞口边站
       （沙发背靠 4 m 的开口是正常设计），按"重叠即红"会得到一堆假阳性。
       这里把门宽这一段沿墙切开，减掉每件挡路家具占的区间，看剩下最宽的一条够不够。
    ⛔ `kind="open"` 的整段拆墙通道不参与——那是"两间屋打通"，不是门。
    """
    errs: list[str] = []
    need = max(w for w, _f, _n in ROBOT_CLEARANCE.values())
    t = layout.WALL_THICK
    rooms = getattr(layout, "ROOMS", {})
    floors = sorted({r.get("floor", 0) for r in rooms.values()})

    def _room_at(x: float, y: float, floor: int):
        for name, r in rooms.items():
            if r.get("floor", 0) != floor:
                continue
            x0, y0, x1, y1 = r["rect"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    # 每层的挡路家具 → 世界 AABB。带 yaw 的按旋转后的外接 AABB 取保守值。
    blockers: dict[int, list] = {f: [] for f in floors}
    for it in layout.FURNITURE:
        if it.get("type") not in ("box", "cylinder"):
            continue
        _px, _py, pz = it["pos"]
        sx, sy, sz = it["size"]
        if pz + sz / 2.0 <= DOOR_STEPOVER_M:
            continue                       # 地毯/地垫这类，跨得过去
        q = it.get("quat")
        if q:
            yaw = 2.0 * math.atan2(q[3], q[0])
            ca, sa = abs(math.cos(yaw)), abs(math.sin(yaw))
            sx, sy = sx * ca + sy * sa, sx * sa + sy * ca
        f = rooms.get(it["room"], {}).get("floor", 0)
        blockers.setdefault(f, []).append(
            (it["name"], it["pos"][0] - sx / 2, it["pos"][0] + sx / 2,
             it["pos"][1] - sy / 2, it["pos"][1] + sy / 2))

    for door in layout.DOORS:
        if door.get("kind") == "open":
            continue
        c, w, co = door["center"], door["width"], door["coord"]
        horiz = door["orient"] == "h"
        note = door.get("note", "?")
        for floor in floors:
            for sgn, lbl in ((-1, "南/西"), (+1, "北/东")):
                px, py = ((c, co + sgn * (t / 2 + 0.30)) if horiz
                          else (co + sgn * (t / 2 + 0.30), c))
                if _room_at(px, py, floor) is None:
                    if floor == floors[0]:
                        _fail(errs, f"门「{note}」{lbl}侧 0.30 m 处 ({px:.2f}, {py:.2f}) "
                                    f"不在任何房间里 —— 这道门通向墙里或屋外")
                    continue
                # 门宽这一段沿墙切开，减掉每件挡路家具占的区间
                lo_b, hi_b = sorted((co + sgn * t / 2, co + sgn * (t / 2 + DOOR_CLEAR_M)))
                free = [(c - w / 2, c + w / 2)]
                hit: list[str] = []
                for nm, x0, x1, y0, y1 in blockers.get(floor, []):
                    across, along = ((y0, y1), (x0, x1)) if horiz else ((x0, x1), (y0, y1))
                    if not (across[0] < hi_b and across[1] > lo_b):
                        continue           # 不在门前那 0.6 m 的进深里
                    nxt = []
                    for f0, f1 in free:
                        for seg in ((f0, min(along[0], f1)), (max(along[1], f0), f1)):
                            if seg[1] - seg[0] > 1e-9:
                                nxt.append(seg)
                    if nxt != free:
                        hit.append(nm)
                    free = nxt
                widest = max((f1 - f0 for f0, f1 in free), default=0.0)
                if widest < need - 1e-9:
                    where = f"（{floor} 层）" if len(floors) > 1 else ""
                    _fail(errs, f"门「{note}」{where}{lbl}侧 {DOOR_CLEAR_M} m 内净通行宽"
                                f"只剩 {widest:.2f} m（要 {need:.2f} m）—— 挡路的是 {hit[:3]}")
    return errs


def _yaw_aabb(it: dict) -> tuple[float, float, float, float]:
    """一件家具的世界 AABB（x0, x1, y0, y1）。带 yaw 的按旋转后的外接框取保守值。"""
    px, py = it["pos"][0], it["pos"][1]
    sx, sy = it["size"][0], it["size"][1]
    q = it.get("quat")
    if q:
        yaw = 2.0 * math.atan2(q[3], q[0])
        ca, sa = abs(math.cos(yaw)), abs(math.sin(yaw))
        sx, sy = sx * ca + sy * sa, sx * sa + sy * ca
    return (px - sx / 2, px + sx / 2, py - sy / 2, py + sy / 2)


def check_furniture_not_through_wall(key: str, layout) -> list[str]:
    """⭐ 家具不许**捅穿墙体伸进隔壁房间**。

    ⚠️ 判据是"穿到墙的另一面"，**不是"碰到墙"**。这个仓的建模惯例就是把柜子、台面
       画到房间矩形边上，让它和墙贴死不留缝——墙从 `rect` 往房间内侧长一个 `WALL_THICK`，
       所以家具伸进墙体那 14 cm 是**有意的**（三个场景合计 56 件这样，碰撞和射线都无害，
       视觉上藏在墙里）。按"碰到墙就红"会把这条惯例判成 56 个 bug。
    ⛔ 真正的缺陷是穿过去：隔壁房间的墙面上会凭空长出半截柜子，
       而且**渲染不报错、射线也照常**——只有走到隔壁抬头看才发现。
       2026-08-07 首次上闸门时抓到 3 件（全在 house1，最深的鞋柜穿出 10 cm）。
    """
    errs: list[str] = []
    t = layout.WALL_THICK
    for it in layout.FURNITURE:
        r = getattr(layout, "ROOMS", {}).get(it["room"])
        if not r:
            continue
        x0, y0, x1, y1 = r["rect"]
        fx0, fx1, fy0, fy1 = _yaw_aabb(it)
        thru = max(x0 - fx0, fx1 - x1, y0 - fy0, fy1 - y1)
        if thru > 1e-3:
            _fail(errs, f"家具 {it['name']}（{it['room']}）捅穿墙体 {thru * 100:.1f} cm "
                        f"伸进隔壁——墙厚只有 {t * 100:.0f} cm，隔壁墙面上会长出半截家具")
    return errs


# layout 里"声明了就该在产物里看得见"的清单：名字 → 产物里对应 geom 名字的前缀。
# ⛔ 为什么要这条检查（2026-08-05 加）：`_wall_arts()` 从写出来那天起就没被 build() 调用过，
#    house1 声明的 11 幅挂画一幅都没进过产物，而**生成器不会报错、截图也看不出少了什么**。
#    这类"声明了但没接线"的腐化，只有拿声明去比产物才抓得到。
#    新增一类会进产物的东西时，在这里登记一行。
DECLARED_TO_GEOM = {
    "FURNITURE": "furn_",
    "WALL_ARTS": "art",
    "TREES": "tree",
    "BUILDINGS": "bldg",
}


def check_wellformed(key: str, layout) -> list[str]:
    """产物是不是合法 XML —— 不需要 mujoco，生成器一坏立刻红。"""
    import xml.etree.ElementTree as ET
    errs: list[str] = []
    for robot in ROBOT_CLEARANCE:
        path = os.path.join(HERE, SCENES.scene_filename(key, robot))
        if not os.path.exists(path):
            continue
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            _fail(errs, f"{os.path.basename(path)} 不是合法 XML：{exc}")
    return errs


def check_assets(key: str, layout) -> list[str]:
    """⭐ 引用的东西必须真的存在 —— 纯 Python，不需要 mujoco。

    ⛔ CHANGELOG [0.6] 记着一个真出过的 bug：材质名 `mat_concrete` 根本不存在。
       那次是靠 MuJoCo 编译报错发现的，但编译要装 mujoco；这条检查不用。
    """
    import xml.etree.ElementTree as ET
    errs: list[str] = []
    for robot in ROBOT_CLEARANCE:
        path = os.path.join(HERE, SCENES.scene_filename(key, robot))
        if not os.path.exists(path):
            continue
        root = ET.parse(path).getroot()
        asset = root.find("asset")
        if asset is None:
            continue
        defined = {m.get("name") for m in asset.findall("material")}
        for geom in root.iter("geom"):
            mat = geom.get("material")
            if mat and mat not in defined:
                _fail(errs, f"{os.path.basename(path)}：geom {geom.get('name')!r} "
                            f"引用了未定义的材质 {mat!r}")
        for tex in asset.findall("texture"):
            for attr, v in tex.items():
                if not attr.startswith("file") or not v:
                    continue
                if not os.path.exists(os.path.join(HERE, v)):
                    _fail(errs, f"{os.path.basename(path)}：贴图文件不存在 {v}")
        # ⛔ 天空盒有且只能有一个：两个是编译错误，零个是一片黑虚空
        skies = [t for t in asset.findall("texture") if t.get("type") == "skybox"]
        if len(skies) != 1:
            _fail(errs, f"{os.path.basename(path)}：天空盒有 {len(skies)} 个，必须正好 1 个")
    return errs


# ⚠️ 不是 0：`size` 取自 fetch 期的 trimesh 对象，`offset/half` 取自落盘后的 OBJ，
#    两者差着导出时的取舍（实测 plant_a 差 3.4 cm）。这是**已知的导出差异**，不是本条要抓的错。
#    5 cm 足够放过它，又远小于真出事时的量级（床差 136 cm、条案差 176 cm）。
LOCK_SPAN_TOL = 0.05

# 同一份 lock 全仓共用，`check_lock_reconciles` 每次运行只跑一次。⛔ 别改回按场景排序判断。
_LOCK_CHECKED = False


def check_lock_reconciles(key: str, layout) -> list[str]:
    """⭐⭐ decor.lock 自洽对账：各部件 `offset ± half` 的并集必须等于整件 `size`。

    ⛔ 为什么必须有它（2026-08-07 血的教训）：`decor/calibrate.py` 曾经只把 `mesh_pos`
       加回顶点、没把 `mesh_quat` 转回来——MuJoCo 编译 `<mesh>` 时不只把顶点平移到重心，
       还会**旋转到惯性主轴系**。于是写进 lock 的 offset/half 是"轴被置换过"的：
       床记成 0.66×2.21×2.15（真值 1.69×2.06×0.78），条案记成 1.31×0.81×2.44
       （真值 2.44×0.52×0.68）。`_fit_scale` 据此把网格缩小了 1.0–4.2 倍——
       **编译不报错、射线自检全绿、渲染看着也正常**，只有把这两个数摆在一起才看得出来。

    ⭐ 这条只查 lock 自己：**不需要 mujoco，也不需要资产字节**，裸 clone 上照样能红。
       同一份 lock 全仓共用，所以**每次运行只跑一次**，免得刷三遍屏。

    ⛔ 这里曾经写的是 `if key != SCENES.keys()[0]: return []`——**拿排序当控制流**，两个毛病：
       ① `keys()` 是 sorted 的，场景一改名首个 key 就换人（apt1→apt1 那次就换了），
          "对账在哪个场景上跑"悄悄挪了地方，没人知道；
       ② `--scene <非首个>` 时它**一次都不跑，屏幕上却显示 ✅**。
       用一个显式的模块级标志表达"每次运行只跑一次"，跟场景排序彻底脱钩。
    """
    global _LOCK_CHECKED
    if _LOCK_CHECKED:
        return []
    _LOCK_CHECKED = True
    try:
        from decor import lock
    except ImportError:
        return ["(跳过) 没有 decor 包"]
    errs: list[str] = []
    for k, rec in sorted(lock.load().items()):
        ps = rec.get("parts") or []
        if not ps or "half" not in ps[0]:
            continue                      # 老 lock 没记部件信息，没什么可对的
        lo = [min(float(p["offset"][j]) - float(p["half"][j]) for p in ps) for j in range(3)]
        hi = [max(float(p["offset"][j]) + float(p["half"][j]) for p in ps) for j in range(3)]
        span = [h - lv for h, lv in zip(hi, lo)]
        want = [float(v) for v in (rec.get("size") or [0.0, 0.0, 0.0])]
        gap = max(abs(a - b) for a, b in zip(span, want))
        if gap > LOCK_SPAN_TOL:
            _fail(errs, f"{k}：部件并集跨度 {[round(v, 3) for v in span]} 对不上 "
                        f"size {[round(v, 3) for v in want]}（差 {gap * 100:.1f} cm）"
                        f"—— ⛔ 十有八九是 decor/calibrate.py 没把 mesh_quat 转回文件坐标，"
                        f"改完重跑 `python -m decor.calibrate`")
        # convert.py 是按**整件包围盒中心**统一居中的，所以并集中心必须落在原点附近。
        # 偏了说明有部件没跟着居中——那会让整件在碰撞盒里偏向一侧。
        ctr = [(h + lv) / 2.0 for h, lv in zip(hi, lo)]
        if max(abs(v) for v in ctr) > LOCK_SPAN_TOL:
            _fail(errs, f"{k}：部件并集中心 {[round(v, 3) for v in ctr]} 不在原点附近"
                        f"—— convert.py 按整件包围盒中心统一居中，偏了说明有部件漏了")
    return errs


# ⛔ 最严的消费方默认值。`mujoco.Renderer(max_geom=10000)`；walkthrough.py 自己设了 20000，
#    但按最严的算才安全——而且 maxgeom **不能在 MJCF 里声明**，场景文件保护不了自己。
RENDER_GEOM_BUDGET = 10000


def check_geom_budget(key: str, layout) -> list[str]:
    """⛔⛔ geom 数不能超过渲染缓冲 —— 这是那条**静默**陷阱唯一的防线。

    2026-08-06 实测：缓冲满了 MuJoCo **只打一条 warning、不报错**，而且是按 geom 在模型里的
    **先后顺序**填、不按距离。窗景排在前面时溢出，**近处 200 件家具一个都进不去（0/200）**。
    生成器现在把室内排在窗景之前（见 make_house.build 里那段 ⛔），最坏后果降级成
    "远处少几栋楼"；但根本上还是不能超。
    """
    try:
        import mujoco
    except ImportError:
        return ["(跳过) 没装 mujoco"]
    errs: list[str] = []
    for robot in ROBOT_CLEARANCE:
        path = os.path.join(HERE, SCENES.scene_filename(key, robot))
        if not os.path.exists(path):
            continue
        n = mujoco.MjModel.from_xml_path(path).ngeom
        if n > RENDER_GEOM_BUDGET:
            _fail(errs, f"{os.path.basename(path)} 有 {n} 个 geom，超过渲染缓冲 "
                        f"{RENDER_GEOM_BUDGET}——超出的部分**不报错、直接不画**")
    return errs


def check_void(key: str, layout) -> list[str]:
    """⛔ 每个朝外的房间，往外都必须撞到实体 —— 否则机器人从 232 米走出去。

    ⚠️ 必须检查命中的 geom 的 `contype != 0`：`mj_ray` 不看 contype，打到一根纯装饰的
       竖挺也会返回距离，那是**假通过**。
    """
    if not getattr(layout, "GLASS_RGBA", None):
        return []                       # 没有落地窗的场景不适用
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    if not os.path.exists(path):
        return []
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gid = np.zeros(1, np.int32)
    errs: list[str] = []
    outward = {"n": (0, 1), "s": (0, -1), "e": (1, 0), "w": (-1, 0)}
    sides = {}
    for w in layout.WINDOWS:
        sides.setdefault(w["room"], set()).add(w["side"])
    for room, ss in sides.items():
        x0, y0, x1, y1 = layout.ROOMS[room]["rect"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        for side in ss:
            vx, vy = outward[side]
            for z in (0.30, 1.00, 1.60):
                origin = np.array([cx, cy, z])
                vec = np.array([float(vx), float(vy), 0.0])
                # ⚠️ 必须**穿过非碰撞体继续走**，不能只看第一个命中：
                #    `mj_ray` 不看 contype，装饰网格、纯视觉挂画都会挡在前面；
                #    而且射线起点常常就在某件家具的盒子里（房间中心往往有茶几）。
                #    只判第一次命中会得到假红——这一条我自己第一版就写错了。
                ok, hits, o = False, [], origin.copy()
                for _ in range(24):
                    dist = mujoco.mj_ray(m, d, o, vec, None, 1, -1, gid)
                    if dist < 0 or int(gid[0]) < 0:
                        break
                    g = int(gid[0])
                    if m.geom_contype[g] != 0:
                        ok = True
                        break
                    hits.append(mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or "?")
                    o = o + vec * (dist + 0.01)
                if not ok:
                    _fail(errs, f"{room} 的 {side} 侧、高 {z:.2f} m 往外打，"
                                f"一路没撞到**可碰撞**的东西（穿过了 {hits[:4] or '空'}）"
                                f"——机器人会直接走出去")
    return errs


def check_decor_inside_box(key: str, layout) -> list[str]:
    """⭐⭐ 每张装饰网格的真实顶点必须整个落在它所装饰的碰撞盒里（包含性不变式的正面证明）。

    ⛔ 为什么它不能被下面那条射线不变性取代：**射线打的全是水平方向**，
       所以只证伪得了水平方向的探出。2026-08-07 实测，当时有 7 件在 z 方向探出——
       落地灯的网格钻进地板 15 cm、盆栽 10.6 cm、冰箱 7.8 cm——**48 项自检一条都没红**。
    ⭐ 这一条不采样、不撞运气：直接从编译好的产物读 `geom_xpos/geom_xmat + mesh_vert`，
       把网格顶点变换到碰撞盒的局部系，和盒子半长逐轴比。探出多少就报多少毫米。
    ⚠️ 网格探出时**放大碰撞盒没有用**——`_fit_scale` 会把网格按比例一起撑大。
       该查的是 `_asset_span`（跨度算对没有）和 `_decor_geoms`（偏移加了几遍）。
    """
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    if not os.path.exists(path):
        return []
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    boxes: dict[str, int] = {}
    meshes: dict[str, list[int]] = {}
    for g in range(m.ngeom):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if nm.startswith("furn_"):
            boxes[nm[len("furn_"):]] = g
        elif nm.startswith("dg_"):
            # dg_<家具名>_<部件下标>
            meshes.setdefault(nm[len("dg_"):].rsplit("_", 1)[0], []).append(g)
    errs: list[str] = []
    for item, gids in sorted(meshes.items()):
        b = boxes.get(item)
        if b is None:
            _fail(errs, f"装饰 {item} 找不到对应的碰撞盒 furn_{item}")
            continue
        Rb = d.geom_xmat[b].reshape(3, 3)
        cb, hb = d.geom_xpos[b], m.geom_size[b]
        worst, axis = -1e9, 0
        for g in gids:
            mid = m.geom_dataid[g]
            v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
            w = (v @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g] - cb) @ Rb
            out = np.maximum(w.max(axis=0) - hb, -w.min(axis=0) - hb)
            if float(out.max()) > worst:
                worst, axis = float(out.max()), int(out.argmax())
        if worst > 1e-6:
            _fail(errs, f"装饰 {item} 的网格探出碰撞盒 {worst * 1000:.1f} mm（{'xyz'[axis]} 轴）"
                        f"—— 包含性不变式破了，⛔ 别去放大碰撞盒，"
                        f"去看 make_house 的 _asset_span / _decor_geoms")
    return errs


def check_decor_ray_invariance(key: str, layout) -> list[str]:
    """⭐⭐ 装饰网格不许改变**任何**射线读数 —— 这是"包含性不变式"的正面证明。

    ⛔ 为什么需要它：**`mj_ray` 根本不看 contype**（check_scene 四处 + walkthrough 两处射线
       全传 `geomgroup=None`）。所以"装饰是纯视觉的"这句话对射线**不成立**。
       house2 有现成伤疤：楼梯平台上放了盆栽，射线打到叶子，落差 +0.80 m。

    做法不是去**藏**装饰，而是**证明它不影响射线**：同一批采样点打两遍，
    一遍正常、一遍 `bodyexclude=decor_visual`，要求两者逐位相同。
    ⭐ 这比"目测网格有没有露出来"强得多——它是可证的。
    """
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    if not os.path.exists(path):
        return []
    m = mujoco.MjModel.from_xml_path(path)
    body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "decor_visual")
    if body < 0:
        return []                        # 这个场景没有装饰网格
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    g1, g2 = np.zeros(1, np.int32), np.zeros(1, np.int32)
    errs: list[str] = []
    # 采样：每间屋中心 + 每件家具中心，各在两个机器人的雷达高度打一圈 36 条
    origins = []
    for r in layout.ROOMS.values():
        x0, y0, x1, y1 = r["rect"]
        origins.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    for it in layout.FURNITURE:
        origins.append((it["pos"][0], it["pos"][1]))
    # ⚠️ **只采样自由空间里的点。** "碰撞盒先被打中"只对**从外面来的**射线成立——
    #    射线起点如果就在某件家具的盒子里，先碰到的自然是网格的内表面
    #    （圆桌网格半径 0.66 < 方盒半宽 0.675，是几何必然，不是缺陷）。
    #    而机器人不可能站在茶几内部，所以那种起点在物理上没有意义。
    #    这一条我第一版没想清楚，是被这个检查自己揪出来的。
    solid = [i for i in range(m.ngeom)
             if m.geom_contype[i] != 0 and m.geom_type[i] == mujoco.mjtGeom.mjGEOM_BOX]

    def _inside(p) -> bool:
        """点在不在某个实心盒子里。

        ⛔ 必须把点变换到**盒子自己的局部系**再比：`geom_size` 是局部系的半长，
           而带 yaw 的家具（条案、餐椅、冰箱）的盒子是转过的。
           ⚠️ 老版本直接拿世界轴比 `abs(p - geom_pos) <= geom_size`，
           于是把一只 yaw=90 的 2.44 m 条案当成东西向的——柜子内部的采样点被判成
           自由空间，射出去先碰到网格内表面，这条自检就报了个**假阳性**
           （2026-08-07 给三处条案换真网格时暴露）。
        """
        for i in solid:
            q = (p - d.geom_xpos[i]) @ d.geom_xmat[i].reshape(3, 3)
            if all(abs(q[k]) <= m.geom_size[i][k] + 0.02 for k in range(3)):
                return True
        return False

    # ⭐ 关键是**从家具外面朝它打**：绕每件装饰件一圈取起点，射向它的中心。
    #    这才是物理上会发生的情形（机器人在屋里走、雷达扫到家具），
    #    也是"碰撞盒必须先被打中"真正成立的情形。
    #    ⚠️ 只在房间中心撒点是不够的——那些射线未必经过装饰件，
    #       把 _FIT_EPS 调到 1.25（网格强行放大 25%）都测不出来，我第一版就是这样。
    shots = []
    for it in layout.FURNITURE:
        if not it.get("mesh"):
            continue
        cx, cy, cz = it["pos"]
        sx, sy, sz = it["size"]
        r = math.hypot(sx, sy) / 2.0 + 0.6          # 站在盒子外面一点
        for k in range(24):
            a = k * math.pi / 12.0
            for zf in (0.25, 0.55, 0.85):
                z = cz - sz / 2.0 + sz * zf
                o = np.array([cx + r * math.cos(a), cy + r * math.sin(a), z])
                if _inside(o):
                    continue
                v = np.array([-math.cos(a), -math.sin(a), 0.0])
                shots.append((o, v, it["name"]))
    # 再补一圈房间中心的水平扫描（雷达的常态）
    for ox, oy in origins:
        for z in (0.30, 0.90):
            o = np.array([ox, oy, z])
            if _inside(o):
                continue
            for k in range(36):
                a = k * math.pi / 18.0
                shots.append((o, np.array([math.cos(a), math.sin(a), 0.0]), "room"))

    bad = 0
    for o, v, who in shots:
        da = mujoco.mj_ray(m, d, o, v, None, 1, -1, g1)
        db = mujoco.mj_ray(m, d, o, v, None, 1, body, g2)
        if abs(da - db) > 1e-9:
            bad += 1
            if bad <= 3:
                nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(g1[0])) or "?"
                _fail(errs, f"装饰改变了射线读数（{who}）：从 "
                            f"({o[0]:.2f},{o[1]:.2f},{o[2]:.2f})，带装饰 {da:.4f} m / "
                            f"不带 {db:.4f} m（挡路的是 {nm}）——它探出了碰撞盒")
    if bad > 3:
        _fail(errs, f"…另有 {bad - 3} 条射线同样被改变")
    return errs


def check_park_sightline(key: str, layout) -> list[str]:
    """本楼和公园之间不许有东西挡着；`zfar × extent` 必须够远。

    ⛔ 两条都实际踩过（2026-08-05 apt1）：
       1. 把 220 CPS 放到了公园里（y=+45），它正杵在大客厅和公园中间，挡死左半边视野。
       2. `zfar=500 × extent 6 = 3000 m` 而公园伸到 4230 m，远半截被裁掉——
          而画面上**读起来像大气雾霾**，根本想不到是裁剪 bug。
       两条都是"渲染出来才发现"，而且第二条连渲染出来都容易看错原因。
    """
    errs: list[str] = []
    slabs = getattr(layout, "GROUND_SLABS", None)
    if not slabs:
        return []
    park_wall = getattr(layout, "PARK_WALL_Y", None)
    near = getattr(layout, "PARK_NEAR_Y", None)
    half_w = getattr(layout, "PARK_W", 0.0) / 2.0
    # 1) 本楼观景墙 → 公园近边这一段，横向 ±半个公园宽的范围内不许有塔楼
    if park_wall is not None and near is not None:
        for name, x, y, sx, sy, _top, _mat in getattr(layout, "SKYLINE", []):
            if park_wall < y - sy / 2.0 < near and abs(x) < half_w:
                _fail(errs, f"塔楼 {name}（x={x:g}, y={y:g}）落在本楼与公园之间"
                            f"（{park_wall:g} < y < {near:g}，|x| < {half_w:g}）"
                            f"——会挡住观景墙望出去的视线")
    # 2) zfar × extent 必须盖得住最远的视景几何
    V = getattr(layout, "VISUAL", {})
    stat = getattr(layout, "STATISTIC", {})
    reach = V.get("zfar", 60) * stat.get("extent", 6)
    far = 0.0
    for s in slabs:
        far = max(far, abs(s["pos"][1]) + s["size"][1] / 2.0, abs(s["pos"][0]) + s["size"][0] / 2.0)
    if reach < far:
        _fail(errs, f"zfar×extent = {reach:g} m 盖不住最远的视景几何 {far:g} m"
                    f"——远端会被裁掉，而画面上看起来只是「有点雾」")
    return errs


def check_art_clear(key: str, layout) -> list[str]:
    """挂画不许压在门洞或窗洞上。

    ⛔ 为什么要这条（2026-08-05 apt1 实际踩到）：一幅画挂到了贯通轴线的门洞正中间，
       渲染出来是一块大黑板把整条视线堵死。而**代码上完全看不出来**——
       画和门是两份互不相干的声明，生成器照单全收，自检也全绿。
       这类"两份声明各自合法、凑在一起才错"的问题，只能靠算重叠来抓。
    """
    errs: list[str] = []
    for i, a in enumerate(getattr(layout, "WALL_ARTS", []) or []):
        x0, y0, x1, y1 = layout.ROOMS[a["room"]]["rect"]
        horizontal = a["side"] in ("n", "s")
        want = "h" if horizontal else "v"
        fixed = {"n": y1, "s": y0, "e": x1, "w": x0}[a["side"]]
        lo, hi = (x0, x1) if horizontal else (y0, y1)
        aa, ab = a["center"] - a["w"] / 2.0, a["center"] + a["w"] / 2.0
        # 这面墙上的所有洞口：门按走向+坐标匹配，窗按房间+朝向匹配
        gaps = [(d["center"], d["width"], d.get("note", "门"))
                for d in layout.DOORS
                if d["orient"] == want and abs(d["coord"] - fixed) < 1e-6 and lo <= d["center"] <= hi]
        gaps += [(w["center"], w["width"], "窗")
                 for w in layout.WINDOWS
                 if w["room"] == a["room"] and w["side"] == a["side"]]
        for c, wd, note in gaps:
            if aa < c + wd / 2.0 and ab > c - wd / 2.0:
                _fail(errs, f"挂画 art{i}（{a['room']} {a['side']} 墙，{aa:.2f}…{ab:.2f}）"
                            f"压在洞口「{note}」（{c - wd / 2:.2f}…{c + wd / 2:.2f}）上"
                            f"——会变成一块悬在过道中间的板子")
    return errs


def check_no_dead_declarations(key: str, layout) -> list[str]:
    """layout 里声明了东西，产物里就必须找得到 —— 抓"死代码把声明吃掉"这一类 bug。"""
    errs: list[str] = []
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    if not os.path.exists(path):
        return []
    xml = open(path, encoding="utf-8").read()
    for name, prefix in DECLARED_TO_GEOM.items():
        declared = getattr(layout, name, None)
        if not declared:
            continue                     # 没声明就不该有，跳过
        found = xml.count(f'name="{prefix}')
        if found == 0:
            _fail(errs, f"layout 声明了 {len(declared)} 条 {name}，"
                        f"但产物里一个 name=\"{prefix}…\" 的 geom 都没有"
                        f"——生成器里对应的那段是不是没被 build() 调用？")
    return errs


def check_route(key: str, layout) -> list[str]:
    """⭐⭐ 沿**整条上楼路线**逐点往下打射线 —— 这个文件里最值钱的一项。

    ⛔ 它取代了老的 `check_walkable`。老那版只沿**单独一跑**打射线，
       所以 2026-08-02 那个"回头跑没接到平台上"的 bug 它**报了绿**：
       绕着走确实摸得到一条路。**查"存在一条路径"证明不了"这是一部楼梯"。**

    现在走的是 layout 给的唯一权威路线 `stair_route(floor)`：
    楼层平台 → 上行跑 → 中间平台 → 横移换道 → 回头跑 → 上一层楼层平台 → 门口。
    每 4.7 cm 采一个点，要求：

      - 处处有实体（不能悬空）；
      - 相邻两点高差不超过一个踢面（不能有断崖，也不能凭空长出一级）；
      - 起点在本层楼面、终点在上一层楼面（各 ±半个踢面）。

    ⚠️ 采样间距 0.047 m 是**故意跟踏面 0.30 无公约数**的：按 0.05 整数倍采样时，
       每 6 个点就正好落在两级的接缝上，射线从缝里穿过去打到底，读出一个凭空的
       大落差（第一版报"最大 0.330 m 落差"，全是假的）。
    """
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
        return []
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy，无法做射线连通性验证"]

    errs: list[str] = []
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    if not os.path.exists(path):
        return [f"产物不存在：{os.path.basename(path)}"]
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    rise = layout.STEP_RISE
    stride = 0.047

    def ground(px: float, py: float, expect: float) -> float | None:
        """(px, py) 脚下实体的高度。

        ⚠️ 射线从"这一点**应该**多高"再抬 0.25 m 处发出，不是从天上发。
           起得太高会先打到楼上那跑楼梯，量出来是别层的东西（早先错过一次）。
        """
        gid = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(m, d, np.array([px, py, expect + 0.25]),
                             np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
        return None if dist < 0 else expect + 0.25 - dist

    for floor in range(layout.N_FLOORS - 1):
        pts = layout.stair_route(floor)
        base, top = layout.FLOOR_Z(floor), layout.FLOOR_Z(floor + 1)
        heights: list[float | None] = []
        where: list[tuple[float, float]] = []
        for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(seg / stride))
            for i in range(n):
                t = (i + 0.5) / n
                px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                heights.append(ground(px, py, z0 + (z1 - z0) * t))
                where.append((px, py))

        holes = [w for h, w in zip(heights, where) if h is None]
        if holes:
            _fail(errs, f"{floor}→{floor + 1} 层：{len(holes)} 个采样点脚下悬空，"
                        f"第一个在 (x={holes[0][0]:.2f}, y={holes[0][1]:.2f})")
            continue
        worst_up = worst_dn = 0.0
        worst_at = None
        for (a, b), w in zip(zip(heights, heights[1:]), where[1:]):
            if b - a > worst_up:
                worst_up, worst_at = b - a, w
            worst_dn = min(worst_dn, b - a)
        if worst_up > rise + 1e-3:
            _fail(errs, f"{floor}→{floor + 1} 层：有一步要抬 {worst_up:.3f} m > 一个踢面 "
                        f"{rise}（在 x={worst_at[0]:.2f}, y={worst_at[1]:.2f}）—— 这里断了")
        if worst_dn < -(rise + 1e-3):
            _fail(errs, f"{floor}→{floor + 1} 层：路上有个 {-worst_dn:.3f} m 的落差 —— 会摔下去")
        if abs(heights[0] - base) > rise / 2:
            _fail(errs, f"{floor}→{floor + 1} 层：起点脚下 {heights[0]:.3f} m，"
                        f"应是本层楼面 {base:.3f} m")
        if abs(heights[-1] - top) > rise / 2:
            _fail(errs, f"{floor}→{floor + 1} 层：终点脚下 {heights[-1]:.3f} m，"
                        f"应是上一层楼面 {top:.3f} m")
        if not errs:
            print(f"      · {floor}→{floor + 1} 层实测走通："
                  f"{heights[0]:.3f} → {heights[-1]:.3f} m，共 {len(heights)} 个采样点")
    return errs


def check_no_open_drop(key: str, layout) -> list[str]:
    """⭐ 楼层平台四周不许有**没拦住的洞**。

    为什么需要单开一项：`check_route` 只管路线上有没有实地，管不了"路线旁边一步
    就是个洞"。顶层最典型——那条上行车道上面已经没有梯段接上去了，于是楼层平台
    北边就是一个直通下面梯段的大洞（这栋楼是 2.7 m）。真实楼梯那儿一定有围栏。

    做法：沿楼层平台的四条边，每 10 cm 取一点，**往外一小步一小步地探**（每 5 cm
    一次，探到半米），看脚下高度是**一级一级往下**（那是楼梯，正常）还是**一步就
    没底**（那是悬崖）。是悬崖，就必须在腰以下的高度横着打到实体，打不到 = 没拦住。

    ⚠️ 第一版是"往外跨 0.35 m 直接量高度"，结果**把正常的下楼口也判成洞**：
       跨 0.35 m 超过一个踏面 0.30，自然落到下面第二级上，读出 0.32 m 的"落差"。
       台阶和悬崖的区别不在落差大小，在**是不是一步到位**。
    """
    if not getattr(layout, "STAIRS", []):
        return []
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]

    errs: list[str] = []
    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    rise = layout.STEP_RISE
    REACH = 0.50          # 往外探这么远（人形一步够得着的范围）
    PROBE = 0.05          # 探测粒度：比一个踏面细得多，才分得出台阶和悬崖
    GUARD_HEIGHTS = (0.25, 0.60)   # 腰以下横着打两道，任一打到实体就算拦住了
    INSET = 0.20          # 横射线从平台里面这么远处发出（见下面的注释）

    def floor_under(px: float, py: float, z_from: float) -> float | None:
        gid = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(m, d, np.array([px, py, z_from]),
                             np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
        return None if dist < 0 else z_from - dist

    for rkey, room in layout.ROOMS.items():
        rects = room.get("floor_rects")
        if not rects:                      # 只查局部楼板（= 楼层平台），整层铺的不用查
            continue
        z = layout.FLOOR_Z(room.get("floor", 0))
        for x0, y0, x1, y1 in rects:
            edges = [((x0, y0), (x1, y0), (0.0, -1.0)), ((x0, y1), (x1, y1), (0.0, +1.0)),
                     ((x0, y0), (x0, y1), (-1.0, 0.0)), ((x1, y0), (x1, y1), (+1.0, 0.0))]
            for (ax, ay), (bx, by), (ox, oy) in edges:
                n = max(1, int(math.hypot(bx - ax, by - ay) / 0.10))
                cliff = None
                for i in range(n + 1):
                    t = i / n
                    px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                    # 往外一小步一小步地探：台阶是一级一级下去，悬崖是一步没底
                    here = z
                    for j in range(1, int(REACH / PROBE) + 1):
                        qx, qy = px + ox * j * PROBE, py + oy * j * PROBE
                        nxt = floor_under(qx, qy, here + 0.25)
                        if nxt is None or here - nxt > rise + 1e-3:
                            cliff = (px, py, None if nxt is None else here - nxt)
                            break
                        here = nxt
                    if cliff:
                        break
                if not cliff:
                    continue
                px, py, drop = cliff
                # ⚠️ 横射线要从**平台里面**发出（往里缩 INSET），不能贴着边发：
                #    楼板压到墙心，贴边发的射线起点就落在墙体内部，MuJoCo 对
                #    "起点在几何体里"的射线不给可信结果，检查会假绿。
                hit = False
                for gh in GUARD_HEIGHTS:
                    gid2 = np.zeros(1, dtype=np.int32)
                    blocked = mujoco.mj_ray(
                        m, d, np.array([px - ox * INSET, py - oy * INSET, z + gh]),
                        np.array([ox, oy, 0.0]), None, 1, -1, gid2)
                    if 0 <= blocked <= INSET + REACH:
                        hit = True
                        break
                if not hit:
                    how = "一步就没底" if drop is None else f"一步掉 {drop:.2f} m"
                    _fail(errs, f"{rkey}：楼层平台边上 (x={px:.2f}, y={py:.2f}) 往外 {how}，"
                                f"而腰以下没有任何东西拦着 —— 需要一道栏板")
    return errs


def check_headroom(key: str, layout) -> list[str]:
    """⭐ 楼梯头顶净空 —— 站在每一级上往上打射线量。

    这一项是 Jeff 目视发现、然后才补上的：踏步原来做成"从楼层地面填上来的实心块"，
    于是上面那跑楼梯的底面成了一块**平顶**，越往上走顶越低，顶级只剩 1.38 m
    （G1 站着就 1.32 m）。改成斜底厚板后就够了——两跑各占一条道，上下层同一条道
    正好隔一个层高，净空处处 = 层高 − 板厚。

    教训：**"能走"不等于"走着不别扭"**，而净空这种事看渲染图看不出来，
    得站上去往上量。
    """
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
        return []
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]

    path = os.path.join(HERE, SCENES.scene_filename(key, "g1"))
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    errs: list[str] = []
    for flight in stairs:
        x, y0 = flight["start_xy"]
        dx, dy = flight["dir"]
        worst, worst_step, worst_geom = 1e9, None, None
        for i in range(flight["risers"] - 1):
            px = x + dx * (i + 0.5) * layout.STEP_RUN
            py = y0 + dy * (i + 0.5) * layout.STEP_RUN
            tread = flight["base_z"] + (i + 1) * layout.STEP_RISE
            gid = np.zeros(1, dtype=np.int32)
            dist = mujoco.mj_ray(m, d, np.array([px, py, tread + 0.02]),
                                 np.array([0.0, 0.0, 1.0]), None, 1, -1, gid)
            if dist < 0:
                continue          # 头上是天，不算问题
            if dist < worst:
                worst, worst_step = dist, i + 1
                worst_geom = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(gid[0]))
        if worst < MIN_HEADROOM_M:
            _fail(errs, f"{flight['name']}：第 {worst_step} 级头顶只有 {worst:.2f} m"
                        f"（下限 {MIN_HEADROOM_M}），挡住的是 {worst_geom}")
    return errs


CHECKS = [
    ("layout 契约完整", check_contract),
    ("产物是合法 XML", check_wellformed),
    ("⭐ 引用的材质/贴图都真的存在", check_assets),
    ("⭐⭐ decor.lock 自洽（offset±half ⇄ size）", check_lock_reconciles),
    ("⛔ geom 数没超渲染缓冲", check_geom_budget),
    ("产物能被 MuJoCo 加载", check_loads),
    ("楼梯爬满一层 + 尺寸合规", check_stairs),
    ("⭐ 四个接头闭合（梯段 ↔ 平台）", check_joints),
    ("门宽够机器人过", check_doors),
    ("⭐⭐ 门真的走得过去（两侧在屋里 + 净通行宽）", check_door_passable),
    ("⭐ 家具没有捅穿墙伸进隔壁", check_furniture_not_through_wall),
    ("⭐ 声明的东西都真的进了产物", check_no_dead_declarations),
    ("挂画没压在门窗洞口上", check_art_clear),
    ("⭐ 望公园的视线没被挡 + 远景没被裁", check_park_sightline),
    ("⛔ 朝外的房间往外都撞得到实体", check_void),
    ("⭐⭐ 装饰网格整个装在碰撞盒里", check_decor_inside_box),
    ("⭐⭐ 装饰网格没改变任何射线读数", check_decor_ray_invariance),
    ("⭐ 整条上楼路线实测走通", check_route),
    ("楼梯头顶净空", check_headroom),
    ("楼层平台没有没拦住的洞", check_no_open_drop),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default="", help="只检查这个场景；不给=全部")
    args = ap.parse_args()

    keys = [args.scene] if args.scene else SCENES.keys()
    bad = 0
    for key in keys:
        layout = SCENES.load_layout(key)
        floors = len({r.get("floor", 0) for r in layout.ROOMS.values()})
        print(f"── {key}：{SCENES.get(key)['label']}（{len(layout.ROOMS)} 空间 / {floors} 层）")
        for title, fn in CHECKS:
            errs = fn(key, layout)
            notes = [e for e in errs if e.startswith("(跳过)")]
            real = [e for e in errs if not e.startswith("(跳过)")]
            mark = "⚠️ " if notes and not real else ("❌" if real else "✅")
            print(f"   {mark} {title}")
            for e in notes + real:
                print(f"        {e}")
            bad += len(real)
    print()
    if bad:
        print(f"❌ {bad} 项不通过")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
