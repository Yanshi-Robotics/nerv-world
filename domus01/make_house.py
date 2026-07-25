#!/usr/bin/env python3
"""由 layout.py 生成屋子场景 house.xml（MJCF）。

照搬 locomotion 仓 scenes/mujoco/make_building.py 的思路：几何不在 XML 里手写，
而是从**一份布局定义**翻译出来——改屋子只改 layout.py，场景与世界服务同时生效。

产物 house.xml = 完整可跑模型：
  三间屋（地板 / 带门窗洞的墙 / 门框窗框 / 家具 / 灯）
  + 屋外景色（草地、树、远处楼房，从窗口望得见）
  + `<include>` 进来的 Go2（带头部前视相机）

用法：
    python make_house.py            # 生成到同目录 house.xml
    python make_house.py 输出.xml    # 指定输出

⚠️ 单位换算只在这里做一次：layout.py 写的是**全长**，MJCF 的 box/cylinder size 要**半长**。
"""
from __future__ import annotations

import os
import sys

import layout as L

# 离屏渲染缓冲上限（决定最大可渲染分辨率）。留足 1080p，够出写真与报告插图。
OFFSCREEN_W, OFFSCREEN_H = 1920, 1080


def _half(v: float) -> float:
    """全长 → 半长（MJCF size 要半长）。"""
    return v / 2.0


def _rgba(c) -> str:
    return " ".join(f"{v:g}" for v in c)


def _box(name: str, pos, size, rgba, extra: str = "", mat: str = "", euler=None) -> str:
    """一个 box geom（size 传全长，这里统一折半）。给了 mat 就用材质，否则用纯色。"""
    look = f'material="{mat}"' if mat else f'rgba="{_rgba(rgba)}"'
    rot = f' euler="{euler[0]:g} {euler[1]:g} {euler[2]:g}"' if euler else ""
    return (f'    <geom name="{name}" type="box" '
            f'size="{_half(size[0]):g} {_half(size[1]):g} {_half(size[2]):g}" '
            f'pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}"{rot} {look}{extra}/>')


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
             if d["orient"] == want and abs(d["coord"] - fixed) < 1e-6 and lo <= d["center"] <= hi]
    # 窗多带一个窗台高度：普通窗用默认值，落地窗在 layout 里用 "sill" 覆盖成贴地
    windows = [(w["center"], w["width"], w.get("sill", L.WINDOW_SILL_H)) for w in L.WINDOWS
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
        all_gaps = [(c, w) for c, w, _k in doors] + [(c, w) for c, w, _s in windows]
        for a, b in _solid_runs(lo, hi, all_gaps):
            rects.append((a, b, 0.0, H))                      # 整高实墙
        for c, w, kind in doors:                               # 门楣（整段拆除的通道没有门楣）
            if kind != "open":
                rects.append((c - w / 2, c + w / 2, L.DOOR_HEIGHT, H))
        for c, w, sill in windows:                             # 窗台墙 + 窗楣墙
            if sill > 1e-6:                                    # 落地窗窗台≈0，就不画下面那截
                rects.append((c - w / 2, c + w / 2, 0.0, sill))
            rects.append((c - w / 2, c + w / 2, L.WINDOW_TOP_H, H))

        for i, (a, b, z0, z1) in enumerate(rects):
            if b - a < 1e-6 or z1 - z0 < 1e-6:
                continue
            along_c, along_len = (a + b) / 2.0, b - a
            zc, zlen = (z0 + z1) / 2.0, z1 - z0
            pos = (along_c, fixed_c, zc) if horizontal else (fixed_c, along_c, zc)
            size = (along_len, t, zlen) if horizontal else (t, along_len, zlen)
            out.append(_box(f"{room_key}_w{side}{i}", pos, size, rgba,
                            mat=room.get("wall_mat", "")))

        # 门框 / 窗框（纯视觉，让洞口看起来是"一扇门/一扇窗"而不是墙上一个豁口）
        for j, (c, w, kind) in enumerate(doors):
            if kind == "open":      # 墙整段拆了，没有门框可画
                continue
            out += _frame(f"{room_key}_df{side}{j}", horizontal, c, w, fixed_c, t,
                          0.0, L.DOOR_HEIGHT, L.DOOR_FRAME_RGBA, L.DOOR_FRAME_THICK, bottom=False)
        for j, (c, w, sill) in enumerate(windows):
            out += _frame(f"{room_key}_wf{side}{j}", horizontal, c, w, fixed_c, t,
                          sill, L.WINDOW_TOP_H, L.WINDOW_FRAME_RGBA, L.WINDOW_FRAME_T,
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
def _floor_geom(room_key: str) -> str:
    room = L.ROOMS[room_key]
    x0, y0, x1, y1 = room["rect"]
    return _box(f"{room_key}_floor",
                ((x0 + x1) / 2.0, (y0 + y1) / 2.0, -_half(L.FLOOR_THICK)),
                (x1 - x0, y1 - y0, L.FLOOR_THICK), room["floor_rgba"],
                mat=room.get("floor_mat", ""))


def _furniture_geom(item: dict) -> str:
    sx, sy, sz = item["size"]
    mat, eu = item.get("mat", ""), item.get("euler")
    if item["type"] in ("cylinder", "sphere"):
        look = f'material="{mat}"' if mat else f'rgba="{_rgba(item["rgba"])}"'
        rot = f' euler="{eu[0]:g} {eu[1]:g} {eu[2]:g}"' if eu else ""
        # cylinder 的 size = (半径, 半高)；sphere 只要半径；layout 里一律写 (直径, 直径, 高)
        dims = f'{_half(sx):g}' if item["type"] == "sphere" else f'{_half(sx):g} {_half(sz):g}'
        return (f'    <geom name="furn_{item["name"]}" type="{item["type"]}" size="{dims}" '
                f'pos="{item["pos"][0]:g} {item["pos"][1]:g} {item["pos"][2]:g}"{rot} {look}/>')
    return _box(f'furn_{item["name"]}', item["pos"], item["size"], item["rgba"], mat=mat, euler=eu)


def _ceiling_geom(room_key: str) -> str:
    """天花板：封顶，狗抬头看到的是屋顶而不是天空。

    单独归一个 geom group（CEILING_GROUP），出俯视写真时把这一组关掉就能看清屋内布局，
    而第一视角照常渲染——不用维护两份场景。
    """
    room = L.ROOMS[room_key]
    x0, y0, x1, y1 = room["rect"]
    zc = L.WALL_HEIGHT + _half(L.CEILING_THICK)
    return _box(f"{room_key}_ceiling", ((x0 + x1) / 2.0, (y0 + y1) / 2.0, zc),
                (x1 - x0, y1 - y0, L.CEILING_THICK), L.CEILING_RGBA,
                extra=f' group="{L.CEILING_GROUP}"')


def _lights() -> list[str]:
    """每间屋一盏吸顶灯 —— 封了顶之后天光进不来，室内全靠这些灯，没灯就是一片黑。"""
    out = []
    for key, room in L.ROOMS.items():
        x0, y0, x1, y1 = room["rect"]
        out.append(
            f'    <light name="light_{key}" pos="{(x0 + x1) / 2.0:g} {(y0 + y1) / 2.0:g} '
            f'{L.WALL_HEIGHT - 0.15:g}" dir="0 0 -1" diffuse="0.62 0.61 0.58" '
            f'specular="0.05 0.05 0.05" attenuation="0.55 0.06 0.010"/>')
    # 屋外一盏"太阳"，让窗外的草地树木亮起来（否则窗外一片死黑，白开窗）
    out.append('    <light name="sun" pos="10 -18 22" dir="-0.35 0.62 -0.70" directional="true" '
               'diffuse="0.55 0.54 0.50" specular="0.10 0.10 0.10"/>')
    return out


def _assets() -> list[str]:
    """<asset> 段：天空盒 + 程序化贴图（make_textures.py 生成）+ 材质定义。

    材质带 specular/shininess/reflectance：金属龙头会有高光、玻璃隔断半透、瓷砖有光泽感——
    这些属性比几何体本身更能把"积木感"压下去。
    """
    out = ['  <asset>']
    out.append('    <texture type="skybox" builtin="gradient" rgb1="0.52 0.68 0.88" '
               'rgb2="0.88 0.92 0.96" width="512" height="1024"/>')
    # 贴图（file 路径相对本 XML 所在目录）
    for name in ("wood_floor", "wood_floor_light", "tile_white", "tile_grey",
                 "marble", "marble_dark", "carpet", "fabric", "fabric_blue", "wall_paint",
                 "city_skyline", "art0", "art1", "art2", "art3"):
        out.append(f'    <texture type="2d" name="tex_{name}" file="textures/{name}.png"/>')
    # 材质：texrepeat 控制平铺密度（数字越大格子越小）
    mats = [
        ("mat_wood", "tex_wood_floor", 3, 3, 0.15, 0.25, 0.02),
        ("mat_wood_light", "tex_wood_floor_light", 3, 3, 0.15, 0.25, 0.02),
        ("mat_tile", "tex_tile_white", 4, 4, 0.35, 0.55, 0.12),
        ("mat_tile_grey", "tex_tile_grey", 4, 4, 0.35, 0.55, 0.12),
        ("mat_marble", "tex_marble", 2, 2, 0.45, 0.70, 0.15),
        ("mat_marble_dark", "tex_marble_dark", 2, 2, 0.45, 0.70, 0.15),
        ("mat_carpet", "tex_carpet", 4, 4, 0.02, 0.05, 0.0),
        ("mat_fabric", "tex_fabric", 6, 6, 0.05, 0.10, 0.0),
        ("mat_fabric_blue", "tex_fabric_blue", 6, 6, 0.05, 0.10, 0.0),
        ("mat_wall", "tex_wall_paint", 2, 2, 0.05, 0.10, 0.0),
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
    out.append('  </asset>')
    return out


def _wall_arts() -> list[str]:
    """墙上挂画：画心（贴图）+ 四周画框。贴在指定房间指定墙的内表面上。"""
    out: list[str] = ['    <!-- ===== 墙上挂画（视觉干扰项）===== -->']
    t = L.WALL_THICK
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
        if horizontal:
            pos, size = (c, fixed + off, z), (w, 0.03, h)
            fpos, fsize = (c, fixed + off * 0.6, z), (w + 2 * L.ART_FRAME_T, 0.04, h + 2 * L.ART_FRAME_T)
        else:
            pos, size = (fixed + off, c, z), (0.03, w, h)
            fpos, fsize = (fixed + off * 0.6, c, z), (0.04, w + 2 * L.ART_FRAME_T, h + 2 * L.ART_FRAME_T)
        out.append(_box(f"artframe{i}", fpos, fsize, L.ART_FRAME_RGBA))
        out.append(_box(f"art{i}", pos, size, (1, 1, 1, 1), mat=f'mat_{a["tex"]}'))
    return out


def _city_backdrop() -> list[str]:
    """屋外四面城市背景板：贴天际线贴图的大立面，任何一扇窗望出去都能看到城市。"""
    cb = L.CITY_BACKDROP
    d, w, h, z = cb["dist"], cb["width"], cb["height"], cb["z"]
    out = ['    <!-- ===== 城市背景板（窗外风景）===== -->']
    for name, pos, size in [
            ("north", (0, d, z), (w, 0.4, h)),
            ("south", (0, -d, z), (w, 0.4, h)),
            ("east", (d, 0, z), (0.4, w, h)),
            ("west", (-d, 0, z), (0.4, w, h))]:
        out.append(_box(f"city_{name}", pos, size, (1, 1, 1, 1), mat="mat_city"))
    return out


def _outdoor() -> list[str]:
    """屋外景色：草地 + 树 + 远处楼房。从窗口望出去有东西可看，屋子才不像个盒子。"""
    out: list[str] = ['    <!-- ===== 屋外景色（透过窗户看得见）===== -->']
    g = L.OUTDOOR_GROUND
    out.append(_box("outdoor_ground", g["pos"], g["size"], g["rgba"]))
    for i, (x, y, trunk_h, crown_d) in enumerate(L.TREES):
        out.append(f'    <geom name="tree{i}_trunk" type="cylinder" '
                   f'size="{0.16:g} {_half(trunk_h):g}" pos="{x:g} {y:g} {_half(trunk_h):g}" '
                   f'rgba="{_rgba(L.TRUNK_RGBA)}"/>')
        out.append(f'    <geom name="tree{i}_crown" type="sphere" size="{_half(crown_d):g}" '
                   f'pos="{x:g} {y:g} {trunk_h + crown_d * 0.35:g}" '
                   f'rgba="{_rgba(L.FOLIAGE_RGBA)}"/>')
    for i, (x, y, sx, sy, h, rgba) in enumerate(L.BUILDINGS):
        out.append(_box(f"bldg{i}", (x, y, h / 2.0), (sx, sy, h), rgba))
    return out


# ---------------------------------------------------------------------- 组装
def build() -> str:
    parts: list[str] = []
    parts.append('<mujoco model="sim_house_nav">')
    parts.append('  <!-- 本文件由 make_house.py 从 layout.py 生成，请勿手改；改屋子改 layout.py 后重跑生成器。 -->')
    parts.append('  <include file="go2.xml"/>')
    parts.append('')
    # ⚠️ 必须显式声明场景尺度：MuJoCo 默认按模型包围盒自动算 extent，而我们为了"窗外有风景"
    # 加了 60m 草地和几十米高的远楼，包围盒被撑到几十米 → 近裁剪面(znear ∝ extent)跟着变大，
    # **把狗脚边的地板裁没了**（实测症状：第一视角画面底部地板下方露出天空）。
    # 把 extent 钉在屋子尺度上，近处几何才不会被裁掉。
    parts.append('  <statistic center="0 -1 1" extent="6"/>')
    parts.append('')
    parts.append('  <visual>')
    parts.append('    <map znear="0.02" zfar="60"/>')
    parts.append('    <headlight diffuse="0.45 0.45 0.45" ambient="0.34 0.34 0.34" specular="0.1 0.1 0.1"/>')
    parts.append('    <quality shadowsize="4096"/>')
    # 离屏缓冲尺寸：MuJoCo 默认只有 640×480，超出就直接报错。放宽到 1080p，
    # 好出高清写真/报告媒体；世界服务给大脑的画面仍按 config 的 CAM_W/CAM_H（小图省 token）。
    parts.append(f'    <global azimuth="120" elevation="-20" offwidth="{OFFSCREEN_W}" offheight="{OFFSCREEN_H}"/>')
    parts.append('  </visual>')
    parts.append('')
    parts.extend(_assets())
    parts.append('')
    parts.append('  <worldbody>')
    parts.extend(_lights())
    parts.append('')
    parts.extend(_outdoor())
    parts.append('')
    parts.extend(_city_backdrop())
    parts.append('')
    for key in L.ROOMS:
        parts.append(f'    <!-- ===== {L.ROOMS[key]["label"]} ===== -->')
        parts.append(_floor_geom(key))
        parts.append(_ceiling_geom(key))
        parts.extend(_wall_geoms(key))
        for item in L.FURNITURE:
            if item["room"] == key:
                parts.append(_furniture_geom(item))
        parts.append('')
    # 入户门（玄关南外墙上的门板 + 把手，纯视觉；狗在屋里活动、不出门）
    parts.append('    <!-- 入户门（视觉件） -->')
    parts.append(_box("front_door", L.FRONT_DOOR["pos"], L.FRONT_DOOR["size"], L.FRONT_DOOR["rgba"]))
    parts.append(_box("front_door_handle", L.FRONT_DOOR_HANDLE["pos"],
                      L.FRONT_DOOR_HANDLE["size"], L.FRONT_DOOR_HANDLE["rgba"]))
    parts.append('')
    parts.append('  </worldbody>')
    parts.append('</mujoco>')
    return "\n".join(parts) + "\n"


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "house.xml")
    xml = build()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    area = sum((r["rect"][2] - r["rect"][0]) * (r["rect"][3] - r["rect"][1]) for r in L.ROOMS.values())
    print(f"生成 {out_path}")
    print(f"  {len(L.ROOMS)} 个空间（净面积 {area:.0f} ㎡）、{xml.count('<geom ')} 个 geom、"
          f"{len(L.FURNITURE)} 件家具")
    print(f"  {len(L.DOORS)} 处门/通道、{len(L.WINDOWS)} 扇窗、层高 {L.WALL_HEIGHT}m（已封天花板）")
    print(f"  屋外 {len(L.TREES)} 棵树、{len(L.BUILDINGS)} 栋远楼")


if __name__ == "__main__":
    main()
