#!/usr/bin/env python3
"""生成 README 用的场景写真 —— 一条命令全部重出。

为什么要有这个脚本：README 的配图第一版是手工一张张摆机位截的，场景一改（比如中厨重排、
地板换石材）就全过时，而且没人记得当初相机在哪。机位写进代码 = 图和场景永远对得上。

用法：
    python make_docs_images.py            # 全出，写到 ../docs/images/
    python make_docs_images.py A1 E1      # 只出指定的几张

两类镜头：
  俯视（关掉天花板那一组 geom）—— 看清户型与家具摆位
  站位（往场景里插一个 <camera> 再按名字渲）—— 看"站在这儿的机器人看得见什么"
"""
from __future__ import annotations

import os
import sys

import mujoco
import numpy as np
from PIL import Image

import layout as L

HERE = os.path.dirname(os.path.abspath(__file__))
# 场景按机器人分了两份（house-go2.xml / house-g1.xml）。出配图用哪份都行——房子是同一间，
# 差别只在里面站着谁；这些图要么关掉天花板俯视、要么是机器人视角（各用各的相机）。
SCENE_FOR = lambda robot: os.path.join(HERE, f"house-{robot}.xml")
SCENE = SCENE_FOR("go2")
OUT_DIR = os.path.join(os.path.dirname(HERE), "docs", "images")

DOG_EYE = 0.50      # 四足机器狗头部相机的高度(m)——"狗视角"那几张用它
HUMAN_EYE = 1.55    # 人/人形机器人的视线高度(m)——对照用

# ── 俯视镜头：(编号, 文件名, 看向哪, 视野距离m, 说明) ──
TOPDOWN = [
    ("A1", "A1-户型俯视图.png", (0.0, 0.0), 30, "整套户型，关掉天花板"),
    ("E1", "E1-中厨.png", (1.75, -4.0), 12, "中厨：沿墙布置，中间留通行区"),
    ("B1", "B1-客餐厅打通.png", (2.0, 6.0), 16, "客厅与餐厅之间整面墙拆除"),
    ("C1", "C1-主卧.png", (-3.0, 6.5), 10, "主卧"),
    ("C3", "C3-主卫+浴缸.png", (-7.5, 7.2), 9, "主卫：独立浴缸，大理石地"),
    ("D1", "D1-小孩房.png", (-7.5, -4.5), 14, "小孩房"),
    ("B2", "B2-客厅.png", (6.7, 6.0), 12, "客厅：转角沙发正对电视墙"),
]

# ── 站位镜头：(编号, 文件名, 站在哪, 眼高, 朝向角度, 说明) ──
#    朝向：0=朝 +x(东)，90=朝 +y(北)，180=朝西，270=朝南
EYE = [
    ("G1", "G1-狗视角-出生在玄关.png", (7.29, -0.60), DOG_EYE, 181, "出生点，玄关"),
    ("G2", "G2-狗视角-看电视.png", (6.6, 5.0), DOG_EYE, 170, "客厅，正对电视墙"),
    ("G3", "G3-狗视角-厨房门口.png", (4.5, -1.6), DOG_EYE, 206, "站在门口望进中厨"),
    ("G4", "G4-狗视角-窗外城市.png", (7.0, 8.6), DOG_EYE, 90, "客厅落地窗，窗外是城市"),
    ("G5", "G5-狗视角-过道.png", (-3.0, -1.5), DOG_EYE, 90, "过道，两侧开着各房间的门"),
    ("H1", "H1-人形视角-中厨.png", (3.0, -5.2), HUMAN_EYE, 190, "同一间中厨，人形视线高度"),
]


def _model_with_camera(pos, yaw_deg: float):
    """把一个 <camera> 插进场景再加载。比换算 MuJoCo 自由相机的 azimuth/elevation 可靠——
    那套是"绕着目标转"的语义，一不小心就把相机放进家具肚子里（踩过）。"""
    th = np.radians(yaw_deg)
    right = (np.sin(th), -np.cos(th), 0.0)   # xyaxes = (右方向, 上方向)；看向 -z_cam = 右×上
    cam = (f'<camera name="probe" pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}" '
           f'xyaxes="{right[0]:.6f} {right[1]:.6f} 0 0 0 1"/>')
    src = open(SCENE, encoding="utf-8").read().replace("</worldbody>", f"  {cam}\n</worldbody>")
    tmp = os.path.join(HERE, "_docs_probe.xml")   # 必须与 house-*.xml 同目录，贴图相对路径才对
    open(tmp, "w", encoding="utf-8").write(src)
    try:
        return mujoco.MjModel.from_xml_path(tmp)
    finally:
        os.remove(tmp)


def render_topdown(center, dist, w=1000, h=1000):
    m = mujoco.MjModel.from_xml_path(SCENE)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    opt = mujoco.MjvOption()
    mujoco.mjv_defaultOption(opt)
    opt.geomgroup[L.CEILING_GROUP] = 0            # 关掉天花板才看得见屋里
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(cam)
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [center[0], center[1], 0.0]
    cam.distance, cam.azimuth, cam.elevation = dist, 90, -89.9   # azimuth 90 = 北在上
    r = mujoco.Renderer(m, height=h, width=w)
    r.update_scene(d, camera=cam, scene_option=opt)
    return r.render()


def render_eye(pos_xy, eye_h, yaw_deg, w=960, h=720):
    m = _model_with_camera((pos_xy[0], pos_xy[1], eye_h), yaw_deg)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=h, width=w)
    r.update_scene(d, camera="probe")
    return r.render()


def main() -> None:
    only = set(sys.argv[1:])
    os.makedirs(OUT_DIR, exist_ok=True)
    print("生成 README 配图 →", OUT_DIR)
    for tag, fn, center, dist, note in TOPDOWN:
        if only and tag not in only:
            continue
        Image.fromarray(render_topdown(center, dist)).save(os.path.join(OUT_DIR, fn))
        print(f"  {tag}  {fn:<28} 俯视 {note}")
    for tag, fn, xy, eye, yaw, note in EYE:
        if only and tag not in only:
            continue
        Image.fromarray(render_eye(xy, eye, yaw)).save(os.path.join(OUT_DIR, fn))
        print(f"  {tag}  {fn:<28} 眼高{eye:.2f}m 朝{yaw}° {note}")
    print("完成。改了场景就重跑这个脚本，README 的图不会再过时。")


if __name__ == "__main__":
    main()
