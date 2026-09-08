"""World-owned display and operator metadata, derived from actual scene geometry."""

from __future__ import annotations

import itertools
import re
import numpy as np
import mujoco
from decor import lock

from scenes import manifest
from scenes.paths import inspection_points, residence_routes

SCENE_LABELS = {
    "apt": {"en": "Manhattan duplex", "zh": "曼哈顿复式公寓"},
    "house": {"en": "Hillside residence", "zh": "山坡住宅"},
}
FIXTURE_LABELS = {
    "rc_fridge": {"en": "Refrigerator", "zh": "冰箱"},
    "rc_sink": {"en": "Kitchen sink", "zh": "厨房水槽"},
    "rc_stove": {"en": "Stove", "zh": "炉灶"},
    "rc_hood": {"en": "Range hood", "zh": "油烟机"},
    "plant_a": {"en": "Potted plant", "zh": "盆栽"},
    "plant_b": {"en": "Potted plant", "zh": "盆栽"},
}
ROOM_EN = {
    "great_room": "Double-height living room",
    "guest_bed": "Guest bedroom",
    "guest_bath": "Guest bathroom",
    "primary_bed": "Primary bedroom",
    "primary_bath": "Primary bathroom",
    "media": "Media room",
    "sitting": "Sitting room",
    "terrace_room": "Sunroom",
    "robot_home": "Robot parking room",
    "guest": "Guest room",
    "entry": "Entrance hall",
    "family_room": "Garden living room",
    "garden_room": "Recreation room",
    "bedroom_w": "West bedroom",
    "lobby0": "Stair hall",
    "lobby1": "Second-floor hall",
    "lobby2": "View hall",
    "master_bath": "Primary bathroom",
    "forecourt": "Entrance courtyard",
    "front_lawn": "Front lawn",
    "side_walk": "Side walk",
    "pool_terrace": "Pool terrace",
    "rear_garden": "Rear garden",
    "west_walk": "West walk",
}


def label(en, zh):
    return {"en": en, "zh": zh}


def corners(bounds):
    low, high = np.asarray(bounds, dtype=float)
    return np.array(list(itertools.product(*zip(low, high))))


class Geometry:
    """Cached local geometry bounds, transformed with current MjData on demand."""

    def __init__(self, model, data):
        self.m, self.d = model, data
        self.local = []
        for gid in range(model.ngeom):
            kind, size = int(model.geom_type[gid]), model.geom_size[gid]
            if kind == mujoco.mjtGeom.mjGEOM_MESH:
                mid = model.geom_dataid[gid]
                start, count = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
                vertices = model.mesh_vert[start : start + count]
                bounds = (vertices.min(axis=0), vertices.max(axis=0))
            else:
                extent = size.copy()
                if kind == mujoco.mjtGeom.mjGEOM_SPHERE:
                    extent[:] = size[0]
                elif kind in (mujoco.mjtGeom.mjGEOM_CAPSULE, mujoco.mjtGeom.mjGEOM_CYLINDER):
                    extent[:] = (
                        size[0],
                        size[0],
                        size[1] + (size[0] if kind == mujoco.mjtGeom.mjGEOM_CAPSULE else 0),
                    )
                bounds = (-extent, extent)
            self.local.append(corners(bounds))

    def points(self, ids):
        return np.concatenate(
            [self.local[g] @ self.d.geom_xmat[g].reshape(3, 3).T + self.d.geom_xpos[g] for g in ids]
        )

    def bounds(self, ids):
        p = self.points(ids)
        return np.stack((p.min(axis=0), p.max(axis=0)))

    def bounds_in_frame(self, ids, origin, rotation):
        """Exact primitive support extents and real mesh vertices in a target frame."""
        lows = []
        highs = []
        for g in ids:
            transform = rotation.T @ self.d.geom_xmat[g].reshape(3, 3)
            center = rotation.T @ (self.d.geom_xpos[g] - origin)
            kind = int(self.m.geom_type[g])
            size = self.m.geom_size[g]
            if kind == mujoco.mjtGeom.mjGEOM_MESH:
                mid = self.m.geom_dataid[g]
                start = self.m.mesh_vertadr[mid]
                count = self.m.mesh_vertnum[mid]
                points = self.m.mesh_vert[start : start + count] @ transform.T + center
                lows.append(points.min(axis=0))
                highs.append(points.max(axis=0))
                continue
            if kind == mujoco.mjtGeom.mjGEOM_SPHERE:
                extent = np.repeat(size[0], 3)
            elif kind == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
                extent = np.sqrt(np.sum((transform * size) ** 2, axis=1))
            elif kind == mujoco.mjtGeom.mjGEOM_CYLINDER:
                axis = transform[:, 2]
                extent = size[0] * np.sqrt(np.maximum(0, 1 - axis * axis)) + size[1] * np.abs(axis)
            elif kind == mujoco.mjtGeom.mjGEOM_CAPSULE:
                extent = size[0] + size[1] * np.abs(transform[:, 2])
            else:
                extent = np.abs(transform) @ size
            lows.append(center - extent)
            highs.append(center + extent)
        return np.stack((np.min(lows, axis=0), np.max(highs, axis=0)))

    def body_geoms(self, bid, recursive=False, collision=False):
        bodies = {bid}
        if recursive:
            for child in range(bid + 1, self.m.nbody):
                if int(self.m.body_parentid[child]) in bodies:
                    bodies.add(child)
        return [
            g
            for g in range(self.m.ngeom)
            if int(self.m.geom_bodyid[g]) in bodies
            and (not collision or self.m.geom_contype[g] or self.m.geom_conaffinity[g])
        ]


class Catalogue:
    def __init__(self, model, data, scene_key, interaction):
        self.m, self.d, self.key, self.ix = model, data, scene_key, interaction
        self.layout = manifest.load_layout(scene_key)
        self.geometry = Geometry(model, data)
        self.facility_geoms = {}
        self.templates = []
        self.rooms = []
        L = self.layout
        for key, room in L.ROOMS.items():
            floor = room.get("floor", 0)
            x0, y0, x1, y1 = room["rect"]
            z = L.FLOOR_Z(floor)
            self.rooms.append(
                dict(
                    id=key,
                    label=label(
                        ROOM_EN.get(
                            key,
                            "Stairwell"
                            if key.startswith("stair_")
                            else key.replace("_", " ").title(),
                        ),
                        room["label"],
                    ),
                    floor=floor,
                    bounds=[[x0, y0, z], [x1, y1, z + L.WALL_HEIGHT]],
                )
            )
        for area in getattr(L, "EXTERIOR_AREAS", []):
            x0, y0, x1, y1 = area["rect"]
            z = area.get("floor_z", 0)
            self.rooms.append(
                dict(
                    id=area["name"],
                    label=label(
                        ROOM_EN.get(area["name"], area["name"].replace("_", " ").title()),
                        area["label"],
                    ),
                    floor=L.floor_at(z),
                    exterior=True,
                    bounds=[[x0, y0, z], [x1, y1, z + L.WALL_HEIGHT]],
                )
            )
        if hasattr(L, "ESTATE"):
            x0, y0, x1, y1 = L.ESTATE["pool"]
            self.rooms.append(
                dict(
                    id="swimming_pool",
                    label=label("Swimming pool", "泳池"),
                    floor=0,
                    exterior=True,
                    bounds=[[x0, y0, -L.ESTATE["pool_depth"]], [x1, y1, 0]],
                )
            )
        items = {"ix_" + item["name"]: item for item in L.FURNITURE}
        for name, jid in interaction.joints.items():
            bid = int(model.jnt_bodyid[jid])
            body = model.body(bid).name
            root_name = body.split("__")[0]
            item = items.get(root_name, {})
            free = model.jnt_type[jid] == mujoco.mjtJoint.mjJNT_FREE
            facility_id = body if free else name
            ids = self.geometry.body_geoms(bid, recursive=True)
            suffix = (
                root_name.removeprefix("ix_a2_")
                if free
                else name.split("__")[-1].removesuffix("_joint")
            )
            en = suffix.replace("_", " ").title()
            zh = {
                "can": "罐体",
                "fruit": "水果",
                "book": "书本",
                "fridge_door": "冷藏室门",
                "freezer_door": "冷冻室门",
            }.get(suffix, "餐椅" if free else en)
            if free and root_name.startswith("ix_dn_"):
                table = next(source for source in L.FURNITURE if source["name"] == "dn_table_top")
                west = item["pos"][0] < table["pos"][0]
                peers = sorted((source for source in L.FURNITURE
                                if source.get("movable") and source["name"].startswith("dn_")
                                and (source["pos"][0] < table["pos"][0]) == west),
                               key=lambda source: source["pos"][1])
                ordinal = next(i+1 for i,source in enumerate(peers) if source["name"] == item["name"])
                en = ("West" if west else "East") + f" dining chair {ordinal}"
                zh = ("西侧" if west else "东侧") + f"餐椅 {ordinal}"
            if not free:
                number = re.search(r"(\d+)", suffix)
                ordinal = (
                    str(int(number.group(1)) + (1 if "drawer" in suffix else 0)) if number else ""
                )
                if "drawer" in suffix:
                    en = (
                        ("Freezer" if "freezer" in suffix else "Refrigerator")
                        + " drawer "
                        + ordinal
                    )
                    zh = ("冷冻室" if "freezer" in suffix else "冷藏室") + "抽屉 " + ordinal
                elif "stove" in root_name:
                    positions = {
                        "front_left": ("Front-left burner control", "左前炉灶旋钮"),
                        "front_right": ("Front-right burner control", "右前炉灶旋钮"),
                        "rear_left": ("Rear-left burner control", "左后炉灶旋钮"),
                        "rear_right": ("Rear-right burner control", "右后炉灶旋钮"),
                    }
                    en, zh = (
                        ("Oven door", "烤箱门")
                        if "door" in suffix.lower()
                        else (
                            ("Oven rack", "烤箱搁架")
                            if "shelf" in suffix.lower()
                            else positions.get(
                                suffix.removeprefix("knob_"),
                                ("Oven control " + ordinal, "烤箱旋钮 " + ordinal),
                            )
                        )
                    )
                elif "hood" in root_name:
                    en, zh = "Hood button " + ordinal, "油烟机按钮 " + ordinal
                elif "sink" in root_name:
                    en, zh = (
                        ("Water-temperature lever", "水温调节柄")
                        if "temp" in suffix
                        else (
                            ("Swivel spout", "水龙头转动出水管")
                            if "spout" in suffix
                            else ("Tap lever", "水龙头开关柄")
                        )
                    )
            template = dict(
                id=facility_id,
                label=label(en, zh),
                room=item.get("room"),
                floor=0,
                kind="movable" if free else "joint",
                body=body,
                operations=["grab", "release"] if free else ["joint"],
                description=label(
                    "A physical movable object."
                    if free
                    else "A physical appliance joint; this does not simulate the appliance's electrical or fluid function.",
                    "具有重力与碰撞的可搬物。"
                    if free
                    else "具有真实行程与碰撞的电器关节；不模拟电器的电气或流体功能。",
                ),
                test=label(
                    "Lift, release and check the resting position."
                    if free
                    else "Move to both limits; an obstruction must stop travel.",
                    "抬起并释放，检查物体落稳位置。"
                    if free
                    else "测试两端行程；遇到障碍时应停止。",
                ),
            )
            if not free:
                template["joint"] = name
                template["range"] = model.jnt_range[jid].tolist()
                if "drawer" in suffix or "shelf" in suffix.lower():
                    template["test"] = label(
                        "Open the enclosing door, pull the drawer or rack fully out, then push it back. With the door closed, inspect contact and any door movement.",
                        "先打开外门，再将抽屉或搁架完全拉出并推回；外门关闭时，检查接触阻挡及门是否被顶开。",
                    )
                elif "door" in suffix.lower():
                    template["test"] = label(
                        "Open fully and close. Check that the visible door and handle move together and stop when obstructed.",
                        "完全打开后再关闭，检查门板与把手同步运动，以及遇到障碍时的停止情况。",
                    )
                elif "button" in suffix.lower():
                    template["test"] = label(
                        "Press to the limited stroke and release. Check physical travel only; fan operation is not simulated.",
                        "按至行程末端后释放，只检查实体行程；不模拟风机工作。",
                    )
                else:
                    template["test"] = label(
                        "Rotate through the declared range and cancel midway; verify the measured joint position and that applied force ends.",
                        "在标定范围内转动并中途取消，核对实际关节位置与施力结束情况。",
                    )
            self.templates.append(template)
            self.facility_geoms[facility_id] = ids
        for seat in getattr(L, "SEATS", []):
            room = L.ROOMS[seat["room"]]
            x, y = seat["at"]
            self.templates.append(
                dict(
                    id="seat_" + seat["name"],
                    label=label("Seating area", "座位"),
                    room=seat["room"],
                    floor=room.get("floor", 0),
                    kind="pose",
                    anchor=[x, y, L.FLOOR_Z(room.get("floor", 0)) + 0.35],
                    operations=[],
                    description=label(
                        "Seating geometry; no autonomous sitting policy is provided.",
                        "可坐区域；不提供自主坐下策略。",
                    ),
                    test=label("Inspect clearance and seat support.", "查看净空与座面支撑。"),
                )
            )
        geom_names = {model.geom(g).name: g for g in range(model.ngeom)}
        for item in L.FURNITURE:
            if not item.get("mesh") or item.get("movable") or item.get("articulated"):
                continue
            name = item["name"]
            ids = [
                g
                for n, g in geom_names.items()
                if n
                and (
                    n == "furn_" + name
                    or n.startswith("dg_" + name + "_")
                    or n.startswith("hc_" + name + "_")
                )
            ]
            if not ids:
                continue
            key = item["mesh"]["id"]
            self.templates.append(
                dict(
                    id=name,
                    label=FIXTURE_LABELS.get(
                        key,
                        label(
                            key.removeprefix("rc_").replace("_", " ").title(),
                            lock.load()[key].get("label", key),
                        ),
                    ),
                    room=item.get("room"),
                    floor=0,
                    kind="static",
                    operations=[],
                    description=label(
                        "Fixed furnishing with its authored geometry.", "按场景设计固定放置的家具。"
                    ),
                    test=label(
                        "Inspect the shape and surrounding clearance.", "查看家具外形与周边净空。"
                    ),
                )
            )
            self.facility_geoms[name] = ids
        if hasattr(L, "ESTATE"):
            estate = L.ESTATE
            for key, title, xy, text_en, text_zh in (
                (
                    "estate_gate",
                    label("Estate gate", "宅地外门"),
                    estate["gate_center"],
                    "Fixed closed collision boundary. The road beyond is background.",
                    "固定关闭的碰撞边界；门外道路仅作背景。",
                ),
                (
                    "swimming_pool",
                    label("Swimming pool", "泳池"),
                    [
                        (estate["pool"][0] + estate["pool"][2]) / 2,
                        (estate["pool"][1] + estate["pool"][3]) / 2,
                    ],
                    "Recessed basin with physical walls and floor. Water is visual and does not support weight.",
                    "池壁与池底具有真实碰撞；水面仅供显示，不承重。",
                ),
            ):
                self.templates.append(
                    dict(
                        id=key,
                        label=title,
                        room=None,
                        floor=0,
                        kind="boundary",
                        anchor=[*xy, 0],
                        operations=[],
                        description=label(text_en, text_zh),
                        test=label(
                            "Inspect the physical boundary and surrounding route.",
                            "查看物理边界与周边路线。",
                        ),
                    )
                )
                prefixes = (
                    ("h2_estate_gate", "h2_gate_frame", "h2_gate_slats", "h2_gate_pier")
                    if key == "estate_gate"
                    else (
                        "h2_pool_bottom",
                        "h2_pool_wall",
                        "h2_pool_step",
                        "h2_pool_water",
                        "h2_pool_coping",
                    )
                )
                self.facility_geoms[key] = [
                    g for n, g in geom_names.items() if n and n.startswith(prefixes)
                ]
        self.templates.extend(inspection_points(L))

    def get(self):
        out = []
        for source in self.templates:
            item = dict(source)
            ids = self.facility_geoms.get(item["id"])
            if ids:
                bounds = self.geometry.bounds(ids)
                item["bounds"] = bounds.tolist()
                item["anchor"] = bounds.mean(axis=0).tolist()
                x, y, z = item["anchor"]
                item["floor"] = self.layout.floor_at(z)
                room = self.layout.room_at(x, y, z)
                if room is not None:
                    item["room"] = room
            out.append(item)
        def floor_label(floor):
            en = f"Floor {floor+1}"
            zh = ("一", "二", "三")[floor] + "层"
            if hasattr(self.layout,"FLOOR_LEVEL"):
                level = self.layout.FLOOR_LEVEL + floor
                en += f" / {level}F"
                zh += f"／{level}F"
            return label(en,zh)

        return dict(
            scene=self.key,
            label=SCENE_LABELS[self.key],
            floors=[
                dict(id=f, label=floor_label(f), z=self.layout.FLOOR_Z(f))
                for f in range(self.layout.N_FLOORS)
            ],
            rooms=self.rooms,
            facilities=out,
            routes=residence_routes(self.layout),
        )
