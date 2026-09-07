# 2026-09-07 apt2 walkthrough event integration. Run from the nerv-world root.
# Uses a hidden real GLFW context and the production callbacks, no network listener.
import sys, math, time, json
sys.path.insert(0,'.')
import glfw, numpy as np
from tools import walkthrough as w
from scenes import interaction as module
from scenes.apt2.interactivity import FRIDGE_XY
capture={}
BasePlayer=w.Player
class Player(BasePlayer):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  capture['player']=self
  self.fly=True
  aim((FRIDGE_XY[0]+.15, FRIDGE_XY[1]-2.0, 1.4),(*FRIDGE_XY,1.0),self)

def aim(eye,target,p):
 p.feet[:]=[eye[0],eye[1],eye[2]-p.eye_h]
 v=np.array(target)-eye
 p.yaw=math.degrees(math.atan2(v[1],v[0]));p.pitch=math.degrees(math.atan2(v[2],np.linalg.norm(v[:2])))

def ray(p):
 yaw,pitch=np.radians([p.yaw,p.pitch])
 return np.array([np.cos(yaw)*np.cos(pitch),np.sin(yaw)*np.cos(pitch),np.sin(pitch)])

Original=module.Interaction
class Interaction(Original):
 def __init__(self,*args):
  super().__init__(*args);capture['interaction']=self
module.Interaction=Interaction;w.Player=Player
create=glfw.create_window
def create_hidden(*args):
 glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
 capture['window']=create(*args)
 return capture['window']
glfw.create_window=create_hidden
register=glfw.set_key_callback
def register_callback(win,cb):
 capture['key']=cb
 return register(win,cb)
glfw.set_key_callback=register_callback
# Never capture the user's mouse or respond to their live keyboard in this check.
glfw.set_input_mode=lambda *a:None
glfw.get_key=lambda *a:glfw.RELEASE
poll=glfw.poll_events
start=None;stage=0

def key(k):capture['key'](capture['window'],k,0,glfw.PRESS,0)
def events():
 global start,stage
 poll();i=capture['interaction'];p=capture['player']
 if start is None:
  start=time.monotonic()
  target=i.select(p.eye,ray(p));assert target, (p.eye,p.yaw,p.pitch)
  capture['joint']=target['names'][0];assert 'door' in capture['joint']
  key(glfw.KEY_E);stage=1
 elapsed=time.monotonic()-start
 if stage==1 and elapsed>5.5:
  status=i.status(capture['joint']);assert status['result']=='reached',status
  capture['opened']=status
  before=i.d.qpos.copy()
  for _ in range(4):key(glfw.KEY_L)
  assert np.array_equal(before,i.d.qpos)
  aim((-9.25,3.2,1.45),(-9.25,4.3,1.0125),p)
  target=i.select(p.eye,ray(p));assert target and target['body'] in i.free_bodies,target
  key(glfw.KEY_G);assert i.held
  p.feet[2]+=.4;stage=2
 if stage==2 and elapsed>7.0:
  key(glfw.KEY_G);assert i.held is None;stage=3
 if stage==3 and elapsed>8.0:
  key(glfw.KEY_BACKSPACE)
  assert not i.targets and not i.held and np.allclose(i.d.qfrc_applied,0)
  capture['passed']=True;key(glfw.KEY_Q)
 if elapsed>12:raise AssertionError('UI event check exceeded deadline')
glfw.poll_events=events
w.run_viewer('apt2','g1',1.25,0,True)
assert capture.get('passed')
print(json.dumps(dict(passed=True,opened=capture['opened'],checks=['real GLFW context','E door','four L phases','G grab and release','Backspace reset'])))
