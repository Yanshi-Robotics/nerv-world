"""Qualify generated SO-101 scenes without a controller, model API or hardware.

Run from any directory. Rendering uses the caller's MuJoCo GL environment. The
reach probe checks endpoint position only, never a collision-free motion or grasp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes.so101_workbench.evaluate import evaluate  # noqa: E402
from scenes.so101_workbench.generate import CONFIG, CATALOG, read_configuration  # noqa: E402


def start_pose(model, data, metadata):
    """The same named start pose exported in the generated world descriptor."""
    for name, value in metadata["initial_joints"].items():
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[model.jnt_qposadr[jid]] = value
        aids = np.flatnonzero(model.actuator_trnid[:, 0] == jid)
        data.ctrl[aids] = value
    mujoco.mj_forward(model, data)


def position_reach(model, metadata, target, cfg):
    """Damped least-squares endpoint probe, with limits and deterministic restarts."""
    site = model.site("gripperframe").id
    names = [n for n in metadata["initial_joints"] if n != "gripper"]
    joints = [model.joint(n).id for n in names]
    qadr, dadr = model.jnt_qposadr[joints], model.jnt_dofadr[joints]
    limits = model.jnt_range[joints]
    data = mujoco.MjData(model)
    start_pose(model, data, metadata)
    rng = np.random.default_rng(cfg["ik_seed"])
    best = float("inf")
    for trial in range(cfg["ik_restarts"]):
        if trial:
            data.qpos[qadr] = rng.uniform(limits[:, 0], limits[:, 1])
        for _ in range(cfg["ik_iterations"]):
            mujoco.mj_kinematics(model, data)
            mujoco.mj_comPos(model, data)
            error = np.asarray(target) - data.site_xpos[site]
            best = min(best, float(np.linalg.norm(error)))
            if best <= cfg["reach_tolerance_m"]:
                return best
            jac = np.zeros((3, model.nv))
            mujoco.mj_jacSite(model, data, jac, None, site)
            j = jac[:, dadr]
            step = j.T @ np.linalg.solve(j @ j.T + cfg["ik_damping"] * np.eye(3), error)
            step = np.clip(step, -cfg["ik_max_step_rad"], cfg["ik_max_step_rad"])
            data.qpos[qadr] = np.clip(data.qpos[qadr] + step, limits[:, 0], limits[:, 1])
    return best


def qualify(preset, cfg, render_dir=None):
    arena = ROOT / "build" / f"so101-{preset}.xml"
    meta = json.loads(arena.with_suffix(".json").read_text())
    for key, path in [("source_config_sha256", CONFIG), ("source_catalog_sha256", CATALOG)]:
        assert meta[key] == hashlib.sha256(path.read_bytes()).hexdigest(), f"stale build: {arena}"
    model = mujoco.MjModel.from_xml_path(str(arena))
    data = mujoco.MjData(model)
    start_pose(model, data, meta)
    for _ in range(round(cfg["validation"]["settle_s"] / model.opt.timestep)):
        mujoco.mj_step(model, data)
    warnings = sum(w.number for w in data.warning)
    assert not warnings and np.isfinite(data.qpos).all(), f"unstable physics: {preset}"
    score = evaluate(model, data, meta)
    assert not score["success"], f"initial scene is already completed: {preset}"
    targets = [
        (o["id"], [*o["xy"], meta["surface_z"] + o["size_m"][2] / 2]) for o in meta["objects"]
    ]
    clearance = cfg["validation"]["approach_clearance_m"]
    targets += [(b["id"], [*b["xy"], b["rim_z"] + clearance]) for b in meta["baskets"]]
    if "hanoi" in meta:
        targets += [
            (
                f"peg_{i}_clearance",
                [*xy, meta["hanoi"]["base_z"] + meta["hanoi"]["peg_height_m"] + clearance],
            )
            for i, xy in enumerate(meta["hanoi"]["peg_xy"])
        ]
    reach = [
        {"target": name, "error_m": position_reach(model, meta, xyz, cfg["validation"])}
        for name, xyz in targets
    ]
    assert all(r["error_m"] <= cfg["validation"]["reach_tolerance_m"] for r in reach), reach
    if render_dir:
        from PIL import Image

        render_dir.mkdir(parents=True, exist_ok=True)
        with mujoco.Renderer(
            model, cfg["runtime"]["render_height"], cfg["runtime"]["render_width"]
        ) as r:
            for camera in ("overview", "top", "wrist"):
                r.update_scene(data, camera=camera)
                Image.fromarray(r.render()).save(render_dir / f"{preset}-{camera}.png")
    return {
        "preset": preset,
        "physics_warning_count": int(warnings),
        "sim_time_s": data.time,
        "actuators": model.nu,
        "flexes": model.nflex,
        "score": score,
        "position_reach_only": reach,
        "motion_and_grasp_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    cfg, _ = read_configuration()
    lock = json.loads((ROOT / "robots/so101/UPSTREAM.json").read_text())
    for item in lock["files"]:
        assert (
            hashlib.sha256((ROOT / "robots/so101" / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    report = {
        "mujoco_version": mujoco.__version__,
        "robot_source_commit": lock["commit"],
        "scenes": [qualify(preset, cfg, args.render_dir) for preset in cfg["presets"]],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
