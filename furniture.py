"""参数化家具构件库 —— 把"一件家具"拆成多个零件生成。

为什么要这个：直接在 layout 里手写基本体，一把椅子就只剩"座面+靠背"两块板悬在空中，
一眼假。真实家具是有**腿、横撑、底盘、收口**的。这里每个函数生成一整套零件，
调一次就得到一件像样的家具，还能带朝向（yaw）。

约定：
  · 每个函数返回 list[dict]，字段与 layout.FURNITURE 的条目一致
    （name / room / type / pos / size / rgba，可选 mat、euler）
  · size 一律写**全长**（与 layout 同约定），make_house.py 负责折半
  · yaw 单位是度，绕 z 轴；0 = 朝 +x（东），90 = 朝 +y（北）
    ⚠️ 度只是**这个库对外的说法**；写进 dict 的是 quat（见 _p 的说明），
       因为 MJCF 那边的 euler 单位跟着全局 <compiler angle> 走，靠不住。
"""
from __future__ import annotations

import math

WOOD = (0.46, 0.33, 0.22, 1.0)
WOOD_DARK = (0.34, 0.24, 0.16, 1.0)
METAL = (0.42, 0.43, 0.46, 1.0)


def _rot(dx: float, dy: float, yaw_deg: float) -> tuple[float, float]:
    """把家具局部坐标的偏移量按 yaw 旋转到世界坐标。"""
    a = math.radians(yaw_deg)
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def _p(name, room, typ, pos, size, rgba, mat="", yaw=0.0):
    """把一个零件打包成 layout.FURNITURE 认的 dict。

    ⛔ 朝向输出的是 **quat 不是 euler**（2026-08-05 修）：`<compiler angle>` 是整个编译模型
       全局的，而它来自 include 进来的机器人 XML（写着 angle="radian"），所以
       `euler="0 0 90"` 会被当成 **90 弧度**读。实测本该 180° 的椅子曾经是 −126.76°。
       四元数没有单位，这类错不会再犯。换算在 make_house.yaw_quat 里，那边有完整说明。
    """
    d = {"name": name, "room": room, "type": typ, "pos": pos, "size": size, "rgba": rgba}
    if mat:
        d["mat"] = mat
    if abs(yaw) > 1e-6:
        a = math.radians(yaw) / 2.0
        d["quat"] = (math.cos(a), 0.0, 0.0, math.sin(a))
    return d


# ---------------------------------------------------------------- 椅子
def chair(name: str, room: str, x: float, y: float, yaw: float = 0.0, *,
          seat_w: float = 0.46, seat_d: float = 0.46, seat_h: float = 0.45,
          back_h: float = 0.52, leg: float = 0.05,
          rgba=WOOD, leg_rgba=WOOD_DARK, mat: str = "") -> list[dict]:
    """一把带**四条腿**的椅子：座面 + 靠背 + 四腿 + 前后横撑。

    局部坐标约定：靠背在 −x 侧（所以 yaw=0 时人朝 +x 坐）。
    """
    out: list[dict] = []
    st = 0.06                                   # 座面板厚
    out.append(_p(f"{name}_seat", room, "box", (x, y, seat_h),
                  (seat_w, seat_d, st), rgba, mat, yaw))
    # 靠背：立在座面后缘，略微后倾靠尺寸体现
    bx, by = _rot(-seat_w / 2 + 0.04, 0.0, yaw)
    out.append(_p(f"{name}_back", room, "box", (x + bx, y + by, seat_h + back_h / 2),
                  (0.06, seat_d * 0.95, back_h), rgba, mat, yaw))
    # 靠背竖档（两根，做出"椅背"的形，不是一块板）
    for k, sy in (("a", -0.28), ("b", 0.28)):
        ox, oy = _rot(-seat_w / 2 + 0.04, sy * seat_d, yaw)
        out.append(_p(f"{name}_slat{k}", room, "box", (x + ox, y + oy, seat_h + back_h / 2),
                      (0.07, 0.05, back_h * 0.98), leg_rgba, "", yaw))
    # 四条腿
    inset = 0.055
    for k, (sx, sy) in (("fl", (+1, +1)), ("fr", (+1, -1)), ("rl", (-1, +1)), ("rr", (-1, -1))):
        ox, oy = _rot(sx * (seat_d / 2 - inset), sy * (seat_w / 2 - inset), yaw)
        out.append(_p(f"{name}_leg{k}", room, "box", (x + ox, y + oy, (seat_h - st / 2) / 2),
                      (leg, leg, seat_h - st / 2), leg_rgba, "", yaw))
    # 前后各一根横撑（腿之间的连接杆，非常显"实物感"）
    for k, sx in (("f", +1), ("r", -1)):
        ox, oy = _rot(sx * (seat_d / 2 - inset), 0.0, yaw)
        out.append(_p(f"{name}_rail{k}", room, "box", (x + ox, y + oy, seat_h * 0.34),
                      (0.04, seat_w - 2 * inset, 0.04), leg_rgba, "", yaw))
    return out


def stool(name: str, room: str, x: float, y: float, *, h: float = 0.68,
          top_d: float = 0.36, rgba=WOOD_DARK) -> list[dict]:
    """吧椅：圆坐面 + 中心柱 + 底盘 + 一圈脚踏环（中岛旁边用）。"""
    return [
        _p(f"{name}_top", room, "cylinder", (x, y, h), (top_d, top_d, 0.06), rgba),
        _p(f"{name}_post", room, "cylinder", (x, y, h / 2), (0.07, 0.07, h), METAL),
        _p(f"{name}_base", room, "cylinder", (x, y, 0.02), (top_d * 0.95, top_d * 0.95, 0.04), METAL),
        _p(f"{name}_ring", room, "cylinder", (x, y, 0.22), (top_d * 0.72, top_d * 0.72, 0.03), METAL),
    ]


# ---------------------------------------------------------------- 桌子
def table(name: str, room: str, x: float, y: float, w: float, d: float, *,
          h: float = 0.75, top_t: float = 0.06, leg: float = 0.08,
          rgba=WOOD, leg_rgba=WOOD_DARK, mat: str = "") -> list[dict]:
    """长桌：桌面 + 四周**望板**（裙边）+ 四条腿。有望板才不像"一块板架空"。"""
    out = [_p(f"{name}_top", room, "box", (x, y, h), (w, d, top_t), rgba, mat)]
    apron_h, apron_z = 0.10, h - top_t / 2 - 0.06
    out.append(_p(f"{name}_apron_n", room, "box", (x, y + d / 2 - 0.06, apron_z),
                  (w - 0.16, 0.04, apron_h), leg_rgba))
    out.append(_p(f"{name}_apron_s", room, "box", (x, y - d / 2 + 0.06, apron_z),
                  (w - 0.16, 0.04, apron_h), leg_rgba))
    out.append(_p(f"{name}_apron_e", room, "box", (x + w / 2 - 0.06, y, apron_z),
                  (0.04, d - 0.16, apron_h), leg_rgba))
    out.append(_p(f"{name}_apron_w", room, "box", (x - w / 2 + 0.06, y, apron_z),
                  (0.04, d - 0.16, apron_h), leg_rgba))
    ins = 0.10
    for k, (sx, sy) in (("a", (+1, +1)), ("b", (+1, -1)), ("c", (-1, +1)), ("d", (-1, -1))):
        out.append(_p(f"{name}_leg{k}", room, "box",
                      (x + sx * (w / 2 - ins), y + sy * (d / 2 - ins), (h - top_t / 2) / 2),
                      (leg, leg, h - top_t / 2), leg_rgba))
    return out


def round_table(name: str, room: str, x: float, y: float, *, dia: float = 1.2,
                h: float = 0.42, rgba=WOOD, mat: str = "") -> list[dict]:
    """圆茶几：台面 + 收腰立柱 + 喇叭底盘（三段式，比一根柱子精致得多）。"""
    return [
        _p(f"{name}_top", room, "cylinder", (x, y, h), (dia, dia, 0.07), rgba, mat),
        _p(f"{name}_neck", room, "cylinder", (x, y, h - 0.10), (dia * 0.55, dia * 0.55, 0.06), rgba, mat),
        _p(f"{name}_post", room, "cylinder", (x, y, h / 2 - 0.03), (dia * 0.22, dia * 0.22, h - 0.16),
           WOOD_DARK),
        _p(f"{name}_footring", room, "cylinder", (x, y, 0.05), (dia * 0.62, dia * 0.62, 0.05), WOOD_DARK),
        _p(f"{name}_footpad", room, "cylinder", (x, y, 0.015), (dia * 0.68, dia * 0.68, 0.03), WOOD_DARK),
    ]


# ---------------------------------------------------------------- 灯具
def floor_lamp(name: str, room: str, x: float, y: float, *, h: float = 1.62,
               shade_d: float = 0.42) -> list[dict]:
    """落地灯：**配重底盘** + 细杆 + 收口 + 灯罩 + 顶部收头。五个零件才像一盏灯。"""
    return [
        _p(f"{name}_base", room, "cylinder", (x, y, 0.018), (0.34, 0.34, 0.036), (0.20, 0.20, 0.22, 1)),
        _p(f"{name}_base2", room, "cylinder", (x, y, 0.055), (0.22, 0.22, 0.04), (0.26, 0.26, 0.28, 1)),
        _p(f"{name}_pole", room, "cylinder", (x, y, h / 2), (0.045, 0.045, h), METAL),
        _p(f"{name}_collar", room, "cylinder", (x, y, h - 0.30), (0.09, 0.09, 0.05), (0.30, 0.30, 0.32, 1)),
        _p(f"{name}_shade", room, "cylinder", (x, y, h - 0.06), (shade_d, shade_d, 0.30),
           (0.97, 0.93, 0.76, 1)),
        _p(f"{name}_shade_top", room, "cylinder", (x, y, h + 0.10), (shade_d * 0.72, shade_d * 0.72, 0.03),
           (0.90, 0.86, 0.70, 1)),
    ]


def table_lamp(name: str, room: str, x: float, y: float, z: float, *,
               shade_d: float = 0.30) -> list[dict]:
    """台灯：底座 + 短杆 + 灯罩（床头柜上用）。"""
    return [
        _p(f"{name}_base", room, "cylinder", (x, y, z + 0.025), (0.18, 0.18, 0.05), (0.28, 0.28, 0.30, 1)),
        _p(f"{name}_pole", room, "cylinder", (x, y, z + 0.16), (0.03, 0.03, 0.26), METAL),
        _p(f"{name}_shade", room, "cylinder", (x, y, z + 0.36), (shade_d, shade_d, 0.24),
           (0.96, 0.90, 0.62, 1)),
    ]


# ---------------------------------------------------------------- 摆件
def vase(name: str, room: str, x: float, y: float, z: float, *, h: float = 0.42,
         belly: float = 0.26, rgba=(0.55, 0.62, 0.60, 1.0), flowers: bool = True) -> list[dict]:
    """花瓶：底足→鼓腹→收颈→瓶口，四段叠出**器型**（不是一个直筒圆柱）；可插花。"""
    out = [
        _p(f"{name}_foot", room, "cylinder", (x, y, z + h * 0.06), (belly * 0.55, belly * 0.55, h * 0.12), rgba),
        _p(f"{name}_belly", room, "cylinder", (x, y, z + h * 0.34), (belly, belly, h * 0.46), rgba),
        _p(f"{name}_shoulder", room, "cylinder", (x, y, z + h * 0.64), (belly * 0.78, belly * 0.78, h * 0.16), rgba),
        _p(f"{name}_neck", room, "cylinder", (x, y, z + h * 0.84), (belly * 0.44, belly * 0.44, h * 0.24), rgba),
        _p(f"{name}_lip", room, "cylinder", (x, y, z + h * 0.98), (belly * 0.56, belly * 0.56, h * 0.05), rgba),
    ]
    if flowers:
        for k, (dx, dy, fh, col) in enumerate([
                (0.05, 0.02, 0.30, (0.86, 0.42, 0.46, 1)), (-0.04, 0.05, 0.24, (0.92, 0.78, 0.42, 1)),
                (0.01, -0.06, 0.34, (0.90, 0.90, 0.92, 1))]):
            out.append(_p(f"{name}_stem{k}", room, "cylinder", (x + dx, y + dy, z + h + fh / 2),
                          (0.018, 0.018, fh), (0.28, 0.46, 0.28, 1)))
            out.append(_p(f"{name}_bloom{k}", room, "sphere", (x + dx, y + dy, z + h + fh),
                          (0.13, 0.13, 0.13), col))
    return out


def potted_plant(name: str, room: str, x: float, y: float, *, pot_d: float = 0.46,
                 h: float = 1.05) -> list[dict]:
    """盆栽：花盆（上宽下窄两段）+ 土面 + 主干 + 三簇叶球。"""
    return [
        _p(f"{name}_pot", room, "cylinder", (x, y, 0.20), (pot_d, pot_d, 0.40), (0.52, 0.40, 0.33, 1)),
        _p(f"{name}_pot_rim", room, "cylinder", (x, y, 0.41), (pot_d * 1.08, pot_d * 1.08, 0.05),
           (0.46, 0.35, 0.29, 1)),
        _p(f"{name}_soil", room, "cylinder", (x, y, 0.43), (pot_d * 0.9, pot_d * 0.9, 0.03),
           (0.22, 0.17, 0.13, 1)),
        _p(f"{name}_trunk", room, "cylinder", (x, y, 0.62), (0.07, 0.07, 0.36), (0.34, 0.26, 0.18, 1)),
        _p(f"{name}_leaf_a", room, "sphere", (x, y, h), (0.62, 0.62, 0.62), (0.24, 0.46, 0.26, 1)),
        _p(f"{name}_leaf_b", room, "sphere", (x + 0.20, y - 0.12, h - 0.16), (0.44, 0.44, 0.44),
           (0.28, 0.52, 0.30, 1)),
        _p(f"{name}_leaf_c", room, "sphere", (x - 0.18, y + 0.14, h - 0.20), (0.40, 0.40, 0.40),
           (0.22, 0.43, 0.24, 1)),
    ]


def books_stack(name: str, room: str, x: float, y: float, z: float) -> list[dict]:
    """一摞书：三本厚薄颜色不同、略微错开（茶几/边几上的生活痕迹）。"""
    cols = [(0.62, 0.26, 0.24, 1), (0.24, 0.36, 0.55, 1), (0.86, 0.82, 0.74, 1)]
    out = []
    zz = z
    for i, c in enumerate(cols):
        t = 0.045 - i * 0.006
        out.append(_p(f"{name}_b{i}", room, "box", (x + i * 0.012, y - i * 0.010, zz + t / 2),
                      (0.30 - i * 0.02, 0.22 - i * 0.015, t), c))
        zz += t
    return out


def tray_set(name: str, room: str, x: float, y: float, z: float) -> list[dict]:
    """托盘 + 两个杯子（茶几上最常见的一组摆件）。"""
    return [
        _p(f"{name}_tray", room, "box", (x, y, z + 0.015), (0.40, 0.28, 0.03), (0.38, 0.28, 0.20, 1)),
        _p(f"{name}_cup_a", room, "cylinder", (x - 0.08, y, z + 0.075), (0.13, 0.13, 0.12),
           (0.95, 0.95, 0.94, 1)),
        _p(f"{name}_cup_b", room, "cylinder", (x + 0.08, y, z + 0.075), (0.13, 0.13, 0.12),
           (0.95, 0.95, 0.94, 1)),
    ]


def mesh_piece(name: str, room: str, x: float, y: float, *, size, mesh: str,
               yaw: float = 0.0, z: float | None = None, rgba=(0.62, 0.60, 0.58, 1.0),
               mat: str = "", offset=(0.0, 0.0, 0.0), fit: str = "contain",
               shrink: float = 1.0) -> list[dict]:
    """一件"穿了真网格外衣"的家具。

    ⭐ 返回的仍然是**一个普通的 box 零件**——它就是碰撞真相；只是多带一个 `mesh` 字段，
       生成器据此再发一张纯视觉的网格几何**套在这个盒子里**。
       所以：改尺寸只改 `size`，网格自动跟着缩；不装资产时场景照样完整（只是没外衣）。
    ⛔ `size` 一律写**全长**（和本文件其余部分同约定）。

    `shrink` = **额外收缩系数**（默认 1.0 = 不额外收）。
    ⚠️ 只在个别资产上需要：`decor/convert.py` 记的是每个部件的**包围盒中心**，而 MuJoCo
       编译时按**重心**重定位顶点，两者在非闭合网格上能差几十厘米。`decor/calibrate.py`
       已经把实测重心写回 lock 补掉了主要部分，但少数资产（软包床、抱枕这类布料件）
       残差仍会让网格探出碰撞盒。判据只有一个：`check_scene.py` 的
       **⭐⭐ 装饰网格没改变任何射线读数** 那条必须绿。
    ⛔ 别改成"放大碰撞盒"——`_fit_scale` 会把网格按比例一起撑大，超出量原封不动。
    """
    zc = size[2] / 2.0 if z is None else z
    d = _p(name, room, "box", (x, y, zc), size, rgba, mat, yaw)
    d["mesh"] = {"id": mesh, "yaw": yaw, "fit": fit, "offset": tuple(offset),
                 "shrink": float(shrink)}
    return [d]
