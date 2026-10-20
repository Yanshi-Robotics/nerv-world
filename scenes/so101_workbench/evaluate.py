"""Operator/offline task measurements. Never inject these simulator truths into an agent.

A proposed plan and the Hanoi solver are symbolic diagnostics, not robot actions.
"""

from __future__ import annotations

import itertools
import math

import mujoco
import numpy as np


def object_points(model, data, obj):
    if obj.get("flex"):
        fid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, obj["flex"])
        start, count = int(model.flex_vertadr[fid]), int(model.flex_vertnum[fid])
        return data.flexvert_xpos[start : start + count].copy()
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, obj["body"])
    points = []
    for gid in np.flatnonzero(model.geom_bodyid == bid):
        center, half = model.geom_aabb[gid, :3], model.geom_aabb[gid, 3:]
        corners = np.asarray(list(itertools.product((-1, 1), repeat=3))) * half + center
        points.extend(corners @ data.geom_xmat[gid].reshape(3, 3).T + data.geom_xpos[gid])
    return np.asarray(points)


def object_contact_with_geoms(model, data, obj, other_geoms):
    if obj.get("flex"):
        fid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, obj["flex"])
        return any(
            int(c.flex[i]) == fid and int(c.geom[1 - i]) in other_geoms
            for c in data.contact
            for i in (0, 1)
        )
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, obj["body"])
    geoms = set(np.flatnonzero(model.geom_bodyid == bid))
    return any(
        (int(c.geom[0]) in geoms and int(c.geom[1]) in other_geoms)
        or (int(c.geom[1]) in geoms and int(c.geom[0]) in other_geoms)
        for c in data.contact
    )


def object_contact_with_robot(model, data, obj):
    controlled = set(
        int(model.body_rootid[model.jnt_bodyid[model.actuator_trnid[i, 0]]])
        for i in range(model.nu)
    )
    robot_geoms = set(
        np.flatnonzero(np.isin(model.body_rootid[model.geom_bodyid], list(controlled)))
    )
    return object_contact_with_geoms(model, data, obj, robot_geoms)


def object_speed(model, data, obj):
    if obj.get("flex"):
        fid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, obj["flex"])
        start, count = int(model.flex_vertadr[fid]), int(model.flex_vertnum[fid])
        bodies = np.unique(model.flex_vertbodyid[start : start + count])
    else:
        bodies = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, obj["body"])]
    speed = 0.0
    for bid in bodies:
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, int(bid), velocity, 0)
        if obj.get("flex"):
            speed = max(speed, float(np.linalg.norm(velocity[3:])))
        else:
            offsets = object_points(model, data, obj) - data.xpos[bid]
            point_velocities = velocity[3:] + np.cross(velocity[:3], offsets)
            speed = max(speed, float(np.linalg.norm(point_velocities, axis=1).max()))
    return speed


def evaluate(model, data, metadata):
    """Conservative containment, release and rest; this is independent physical scoring."""
    tolerance = metadata["validation"]["surface_tolerance_m"]
    margin = metadata["validation"]["inside_margin_m"]
    if "hanoi" in metadata:
        return evaluate_hanoi(model, data, metadata)
    baskets = {b["id"]: b for b in metadata["baskets"]}
    results = []
    for obj in metadata["objects"]:
        points = object_points(model, data, obj)
        basket = baskets[obj["basket"]]
        center = np.asarray(basket["xy"])
        half = np.asarray(basket["inner_size_xy"]) / 2 - margin
        radius = (
            model.flex_radius[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, obj["flex"])]
            if obj.get("flex")
            else 0
        )
        inside = bool(
            np.all(np.abs(points[:, :2] - center) + radius <= half)
            and np.all(points[:, 2] - radius >= basket["bottom_z"] - tolerance)
            and np.all(points[:, 2] + radius <= basket["rim_z"] + tolerance)
        )
        held = object_contact_with_robot(model, data, obj)
        supported = object_contact_with_geoms(
            model, data, obj, {model.geom(f"{basket['id']}_bottom").id}
        )
        speed = object_speed(model, data, obj)
        resting = speed <= metadata["validation"]["rest_speed_m_s"]
        results.append(
            {
                "id": obj["id"],
                "target": obj["basket"],
                "inside": inside,
                "released": not held,
                "supported": supported,
                "resting": resting,
                "max_speed_m_s": speed,
                "success": inside and not held and supported and resting,
            }
        )
    return {
        "kind": "sorting" if len(results) > 1 else "pick-place",
        "objects": results,
        "success": bool(results) and all(r["success"] for r in results),
        "evidence": "simulator_state_for_operator_only",
    }


def evaluate_hanoi(model, data, metadata):
    spec = metadata["hanoi"]
    tol = metadata["validation"]["surface_tolerance_m"]
    pegs = np.asarray(spec["peg_xy"])
    stacks = [[] for _ in pegs]
    unplaced = []
    rows = []
    for i, disk in enumerate(spec["disks"]):
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, disk["body"])
        xyz = data.xpos[bid]
        distances = np.linalg.norm(pegs - xyz[:2], axis=1)
        peg = int(np.argmin(distances))
        # Inner disk radius, not its outer perimeter, determines whether the peg is inside.
        aligned = distances[peg] < spec["hole_radius_m"] - spec["peg_radius_m"] + tol
        upright = data.xmat[bid].reshape(3, 3)[2, 2] >= math.cos(
            math.radians(metadata["validation"]["disk_tilt_deg"])
        )
        held = object_contact_with_robot(model, data, {"body": disk["body"]})
        resting = (
            object_speed(model, data, {"body": disk["body"]})
            <= metadata["validation"]["rest_speed_m_s"]
        )
        row = {
            "disk": i,
            "peg": peg if aligned and upright else None,
            "z": float(xyz[2]),
            "released": not held,
            "resting": resting,
        }
        rows.append(row)
        if not aligned or not upright:
            unplaced.append(i)
        else:
            stacks[peg].append((float(xyz[2]), i))
    ordered = [[i for _z, i in sorted(s)] for s in stacks]
    legal = not unplaced and all(s == sorted(s) for s in ordered)
    supported = True
    for peg, stack in enumerate(stacks):
        ordered_stack = sorted(stack)
        for level, (z, disk_index) in enumerate(ordered_stack):
            expected = spec["base_z"] + (level + 0.5) * spec["disk_height_m"]
            supported &= abs(z - expected) <= tol
            if level == 0:
                support_geoms = {model.geom(f"peg_base_{peg}").id}
            else:
                below = model.body(spec["disks"][ordered_stack[level - 1][1]]["body"]).id
                support_geoms = set(np.flatnonzero(model.geom_bodyid == below))
            supported &= object_contact_with_geoms(
                model, data, spec["disks"][disk_index], support_geoms
            )
    complete = ordered[spec["target_peg"]] == list(range(len(spec["disks"])))
    return {
        "kind": "hanoi",
        "stacks_bottom_to_top": ordered,
        "unplaced": unplaced,
        "legal": legal,
        "supported": bool(supported),
        "success": bool(
            complete and legal and supported and all(r["released"] and r["resting"] for r in rows)
        ),
        "disks": rows,
        "evidence": "simulator_state_for_operator_only",
    }


def hanoi_plan(disks, source=0, target=2, spare=1):
    """Minimum legal symbolic plan, never a prerecorded physical execution."""
    if not isinstance(disks, int) or disks < 1:
        raise ValueError("disk count must be a positive integer")
    if len({source, target, spare}) != 3:
        raise ValueError("pegs must be different")
    moves = []

    def solve(n, a, b, c):
        if n == 0:
            return
        solve(n - 1, a, c, b)
        moves.append({"disk": disks - n, "from": a, "to": b})
        solve(n - 1, c, b, a)

    solve(disks, source, target, spare)
    return moves
