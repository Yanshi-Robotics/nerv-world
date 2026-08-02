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

检查项（任一不过 → 退出码 1）：
  1. layout 契约完整：生成器要读的名字一个不缺
  2. 产物能被 MuJoCo 真正加载（不是"文件存在"）
  3. 楼梯正好爬满一层，且尺寸合规（GB 50096-2011 §6.3）
  4. ⭐ 四个接头闭合：上一段末级 ↔ 下一段起始平台，首尾相接 + 差一个踢面
  5. 门宽够登记在册的机器人通过
  6. ⭐ 整条路线走得通：楼层平台→上行跑→中间平台→回头跑→上一层→门口，逐点实测
  7. 楼梯头顶净空 ≥ 规范值
  8. 楼层平台四周不许有没拦住的洞
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
    ("产物能被 MuJoCo 加载", check_loads),
    ("楼梯爬满一层 + 尺寸合规", check_stairs),
    ("⭐ 四个接头闭合（梯段 ↔ 平台）", check_joints),
    ("门宽够机器人过", check_doors),
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
