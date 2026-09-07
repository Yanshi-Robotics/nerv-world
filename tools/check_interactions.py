#!/usr/bin/env python3
"""CPU physics acceptance for apt2 furniture; does not run a robot manipulation policy."""
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


def run(robot='g1'):
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename('apt2', robot)))
    d = mujoco.MjData(m)
    park_robot(m, d, manifest.load_layout('apt2'), robot)
    mujoco.mj_forward(m, d)
    i = Interaction(m, d)
    p = InspectionPhysics(m, d, i)
    p.advance(0.5)
    native = [n for n,j in i.joints.items() if m.jnt_type[j] != mujoco.mjtJoint.mjJNT_FREE]
    assert len(native) == 22 and len(i.free_bodies) == 9
    assert m.nu == (29 if robot == 'g1' else 12)
    results = []
    # Source tree order opens doors before their drawers. Close in reverse order.
    for names, target in ((native, 1), (list(reversed(native)), 0)):
        for name in names:
            i.command(name, target)
            p.advance(ACTION_TIMEOUT + 0.1)
            status = i.status(name)
            assert status['result'] == 'reached', status
            assert abs(status['fraction']-target) < FRACTION_TOLERANCE, status
            assert np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()
            bad = [(m.geom(c.geom1).name, m.geom(c.geom2).name, float(c.dist))
                   for c in d.contact if c.dist < -MAX_PENETRATION]
            assert not bad, (status, bad)
            results.append(dict(target=target, **status))
    assert np.array_equal(m.dof_damping, i.base_damping)

    # A lifted task object falls back onto the real worktop after release.
    body = m.body('ix_a2_can').id
    resting = d.xipos[body].copy()
    i.grab(body)
    for fraction in np.linspace(0, 1, 100):
        i.move_grab(resting + [0, 0, DROP_HEIGHT*fraction])
        p.advance(0.02)
    raised = d.xipos[body].copy()
    assert raised[2] > resting[2] + DROP_HEIGHT*0.75
    i.release()
    p.advance(2.0)
    landed = d.xipos[body].copy()
    assert abs(landed[2]-resting[2]) < 0.025, (resting, landed)
    assert np.linalg.norm(d.qvel[m.jnt_dofadr[i.free_bodies[body]]:][:3]) < 0.1

    # Lighting switches leave furniture untouched and day restores every model field.
    cycle = TimeCycle(m, 'apt2')
    qpos, qvel = d.qpos.copy(), d.qvel.copy()
    for phase in (*cycle.phases, 'night', 'morning', 'day'):
        cycle.set(phase)
        assert np.array_equal(qpos, d.qpos) and np.array_equal(qvel, d.qvel)
    assert all(np.array_equal(getattr(m,k),v) for k,v in cycle.base.items())
    try:
        cycle.set('invalid')
        raise AssertionError('invalid time was accepted')
    except ValueError:
        pass
    i.command(native[0], 1)
    p.advance(0.1)
    i.cancel()
    assert i.status(native[0])['result'] == 'cancelled'
    assert np.array_equal(m.dof_damping, i.base_damping)
    assert np.allclose(d.qfrc_applied, 0)
    # Correct UI reset ordering: cancel first, then reset.
    mujoco.mj_resetData(m, d)
    assert not i.targets and i.held is None and np.allclose(d.qfrc_applied, 0)
    return dict(robot=robot, nq=m.nq, nv=m.nv, nu=m.nu, ngeom=m.ngeom,
                joint_cycles=results, movable_bodies=len(i.free_bodies),
                object_drop=dict(resting=resting.tolist(), raised=raised.tolist(), landed=landed.tolist()),
                time_presets=list(cycle.phases), cancellation='passed')


def obstruction():
    # A real wall stops a commanded slider. No qpos injection or disabled contact.
    m = mujoco.MjModel.from_xml_string('''<mujoco><option timestep="0.002" gravity="0 0 0"/>
    <worldbody><geom name="wall" type="box" pos=".3 0 0" size=".05 .4 .4" solref=".005 1"/>
    <body name="ix_slider"><joint name="ix_slide" type="slide" axis="1 0 0" range="0 1"/>
    <geom size=".05" mass="1" solref=".005 1"/></body></worldbody></mujoco>''')
    d = mujoco.MjData(m)
    mujoco.mj_forward(m,d)
    i = Interaction(m,d)
    p = InspectionPhysics(m,d,i)
    # Selection obeys distance and the intervening wall.
    assert i.select([-.2,0,0],[1,0,0])['names'] == ['ix_slide']
    assert i.select([1,0,0],[-1,0,0]) is None
    assert i.select([-3,0,0],[1,0,0]) is None
    i.command('ix_slide',1)
    p.advance(ACTION_TIMEOUT+0.1)
    assert i.status('ix_slide')['result'] == 'blocked'
    assert d.qpos[0] < .21 and np.allclose(d.qfrc_applied,0)
    return i.status('ix_slide')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--robot', choices=['g1','go2'], default='g1')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    report = dict(scene='apt2', mujoco=mujoco.__version__, physics=run(args.robot), obstruction=obstruction())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"PASS apt2/{args.robot}: 44 joint targets, 9 movable objects, gravity, occlusion, obstruction, reset and four time presets")


if __name__ == '__main__':
    main()
