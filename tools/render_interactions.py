#!/usr/bin/env python3
"""Photograph actual apt fixture motion and the four reversible time presets."""
from pathlib import Path
import argparse
import json
import sys
import mujoco
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest
from scenes.interaction import Interaction, InspectionPhysics, ACTION_TIMEOUT
from scenes.time_cycle import TimeCycle
from tools.make_time_stills import _look_at_quat
from tools.walkthrough import park_robot


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT/'docs/images/apt/interactions')
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--height', type=int, default=800)
    a=ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    m=mujoco.MjModel.from_xml_path(str(ROOT/'build/apt-g1.xml'))
    d=mujoco.MjData(m)
    park_robot(m,d,manifest.load_layout('apt'),'g1')
    mujoco.mj_forward(m,d)
    i=Interaction(m,d);p=InspectionPhysics(m,d,i);p.advance(.5)
    opt=mujoco.MjvOption();opt.geomgroup[2:5]=0
    shots=manifest.load_sibling('apt','shots').INTERACTIVE
    states={}
    with mujoco.Renderer(m,height=a.height,width=a.width) as renderer:
        cycle=TimeCycle(m,'apt',renderer)
        cam=m.camera('film').id
        def frame(tag,eye,target):
            m.cam_pos[cam]=eye;m.cam_quat[cam]=_look_at_quat(eye,target);m.cam_fovy[cam]=58
            mujoco.mj_forward(m,d)
            renderer.update_scene(d,camera='film',scene_option=opt)
            rgb=renderer.render()
            Image.fromarray(rgb).save(a.output/(tag+'.png'))
            print(tag,flush=True)
        for phase in cycle.phases:
            cycle.set(phase)
            for tag,eye,target in shots[:1]:
                frame(tag+'-'+phase,eye,target)
        cycle.set('day')
        for tag,eye,target in shots[1:]:
            frame(tag+'-closed',eye,target)
        for stem in ('fridge__freezer_door', 'fridge__fridge_door', 'stove__Door001'):
            name='ix_a2_'+stem+'_joint'
            i.command(name,1);p.advance(ACTION_TIMEOUT+.1)
            states[name]=i.status(name)
            assert states[name]['result']=='reached',states[name]
        for stem in ('fridge__freezer_drawer0','fridge__fridge_drawer0','stove__Shelf001'):
            name='ix_a2_'+stem+'_joint'
            i.command(name,.65);p.advance(ACTION_TIMEOUT+.1)
            states[name]=i.status(name)
            assert states[name]['result']=='reached',states[name]
        for tag,eye,target in shots:
            frame(tag+'-open',eye,target)
        cycle.set('night')
        frame('kitchen-open-night',shots[0][1],shots[0][2])
    i.cancel()
    (a.output/'states.json').write_text(json.dumps(states,indent=2)+'\n')


if __name__=='__main__':
    main()
