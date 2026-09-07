#!/usr/bin/env python3
"""由 layout.py 生成屋子场景 house-<机器人>.xml（MJCF）。

照搬 locomotion 仓 scenes/mujoco/make_building.py 的思路：几何不在 XML 里手写，
而是从**一份布局定义**翻译出来——改屋子只改 layout.py，场景与世界服务同时生效。

产物 house-<机器人>.xml = 完整可跑模型：
  十二个空间（地板 / 带门窗洞的墙 / 门框窗框 / 家具 / 灯）
  + 屋外景色（草地、树、远处楼房，从窗口望得见）
  + `<include>` 进来的那台机器人（带头部前视相机）

**一台机器人一份场景文件**：机器人的网格路径（meshdir）在编译期就定死了，
两台机器人塞不进同一份 MJCF。所以按机器人各生成一份，谁也不挤谁。
机器人清单见 `robots/manifest.py`。

用法：
    python tools/make_house.py                 # 全部机器人各生成一份
    python tools/make_house.py --robot g1      # 只生成人形那份
    python tools/make_house.py --robot go2 --out 别处.xml

⚠️ 单位换算只在这里做一次：layout.py 写的是**全长**，MJCF 的 box/cylinder size 要**半长**。
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
sys.path.insert(0, ROOT)

from scenes import manifest as SCENES  # noqa: E402

# 当前正在生成的场景的 layout 模块。build() 会按 --scene 换掉它。
# ⚠️ 之所以是模块级变量而不是参数：本文件里几十个 _xxx_geom() 帮手都读 L.*，
# 一个个加参数会把这次重构变成一次重写。换场景走 use_scene()，它是唯一的写入点。
L = SCENES.load_layout(SCENES.DEFAULT_SCENE)


def use_scene(scene_key: str) -> None:
    """切换到另一个场景的 layout。生成器的所有帮手都读模块级的 L。"""
    global L
    L = SCENES.load_layout(scene_key)

# 机器人清单住在仓根的 robots/manifest.py（跨场景共用），按路径加载——
# 仓根不是包，import 不到，只能按路径加载。
_spec = importlib.util.spec_from_file_location(
    "alice_robots", os.path.join(ROOT, "robots", "manifest.py"))
ROBOTS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ROBOTS)

# 离屏渲染缓冲上限（决定最大可渲染分辨率）。留足 1080p，够出写真与报告插图。
OFFSCREEN_W, OFFSCREEN_H = 1920, 1080


def _half(v: float) -> float:
    """全长 → 半长（MJCF size 要半长）。"""
    return v / 2.0


def _rgba(c) -> str:
    return " ".join(f"{v:g}" for v in c)


def yaw_quat(yaw_deg: float):
    """绕 z 轴转 yaw（**度**）对应的四元数 (w, x, y, z)。

    ⛔ 为什么旋转一律走 quat 而不是 euler：`<compiler angle="...">` 是**整个编译模型全局**的，
       而它来自 include 进来的机器人 XML（robots/g1/g1.xml、robots/go2/go2.xml 都写着
       angle="radian"）。也就是说 `euler="0 0 90"` 会被当成 **90 弧度**读，不是 90 度。
       2026-08-05 实测：本仓所有家具的朝向因此全是错的——本该 180° 的椅子实际是 −126.76°，
       本该 90° 的实际是 116.62°。
       四元数**没有单位**，换谁当机器人、上游哪天改了 angle 都不会再错一次。
    """
    a = math.radians(yaw_deg) / 2.0
    return (math.cos(a), 0.0, 0.0, math.sin(a))


def _box(name: str, pos, size, rgba, extra: str = "", mat: str = "",
         euler=None, quat=None, group: int = 0) -> str:
    """一个 box geom（size 传全长，这里统一折半）。给了 mat 就用材质，否则用纯色。

    旋转二选一：`quat`（首选，无单位）或 `euler`。
    ⚠️ `euler` 的单位跟随全局 `<compiler angle>`，本模型是**弧度**（见 yaw_quat 的说明）。
       只有 `_stair_rails` 还在用它，因为它本来算出来的就是弧度。新代码一律用 quat。
    """
    if euler is not None and quat is not None:
        raise ValueError(f"geom {name!r} 同时给了 euler 和 quat，只能给一个")
    look = f'material="{mat}"' if mat else f'rgba="{_rgba(rgba)}"'
    rot = _rot_attr(euler, quat)
    # `group` 只管画不画（默认渲染器只画 0–2 组），**不影响碰撞，也不影响 mj_ray**。
    grp = f' group="{group}"' if group else ""
    return (f'    <geom name="{name}" type="box" '
            f'size="{_half(size[0]):g} {_half(size[1]):g} {_half(size[2]):g}" '
            f'pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}"{rot} {look}{grp}{extra}/>')


def _rot_attr(euler=None, quat=None) -> str:
    """把旋转渲染成 XML 属性串；两个都没有就返回空串。

    ⚠️ 四元数分量按 1e-12 归零：cos(180°/2) 算出来是 6.12e-17 而不是 0，
       原样写进产物既难读、又让 diff 里出现一串无意义的科学计数法。
       1e-12 远小于任何有意义的旋转（1e-12 rad ≈ 6e-11 度），归零不改变几何。
    """
    if quat is not None:
        q = [0.0 if abs(v) < 1e-12 else v for v in quat]
        return f' quat="{q[0]:g} {q[1]:g} {q[2]:g} {q[3]:g}"'
    if euler is not None:
        return f' euler="{euler[0]:g} {euler[1]:g} {euler[2]:g}"'
    return ""


def _solid_runs(start: float, end: float, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """一段墙（start→end）挖掉若干洞口后剩下的实心段。gaps = [(洞中心, 洞宽), ...]。"""
    cuts = sorted((c - w / 2.0, c + w / 2.0) for c, w in gaps)
    runs: list[tuple[float, float]] = []
    cursor = start
    for g0, g1 in cuts:
        if g1 <= start or g0 >= end:
            continue
        if g0 > cursor:
            runs.append((cursor, g0))
        cursor = max(cursor, g1)
    if cursor < end:
        runs.append((cursor, end))
    return [(a, b) for a, b in runs if b - a > 1e-6]


# ---------------------------------------------------------------------- 墙
def _openings_on(room_key: str, side: str, horizontal: bool, fixed: float,
                 lo: float, hi: float) -> tuple[list, list]:
    """这面墙上有哪些门、哪些窗。返回 (门列表, 窗列表)，元素都是 (中心, 净宽)。

    门统一从 layout.DOORS 查：按"这道门所在的墙"（走向 + 坐标）匹配当前正在画的这条边，
    不靠"哪间屋的哪一侧"去猜——户型一复杂（三室两厅九个空间）那种猜法必错。
    """
    want = "h" if horizontal else "v"
    doors = [(d["center"], d["width"], d.get("kind", "door")) for d in L.DOORS
             if d.get("floor", L.ROOMS[room_key].get("floor", 0)) == L.ROOMS[room_key].get("floor", 0)
             and d["orient"] == want and abs(d["coord"] - fixed) < 1e-6 and lo <= d["center"] <= hi]
    # 窗多带窗台高和窗楣高：普通窗用默认值，落地窗在 layout 里用 "sill"/"top" 各自覆盖
    # （落地窗 sill≈0、top≈层高，一整片玻璃从地到顶）
    windows = [(w["center"], w["width"], w.get("sill", L.WINDOW_SILL_H),
                w.get("top", L.WINDOW_TOP_H)) for w in L.WINDOWS
               if w["room"] == room_key and w["side"] == side and lo <= w["center"] <= hi]
    return doors, windows


def _wall_geoms(room_key: str) -> list[str]:
    """给一间屋沿它的矩形边界画四面墙（该屋自己的颜色），门洞窗洞处留空。

    相邻两屋的公共边界各画各的一片薄墙（背靠背）——这样每间屋从内部看到的都是自己的墙色，
    正是 ANIMA "靠看认屋"需要的视觉区分。

    墙不是一整块：门洞上方留**门楣**、窗洞下方留**窗台墙**、上方留**窗楣墙**，
    所以每面墙会被切成若干矩形分别成 geom。
    """
    room = L.ROOMS[room_key]
    x0, y0, x1, y1 = room["rect"]
    rgba = room["wall_rgba"]
    t, H = L.WALL_THICK, L.WALL_HEIGHT
    zb = _zbase(room_key)
    out: list[str] = []

    # 四条边：(side, 是否水平, 沿墙起止, 固定坐标, 墙心朝屋内偏移的符号)
    edges = [
        ("s", True, (x0, x1), y0, +1),
        ("n", True, (x0, x1), y1, -1),
        ("w", False, (y0, y1), x0, +1),
        ("e", False, (y0, y1), x1, -1),
    ]
    for side, horizontal, (lo, hi), fixed, inward in edges:
        doors, windows = _openings_on(room_key, side, horizontal, fixed, lo, hi)
        fixed_c = fixed + inward * _half(t)      # 墙体贴在房间矩形内侧，避免两屋的墙互穿

        # 待画矩形列表：(沿墙起, 沿墙止, z 下, z 上)
        rects: list[tuple[float, float, float, float]] = []
        all_gaps = [(c, w) for c, w, _k in doors] + [(c, w) for c, w, _s, _t in windows]
        for a, b in _solid_runs(lo, hi, all_gaps):
            rects.append((a, b, 0.0, H))                      # 整高实墙
        for c, w, kind in doors:                               # 门楣（整段拆除的通道没有门楣）
            if kind != "open":
                rects.append((c - w / 2, c + w / 2, L.DOOR_HEIGHT, H))
        for c, w, sill, top in windows:                        # 窗台墙 + 窗楣墙
            if sill > 1e-6:                                    # 落地窗窗台≈0，就不画下面那截
                rects.append((c - w / 2, c + w / 2, 0.0, sill))
            if H - top > 1e-6:                                 # 落地窗顶到天花板，也就没有窗楣墙
                rects.append((c - w / 2, c + w / 2, top, H))

        # ⚠️ 墙是**竖着**的板，而 MuJoCo 给基本体贴 2D 图是沿几何体局部 Z 轴投影的——
        #    不转的话墙面贴图会被拉成竖条纹。house1/house2 用的是程序化噪点，
        #    条纹读起来像"拉毛墙面"所以一直没人发现；换成有纹理的石膏就露馅了。
        #    ⛔ 转过来会改变老场景的产物，所以由 layout 的 `WALL_FACE_FIX` 开关控制，
        #       默认关（house1/house2 逐字节不变），apt1 打开。
        face_fix = getattr(L, "WALL_FACE_FIX", False) and room.get("wall_mat")
        wquat = (_FACE_NS if horizontal else _FACE_EW) if face_fix else None
        for i, (a, b, z0, z1) in enumerate(rects):
            if b - a < 1e-6 or z1 - z0 < 1e-6:
                continue
            along_c, along_len = (a + b) / 2.0, b - a
            zc, zlen = (z0 + z1) / 2.0 + zb, z1 - z0
            pos = (along_c, fixed_c, zc) if horizontal else (fixed_c, along_c, zc)
            if wquat:
                # 转过之后：局部 X = 墙的水平方向、局部 Y = 竖直、局部 Z = 法线
                size = (along_len, zlen, t)
            else:
                size = (along_len, t, zlen) if horizontal else (t, along_len, zlen)
            out.append(_box(f"{room_key}_w{side}{i}", pos, size, rgba,
                            mat=room.get("wall_mat", ""), quat=wquat))

        # 门框 / 窗框（纯视觉，让洞口看起来是"一扇门/一扇窗"而不是墙上一个豁口）
        for j, (c, w, kind) in enumerate(doors):
            if kind == "open":      # 墙整段拆了，没有门框可画
                continue
            out += _frame(f"{room_key}_df{side}{j}", horizontal, c, w, fixed_c, t,
                          zb, zb + L.DOOR_HEIGHT, L.DOOR_FRAME_RGBA, L.DOOR_FRAME_THICK, bottom=False)
        for j, (c, w, sill, top) in enumerate(windows):
            out += _frame(f"{room_key}_wf{side}{j}", horizontal, c, w, fixed_c, t,
                          zb + sill, zb + top, L.WINDOW_FRAME_RGBA, L.WINDOW_FRAME_T,
                          bottom=True)
    return out


def _frame(name: str, horizontal: bool, center: float, width: float, fixed_c: float,
           wall_t: float, z0: float, z1: float, rgba, bar: float, bottom: bool) -> list[str]:
    """洞口四周的框：两根竖边框 + 上沿（+ 下沿，窗有、门没有）。稍厚于墙，才看得出立体感。"""
    out: list[str] = []
    depth = wall_t + 0.03
    zc, zlen = (z0 + z1) / 2.0, z1 - z0
    for k, off in (("l", -width / 2.0), ("r", +width / 2.0)):
        pos = (center + off, fixed_c, zc) if horizontal else (fixed_c, center + off, zc)
        size = (bar, depth, zlen) if horizontal else (depth, bar, zlen)
        out.append(_box(f"{name}_{k}", pos, size, rgba))
    edges = [("top", z1)] + ([("bot", z0)] if bottom else [])
    for k, z in edges:
        pos = (center, fixed_c, z) if horizontal else (fixed_c, center, z)
        size = (width + bar, depth, bar) if horizontal else (depth, width + bar, bar)
        out.append(_box(f"{name}_{k}", pos, size, rgba))
    return out


# ---------------------------------------------------------------------- 其它构件
def _zbase(room_key: str) -> float:
    """这间屋所在楼层的地面高度（m）。

    多层场景的 layout 提供 `FLOOR_Z(floor)`，并在每间屋上写 `"floor": n`；
    单层场景两样都没有，这里恒返回 0——所以同一套生成器代码对两种场景都成立，
    而且单层场景的产物逐字节不变。
    """
    floor_z = getattr(L, "FLOOR_Z", None)
    if floor_z is None:
        return 0.0
    return float(floor_z(L.ROOMS[room_key].get("floor", 0)))


def _floor_geom(room_key: str) -> list[str]:
    """这间屋的地板（可能不止一块）。

    ⭐ `floor_rects` = 只在这些矩形上铺地板（**局部楼板**）。楼梯井的上面几层就是这样：
    梯段升上来的地方必须空着，而下梯之后要有一块楼层平台，否则人上来就踩空。
    两头都错过：整层铺 → 把上楼的口封死；整层不铺 → 人爬上来掉回下一层。
    而且这两种错**从截图上完全看不出来**，只有沿着整条路线打射线才发现
    （见 check_scene.py 的 check_route）。
    """
    room = L.ROOMS[room_key]
    zb = _zbase(room_key) - _half(L.FLOOR_THICK)
    mat, rgba = room.get("floor_mat", ""), room["floor_rgba"]
    rects = room.get("floor_rects")
    if rects is None:
        rects = [room["rect"]]
    out = []
    for i, (x0, y0, x1, y1) in enumerate(rects):
        suffix = "" if len(rects) == 1 else f"{i}"
        out.append(_box(f"{room_key}_floor{suffix}",
                        ((x0 + x1) / 2.0, (y0 + y1) / 2.0, zb),
                        (x1 - x0, y1 - y0, L.FLOOR_THICK), rgba, mat=mat))
    return out


_FURN_TYPES = ("box", "cylinder", "sphere")

# ⭐⭐ MuJoCo geom 分组的归属约定 —— 本仓与消费方**共用的一张表**，改之前先读完。
#
# `group` 在 MuJoCo 里只有一个语义：**画不画**（默认渲染器只画第 0–2 组，射线一律照打）。
# 但消费方（anima-zero 的 sim-house-nav）还得靠它把「机器人自己」和「房子」分开——
# 它的激光测距要滤掉打在自己身上的射线，而 `mj_ray` 的过滤接口**只吃一个 6 位分组掩码**，
# 没法按 geom 或 body 子树过滤。于是这个本来只管渲染的数字，事实上也承担了"谁是谁"。
#
#   | 组 | 归谁 | 画不画 |
#   |----|------|--------|
#   | 0  | 房子可见部分：墙 / 地板 / 门套 / 窗框 / 玻璃 / 裸家具 / 装饰网格 | 画 |
#   | 1  | 天花板（各场景 layout 的 `CEILING_GROUP`，出俯视图时单独关掉）        | 画 |
#   | 2  | ⛔ **机器人视觉网格**（MuJoCo Menagerie 惯例）—— 房子不许用          | 画 |
#   | 3  | ⛔ **机器人碰撞网格**（同上惯例）—— 房子不许用                      | 不画 |
#   | 4  | 房子的隐身碰撞盒（穿了网格外衣的家具，见下）                          | 不画 |
#   | 5  | 预留                                                                | 不画 |
#
# ⛔ 房子这边只准用 **0 / 1 / 4 / 5**。占了 2 或 3，消费方的自检会当场拒绝启动
#    （2026-08-08 apt1 就是这么炸的：31 个隐身盒占着 3，和 g1/go2 的碰撞网格撞车）。
# ⛔ 硬上界 **≤ 5**：MuJoCo 的分组掩码固定 6 个槽，≥6 会被静默丢掉——那些碰撞盒对激光
#    就成了透明的，和下面 alpha=0 那个坑是同一类，但连报错都没有。
HIDDEN_BOX_GROUP = 4


def _has_mesh_coat(item: dict) -> bool:
    """这件家具是不是真的会发出一张网格外衣（资产已登记且字节在磁盘上）。"""
    key = (item.get("mesh") or {}).get("id", "")
    if not key:
        return False
    from decor import lock
    return lock.has(key) and lock.bytes_present(key)


def _has_hulls(item: dict) -> bool:
    """这件家具要不要用**真碰撞体**（CoACD 凸块）代替那个隐身碰撞盒。

    三个条件都成立才算：layout 里写了 `collide=True`、资产做过凸分解、凸块字节在磁盘上。
    ⚠️ 少任何一个都**退回隐身盒**，不报错——和网格外衣同样是"有就穿、没有就裸盒"的语义，
       裸 clone 上照样生成得出场景。判据同样是产物里数一下（见 `check_scene`）。
    """
    spec = item.get("mesh") or {}
    if not spec.get("collide"):
        return False
    from decor import lock
    return lock.has_hulls(spec["id"]) and lock.hulls_present(spec["id"])


def _furniture_geom(item: dict) -> str:
    """一件家具。

    ⚠️ layout 里的 z 写的是**该楼层内的高度**（桌面 0.75 就是 0.75），生成器在这里加上
    楼层基面。让作者心算 "三楼的桌子 = 0.75 + 5.76" 是制造错误的做法。
    """
    if item["type"] not in _FURN_TYPES:
        raise ValueError(
            f'家具 {item["name"]!r} 的 type={item["type"]!r} 不认识（只支持 '
            f'{"/".join(_FURN_TYPES)}）。⛔ 这里以前会**悄悄按 box 出**——打错一个字'
            f'就是屋里凭空多一块板，而且从截图上根本看不出来。')
    sx, sy, sz = item["size"]
    mat, eu, qt = item.get("mat", ""), item.get("euler"), item.get("quat")
    # ⭐ 穿了真网格外衣的家具，**碰撞盒本身不能画出来**。
    #    网格是缩到盒子里面去的（包含性不变式），盒子不透明就把外衣整个盖住了——
    #    ⚠️ 这个错渲染不报错、自检也全绿，只有看图才发现"上了真家具还是一堆白盒子"。
    #
    # ⛔⛔ 隐身只能靠 `group`（见上面 HIDDEN_BOX_GROUP 那张表），
    #    **绝不能把 rgba 的 alpha 设成 0**。
    #    实测：alpha=0 之后 `mj_ray` 直接跳过这个 geom——碰撞盒等于被悄悄挖空，
    #    导航和雷达全变，而**编译不报错**。是本仓的射线不变性自检当场抓到的
    #    （3 条射线穿过茶几打到了后面）。
    hide_box = _has_mesh_coat(item) or bool(item.get("visual_mesh"))
    # ⭐ walkover = 「脚可以踩过去当它不存在」的薄铺装（地毯、门垫）。
    #    2026-08-09 实测：G1 的盲策略（无外感知）踩上 1.6 cm 的地毯盒当场步态崩坏——
    #    玄关轴线 vx=0.6 走 5 秒只挪 0.35 m、原地趔趄漂移；把毯的碰撞关掉立刻恢复 2.82 m。
    #    house1 那条「⛔ 不许踩在地毯上（机器人 156° 翻了）」教训的行走版。
    #    真机器人本来就踩着毯走，仿真里让脚踩地板、毯只管看，反而更接近真实。
    #    ⚠️ mj_ray 不看 contype，毯照样挡射线——但它平贴地面（顶面 ≤2.4 cm），
    #    胸高的水平雷达射线从它上方过，读数不受影响。
    walkover = bool(item.get("walkover")) or not item.get("collide", True)
    zb = _zbase(item["room"])
    px, py, pz = item["pos"]
    item = {**item, "pos": (px, py, pz + zb)}
    if item["type"] in ("cylinder", "sphere"):
        look = f'material="{mat}"' if mat else f'rgba="{_rgba(item["rgba"])}"'
        if walkover:
            look += _DECOR
        rot = _rot_attr(eu, qt)
        # cylinder 的 size = (半径, 半高)；sphere 只要半径；layout 里一律写 (直径, 直径, 高)
        dims = f'{_half(sx):g}' if item["type"] == "sphere" else f'{_half(sx):g} {_half(sz):g}'
        return (f'    <geom name="furn_{item["name"]}" type="{item["type"]}" size="{dims}" '
                f'pos="{item["pos"][0]:g} {item["pos"][1]:g} {item["pos"][2]:g}"{rot} {look}/>')
    return _box(f'furn_{item["name"]}', item["pos"], item["size"], item["rgba"],
                mat=mat, euler=eu, quat=qt, group=HIDDEN_BOX_GROUP if hide_box else 0,
                extra=_DECOR if walkover else "")


def _furniture_parts(item: dict) -> list[str]:
    """一件家具发出来的**全部** geom。

    ⭐ 两条路，二选一：
      - 默认：一个碰撞盒（`furn_<名字>`），碰撞真相就是这个盒子；
      - `collide=True` 且资产做过凸分解：**改发一组 CoACD 凸块**
        （`furn_<名字>__h<N>`），碰撞真相变成真实形状。

    ⛔⛔ **走凸块那条路时，那个包络盒一个都不能留下。**
       原因是 `mj_ray` **不看 contype**——留一个 `contype=0` 的"纯声明"盒子，
       物理上确实不挡人，但**激光照样打在它上面**，于是消费方的雷达看到的还是一块
       97 cm 高的实心砖，真实形状白做了。而且它没法靠分组藏起来：消费方
       (`sim.py:_build_ray_mask`) 的掩码把**房子用到的每一个组**都打开。
       ⚠️ 唯一能让射线跳过 geom 的办法是 alpha=0，那是本仓明令禁止的坑（见 `_furniture_geom`）。

    ⚠️ 盒子不发了，但 layout 里的 `size` **一个字没变**——`check_reachability` /
       `check_furniture_overlap` / `check_furniture_not_through_wall` 三道都读
       `layout.FURNITURE` 的声明、不读产物，所以它们照常按"关着门的整件外廓"保守判定。
    """
    if item.get("articulated"):
        from scenes.articulated import fixture
        scale, quat, position = _mesh_placement(item)
        xml, excludes = fixture(item, scale, quat, position, _BUILD_ANGLE)
        _CONTACT_EXCLUDES.extend(excludes)
        return ["    " + xml]
    if item.get("movable"):
        from scenes.articulated import movable
        static = {k:v for k,v in item.items() if k != "movable"}
        geometry = _furniture_parts(static)
        if _has_mesh_coat(item):
            wrapped = ET.fromstring("<root>" + "\n".join(_decor_geoms([item])) + "</root>")
            geometry += [ET.tostring(g, encoding="unicode") for g in wrapped.iter("geom")]
        x, y, z = item["pos"]
        return ["    " + movable(dict(item, world_pos=(x, y, z + _zbase(item["room"]))), geometry)]
    if _has_hulls(item):
        return _hull_geoms(item)
    out = [_furniture_geom(item)]
    if item.get("visual_mesh"):
        visual = dict(item, name="furn_" + item["name"] + "_finish", type="mesh",
                      mesh_name=item["visual_mesh"], collide=False)
        x, y, z = visual["pos"]
        visual["pos"] = (x, y, z + _zbase(item["room"]))
        out.append(_residence_geom(visual))
    return out


def _ceiling_geom(room_key: str) -> str:
    """天花板：封顶，狗抬头看到的是屋顶而不是天空。

    声明了 `no_ceiling` 的不出顶。**楼梯井是竖着通的**，所以它在下面几层不能有天花板，
    在上面几层不能有地板——两个键成对使用，少一个梯井就从一头被封死。

    单独归一个 geom group（CEILING_GROUP），出俯视写真时把这一组关掉就能看清屋内布局，
    而第一视角照常渲染——不用维护两份场景。
    """
    room = L.ROOMS[room_key]
    if room.get("no_ceiling"):
        return ""
    x0, y0, x1, y1 = room["rect"]
    zc = _zbase(room_key) + L.WALL_HEIGHT + _half(L.CEILING_THICK)
    return _box(f"{room_key}_ceiling", ((x0 + x1) / 2.0, (y0 + y1) / 2.0, zc),
                (x1 - x0, y1 - y0, L.CEILING_THICK), L.CEILING_RGBA,
                extra=f' group="{L.CEILING_GROUP}"')


def _stairs() -> list[str]:
    """楼梯：踏板 + 平台 + 梯井隔墙 + 扶手护栏。多层场景才有（单层 layout 没有 STAIRS）。

    ⛔⛔ **一跑楼梯出 `risers − 1` 块踏板，不是 `risers` 块**——最上面那一级由平台充当。
       这是行业标准算法（treads = risers − 1，the landing is never counted under tread）。
       多出一块，就等于在平台边上叠了一块同高的板。

    ⭐ 为什么每级单独出 geom 而不是画个斜面：斜面对轮式/四足也许够用，但人形是**踩台阶**的，
    盲走策略靠脚底接触反馈判断落脚点，斜面给不出那个信号。踏面尺寸也因此是关键参数——
    见 layout 的 STEP_RUN 注释（G1 脚长约 0.25 m，踏面必须留出真余量）。

    ⭐ 每级单独给 friction：楼梯摩擦是想扫的变量（上楼滑不滑），所以它必须是场景里
    一个能改的旋钮，而不是继承 MuJoCo 默认值后无处可调。
    """
    if not hasattr(L, "STAIRS"):
        return []
    out: list[str] = ['    <!-- ===== 楼梯 ===== -->']
    fric_attr = f' friction="{L.STEP_FRICTION} 0.005 0.0001"'
    for flight in L.STAIRS:
        name = flight["name"]
        rise, run = L.STEP_RISE, L.STEP_RUN
        w = flight["width"]
        # 起跑线 = **这一跑下面那块平台的边缘**；dir 是水平前进方向
        x, y = flight["start_xy"]
        z0 = flight["base_z"]
        dx, dy = flight["dir"]
        fric = flight.get("friction", L.STEP_FRICTION)
        slab = L.STEP_SLAB
        for i in range(flight["risers"] - 1):
            # 第 i 块踏板 = 一块**厚板**，顶面就是踏面。板厚 > 踢面，所以相邻两级重叠、
            # 踢面处不露缝；而底面跟着坡度斜下去，头顶净空才是常数
            # （= 层高 − 板厚）。⛔ 别改回"从地面填上来的实心块"：那样上面那跑的
            # 底面会变成平顶，把下面那跑的净空压到一个人过不去的高度。
            top = z0 + (i + 1) * rise
            bottom = top - slab
            cx = x + dx * (i + 0.5) * run
            cy = y + dy * (i + 0.5) * run
            sx = run if dx else w
            sy = w if dx else run
            out.append(_box(f"{name}_s{i}", (cx, cy, (bottom + top) / 2.0),
                            (sx, sy, slab), L.STEP_RGBA,
                            extra=f' friction="{fric} 0.005 0.0001"', mat=L.STEP_MAT))
        # 扶手：只在**敞开的那一侧**出。靠墙那侧不出——真实楼梯就是一侧靠墙一侧扶手，
        # 而且贴着墙画会让扶手嵌进墙里（第一版就是这样，渲染出来像穿墙的斜杆）。
        if flight.get("rail_side"):
            out += _stair_rails(flight)
    # 中间休息平台：把两跑接起来的那块板。⛔ 少了它，走到上行跑顶端就没路了。
    for slab in getattr(L, "LANDINGS", []):
        out.append(_box(slab["name"], slab["pos"], slab["size"], L.STEP_RGBA,
                        extra=fric_attr, mat=L.STEP_MAT))
    # 梯井隔墙：两跑之间那道墙（不留缝，见 layout 的 WELL_WALL_THICK 注释）
    for wall in getattr(L, "WELL_WALLS", []):
        out.append(_box(wall["name"], wall["pos"], wall["size"], L.WELL_WALL_RGBA,
                        mat=L.WELL_WALL_MAT))
    # 梯口栏板：顶层那条没有梯段接上去的车道，是个直通下面的洞，必须围住
    for bar in getattr(L, "GUARDS", []):
        out.append(_box(bar["name"], bar["pos"], bar["size"], L.WELL_WALL_RGBA,
                        mat=L.WELL_WALL_MAT))
    return out


def _stair_rails(flight: dict) -> list[str]:
    """一跑楼梯敞开侧的扶手（不只是视觉：人形踉跄时有实体挡一下）。

    扶手沿**踏步鼻线**走：从起跑线（下平台边缘）到最后一块踏板的鼻端，
    水平跨 `(risers−1) × 踏面`、升 `(risers−1) × 踢面`。

    `rail_side` 是**世界坐标轴**的符号：沿 y 跑的梯，+1 = 扶手在 +x 侧；沿 x 跑的梯，
    +1 = 在 +y 侧。⚠️ 与前进方向无关——回头跑虽然朝 -y 走，它的 +1 仍然是 +x。
    """
    import math

    rise, run = L.STEP_RISE, L.STEP_RUN
    n, w = flight["risers"] - 1, flight["width"]
    x, y = flight["start_xy"]
    z0, (dx, dy) = flight["base_z"], flight["dir"]
    length = n * run
    slope = math.atan2(n * rise, length)
    cx, cy = x + dx * length / 2.0, y + dy * length / 2.0
    cz = z0 + n * rise / 2.0 + L.RAIL_HEIGHT
    sign = flight["rail_side"]
    # 往里收半个扶手厚度，让它贴着梯边而不是骑在边界线上
    inset = w / 2.0 - L.RAIL_THICK / 2.0
    ox, oy = (0.0, sign * inset) if dx else (sign * inset, 0.0)
    # ⚠️ 这里用 euler 而不是 quat 是**有意的且正确的**：slope 来自 math.atan2，本来就是弧度，
    #    而全局 <compiler angle="radian">（机器人 XML 带进来的）正好也是弧度，两边对得上。
    #    家具那条路径当年就是栽在这里——它按"度"写却走同一个 euler 出口。新代码请用 quat。
    euler = (0.0, -slope, 0.0) if dx else (slope, 0.0, 0.0)
    size = (length / math.cos(slope), L.RAIL_THICK, L.RAIL_THICK) if dx else \
           (L.RAIL_THICK, length / math.cos(slope), L.RAIL_THICK)
    return [_box(f"{flight['name']}_rail", (cx + ox, cy + oy, cz), size,
                 L.RAIL_RGBA, euler=euler)]


def _lights() -> list[str]:
    """每间屋一盏吸顶灯 —— 封了顶之后天光进不来，室内全靠这些灯，没灯就是一片黑。

    场景可以声明 `LIGHTS` 自己排灯位（apt1 那种朝北大平层要的是"沿窗墙一排天光"，
    不是"一房一盏"）。声明了就整份接管，不再走下面的默认规则。
    原生 OpenGL 灯槽有限；新场景须通过 check_lights_render，不能用 mjMAXLIGHT 推断可见灯数。
    """
    if getattr(L, "LIGHTS", None):
        out = ['    <!-- ===== 灯光（场景自排）===== -->']
        for lt in L.LIGHTS:
            attrs = " ".join(f'{k}="{v}"' for k, v in lt.items() if k != "name")
            out.append(f'    <light name="{lt["name"]}" {attrs}/>')
        return out
    out = []
    for key, room in L.ROOMS.items():
        x0, y0, x1, y1 = room["rect"]
        out.append(
            f'    <light name="light_{key}" pos="{(x0 + x1) / 2.0:g} {(y0 + y1) / 2.0:g} '
            f'{_zbase(key) + L.WALL_HEIGHT - 0.15:g}" dir="0 0 -1" diffuse="0.62 0.61 0.58" '
            f'specular="0.05 0.05 0.05" attenuation="0.55 0.06 0.010"/>')
    # 屋外一盏"太阳"，让窗外的草地树木亮起来（否则窗外一片死黑，白开窗）
    out.append('    <light name="sun" pos="10 -18 22" dir="-0.35 0.62 -0.70" directional="true" '
               'diffuse="0.55 0.54 0.50" specular="0.10 0.10 0.10"/>')
    return out


# make_textures.py 生成的那批基础贴图。⛔ 改这里要同步改 make_textures.py，两边名字必须对得上。
# 场景专属的贴图不要往这里加，走 layout 的 TEXTURES_EXTRA（不撞名 = 老场景零回归面）。
_BASE_TEXTURES = ("wood_floor", "wood_floor_light", "tile_white", "tile_grey",
                  "marble", "marble_dark", "marble_warm", "marble_grey", "marble_greige",
                  "carpet", "fabric", "fabric_blue", "wall_paint",
                  "city_skyline", "art0", "art1", "art2", "art3",
                  "oven_glass", "appliance_panel")

# ⭐⭐ 贴到**基本体**上的贴图必须是 `type="cube"`，不能是 `type="2d"`。
#
# ⛔ MuJoCo 给基本体贴 2D 图时**沿几何体的局部 Z 轴投影**：只有法线朝 Z 的面（地板、台面
#    这些水平面）是对的，四个**竖直面**上贴图会被沿 Z 拖成一道道竖条纹。
#    地板一直好看、沙发/柜子/墙面一直"像拉丝金属"，就是这个原因——
#    Jeff 2026-08-08 的原话是"好多 vertical 射线，而不是沙发材质的感觉"。
#    cube 贴图对六个面各自投影，竖直面才有真正的织物/木纹。
#
# ⚠️ 走过的弯路（别再走一遍）：`texuniform` **治不了这个**。它只改"texrepeat 是相对
#    geom 还是按空间单位"，实测开/关渲染出来**逐像素一样**。塔楼立面之所以正常，
#    是因为它本来就声明成了 cube（见 apt1 layout 的 TEXTURES_EXTRA），不是因为 texuniform。
#
# ⛔ 两类例外必须留 2d：
#   ① **整张图只铺一次、只看一个面**的（城市天际线背景板、挂画）——cube 只是把同一张图
#      在六个面各贴一遍，没有收益；挂画那种细横线换投影反而走样。
#   ② ⛔ **非正方形的图**——MuJoCo 的 cube 贴图要求"PNG 尺寸是 gridsize 的整数倍"，
#      喂一张 512×128 的会**编译期直接报错**（`appliance_panel` 就是 512×128）。
#      判据**从图片实际尺寸算**，⛔ 不要手维护一张名单：以后换张图、加张图，名单必然忘记跟。
_FLAT_ONLY_TEXTURES = ("city_skyline", "art0", "art1", "art2", "art3")


def _tex_kind(name: str) -> str:
    """这张贴图该用 cube 还是 2d。见上面 _FLAT_ONLY_TEXTURES 那段。"""
    if name in _FLAT_ONLY_TEXTURES:
        return "2d"
    path = os.path.join(ROOT, "textures", f"{name}.png")
    try:
        from PIL import Image
        with Image.open(path) as im:
            if im.size[0] != im.size[1]:
                return "2d"                  # 非方形，cube 会编译失败
    except Exception:
        return "2d"                          # 读不出来就保守走 2d（至少能编译）
    return "cube"


def _assets(robot_key: str) -> list[str]:
    """<asset> 段：天空盒 + 程序化贴图（make_textures.py 生成）+ 材质定义。

    材质带 specular/shininess/reflectance：金属龙头会有高光、玻璃隔断半透、瓷砖有光泽感——
    这些属性比几何体本身更能把"积木感"压下去。
    """
    out = ['  <asset>']
    # ⛔ 一个模型只能有一个 skybox（多了是编译错误）。场景自带 SKYBOX 就不出这个内置渐变天空。
    if not getattr(L, "SKYBOX", None):
        out.append('    <texture type="skybox" builtin="gradient" rgb1="0.52 0.68 0.88" '
                   'rgb2="0.88 0.92 0.96" width="512" height="1024"/>')
    else:
        # ⭐ 属性名以 file 开头的就是路径，过一遍 _root_rel（layout 里写的是仓根相对）
        attrs = " ".join(f'{k}="{_root_rel(v) if k.startswith("file") else v}"'
                         for k, v in L.SKYBOX.items())
        out.append(f'    <texture type="skybox" {attrs}/>')
    # 贴图（file 路径相对**本 XML 所在目录**，即 build/ —— 所以要 _root_rel 退回仓根）
    for name in _BASE_TEXTURES:
        kind = _tex_kind(name)
        out.append(f'    <texture type="{kind}" name="tex_{name}" '
                   f'file="{_root_rel(f"textures/{name}.png")}"/>')
    # 场景自己的额外贴图（apt1 的公园航拍、城市底图、塔楼立面等）。
    # ⛔ 名字必须和 _BASE_TEXTURES 不撞——不撞 = 对 house1/house2 零回归面。
    # ⚠️ type 默认 "2d"，但**允许字典自己覆盖**（塔楼立面要 type="cube"，
    #    因为 2d 贴图在竖着的基本体上会被沿局部 Z 拉成条纹）。
    #    别把 type 硬写在 f-string 里再 join 一遍字典——会出两个 type 属性，XML 直接解析失败。
    for t in getattr(L, "TEXTURES_EXTRA", []):
        d = {"type": "2d", **t}
        attrs = " ".join(f'{k}="{_root_rel(v) if k.startswith("file") else v}"'
                         for k, v in d.items())
        out.append(f'    <texture {attrs}/>')
    # 材质：texrepeat 控制平铺密度（数字越大格子越小）
    mats = [
        ("mat_wood", "tex_wood_floor", 3, 3, 0.15, 0.25, 0.02),
        ("mat_wood_light", "tex_wood_floor_light", 3, 3, 0.15, 0.25, 0.02),
        ("mat_tile", "tex_tile_white", 4, 4, 0.35, 0.55, 0.12),
        ("mat_tile_grey", "tex_tile_grey", 4, 4, 0.35, 0.55, 0.12),
        ("mat_marble", "tex_marble", 2, 2, 0.45, 0.70, 0.15),
        ("mat_marble_dark", "tex_marble_dark", 2, 2, 0.45, 0.70, 0.15),
        ("mat_marble_warm", "tex_marble_warm", 2, 2, 0.45, 0.70, 0.15),
        ("mat_marble_grey", "tex_marble_grey", 2, 2, 0.45, 0.70, 0.15),
        # 玄关地面：石材光泽压低（0.45/0.70/0.15 是台面档，铺整片地面在俯拍顶光下会过曝发白）
        ("mat_marble_greige", "tex_marble_greige", 2, 2, 0.20, 0.35, 0.04),
        ("mat_carpet", "tex_carpet", 4, 4, 0.02, 0.05, 0.0),
        ("mat_fabric", "tex_fabric", 6, 6, 0.05, 0.10, 0.0),
        ("mat_fabric_blue", "tex_fabric_blue", 6, 6, 0.05, 0.10, 0.0),
        ("mat_wall", "tex_wall_paint", 2, 2, 0.05, 0.10, 0.0),
        # 家电：烤箱/洗碗机的玻璃门与控制面板（厨房里最好认的两样东西）
        ("mat_oven_glass", "tex_oven_glass", 1, 1, 0.85, 0.90, 0.30),
        ("mat_appliance_panel", "tex_appliance_panel", 1, 1, 0.70, 0.80, 0.25),
    ]
    for name, tex, rx, ry, spec, shin, refl in mats:
        out.append(f'    <material name="{name}" texture="{tex}" texrepeat="{rx} {ry}" '
                   f'specular="{spec}" shininess="{shin}" reflectance="{refl}"/>')
    # 无贴图但要质感的材质：不锈钢 / 镀铬 / 玻璃 / 亮漆
    out.append('    <material name="mat_steel" rgba="0.82 0.84 0.87 1" '
               'specular="0.9" shininess="0.85" reflectance="0.35"/>')
    out.append('    <material name="mat_chrome" rgba="0.90 0.92 0.94 1" '
               'specular="1.0" shininess="0.95" reflectance="0.5"/>')
    out.append('    <material name="mat_glass" rgba="0.72 0.85 0.90 0.32" '
               'specular="0.8" shininess="0.9" reflectance="0.25"/>')
    out.append('    <material name="mat_porcelain" rgba="0.98 0.98 0.97 1" '
               'specular="0.55" shininess="0.75" reflectance="0.12"/>')
    out.append('    <material name="mat_screen" rgba="0.04 0.04 0.06 1" '
               'specular="0.6" shininess="0.9" reflectance="0.2"/>')
    out.append('    <material name="mat_city" texture="tex_city_skyline" '
               'specular="0" shininess="0" reflectance="0" emission="0.35"/>')
    for i in range(4):
        out.append(f'    <material name="mat_art{i}" texture="tex_art{i}" '
                   f'specular="0.1" shininess="0.2"/>')
    out.append('    <material name="mat_mirror" rgba="0.78 0.85 0.90 1" '
               'specular="1.0" shininess="0.98" reflectance="0.6"/>')
    # 场景自己的额外材质。同样⛔不许和上面的名字撞。
    for m in getattr(L, "MATERIALS_EXTRA", []):
        attrs = " ".join(f'{k}="{v}"' for k, v in m.items())
        out.append(f'    <material {attrs}/>')
    # ⛔ 装饰网格的 <mesh>/<texture>/<material> 必须在 **</asset> 之前**——
    #    MJCF 的 schema 不认 <asset> 外面的 <mesh>，报的是
    #    "Schema violation: unrecognized element"，看不出是位置错了。
    out.extend(_mesh_assets(robot_key))
    for name, mesh in getattr(L, "RES_MESHES", {}).items():
        attrs = " ".join(f'{k}="{_flatten(v)}"' for k, v in mesh.items())
        out.append(f'    <mesh name="{name}" {attrs}/>')
    out.append('  </asset>')
    return out


def _wall_arts() -> list[str]:
    """墙上挂画：画心（贴图）+ 四周画框。贴在指定房间指定墙的内表面上。

    ⚠️ 挂画和城市背景板踩的是同一个坑：竖着的板贴 2D 图会被沿局部 Z 投影成条纹。
       所以这里也把板转到"局部 +Z = 法线"，size 一律写成 (画宽, 画高, 板厚) 的**局部**尺寸。
       详见 _FACE_NS / _FACE_EW 上面那段说明。
    """
    if not getattr(L, "WALL_ARTS", None):
        return []
    out: list[str] = ['    <!-- ===== 墙上挂画（视觉干扰项）===== -->']
    t = L.WALL_THICK
    ft = L.ART_FRAME_T
    for i, a in enumerate(L.WALL_ARTS):
        x0, y0, x1, y1 = L.ROOMS[a["room"]]["rect"]
        horizontal = a["side"] in ("n", "s")
        # 画贴在墙内表面，往房间里探出一点点
        if a["side"] == "n":
            fixed, off = y1 - t, -0.02
        elif a["side"] == "s":
            fixed, off = y0 + t, +0.02
        elif a["side"] == "e":
            fixed, off = x1 - t, -0.02
        else:
            fixed, off = x0 + t, +0.02
        c, z, w, h = a["center"], a["z"], a["w"], a["h"]
        quat = _FACE_NS if horizontal else _FACE_EW
        zb = _zbase(a["room"])
        if horizontal:
            pos, fpos = (c, fixed + off, z + zb), (c, fixed + off * 0.6, z + zb)
        else:
            pos, fpos = (fixed + off, c, z + zb), (fixed + off * 0.6, c, z + zb)
        out.append(_box(f"artframe{i}", fpos, (w + 2 * ft, h + 2 * ft, 0.04),
                        L.ART_FRAME_RGBA, quat=quat, extra=_DECOR))
        out.append(_box(f"art{i}", pos, (w, h, 0.03), (1, 1, 1, 1),
                        mat=f'mat_{a["tex"]}', quat=quat, extra=_DECOR))
    return out


# 把一块板转到"局部 +Z 指向法线方向"的两个四元数。
# ⛔ 为什么必须转（2026-08-05 修的老 bug）：MuJoCo 给**基本体**贴 type="2d" 纹理时没有 UV，
#    它是**沿几何体自己的局部 Z 轴投影**的。所以只有法线朝局部 +Z 的面才贴得对——
#    本仓的地板一直是对的，正因为地板是水平的、局部 +Z 朝上。
#    而城市背景板是**竖着**的，局部 +Z 是那根 34 m 的竖轴，大面正好投不上，
#    2048×768 的天际线图被拉成了竖条纹（见 docs/images/house1 里 2026-08-05 前的窗外截图）。
#    转过来之后：局部 X = 板子的水平方向（贴图 u）、局部 Y = 竖直（贴图 v）、局部 Z = 法线。
_FACE_NS = (0.70710678, 0.70710678, 0.0, 0.0)          # 绕 X 转 90°：局部 Z → 世界 −Y
_FACE_EW = (0.5, 0.5, 0.5, 0.5)                        # 绕 (1,1,1) 转 120°：局部 Z → 世界 +X


def _city_backdrop() -> list[str]:
    """屋外四面城市背景板：贴天际线贴图的大立面，任何一扇窗望出去都能看到城市。

    ⚠️ size 一律写成 (板宽, 板高, 板厚)——那是**局部**尺寸。转过去之后世界里的
       长宽高会换位，别拿世界坐标去核对这三个数。
    """
    if not L.CITY_BACKDROP:              # apt1 用的是 VIEW 那套四层窗景，不出这个
        return []
    cb = L.CITY_BACKDROP
    d, w, h, z = cb["dist"], cb["width"], cb["height"], cb["z"]
    out = ['    <!-- ===== 城市背景板（窗外风景）===== -->']
    for name, pos, quat in [
            ("north", (0, d, z), _FACE_NS),
            ("south", (0, -d, z), _FACE_NS),
            ("east", (d, 0, z), _FACE_EW),
            ("west", (-d, 0, z), _FACE_EW)]:
        out.append(_box(f"city_{name}", pos, (w, h, 0.4), (1, 1, 1, 1),
                        mat="mat_city", extra=_DECOR, quat=quat))
    return out


# 屋外的一切都是**纯装饰**：狗永远不出门，这些不该参与碰撞。
# ⚠️ 实测教训（2026-07-25）：草地是块 120m 的大板、顶面只比室内地板低 1cm，
#    机器狗的脚会同时接触室内地板和屋外草地，两层地面的接触约束打架 → 站着就被掀翻。
#    关掉碰撞后彻底根治，视觉毫无损失。
_DECOR = ' contype="0" conaffinity="0"'


def _outdoor() -> list[str]:
    """屋外景色：草地 + 树 + 远处楼房。从窗口望出去有东西可看，屋子才不像个盒子。"""
    if not (L.OUTDOOR_GROUND or L.TREES or L.BUILDINGS):
        return []                        # 高层公寓脚下没有草地和树，整段不出
    out: list[str] = ['    <!-- ===== 屋外景色（纯装饰，不参与碰撞）===== -->']
    if L.OUTDOOR_GROUND:
        g = L.OUTDOOR_GROUND
        out.append(_box("outdoor_ground", g["pos"], g["size"], g["rgba"], extra=_DECOR))
    for i, (x, y, trunk_h, crown_d) in enumerate(L.TREES):
        out.append(f'    <geom name="tree{i}_trunk" type="cylinder" '
                   f'size="{0.16:g} {_half(trunk_h):g}" pos="{x:g} {y:g} {_half(trunk_h):g}" '
                   f'rgba="{_rgba(L.TRUNK_RGBA)}"{_DECOR}/>')
        out.append(f'    <geom name="tree{i}_crown" type="sphere" size="{_half(crown_d):g}" '
                   f'pos="{x:g} {y:g} {trunk_h + crown_d * 0.35:g}" '
                   f'rgba="{_rgba(L.FOLIAGE_RGBA)}"{_DECOR}/>')
    for i, (x, y, sx, sy, h, rgba) in enumerate(L.BUILDINGS):
        out.append(_box(f"bldg{i}", (x, y, h / 2.0), (sx, sy, h), rgba, extra=_DECOR))
    return out


def _view() -> list[str]:
    """高层窗景：脚下的水平地面板 + 中景实体塔楼 + 本楼自己的外皮。

    ⭐ 为什么分层、切点为什么在 600 m —— 算的是视差，不是拍的：
       屋里相机横向能走约 ±4 m，取 8 m 最坏情况；960×720 + 默认 45° 视场 = 0.0625°/像素。
       距离 d 处的特征走 8 m 的角位移是 8/d：
         120 m（公园近边）→ 3.8° = 61 像素      300 m（亿万富翁街）→ 1.53° = 24 像素
         600 m            → 0.76° = 12 像素     3000 m             → 0.15° = 2.4 像素
       所以 600 m 以内必须是**真几何**（不然窗框一做参照就穿帮），以外交给无限远的天空盒，
       全屋走一遍误差不到 10 像素，看不出来。

    ⭐ GROUND_SLABS 是**水平**的板 —— 这是 MuJoCo 给基本体贴 2D 图**唯一投影正确**的朝向
       （本仓的地板就是活证据，城市背景板当年就是栽在竖着贴）。而且从 62 层往外看，
       视线大部分本来就是往下往外扫的，俯角天生正确 —— 这是任何一张平视照片都给不了的。
    """
    out: list[str] = []
    slabs = getattr(L, "GROUND_SLABS", [])
    if slabs:
        out.append('    <!-- ===== 窗景 C 层：脚下的地面（水平板，贴图投影唯一正确的朝向）===== -->')
        for s in slabs:
            out.append(_box(s["name"], s["pos"], s["size"], s.get("rgba", (1, 1, 1, 1)),
                            mat=s.get("mat", ""), extra=_DECOR))
    skyline = getattr(L, "SKYLINE", [])
    if getattr(L, 'SKYLINE_GEOMS', None):
        out.extend(_residence_geom(item) for item in L.SKYLINE_GEOMS)
    elif skyline:
        out.append('')
        out.append('    <!-- ===== 窗景 B 层：120–600 m 的实体塔楼（真视差 + 真遮挡）===== -->')
        for name, x, y, sx, sy, top, mat in skyline:
            # top 是楼顶相对本层地面的标高；楼从脚下的地面板一直长上来
            base = -L.ELEV
            h = top - base
            out.append(_box(f"sky_{name}", (x, y, base + h / 2.0), (sx, sy, h),
                            (1, 1, 1, 1), mat=mat, extra=_DECOR))
    tower = getattr(L, "HOST_TOWER", [])
    if tower:
        out.append('')
        out.append('    <!-- ===== 窗景 D 层：本楼自己的外皮（否则这套房子是飘在天上的）===== -->')
        for t in tower:
            out.append(_box(t["name"], t["pos"], t["size"], t.get("rgba", (1, 1, 1, 1)),
                            mat=t.get("mat", ""), extra=_DECOR))
    return out


def _glazing() -> list[str]:
    """落地窗的玻璃 —— ⛔ **必须参与碰撞**，这不是装饰。

    ⚠️ 血的道理：`walkthrough.PROBE_H = 1.0` 在胸高打横射线来挡人，落地窗洞口打不到东西，
       人物就直接走出去了。在 house1 那是下 5 cm 台阶到草地；在 apt1 是**232 米自由落体**，
       而且机器人有同样的自由——窗洞在老场景里本来就没有碰撞几何。
       那里现实中就是有玻璃，补上它既是物理事实，也修好了 walkthrough 自检第 2 项。
    """
    if not getattr(L, "GLASS_RGBA", None):
        return []
    out = ['    <!-- ===== 落地窗玻璃（⛔ 参与碰撞：没有它机器人会从 232 米走出去）===== -->']
    t = L.WALL_THICK
    for i, w in enumerate(L.WINDOWS):
        if not w.get("glass"):
            continue
        x0, y0, x1, y1 = L.ROOMS[w["room"]]["rect"]
        sill = w.get("sill", L.WINDOW_SILL_H)
        top = w.get("top", L.WINDOW_TOP_H)
        zc, hh = (sill + top) / 2.0 + _zbase(w["room"]), top - sill
        c, ww = w["center"], w["width"]
        fixed = {"n": y1 - t / 2.0, "s": y0 + t / 2.0,
                 "e": x1 - t / 2.0, "w": x0 + t / 2.0}[w["side"]]
        if w["side"] in ("n", "s"):
            pos, size = (c, fixed, zc), (ww, L.GLASS_THICK, hh)
        else:
            pos, size = (fixed, c, zc), (L.GLASS_THICK, ww, hh)
        out.append(_box(f"glass{i}", pos, size, L.GLASS_RGBA))
    return out



# ---------------------------------------------------------------- 入户门
# ⭐ 门厚由生成器从 `WALL_THICK` 推，**layout 不许自己填厚度**。
#    ⛔ 这条是 2026-08-08 血的教训：三个 layout 各自手填了一个"比墙薄"的厚度，
#    又把门心放在房间矩形的边上——而墙是**从 rect 边往房间内侧长满一个墙厚**的
#    （见 `_walls()` 里那句 `fixed + inward * _half(t)`）。结果：
#      · apt1  门 y∈[−7.51,−7.45]，南墙 y∈[−7.50,−7.36] → **整块埋在墙里，两面都看不见**
#      · house1 同病（x∈[9.38,9.46] 对墙 [9.36,9.50]）
#      · house2 只贴在**室外**面，屋里同样看不见
#    Jeff 走进玄关看到的就是一面白墙，完全不知道哪儿是门。
#    → 现在门**比墙厚**，两面各凸出 `_DOOR_PROUD`，屋里屋外都看得见，而且**不可能再填错**。
_DOOR_PROUD = 0.02      # 门扇比墙面凸出多少（两面各这么多）
_CASING_W = 0.09        # 门套宽度（贴脸的可见宽度）
_CASING_PROUD = 0.03    # 门套再比门扇凸出多少 —— 这一圈凸边就是"一眼认出是门"的关键
_HANDLE_LEN = 1.10      # 竖向长拉手。公寓入户门用的是这种，不是把小圆球
_HANDLE_T = 0.045


def _flatten(values):
    """Serialize authored mesh/transform values deterministically."""
    if isinstance(values, (list, tuple)):
        return " ".join(_flatten(v) for v in values)
    return f"{values:.7g}"


def _residence_geom(item):
    attrs = {"name": item["name"], "type": item["type"]}
    if item.get("fromto"):
        attrs["fromto"] = _flatten(item["fromto"])
        attrs["size"] = _flatten(item["radius"])
    else:
        attrs["pos"] = _flatten(item["pos"])
        typ = item["type"]
        size = item.get("size", ())
        if typ == "mesh": attrs["mesh"] = item["mesh_name"]
        elif typ == "sphere": attrs["size"] = _flatten(size[0]/2)
        elif typ == "cylinder": attrs["size"] = _flatten((size[0]/2,size[2]/2))
        else: attrs["size"] = _flatten(tuple(v/2 for v in size))
    if item.get("quat"): attrs["quat"] = _flatten(item["quat"])
    if item.get("mat"): attrs["material"] = item["mat"]
    else: attrs["rgba"] = _flatten(item.get("rgba", (1,1,1,1)))
    attrs["group"] = item.get("group", 0)
    if not item.get("collide", True):
        attrs.update(contype=0, conaffinity=0)
    return '    <geom ' + ' '.join(f'{k}="{v}"' for k,v in attrs.items()) + '/>'


def _residence_parts(item):
    if not item.get("visual_mesh"): return [_residence_geom(item)]
    out = []
    if item.get("collide", True):
        out.append(_residence_geom(dict(item, group=HIDDEN_BOX_GROUP)))
    out.append(_residence_geom(dict(item, name=item["name"]+"_finish", type="mesh",
                                   mesh_name=item["visual_mesh"], collide=False)))
    return out


def _front_door() -> list[str]:
    """入户门：门扇 + 三面门套 + 竖向长拉手。⛔ 纯视觉件，碰撞由墙承担。

    layout 只声明「开在哪间屋的哪面墙、沿墙哪个位置、多宽多高、什么材质」——
    和 `WINDOWS` 用的是同一套 `room` / `side` / `center` / `width` 写法，⛔ 别再发明第二种。
    """
    d = getattr(L, "FRONT_DOOR", None)
    if not d:
        return []
    t = L.WALL_THICK
    x0, y0, x1, y1 = L.ROOMS[d["room"]]["rect"]
    # 墙心：和 `_walls()` / 玻璃窗用的是同一个公式，⛔ 别在这儿另算一份
    fixed = {"n": y1 - t / 2.0, "s": y0 + t / 2.0,
             "e": x1 - t / 2.0, "w": x0 + t / 2.0}[d["side"]]
    horiz = d["side"] in ("n", "s")
    c, w, h = d["center"], d["width"], d["height"]
    zb = _zbase(d["room"])
    zc = zb + h / 2.0
    leaf_t = t + 2 * _DOOR_PROUD
    case_t = leaf_t + 2 * _CASING_PROUD
    mat = d.get("mat", "")
    cmat = d.get("casing_mat", "")
    out = ["    <!-- 入户门（视觉件：门扇 + 门套 + 长拉手）-->"]

    def _put(name, along_c, along_w, z, zh, thick, m, rgba):
        pos = (along_c, fixed, z) if horiz else (fixed, along_c, z)
        size = (along_w, thick, zh) if horiz else (thick, along_w, zh)
        out.append(_box(name, pos, size, rgba, mat=m))

    # 门套：左右两条 + 上面一条（把门框出来）
    cw = w + 2 * _CASING_W
    _put("front_door_casing_l", c - (w + _CASING_W) / 2.0, _CASING_W, zb + h / 2.0, h, case_t,
         cmat, d["casing_rgba"])
    _put("front_door_casing_r", c + (w + _CASING_W) / 2.0, _CASING_W, zb + h / 2.0, h, case_t,
         cmat, d["casing_rgba"])
    _put("front_door_casing_t", c, cw, zb + h + _CASING_W / 2.0, _CASING_W, case_t,
         cmat, d["casing_rgba"])
    if d.get("state") == "fixed_open":
        angle = math.radians(d.get("open_angle", 90))
        hinge = (c-w/2, fixed, zb) if horiz else (fixed, c-w/2, zb)
        q = yaw_quat(d.get("open_angle", 90))
        leaf = (w/2, 0, h/2) if horiz else (0, w/2, h/2)
        size = (w, leaf_t, h) if horiz else (leaf_t, w, h)
        out.append(f'    <body name="front_door_fixed" pos="{_flatten(hinge)}" quat="{_flatten(q)}">')
        out.append(_box("front_door", leaf, size, d["rgba"], mat=mat))
        handle = (w-.11, leaf_t/2+.02, 1.05) if horiz else (leaf_t/2+.02, w-.11, 1.05)
        out.append(_box("front_door_handle", handle, (_HANDLE_T,_HANDLE_T,_HANDLE_LEN),
                        d["handle_rgba"], mat=d.get("handle_mat", "")))
        out.append('    </body>')
        return out
    # 门扇
    _put("front_door", c, w, zc, h, leaf_t, mat, d["rgba"])
    # 竖向长拉手：贴在门扇**室内**那一面（凸出来一点，不然又埋进门里）
    hx = c + d.get("handle_side", 1) * (w / 2.0 - 0.11)
    inward = {"n": -1.0, "s": 1.0, "e": -1.0, "w": 1.0}[d["side"]]
    hf = fixed + inward * (leaf_t / 2.0 + _HANDLE_T / 2.0)
    hpos = (hx, hf, zb + 1.05) if horiz else (hf, hx, zb + 1.05)
    hsize = (_HANDLE_T, _HANDLE_T, _HANDLE_LEN) if horiz else (_HANDLE_T, _HANDLE_T, _HANDLE_LEN)
    out.append(_box("front_door_handle", hpos, hsize, d["handle_rgba"], mat=d.get("handle_mat", "")))
    return out

# ---------------------------------------------------------------- 装饰网格
# 每张装饰网格都是**纯视觉外衣**，碰撞仍然由它所装饰的那个 box 承担。
#
# ⭐ **包含性不变式**：网格缩放到完全装进碰撞盒里 → 任何会打到网格的射线一定先打到盒子
#    → **所有射线结果和没装饰时逐位相同**。
# ⛔ 为什么必须这样而不是简单设 contype=0：**`mj_ray` 根本不看 contype/conaffinity**。
#    check_scene.py 四处射线 + walkthrough.py 两处射线全传 `geomgroup=None`，
#    一张探出碰撞盒的装饰网格照样会被打中。house2 有现成伤疤（楼梯平台放盆栽，射线打到叶子）。
# ⭐ 而且这一对属性还有个**实测的**好处：`contype=0` **且** `conaffinity=0` 时
#    MuJoCo **完全跳过 qhull**（`nmeshgraph = 0`），任何一个非零就要算全套凸包。
#    20 张 9.3 万面的视觉网格编译只要 0.23 秒——⚠️ 这是整件事便宜的唯一原因，
#    所以每张网格都必须真的带上这两个属性。
# ⭐ 网格相对碰撞盒的**统一安全余量** = 每轴留 1%。
#    2026-08-07 实测定标（EPS 设成 1.0 重新生成，量每张网格顶点在盒子局部系里的超出量）：
#    全场 25 件装饰的最坏超出是 **+4.84 µm**（吊灯），也就是恰好相切。
#    那点残量的唯一来源是 XML 里 `%g` 只写 6 位有效数字，位置和缩放都被截断——
#    是**数值**问题，不是几何问题。
#    0.99 给最薄的那件（木碗，盒子半长 5 cm）留 **0.50 mm** 净空，是截断误差的 100 倍。
# ⛔ 这个值以前是 0.88，理由写着三条，修完之后**三条全部不成立**（2026-08-07）：
#    ① `%g` 截断 —— 真的，但那是 µm 级，用不着 12%；
#    ② "标定的包围盒和摆位用的重心之间有残差" —— 不存在，摆位根本不该用重心
#       （MuJoCo 自己补偿了，见 `_decor_geoms` 里那段 ⛔⛔）；
#    ③ "带 yaw 的件按旋转后 AABB 估外廓会低估" —— 数学上不可能低估，
#       而且 yaw 根本不该在 `_fit_scale` 里算（见那个函数的 ⛔）。
# ⛔ 网格探出盒子时**别调这个值，也别放大碰撞盒**（缩放会把网格按比例一起撑大）。
#    判据是 `check_scene.py` 的 **⭐⭐ 装饰网格整个装在碰撞盒里**——它直接量顶点，
#    报出探出多少毫米；探出说明 `_asset_span` 或 `_decor_geoms` 坏了，去修那里。
_FIT_EPS = 0.99


_ROOT_PREFIX = "../" * len(SCENES.OUT_SUBDIR.strip("/").split("/"))


def _root_rel(p: str) -> str:
    """把一条**仓根相对**的路径，翻译成"从产物 XML 所在目录看"的相对路径。

    ⭐ 存在的理由是分层：`layout.py` 里写的贴图路径永远是**仓根相对**的
       （`textures/house3/park_aerial.png`），产物住哪一层是**生成器的部署细节**。
       漏进 layout 就等于每个新场景作者都得知道 `build/` 有几层深——
       正是 AGENTS.md 那条「目录一动，所有 `..` 重新数一遍」红线在防的事。

    ⛔ **只给 `<include>` 与 `<texture file*>` 用**：它们相对**主模型 XML 所在目录**解析。
       `<mesh file>` 走的是 `meshdir`，用 `_decor_prefix()`——**两者规则不同，别照抄**。
    ⚠️ 判据是"属性名以 `file` 开头的就是路径"（`fileright`/`fileup`… 都算），
       `check_scene.py` 的贴图存在性检查用的是同一条规则。
    """
    return _ROOT_PREFIX + p


def _assert_meshdir_agrees(robot_key: str) -> None:
    """机器人 XML 声明的 meshdir，必须和 `robots/manifest.py` 说的指向同一个目录。

    ⛔ 同一个 meshdir 在两处各存一份，**语义有意不同**（别去"统一"它们）：
       · `robots/manifest.py` 存**仓根相对**的 `robots/g1/meshes` —— "网格住哪儿"是这台
         机器人的 durable 事实，和产物住哪一层无关；`_decor_prefix()` 数的是它。
       · `robots/<key>/<key>.xml` 存**从产物目录看**的 `../robots/g1/meshes` —— 多出来的
         `../` 是 `build/` 那一层的补偿，由 `SCENES.OUT_SUBDIR` 决定。
    ⭐ 这个仓被"同一个量存两处、没人逼它们对账"咬过两次（decor.lock 的包围盒、
       check_scene 的项数），所以这里当场读 XML 核对。

    ⛔ 必须在**每份产物**都跑：它以前挂在 `_decor_prefix()` 里，而那个函数只有**有装饰网格
       的场景**才会调到——house1/house2 没有装饰，于是漏检了三分之二的产物，
       实测把 meshdir 改错后它们照常生成成功。检查要挂在无条件路径上。
    """
    md = ROBOTS.get(robot_key)["meshdir"].strip("/")
    xml_path = ROBOTS.path(robot_key, "xml")
    m = re.search(r'<compiler[^>]*\bmeshdir="([^"]*)"', open(xml_path, encoding="utf-8").read())
    if not m:
        raise ValueError(f"{xml_path} 里没找到 <compiler meshdir=...>，无法核对")
    declared = os.path.normpath(os.path.join(SCENES.OUT_SUBDIR, m.group(1))).replace(os.sep, "/")
    if declared != md:
        raise ValueError(
            f"⛔ meshdir 对不上：{os.path.basename(xml_path)} 声明 {m.group(1)!r}，"
            f"从产物目录 {SCENES.OUT_SUBDIR!r} 解析出来是 {declared!r}，"
            f"而 robots/manifest.py 说是 {md!r}。改了 OUT_SUBDIR 就要同轮改机器人 XML 的 meshdir。")


def _decor_prefix(robot_key: str) -> str:
    """`<mesh file>` 要爬几层 `../` 才回到仓根。

    ⛔ `<compiler meshdir>` 是**整个编译模型全局**的，而且它来自 `<include>` 进来的
       机器人 XML，相对**主模型文件所在目录**解析。所以直接写
       `<mesh file="decor/x.obj">` 会被找成 `<meshdir>/decor/x.obj`。
       在 include 之后再写一个 compiler 会把机器人自己的网格弄丢；写在前面则被覆盖。
    ⚠️ 而 `<texture file>` 走的是 `texturedir`（没设 → 相对主模型目录），**两者解析规则不同**，
       所以贴图不带这个前缀、走 `_root_rel()`。别照抄隔壁那一行。

    ⭐ 同一个 meshdir 在两个地方各存了一份，**语义有意不同**，别去"统一"它们：
       · `robots/manifest.py` 的 `meshdir` = **仓根相对**（`robots/g1/meshes`）——
         "网格住哪儿"是这台机器人的durable 事实，和产物住哪一层无关。本函数数的是它。
       · `robots/<key>/<key>.xml` 的 `meshdir` = **从产物目录看**（`../robots/g1/meshes`）——
         多出来的 `../` 是 `build/` 那一层的补偿，由 `SCENES.OUT_SUBDIR` 决定。
       ⛔ 两处必须指向同一个真实目录。这个仓被"同一个量存两处、没人逼它们对账"咬过两次
          （decor.lock 的包围盒、check_scene 的项数），所以下面**当场读 XML 交叉核对**。
    ✅ `..` 本身可用，已实测（载入 8738 顶点的机器人网格验证过）。
    """
    md = ROBOTS.get(robot_key)["meshdir"].strip("/")
    if os.path.isabs(md) or ".." in md.split("/"):
        raise ValueError(f"{robot_key} 的 meshdir={md!r} 不是仓根相对的干净路径，算不出 ../ 前缀")

    return "../" * len(md.split("/"))


def _selected_parts(key, parts=None):
    """该资产要用的部件（含原始下标）：`[(i, part_dict), ...]`。

    ⭐ `parts` 是可选的**部件白名单**，用来从"一个文件里装了好几件东西"的上游资产里
       只取一件。目前唯一的用户是 `plant_b`（Poly Haven 把四棵发财树并排摆在一个文件里，
       见 `decor/manifest.py` 那条注释）。`parts=None` 时行为和以前逐字节一致。
    ⚠️ 返回的**下标是原始下标**，不是重新编号的。mesh 名与贴图去重都按它走，
       所以"只取一棵树"不会让别处的 `dm_<key>_<i>` 改名。
    """
    from decor import lock
    ps = list(enumerate(lock.parts(key)))
    if parts is None:
        return ps
    want = set(int(i) for i in parts)
    bad = want - {i for i, _ in ps}
    if bad:
        raise ValueError(f"资产 {key!r} 没有第 {sorted(bad)} 个部件（共 {len(ps)} 个）")
    return [(i, p) for i, p in ps if i in want]


def _asset_span(key, parts=None):
    """资产**装配之后**的真实跨度：返回 (全长 xyz, 跨度中心 xyz)。

    ⛔ 不能直接用 lock 里的整件 `size`：`parts` 选出子集时它就不对了，而且它取自
       fetch 期的 trimesh 对象、和落盘 OBJ 差着导出取舍。这里按各部件的
       `offset ± half`（`decor/calibrate.py` 从编译后顶点实测）求并集才是真值。
    ⚠️ 必须把**跨度中心**一起返回并在摆位时减掉：资产往往是偏心的，
       若按"关于原点对称"来算，偏心那一侧就会探出碰撞盒。
       ⭐ 这也是 `parts` 子集能自动归正的原因——中心是按子集算的。
    """
    from decor import lock
    ps = [p for _i, p in _selected_parts(key, parts)]
    if not ps or "half" not in ps[0]:
        return lock.size(key), (0.0, 0.0, 0.0)      # 老 lock 没记部件信息就退回整件包围盒
    lo = [min(float(p["offset"][k]) - float(p["half"][k]) for p in ps) for k in range(3)]
    hi = [max(float(p["offset"][k]) + float(p["half"][k]) for p in ps) for k in range(3)]
    return (tuple(h - l for h, l in zip(hi, lo)),
            tuple((h + l) / 2.0 for h, l in zip(hi, lo)))


def _fit_scale(item: dict, asset_size) -> float:
    """算出让网格**完全装进**碰撞盒的均匀缩放系数。装不进就直接报错。

    ⛔ **不要在这里把 yaw 再转一遍**（2026-08-07 删掉的一段）：`item["size"]` 写的是
       碰撞盒**自己局部系**里的边长，而那个盒子本身就带着同一个 yaw 的 quat
       （产物实证：`<geom name="furn_dn_n0" size="0.23 0.3 0.5" quat="...-0.707107">`）。
       网格用同一个 quat 转，所以盒子和网格**一起转**，比例关系与 yaw 无关。
       老代码额外按"旋转后 AABB"估外廓，等于把 yaw 算了两遍，餐椅因此白缩 23%。
       ⚠️ 当年写下的依据"旋转后 AABB 会低估"也是假的——`ex|cos|+ey|sin|` 是旋转 AABB
       的数学上界，不可能低估；那个"低估"是错跨度（见 `decor/calibrate.py`）的产物。
    """
    sx, sy, sz = item["size"]
    ex, ey, ez = asset_size
    if min(ex, ey, ez) <= 0:
        raise ValueError(f"装饰 {item['name']!r} 的资产包围盒是 {asset_size}，无效")
    return _FIT_EPS * min(sx / ex, sy / ey, sz / ez)


def _decor_items() -> list[dict]:
    """当前场景里所有"要穿外衣"的家具，且资产字节确实在磁盘上。"""
    try:
        from decor import lock
    except ImportError:
        return []
    out = []
    for item in L.FURNITURE:
        spec = item.get("mesh")
        if not spec:
            continue
        key = spec["id"]
        if not lock.has(key):
            print(f"   ⚠️ 装饰 {item['name']}：资产 {key} 不在 decor.lock.json 里，跳过")
            continue
        if not lock.bytes_present(key):
            print(f"   ⚠️ 装饰 {item['name']}：{key} 的字节不在本机，跳过"
                  f"（跑 python -m decor.fetch --only {key}）")
            continue
        out.append(item)
    return out


def _mesh_assets(robot_key: str) -> list[str]:
    """装饰网格的 <mesh>/<texture>/<material> 声明。"""
    items = _decor_items()
    if not items:
        return []
    from decor import lock
    pre = _decor_prefix(robot_key)
    out = ['', '    <!-- ===== 装饰网格资产（decor/manifest.py 登记，decor.lock.json 落账）===== -->']
    # ⚠️ 两套去重，**粒度不同**，别合成一套：
    #    - <mesh> 按 (资产, 部件, **缩放**) —— scale 是 <mesh> 的属性不是 <geom> 的，
    #      同一资产装进不同大小的盒子必须各自一份；
    #    - <texture>/<material> 按 (资产, 部件) —— 和缩放无关，八把共用同一张贴图的餐椅
    #      如果跟着 mesh 一起去重，就会重复声明八次，MuJoCo 直接
    #      "repeated name 'dt_dining_chair_0' in texture" 拒绝编译。
    seen_mesh, seen_tex = set(), set()
    for item in items:
        key = item["mesh"]["id"]
        sel = item["mesh"].get("parts")
        span, ctr = _asset_span(key, sel)
        scale = _fit_scale(item, span)
        for i, p in _selected_parts(key, sel):
            tag = f"{key}_{i}_{scale:.4f}".replace(".", "_")
            if tag not in seen_mesh:
                seen_mesh.add(tag)
                out.append(f'    <mesh name="dm_{tag}" file="{pre}{lock.rel_path(key, p["obj"])}" '
                           f'scale="{scale:g} {scale:g} {scale:g}"/>')
            if p.get("png") and (key, i) not in seen_tex:
                seen_tex.add((key, i))
                out.append(f'    <texture type="2d" name="dt_{key}_{i}" '
                           f'file="{_root_rel(lock.rel_path(key, p["png"]))}" colorspace="sRGB"/>')
                override = getattr(L, "DECOR_MATERIAL_OVERRIDES", {}).get(key, {})
                if override:
                    props = dict(texture=f"dt_{key}_{i}",specular=.15,shininess=.25,reflectance=0)
                    props.update(override.get(str(i), override.get("all", {})))
                    attrs = " ".join(f'{k}="{v}"' for k,v in props.items() if v is not None)
                    out.append(f'    <material name="dmat_{key}_{i}" {attrs}/>')
                else:
                    out.append(f'    <material name="dmat_{key}_{i}" texture="dt_{key}_{i}" '
                               f'specular="0.15" shininess="0.25" reflectance="0.02"/>')
    # ⭐ 碰撞凸块的 <mesh>。去重粒度和视觉网格一样是 (资产, 第几块, **缩放**)——
    #    8 把餐椅只声明一套，所以"重复摆放几乎免费"（实测 nmeshgraph 与件数无关）。
    hull_items = [it for it in items if _has_hulls(it)]
    if hull_items:
        out.append('')
        out.append('    <!-- ===== 碰撞凸块（CoACD；生成见 decor/hulls.py）===== -->')
        seen_hull = set()
        for item in hull_items:
            key = item["mesh"]["id"]
            scale, _q, _pos = _mesh_placement(item)
            for i, f in enumerate(lock.hulls(key)):
                tag = f"{key}_{i}_{scale:.4f}".replace(".", "_")
                if tag in seen_hull:
                    continue
                seen_hull.add(tag)
                out.append(f'    <mesh name="dh_{tag}" file="{pre}{lock.rel_path(key, f["obj"])}" '
                           f'scale="{scale:g} {scale:g} {scale:g}"/>')
    return out


def _mesh_placement(item: dict) -> tuple[float, tuple, tuple]:
    """一件家具的网格该缩多少、转多少、摆在哪 —— **视觉外衣与碰撞凸块共用这一份**。

    返回 `(scale, quat, (x, y, z))`。同一件资产的所有部件/凸块共用同一组值，
    因为部件之间的相对位置**已经烘在 OBJ 文件坐标里**了（`decor/convert.py` 按整件
    包围盒中心统一居中）。

    ⛔⛔ 这个函数存在的唯一理由是：外衣和凸块必须用**逐位相同**的变换。
       它们要是各算各的，网格和碰撞体就会错开，而且**编译不报错、渲染看着也正常**——
       只有射线打上去才发现"看见的地方摸不着"。本仓已经在"同一个量存两处"上栽过
       （见 `decor/calibrate.py` 顶部那段），⛔ 别把它拆回两份。
    """
    spec = item["mesh"]
    key, sel = spec["id"], spec.get("parts")
    span, ctr = _asset_span(key, sel)
    scale = _fit_scale(item, span)
    yaw = float(spec.get("yaw", 0.0))
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    px, py, pz = item["pos"]
    ox, oy, oz = spec.get("offset", (0.0, 0.0, 0.0))
    # ⭐ 所有部件共用同一个偏移 `-ctr`：把整件摆正到碰撞盒中心，
    #    偏心资产（以及 `parts` 选出的子集）才不会探出一侧。⚠️ 偏移要跟着 yaw 转再乘缩放。
    # ⛔⛔ 这里**绝不能再加每个部件自己的重心/包围盒中心**（2026-08-07 删掉的一段）。
    #    MuJoCo 编译 <mesh> 时虽然把顶点搬进了惯性系，却把那个重定位量**抄进
    #    geom_pos/geom_quat 自己补偿掉了**——实测 `<geom type="mesh" pos="0 0 0">`
    #    的世界 bbox 与 OBJ 文件 bbox 逐位相同。老代码用 `lock.part_offset()` 又加了一遍，
    #    条案两条柜腿各飞 ±0.49 m，这才是 console / nightstand 当年被判红的真因。
    fx, fy, fz = (-c for c in ctr)
    x = px + ox + (fx * ca - fy * sa) * scale
    y = py + oy + (fx * sa + fy * ca) * scale
    z = pz + _zbase(item["room"]) + oz + fz * scale
    return scale, yaw_quat(yaw), (x, y, z)


def _hull_geoms(item: dict) -> list[str]:
    """一件家具的 CoACD 碰撞凸块 —— 它们**就是**这件家具的碰撞真相。

    ⛔ 每一块都必须带 `solref`（值取 `decor.lock.HULL_SOLREF`，那边写了为什么）：
       MuJoCo 默认接触太软，快速撞击会直接穿过去，而且**编译不报错、慢速测试全绿**。

    分组走 `HIDDEN_BOX_GROUP`（4）：它们不该被画出来（画的是外面那张视觉网格），
    但**照样参与碰撞、也照样挡射线**——这正是我们要的，雷达看到的就是真实形状。
    """
    from decor import lock
    key = item["mesh"]["id"]
    scale, q, (x, y, z) = _mesh_placement(item)
    rot = _rot_attr(quat=q)
    out = [f'    <!-- {item["name"]}：{len(lock.hulls(key))} 块 CoACD 凸块 = 真碰撞体 -->']
    for i, _f in enumerate(lock.hulls(key)):
        tag = f"{key}_{i}_{scale:.4f}".replace(".", "_")
        out.append(f'    <geom name="furn_{item["name"]}__h{i}" type="mesh" mesh="dh_{tag}" '
                   f'pos="{x:g} {y:g} {z:g}"{rot} '
                   f'group="{HIDDEN_BOX_GROUP}" solref="{lock.HULL_SOLREF}"/>')
    return out


def _decor_geoms(items=None) -> list[str]:
    """装饰网格几何。整体收在一个 body 里，方便自检做 bodyexclude 的 A/B 对照。"""
    if items is None:
        items = [item for item in _decor_items() if not item.get("articulated") and not item.get("movable")]
    if not items:
        return []
    out = ['    <!-- ===== 装饰网格（纯视觉外衣；碰撞仍由下面那些 box 承担）=====',
           '         ⚠️ mj_ray 不看 contype——射线安全靠的是"包含性不变式"：',
           '            每张网格都缩放进它的碰撞盒里，所以盒子永远先被打中。 -->',
           '    <body name="decor_visual">']
    for item in items:
        spec = item["mesh"]
        key = spec["id"]
        sel = spec.get("parts")
        # ⭐ 缩放 / 朝向 / 摆位由 `_mesh_placement()` 统一算 —— 碰撞凸块读的是**同一份**，
        #    两边各算一遍就会错开，而且编译不报错、渲染看着也正常（见那个函数的注释）。
        scale, q, (gx, gy, gz) = _mesh_placement(item)
        for i, p in _selected_parts(key, sel):
            tag = f"{key}_{i}_{scale:.4f}".replace(".", "_")
            look = (f'material="dmat_{key}_{i}"' if p.get("png")
                    else f'rgba="{_rgba(item["rgba"])}"')
            out.append(f'      <geom name="dg_{item["name"]}_{i}" type="mesh" mesh="dm_{tag}" '
                       f'{look} pos="{gx:g} {gy:g} {gz:g}"'
                       f'{_rot_attr(quat=q)} contype="0" conaffinity="0" density="0"/>')
    out.append('    </body>')
    return out


# ---------------------------------------------------------------------- 组装
def build(robot_key: str) -> str:
    global _CONTACT_EXCLUDES, _BUILD_ANGLE
    _CONTACT_EXCLUDES = []
    r = ROBOTS.get(robot_key)
    compiler = ET.parse(os.path.join(ROOT, r["xml"])).find("compiler")
    _BUILD_ANGLE = compiler.get("angle", "degree") if compiler is not None else "degree"
    parts: list[str] = []
    parts.append(f'<mujoco model="sim_house_nav_{robot_key}">')
    parts.append('  <!-- 本文件由 make_house.py 从 layout.py 生成，请勿手改；改屋子改 layout.py 后重跑生成器。 -->')
    parts.append(f'  <!-- 机器人：{r["label"]}（清单见 ../robots/manifest.py） -->')
    # 机器人的 XML 与网格都住在 robots/<key>/，从这里按相对路径 include。
    # meshdir 由机器人自己的 XML 声明（导入脚本写好的），这里不重复声明、免得两处打架。
    _assert_meshdir_agrees(robot_key)   # ⛔ 每份产物都核一次，见该函数的 docstring
    parts.append('  <include file="'
                 + _root_rel(f'robots/{robot_key}/{os.path.basename(r["xml"])}') + '"/>')
    parts.append('')
    # ⚠️ 必须显式声明场景尺度：MuJoCo 默认按模型包围盒自动算 extent，而我们为了"窗外有风景"
    # 加了 60m 草地和几十米高的远楼，包围盒被撑到几十米 → 近裁剪面(znear ∝ extent)跟着变大，
    # **把狗脚边的地板裁没了**（实测症状：第一视角画面底部地板下方露出天空）。
    # 把 extent 钉在屋子尺度上，近处几何才不会被裁掉。
    _stat = getattr(L, "STATISTIC", {"center": "0 -1 1", "extent": 6})
    parts.append(f'  <statistic center="{_stat["center"]}" extent="{_stat["extent"]:g}"/>')
    parts.append('')
    # 场景可以覆盖这几项。apt1 必须覆盖 zfar（默认 60×extent 6 = 360 m，脚下 1200 m 的
    # 地面板会被裁掉一半，看起来像大气雾霾、其实是裁剪 bug）和 shadowclip（默认 1×extent = 6 m
    # 的阴影体，装不下 23×15 m 的公寓，大半个屋子根本没影子——这就是"MuJoCo 阴影不行"的误解来源）。
    V = getattr(L, "VISUAL", {})
    parts.append('  <visual>')
    _map = f'    <map znear="{V.get("znear", 0.02):g}" zfar="{V.get("zfar", 60):g}"'
    if "shadowclip" in V:
        _map += f' shadowclip="{V["shadowclip"]:g}"'
    parts.append(_map + '/>')
    parts.append(f'    <headlight diffuse="{V.get("headlight_diffuse", "0.45 0.45 0.45")}" '
                 f'ambient="{V.get("headlight_ambient", "0.34 0.34 0.34")}" '
                 f'specular="{V.get("headlight_specular", "0.1 0.1 0.1")}"/>')
    parts.append(f'    <quality shadowsize="{V.get("shadowsize", 4096)}"/>')
    # 离屏缓冲尺寸：MuJoCo 默认只有 640×480，超出就直接报错。放宽到 1080p，
    # 好出高清写真/报告媒体；世界服务给大脑的画面仍按 config 的 CAM_W/CAM_H（小图省 token）。
    parts.append(f'    <global azimuth="120" elevation="-20" offwidth="{OFFSCREEN_W}" offheight="{OFFSCREEN_H}"/>')
    parts.append('  </visual>')
    parts.append('')
    parts.extend(_assets(robot_key))
    parts.append('')
    parts.append('  <worldbody>')
    parts.extend(_lights())
    parts.append('')
    # ⭐ 电影机位探针：给录像/出图工具用的具名相机。消费方按名字 mj_name2id 取到它之后
    #    逐帧改写 cam_pos / cam_quat / cam_fovy（挂在 worldbody 上 ⇒ cam_bodyid=0，
    #    写进去的就是世界坐标）——任意位置 + 俯仰 + 荷兰角 + 变焦都从这一只相机出。
    #    ⚠️ 写完 model 字段必须调 mj_camlight(m, d) 才会刷进 data.cam_xpos；
    #       只写 model 的话相机纹丝不动、画面却照常渲（实测过的静默坑）。
    #    初始位姿只是占位（场景统计中心、朝北），⛔ 别依赖它——每一帧都该被改写。
    parts.append(f'    <camera name="film" pos="{_stat["center"]}" xyaxes="1 0 0 0 0 1"/>')
    parts.append('')
    # ⛔⛔ 发射顺序：**室内在前，窗外在后**。这不是风格问题，是安全阀。
    #
    #    MuJoCo 渲染时按 geom 在模型里的**先后顺序**填 `mjvScene` 的缓冲，**不按距离**；
    #    缓冲满了只打一条 warning（"Pre-allocated visual geom buffer is full"），
    #    **不报错**，多出来的直接不画。而 `maxgeom` **不能在 MJCF 里声明**
    #    （`<visual><global maxgeom>` 是 schema violation），它是调用方参数：
    #    `mujoco.Renderer` 默认 10000、`walkthrough.py` 设了 20000、消费方各写各的。
    #    **场景文件保护不了自己。**
    #
    #    2026-08-06 实测（12200 个 geom）：窗景排在前面时，一旦溢出，
    #    **近处 200 件家具一个都进不去**（0/200），远处的楼反而占满缓冲。
    #    也就是说最坏情况是"公寓凭空消失、窗外风景完好"。
    #    倒过来之后，最坏情况降级成"远处少几栋楼"——同样的溢出，后果天差地别。
    #    ⛔ 别为了"先画背景再画前景"这种直觉把顺序改回去。
    for key in L.ROOMS:
        parts.append(f'    <!-- ===== {L.ROOMS[key]["label"]} ===== -->')
        parts.extend(_floor_geom(key))
        ceiling_geom = _ceiling_geom(key)
        if ceiling_geom:
            parts.append(ceiling_geom)
        parts.extend(_wall_geoms(key))
        for item in L.FURNITURE:
            if item["room"] == key:
                parts.extend(_furniture_parts(item))
        parts.append('')
    decor = _decor_geoms()               # 装饰网格外衣（阶段 E；没资产就是空的）
    if decor:
        parts.extend(decor)
        parts.append('')
    art_geoms = _wall_arts()             # 声明了挂画才出；house2 没声明就是空的
    if art_geoms:
        parts.extend(art_geoms)
        parts.append('')
    glass = _glazing()                   # ⛔ 落地窗的玻璃，参与碰撞
    if glass:
        parts.extend(glass)
        parts.append('')
    # 入户门（玄关南外墙上的门板 + 把手，纯视觉；狗在屋里活动、不出门）
    stair_geoms = _stairs()
    if stair_geoms:                      # 单层场景没有楼梯，连分隔空行都不该多出来
        parts.extend(stair_geoms)
        parts.append('')
    parts.extend(_front_door())
    for item in getattr(L, "ARCHITECTURE", []):
        parts.extend(_residence_parts(item))
    for item in getattr(L, "EXTERIOR_GEOMS", []):
        parts.extend(_residence_parts(item))
    parts.append('')
    # ── 窗外的一切放在最后发射（理由见上面那段 ⛔）────────────────────────
    parts.extend(_outdoor())
    parts.append('')
    backdrop = _city_backdrop()
    if backdrop:
        parts.extend(backdrop)
        parts.append('')
    view = _view()                       # 高层窗景四层（apt1 用；老场景没声明就是空的）
    if view:
        parts.extend(view)
        parts.append('')
    for item in getattr(L, "BACKGROUND_GEOMS", []):
        parts.extend(_residence_parts(item))
    parts.append('  </worldbody>')
    if _CONTACT_EXCLUDES:
        contact = ET.Element("contact")
        for first, second in _CONTACT_EXCLUDES:
            ET.SubElement(contact, "exclude", body1=first, body2=second)
        parts.append("  " + ET.tostring(contact, encoding="unicode"))
    parts.append('</mujoco>')
    return "\n".join(parts) + "\n"


def scene_filename(scene_key: str, robot_key: str) -> str:
    """(场景, 机器人) 对应的产物文件名 —— 转发到 scenes/manifest.py 的同名函数。

    单一真相源在那边：世界服务也按它去找，两边别各写各的。
    """
    return SCENES.scene_filename(scene_key, robot_key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot", default="", help=f"只生成这一台（{'/'.join(ROBOTS.ROBOTS)}）；不给=全部")
    ap.add_argument("--scene", default="", help=f"只生成这个场景（{'/'.join(SCENES.keys())}）；不给=全部")
    ap.add_argument("--out", default="", help="指定输出文件（只在 --robot + --scene 都单指定时有意义）")
    args = ap.parse_args()
    here = ROOT
    robot_keys = [args.robot] if args.robot else list(ROBOTS.ROBOTS)
    scene_keys = [args.scene] if args.scene else SCENES.keys()
    if args.out and (len(robot_keys) != 1 or len(scene_keys) != 1):
        ap.error("--out 只能配合 --robot + --scene 一起用（一次只写一个文件）")
    if args.out:
        # ⛔ 产物里的相对路径（`../textures`、`../robots`、`../../../decor`）是按
        #    "住在仓根下**恰好一层**"算死的。落到别的深度，XML 长得一模一样、写文件也
        #    照常成功，只有 MuJoCo 去加载时才报"找不到网格/贴图"——典型的静默产出坏文件。
        #    这里当场拦住，别让人拿着一份看着正常的坏产物去排查。
        d = os.path.relpath(os.path.dirname(os.path.abspath(args.out)), here)
        if d.startswith("..") or os.sep in d or d == ".":
            ap.error(f"--out 必须落在仓根下**恰好一层**的目录里（现在是 {d!r}）——"
                     f"产物里的 ../ 层数按那一层算死了。默认落点是 {SCENES.OUT_SUBDIR}/。")

    for scene_key in scene_keys:
        use_scene(scene_key)
        _generate(here, scene_key, robot_keys, args.out)


def _generate(here: str, scene_key: str, robot_keys: list[str], out_override: str) -> None:
    area = sum((r["rect"][2] - r["rect"][0]) * (r["rect"][3] - r["rect"][1]) for r in L.ROOMS.values())
    print(f"── 场景 {scene_key}：{SCENES.get(scene_key)['label']}")
    for key in robot_keys:
        out_path = out_override or os.path.join(here, scene_filename(scene_key, key))
        xml = build(key)
        # 产物住 build/，裸 clone 上第一次跑时那个目录还不存在
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"生成 {out_path}  ← {ROBOTS.get(key)['label']}")
        stairs = getattr(L, "STAIRS", [])
        extra = f"、{len(stairs)} 跑楼梯（共 {sum(f['risers'] for f in stairs)} 级踢面）" if stairs else ""
        print(f"  {len(L.ROOMS)} 个空间（净面积 {area:.0f} ㎡）、{xml.count('<geom ')} 个 geom、"
              f"{len(L.FURNITURE)} 件家具{extra}")
    print(f"  {len(L.DOORS)} 处门/通道、{len(L.WINDOWS)} 扇窗、层高 {L.WALL_HEIGHT}m（已封天花板）")
    print(f"  屋外 {len(L.TREES)} 棵树、{len(L.BUILDINGS)} 栋远楼")


if __name__ == "__main__":
    main()
