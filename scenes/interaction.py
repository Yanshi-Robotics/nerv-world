"""Operator interaction through bounded forces, with actual joint-state feedback.

This is a scene inspection tool, not a robot manipulation policy. No action writes
qpos, teleports an object, or adds actuators to the robot's control vector.
"""

from __future__ import annotations

import numpy as np
import mujoco

REACH = 2.0  # metres from the operator camera; occluding geometry still blocks selection.
HINGE_KP, HINGE_KD, HINGE_FORCE = 80.0, 18.0, 35.0
SLIDE_KP, SLIDE_KD, SLIDE_FORCE = 350.0, 35.0, 60.0
BUTTON_KP, BUTTON_KD, BUTTON_FORCE = 60000.0, 50.0, 15.0
BUTTON_TRAVEL = 0.005  # metres: source hood buttons have millimetre travel.
ACTION_TIMEOUT = 5.0
TRAVEL_SECONDS = 1.2
GRAB_KP, GRAB_KD, GRAB_FORCE = 160.0, 25.0, 100.0
GRAB_TARGET_SPEED = 0.5  # m/s; operator cursor targets follow a deliberate carrying speed.
# A velocity-driven PD spring lags by speed*KD/KP. Allow twice that steady
# lag, then release a body that cannot follow instead of accumulating strain.
GRAB_MAX_LAG = 2 * GRAB_TARGET_SPEED * GRAB_KD / GRAB_KP


class Interaction:
    def __init__(self, model, data):
        self.m, self.d = model, data
        self.joints = {model.joint(j).name: j for j in range(model.njnt)
                       if model.joint(j).name.startswith("ix_")}
        self.free_bodies = {int(model.jnt_bodyid[j]): j for j in self.joints.values()
                            if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE}
        self.targets = {}
        self.results = {}
        self.held = None
        self.grab_target = None
        self.owned_force = np.zeros(model.nv)
        self.base_damping = model.dof_damping.copy()

    def gains(self, j):
        span = float(np.ptp(self.m.jnt_range[j]))
        if self.m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            return HINGE_KP, HINGE_KD, HINGE_FORCE
        if span < BUTTON_TRAVEL:
            return BUTTON_KP, BUTTON_KD, BUTTON_FORCE
        return SLIDE_KP, SLIDE_KD, SLIDE_FORCE

    def finish(self, name, result):
        v = self.m.jnt_dofadr[self.joints[name]]
        self.m.dof_damping[v] = self.base_damping[v]
        self.targets.pop(name, None)
        self.results[name] = result

    def clear_forces(self):
        self.d.qfrc_applied[:] -= self.owned_force
        self.owned_force[:] = 0

    def cancel(self):
        self.clear_forces()
        for name in list(self.targets):
            self.finish(name, 'cancelled')
        if self.held:
            self.results[self.m.joint(self.free_bodies[self.held[0]]).name] = "cancelled"
        self.held = self.grab_target = None

    def command(self, name, fraction):
        if name not in self.joints or not np.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("Expected a named furniture joint and a fraction in [0, 1]")
        j = self.joints[name]
        if self.m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
            raise ValueError("Free objects are moved by grab/release, not joint targets")
        low, high = self.m.jnt_range[j]
        start = float(self.d.qpos[self.m.jnt_qposadr[j]])
        self.targets[name] = dict(value=float(low + fraction * (high-low)), start=start,
                                  time=float(self.d.time))
        self.results[name] = "moving"
        # MuJoCo integrates joint damping implicitly. Explicit velocity feedback
        # at cabinet-door gains is unstable for tiny native knob inertias.
        v = self.m.jnt_dofadr[j]
        self.m.dof_damping[v] = self.base_damping[v] + self.gains(j)[1]

    def status(self, name):
        j = self.joints[name]
        if self.m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
            body = int(self.m.jnt_bodyid[j])
            return dict(name=name, position=self.d.xpos[body].tolist(),
                        held=bool(self.held and self.held[0] == body),
                        result=self.results.get(name, "idle"))
        low, high = self.m.jnt_range[j]
        value = float(self.d.qpos[self.m.jnt_qposadr[j]])
        return dict(name=name, value=value, fraction=float((value-low)/(high-low)),
                    result=self.results.get(name, "idle"))

    def select(self, origin, direction, reach=REACH):
        # Visible parts and physical colliders both occlude; glass is not ignored.
        gid = np.array([-1], dtype=np.int32)
        origin, direction = np.asarray(origin, float), np.asarray(direction, float)
        length = np.linalg.norm(direction)
        if length == 0:
            return None
        direction /= length
        distance = mujoco.mj_ray(self.m, self.d, origin, direction, None, 1, -1, gid)
        if distance < 0 or distance > reach:
            return None
        body = int(self.m.geom_bodyid[gid[0]])
        point = origin + direction * distance
        while body:
            candidates = [name for name,j in self.joints.items() if self.m.jnt_bodyid[j] == body]
            if candidates:
                return dict(names=candidates, body=body, point=point, distance=float(distance))
            body = int(self.m.body_parentid[body])
        return None

    def grab(self, body, point=None):
        if body not in self.free_bodies:
            raise ValueError("Only declared movable furniture can be picked up")
        point = self.d.xipos[body].copy() if point is None else np.asarray(point, float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError("Grab point must be a finite 3D vector")
        # Validate first: an invalid replacement preserves the existing hold.
        if self.held:
            self.release()
        rotation = self.d.xmat[body].reshape(3, 3)
        local = rotation.T @ (point - self.d.xpos[body])
        self.held = (body, local, point.copy())
        self.grab_target = point.copy()
        self.results[self.m.joint(self.free_bodies[body]).name] = "moving"

    def move_grab(self, target):
        if self.held:
            target=np.asarray(target,float)
            if target.shape != (3,) or not np.all(np.isfinite(target)):
                raise ValueError("Grab target must be a finite 3D vector")
            self.held = (*self.held[:2], target.copy())

    def release(self):
        if self.held:
            self.results[self.m.joint(self.free_bodies[self.held[0]]).name] = "released"
        self.held = self.grab_target = None
        self.clear_forces()

    def update(self):
        self.clear_forces()
        for name, target in list(self.targets.items()):
            j = self.joints[name]
            q, v = int(self.m.jnt_qposadr[j]), int(self.m.jnt_dofadr[j])
            span = float(np.ptp(self.m.jnt_range[j]))
            elapsed = self.d.time - target["time"]
            tolerance = max(0.0001, span * 0.015)
            error = target["value"] - self.d.qpos[q]
            if elapsed > TRAVEL_SECONDS and abs(error) < tolerance and abs(self.d.qvel[v]) < tolerance * 5:
                self.finish(name, 'reached')
                continue
            if elapsed > ACTION_TIMEOUT:
                self.finish(name, 'blocked')
                continue
            kp, _kd, limit = self.gains(j)
            fraction = min(1.0, max(0.0, elapsed/TRAVEL_SECONDS))
            wanted = target["start"] + (target["value"]-target["start"]) * fraction
            effort = kp * (wanted-self.d.qpos[q]) + self.d.qfrc_bias[v]
            self.owned_force[v] = np.clip(effort, -limit, limit)
        if self.held:
            body, local, wanted = self.held
            point = self.d.xpos[body] + self.d.xmat[body].reshape(3,3) @ local
            change = wanted - self.grab_target
            distance = np.linalg.norm(change)
            if distance:
                self.grab_target += change * min(1, GRAB_TARGET_SPEED*self.m.opt.timestep/distance)
            error = self.grab_target - point
            if np.linalg.norm(error) > GRAB_MAX_LAG:
                self.results[self.m.joint(self.free_bodies[body]).name] = "blocked"
                self.held = self.grab_target = None
                self.d.qfrc_applied[:] += self.owned_force
                return
            jac = np.zeros((3, self.m.nv))
            mujoco.mj_jac(self.m, self.d, jac, None, point, body)
            force = GRAB_KP*error - GRAB_KD*(jac @ self.d.qvel)
            force -= self.m.body_mass[body]*self.m.opt.gravity
            norm = np.linalg.norm(force)
            if norm > GRAB_FORCE:
                force *= GRAB_FORCE/norm
            mujoco.mj_applyFT(self.m, self.d, force, np.zeros(3), point, body, self.owned_force)
        self.d.qfrc_applied[:] += self.owned_force


class InspectionPhysics:
    """Step furniture physics while preserving the walkthrough's parked robot."""
    def __init__(self, model, data, interaction, observer=None):
        self.m, self.d, self.interaction = model, data, interaction
        self.observer = observer
        movable = set(interaction.joints.values())
        self.qindices, self.vindices = [], []
        for j in range(model.njnt):
            if j in movable:
                continue
            free = model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
            nq = 7 if free else (4 if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_BALL else 1)
            nv = 6 if free else (3 if nq == 4 else 1)
            self.qindices += list(range(model.jnt_qposadr[j], model.jnt_qposadr[j]+nq))
            self.vindices += list(range(model.jnt_dofadr[j], model.jnt_dofadr[j]+nv))
        self.parked = data.qpos[self.qindices].copy()
        self.accumulated = 0.0

    def advance(self, seconds):
        self.accumulated += seconds
        dt = self.m.opt.timestep
        while self.accumulated >= dt:
            self.interaction.update()
            mujoco.mj_step(self.m, self.d)
            if self.observer is not None:
                self.observer(self.m, self.d)
            self.d.qpos[self.qindices] = self.parked
            self.d.qvel[self.vindices] = 0
            self.accumulated -= dt
        mujoco.mj_forward(self.m, self.d)
