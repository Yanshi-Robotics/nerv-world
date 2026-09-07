"""加州山坡宅地：承重庭院、真实泳池、封闭边界和不可进入的社区远景。"""

from __future__ import annotations

import math
import random


SITE = (-40.0, -39.5, 40.0, 30.5)
POOL = (20.0, -27.5, 26.0, -12.5)
LAWN = (-16.0, -35.5, 14.0, -10.5)
GATE_CENTER = -28.0
GATE_WIDTH = 5.2
POOL_DEPTH = 1.5
BOUNDARY_HEIGHT = 1.85
PAVING_THICKNESS = 0.16
GROUND_TOP = 0.0
TERRAIN_GRID = 30
TERRAIN_SPACING = 22.0


def build_estate(b, floor_z, storey_h, footprints):
    exterior, areas, background = [], [], []

    def box(name, rect, z, thick, mat="stone", collide=True, **kw):
        x0, y0, x1, y1 = rect
        d = b.box(
            name,
            ((x0 + x1) / 2, (y0 + y1) / 2, z - thick / 2),
            (x1 - x0, y1 - y0, thick),
            mat,
            collide=collide,
            **kw,
        )
        exterior.append(d)
        return d

    def area(name, label, rect, z=0):
        areas.append(dict(name=name, label=label, rect=rect, floor_z=z))

    sx, sy, ex, ey = SITE
    px, py, qx, qy = POOL
    bw, bs, be, bn = footprints[0]
    # Split around BOTH house and basin, avoiding duplicate indoor floor contacts.
    xs = sorted({sx, bw, be, px, qx, ex})
    ys = sorted({sy, py, qy, bs, bn, ey})
    for i, (a, c) in enumerate(zip(xs, xs[1:])):
        for j, (d, e) in enumerate(zip(ys, ys[1:])):
            cx, cy = (a + c) / 2, (d + e) / 2
            if (bw < cx < be and bs < cy < bn) or (px < cx < qx and py < cy < qy):
                continue
            box(
                f"estate_ground{i}_{j}",
                (a, d, c, e),
                GROUND_TOP,
                PAVING_THICKNESS,
                "grass",
                radius=0,
                tile=7.0,
            )
    # 连续草坪以低起伏的颜色与细纹表现，不为每根草增加碰撞。
    btex = dict(
        name="h2_tex_grass", type="2d", file="textures/residences/grass.png", colorspace="sRGB"
    )
    # 材质由 layout 接入；本模块返回声明，避免改变其它场景的纹理集合。
    box("main_lawn", LAWN, 0.003, 0.003, "grass", False, radius=0, tile=7.0)
    area("front_lawn", "前庭草坪", LAWN)
    area("forecourt", "入户前庭", (-16, -10.5, 16, -4.5))
    area("driveway", "车道", (-31, -39.5, -25, -4.5))
    area("side_walk", "侧庭步道", (15, -10.5, 19.5, 20.0))
    area("pool_terrace", "泳池露台", (15, -31.0, 31.0, 8.0))
    area("rear_garden", "后庭", (-18, 17.5, 19, 28))
    area("west_walk", "西侧步道", (-19, -4.5, -15, 20))
    for i, r in enumerate([(-18, -7, -15, 20), (-18, 17.5, 19, 20), (15, -7, 18, 20)]):
        box(f"house_walk{i}", r, 0.005, 0.005, "stone", False, radius=0, tile=2.0)
    box("driveway_surface", (-31, sy, -25, -4.5), 0.002, 0.002, "stone", False, radius=0, tile=4.0)
    box("arrival_surface", (-31, -10.5, 16, -4.5), 0.004, 0.004, "stone", False, radius=0, tile=2.0)
    box("pool_deck", (16, -31, 30, 8), 0.002, 0.002, "stone", False, radius=0, tile=2.0)
    # 泳池上方的露台装饰也必须扣除水域。
    exterior.pop()
    for i, r in enumerate([(16, -31, 20, 8), (26, -31, 30, 8), (20, -31, 26, py), (20, qy, 26, 8)]):
        box(f"pool_deck{i}", r, 0.002, 0.002, "stone", False, radius=0, tile=2.0)
    # 灰色铺装分缝是真实窄槽视觉，路面高度不变。
    for i in range(13):
        y = -38 + i * 2.6
        box(f"drive_joint{i}", (-31, y, -25, y + 0.012), 0.006, 0.002, "metal", False, radius=0)
    # 草坪东侧的踏步步道实际是连续平整路面上的石材铺装。
    for i in range(13):
        y = -35 + i * 2.15
        box(
            f"garden_paver{i}", (14.6, y, 16.6, y + 1.6), 0.006, 0.006, "stone", False, radius=0.015
        )
    for i, r in enumerate(
        [
            (-16.15, -35.65, 14.15, -35.5),
            (-16.15, -10.5, 14.15, -10.35),
            (-16.15, -35.5, -16, -10.5),
            (14, -35.5, 14.15, -10.5),
        ]
    ):
        box(f"lawn_edging{i}", r, 0.028, 0.05, "stone", False, radius=0.01)
    # 水池的池底、池壁、池沿、池内台阶各自具有真实形状与碰撞。
    box("pool_bottom", POOL, -POOL_DEPTH, 0.20, "pool_tile", radius=0, tile=0.6)
    for tag, r in [
        ("west", (px - 0.18, py - 0.18, px, qy + 0.18)),
        ("east", (qx, py - 0.18, qx + 0.18, qy + 0.18)),
        ("south", (px, py - 0.18, qx, py)),
        ("north", (px, qy, qx, qy + 0.18)),
    ]:
        box("pool_wall_" + tag, r, 0, POOL_DEPTH + 0.2, "pool_tile", radius=0, tile=0.6)
    for i in range(4):
        depth = (i + 1) * 0.3
        box(
            f"pool_step{i}",
            (px + 0.12, qy - (i + 1) * 0.36, qx - 0.12, qy - i * 0.36),
            -depth,
            POOL_DEPTH - depth,
            "pool_tile",
            radius=0.02,
            tile=0.6,
        )
    box("pool_water", POOL, -0.12, 0.002, "water", False, radius=0)
    for i, r in enumerate(
        [
            (px - 0.38, py - 0.38, px, qy + 0.38),
            (qx, py - 0.38, qx + 0.38, qy + 0.38),
            (px, py - 0.38, qx, py),
            (px, qy, qx, qy + 0.38),
        ]
    ):
        box(f"pool_coping{i}", r, 0.075, 0.12, "stone", radius=0.025, tile=1.0)
    # 池畔躺椅、靠背、木脚架与遮阳廊架。
    for i, y in enumerate((-25.0, -21.0, -17.0)):
        for tag, dx, dy, z, size, mat, rad in [
            ("frame", 0, 0, 0.27, (1.0, 2.05, 0.11), "walnut", 0.03),
            ("cushion", 0, -0.28, 0.365, (0.92, 1.4, 0.12), "linen", 0.045),
            ("back", 0, 0.65, 0.54, (0.92, 0.54, 0.40), "linen", 0.05),
        ]:
            exterior.append(
                b.box(f"lounger{i}_{tag}", (28.1 + dx, y + dy, z), size, mat, radius=rad)
            )
        for dx in (-0.4, 0.4):
            for dy in (-0.75, 0.75):
                exterior.append(
                    b.box(
                        f"lounger{i}_leg{dx}_{dy}",
                        (28.1 + dx, y + dy, 0.13),
                        (0.07, 0.07, 0.26),
                        "metal",
                    )
                )
    for x in (17.5, 28.5):
        for y in (-7.0, 4.0):
            exterior.append(
                b.box(f"pergola_post{x}_{y}", (x, y, 1.55), (0.18, 0.18, 3.1), "walnut")
            )
    for i in range(17):
        y = -7.0 + i * 11 / 16
        exterior.append(
            b.box(f"pergola_beam{i}", (23.0, y, 3.1), (11.4, 0.13, 0.21), "walnut", collide=False)
        )
    # 围墙和门洞同源，关闭的大门覆盖完整开口。
    for tag, pos, size in [
        ("west", (sx, (sy + ey) / 2, BOUNDARY_HEIGHT / 2), (0.24, ey - sy, BOUNDARY_HEIGHT)),
        ("east", (ex, (sy + ey) / 2, BOUNDARY_HEIGHT / 2), (0.24, ey - sy, BOUNDARY_HEIGHT)),
        ("north", ((sx + ex) / 2, ey, BOUNDARY_HEIGHT / 2), (ex - sx, 0.24, BOUNDARY_HEIGHT)),
    ]:
        exterior.append(b.box("boundary_" + tag, pos, size, "plaster", radius=0, tile=2.0))
    for tag, a, c in [
        ("left", sx, GATE_CENTER - GATE_WIDTH / 2),
        ("right", GATE_CENTER + GATE_WIDTH / 2, ex),
    ]:
        exterior.append(
            b.box(
                "boundary_south_" + tag,
                ((a + c) / 2, sy, BOUNDARY_HEIGHT / 2),
                (c - a, 0.24, BOUNDARY_HEIGHT),
                "plaster",
                radius=0,
            )
        )
    exterior.append(
        b.box(
            "estate_gate",
            (GATE_CENTER, sy, 1.0),
            (GATE_WIDTH, 0.16, 2.0),
            "metal",
            radius=0.015,
            group=4,
        )
    )
    for z in (0.12, 1.88):
        exterior.append(
            b.box(
                "gate_frame" + str(z),
                (GATE_CENTER, sy - 0.095, z),
                (GATE_WIDTH, 0.055, 0.09),
                "metal",
                collide=False,
            )
        )
    for i in range(18):
        x = GATE_CENTER - GATE_WIDTH / 2 + (i + 0.5) * GATE_WIDTH / 18
        exterior.append(
            b.box(
                f"gate_slats{i}", (x, sy - 0.095, 1.0), (0.09, 0.045, 1.9), "walnut", collide=False
            )
        )
    for x in (GATE_CENTER - GATE_WIDTH / 2 - 0.2, GATE_CENTER + GATE_WIDTH / 2 + 0.2):
        exterior.append(b.box("gate_pier" + str(x), (x, sy, 1.2), (0.5, 0.7, 2.4), "stone"))
    # 树木位于边界内侧；疏密错落，南侧和东侧留观察坡地社区的空隙。
    trees = [(-36, y) for y in (-33, -21, -9, 4, 17, 26)] + [(36, y) for y in (-32, -10, 12, 26)]
    trees += [(x, 26) for x in (-26, -15, -3, 10, 23)] + [(x, -36.5) for x in (-18, -7, 7, 21, 34)]
    for i, (x, y) in enumerate(trees):
        exterior += b.tree(
            f"tree{i}", x, y, 8.0 + (i % 4) * 0.7, 5.6 + (i % 4) * 0.3, seed=901 + i % 4
        )
    for i in range(12):
        x = -33 + i * 6
        exterior.append(
            dict(
                name=f"h2_hedge{i}",
                type="ellipsoid",
                pos=(x, 28.0, 0.7),
                size=(4.8, 1.4, 1.2),
                rgba=(0.25, 0.37, 0.18, 1),
                collide=False,
            )
        )
    # 三层前露台位于二层屋顶，地面与上层门厅标高一致。
    tz = floor_z(2)
    box("view_terrace_floor", (-15, -4.5, 15, -1), tz, 0.10, "stone", radius=0, tile=2.0)
    area("view_terrace", "观景露台", (-15, -4.5, 15, -1), tz)
    for tag, pos, size in [
        ("front", (0, -4.45, tz + 0.6), (30, 0.06, 1.2)),
        ("west", (-14.95, -2.75, tz + 0.6), (0.06, 3.4, 1.2)),
        ("east", (14.95, -2.75, tz + 0.6), (0.06, 3.4, 1.2)),
    ]:
        exterior.append(b.box("terrace_guard_" + tag, pos, size, "glass", radius=0))
    for side, a, c in [("west", -15.0, -11.0), ("east", 11.0, 15.0)]:
        exterior.append(
            b.box(
                "terrace_return_" + side,
                ((a + c) / 2, -1.03, tz + 0.6),
                (c - a, 0.06, 1.2),
                "glass",
                radius=0,
            )
        )
    # 建筑水平收口强化三层的体量关系，框架在墙外不横穿窗口。
    # Deep entrance portico, offset stone chimney and recessed timber panels.
    exterior.append(
        b.box("entry_canopy", (-1.4, -5.7, 2.55), (7.1, 2.65, 0.24), "stone", collide=False)
    )
    for x in (-4.65, 1.85):
        exterior.append(
            b.box("entry_column" + str(x), (x, -6.45, 1.20), (0.20, 0.20, 2.40), "metal")
        )
    exterior.append(
        b.box("entry_soffit", (-1.4, -5.7, 2.414), (6.7, 2.4, 0.02), "walnut", collide=False)
    )
    exterior.append(
        b.box("stone_chimney", (-7.45, -4.69, 3.0), (1.20, 0.36, 6.0), "stone", collide=False)
    )
    for i in range(10):
        x = 1.1 + i * 0.135
        exterior.append(
            b.box(f"entry_timber{i}", (x, -4.54, 1.3), (0.065, 0.08, 2.42), "walnut", collide=False)
        )
    for f, rect in enumerate(footprints):
        a, c, d, e = rect
        z = floor_z(f) + storey_h - 0.13
        for tag, pos, size in [
            ("s", ((a + d) / 2, c - 0.16, z), (d - a + 0.7, 0.48, 0.18)),
            ("n", ((a + d) / 2, e + 0.16, z), (d - a + 0.7, 0.48, 0.18)),
            ("w", (a - 0.16, (c + e) / 2, z), (0.48, e - c, 0.18)),
            ("e", (d + 0.16, (c + e) / 2, z), (0.48, e - c, 0.18)),
        ]:
            exterior.append(
                b.box(f"cornice{f}_{tag}", pos, size, "white", radius=0.02, collide=False)
            )
        for x in (a + 0.12, d - 0.12):
            for y in (c + 0.12, e - 0.12):
                exterior.append(
                    b.box(
                        f"corner{f}_{x}_{y}",
                        (x, y, floor_z(f) + 1.32),
                        (0.30, 0.30, 2.64),
                        "stone",
                        collide=False,
                    )
                )

    # 山坡地形在宅地外下降；可见道路与邻宅放在同一个地形函数上。
    def height(x, y):
        cx, cy = (sx + ex) / 2, (sy + ey) / 2
        radius = math.hypot(x - cx, y - cy)
        edge = max(abs(x - cx) / ((ex - sx) / 2), abs(y - cy) / ((ey - sy) / 2)) - 1
        descent = -min(23, max(0, edge) * 7)
        ridge = max(0, (radius - 140) / 170) * 38
        undulation = (math.sin(x / 58) * math.cos(y / 67) * 7 + math.sin(y / 42) * 4) * min(
            1, max(0, edge)
        )
        return descent + ridge + undulation - 0.22

    verts = []
    uv = []
    faces = []
    grid = [(i - TERRAIN_GRID / 2) * TERRAIN_SPACING for i in range(TERRAIN_GRID + 1)]
    gx = sorted(set(grid + [sx, ex]))
    gy = sorted(set(grid + [sy, ey]))
    stride = len(gx)
    for y in gy:
        for x in gx:
            verts.append((x, y, height(x, y)))
            uv.append((x / 50, y / 50))
    for j in range(len(gy) - 1):
        for i in range(len(gx) - 1):
            q = j * stride + i
            x, y, _ = verts[q]
            xx, yy, _ = verts[q + stride + 1]
            if x < ex and xx > sx and y < ey and yy > sy:
                continue
            faces.extend([(q, q + 1, q + stride + 1), (q, q + stride + 1, q + stride)])
    b.meshes["h2_hills"] = dict(vertex=verts, texcoord=uv, face=faces)
    background.append(
        dict(
            name="h2_community_hills",
            type="mesh",
            mesh_name="h2_hills",
            pos=(0, 0, 0),
            mat="h2_grass",
            collide=False,
        )
    )
    rng = random.Random(902)
    for i in range(55):
        angle = 2 * math.pi * i / 55
        distance = 75 + (i % 4) * 44 + rng.uniform(-10, 10)
        x, y = math.cos(angle) * distance, math.sin(angle) * distance
        z = height(x, y)
        w = rng.uniform(9, 16)
        depth = rng.uniform(7, 12)
        h = rng.uniform(4.5, 8.0)
        base = dict(collide=False, radius=0)
        background.append(b.box(f"neighbor{i}", (x, y, z + h / 2), (w, depth, h), "white", **base))
        background.append(
            b.box(
                f"neighbor{i}_roof",
                (x, y, z + h + 0.12),
                (w + 0.9, depth + 0.9, 0.24),
                "walnut",
                **base,
            )
        )
        background.append(
            b.box(
                f"neighbor{i}_wing",
                (x + w * 0.45, y + depth * 0.3, z + h * 0.32),
                (w * 0.55, depth * 0.8, h * 0.64),
                "stone",
                **base,
            )
        )
        for side in (-1, 1):
            for win in (-1, 0, 1):
                background.append(
                    b.box(
                        f"neighbor{i}_window{side}_{win}",
                        (x + win * w * 0.26, y + side * (depth / 2 + 0.01), z + h * 0.56),
                        (w * 0.18, 0.02, h * 0.42),
                        "metal",
                        **base,
                    )
                )
    # Roads share the triangulated terrain height, avoiding floating/clipped segments.
    import bisect

    def surface(x, y):
        i = max(0, min(len(gx) - 2, bisect.bisect_right(gx, x) - 1))
        j = max(0, min(len(gy) - 2, bisect.bisect_right(gy, y) - 1))
        a = (x - gx[i]) / (gx[i + 1] - gx[i])
        c = (y - gy[j]) / (gy[j + 1] - gy[j])
        q = j * stride + i
        z0 = verts[q][2]
        z1 = verts[q + 1][2]
        z2 = verts[q + stride + 1][2]
        z3 = verts[q + stride][2]
        return (
            z0 + (a - c) * (z1 - z0) + c * (z2 - z0)
            if a >= c
            else z0 + a * (z2 - z0) + (c - a) * (z3 - z0)
        )

    def road(name, points, width):
        mesh = dict(vertex=[], texcoord=[], face=[])
        for i, (x, y) in enumerate(points):
            before = points[max(0, i - 1)]
            after = points[min(len(points) - 1, i + 1)]
            dx, dy = after[0] - before[0], after[1] - before[1]
            length = math.hypot(dx, dy)
            for sign in (-1, 1):
                xx = x - sign * dy / length * width / 2
                yy = y + sign * dx / length * width / 2
                mesh["vertex"].append((xx, yy, surface(xx, yy) + 0.035))
                mesh["texcoord"].append(((sign + 1) / 2, i / 8))
            if i:
                q = 2 * i
                mesh["face"] += [(q - 2, q - 1, q + 1), (q - 2, q + 1, q)]
        b.meshes[name] = mesh
        background.append(
            dict(
                name=name, type="mesh", mesh_name=name, pos=(0, 0, 0), mat="h2_road", collide=False
            )
        )

    for radius in (70.0, 125.0, 190.0):
        road(
            "h2_road" + str(int(radius)),
            [
                (radius * math.cos(i * 2 * math.pi / 256), radius * math.sin(i * 2 * math.pi / 256))
                for i in range(257)
            ],
            5.0,
        )
    road(
        "h2_gate_approach",
        [(GATE_CENTER - 9 * t, sy - 20 * t) for t in [i / 30 for i in range(31)]],
        5.2,
    )
    return (
        exterior,
        areas,
        background,
        dict(
            site=SITE,
            pool=POOL,
            pool_depth=POOL_DEPTH,
            lawn=LAWN,
            gate_center=(GATE_CENTER, sy),
            gate_width=GATE_WIDTH,
            grass_texture=btex,
            routes=[
                [
                    (8, -2.7),
                    (8, -1.95),
                    (4.6, -1.95),
                    (-1.4, -1.95),
                    (-1.4, -5.5),
                    (-1.4, -8),
                    (-28, -8),
                    (-28, -38),
                ],
                [(-1.4, -8), (17.5, -8), (17.5, -20)],
                [(-1.4, -8), (-1.4, -20)],
            ],
        ),
    )
