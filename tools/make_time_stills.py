#!/usr/bin/env python3
"""四时段光照的验收工具：同机位 × 四段对比图 + 三道量化门禁。

    python tools/make_time_stills.py [--scene apt] [--out docs/images/apt/time-presets]

产出 `T0-四时段对比.png`（2×2，同一机位）+ 每段一张全尺寸静帧，并打印门禁：
  ① 整帧平均亮度单调：day > morning > dusk > night（时段没生效一眼露馅）
  ② night 下每个房间的**地面**亮度 ≥ 8/255（headlight 压过头 = 无窗区死黑，
     H.264 编码后糊成色块）——用 segmentation 渲染按地板 geom id 取掩码，
     ⛔ 不拿矩形猜像素（会把白色洁具和机器人算进去，读数饱和）
  ③ 换过天空的段：换装前后整帧 mean 必须变（忘了 mjr_uploadTexture = 静默失效）

机位选「贴玻璃看上西区」：画面同时含天空/对岸楼/公园三种面，四段各自都会明显不同。
⛔ 机位坐标从 layout 算（shots.py 立的规矩）。机器人摆到 ROBOT_HOME（洗衣房停机位），
   免得它站在画廊正中把读数带偏（实测踩过）。
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _look_at_quat(eye, target) -> np.ndarray:
    """(w,x,y,z)，约定与消费方 rig 相同：cam 看 −z_cam、forward = up × right。
    ⚠️ 已知这是第二份实现（消费方 rig 里有一份 quat 版）——两边都被彩色方位探针
    校过同一约定；若将来第三个消费方出现，再提公共件。"""
    fwd = np.asarray(target, float) - np.asarray(eye, float)
    fwd = fwd / np.linalg.norm(fwd)
    up_w = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up_w)
    right = right / np.linalg.norm(right)
    up = np.cross(right, fwd)
    R = np.column_stack([right, up, -fwd])
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.ascontiguousarray(R.ravel()))
    return q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="apt")
    ap.add_argument("--robot", default="g1")
    ap.add_argument("--out", help="Output directory; defaults to docs/images/<scene>/time-presets")
    a = ap.parse_args()

    manifest = _load("ah_manifest_tp", "scenes/manifest.py")
    preset = _load("ah_preset_tp", "scenes/apply_time_preset.py")
    L = manifest.load_layout(a.scene)
    phases = getattr(L, "PHASES", ("day",))
    out_dir = os.path.join(ROOT, a.out or os.path.join("docs", "images", a.scene, "time-presets"))
    os.makedirs(out_dir, exist_ok=True)

    xml = os.path.join(ROOT, manifest.scene_filename(a.scene, a.robot))
    Wpx, Hpx = 1280, 720

    # 机位：贴大客厅中央开间玻璃，看上西区（同帧含天空/对岸楼/公园）
    if hasattr(L,"TIME_VIEW"):
        eye,target=L.TIME_VIEW["eye"],L.TIME_VIEW["target"]
    else:
        eye = (L.ENFILADE_X, L.Y3 - 0.45, 1.85)
        target = (-L.PARK_W / 2.0 - 300.0, L.PARK_NEAR_Y + 900.0, -L.ELEV * 0.45)

    frames: dict[str, np.ndarray] = {}
    means: dict[str, float] = {}
    all_warns: list[str] = []
    for phase in phases:
        m = mujoco.MjModel.from_xml_path(xml)      # ⛔ 每段重新加载，不指望复原
        d = mujoco.MjData(m)
        # 机器人摆去停机位（产物里它站在世界原点）
        d.qpos[0:2] = L.ROBOT_HOME_XY
        yaw = L.ROBOT_HOME_YAW
        d.qpos[3:7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        mujoco.mj_forward(m, d)
        r = mujoco.Renderer(m, Hpx, Wpx)
        cid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "film")
        m.cam_pos[cid] = eye
        m.cam_quat[cid] = _look_at_quat(eye, target)
        m.cam_fovy[cid] = 44.0
        mujoco.mj_camlight(m, d)
        # 门禁③：换天空的段，换装前后 mean 必须变
        r.update_scene(d, camera=cid)
        before = r.render().astype(float).mean()
        assert mujoco.mjr_getError() == 0, "OpenGL error while rendering the daytime model"
        day_facades = {}
        for texture in ("a2_city_tex_glass", "a2_city_tex_stone"):
            tid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, texture)
            if tid >= 0:
                adr = int(m.tex_adr[tid])
                size = int(m.tex_height[tid]*m.tex_width[tid]*m.tex_nchannel[tid])
                day_facades[tid] = (adr, m.tex_data[adr:adr+size].copy())
        warns = preset.apply(m, r, phase, scene_key=a.scene)
        mujoco.mj_camlight(m, d)
        all_warns += warns
        r.update_scene(d, camera=cid)
        rgb = r.render()
        assert mujoco.mjr_getError() == 0, f"OpenGL error while rendering {phase}"
        frames[phase] = rgb
        means[phase] = float(rgb.astype(float).mean())
        spec = getattr(L, "LIGHTS_BY_TIME", {}).get(phase) or {}
        if spec.get("sky") and abs(means[phase] - before) < 1e-9:
            print(f"❌ 门禁③：{phase} 声明了换天空但画面 mean 一字没变（上传静默失效？）")
            sys.exit(1)
        Image.fromarray(rgb).save(os.path.join(out_dir, f"T-{phase}.png"))
        if phase == "night" and day_facades:
            # An ablation verifies real night pixels, not only changed model fields:
            # keep night lighting but restore day facade textures and compare frames.
            for tid, (adr, pixels) in day_facades.items():
                m.tex_data[adr:adr+pixels.size] = pixels
                mujoco.mjr_uploadTexture(m, r._mjr_context, tid)
            r.update_scene(d, camera=cid)
            no_window_lights = r.render()
            difference = float(np.abs(rgb.astype(float)-no_window_lights.astype(float)).mean())
            min_difference = 1.0  # RGB levels over the whole fixed frame; detects a missing upload.
            assert difference > min_difference, f"Night facade textures have no visible effect: {difference}"
            print(f"Night facade ablation: mean absolute pixel change={difference:.3f}/255; OpenGL errors=0")
        r.close()

    # 拼 2×2 对比图
    tile_w, tile_h = Wpx // 2, Hpx // 2
    canvas = Image.new("RGB", (tile_w * 2, tile_h * 2 + 22), (12, 12, 12))
    dr = ImageDraw.Draw(canvas)
    order = [p for p in ("morning", "day", "dusk", "night") if p in frames]
    for i, p in enumerate(order):
        im = Image.fromarray(frames[p]).resize((tile_w, tile_h))
        rr, cc = divmod(i, 2)
        canvas.paste(im, (cc * tile_w, rr * tile_h))
        dr.text((cc * tile_w + 8, rr * tile_h + 6), f"{p}  mean={means[p]:.1f}",
                fill=(255, 255, 90))
    t0 = os.path.join(out_dir, "T0-四时段对比.png")
    canvas.save(t0)
    print(f"对比图 → {t0}")
    for w in sorted(set(all_warns)):
        print(w)

    # 门禁①：单调
    ladder = [means.get(p) for p in ("day", "morning", "dusk", "night") if p in means]
    print("亮度阶梯（day→morning→dusk→night）：",
          " > ".join(f"{v:.1f}" for v in ladder))
    if any(ladder[i] <= ladder[i + 1] for i in range(len(ladder) - 1)):
        print("❌ 门禁①：整帧亮度不单调——某段的光照没起作用或反了")
        sys.exit(1)

    # 门禁②：night 每间屋的地面亮度（segmentation 掩码）
    if "night" in phases:
        if getattr(L, 'N_FLOORS', 1)>1:
            # A roof camera cannot see the duplex's lower floor. Sample inside
            # every room instead, below that room's ceiling, using floor IDs.
            check_room_nights(xml, L, preset, a.scene)
            print(f'✅ 三道门禁全过（逐房间检查 {L.N_FLOORS} 层）')
            return
        m = mujoco.MjModel.from_xml_path(xml)
        d = mujoco.MjData(m)
        d.qpos[0:2] = L.ROBOT_HOME_XY
        mujoco.mj_forward(m, d)
        r = mujoco.Renderer(m, 720, 960)
        preset.apply(m, r, "night", scene_key=a.scene)
        cid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "film")
        cx = (min(rm["rect"][0] for rm in L.ROOMS.values())
              + max(rm["rect"][2] for rm in L.ROOMS.values())) / 2.0
        cy = (min(rm["rect"][1] for rm in L.ROOMS.values())
              + max(rm["rect"][3] for rm in L.ROOMS.values())) / 2.0
        m.cam_pos[cid] = (cx, cy, 30.0)
        m.cam_quat[cid] = _look_at_quat((cx, cy + 1e-4, 30.0), (cx, cy, 0.0))
        m.cam_fovy[cid] = 45.0
        mujoco.mj_camlight(m, d)
        opt = mujoco.MjvOption()
        mujoco.mjv_defaultOption(opt)
        opt.geomgroup[L.CEILING_GROUP] = 0
        r.update_scene(d, camera=cid, scene_option=opt)
        rgb = r.render().astype(float)
        r.enable_segmentation_rendering()
        r.update_scene(d, camera=cid, scene_option=opt)
        seg = r.render()[..., 0]
        r.disable_segmentation_rendering()
        bad = []
        for room in L.ROOMS:
            gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"{room}_floor")
            if gid < 0:
                continue
            mask = seg == gid
            if mask.sum() < 50:
                continue                    # 被家具盖满/视角照不到，不算数
            v = float(rgb[mask].mean())
            status = "✅" if v >= 8.0 else "❌"
            print(f"  {status} night 地面亮度 {room:14s} {v:6.1f} /255")
            if v < 8.0:
                bad.append(room)
        if bad:
            print(f"❌ 门禁②：{bad} 的地面在夜里死黑（<8/255），headlight 或 practical 要加")
            sys.exit(1)
        r.close()

    print("✅ 三道门禁全过")


def check_room_nights(xml, layout, preset, scene_key):
    m = mujoco.MjModel.from_xml_path(xml)
    d = mujoco.MjData(m)
    d.qpos[:2] = layout.ROBOT_HOME_XY
    mujoco.mj_forward(m, d)
    minimum_brightness = 8.0  # Retain the original floor readability threshold.
    minimum_pixels = 50
    camera_height = 2.6  # Below the duplex ceiling, above ordinary furniture.
    opt = mujoco.MjvOption()
    opt.geomgroup[2:5] = 0
    with mujoco.Renderer(m, 480, 640) as renderer:
        preset.apply(m, renderer, 'night', scene_key=scene_key)
        cam = m.camera('film').id
        for name, room in layout.ROOMS.items():
            surfaces = {a['name']+'_finish' for a in getattr(layout,'ARCHITECTURE', [])
                        if ('_'+name+'_finish') in a['name']}
            gids = [g for g in range(m.ngeom) if (m.geom(g).name or '').startswith(name+'_floor')
                    or m.geom(g).name in surfaces]
            assert gids, f'No floor geometry for {name}'
            x0,y0,x1,y1 = room['rect']
            z = layout.FLOOR_Z(room.get('floor', 0))
            samples = []
            for u,v in ((.5,.5),(.2,.2),(.8,.8),(.2,.8),(.8,.2)):
                eye = (x0+(x1-x0)*u, y0+(y1-y0)*v, z+camera_height)
                m.cam_pos[cam] = eye
                m.cam_quat[cam] = _look_at_quat(eye,(eye[0],eye[1]+.001,z))
                m.cam_fovy[cam] = 65
                mujoco.mj_camlight(m,d)
                renderer.update_scene(d,camera=cam,scene_option=opt)
                rgb = renderer.render().astype(float)
                renderer.enable_segmentation_rendering()
                renderer.update_scene(d,camera=cam,scene_option=opt)
                seg = renderer.render()
                renderer.disable_segmentation_rendering()
                mask = np.isin(seg[...,0],gids) & (seg[...,1] == int(mujoco.mjtObj.mjOBJ_GEOM))
                if mask.sum() >= minimum_pixels:
                    samples.append(float(rgb[mask].mean()))
            assert samples, f'No visible floor pixels in room {name}; night coverage incomplete'
            value = min(samples)
            print(f'  night {name}: {value:.1f}/255 ({len(samples)} views)', flush=True)
            assert value >= minimum_brightness, f'Night floor too dark: {name} = {value}'


if __name__ == "__main__":
    main()
