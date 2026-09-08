#!/usr/bin/env python3
"""CPU physics acceptance for apt furniture; does not run a robot manipulation policy."""

from pathlib import Path
import argparse
import json
import sys
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest
from scenes.interaction import Interaction, InspectionPhysics, ACTION_TIMEOUT
from scenes.time_cycle import TimeCycle
from tools.walkthrough import park_robot

# Acceptance tolerances: joint stops are soft constraints, not exact clamps.
FRACTION_TOLERANCE = 0.04
MAX_PENETRATION = 0.01
DROP_HEIGHT = 0.4
MAX_DROP_HEIGHT = 2.0  # m; test trajectories remain below this release-height envelope.
MAX_COMMAND_SPEED = 0.5  # m/s; matches the slow carry trajectories.
MAX_JOINT_ANGULAR_SPEED = 20.0  # rad/s; excludes explosive servo motion in appliance hinges.


class Monitor:
    """Observe every physics step, including brief contacts before an action ends."""

    def __init__(self, model, interaction):
        self.ix = interaction
        self.joints = list(interaction.joints.values())
        self.movable_bodies = set(interaction.free_bodies)
        self.samples = 0
        self.penetration = 0.0
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.joint_angular_speed = 0.0
        gravity = float(np.linalg.norm(model.opt.gravity))
        self.linear_limit = (2 * gravity * MAX_DROP_HEIGHT) ** 0.5 + MAX_COMMAND_SPEED
        # A small body's ordinary tumble can exceed a hinge's angular speed.
        # Bound it using gravitational energy and its actual smallest inertia.
        self.angular_limits = {
            body: (
                2
                * model.body_mass[body]
                * gravity
                * MAX_DROP_HEIGHT
                / min(model.body_inertia[body])
            )
            ** 0.5
            for body in self.movable_bodies
        }
        self.worst_pair = None
        self.worst_time = None
        self.max_owned_force = 0.0

    def __call__(self, m, d):
        self.samples += 1
        assert np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()
        assert np.isfinite(self.ix.owned_force).all()
        for warning in (
            mujoco.mjtWarning.mjWARN_BADQPOS,
            mujoco.mjtWarning.mjWARN_BADQVEL,
            mujoco.mjtWarning.mjWARN_BADQACC,
        ):
            assert d.warning[warning].number == 0, str(warning)
        self.max_owned_force = max(self.max_owned_force, float(np.max(np.abs(self.ix.owned_force))))
        for contact in d.contact:
            if m.geom_group[contact.geom1] in (2, 3) or m.geom_group[contact.geom2] in (2, 3):
                continue
            depth = max(0, -float(contact.dist))
            if depth > self.penetration:
                self.penetration = depth
                self.worst_pair = [m.geom(contact.geom1).name, m.geom(contact.geom2).name]
                self.worst_time = float(d.time)
        for joint in self.joints:
            v = m.jnt_dofadr[joint]
            kind = int(m.jnt_type[joint])
            if kind == mujoco.mjtJoint.mjJNT_FREE:
                from scenes.interaction import GRAB_FORCE

                assert np.linalg.norm(self.ix.owned_force[v : v + 3]) <= GRAB_FORCE + 1e-6
                self.linear_speed = max(self.linear_speed, float(np.linalg.norm(d.qvel[v : v + 3])))
                angular = float(np.linalg.norm(d.qvel[v + 3 : v + 6]))
                self.angular_speed = max(self.angular_speed, angular)
                assert angular <= self.angular_limits[int(m.jnt_bodyid[joint])], (joint, angular)
            elif kind == mujoco.mjtJoint.mjJNT_HINGE:
                self.joint_angular_speed = max(self.joint_angular_speed, abs(float(d.qvel[v])))
            else:
                self.linear_speed = max(self.linear_speed, abs(float(d.qvel[v])))
            if kind != mujoco.mjtJoint.mjJNT_FREE:
                assert abs(self.ix.owned_force[v]) <= self.ix.gains(joint)[2] + 1e-6

    def report(self):
        result = dict(
            samples=self.samples,
            max_penetration=self.penetration,
            max_linear_speed=self.linear_speed,
            max_angular_speed=self.angular_speed,
            max_owned_force=self.max_owned_force,
            worst_pair=self.worst_pair,
            worst_time=self.worst_time,
            max_joint_angular_speed=self.joint_angular_speed,
            linear_speed_limit=self.linear_limit,
        )
        assert self.penetration <= MAX_PENETRATION, result
        assert (
            self.linear_speed <= self.linear_limit
            and self.joint_angular_speed <= MAX_JOINT_ANGULAR_SPEED
        ), result
        return result


def run(robot="g1"):
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename("apt", robot)))
    d = mujoco.MjData(m)
    park_robot(m, d, manifest.load_layout("apt"), robot)
    mujoco.mj_forward(m, d)
    i = Interaction(m, d)
    monitor = Monitor(m, i)
    p = InspectionPhysics(m, d, i, observer=monitor)
    p.advance(0.5)
    native = [n for n, j in i.joints.items() if m.jnt_type[j] != mujoco.mjtJoint.mjJNT_FREE]
    assert len(native) == 22 and len(i.free_bodies) == 9
    assert m.nu == (29 if robot == "g1" else 12)
    results = []
    # Source tree order opens doors before their drawers. Close in reverse order.
    for names, target in ((native, 1), (list(reversed(native)), 0)):
        for name in names:
            i.command(name, target)
            p.advance(ACTION_TIMEOUT + 0.1)
            status = i.status(name)
            assert status["result"] == "reached", status
            assert abs(status["fraction"] - target) < FRACTION_TOLERANCE, status
            assert np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()
            bad = [
                (m.geom(c.geom1).name, m.geom(c.geom2).name, float(c.dist))
                for c in d.contact
                if c.dist < -MAX_PENETRATION
            ]
            assert not bad, (status, bad)
            results.append(dict(target=target, **status))
    assert np.array_equal(m.dof_damping, i.base_damping)

    # A lifted task object falls back onto the real worktop after release.
    body = m.body("ix_a2_can").id
    resting = d.xipos[body].copy()
    i.grab(body)
    for fraction in np.linspace(0, 1, 100):
        i.move_grab(resting + [0, 0, DROP_HEIGHT * fraction])
        p.advance(0.02)
    raised = d.xipos[body].copy()
    assert raised[2] > resting[2] + DROP_HEIGHT * 0.75
    i.release()
    p.advance(2.0)
    landed = d.xipos[body].copy()
    assert abs(landed[2] - resting[2]) < 0.025, (resting, landed)
    assert np.linalg.norm(d.qvel[m.jnt_dofadr[i.free_bodies[body]] :][:3]) < 0.1

    # Lighting switches leave furniture untouched and day restores every model field.
    cycle = TimeCycle(m, "apt")
    qpos, qvel = d.qpos.copy(), d.qvel.copy()
    for phase in (*cycle.phases, "night", "morning", "day"):
        cycle.set(phase)
        assert np.array_equal(qpos, d.qpos) and np.array_equal(qvel, d.qvel)
    assert all(np.array_equal(getattr(m, k), v) for k, v in cycle.base.items())
    try:
        cycle.set("invalid")
        raise AssertionError("invalid time was accepted")
    except ValueError:
        pass
    for name in native:
        i.command(name, 1)
        p.advance(0.1)
        i.cancel()
        assert i.status(name)["result"] == "cancelled"
    assert np.array_equal(m.dof_damping, i.base_damping)
    assert np.allclose(d.qfrc_applied, 0)
    # Correct UI reset ordering: cancel first, then reset.
    mujoco.mj_resetData(m, d)
    assert not i.targets and i.held is None and np.allclose(d.qfrc_applied, 0)
    return dict(
        robot=robot,
        nq=m.nq,
        nv=m.nv,
        nu=m.nu,
        ngeom=m.ngeom,
        joint_cycles=results,
        movable_bodies=len(i.free_bodies),
        object_drop=dict(resting=resting.tolist(), raised=raised.tolist(), landed=landed.tolist()),
        time_presets=list(cycle.phases),
        cancellation_count=len(native),
        trajectory=monitor.report(),
    )


def obstruction():
    # A real wall stops a commanded slider. No qpos injection or disabled contact.
    m = mujoco.MjModel.from_xml_string("""<mujoco><option timestep="0.002" gravity="0 0 0"/>
    <worldbody><geom name="wall" type="box" pos=".3 0 0" size=".05 .4 .4" solref=".005 1"/>
    <body name="ix_slider"><joint name="ix_slide" type="slide" axis="1 0 0" range="0 1"/>
    <geom size=".05" mass="1" solref=".005 1"/></body></worldbody></mujoco>""")
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    i = Interaction(m, d)
    p = InspectionPhysics(m, d, i)
    # Selection obeys distance and the intervening wall.
    assert i.select([-0.2, 0, 0], [1, 0, 0])["names"] == ["ix_slide"]
    assert i.select([1, 0, 0], [-1, 0, 0]) is None
    assert i.select([-3, 0, 0], [1, 0, 0]) is None
    i.command("ix_slide", 1)
    p.advance(ACTION_TIMEOUT + 0.1)
    assert i.status("ix_slide")["result"] == "blocked"
    assert d.qpos[0] < 0.21 and np.allclose(d.qfrc_applied, 0)
    return i.status("ix_slide")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--robot", choices=["g1", "go2"], default="g1")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    report = dict(
        scene="apt", mujoco=mujoco.__version__, physics=run(args.robot), obstruction=obstruction()
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"PASS apt/{args.robot}: 44 joint targets, 22 cancellations, can drop, occlusion, obstruction, reset and four time presets; see check_interaction_cases.py for all nine bodies"
    )


if __name__ == "__main__":
    main()
