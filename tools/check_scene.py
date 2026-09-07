#!/usr/bin/env python3
"""场景自检 —— 生成之后、用之前跑一遍。

    python tools/check_scene.py                 # 检查全部已登记场景
    python tools/check_scene.py --scene house2

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
import collections
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
#    这条规矩是为了 review 时一眼看得出有没有漏改：任何落点错误都会在
#    tools/ 下长出一个目录（`ls tools/ | grep -v '\.py$'` 必须为空）。
sys.path.insert(0, ROOT)

from scenes import manifest as SCENES  # noqa: E402

# 生成器会读的 layout 顶层名字。少一个就是运行到一半炸，而不是启动时说清楚。
REQUIRED_NAMES = [
    "WALL_HEIGHT", "WALL_THICK", "DOOR_HEIGHT", "FLOOR_THICK", "CEILING_THICK",
    "CEILING_GROUP", "CEILING_RGBA", "WINDOW_SILL_H", "WINDOW_TOP_H",
    "DOOR_FRAME_THICK", "DOOR_FRAME_RGBA", "WINDOW_FRAME_T", "WINDOW_FRAME_RGBA",
    "ART_FRAME_T", "ART_FRAME_RGBA", "FRONT_DOOR",   # ⚠️ FRONT_DOOR_HANDLE 2026-08-08 并进 FRONT_DOOR
    "ROOMS", "DOORS", "WINDOWS", "FURNITURE", "WALL_ARTS",
    "START_POS_XY", "START_YAW",
    # ⭐ 停机位（「保姆间」）。⛔ 和 START_POS_XY 是两个量，别合并——那是任务出生点。
    "ROBOT_HOME_XY", "ROBOT_HOME_YAW",
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
#
# ⛔⛔ **这张表不是"本仓有哪些机器人"** —— 它是"哪些机器人得走得过去"。
#    两者不是一回事：扫地机器人的模型住在另一个仓（open-cleaning-robot），
#    本仓**没有它的产物**。要遍历"有模型的机器人"请用 `_modelled_robots()`。
#    ⚠️ 2026-08-08 把扫地机器人加进来时就踩了这个：四处 `for robot in ROBOT_CLEARANCE`
#    当场去找 `apt1-cleaning.xml`，自检红了三条。
ROBOT_CLEARANCE = {
    # key: (通行宽度 m, 脚长 m, 出处)
    # ⚠️ 这三个数是**实测复核过**的（2026-08-08，从编译后的模型量挡路带 0.25–1.35 m 里的水平占地）：
    #    G1 肩宽 0.446、Go2 机身宽 0.317、扫地机直径 0.349。判据取 max = G1 的 0.60，
    #    多出来的余量是手臂摆动 + 走偏。补第三台之后判据值**没变**，但把依据记下来了。
    "g1": (0.60, 0.25, "宇树 G1 肩宽实测 0.446 m，走动时手臂摆动取 0.60；脚长实测约 0.25"),
    "go2": (0.40, 0.10, "宇树 Go2 机身宽实测 0.317 m，取 0.40 留余量；足端接近点接触"),
    "cleaning": (0.45, 0.02, "扫地机器人 base_diameter=0.349（open-cleaning-robot 的 "
                             "src/cr_description/urdf/params.xacro:15），取 0.45 留余量；轮子接近点接触"),
}


def _modelled_robots() -> list[str]:
    """本仓**有模型、会出产物**的机器人 key。⛔ 别用 `ROBOT_CLEARANCE` 代替它（见上）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "alice_robots_chk", os.path.join(ROOT, "robots", "manifest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.ROBOTS)

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

# ── 真碰撞体（CoACD 凸块）相关 ──────────────────────────────────────────
# 网格允许探出「凸块并集包围盒」多少。⭐ 这个数是**量出来的不是拍的**：
# 2026-08-22 实测三件已分解的资产，网格都稳稳**缩在**凸块并集里面——
#     dining_chair −3.4 mm   armchair −4.2 mm   coffee_table −5.9 mm （负 = 在里面）
# 也就是说真实余量至少 3.4 mm。取 1 mm 作为门线：既容得下 `%g` 六位有效数字的截断
# （box 那条路实测最坏 4.84 µm），又远小于真实余量，变换一旦分家就当场红。
_HULL_AABB_TOL = 0.001

# 座面高度上限。⭐ 实测出来的硬指标，不是审美：G1 小腿 0.318 + 踝高 0.033 = 0.351，
# 坐姿保持 3 秒的实测结果是 0.30 ✅ / 0.35 ✅ / 0.40 ❌ 滑落 / 0.45 ❌ 直接倒。
# ⚠️ apt1 现有那张沙发是 0.42，正落在失败带里（那张不改，见 apt2 计划）。
SEAT_MAX_H = 0.36
# 座面下方要留的净空高度：脚和小腿要收得进去（⚠️ 只对声明了 under_clear 的坐具查）
SEAT_CLEAR_Z = 0.26
# 座面上方要留给上半身的净空。G1 坐姿骨盆在座面上方约 6 cm，肩在骨盆上方约 0.29 m，
# 头顶再高一截；取 0.60 m 是"上半身塞得进去"的下限，不是舒适值。
SEAT_HEADROOM = 0.60


def _fail(msgs: list[str], text: str) -> None:
    msgs.append(text)


def _scene_path(key: str, robot: str) -> str:
    """产物的绝对路径。⭐ **全文件只有这一处拼产物路径** —— 目录再动只改这里。

    ⚠️ `scene_filename()` 返回的是**含 `build/` 的仓根相对路径**（不是裸文件名），
       所以这里 join 的是仓根。这个仓的红线之一是「目录一动，所有 `..` 重新数一遍」，
       而把同一个拼接抄 11 遍正是它最容易翻车的形态。
    """
    return os.path.join(ROOT, SCENES.scene_filename(key, robot))


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
    for robot in _modelled_robots():
        path = _scene_path(key, robot)
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
# 底面高于这个的东西不挡路：吊柜、油烟机、挂画——1.38 m 的 G1 从下面钻过去。
# ⚠️ 2026-08-08 新加。在此之前只判下界（跨得过去），于是 kt_upper / ck_hood 这类
#    吊柜被当成落地的实心障碍，可通行性会被低估。
BODY_TOP_M = 1.35


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
        # ⛔⛔ 这里曾经写着 `if door.get("kind") == "open": continue`，直接跳过整段拆墙的开敞通道。
        #    2026-08-08 删掉。理由：**开敞洞口恰恰是最容易被家具堵死的那种**——它没有门框拦着，
        #    沙发就直接顶上去了。apt1「画廊→大客厅」那个 4.00 m 的开口正是 kind="open"，
        #    沙发组把它塞掉 3.76 m、只剩 0.44 m 的窄缝，而 **G1 只能到达大客厅 2%**
        #    （北半区 10.4 ㎡ 整块是孤岛）—— 48 项自检却全绿，因为这一行把它跳过去了。
        #    跳过最大的洞，等于在网上剪了个最大的窟窿。
        c, w, co = door["center"], door["width"], door["coord"]
        horiz = door["orient"] == "h"
        note = door.get("note", "?")
        for floor in floors:
            if "floor" in door and door["floor"] != floor:
                continue
            for sgn, lbl in ((-1, "南/西"), (+1, "北/东")):
                px, py = ((c, co + sgn * (t / 2 + 0.30)) if horiz
                          else (co + sgn * (t / 2 + 0.30), c))
                external = any(a['rect'][0] <= px <= a['rect'][2] and
                               a['rect'][1] <= py <= a['rect'][3] and
                               abs(a['floor_z'] - layout.FLOOR_Z(floor)) < 1e-6
                               for a in getattr(layout, 'EXTERIOR_AREAS', []))
                if _room_at(px, py, floor) is None and not external:
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



# ── 可通行性（reachability）──────────────────────────────────────────────
# 判据不是「两件家具之间多宽」，而是「机器人到底走不走得到」。⭐ 这个区别是本项的全部价值：
# 逐缝报数会被床头柜↔床、餐椅↔餐桌、贴合橱柜炸出上百条假阳性，而且**根本没法自动判断
# 哪条缝该管**——沙发和茶几之间 0.42 m 是正常客厅，绕得开就没问题。
# 可通行性直接回答「绕不绕得开」。
REACH_GRID_M = 0.05         # 栅格边长。0.60 m 的判据下这个精度足够（12 格），全场 ~14 万格
REACH_MIN_AREA_M2 = 0.25    # 一间屋至少要有这么大的可站立面积才算"进得去"（≈ 一个身位）


def _reach_obstacles(layout, floor: int) -> list:
    """这一层的挡路家具 → (类型, 参数) 列表。挡路带 = 顶面高于跨越高度、底面低于身高。

    ⛔ 高度这两头都要判：
      · 顶面 ≤ DOOR_STEPOVER_M（0.25）—— 地毯、地垫、门槛，抬脚跨得过去；
      · 底面 ≥ BODY_TOP_M（1.35）—— 吊柜、油烟机、挂画，1.4 m 的人形从下面钻过去。
        ⚠️ 上界这一条是 2026-08-08 新加的：在此之前 `check_door_passable` 只判下界，
        于是 kt_upper / ck_hood 这类吊柜被当成落地的实心障碍。
    ⭐ 带 yaw 的用**精确 OBB**（记下中心+半长+yaw，判距时把点转进局部系），
       ⛔ 不用 `_yaw_aabb` 那个保守外接框——对 yaw=200° 的单椅它比真形状大 0.30 m，
       拿来算可达性会造出假的"堵死"。
    """
    out = []
    for it in getattr(layout, "FURNITURE", []):
        if it.get("type") not in ("box", "cylinder"):
            continue
        if _furn_floor(layout, it) != floor:
            continue
        px, py, pz = it["pos"]
        sx, sy, sz = it["size"]
        if pz + sz / 2.0 <= DOOR_STEPOVER_M and not it.get('enclosed_fixture'):
            # An enclosed tub bottom is below step height but is not room floor.
            continue
        if pz - sz / 2.0 >= BODY_TOP_M:           # 钻得过去
            continue
        if it["type"] == "cylinder":
            out.append(("cyl", px, py, sx / 2.0))
            continue
        q = it.get("quat")
        yaw = 2.0 * math.atan2(q[3], q[0]) if q else 0.0
        out.append(("obb", px, py, sx / 2.0, sy / 2.0, yaw))
    return out


def _obstacle_dist(ob, x: float, y: float) -> float:
    """点到障碍的水平距离（在里面算 0）。"""
    if ob[0] == "cyl":
        _, cx, cy, r = ob
        return max(0.0, math.hypot(x - cx, y - cy) - r)
    _, cx, cy, hx, hy, yaw = ob
    dx, dy = x - cx, y - cy
    ca, sa = math.cos(-yaw), math.sin(-yaw)
    lx, ly = dx * ca - dy * sa, dx * sa + dy * ca      # 转进盒子局部系
    ox, oy = max(abs(lx) - hx, 0.0), max(abs(ly) - hy, 0.0)
    return math.hypot(ox, oy)


def _furn_floor(layout, it: dict) -> int:
    rooms = getattr(layout, "ROOMS", {})
    return rooms.get(it.get("room", ""), {}).get("floor", 0)




# 贴墙判据：家具边离墙内表面小于这个值就算"贴着墙摆的"，才需要管它正面朝哪。
FACE_WALL_NEAR_M = 0.35
# 正面前方至少要有这么多净空，否则就是"脸冲着墙"。
FACE_CLEAR_M = 0.50



def check_mesh_has_uv(key: str, layout) -> list[str]:
    """⭐⭐ 产物里每一张装饰网格都必须**带 UV**（`mesh_texcoordnum > 0`）。

    ⛔ 为什么必须有它（2026-08-08，Jeff 走进屋里才发现，此前活了整整两版）：
       `decor/convert.py` 的 `export_obj` 把 `include_texture` 写成了 False。
       那个开关的名字有迷惑性——它管的**不是"要不要打包贴图"**，而是**要不要写 `vt` 行**。
       于是 16 件资产、39 张网格的 OBJ 一行 UV 都没有，而 MuJoCo 拿不到 UV 就把整张网格
       按 **uv=(0,0) 采一个像素**涂满：木柜那个像素恰好是 (49,31,17) 近黑棕 → "柜子发黑"；
       床和床头柜是 (192,191,187) 灰白 → "门洞里一个怪箱子""床头一个没渲染的盒子"。
       ⚠️ **编译不报错、渲染不报错、26 项自检全绿**，只有肉眼看图才发现"上了真家具还是一堆盒子"。

    ⭐ 这是"同一个东西在两处各存了一份、没人逼它们对账"的又一次现形——
       lock 里明明记着每件资产的贴图 PNG，产物里也明明引用了那些贴图，
       **却从来没有人问过"网格到底能不能用上它"**。和 [0.9] 的 `check_lock_reconciles` 同族。

    ⚠️ 只查带贴图的那些：少数部件（如床头柜的拉手）本来就没有 PNG、只有纯色 rgba，
       那种没有 UV 是正常的，不该判红。判据取"这张网格对应的 material 引用了 texture"。
    """
    try:
        import mujoco
    except ImportError:
        return ["(跳过) 没装 mujoco"]
    errs: list[str] = []
    m = mujoco.MjModel.from_xml_path(_scene_path(key, "g1"))
    for g in range(m.ngeom):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if not nm.startswith("dg_") or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mid = int(m.geom_matid[g])
        if mid < 0 or int(m.mat_texid[mid][mujoco.mjtTextureRole.mjTEXROLE_RGB]) < 0:
            continue                      # 纯色部件，本来就不需要 UV
        mesh = int(m.geom_dataid[g])
        if int(m.mesh_texcoordnum[mesh]) == 0:
            mname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mesh) or "?"
            _fail(errs, f"装饰网格 {mname!r}（geom {nm}）**没有 UV**，但它的材质引用了贴图——"
                        f"MuJoCo 会按 uv=(0,0) 采一个像素涂满整件，看起来就是个单色盒子。"
                        f"根因通常在 decor/convert.py 的 export_obj（`include_texture` 必须为 True），"
                        f"改完要重跑 `python -m decor.fetch --force` 与 `python -m decor.calibrate`")
    return errs

def check_mesh_faces_room(key: str, layout) -> list[str]:
    """⭐ 贴墙摆的家具，正面不许朝着墙。

    ⛔ 为什么要它（2026-08-08）：三只同款木柜里，靠**东**墙那只 `gr_console` 抄了另两只
       靠**西**墙的 `yaw=90`，于是正面顶着墙、屋里只看得到那块没有任何门缝的背板。
       Jeff 报的"柜子发黑、结构像穿透"有一半是这个。
       26 项自检里**没有一项管过朝向**——位置、碰撞、通行、包围盒包含性全查了，
       唯独没查"这东西是不是背对着人"。

    ⚠️ 只检查在 `decor/manifest.py` 里**显式声明了 `front`** 的资产。
       ⛔ 别去自动推断正面：同一套启发式对油烟机就会判错（它的小部件是烟道，本来朝墙）。
       宁可只守住实测过的那几件，也不要制造假阳性——假阳性会让人开始无视这项检查。
    """
    errs: list[str] = []
    try:
        from decor import manifest as DM
    except ImportError:
        return []
    rooms = getattr(layout, "ROOMS", {})
    t = layout.WALL_THICK
    for it in getattr(layout, "FURNITURE", []):
        spec = it.get("mesh") or {}
        akey = spec.get("id", "")
        front = (DM.ASSETS.get(akey) or {}).get("front")
        if not front:
            continue
        r = rooms.get(it.get("room", ""))
        if not r:
            continue
        sign = -1.0 if front.startswith("-") else 1.0
        axis = front[-1]
        fx, fy = (sign, 0.0) if axis == "x" else (0.0, sign)
        q = it.get("quat")
        yaw = 2.0 * math.atan2(q[3], q[0]) if q else 0.0
        ca, sa = math.cos(yaw), math.sin(yaw)
        wx, wy = fx * ca - fy * sa, fx * sa + fy * ca          # 正面在世界系的方向
        px, py = it["pos"][0], it["pos"][1]
        x0, y0, x1, y1 = r["rect"]
        # 家具贴着哪面墙？（四面各算一次边到墙内表面的距离）
        # ⛔ 必须用**转过 yaw 的世界 AABB**，不能用 `it["size"]`——那是**局部**边长。
        #    第一版就栽在这儿：2.44 长的条案转 90° 后世界占地只有 0.52 宽，拿局部的 2.44 去量
        #    离墙距离得到 0.94 m，于是被当成"不是贴墙摆的"直接跳过，故障注入一次都没抓到。
        #    `_yaw_aabb()` 就是仓里干这件事的现成帮手。
        ax0, ax1, ay0, ay1 = _yaw_aabb(it)
        near = min(abs((x0 + t) - ax0), abs((x1 - t) - ax1),
                   abs((y0 + t) - ay0), abs((y1 - t) - ay1))
        if near > FACE_WALL_NEAR_M:
            continue                                            # 不是贴墙摆的，正面朝哪随意
        # 正面方向上到墙的净空
        dx = ((x1 - t) - px) / wx if wx > 0.1 else (((x0 + t) - px) / wx if wx < -0.1 else 1e9)
        dy = ((y1 - t) - py) / wy if wy > 0.1 else (((y0 + t) - py) / wy if wy < -0.1 else 1e9)
        clear = min(dx, dy)
        if clear < FACE_CLEAR_M:
            _fail(errs, f"家具 {it['name']}（{akey}）**正面朝着墙**：正面方向只有 "
                        f"{clear:.2f} m 就到墙了（要 {FACE_CLEAR_M} m）。"
                        f"该资产的正面是局部 {front}，现在 yaw={math.degrees(yaw):.0f}° —— "
                        f"靠西墙用 +90、靠东墙用 −90，别抄错")
    return errs

def check_front_door_visible(key: str, layout) -> list[str]:
    """⭐ 入户门从**屋里**看得见 —— 射线打过去第一个命中必须是门扇，不能是墙。

    ⛔ 为什么要这一项（2026-08-08，Jeff 走进玄关才发现）：三个场景里有 **两个半** 把门
       画进了墙体内部。生成器的墙是**从房间矩形的边往屋内长满一个墙厚**，而三个 layout
       都把门心放在矩形边上、又让门比墙薄：
         · apt1  门 y∈[−7.51,−7.45] vs 南墙 y∈[−7.50,−7.36] → 整块埋在墙里，两面都看不见
         · house1 同病；house2 只贴在室外面，屋里看不见
       屏幕上就是一面白墙，**完全不知道哪儿是门**。而 26 项自检没有一项管过它——
       `check_no_dead_declarations` 只问"声明的东西进没进产物"，门确实在产物里，
       只是被墙挡住了。**"在产物里"不等于"看得见"。**
    ⭐ 这也是门厚改成由生成器从 `WALL_THICK` 推的原因（layout 不再有机会填错）。
    """
    d = getattr(layout, "FRONT_DOOR", None)
    if not d:
        return []
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    errs: list[str] = []
    t = layout.WALL_THICK
    x0, y0, x1, y1 = layout.ROOMS[d["room"]]["rect"]
    fixed = {"n": y1 - t / 2.0, "s": y0 + t / 2.0,
             "e": x1 - t / 2.0, "w": x0 + t / 2.0}[d["side"]]
    inward = {"n": -1.0, "s": 1.0, "e": -1.0, "w": 1.0}[d["side"]]
    horiz = d["side"] in ("n", "s")
    zb = _zbase_of(layout, d["room"])
    m = mujoco.MjModel.from_xml_path(_scene_path(key, "g1"))
    data = mujoco.MjData(m)
    mujoco.mj_forward(m, data)
    if d.get("state") == "fixed_open":
        from scenes.collision import collision_ray
        for frac in (.25, .5, .85):
            z = zb + d["height"]*frac
            for offset in (-.30, 0, .30):
                origin = [d["center"]+offset, fixed+inward*.6, z] if horiz else [fixed+inward*.6,d["center"]+offset,z]
                vec = [0.,-inward,0.] if horiz else [-inward,0.,0.]
                distance, _ = collision_ray(m,data,origin,vec)
                if 0 <= distance < 1.2:
                    _fail(errs, "固定敞开的入户门没有留下完整通行净宽")
        leaf=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,"front_door")
        if leaf < 0 or not m.geom_contype[leaf]:
            _fail(errs, "固定敞开门扇缺失或没有真实碰撞")
        return errs
    for frac in (0.25, 0.5, 0.85):           # 门下段/中段/上段各打一条
        z = zb + d["height"] * frac
        o = ([d["center"], fixed + inward * 0.6, z] if horiz
             else [fixed + inward * 0.6, d["center"], z])
        v = [0.0, -inward, 0.0] if horiz else [-inward, 0.0, 0.0]
        gid = np.zeros(1, dtype=np.int32)
        mujoco.mj_ray(m, data, np.array(o, float), np.array(v, float), None, 1, -1, gid)
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(gid[0])) or "(没打到东西)"
        if not nm.startswith("front_door"):
            _fail(errs, f"入户门在 z={z:.2f} 处从屋里看不见——射线先打到了 {nm!r}。"
                        f"门被墙挡住了（门厚必须 > WALL_THICK，见 make_house._front_door）")
    return errs


def _zbase_of(layout, room: str) -> float:
    fz = getattr(layout, "FLOOR_Z", None)
    fl = layout.ROOMS[room].get("floor", 0)
    return float(fz(fl)) if fz else 0.0

def check_reachability(key: str, layout) -> list[str]:
    """⭐⭐ 机器人到底走不走得到每间屋 —— 整层的可通行区域必须**只有一个连通块**。

    ⛔ 为什么必须有它（2026-08-08，Jeff 自己走进去才发现的）：
       `check_door_passable` 只看**门洞前后 0.6 m** 那一小段，而且当时还跳过 `kind="open"`。
       于是 apt1 的沙发把「画廊→大客厅」那个 4 m 开口堵成 0.44 m，**G1 只能到达大客厅 2%**
       （北半区 10.4 ㎡ 连落地窗带茶几整块是孤岛，正是作品集封面那个机位），
       而 48 项自检**全绿**。同一轮还照出 house1 的淋浴间被玻璃整面封死（1.84 ㎡ 的死岛）、
       次卧只剩 0.30 m 通道。
       **教训与这个仓反复踩的那条同源：查"存在一条路径"证明不了"这地方走得通"，
       得反过来查"有没有走不到的地方"。**

    算法（纯 stdlib，不要 mujoco）：
      ① 自由空间 = 各房间矩形内缩一个墙厚 ∪ 各门洞（含 kind="open" 的整段开口）；
      ② 扣掉挡路家具（精确 OBB / 圆柱）；
      ③ 两遍 chamfer 距离变换，取 dt ≥ 机器人半宽的格子 = 可站立；
      ④ 连通域标记；**每间屋都必须在最大的那个连通块里**，且自身可站立面积够一个身位。

    ⚠️ 只做**同层**连通：跨层靠楼梯，那是 `check_route` 的活。
    ⚠️ 判据用 `ROBOT_CLEARANCE` 里最宽的那台（G1 0.60），和 `check_door_passable` 同一个数——
       ⛔ 别在这里另写一个阈值。
    """
    rooms = getattr(layout, "ROOMS", {})
    if not rooms:
        return []
    errs: list[str] = []
    need = max(w for w, _f, _n in ROBOT_CLEARANCE.values())
    r_cells = (need / 2.0) / REACH_GRID_M
    t = layout.WALL_THICK
    floors = sorted({r.get("floor", 0) for r in rooms.values()})

    for floor in floors:
        here = {n: r for n, r in rooms.items() if r.get("floor", 0) == floor}
        xs = [v for r in here.values() for v in (r["rect"][0], r["rect"][2])]
        ys = [v for r in here.values() for v in (r["rect"][1], r["rect"][3])]
        x0, x1, y0, y1 = min(xs) - t, max(xs) + t, min(ys) - t, max(ys) + t
        nx = int((x1 - x0) / REACH_GRID_M) + 1
        ny = int((y1 - y0) / REACH_GRID_M) + 1

        def cx(i):  # noqa: E306
            return x0 + (i + 0.5) * REACH_GRID_M

        def cy(j):
            return y0 + (j + 0.5) * REACH_GRID_M

        # ① 自由空间：房间净空 ∪ 门洞
        free = bytearray(nx * ny)
        for r in here.values():
            a, b, c, d = r["rect"]
            for j in range(max(0, int((b + t - y0) / REACH_GRID_M)),
                           min(ny, int((d - t - y0) / REACH_GRID_M) + 1)):
                base = j * nx
                for i in range(max(0, int((a + t - x0) / REACH_GRID_M)),
                               min(nx, int((c - t - x0) / REACH_GRID_M) + 1)):
                    free[base + i] = 1
        for door in getattr(layout, "DOORS", []):
            if door.get("floor", floor) != floor and "floor" in door:
                continue
            c0, w, co = door["center"], door["width"], door["coord"]
            horiz = door["orient"] == "h"
            # 洞口沿墙方向 = 门宽；穿墙方向 = 两侧各一个墙厚（两间屋各自的墙都要打通）
            ax0, ax1 = (c0 - w / 2, c0 + w / 2) if horiz else (co - t * 1.5, co + t * 1.5)
            ay0, ay1 = (co - t * 1.5, co + t * 1.5) if horiz else (c0 - w / 2, c0 + w / 2)
            for j in range(max(0, int((ay0 - y0) / REACH_GRID_M)),
                           min(ny, int((ay1 - y0) / REACH_GRID_M) + 1)):
                base = j * nx
                for i in range(max(0, int((ax0 - x0) / REACH_GRID_M)),
                               min(nx, int((ax1 - x0) / REACH_GRID_M) + 1)):
                    free[base + i] = 1

        # ② 扣掉挡路家具：只遍历它自己那一小块窗口，别扫全场
        for ob in _reach_obstacles(layout, floor):
            ex = ob[3] if ob[0] == "cyl" else math.hypot(ob[3], ob[4])
            ocx, ocy = ob[1], ob[2]
            for j in range(max(0, int((ocy - ex - y0) / REACH_GRID_M)),
                           min(ny, int((ocy + ex - y0) / REACH_GRID_M) + 2)):
                base = j * nx
                yy = cy(j)
                for i in range(max(0, int((ocx - ex - x0) / REACH_GRID_M)),
                               min(nx, int((ocx + ex - x0) / REACH_GRID_M) + 2)):
                    if free[base + i] and _obstacle_dist(ob, cx(i), yy) <= 0.0:
                        free[base + i] = 0

        # ③ chamfer 距离变换（两遍，(3,4)/3 近似），单位=格
        BIG = 10 ** 6
        dt = [0 if free[k] == 0 else BIG for k in range(nx * ny)]
        for j in range(ny):
            base = j * nx
            for i in range(nx):
                k = base + i
                if dt[k] == 0:
                    continue
                v = dt[k]
                if i: v = min(v, dt[k - 1] + 3)
                if j: v = min(v, dt[k - nx] + 3)
                if i and j: v = min(v, dt[k - nx - 1] + 4)
                if i < nx - 1 and j: v = min(v, dt[k - nx + 1] + 4)
                dt[k] = v
        for j in range(ny - 1, -1, -1):
            base = j * nx
            for i in range(nx - 1, -1, -1):
                k = base + i
                if dt[k] == 0:
                    continue
                v = dt[k]
                if i < nx - 1: v = min(v, dt[k + 1] + 3)
                if j < ny - 1: v = min(v, dt[k + nx] + 3)
                if i < nx - 1 and j < ny - 1: v = min(v, dt[k + nx + 1] + 4)
                if i and j < ny - 1: v = min(v, dt[k + nx - 1] + 4)
                dt[k] = v
        thr = r_cells * 3.0        # chamfer 的单位是 3/格
        walk = bytearray(1 if dt[k] >= thr else 0 for k in range(nx * ny))

        # ④ 连通域
        comp = [-1] * (nx * ny)
        sizes = []
        for start in range(nx * ny):
            if not walk[start] or comp[start] >= 0:
                continue
            cid = len(sizes)
            stack, n = [start], 0
            comp[start] = cid
            while stack:
                k = stack.pop()
                n += 1
                i, j = k % nx, k // nx
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ii, jj = i + di, j + dj
                    if 0 <= ii < nx and 0 <= jj < ny:
                        kk = jj * nx + ii
                        if walk[kk] and comp[kk] < 0:
                            comp[kk] = cid
                            stack.append(kk)
            sizes.append(n)
        if not sizes:
            _fail(errs, f"{_floor_tag(floors, floor)}整层没有任何可站立的格子（判据 {need:.2f} m）")
            continue
        main = max(range(len(sizes)), key=lambda c: sizes[c])

        cell_a = REACH_GRID_M ** 2

        # ⭐⭐ 判据：**整层只准有一个够大的连通块**。
        # ⛔ 第一版写的是「每间屋只要有一个可站立格子在主连通块里就算过」——太松，
        #    故障注入当场打脸：把 apt1 的沙发挪回堵门的旧位置，大客厅南缘仍留着一条
        #    y≈2.50 的窄带连着画廊，于是"有格子在主块里"成立、检查报绿，
        #    而北边那 10 ㎡（落地窗 + 茶几 + 两把单椅，正是作品集封面那个机位）是**孤岛**。
        #    ⭐ 这正是本仓那条老教训的又一次现形：**查"存在一条路径"证明不了"这地方走得通"**，
        #    必须反过来查"有没有走不到的地方"。
        # ⚠️ 小于一个身位的碎块忽略（栅格化边角、家具缝里的零星格子），否则全是噪声。
        islands = [(c, n) for c, n in enumerate(sizes)
                   if c != main and n * cell_a >= REACH_MIN_AREA_M2]
        for cid, n in sorted(islands, key=lambda kv: -kv[1]):
            where = collections.Counter()
            for k in range(nx * ny):
                if comp[k] == cid:
                    nm = _room_of(here, x0 + (k % nx + 0.5) * REACH_GRID_M,
                                  y0 + (k // nx + 0.5) * REACH_GRID_M)
                    if nm:
                        where[here[nm].get("label", nm)] += 1
            spots = "、".join(f"{lb}" for lb, _ in where.most_common(3)) or "屋外"
            _fail(errs, f"{_floor_tag(floors, floor)}有一块 {n * cell_a:.2f} ㎡ 的地方"
                        f"**机器人走不进去**（在 {spots}）——和主通行区断开了。"
                        f"判据：{need:.2f} m 净宽（{_widest_robot()}）")

        # 每间屋自己也得站得下一个身位
        for name, r in sorted(here.items()):
            a, b, c, d = r["rect"]
            own = 0
            for j in range(max(0, int((b - y0) / REACH_GRID_M)),
                           min(ny, int((d - y0) / REACH_GRID_M) + 1)):
                base = j * nx
                for i in range(max(0, int((a - x0) / REACH_GRID_M)),
                               min(nx, int((c - x0) / REACH_GRID_M) + 1)):
                    if walk[base + i]:
                        own += 1
            if own * cell_a < REACH_MIN_AREA_M2:
                _fail(errs, f"{_floor_tag(floors, floor)}「{r.get('label', name)}」({name}) "
                            f"里几乎站不下机器人：可站立面积只有 {own * cell_a:.2f} ㎡"
                            f"（判据 {need:.2f} m 宽）")
    return errs


def _room_of(here: dict, x: float, y: float):
    for nm, r in here.items():
        a, b, c, d = r["rect"]
        if a <= x <= c and b <= y <= d:
            return nm
    return None


def _widest_robot() -> str:
    k, (w, _f, _n) = max(ROBOT_CLEARANCE.items(), key=lambda kv: kv[1][0])
    return f"最宽的是 {k}，{w:.2f} m"


def _floor_tag(floors: list, floor: int) -> str:
    return f"{floor} 层：" if len(floors) > 1 else ""

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


# 小于这个量的重叠不算数（毫米级的贴合摆放是建模常态，比如花瓶正好放在柜面上）。
OVERLAP_TOL = 0.005

# ⭐ 允许互相插进去的家具对 —— **登记制**，一行一个理由。
# ⛔ 往这儿加之前先问一句：这是"设计就该这样"，还是"我懒得改"？只有前者能进。
#    没有理由的例外会让这道闸门在两年内退化成一张永远全绿的白名单。
# 名字里的 `*` 是前缀通配（`gr_ch*` 一次盖住两把扶手椅）。
FURNITURE_MAY_OVERLAP = [
    # 嵌入式电器本来就是嵌进台面/吊柜里的，这是厨房的做法不是错
    ("kt_counter", "kt_range", "嵌入式灶具嵌在台面里"),
    ("kt_counter", "kt_sink", "水槽嵌在台面里"),
    ("kt_counter_top", "kt_range", "同上，台面板那一层"),
    ("kt_counter_top", "kt_sink", "同上，台面板那一层"),
    ("kt_upper", "kt_hood", "抽油烟机嵌在吊柜中间"),
    ("a2i_island_top_*", "a2_sink", "水槽边缘搭接开孔四周的石材；台面没有跨过池盆，龙头行程另做物理验证"),
    # 软装：抱枕本来就该陷进沙发里
    ("gr_sofa_back", "gr_pillows", "抱枕靠在沙发背上"),
    ("gr_sofa_arm*", "gr_pillows", "抱枕挨着扶手"),
    # 地毯是平铺的，家具**站在它上面**，重叠量 = 地毯厚度
    ("gr_rug", "gr_coffee", "茶几站在地毯上"),
    ("gr_rug", "gr_ch*", "扶手椅站在地毯上"),
]


def _overlap_allowed(a: str, b: str) -> bool:
    """这一对是不是登记过的合法重叠（顺序无关，支持 `前缀*` 通配）。"""
    def hit(pat: str, name: str) -> bool:
        return name.startswith(pat[:-1]) if pat.endswith("*") else name == pat
    return any((hit(p, a) and hit(q, b)) or (hit(p, b) and hit(q, a))
               for p, q, _why in FURNITURE_MAY_OVERLAP)


def check_furniture_overlap(key: str, layout) -> list[str]:
    """⭐⭐ 穿了真网格外衣的家具，不许和别的家具插在一起。

    ⚠️ 判据**故意很窄**，因为宽判据完全不可用：拿"任意两件家具的包围盒相交"去查，
       三个场景分别命中 193 / 104 / 71 对，而绝大多数是**合法**的——沙发是底座+靠背+
       扶手拼出来的、植物是树干+叶片、浴缸是外壳+内胆、马桶带水箱。逐对报数只会淹死人。
       （同样的教训 v0.12 在"逐缝报净宽"上刚吃过一次。）
    ⭐ 所以只查**至少一件穿了真网格外衣**的组合：外衣是照着真家具建模的，插进别的东西里
       在画面上一眼可见（2026-08-08 就是 Jeff 看截图发现餐椅靠背穿过桌面的），
       而白盒子之间的重叠往往是建模手法。同一件家具的零件靠名字前缀排除。
       实测这么一收：house1 / house2 **零命中**，apt1 只剩 10 对且全部登记在案。
    ⛔ 例外走 `FURNITURE_MAY_OVERLAP`，一行一个理由。

    背景：apt1 的两把端餐椅曾整个插进桌面板 0.18 m —— 边椅按"桌沿留 0.30"摆、
    端椅却按"留 0.05"摆，一套家具两套余量。**当时 22 项自检一条都没红**，
    因为没有任何一项管家具之间的关系。
    """
    errs: list[str] = []
    items = [it for it in layout.FURNITURE if it["type"] in ("box", "cylinder", "sphere")]
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a["room"] != b["room"]:
                continue
            if not ((a.get("mesh") or {}).get("id") or (b.get("mesh") or {}).get("id")):
                continue                       # 两件都是白盒子 → 多半是拼件，不管
            na, nb = a["name"], b["name"]
            if na.startswith(nb) or nb.startswith(na):
                continue                       # 同一件家具的零件（名字共前缀）
            if _overlap_allowed(na, nb):
                continue
            ax0, ax1, ay0, ay1 = _yaw_aabb(a)
            bx0, bx1, by0, by1 = _yaw_aabb(b)
            az0, az1 = a["pos"][2] - a["size"][2] / 2, a["pos"][2] + a["size"][2] / 2
            bz0, bz1 = b["pos"][2] - b["size"][2] / 2, b["pos"][2] + b["size"][2] / 2
            ov = min(min(ax1, bx1) - max(ax0, bx0),
                     min(ay1, by1) - max(ay0, by0),
                     min(az1, bz1) - max(az0, bz0))
            if ov > OVERLAP_TOL:
                _fail(errs, f"家具 {na} 和 {nb}（{a['room']}）插在一起 {ov * 100:.1f} cm"
                            f"——真网格会明显穿模。要么挪开，要么去 "
                            f"FURNITURE_MAY_OVERLAP 登记并写明理由")
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
    for robot in _modelled_robots():
        path = _scene_path(key, robot)
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
    for robot in _modelled_robots():
        path = _scene_path(key, robot)
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
                # ⭐ 按 MuJoCo 自己的规则解析：`<texture file>` 走 texturedir（本仓没设），
                #    即相对**这份 XML 所在的目录**。⛔ 别写成仓根——那是在这里复制一份
                #    MuJoCo 的规则，产物换一层目录就悄悄判错（产物 v0.10 挪进了 build/）。
                if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(path), v))):
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
    for robot in _modelled_robots():
        path = _scene_path(key, robot)
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
    path = _scene_path(key, "g1")
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
                origin = np.array([cx, cy, z + _zbase_of(layout, room)])
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

    ⭐ **开了 `collide=True` 的家具走另一条判据**（2026-08-22 加）：它没有包络盒，
       碰撞真相是一组 CoACD 凸块（`furn_<件>__h<N>`）。对这种件，改判
       **网格的包围盒必须落在凸块并集的包围盒里**。
       ⚠️ 这条判据看着比逐顶点弱，但它精准盯住**真正会出的那个错**：
       视觉网格和凸块用的是同一个 `_mesh_placement()`，两者本来就重合；
       唯一现实的失效方式是有人把那两处变换改分家了——而变换一分家，
       包围盒立刻整体平移或缩放，这条当场就红。
       ⭐ 水平方向另有 `check_decor_ray_invariance` 兜着（实测 180 条射线里
       第一个命中是 `dg_` 的次数为 0，说明凸块确实把网格整个裹住了）。
    """
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    path = _scene_path(key, "g1")
    if not os.path.exists(path):
        return []
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    boxes: dict[str, int] = {}
    hulls: dict[str, list[int]] = {}
    meshes: dict[str, list[int]] = {}
    for g in range(m.ngeom):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if nm.startswith("furn_"):
            stem = nm[len("furn_"):]
            if "__h" in stem:                       # furn_<家具名>__h<第几块>
                hulls.setdefault(stem.split("__h", 1)[0], []).append(g)
            else:
                boxes[stem] = g
        elif nm.startswith("dg_"):
            # dg_<家具名>_<部件下标>
            meshes.setdefault(nm[len("dg_"):].rsplit("_", 1)[0], []).append(g)

    def _world_aabb(gids):
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        for g in gids:
            mid = m.geom_dataid[g]
            v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
            w = v @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
            lo, hi = np.minimum(lo, w.min(axis=0)), np.maximum(hi, w.max(axis=0))
        return lo, hi

    errs: list[str] = []
    articulated = {i['name'] for i in layout.FURNITURE if i.get('articulated')}
    for item, gids in sorted(meshes.items()):
        if item in articulated:
            # Articulated pieces deliberately have no enclosing box: a door
            # must carry its own visual and analytic collision geometry.
            root = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'ix_' + item)
            if root < 0:
                _fail(errs, f'Articulated furniture {item} has no body tree')
                continue
            for g in gids:
                body = int(m.geom_bodyid[g])
                ancestor = body
                while ancestor and ancestor != root:
                    ancestor = int(m.body_parentid[ancestor])
                if ancestor != root:
                    _fail(errs, f'Articulated visual {m.geom(g).name} is outside its body tree')
                # Glass can be a fixed child of the corresponding door.
                collision_body = body
                colliders = []
                while collision_body and collision_body != root:
                    colliders = [c for c in range(m.ngeom) if m.geom_bodyid[c] == collision_body
                                 and (m.geom_contype[c] or m.geom_conaffinity[c])]
                    if colliders:
                        break
                    if m.body_jntnum[collision_body]:
                        break
                    collision_body = int(m.body_parentid[collision_body])
                if not colliders:
                    _fail(errs, f'Articulated visual {m.geom(g).name} has no attached collider')
            continue
        hg = hulls.get(item)
        if hg:
            # ⭐ 真碰撞体那条路：网格包围盒必须在凸块并集的包围盒里（理由见 docstring）
            mlo, mhi = _world_aabb(gids)
            hlo, hhi = _world_aabb(hg)
            out = np.maximum(mhi - hhi, hlo - mlo)
            if float(out.max()) > _HULL_AABB_TOL:
                ax = int(out.argmax())
                _fail(errs, f"装饰 {item} 的网格探出 CoACD 凸块并集 "
                            f"{float(out.max()) * 1000:.1f} mm（{'xyz'[ax]} 轴）"
                            f"—— 八成是视觉外衣和凸块用了不同的变换，"
                            f"去看 make_house._mesh_placement 是不是被拆成了两份")
            continue
        b = boxes.get(item)
        if b is None:
            _fail(errs, f"装饰 {item} 既没有碰撞盒 furn_{item}，也没有凸块 furn_{item}__h*")
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


def check_collision_solref(key: str, layout) -> list[str]:
    """⛔ 每一块 CoACD 碰撞凸块都必须带硬化过的 `solref` —— 不带就会被高速撞击穿透。

    ⭐ 为什么单列一道门：这是本仓典型的**静默坑**。用 MuJoCo 默认接触时，
       3.9 kg 的板从 1.20 m 砸到 49 mm 厚的座面凸块上会**直接穿过去落到地上**
       （2026-08-22 实测；阈值很陡——每步位移 3.2 mm 还好、4.1 mm 就穿）。
       而**编译不报错、慢速放置全绿**：机器人慢慢坐下去一切正常，摔一跤砸上去就穿模。
    ⚠️ 减小时间步没用、加 `margin` 也没用，都实测过。只有硬化 `solref` 有效。
    ⚠️ 这不是"几何太薄"：凸块最薄边 30 mm、座面那块 49 mm。是接触刚度的问题。

    判据取 `decor.lock.HULL_SOLREF` 的**时间常数**：产物里写的必须不比它软
    （更小 = 更硬 = 可以）。⛔ 别在这里写第二个字面量，那个数只有一处真相源。
    """
    try:
        import mujoco
    except ImportError:
        return ["(跳过) 没装 mujoco"]
    try:
        from decor import lock
    except ImportError:
        return ["(跳过) 没有 decor 包"]
    path = _scene_path(key, "g1")
    if not os.path.exists(path):
        return []
    want = float(str(lock.HULL_SOLREF).split()[0])
    m = mujoco.MjModel.from_xml_path(path)
    errs: list[str] = []
    for g in range(m.ngeom):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if "__h" not in nm or not nm.startswith("furn_"):
            continue
        got = float(m.geom_solref[g][0])
        if got > want + 1e-9:
            _fail(errs, f"碰撞凸块 {nm} 的 solref 时间常数是 {got:g}，比要求的 {want:g} 软"
                        f"——高速撞击会穿过去，而且慢速测试全绿。"
                        f"⛔ 去看 make_house._hull_geoms 有没有漏写 solref")
            break                      # 一件报一次就够，不刷屏
    return errs


def check_seat_reachable(key: str, layout) -> list[str]:
    """⭐ 声明了「能坐」的家具，必须**真的坐得下** —— 用射线量，不看声明。

    三条判据：

      1. **座面高度 ≤ SEAT_MAX_H**：俯视射线在座位区量到的最高实体面。
         实测 G1 坐姿保持 3 秒：0.30 ✅ / 0.35 ✅ / 0.40 ❌ 滑落 / 0.45 ❌ 直接倒。
      2. **座面上方留得下上半身**：座面往上 SEAT_HEADROOM 之内不许有实体。
         抓的是"靠背前伸盖住了座面""吊灯挂太低""上面压着一块楼板"这类。
      3. **（可选）座面下方是空的** —— `"under_clear": True` 才查。

    ⚠️ 第 3 条**默认不查**，这是想清楚之后的选择，不是偷懒：
       人坐下时小腿是竖直的、脚落在座面**前沿之外**，根本不需要把脚伸到座面底下。
       所以一张**整体软包到地**的沙发（底下是实的）照样坐得住，是完全合法的做法。
       只有餐椅、书桌椅这类"要把脚往里收"的才该开这一条。
       ⛔ 别为了"更严格"给沙发也开——那会把一个正确的家具判成红的，
       而假红比不查更坏：它会逼着后来的人去改本来对的东西。

    layout 里怎么声明：
        SEATS = [{"name": "gr_sofa", "room": "great_room", "at": (x, y),
                  "span": (w, d), "under_clear": False}, ...]
    没声明 `SEATS` 的场景直接跳过（house1 / house2 / apt1 都没有）。
    """
    seats = getattr(layout, "SEATS", None)
    if not seats:
        return []
    try:
        import mujoco
        import numpy as np
    except ImportError:
        return ["(跳过) 没装 mujoco/numpy"]
    path = _scene_path(key, "g1")
    if not os.path.exists(path):
        return []
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gid = np.zeros(1, np.int32)
    errs: list[str] = []
    for s in seats:
        cx, cy = s["at"]
        w, dep = s.get("span", (0.30, 0.30))
        zb = _zbase_of(layout, s["room"]) if s.get("room") else 0.0
        # ① 座面高度：在座位区打一圈俯视射线，取**最高**的那个实体面
        tops = []
        for ux in np.linspace(-w / 2, w / 2, 5):
            for uy in np.linspace(-dep / 2, dep / 2, 5):
                o = np.array([cx + ux, cy + uy, zb + 2.0])
                dist = mujoco.mj_ray(m, d, o, np.array([0.0, 0.0, -1.0]), None, 1, -1, gid)
                if dist >= 0:
                    tops.append(zb + 2.0 - dist)
        if not tops:
            _fail(errs, f"坐具 {s['name']}：座位区往下打射线什么都没打到，座面根本不存在")
            continue
        top = max(tops)
        if top - zb > SEAT_MAX_H:
            _fail(errs, f"坐具 {s['name']} 的座面高 {(top - zb) * 100:.1f} cm > "
                        f"{SEAT_MAX_H * 100:.0f} cm —— G1 坐上去会滑落"
                        f"（实测 0.40 m 就滑、0.45 m 直接倒）")
        # ② 座面上方要留得下上半身 —— 从座面往上打，第一个实体必须够高
        low = 9e9
        for ux in np.linspace(-w / 2, w / 2, 3):
            for uy in np.linspace(-dep / 2, dep / 2, 3):
                o = np.array([cx + ux, cy + uy, top + 0.02])
                dist = mujoco.mj_ray(m, d, o, np.array([0.0, 0.0, 1.0]), None, 1, -1, gid)
                if dist >= 0:
                    low = min(low, dist + 0.02)
        if low < SEAT_HEADROOM:
            _fail(errs, f"坐具 {s['name']} 座面上方只有 {low * 100:.0f} cm 净空 "
                        f"< {SEAT_HEADROOM * 100:.0f} cm —— 上半身坐不进去"
                        f"（靠背前伸？上面压着楼板或灯？）")
        # ③ 座面下方是不是空的 —— ⚠️ 只在这件家具**声明要查**时才查，理由见 docstring
        if s.get("under_clear"):
            half = max(w, dep) / 2 + 0.60
            blocked = 0
            for uy in np.linspace(-dep / 2, dep / 2, 5):
                o = np.array([cx - half, cy + uy, zb + SEAT_CLEAR_Z])
                dist = mujoco.mj_ray(m, d, o, np.array([1.0, 0.0, 0.0]), None, 1, -1, gid)
                if 0 <= dist <= 2 * half:
                    blocked += 1
            if blocked == 5:
                _fail(errs, f"坐具 {s['name']} 的座面下方 {SEAT_CLEAR_Z * 100:.0f} cm 处全被挡住"
                            f"——碰撞体退化成一个实心盒了，脚收不进去。"
                            f"⛔ 这件是不是漏了 collide=True，或者凸块字节不在磁盘上？")
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
    path = _scene_path(key, "g1")
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

    # ⭐ 开了 `collide=True` 的家具**没有包络盒**（碰撞真相是一组凸块），
    #    所以上面那张 box 清单里找不到它们，采样点会落进椅子肚子里。
    #    ⇒ 补上它们**声明的**外廓。用声明而不是去量凸块，是因为声明本来就是
    #    「关着门的保守外廓」，`check_reachability` 那几道读的也是它——同一个真相源。
    # ⚠️ 2026-08-22 实测踩到：餐椅间距 0.80 m，而绕单椅打的那圈射线半径 0.96 m，
    #    起点正好落在**隔壁那把椅子**里，于是每一发都先撞上邻居的网格，报一串假阳性。
    decl_solids = []
    for it in layout.FURNITURE:
        if not (it.get("mesh") or {}).get("collide"):
            continue
        px, py, pz = it["pos"]
        sx, sy, sz = it["size"]
        yaw = math.radians(float(it["mesh"].get("yaw", 0.0)))
        decl_solids.append((np.array([px, py, pz + _zbase_of(layout, it["room"])]),
                            np.array([sx / 2, sy / 2, sz / 2]), math.cos(yaw), math.sin(yaw)))

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
        for c, h, ca, sa in decl_solids:
            dxy = p - c
            qx = dxy[0] * ca + dxy[1] * sa          # 转进家具自己的局部系
            qy = -dxy[0] * sa + dxy[1] * ca
            if (abs(qx) <= h[0] + 0.02 and abs(qy) <= h[1] + 0.02
                    and abs(dxy[2]) <= h[2] + 0.02):
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
    path = _scene_path(key, "g1")
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
    path = _scene_path(key, "g1")
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
    path = _scene_path(key, "g1")
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

    path = _scene_path(key, "g1")
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



def check_time_presets(key: str, layout) -> list[str]:
    """四时段光照预设（LIGHTS_BY_TIME）的静态自洽。⛔ 纯 Python 不碰 mujoco——
    本仓缺依赖时多项是「跳过 ⚠️」语义，这一项必须在裸环境也能真红。

    预设是「产物之上的一层受约束补丁」：引用的灯名/材质名/贴图文件必须已存在、
    不能凭空创造；灯数不超渲染预算；sun_sse 不许挪方位（阴影贴图坑）；
    glass alpha 不许 ≤0.02（mj_ray 挖空坑）；day 必须是空 dict（产物即白天真相）。
    没声明 LIGHTS_BY_TIME 的场景不受此检（约束随声明而生）。
    """
    presets = getattr(layout, "LIGHTS_BY_TIME", None)
    if presets is None:
        return []
    errs: list[str] = []
    budget = getattr(layout, "LIGHT_BUDGET", 7)
    xml = open(_scene_path(key, "g1"), encoding="utf-8").read()   # 灯/材质名两台机器人产物相同，核一份即可
    import re as _re
    light_names = set(_re.findall(r'<light name="([^"]+)"', xml))
    mat_names = set(_re.findall(r'<material name="([^"]+)"', xml))
    if presets.get("day"):
        _fail(errs, "day 预设必须是空 dict——「产物即白天真相」是定义不是口头承诺")
    for phase, spec in presets.items():
        if not spec:
            continue
        lights = spec.get("lights", {})
        if len(lights) > budget:
            _fail(errs, f"{phase}: {len(lights)} 盏灯超预算 {budget}"
                        "（渲染器只点亮 headlight+7 盏，多的静默不亮）")
        for name, attrs in lights.items():
            if name not in light_names:
                _fail(errs, f"{phase}: 灯 {name!r} 不在产物里——预设不能凭空创造")
            if name == "sun_sse" and ("pos" in attrs or "dir" in attrs):
                _fail(errs, f"{phase}: ⛔ sun_sse 的方位不许动（方向光穿玻璃 = 阴影贴图坑），"
                            "只准调色/强度/castshadow")
        for name in spec.get("lights_off", ()):
            if name not in light_names:
                _fail(errs, f"{phase}: lights_off 里的 {name!r} 不在产物里")
        for name in spec.get("materials", {}):
            if name not in mat_names:
                _fail(errs, f"{phase}: 材质 {name!r} 不在产物里")
        glass = spec.get("glass")
        if glass:
            try:
                alpha = float(str(glass["rgba"]).split()[3])
            except Exception:
                alpha = -1.0
            if alpha <= 0.02:
                _fail(errs, f"{phase}: ⛔ 玻璃 alpha={alpha} ≤0.02"
                            "（alpha=0 曾让 mj_ray 挖空碰撞盒——232 米自由落体坑）")
            if glass.get("bind_material") not in mat_names:
                _fail(errs, f"{phase}: glass.bind_material 不在产物里")
        sky = spec.get("sky")
        if sky:
            for a in ("fileright", "fileleft", "fileup", "filedown", "filefront", "fileback"):
                pth = os.path.join(ROOT, "textures", "house3", f"sky_{sky}_{a}.png")
                if not os.path.isfile(pth):
                    _fail(errs, f"{phase}: 天空盒面缺文件 {os.path.relpath(pth, ROOT)}"
                                "（先跑 tools/make_view.py --sky --sky-phase <时段>）")
        for tex_name, night_file in spec.get("textures", {}).items():
            decl = next((t for t in getattr(layout, "TEXTURES_EXTRA", ())
                         if t.get("name") == tex_name), None)
            if decl is None:
                _fail(errs, f"{phase}: textures 引用了 TEXTURES_EXTRA 没有的 {tex_name!r}")
                continue
            pth = os.path.join(ROOT, os.path.dirname(decl["file"]), night_file)
            if not os.path.isfile(pth):
                _fail(errs, f"{phase}: 换装贴图缺文件 {os.path.relpath(pth, ROOT)}")
        for tint in spec.get("geom_tint", ()):
            if tint.get("where") not in getattr(layout, "GEOM_BANDS", {}):
                _fail(errs, f"{phase}: geom_tint 的 where={tint.get('where')!r} 不在 GEOM_BANDS 里")
    return errs



def check_lights_render(key: str, layout) -> list[str]:
    """⛔ 渲染器只点亮 headlight + 前 7 盏 active 模型灯（2026-08-09 逐盏关灯实测，
    第 8 盏起受影响像素 = 0.000%）。`mjMAXLIGHT=100` 是 mjvScene 的容量不是渲染能力。

    从**产物**数灯（⛔ 不能数 len(L.LIGHTS)——机器人 include 也带灯，layout 看不见）。
    超预算的灯不会报错、只是静默不亮——这道门把静默变成红。
    ⚠️ 本门首次加入时三个场景都超（apt1 11 / house1 14 / house2 13，各有 3–7 盏
    从来没亮过的死灯，含 house1/2 那盏「让窗外草地亮起来」的 sun）——这是存量 bug，
    修灯要重排 LIGHTS + 重跑产物 + 重出 README 配图，单独一个 commit 做。
    """
    errs: list[str] = []
    budget = getattr(layout, "LIGHT_BUDGET", 7)
    import re as _re
    for robot in ("g1", "go2"):
        xml = open(_scene_path(key, robot), encoding="utf-8").read()
        scene_lights = _re.findall(r'<light[^>]*name="([^"]+)"', xml)
        inc = _re.search(r'<include file="([^"]+)"', xml)
        robot_lights = 0
        if inc:
            rp = os.path.normpath(os.path.join(os.path.dirname(_scene_path(key, robot)),
                                               inc.group(1)))
            if os.path.isfile(rp):
                robot_lights = open(rp, encoding="utf-8").read().count("<light")
        total = len(scene_lights) + robot_lights
        if total > 1 + budget:
            dead = scene_lights[budget - robot_lights + 1 - 1:]
            _fail(errs, f"{key}-{robot}: 共 {total} 盏灯（场景 {len(scene_lights)} + "
                        f"机器人 {robot_lights}）> 渲染上限 {1 + budget}；"
                        f"排在后面的静默不亮：{', '.join(dead)}")
    return errs


CHECKS = [
    ("layout 契约完整", check_contract),
    ("产物是合法 XML", check_wellformed),
    ("⭐ 引用的材质/贴图都真的存在", check_assets),
    ("⭐ 四时段光照预设自洽（声明了才检）", check_time_presets),
    ("⛔ 灯数没超渲染器上限（headlight+7）", check_lights_render),
    ("⭐⭐ decor.lock 自洽（offset±half ⇄ size）", check_lock_reconciles),
    ("⛔ geom 数没超渲染缓冲", check_geom_budget),
    ("产物能被 MuJoCo 加载", check_loads),
    ("楼梯爬满一层 + 尺寸合规", check_stairs),
    ("⭐ 四个接头闭合（梯段 ↔ 平台）", check_joints),
    ("门宽够机器人过", check_doors),
    ("⭐⭐ 门真的走得过去（两侧在屋里 + 净通行宽）", check_door_passable),
    ("⭐⭐ 每间屋机器人都走得进去（可通行性）", check_reachability),
    ("⭐ 家具没有捅穿墙伸进隔壁", check_furniture_not_through_wall),
    ("⭐⭐ 家具之间没有插在一起", check_furniture_overlap),
    ("⭐ 声明的东西都真的进了产物", check_no_dead_declarations),
    ("⭐ 入户门从屋里看得见", check_front_door_visible),
    ("⭐ 贴墙家具的正面没朝着墙", check_mesh_faces_room),
    ("挂画没压在门窗洞口上", check_art_clear),
    ("⭐ 望公园的视线没被挡 + 远景没被裁", check_park_sightline),
    ("⛔ 朝外的房间往外都撞得到实体", check_void),
    ("⭐⭐ 装饰网格都带 UV（不是单色块）", check_mesh_has_uv),
    ("⭐⭐ 装饰网格整个装在碰撞盒/凸块里", check_decor_inside_box),
    ("⭐⭐ 装饰网格没改变任何射线读数", check_decor_ray_invariance),
    ("⛔ 碰撞凸块都硬化过 solref（不然高速撞击穿模）", check_collision_solref),
    ("⭐ 声明能坐的家具真的坐得下（座面高 + 座下净空）", check_seat_reachable),
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
