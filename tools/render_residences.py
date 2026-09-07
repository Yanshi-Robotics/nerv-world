#!/usr/bin/env python3
"""用原生 MuJoCo 和场景固定机位渲染住宅；同一模型复用 Renderer。"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", choices=["house", "apt"], required=True)
    parser.add_argument("--shots", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument(
        "--contract", type=Path, help="G1 policy contract used to settle seated poses"
    )
    args = parser.parse_args()
    import mujoco
    import numpy as np
    from PIL import Image
    from scenes import manifest

    layout = manifest.load_layout(args.scene)
    shots = manifest.load_sibling(args.scene, "shots")
    out = args.output or ROOT / "docs" / "images" / args.scene
    out.mkdir(parents=True, exist_ok=True)
    path = ROOT / manifest.scene_filename(args.scene, "g1")
    if args.baseline:
        source = subprocess.check_output(
            ["git", "show", f"{args.baseline}:{path.relative_to(ROOT)}"], cwd=ROOT, text=True
        )
        os.chdir(path.parent)
        model = mujoco.MjModel.from_xml_string(source)
    else:
        model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    data.qpos[:3] = [*layout.ROBOT_HOME_XY, 0.80]
    mujoco.mj_forward(model, data)
    opt = mujoco.MjvOption()
    opt.geomgroup[2] = 0
    opt.geomgroup[3] = 0
    opt.geomgroup[4] = 0
    renderer = mujoco.Renderer(model, height=args.height, width=args.width)
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "film")

    def aim(pos, target):
        forward = np.array(target, dtype=float) - pos
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 0, 1])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        matrix = np.column_stack([right, up, -forward]).ravel()
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, matrix)
        model.cam_pos[camera] = pos
        model.cam_quat[camera] = quat
        model.cam_fovy[camera] = 58
        mujoco.mj_forward(model, data)

    entries = []
    for tag, name, pos, yaw, note in getattr(shots, "EYE", []):
        angle = math.radians(yaw)
        target = (pos[0] + math.cos(angle), pos[1] + math.sin(angle), pos[2])
        entries.append((tag, name, pos, target, note))
    entries += getattr(shots, "EXTERIOR", [])
    for tag, name, pos, target, note in entries:
        if args.shots and tag not in args.shots:
            continue
        aim(pos, target)
        renderer.update_scene(data, camera="film", scene_option=opt)
        Image.fromarray(renderer.render()).save(out / name)
        print(f"{args.scene}/{tag}: {out / name}", flush=True)
    for tag, name, center, distance, note in getattr(shots, "TOPDOWN", []):
        if args.shots and tag not in args.shots:
            continue
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [*center, 0]
        cam.distance = distance
        cam.azimuth = 90
        cam.elevation = -89.9
        opt.geomgroup[layout.CEILING_GROUP] = 0
        renderer.update_scene(data, camera=cam, scene_option=opt)
        Image.fromarray(renderer.render()).save(out / name)
        opt.geomgroup[layout.CEILING_GROUP] = 1
    pose_results = {}
    for tag, name, pose_key, robot, pos, target, note in getattr(shots, "POSED", []):
        if args.shots and tag not in args.shots:
            continue
        if not args.contract:
            raise ValueError("Seated pictures require --contract from the released G1 policy")
        from scenes import apply_pose

        mujoco.mj_resetData(model, data)
        assert apply_pose.apply(model, data, layout.SIT_POSES[pose_key]) >= 6
        result = apply_pose.settle(
            model, data, apply_pose.load_gains(str(args.contract)), seconds=3.0
        )
        assert abs(result["rise"]) <= 0.08 and result["tilt_deg"] <= 30, f"Unstable seat: {result}"
        pose_results[tag] = result
        opt.geomgroup[2] = 1
        aim(pos, target)
        renderer.update_scene(data, camera="film", scene_option=opt)
        Image.fromarray(renderer.render()).save(out / name)
        print(f"{args.scene}/{tag}: {result}", flush=True)
    if pose_results:
        (out / "seated-poses.json").write_text(json.dumps(pose_results, indent=2))
    renderer.close()
    if args.benchmark:
        renderer = mujoco.Renderer(model, height=480, width=640)
        cameras = [
            model.camera(i).name for i in range(model.ncam) if "head" in model.camera(i).name
        ]
        sensor = cameras[0] if cameras else "film"
        times = []
        for i in range(90):
            start = time.perf_counter()
            for name in (sensor, "film"):
                renderer.update_scene(data, camera=name, scene_option=opt)
                renderer.render()
            times.append(time.perf_counter() - start)
        renderer.close()
        start = time.perf_counter()
        for _ in range(1000):
            mujoco.mj_step(model, data)
        elapsed = time.perf_counter() - start
        report = dict(
            scene=args.scene,
            mujoco=mujoco.__version__,
            ngeom=model.ngeom,
            nmesh=model.nmesh,
            dual_frame_median_ms=float(np.median(times[10:]) * 1000),
            dual_frame_p95_ms=float(np.percentile(times[10:], 95) * 1000),
            physics_capacity_realtime_factor=1000 * model.opt.timestep / elapsed,
            note="Unpaced renderer/physics capacity; NERV streaming acceptance is separate.",
        )
        (out / "render-capacity.json").write_text(json.dumps(report, indent=2))
        print(report, flush=True)


if __name__ == "__main__":
    main()
