"""Furnish the duplex's service rooms without obstructing their shared door routes.

Fixtures here are static. Kitchen articulation lives in interactivity.py.
All heights are relative to the room floor; the scene generator adds its elevation.
"""

import math

from scenes import furniture as F

WALL_GAP = 0.04  # Clearance between cabinet backs and finished walls, metres.
WARDROBE_DEPTH = 0.60
WARDROBE_HEIGHT = 2.30
ENTRY_APRON = 0.80  # Leave the dressing-room door and its turning space clear.
STORAGE_DEPTH = 0.55
STORAGE_END_GAPS = (0.50, 0.85)  # South/north setbacks; the north end has a doorway.
MACHINE_SIZE = (0.65, 0.65, 0.90)
MACHINE_GAP = 0.10
TUB_SIZE = (0.95, 1.95)
TUB_WALL = 0.09
TUB_BOTTOM_TOP = 0.14
TUB_RIM_TOP = 0.62
SHOWER_SIZE = (1.30, 1.40)
SHOWER_NORTH_GAP = 0.65  # Clears the dressing-room doorway at the north wall.


def furnish(layout, b):
    out = []
    t = layout.WALL_THICK
    x0, y0, x1, y1 = layout.ROOMS["dressing"]["rect"]
    start, end = x0 + t + ENTRY_APRON, x1 - t - WALL_GAP
    for side, y, yaw in (
        ("north", y1 - t - WALL_GAP - WARDROBE_DEPTH / 2, 0),
        ("south", y0 + t + WALL_GAP + WARDROBE_DEPTH / 2, 180),
    ):
        out += b.cabinet(
            "dressing_" + side,
            "dressing",
            (start + end) / 2,
            y,
            end - start,
            WARDROBE_DEPTH,
            WARDROBE_HEIGHT,
            yaw,
        )
    x0, y0, x1, y1 = layout.ROOMS["closet"]["rect"]
    start, end = y0 + t + STORAGE_END_GAPS[0], y1 - t - STORAGE_END_GAPS[1]
    out += b.cabinet(
        "storage",
        "closet",
        x0 + t + WALL_GAP + STORAGE_DEPTH / 2,
        (start + end) / 2,
        end - start,
        STORAGE_DEPTH,
        2.20,
        90,
    )

    x0, y0, x1, y1 = layout.ROOMS["laundry"]["rect"]
    width, depth, height = MACHINE_SIZE
    cx, cy = (x0 + x1) / 2, y0 + t + WALL_GAP + depth / 2
    # The door cylinders face +y; the appliances are closed, static fixtures.
    face_quat = (math.sqrt(0.5), -math.sqrt(0.5), 0, 0)
    for i, name in enumerate(("washer", "dryer")):
        x = cx + (i - 0.5) * (width + MACHINE_GAP)
        out.append(
            b.box(
                name + "_body",
                (x, cy, height / 2),
                MACHINE_SIZE,
                "white",
                room="laundry",
                radius=0.03,
            )
        )
        for tag, radius, offset, mat in (
            ("ring", 0.23, 0.012, "metal"),
            ("window", 0.18, 0.025, "glass"),
        ):
            part = F._p(
                "a2_" + name + "_" + tag,
                "laundry",
                "cylinder",
                (x, cy + depth / 2 + offset, 0.44),
                (radius * 2, radius * 2, 0.014),
                (1, 1, 1, 1),
                mat="a2_" + mat,
            )
            part["quat"] = face_quat
            part["collide"] = False
            out.append(part)
        out.append(
            b.box(
                name + "_controls",
                (x, cy + depth / 2 + 0.012, 0.78),
                (0.49, 0.016, 0.085),
                "metal",
                room="laundry",
                collide=False,
            )
        )
    out.append(
        b.box(
            "laundry_counter",
            (cx, cy, height + 0.025),
            (2 * width + MACHINE_GAP + 0.08, depth + 0.05, 0.05),
            "stone",
            room="laundry",
        )
    )

    for room, offset_from_south, yaw in (("guest_bath", 1.80, -90), ("primary_bath", 1.30, 90)):
        x0, y0, x1, y1 = layout.ROOMS[room]["rect"]
        x = x0 + t + 0.45 if yaw < 0 else x1 - t - 0.45
        y = y0 + offset_from_south
        parts = (
            ("base", 0, 0.135, (0.30, 0.43, 0.27)),
            ("bowl", 0.035, 0.320, (0.38, 0.58, 0.30)),
            ("seat", 0.05, 0.4875, (0.42, 0.62, 0.035)),
            ("lid", 0.05, 0.5225, (0.40, 0.60, 0.035)),
            ("tank", -0.255, 0.520, (0.38, 0.17, 0.38)),
        )
        for tag, dy, z, size in parts:
            dx, dy = F._rot(0, dy, yaw)
            out.append(
                b.box(
                    room + "_wc_" + tag,
                    (x + dx, y + dy, z),
                    size,
                    "ceramic",
                    room=room,
                    radius=0.025,
                    yaw=yaw,
                )
            )
        mirror = b.box(
            room + "_mirror",
            ((x0 + x1) / 2, y0 + t + 0.025, 1.70),
            (1.40, 0.018, 1.10),
            "metal",
            room=room,
            radius=0.006,
            collide=False,
        )
        mirror["mat"] = "mat_mirror"
        out.append(mirror)

    room = "primary_bath"
    x0, y0, x1, y1 = layout.ROOMS[room]["rect"]
    width, length = TUB_SIZE
    x, y = x0 + t + WALL_GAP + width / 2, (y0 + y1) / 2
    base = b.box(
        "primary_tub_base", (x, y, 0.09), (width, length, 0.10), "ceramic", room=room, radius=0.02
    )
    base["enclosed_fixture"] = True
    out.append(base)
    wall_height = TUB_RIM_TOP - TUB_BOTTOM_TOP
    for tag, dx, dy, size in (
        ("w", -(width - TUB_WALL) / 2, 0, (TUB_WALL, length, wall_height)),
        ("e", (width - TUB_WALL) / 2, 0, (TUB_WALL, length, wall_height)),
        ("s", 0, -(length - TUB_WALL) / 2, (width - 2 * TUB_WALL, TUB_WALL, wall_height)),
        ("n", 0, (length - TUB_WALL) / 2, (width - 2 * TUB_WALL, TUB_WALL, wall_height)),
    ):
        out.append(
            b.box(
                "primary_tub_" + tag,
                (x + dx, y + dy, (TUB_RIM_TOP + TUB_BOTTOM_TOP) / 2),
                size,
                "ceramic",
                room=room,
                radius=0.025,
            )
        )
    right, top = x1 - t - WALL_GAP, y1 - t - SHOWER_NORTH_GAP
    left, bottom = right - SHOWER_SIZE[0], top - SHOWER_SIZE[1]
    for tag, pos, size in (
        ("west", (left, (top + bottom) / 2, 1.04), (0.03, SHOWER_SIZE[1], 2.08)),
        ("north", ((left + right) / 2, top, 1.04), (SHOWER_SIZE[0], 0.03, 2.08)),
    ):
        out.append(b.box("primary_shower_" + tag, pos, size, "glass", room=room, radius=0))
    out.append(
        b.box(
            "primary_shower_floor",
            ((left + right) / 2, (bottom + top) / 2, 0.006),
            (*SHOWER_SIZE, 0.008),
            "stone",
            room=room,
            collide=False,
            radius=0,
        )
    )
    out.append(
        b.box(
            "primary_shower_riser",
            (right - 0.03, (top + bottom) / 2, 1.45),
            (0.03, 0.03, 1.10),
            "metal",
            room=room,
            collide=False,
        )
    )
    out.append(
        b.box(
            "primary_shower_head",
            (right - 0.18, (top + bottom) / 2, 2.02),
            (0.34, 0.24, 0.035),
            "metal",
            room=room,
            collide=False,
        )
    )

    x0, y0, x1, y1 = layout.ROOMS["foyer"]["rect"]
    door = layout.FRONT_DOOR
    centres = (
        (x0 + t + door["center"] - door["width"] / 2) / 2,
        (door["center"] + door["width"] / 2 + x1 - t) / 2,
    )
    for i, x in enumerate(centres):
        for sign in (-1, 1):
            out.append(
                b.box(
                    f"lift{i}_panel{sign}",
                    (x + sign * 0.253, y0 + t + 0.028, 1.175),
                    (0.494, 0.04, 2.30),
                    "metal",
                    room="foyer",
                    radius=0.006,
                    collide=False,
                )
            )
        out.append(
            b.box(
                f"lift{i}_header",
                (x, y0 + t + 0.045, 2.36),
                (1.10, 0.06, 0.05),
                "stone",
                room="foyer",
                collide=False,
            )
        )
    return out
