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

检查项（任一不过 → 退出码 1）：
  1. layout 契约完整：生成器要读的名字一个不缺
  2. 产物能被 MuJoCo 真正加载（不是"文件存在"）
  3. 楼梯连通性：每组楼梯正好爬满一层，顶端落在上一层地面上（±1 mm）
  4. 楼梯几何合理：踏面容得下机器人的脚、坡度在可走范围内
  5. 门宽够登记在册的机器人通过
  6. 多层场景的楼梯井上方不铺地板（铺了就把上楼的口封死）
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

# 多层场景额外要有的
MULTIFLOOR_NAMES = ["FLOOR_Z", "STOREY_H", "N_FLOORS", "STEP_RISE", "STEP_RUN", "STAIRS"]

# 机器人的通行尺寸。⚠️ 不是从 robots/manifest.py 读的：那里是资产事实
# （模型在哪、出生多高），不含"这台机器人多宽、脚多长"。这两个数只在这里用来做
# 通行性判断，所以就地具名 + 写清出处，而不是散在检查代码里当魔法数。
ROBOT_CLEARANCE = {
    # key: (通行宽度 m, 脚长 m, 出处)
    "g1": (0.60, 0.25, "宇树 G1 肩宽约 0.45 m，走动时手臂摆动取 0.60；脚长实测约 0.25"),
    "go2": (0.40, 0.10, "宇树 Go2 机身宽约 0.31 m，取 0.40 留余量；足端接近点接触"),
}

MIN_TREAD_MARGIN = 0.03   # 踏面至少比脚长多这么多，否则盲走一偏就踩空
MAX_STAIR_SLOPE_DEG = 38.0  # 超过这个坡度人形基本上不去（住宅规范上限约 33–38°）


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
    """⭐ 顶步悬空防线：每组楼梯必须正好爬满一层。"""
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
        return []
    errs: list[str] = []
    rise, run = layout.STEP_RISE, layout.STEP_RUN
    storey = layout.STOREY_H

    # 按起点高度分组：同一层的两跑加起来应等于层高
    climbed: dict[float, float] = {}
    for flight in stairs:
        base = round(flight["base_z"], 6)
        climbed[base] = climbed.get(base, 0.0) + flight["steps"] * rise

    for floor in range(layout.N_FLOORS - 1):
        z0 = round(layout.FLOOR_Z(floor), 6)
        total = sum(v for b, v in climbed.items()
                    if z0 - 1e-6 <= b < z0 + storey - 1e-6)
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
    return errs


def check_doors(key: str, layout) -> list[str]:
    errs: list[str] = []
    need = max(w for w, _f, _n in ROBOT_CLEARANCE.values())
    for door in layout.DOORS:
        if door["width"] < need:
            _fail(errs, f"门 {door.get('note', '?')} 净宽 {door['width']:.2f} m "
                        f"< 需要的 {need:.2f} m")
    return errs


def check_walkable(key: str, layout) -> list[str]:
    """⭐ 沿每一跑楼梯打射线，量脚下实体的高度 —— **查产物，不查声明**。

    这一项是这个文件里最值钱的检查，因为它是唯一"从物理上"验证的。
    写 house2 时的真实经历：布局里写了 `"no_floor": True`，生成器却从没实现这个键，
    二三层楼梯井照样铺了地板、把上楼的口封死；而当时那版检查只核对布局有没有写
    `no_floor`，于是**报了绿**。查声明的检查只能证明"我说了"，证明不了"它是"。

    判据：沿梯中心线每 5 cm 一个采样，落脚高度必须
      - 处处有实体（不能悬空），
      - 相邻不超过一个踢面（不能有断崖），
      - 起止高度对得上这一跑的设计值。
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
    rise, run = layout.STEP_RISE, layout.STEP_RUN

    for flight in stairs:
        x, y0 = flight["start_xy"]
        dy = flight["dir"][1]
        dx = flight["dir"][0]
        top = flight["base_z"] + flight["steps"] * rise
        # ⚠️ 射线起点只比这一跑的顶高一点点。起得太高会先打到**上一层**的几何，
        #    量出来的是楼上那跑楼梯（第一版就这么错过一次）。
        z_from = top + 0.30
        # ⚠️ 采样点必须**避开踏步交界**。步距 0.30 m，若按 0.05 m 整数倍采样，
        #    每 6 个点就正好落在两级的接缝上，射线从缝里穿过去打到地板，
        #    读出来是一个凭空的大落差（第一版报了"最大 0.330 m 落差"，全是假的）。
        #    取 0.047 m 这个与步距无公约数的间距，并整体偏移半步。
        heights: list[float | None] = []
        span = flight["steps"] * run
        stride = 0.047
        n = int(span / stride)
        for i in range(1, n):
            along = i * stride + stride / 2.0
            px = x + dx * along
            py = y0 + dy * along
            gid = np.zeros(1, dtype=np.int32)
            dist = mujoco.mj_ray(m, d, np.array([px, py, z_from]),
                                 np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
            heights.append(None if dist < 0 else z_from - dist)

        if any(h is None for h in heights):
            _fail(errs, f"{flight['name']}：有 {sum(h is None for h in heights)} 个采样点脚下悬空")
            continue
        jumps = [(a, b) for a, b in zip(heights, heights[1:]) if b - a > rise + 1e-3]
        if jumps:
            worst = max(b - a for a, b in jumps)
            _fail(errs, f"{flight['name']}：{len(jumps)} 处落差超过一个踢面（最大 {worst:.3f} m > {rise} m）")
        lo, hi = heights[0], heights[-1]
        if abs(lo - flight["base_z"]) > rise + 1e-3:
            _fail(errs, f"{flight['name']}：起点脚下 {lo:.3f} m，应在 {flight['base_z']:.3f} m 附近")
        if abs(hi - top) > rise + 1e-3:
            _fail(errs, f"{flight['name']}：终点脚下 {hi:.3f} m，应在 {top:.3f} m 附近")
    return errs


def check_egress(key: str, layout) -> list[str]:
    """⭐ 下了楼梯之后，能不能走出去 —— 上一项只沿梯段探，探不到这一段。

    真实经历（2026-08-02）：上层楼梯井整层写了 `no_floor`，梯段本身四跑全通、
    自检全绿，但人爬到二层落点脚下是空的，当场掉回一层。
    **"梯段是通的"和"上去之后站得住"是两件事。**

    做法：从每一跑的终点起，朝出口方向每 5 cm 探一次脚下，要求
    一路有实地、且高度不掉下去（容差一个踢面）。
    """
    stairs = getattr(layout, "STAIRS", [])
    if not stairs:
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

    # 每层的到达点 = 那一层最后一跑的终点；出口 = 该层楼梯间朝外的门
    for floor in range(1, layout.N_FLOORS):
        arriving = [f for f in stairs
                    if abs(f["base_z"] + f["steps"] * rise - layout.FLOOR_Z(floor)) < 1e-3]
        if not arriving:
            _fail(errs, f"{floor} 层没有任何一跑楼梯到达 —— 这层上不去")
            continue
        flight = arriving[0]
        dx, dy = flight["dir"]
        ex = flight["start_xy"][0] + dx * flight["steps"] * layout.STEP_RUN
        ey = flight["start_xy"][1] + dy * flight["steps"] * layout.STEP_RUN
        # 沿最后一跑的前进方向再往前走 1.2 m（人形转身+迈出所需）
        z_from = layout.FLOOR_Z(floor) + 0.40
        bad = 0
        for i in range(1, 25):
            px, py = ex + dx * i * 0.05, ey + dy * i * 0.05
            gid = np.zeros(1, dtype=np.int32)
            dist = mujoco.mj_ray(m, d, np.array([px, py, z_from]),
                                 np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
            z = None if dist < 0 else z_from - dist
            if z is None or z < layout.FLOOR_Z(floor) - rise:
                bad += 1
        if bad:
            _fail(errs, f"{floor} 层到达点前方 1.2 m 内有 {bad}/24 个采样点脚下没有实地 —— "
                        f"上来就踩空，需要一块到达平台（floor_rects）")
    return errs


CHECKS = [
    ("layout 契约完整", check_contract),
    ("产物能被 MuJoCo 加载", check_loads),
    ("楼梯正好爬满一层", check_stairs),
    ("楼梯几何可走", check_stairs),   # 同一函数，报告里分两行更好读
    ("门宽够机器人过", check_doors),
    ("楼梯全程可走（射线实测）", check_walkable),
    ("下梯之后站得住、走得出", check_egress),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default="", help="只检查这个场景；不给=全部")
    args = ap.parse_args()

    keys = [args.scene] if args.scene else SCENES.keys()
    bad = 0
    seen: set[str] = set()
    for key in keys:
        layout = SCENES.load_layout(key)
        floors = len({r.get("floor", 0) for r in layout.ROOMS.values()})
        print(f"── {key}：{SCENES.get(key)['label']}（{len(layout.ROOMS)} 空间 / {floors} 层）")
        for title, fn in CHECKS:
            if (key, fn.__name__) in seen:
                continue
            seen.add((key, fn.__name__))
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
