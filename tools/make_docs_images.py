#!/usr/bin/env python3
"""生成 README 用的场景写真 —— 一条命令全部重出。

为什么要有这个脚本：README 的配图第一版是手工一张张摆机位截的，场景一改（比如中厨重排、
地板换石材）就全过时，而且没人记得当初相机在哪。机位写进代码 = 图和场景永远对得上。

用法：
    python tools/make_docs_images.py            # 全出，写到 docs/images/
    python tools/make_docs_images.py A1 E1      # 只出指定的几张

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

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
#    ⚠️ 这个 sys.path 是必需的：本文件原来一行都没有，能 import 到 scenes 纯属
#    "脚本住仓根、sys.path[0] 恰好是仓根"的巧合。搬进 tools/ 之后就得显式插。
sys.path.insert(0, ROOT)

from scenes import manifest as SCENES  # noqa: E402

# ⚠️ 2026-08-02 资产库改多场景：layout 不再躺在仓根，产物也改名 <场景>-<机器人>.xml。
#    这个文件 2026-07-26 就因为目录一动没跟着改而把配图写到仓库外面（脚本照常打印
#    「完成」）。**目录一动，这里所有路径重新数一遍。**
SCENE_KEY = os.environ.get("ALICE_SCENE", SCENES.DEFAULT_SCENE)
L = SCENES.load_layout(SCENE_KEY)

# 场景按 (场景, 机器人) 分文件。出配图用哪台机器人都行——房子是同一间，
# 差别只在里面站着谁；这些图要么关掉天花板俯视、要么是机器人视角（各用各的相机）。
SCENE_FOR = lambda robot: os.path.join(ROOT, SCENES.scene_filename(SCENE_KEY, robot))
SCENE = SCENE_FOR("go2")

# ⚠️ 这两个高度必须和 robots/manifest.py 里那两台机器人**实际**的相机高度对得上，
#    不然配图说"人形看到的"其实是个不存在的机位（v0.3 之前这里写 1.55 m，
#    那是还没有真人形时随手定的；真 G1 装上相机后实测眼高 1.25 m，已改）。
# 镜头清单跟着场景走（scenes/<key>/shots.py）——站在哪、看哪儿只对那一栋楼成立。
SHOTS = SCENES.load_sibling(SCENE_KEY, "shots")

# 产物写到**本仓**的 docs/images/<场景>/。
# ⚠️ 2026-07-26 场景目录扁平化时这里没跟着改（还是 os.path.dirname(HERE)，那是场景
#    还在 domus01/ 子目录时的写法），配图被写到了仓库外面——脚本照常打印"完成"，
#    README 的图却一张没更新。**目录一动，所有 ".." 重新数一遍。**
OUT_DIR = os.path.join(ROOT, "docs", "images", SCENE_KEY)


def _model_with_camera(pos, yaw_deg: float):
    """把一个 <camera> 插进场景再加载。比换算 MuJoCo 自由相机的 azimuth/elevation 可靠——
    那套是"绕着目标转"的语义，一不小心就把相机放进家具肚子里（踩过）。"""
    th = np.radians(yaw_deg)
    right = (np.sin(th), -np.cos(th), 0.0)   # xyaxes = (右方向, 上方向)；看向 -z_cam = 右×上
    cam = (f'<camera name="probe" pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}" '
           f'xyaxes="{right[0]:.6f} {right[1]:.6f} 0 0 0 1"/>')
    src = open(SCENE, encoding="utf-8").read().replace("</worldbody>", f"  {cam}\n</worldbody>")
    # ⛔ 必须与场景 xml **同目录**（现在是 build/）：贴图与网格的相对路径全按主模型
    #    所在目录解析，探针放错地方 MuJoCo 会直接报"找不到贴图"。
    #    ⭐ 从 SCENE 自己派生，⛔ 别写死 "build"、也别写仓根 —— 产物再挪它自动跟着走。
    tmp = os.path.join(os.path.dirname(SCENE), "_docs_probe.xml")
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


def _model_looking_at(pos, target):
    """机位固定、镜头对准某一点。外景用。

    同样走"把 <camera> 插进场景"这条路而不是自由相机的 azimuth/elevation：
    后者是"绕着目标转"的语义，算错一次相机就跑进墙里或家具肚子里（踩过）。
    """
    import numpy as _np

    fwd = _np.array(target, dtype=float) - _np.array(pos, dtype=float)
    fwd /= _np.linalg.norm(fwd)
    right = _np.cross(fwd, [0.0, 0.0, 1.0]); right /= _np.linalg.norm(right)
    up = _np.cross(right, fwd)
    cam = (f'<camera name="probe" pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}" '
           f'xyaxes="{right[0]:.6f} {right[1]:.6f} {right[2]:.6f} '
           f'{up[0]:.6f} {up[1]:.6f} {up[2]:.6f}"/>')
    src = open(SCENE, encoding="utf-8").read().replace("</worldbody>", f"  {cam}\n</worldbody>")
    tmp = os.path.join(os.path.dirname(SCENE), "_docs_probe.xml")
    open(tmp, "w", encoding="utf-8").write(src)
    try:
        return mujoco.MjModel.from_xml_path(tmp)
    finally:
        os.remove(tmp)


def render_exterior(pos, target, w=1280, h=900):
    m = _model_looking_at(pos, target)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=h, width=w)
    r.update_scene(d, camera="probe")
    return r.render()


def render_eye(pos_xyz, yaw_deg, w=960, h=720):
    m = _model_with_camera(pos_xyz, yaw_deg)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=h, width=w)
    r.update_scene(d, camera="probe")
    return r.render()


def main() -> None:
    only = set(sys.argv[1:])
    os.makedirs(OUT_DIR, exist_ok=True)
    print("生成 README 配图 →", OUT_DIR)
    for tag, fn, center, dist, note in SHOTS.TOPDOWN:
        if only and tag not in only:
            continue
        Image.fromarray(render_topdown(center, dist)).save(os.path.join(OUT_DIR, fn))
        print(f"  {tag}  {fn:<30} 俯视 {note}")
    for tag, fn, pos, yaw, note in SHOTS.EYE:
        if only and tag not in only:
            continue
        Image.fromarray(render_eye(pos, yaw)).save(os.path.join(OUT_DIR, fn))
        print(f"  {tag}  {fn:<30} 站 z={pos[2]:.2f}m 朝{yaw}° {note}")
    for tag, fn, pos, target, note in getattr(SHOTS, "EXTERIOR", []):
        if only and tag not in only:
            continue
        Image.fromarray(render_exterior(pos, target)).save(os.path.join(OUT_DIR, fn))
        print(f"  {tag}  {fn:<30} 外景 {note}")
    print(f"完成（场景 {SCENE_KEY}）。改了场景就重跑：ALICE_SCENE=<场景> python tools/make_docs_images.py")


if __name__ == "__main__":
    main()
