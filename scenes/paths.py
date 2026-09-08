"""Shared inspection points and flat-ground routes, derived from scene declarations.

These describe places to inspect. They do not grant a robot policy the ability to
climb stairs, operate a door, or follow a route autonomously.
"""

from __future__ import annotations
import numpy as np
import mujoco


def _label(en, zh):
    return {"en": en, "zh": zh}


def residence_routes(layout):
    if not hasattr(layout, "ESTATE"):
        return apartment_routes(layout) if hasattr(layout, "FRIDGE_TASK") else []
    areas = {area["name"]: area["rect"] for area in layout.EXTERIOR_AREAS}
    estate = layout.ESTATE
    routes = [
        dict(id=name, label=_label(en, zh), points=[[*point, 0] for point in points])
        for name, en, zh, points in zip(
            ("gate_approach", "pool_approach", "lawn_approach"),
            ("Entrance to gate", "Pool approach", "Lawn approach"),
            ("入户至外大门", "泳池接近路线", "草坪接近路线"),
            estate["routes"],
        )
    ]
    fore, terrace, pool = areas["forecourt"], areas["pool_terrace"], estate["pool"]
    west, side, rear = areas["west_walk"], areas["side_walk"], areas["rear_garden"]
    geoms = {g["name"]: g for g in layout.EXTERIOR_GEOMS}
    coping = geoms["h2_pool_coping1"]
    pool_edge = coping["pos"][0] + coping["size"][0] / 2
    chair_edge = min(
        g["pos"][0] - g["size"][0] / 2
        for name, g in geoms.items()
        if "lounger" in name and name.endswith("frame")
    )
    east_x = (pool_edge + chair_edge) / 2
    front_y = (fore[1] + fore[3]) / 2
    west_x = (terrace[0] + pool[0]) / 2
    south_y = (terrace[1] + pool[1]) / 2
    north_y = (pool[3] + fore[1]) / 2
    junction = (layout.ENTRY_X, front_y)
    walk_west = (west[0] + west[2]) / 2
    walk_east = geoms["h2_house_walk2"]["pos"][0]
    rear_walk = (rear[1] + min(west[3], side[3])) / 2
    rear_y = (rear[1] + rear[3]) / 2
    for name, en, zh, points in (
        (
            "pool_loop",
            "Complete pool circuit",
            "泳池完整环线",
            [
                junction,
                (west_x, front_y),
                (west_x, north_y),
                (west_x, south_y),
                (east_x, south_y),
                (east_x, north_y),
                (west_x, north_y),
            ],
        ),
        (
            "residence_loop",
            "West, rear and east paths",
            "西侧、后侧与东侧步道",
            [
                junction,
                (walk_west, front_y),
                (walk_west, rear_walk),
                (walk_east, rear_walk),
                (walk_east, front_y),
                junction,
            ],
        ),
        (
            "rear_branch",
            "Rear garden branch",
            "后庭支线",
            [
                (walk_west, rear_walk),
                (walk_west, rear_y),
                (walk_east, rear_y),
                (walk_east, rear_walk),
            ],
        ),
    ):
        routes.append(dict(id=name, label=_label(en, zh), points=[[*point, 0] for point in points]))
    return routes


def apartment_routes(L):
    """Initial-state flat routes, with furniture clearances derived from source bounds."""

    def door_between(a, b):
        ra, rb = L.ROOMS[a]["rect"], L.ROOMS[b]["rect"]
        for door in L.DOORS:
            if door.get("floor", 0):
                continue
            horizontal = door["orient"] == "h"
            edge = 1 if horizontal else 0
            cross = 0 if horizontal else 1
            if (
                door["coord"] in (ra[edge], ra[edge + 2])
                and door["coord"] in (rb[edge], rb[edge + 2])
                and max(ra[cross], rb[cross]) < door["center"] < min(ra[cross + 2], rb[cross + 2])
            ):
                return door
        raise ValueError(f"No ground-floor doorway between {a} and {b}")

    def bounds(prefix):
        lows = []
        highs = []
        for item in L.FURNITURE:
            if not item["name"].startswith(prefix):
                continue
            matrix = np.empty(9)
            mujoco.mju_quat2Mat(matrix, np.array(item.get("quat", (1, 0, 0, 0)), float))
            extent = np.abs(matrix.reshape(3, 3)) @ (np.array(item["size"]) / 2)
            lows.append(np.array(item["pos"]) - extent)
            highs.append(np.array(item["pos"]) + extent)
        return np.min(lows, axis=0), np.max(highs, axis=0)

    entry = door_between("foyer", "gallery")
    living = door_between("gallery", "great_room")
    dining = door_between("great_room", "dining")
    stair = door_between("gallery", "stair_f62")
    kitchen = door_between("stair_f62", "kitchen")
    sofa_low, _ = bounds("gr_sofa")
    stool_low, _ = bounds("kt_st")
    gallery = L.ROOMS["gallery"]["rect"]
    center = (entry["center"], (gallery[1] + gallery[3]) / 2)
    front = (living["coord"] + sofa_low[1]) / 2
    west = (L.ROOMS["great_room"]["rect"][0] + sofa_low[0]) / 2
    # Stop just inside the doorway, retaining the validated standing/turning
    # clearance from dining chairs even with the walking policy's overshoot.
    dining_x = dining["coord"] - L.WALL_THICK
    landing = next(p for p in L.LANDINGS if p["name"] == "stair0_mid")
    wall = next(p for p in L.WELL_WALLS if p["name"] == "stair_well_wall")
    north = (
        wall["pos"][1] + wall["size"][1] / 2 + L.ROOMS["stair_f62"]["rect"][3] - L.WALL_THICK
    ) / 2
    kitchen_y = (L.ROOMS["kitchen"]["rect"][1] + stool_low[1]) / 2
    living_points = [center, (living["center"], front), (west, front), (west, dining["center"])]
    routes = (
        (
            "entry_gallery",
            "Entrance and gallery",
            "玄关与画廊",
            [L.ROBOT_HOME_XY, center, (entry["center"], entry["coord"]), L.START_POS_XY],
        ),
        (
            "living_dining",
            "Living and dining access",
            "客厅与餐厅通道",
            [L.ROBOT_HOME_XY, *living_points, (dining_x, dining["center"])],
        ),
        (
            "kitchen_access",
            "Kitchen ground-floor access",
            "厨房平层通道",
            [
                L.ROBOT_HOME_XY,
                center,
                (stair["coord"], stair["center"]),
                (landing["pos"][0], stair["center"]),
                (landing["pos"][0], north),
                (kitchen["center"], north),
                (kitchen["center"], kitchen["coord"]),
                (kitchen["center"], kitchen_y),
            ],
        ),
    )
    return [
        dict(
            id=name,
            label=_label(en, zh),
            points=[[float(x), float(y), L.FLOOR_Z(0)] for x, y in points],
        )
        for name, en, zh, points in routes
    ]


def inspection_points(layout):
    points = []
    for index, door in enumerate(layout.DOORS):
        floor = door.get("floor", 0)
        x, y = (
            (door["center"], door["coord"])
            if door["orient"] == "h"
            else (door["coord"], door["center"])
        )
        z = layout.FLOOR_Z(floor)
        # Resolve adjacent room labels on opposite sides of the wall centerline.
        offset = layout.WALL_THICK
        candidates = (
            ((x, y - offset), (x, y + offset))
            if door["orient"] == "h"
            else ((x - offset, y), (x + offset, y))
        )
        rooms = list(
            dict.fromkeys(filter(None, (layout.room_at(px, py, z) for px, py in candidates)))
        )
        zh = " / ".join(layout.ROOMS[room]["label"] for room in rooms if room in layout.ROOMS)
        points.append(
            dict(
                id=f"passage_{floor}_{index}",
                label=_label(f"Doorway {index + 1}", f"门洞：{zh}" if zh else f"门洞 {index + 1}"),
                floor=floor,
                room=rooms[0] if rooms else None,
                kind="boundary",
                anchor=[x, y, z],
                operations=[],
                description=_label(
                    "An authored room opening; this is a passage checkpoint, not an operable door leaf.",
                    "房间通道检查点；此处不代表可操作的门扇。",
                ),
                test=_label(
                    "Inspect both sides, check the clear opening and floor continuity before entering.",
                    "通行前查看门洞两侧，检查净宽与地面连续性。",
                ),
            )
        )
    for floor in range(layout.N_FLOORS):
        anchor = (
            layout.stair_route(floor)[0]
            if floor < layout.N_FLOORS - 1
            else layout.stair_route(floor - 1)[-1]
        )
        points.append(
            dict(
                id=f"stairs_stop_{floor}",
                label=_label(f"Floor {floor + 1} stair stop", f"{floor + 1}层楼梯停止检查点"),
                floor=floor,
                room=layout.room_at(*anchor),
                kind="boundary",
                anchor=list(anchor),
                operations=[],
                description=_label(
                    "Stop before the stair flight. G1 stair climbing is not validated.",
                    "在梯段前停止。G1 上下楼能力尚未验证。",
                ),
                test=_label(
                    "Inspect the landing, first step and guardrail while remaining on the level floor.",
                    "停留在平层地面，检查平台、首级踏步与护栏。",
                ),
            )
        )
    for route in residence_routes(layout):
        points.append(
            dict(
                id="route_" + route["id"],
                label=route["label"],
                floor=0,
                room=None,
                kind="boundary",
                anchor=route["points"][0],
                points=route["points"],
                operations=[],
                description=_label(
                    "An initial-state flat-ground inspection route; check again after moving furniture.",
                    "初始家具状态下的平地通行检查路线；移动家具后需重新检查。",
                ),
                test=_label(
                    "Check ground support, obstacles and pool edges along the route; this is not an autonomous navigation command.",
                    "沿线检查地面承托、障碍与池沿；此项不执行自主导航。",
                ),
            )
        )
    return points
