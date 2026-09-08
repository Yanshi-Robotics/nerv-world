#!/usr/bin/env python3
"""Extended real-scene furniture trajectories, independent of robot policies."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_operator import setup
from tools.check_interactions import Monitor
from scenes.interaction import ACTION_TIMEOUT, GRAB_FORCE
from scenes.paths import residence_routes
from scenes.collision import collision_ray

LIFT_HEIGHT = 0.4  # Same gravity-drop distance used by the original acceptance.
MOVE_SECONDS = 3.0  # Deliberate operator drag, faster than neither a dropped object nor the servo.
PERIOD = 0.02  # Operator updates; the monitor still observes every physics dt.
REST_SECONDS = 3.0
CARRY_SPEED = 0.5  # m/s, leaves contact clearance at route corners for the force servo.


class Fixture:
    def __init__(self):
        self.m, self.d, self.r, self.p = setup()
        self.ix = self.r.interaction
        self.monitor = Monitor(self.m, self.ix)
        self.p.observer = self.monitor
        self.p.advance(0.5)

    def reset(self):
        self.ix.cancel()
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[self.p.qindices] = self.p.parked
        self.d.qvel[self.p.vindices] = 0
        self.ix.results.clear()
        self.p.accumulated = 0
        mujoco.mj_forward(self.m, self.d)
        self.monitor = Monitor(self.m, self.ix)
        self.p.observer = self.monitor
        self.p.advance(0.5)

    def move(self, target, seconds=MOVE_SECONDS):
        if self.ix.held is None:
            return False
        start = self.ix.held[2].copy()
        seconds = max(seconds, float(np.linalg.norm(np.asarray(target) - start)) / CARRY_SPEED)
        for fraction in np.linspace(0, 1, round(seconds / PERIOD)):
            self.ix.move_grab(start + (np.asarray(target) - start) * fraction)
            self.p.advance(PERIOD)
            if self.ix.held is None:
                break
        self.p.advance(0.3)
        return self.ix.held is not None

    def bounds(self, body):
        return self.r._catalogue.geometry.bounds_in_frame(
            self.r._catalogue.geometry.body_geoms(body, recursive=True),np.zeros(3),np.eye(3)
        )

    def clear_chair(self, body, table):
        """Pull far enough to clear the real tabletop, within the room aisle."""
        bounds = self.bounds(body)
        axis = int(np.argmin(table[1,:2]-table[0,:2]))
        target = self.d.xipos[body].copy()
        clearance = 0.05  # m; enough separation to lift without grazing the table edge.
        if target[axis] < table.mean(axis=0)[axis]:
            target[axis] += min(0,table[0,axis]-bounds[1,axis]-clearance)
        else:
            target[axis] += max(0,table[1,axis]-bounds[0,axis]+clearance)
        return self.move(target)


def closed_door_cases(fixture):
    f = fixture
    m, ix = f.m, f.ix
    cases = [
        (name, "ix_a2_fridge__" + ("freezer" if "freezer" in name else "fridge") + "_door_joint")
        for name in ix.joints
        if "drawer" in name
    ]
    cases += [(name, "ix_a2_stove__Door001_joint") for name in ix.joints if "Shelf" in name]
    results = []
    for name, door in cases:
        f.reset()
        drawer_body = m.jnt_bodyid[ix.joints[name]]
        door_body = m.jnt_bodyid[ix.joints[door]]
        door_geoms = set(f.r._catalogue.geometry.body_geoms(door_body, recursive=True))
        drawer_geoms = set(f.r._catalogue.geometry.body_geoms(drawer_body, recursive=True))
        evidence = dict(contacts=0, door_max_fraction=0.0)

        def observe(model, data):
            f.monitor(model, data)
            evidence["door_max_fraction"] = max(
                evidence["door_max_fraction"], abs(ix.status(door)["fraction"])
            )
            evidence["contacts"] += sum(
                (c.geom1 in drawer_geoms and c.geom2 in door_geoms)
                or (c.geom2 in drawer_geoms and c.geom1 in door_geoms)
                for c in data.contact
            )

        f.p.observer = observe
        ix.command(name, 1)
        f.p.advance(ACTION_TIMEOUT + 0.2)
        status = ix.status(name)
        assert status["result"] in ("blocked", "reached"), status
        assert evidence["contacts"] > 0, (name, evidence, status)
        results.append(
            dict(joint=name, door=door, result=status, **evidence, trajectory=f.monitor.report())
        )
    return results


def movable_cases(fixture):
    f = fixture
    m, d, ix = f.m, f.d, f.ix
    results = []
    table = f.r._catalogue.geometry.bounds([m.geom("furn_dn_table_top").id])
    for body in ix.free_bodies:
        for eccentric in (False, True):
            f.reset()
            start = d.xipos[body].copy()
            bounds = f.bounds(body)
            assert m.body_mass[body] * np.linalg.norm(m.opt.gravity) < GRAB_FORCE
            ix.grab(body)
            # Pull dining chairs out from under the tabletop before lifting.
            if m.body(body).name.startswith("ix_dn_"):
                f.clear_chair(body,table)
            resting = d.xipos[body].copy()
            ix.release()
            ix.grab(body)
            if eccentric:
                ix.release()
                bounds = f.bounds(body)
                point = d.xipos[body].copy()
                point[0] += (bounds[1, 0] - bounds[0, 0]) * 0.2
                ix.grab(body, point)
            target = ix.held[2].copy()
            target[2] += LIFT_HEIGHT
            f.move(target)
            f.p.advance(1)
            raised = d.xipos[body].copy()
            ix.release()
            f.p.advance(REST_SECONDS)
            landed = d.xipos[body].copy()
            # Eccentric single-point grabs may rotate or topple the object. The
            # evidence is real motion followed by released support, not pose control.
            contacts = [
                c
                for c in d.contact
                if m.geom_bodyid[c.geom1] == body or m.geom_bodyid[c.geom2] == body
            ]
            assert contacts, (m.body(body).name, eccentric, "no final support")
            if not eccentric:
                assert raised[2] > resting[2] + LIFT_HEIGHT * 0.5, (
                    m.body(body).name,
                    resting,
                    raised,
                )
            assert ix.held is None
            results.append(
                dict(
                    body=m.body(body).name,
                    case="eccentric_release" if eccentric else "center_lift_drop",
                    start=start.tolist(),
                    raised=raised.tolist(),
                    landed=landed.tolist(),
                    contacts=len(contacts),
                    trajectory=f.monitor.report(),
                )
            )
    return results


def invalid_inputs(f):
    f.reset()
    body = next(iter(f.ix.free_bodies))
    f.ix.grab(body)
    initial = f.ix.held
    before = f.d.qpos.copy()
    checks = 0
    for point in ([np.nan, 0, 0], [1, 2], 1):
        for operation in (lambda: f.ix.grab(body, point), lambda: f.ix.move_grab(point)):
            try:
                operation()
                raise AssertionError("Invalid point accepted")
            except ValueError:
                pass
            assert f.ix.held is initial and np.array_equal(f.d.qpos, before)
            checks += 1
    for name, jid in f.ix.joints.items():
        if f.m.jnt_type[jid] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        for fraction in (-1, 2, np.nan):
            try:
                f.ix.command(name, fraction)
                raise AssertionError("Invalid fraction accepted")
            except ValueError:
                pass
            assert not f.ix.targets
            checks += 1
    other = next(b for b in f.ix.free_bodies if b != body)
    f.ix.grab(other)
    old_status = f.ix.status(f.m.joint(f.ix.free_bodies[body]).name)
    assert old_status["result"] == "released" and not old_status["held"]
    assert f.ix.held[0] == other and np.allclose(f.ix.owned_force, 0)
    f.ix.cancel()
    return checks


def prop_barrier(f):
    """A real carried can obstructs the refrigerator door sweep."""
    f.reset()
    m, d, ix = f.m, f.d, f.ix
    task = f.r._task
    rotation = d.xmat[task.container].reshape(3, 3)
    origin = d.xpos[task.container]
    local = task.volume.mean(axis=0)
    bounds = f.bounds(task.object)
    # Approach the open compartment away from its swung-out hinged edge. Keep
    # the can at the real shelf height so the closing door meets a supported prop.
    local[2] = task.volume[0, 2] + (bounds[1, 2] - bounds[0, 2]) / 2 + 0.018
    target = origin + rotation @ local
    door_body = m.jnt_bodyid[ix.joints[task.door]]
    doors = set(f.r._catalogue.geometry.body_geoms(door_body, recursive=True))
    can = set(task.object_geoms)
    door_bounds = f.r._catalogue.geometry.bounds(list(doors))
    ray_start = target.copy()
    ray_start[1] = door_bounds[0, 1] - (bounds[1, 1] - bounds[0, 1])
    distance, gid = collision_ray(m, d, ray_start, (0, 1, 0))
    assert gid in doors, (gid, m.geom(gid).name)
    target[1] = ray_start[1] + distance
    ix.command(task.door, 1)
    f.p.advance(ACTION_TIMEOUT + 0.2)
    door_bounds = f.r._catalogue.geometry.bounds(list(doors))
    outside = target.copy()
    outside[1] = min(door_bounds[0, 1], target[1]) - 2 * np.max(bounds[1] - bounds[0])
    ix.grab(task.object)
    start = d.xipos[task.object].copy()
    for point in ([start[0], outside[1], target[2]], outside, target):
        assert f.move(point), (point, ix.status(m.joint(ix.free_bodies[task.object]).name))
    evidence = dict(contacts=0)

    def observe(model, data):
        f.monitor(model, data)
        evidence["contacts"] += sum(
            (c.geom1 in doors and c.geom2 in can) or (c.geom2 in doors and c.geom1 in can)
            for c in data.contact
        )

    f.p.observer = observe
    ix.command(task.door, 0)
    f.p.advance(ACTION_TIMEOUT + 0.2)
    status = ix.status(task.door)
    assert evidence["contacts"] > 0, (status, evidence)
    assert status["result"] == "blocked", status
    before = d.qpos.copy()
    velocity = d.qvel.copy()
    time = d.time
    ix.cancel()
    assert np.array_equal(d.qpos, before) and np.array_equal(d.qvel, velocity) and d.time == time
    assert not ix.held and not ix.targets and np.allclose(ix.owned_force, 0)
    return dict(result=status, **evidence, trajectory=f.monitor.report())


def table_cases(f):
    """Three small props contact real table legs and drop at the actual table edge."""
    m, d, ix = f.m, f.d, f.ix
    top = m.geom("furn_dn_table_top").id
    table = f.r._catalogue.geometry.bounds([top])
    leg = m.geom("furn_dn_table_legd").id
    leg_bounds = f.r._catalogue.geometry.bounds([leg])
    x = leg_bounds.mean(axis=0)[0]
    front = table[0, 1]
    props = [b for b in ix.free_bodies if m.body(b).name.startswith("ix_a2_")]
    results = []
    for body in props:
        for case in ("leg_contact", "inside_edge_release", "outside_edge_drop"):
            f.reset()
            bounds = f.bounds(body)
            half = (bounds[1] - bounds[0]) / 2
            start = d.xipos[body].copy()
            ix.grab(body)
            # A high transfer clears the island; a front approach avoids the
            # six chairs. The test object reaches the obstacle through forces.
            height = max(start[2], table[1, 2]) + LIFT_HEIGHT
            corridor = front - 4 * half[1]
            routes = {
                route["id"]: route["points"] for route in residence_routes(f.r._catalogue.layout)
            }
            kitchen = routes["kitchen_access"]
            living = routes["living_dining"]
            # Kitchen and dining are divided by a wall. Follow their actual door
            # connections through the gallery instead of dragging across it.
            transfer = [[start[0], start[1], height], [start[0], kitchen[-1][1], height]]
            transfer += [[px, py, height] for px, py, _ in reversed(kitchen)]
            transfer += [[px, py, height] for px, py, _ in living]
            # The robot route stops near the doorway for safe standing. Carry
            # the small prop fully inside before turning past that door jamb.
            transfer += [[x, living[-1][1], height], [x, corridor, height]]
            for point in transfer:
                assert f.move(point), (m.body(body).name, point, "carry approach obstructed")
            evidence = dict(leg_contacts=0, table_contacts=0)

            def observe(model, data):
                f.monitor(model, data)
                for contact in data.contact:
                    if (
                        model.geom_bodyid[contact.geom1] != body
                        and model.geom_bodyid[contact.geom2] != body
                    ):
                        continue
                    evidence["leg_contacts"] += int(leg in (contact.geom1, contact.geom2))
                    evidence["table_contacts"] += int(top in (contact.geom1, contact.geom2))

            f.p.observer = observe
            if case == "leg_contact":
                target = [x, corridor, leg_bounds.mean(axis=0)[2]]
                f.move(target)
                target[1] = leg_bounds[1, 1] + half[1]
                f.move(target)
                f.p.advance(1)
                assert evidence["leg_contacts"] > 0, (
                    m.body(body).name,
                    case,
                    evidence,
                    d.xipos[body].tolist(),
                    target,
                    leg_bounds.tolist(),
                    [
                        (m.geom(c.geom1).name, m.geom(c.geom2).name)
                        for c in d.contact
                        if m.geom_bodyid[c.geom1] == body or m.geom_bodyid[c.geom2] == body
                    ],
                )
                ix.cancel()
                f.p.advance(REST_SECONDS)
            else:
                target = [
                    x,
                    front + (2 * half[1] if case == "inside_edge_release" else -2 * half[1]),
                    table[1, 2] + half[2] + 0.02,
                ]
                f.move(target)
                f.p.advance(1)
                ix.release()
                f.p.advance(REST_SECONDS)
                if case == "inside_edge_release":
                    assert evidence["table_contacts"] > 0, (m.body(body).name, case, evidence)
                else:
                    assert d.xipos[body, 2] < table[0, 2], (
                        m.body(body).name,
                        case,
                        d.xipos[body].tolist(),
                    )
            results.append(
                dict(body=m.body(body).name, case=case, **evidence, trajectory=f.monitor.report())
            )
    return results


def chair_boundary_cases(f):
    """All six chairs attempt the real table boundary, including obstructed paths."""
    m, d, ix = f.m, f.d, f.ix
    top = m.geom("furn_dn_table_top").id
    table = f.r._catalogue.geometry.bounds([top])
    table_xy = table.mean(axis=0)[:2]
    legs = {m.geom("furn_dn_table_leg" + tag).id for tag in "abcd"}
    chairs = [body for body in ix.free_bodies if m.body(body).name.startswith("ix_dn_")]
    results = []
    for body in chairs:
        for case in ("table_leg_approach", "table_edge_release"):
            f.reset()
            initial = d.xipos[body].copy()
            bounds = f.bounds(body)
            ix.grab(body)
            f.clear_chair(body,table)
            ix.release()
            ix.grab(body)
            evidence = dict(
                table_contacts=0, leg_contacts=0, first_table_contact=None, other_contacts={}
            )

            def observe(model, data):
                f.monitor(model, data)
                for contact in data.contact:
                    one, two = int(contact.geom1), int(contact.geom2)
                    if model.geom_bodyid[one] != body and model.geom_bodyid[two] != body:
                        continue
                    other = two if model.geom_bodyid[one] == body else one
                    other_name = model.geom(other).name
                    evidence["other_contacts"][other_name] = (
                        evidence["other_contacts"].get(other_name, 0) + 1
                    )
                    kind = (
                        "tabletop"
                        if top in (one, two)
                        else "table_leg"
                        if one in legs or two in legs
                        else None
                    )
                    if kind is None:
                        continue
                    if evidence["first_table_contact"] is None:
                        evidence["first_table_contact"] = kind
                    evidence["table_contacts"] += int(kind == "tabletop")
                    evidence["leg_contacts"] += int(kind == "table_leg")

            f.p.observer = observe
            if case == "table_leg_approach":
                leg = min(
                    legs, key=lambda geom: np.linalg.norm(d.geom_xpos[geom, :2] - initial[:2])
                )
                target = d.xipos[body].copy()
                target[:2] = d.geom_xpos[leg, :2]
                f.move(target)
                f.p.advance(REST_SECONDS)
                outcome = (
                    "tabletop_obstructed"
                    if evidence["first_table_contact"] == "tabletop"
                    else "table_leg_contact"
                    if evidence["first_table_contact"] == "table_leg"
                    else "other_boundary_obstructed"
                )
                assert evidence["other_contacts"], (m.body(body).name, case, "No contact")
            else:
                bounds = f.bounds(body)
                com = d.xipos[body].copy()
                target = com.copy()
                target[2] = table[1, 2] + com[2] - bounds[0, 2] + 0.02
                f.move(target)
                f.p.advance(1)
                side = -1 if initial[0] < table_xy[0] else 1
                edge = table[0 if side < 0 else 1, 0]
                target[0] = edge + side * (bounds[1, 0] - bounds[0, 0]) * 0.15
                target[1] = initial[1]
                f.move(target)
                f.p.advance(1)
                release_bounds = f.bounds(body)
                # If the edge already obstructs the lift, record the contact
                # instead of pretending the requested target was reached.
                outcome = (
                    "edge_release"
                    if release_bounds[0, 0] <= edge <= release_bounds[1, 0]
                    else "edge_approach_obstructed"
                )
                assert outcome == "edge_release" or evidence["first_table_contact"] is not None, (
                    m.body(body).name,
                    release_bounds,
                    evidence,
                )
            before = d.qpos.copy()
            velocity = d.qvel.copy()
            time = d.time
            ix.cancel()
            assert ix.held is None and not ix.targets and np.allclose(ix.owned_force, 0)
            assert (
                np.array_equal(d.qpos, before)
                and np.array_equal(d.qvel, velocity)
                and d.time == time
            )
            f.p.advance(REST_SECONDS)
            support = sum(
                m.geom_bodyid[c.geom1] == body or m.geom_bodyid[c.geom2] == body for c in d.contact
            )
            assert support, (m.body(body).name, case, "No resting contact")
            try:
                trajectory = f.monitor.report()
                passed = True
            except AssertionError as error:
                # Finish the coverage matrix and retain the failing trajectory.
                # The command exits unsuccessfully after writing every result.
                trajectory = error.args[0]
                passed = False
            results.append(
                dict(
                    body=m.body(body).name,
                    case=case,
                    outcome=outcome,
                    passed=passed,
                    **evidence,
                    final_position=d.xipos[body].tolist(),
                    resting_contacts=int(support),
                    cancel_cleared=True,
                    trajectory=trajectory,
                )
            )
    return results


def blocked_drag_cases(f):
    """Retain the original overlong chair drag as an actual blocked-input case."""
    m,d,ix=f.m,f.d,f.ix
    table=f.r._catalogue.geometry.bounds([m.geom("furn_dn_table_top").id])
    results=[]
    for body in ix.free_bodies:
        if not m.body(body).name.startswith("ix_dn_"):
            continue
        f.reset()
        start=d.xipos[body].copy()
        old_bounds=f.r._catalogue.geometry.bounds(f.r._catalogue.geometry.body_geoms(body,recursive=True))
        outward=start[:2]-table.mean(axis=0)[:2]
        outward/=np.linalg.norm(outward)
        target=start.copy()
        target[:2]+=outward*np.linalg.norm(old_bounds[1,:2]-old_bounds[0,:2])
        ix.grab(body)
        f.move(target)
        # Preserve the former second stage too: regrasp at the achieved pose
        # and drive the chair toward the nearest leg, including any tight gap.
        ix.release()
        ix.grab(body)
        legs=[m.geom("furn_dn_table_leg"+tag).id for tag in "abcd"]
        leg=min(legs,key=lambda g:np.linalg.norm(d.geom_xpos[g,:2]-start[:2]))
        leg_target=d.xipos[body].copy()
        leg_target[:2]=d.geom_xpos[leg,:2]
        f.move(leg_target)
        f.p.advance(REST_SECONDS)
        status=ix.status(m.joint(ix.free_bodies[body]).name)
        assert status["result"]=="blocked" and not status["held"],status
        assert np.allclose(ix.owned_force,0)
        before=d.qpos.copy();velocity=d.qvel.copy();time=d.time
        ix.cancel()
        assert np.array_equal(d.qpos,before) and np.array_equal(d.qvel,velocity) and d.time==time
        results.append(dict(body=m.body(body).name,target=target.tolist(),leg_target=leg_target.tolist(),status=status,
                            cancelled_without_state_change=True,trajectory=f.monitor.report()))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        choices=("closed", "movable", "input", "barrier", "table", "chairs", "blocked", "all"),
        default="all",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    f = Fixture()
    result = {}
    if args.case in ("closed", "all"):
        result["closed_door"] = closed_door_cases(f)
    if args.case in ("movable", "all"):
        result["movable"] = movable_cases(f)
    if args.case in ("input", "all"):
        result["invalid_input_checks"] = invalid_inputs(f)
    if args.case in ("barrier", "all"):
        result["prop_barrier"] = prop_barrier(f)
    if args.case in ("table", "all"):
        result["table"] = table_cases(f)
    if args.case in ("chairs", "all"):
        result["chair_boundaries"] = chair_boundary_cases(f)
    if args.case in ("blocked", "all"):
        result["blocked_drags"] = blocked_drag_cases(f)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not all(case["passed"] for case in result.get("chair_boundaries", [])):
        raise SystemExit(1)
