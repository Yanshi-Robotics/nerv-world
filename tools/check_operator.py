#!/usr/bin/env python3
"""CPU acceptance of runtime metadata, task contacts, reset and reversible lighting."""

from pathlib import Path
import argparse
import json
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest
from scenes.operator import SceneRuntime
from scenes.interaction import InspectionPhysics, ACTION_TIMEOUT
from scenes.tasks import SETTLE_SECONDS
from tools.walkthrough import park_robot


def setup(scene="apt", robot="g1"):
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename(scene, robot)))
    d = mujoco.MjData(m)
    park_robot(m, d, manifest.load_layout(scene), robot)
    mujoco.mj_forward(m, d)
    runtime = SceneRuntime(m, d, scene)
    return (
        m,
        d,
        runtime,
        InspectionPhysics(
            m, d, runtime.interaction, observer=lambda _m, _d: runtime.observe_step()
        ),
    )


def advance(physics, runtime, seconds):
    # Predicates run after real physics with contacts populated, at the same 20 Hz as NERV.
    period = 0.05
    for _ in range(round(seconds / period)):
        physics.advance(period)
        runtime.update_task()


def catalogue_and_time(scene, robot):
    m, d, r, p = setup(scene, robot)
    catalogue = r.catalogue()
    ids = [f["id"] for f in catalogue["facilities"]]
    assert len(ids) == len(set(ids))
    assert len(catalogue["floors"]) == manifest.get(scene)["floors"]
    for f in catalogue["facilities"]:
        assert np.isfinite(f["anchor"]).all(), f
        if f.get("joint"):
            assert m.joint(f["joint"]).id in r.interaction.joints.values()
        if f.get("body"):
            assert m.body(f["body"]).id > 0
        if f["kind"] in ("static", "pose", "boundary"):
            assert not f["operations"]
    fields = ("qpos", "qvel", "act", "ctrl", "qfrc_applied", "xfrc_applied")
    data = {k: getattr(d, k).copy() for k in fields}
    time = d.time
    for phase in (*r.phases, "night", "morning", "day"):
        warnings = r.set_time(phase)
        assert all("没有 renderer" in warning for warning in warnings), warnings
        assert int(m.light_active.sum()) + int(m.vis.headlight.active) <= 8
        for light in range(m.nlight):
            if int(m.light_bodyid[light]) == 0:
                assert np.allclose(d.light_xpos[light], m.light_pos[light])
                assert np.allclose(d.light_xdir[light], m.light_dir[light])
        assert d.time == time and all(np.array_equal(getattr(d, k), v) for k, v in data.items())
    assert all(np.array_equal(getattr(m, k), v) for k, v in r._cycle.base.items())
    try:
        r.set_time("invalid")
        raise AssertionError("Accepted invalid time")
    except ValueError:
        pass
    before = d.qpos.copy()
    r.reset()
    assert np.array_equal(before, d.qpos)
    return dict(
        scene=scene,
        robot=robot,
        rooms=len(catalogue["rooms"]),
        facilities=len(ids),
        phases=list(r.phases),
    )


def perform_fridge_placement(r, step):
    """Reuse in a running simulation: step(seconds) advances its own real physics.

    Caller supplies the simulation's lock/pacing and fresh reset state. This
    function never parks the robot, resets data, changes qpos or steps MuJoCo.
    """
    m, d = r.model, r.data
    task = r._task
    ix = r.interaction
    step(0.5)
    assert not r.task_status()["success"]
    ix.command(task.door, 1)
    step(ACTION_TIMEOUT + 0.2)
    assert ix.status(task.door)["result"] == "reached"
    assert task.opened
    rotation = d.xmat[task.container].reshape(3, 3)
    body_origin = d.xpos[task.container].copy()
    target_local = task.volume.mean(axis=0)
    # Place just above the shelf, accounting for the full can envelope.
    object_bounds = r._catalogue.geometry.bounds(task.object_geoms)
    half_height = (object_bounds[1, 2] - object_bounds[0, 2]) / 2
    target_local[2] = task.volume[0, 2] + half_height + 0.018
    target = body_origin + rotation @ target_local
    start = d.xipos[task.object].copy()
    door_body = m.jnt_bodyid[ix.joints[task.door]]
    door_bounds = r._catalogue.geometry.bounds(
        r._catalogue.geometry.body_geoms(door_body, recursive=True)
    )
    outside = target.copy()
    outside[1] = min(door_bounds[0, 1], target[1]) - 2 * np.max(object_bounds[1] - object_bounds[0])
    ix.grab(task.object)
    # Real bounded forces move the object around the island and through the open front.
    for destination in (np.array([start[0], outside[1], target[2]]), outside, target):
        current = ix.held[2].copy()
        for f in np.linspace(0, 1, 80):
            ix.move_grab(current + (destination - current) * f)
            step(0.05)
    held = r.task_status()
    assert not held["success"] and not held["checks"]["released"]
    # Stop the carry motion before releasing; momentum must not roll the can off its target.
    step(1.5)
    ix.release()
    step(2)
    placed = r.task_status()
    points = (r._catalogue.geometry.points(task.object_geoms) - body_origin) @ rotation
    assert placed["checks"]["inside"] and placed["checks"]["supported"], (
        placed,
        points.min(axis=0).tolist(),
        points.max(axis=0).tolist(),
    )
    assert not placed["success"] and not placed["checks"]["closed"]
    ix.command(task.door, 0)
    step(ACTION_TIMEOUT + 0.2)
    final = r.task_status()
    assert final["success"], final
    # Releasing the lease/controller cannot undo the physical success state.
    ix.cancel()
    r.update_task()
    assert r.task_status()["success"]
    return dict(held_rejected=True, open_door_rejected=True, physical_placement=final)


def fridge_physics():
    m, d, r, p = setup()
    result = perform_fridge_placement(r, lambda seconds: advance(p, r, seconds))
    # A brief hold between display updates must break the continuous-rest window.
    r.interaction.grab(r._task.object)
    r.observe_step()
    r.interaction.release()
    r.update_task()
    assert not r.task_status()["checks"]["settled"] and not r.task_status()["success"]
    advance(p, r, SETTLE_SECONDS + 0.1)
    assert r.task_status()["success"]
    result["sub_frame_hold_rejected"] = True
    qpos = d.qpos.copy()
    r.reset()
    assert np.array_equal(qpos, d.qpos) and not r.task_status()["success"]
    return result


def negative_predicates():
    # Deliberate state fixtures test predicate rejection; only fridge_physics above
    # is evidence of an executed placement. No fabricated contact or force arrays.
    m, d, r, p = setup()
    task = r._task
    ix = r.interaction
    jid = ix.free_bodies[task.object]
    q = int(m.jnt_qposadr[jid])
    v = int(m.jnt_dofadr[jid])
    joint = ix.joints[task.door]
    doorq = m.jnt_qposadr[joint]
    rotation = d.xmat[task.container].reshape(3, 3)
    origin = d.xpos[task.container].copy()
    half = (
        r._catalogue.geometry.bounds(task.object_geoms)[1]
        - r._catalogue.geometry.bounds(task.object_geoms)[0]
    ) / 2
    center = task.volume.mean(axis=0)
    cases = {
        "floating": center.copy(),
        "partial": center.copy(),
        "wrong_shelf": center.copy(),
        "wedged": center.copy(),
        "falling": center.copy(),
    }
    cases["partial"][0] = task.volume[1, 0] - half[0] / 2
    cases["wrong_shelf"][2] = task.volume[0, 2] - 0.3
    cases["wedged"][0] = task.volume[1, 0] + half[0] / 2
    out = {}
    for name, local in cases.items():
        ix.cancel()
        mujoco.mj_resetData(m, d)
        task.reset()
        d.qpos[doorq] = m.jnt_range[joint, 1]
        mujoco.mj_forward(m, d)
        task.update()
        d.qpos[doorq] = 0
        d.qpos[q : q + 3] = origin + rotation @ local
        d.qpos[q + 3 : q + 7] = [1, 0, 0, 0]
        if name == "falling":
            d.qvel[v + 2] = -1
        mujoco.mj_forward(m, d)
        task.update()
        d.time += SETTLE_SECONDS + 0.1
        task.update()
        assert not task.state["success"], (name, task.state)
        out[name] = dict(task.state["checks"])
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-physical", action="store_true")
    args = parser.parse_args()
    report = dict(
        runtime=[catalogue_and_time(s, b) for s in manifest.keys() for b in ("g1", "go2")],
        negative=negative_predicates(),
    )
    if not args.skip_physical:
        report["physics"] = fridge_physics()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
