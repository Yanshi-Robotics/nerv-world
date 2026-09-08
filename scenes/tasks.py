"""Measured task predicates; evaluation never drives or teleports an object."""

from __future__ import annotations
import numpy as np
import mujoco

from scenes.catalogue import label, corners

SETTLE_SECONDS = 0.5  # Sustained simulated rest, avoiding transient in-volume crossings.
LINEAR_SPEED = 0.05  # m/s, below deliberate placement motion.
ANGULAR_SPEED = 0.2  # rad/s, excludes a spinning or tumbling object.
DOOR_CLOSED = 0.04  # Soft joint stops have finite compliance.
DOOR_OPEN = 0.65  # A visibly open, usable aperture.
CONTAINMENT_TOLERANCE = 0.002  # 2 mm contact compliance at the supporting shelf.
MAX_PENETRATION = 0.01  # Same 1 cm rejection bound as check_interactions.py.
SUPPORT_NORMAL = 0.5  # Support normal within 60 degrees of upward.
SUPPORT_LOAD_FRACTION = 0.1  # Reject a merely touching, unloaded contact.
SHELF_MIN_HALF_WIDTH = 0.1  # Reject small door hardware when locating shelf boxes.
SHELF_MAX_HALF_THICKNESS = 0.012  # The calibrated refrigerator uses thin horizontal shelves.


class FridgeTask:
    def __init__(self, model, data, interaction, geometry, config):
        self.m, self.d, self.ix, self.geometry = model, data, interaction, geometry
        self.object = model.body(config["object"]).id
        self.container = model.body(config["container"]).id
        self.door = config["door"]
        self.target_label = config["target_label"]
        self.object_geoms = geometry.body_geoms(self.object, recursive=True)
        self.object_geom_set = set(self.object_geoms)
        # Named source collision parts refer to the calibrated Refrigerator031 shell.
        # Select horizontal shelves geometrically, not by incidental collision index.
        ids = geometry.body_geoms(self.container, collision=True)
        boxes = [
            (g, model.geom_pos[g], model.geom_size[g])
            for g in ids
            if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX
        ]
        side = 1 if config["compartment"] == "right" else -1
        shelves = sorted(
            [
                (g, p, s)
                for g, p, s in boxes
                if side * p[0] > s[0] / 2
                and s[0] > SHELF_MIN_HALF_WIDTH
                and s[1] > SHELF_MIN_HALF_WIDTH
                and s[2] < SHELF_MAX_HALF_THICKNESS
            ],
            key=lambda b: b[1][2],
        )
        rank = config["shelf_rank"]
        if len(shelves) != config["shelf_count"] or not 0 <= rank < len(shelves) - 1:
            raise ValueError("Review refrigerator task volume after changing its shelves")
        lower, upper = shelves[rank], shelves[rank + 1]
        self.support_geom = lower[0]
        p, s = lower[1:]
        # The fixed shelf footprint is already inside the cavity. Constrain it
        # further by the tall divider, side wall and back wall.
        low, high = p - s, p + s
        low[2], high[2] = p[2] + s[2], upper[1][2] - upper[2][2]
        for _, center, half in boxes:
            if half[2] > (high[2] - low[2]):
                if center[0] < p[0] and center[1] - half[1] < p[1] < center[1] + half[1]:
                    low[0] = max(low[0], center[0] + half[0])
                if center[0] > p[0] and center[1] - half[1] < p[1] < center[1] + half[1]:
                    high[0] = min(high[0], center[0] - half[0])
                if center[1] > p[1] and center[0] - half[0] < p[0] < center[0] + half[0]:
                    high[1] = min(high[1], center[1] - half[1])
        if np.any(high <= low):
            raise ValueError("Refrigerator task volume is empty")
        self.volume = np.stack((low, high))
        self.reset()

    def reset(self):
        self.opened = False
        self.valid_contacts = True
        self.stable_since = None
        self.state = {
            "id": "put_can_in_fridge",
            "label": label("Put the can in the refrigerator", "将罐体放入冰箱"),
            "supported": True,
            "stage": "open_door",
            "success": False,
            "checks": {},
            "target": self.target(),
        }

    def target(self):
        world = (
            corners(self.volume) @ self.d.xmat[self.container].reshape(3, 3).T
            + self.d.xpos[self.container]
        )
        return dict(
            body=self.m.body(self.container).name,
            bounds=self.volume.tolist(),
            frame="body",
            label=self.target_label,
            world_bounds=[world.min(axis=0).tolist(), world.max(axis=0).tolist()],
            world_anchor=world.mean(axis=0).tolist(),
        )

    def observe_contacts(self):
        """Cheap per-physics-step latch; full containment/support runs at UI rate."""
        if not self.valid_contacts:
            return
        for contact in self.d.contact:
            if contact.dist < -MAX_PENETRATION and (
                int(contact.geom1) in self.object_geom_set
                or int(contact.geom2) in self.object_geom_set
            ):
                self.valid_contacts = False
                return

    def update(self, publish=True):
        fraction = self.ix.status(self.door)["fraction"]
        self.opened |= fraction >= DOOR_OPEN
        rotation = self.d.xmat[self.container].reshape(3, 3)
        bounds = self.geometry.bounds_in_frame(
            self.object_geoms, self.d.xpos[self.container], rotation
        )
        inside = bool(
            np.all(bounds[0] >= self.volume[0] - CONTAINMENT_TOLERANCE)
            and np.all(bounds[1] <= self.volume[1] + CONTAINMENT_TOLERANCE)
        )
        released = not (self.ix.held and self.ix.held[0] == self.object)
        j = self.ix.free_bodies[self.object]
        v = self.m.jnt_dofadr[j]
        quiet = bool(
            np.linalg.norm(self.d.qvel[v : v + 3]) <= LINEAR_SPEED
            and np.linalg.norm(self.d.qvel[v + 3 : v + 6]) <= ANGULAR_SPEED
        )
        supported = False
        upward = rotation[:, 2]
        minimum_load = (
            SUPPORT_LOAD_FRACTION
            * self.m.body_mass[self.object]
            * np.linalg.norm(self.m.opt.gravity)
        )
        for index, contact in enumerate(self.d.contact):
            one, two = int(contact.geom1), int(contact.geom2)
            if one not in self.object_geoms and two not in self.object_geoms:
                continue
            if contact.dist < -MAX_PENETRATION:
                self.valid_contacts = False
            normal = contact.frame[:3] if one == self.support_geom else -contact.frame[:3]
            if self.support_geom in (one, two) and normal @ upward >= SUPPORT_NORMAL:
                force = np.zeros(6)
                mujoco.mj_contactForce(self.m, self.d, index, force)
                supported |= force[0] >= minimum_load
        if inside and released and quiet and supported and self.valid_contacts:
            if self.stable_since is None:
                self.stable_since = float(self.d.time)
        else:
            self.stable_since = None
        if not publish:
            return
        settled = (
            self.stable_since is not None and self.d.time - self.stable_since >= SETTLE_SECONDS
        )
        closed = bool(fraction <= DOOR_CLOSED)
        checks = dict(
            opened=bool(self.opened),
            inside=inside,
            released=bool(released),
            settled=bool(settled),
            supported=bool(supported),
            contact_valid=bool(self.valid_contacts),
            closed=closed,
        )
        success = all(checks.values())
        stage = (
            "complete"
            if success
            else "invalid_contact"
            if not self.valid_contacts
            else "open_door"
            if not self.opened
            else "place_object"
            if not inside
            else "release_object"
            if not released
            else "wait_until_settled"
            if not settled
            else "close_door"
        )
        self.state.update(stage=stage, success=success, checks=checks, target=self.target())
        return self.state
