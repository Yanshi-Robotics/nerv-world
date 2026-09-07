"""house2/apt2 专属的住宅构件；旧场景不调用这些构造函数。尺寸单位为米。"""

from __future__ import annotations

import math
import random

from scenes import furniture as F

WHITE = (0.91, 0.89, 0.84, 1)
OAK = (0.74, 0.62, 0.45, 1)
LINEN = (0.87, 0.84, 0.77, 1)
BRONZE = (0.18, 0.19, 0.18, 1)
STONE = (0.78, 0.76, 0.69, 1)
MESH_GRID = 6  # 每面六等分，圆角轮廓足够平滑且远低于高模成本。
DETAIL_GAP = 0.004  # 可见饰面与底层之间的偏移，避免共面闪烁。


def material_set(prefix):
    """复用已校验的材质字节，只建立本次场景自己的名字与反光属性。"""
    sources = dict(
        oak="h3_oak",
        walnut="h3_oak_dark",
        stone="h3_travertine",
        marble="h3_marble",
        linen="h3_linen",
        plaster="h3_plaster",
        rug="h3_rug",
    )
    textures, materials = [], []
    shine = dict(
        oak=(0.18, 0.28),
        walnut=(0.18, 0.32),
        stone=(0.12, 0.22),
        marble=(0.28, 0.48),
        linen=(0.025, 0.08),
        plaster=(0.02, 0.08),
        rug=(0.01, 0.04),
    )
    for key, source in sources.items():
        file = {
            "oak": "textures/residences/pale_oak.png",
            "stone": "textures/residences/limestone.png",
            "linen": "textures/residences/linen.png",
        }.get(key, f"textures/house3/{source}.png")
        textures.append(
            dict(
                name=f"{prefix}_tex_{key}",
                type="cube" if key == "plaster" else "2d",
                file=file,
                colorspace="sRGB",
            )
        )
        sp, sh = shine[key]
        materials.append(
            dict(
                name=f"{prefix}_{key}",
                texture=f"{prefix}_tex_{key}",
                rgba="1 1 1 1",
                specular=sp,
                shininess=sh,
                reflectance=0,
            )
        )
    for key, rgba, sp, sh in [
        ("white", WHITE, 0.08, 0.2),
        ("metal", BRONZE, 0.6, 0.72),
        ("ceramic", (0.93, 0.94, 0.91, 1), 0.45, 0.65),
        ("glass", (0.62, 0.80, 0.83, 0.18), 0.65, 0.8),
        ("water", (0.22, 0.53, 0.59, 0.24), 0.6, 0.8),
        ("leaf", (0.31, 0.41, 0.20, 1), 0.015, 0.04),
        ("leaf_light", (0.40, 0.49, 0.25, 1), 0.015, 0.04),
        ("bark", (0.33, 0.28, 0.20, 1), 0.03, 0.1),
        ("light", (0.98, 0.89, 0.68, 1), 0.1, 0.2),
    ]:
        m = dict(name=f"{prefix}_{key}", rgba=" ".join(map(str, rgba)), specular=sp, shininess=sh)
        if key == "light":
            m["emission"] = 0.45
        materials.append(m)
    return textures, materials


def rounded_mesh(size, radius=0.025, tile=1.0):
    """有真实圆角及米制 UV 的盒网格，顶点永远位于原碰撞盒内。"""
    half = [v / 2 for v in size]
    radius = min(radius, min(half) * 0.8)
    inner = [v - radius for v in half]
    verts, normals, uv, faces = [], [], [], []
    n = MESH_GRID if radius else 1
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for sign in (-1, 1):
            first = len(verts)
            for j in range(n + 1):
                for i in range(n + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = sign * half[axis]
                    p[a] = (2 * i / n - 1) * half[a]
                    p[b] = (2 * j / n - 1) * half[b]
                    if radius:
                        c = [max(-inner[k], min(inner[k], p[k])) for k in range(3)]
                        v = [p[k] - c[k] for k in range(3)]
                        length = math.sqrt(sum(x * x for x in v))
                        normal = [x / length for x in v]
                        p = [c[k] + radius * normal[k] for k in range(3)]
                    else:
                        normal = [0.0, 0.0, 0.0]
                        normal[axis] = sign
                    verts.append(p)
                    normals.append(normal)
                    uv.append((i / n * size[a] / tile, j / n * size[b] / tile))
            for j in range(n):
                for i in range(n):
                    q = first + j * (n + 1) + i
                    pair = [(q, q + 1, q + n + 2), (q, q + n + 2, q + n + 1)]
                    faces.extend(pair if sign > 0 else [tuple(reversed(t)) for t in pair])
    return dict(vertex=verts, normal=normals, texcoord=uv, face=faces)


class Builder:
    """构件与网格同源生成，重复尺寸共享网格；不接触其它场景资产。"""

    def __init__(self, prefix):
        self.prefix = prefix
        self.meshes = {}
        self._keys = {}

    def mesh(self, size, radius=0.025, tile=1.0):
        key = tuple(round(v, 5) for v in (*size, radius, tile))
        if key not in self._keys:
            name = f"{self.prefix}_shape_{len(self._keys)}"
            self._keys[key] = name
            self.meshes[name] = rounded_mesh(size, radius, tile)
        return self._keys[key]

    def box(
        self,
        name,
        pos,
        size,
        mat="stone",
        *,
        room=None,
        rgba=WHITE,
        radius=0.02,
        tile=1.0,
        collide=True,
        yaw=0,
        group=0,
    ):
        d = F._p(f"{self.prefix}_{name}", room, "box", pos, size, rgba, f"{self.prefix}_{mat}", yaw)
        d.update(visual_mesh=self.mesh(size, radius, tile), collide=collide, group=group)
        return d

    def detail(self, item, radius=0.02, tile=1.0):
        """为已存在的家具盒加视觉网格，不改其碰撞尺寸或位置。"""
        if item["type"] == "box" and not item.get("mesh"):
            item["visual_mesh"] = self.mesh(item["size"], radius, tile)
        return item

    def cabinet(self, name, room, x, y, width=2.4, depth=0.58, height=0.85, yaw=0):
        out = []

        def part(tag, dx, dy, z, size, mat, r=0.015):
            dx, dy = F._rot(dx, dy, yaw)
            out.append(
                self.box(
                    name + "_" + tag, (x + dx, y + dy, z), size, mat, room=room, radius=r, yaw=yaw
                )
            )

        part("plinth", 0, 0, 0.05, (width - 0.12, depth - 0.08, 0.10), "metal")
        part("case", 0, 0, height / 2, (width, depth, height - 0.08), "walnut")
        count = max(2, round(width / 0.55))
        panel = width / count
        for i in range(count):
            dx = -width / 2 + (i + 0.5) * panel
            part(
                f"front{i}",
                dx,
                -depth / 2 - 0.012,
                height / 2,
                (panel - 0.016, 0.025, height - 0.15),
                "oak",
            )
            part(
                f"handle{i}",
                dx + panel * 0.3,
                -depth / 2 - 0.045,
                height * 0.72,
                (0.018, 0.04, 0.16),
                "metal",
            )
        part("top", 0, 0, height, (width + 0.035, depth + 0.045, 0.045), "stone")
        return out

    def bed(self, name, room, x, y, width=1.9, yaw=0):
        out = []
        for tag, dx, dy, z, size, mat, r in [
            ("base", 0, 0, 0.16, (width, 2.1, 0.26), "walnut", 0.04),
            ("mattress", 0, 0, 0.40, (width - 0.04, 2.06, 0.24), "linen", 0.10),
            ("head", 0, 0.99, 0.64, (width + 0.18, 0.16, 1.12), "linen", 0.05),
            ("duvet", 0, -0.24, 0.545, (width + 0.06, 1.47, 0.10), "linen", 0.045),
            ("throw", 0, -0.70, 0.605, (width + 0.08, 0.43, 0.035), "rug", 0.015),
            ("pillow0", -width * 0.24, 0.64, 0.565, (width * 0.42, 0.42, 0.13), "linen", 0.06),
            ("pillow1", width * 0.24, 0.64, 0.565, (width * 0.42, 0.42, 0.13), "linen", 0.06),
        ]:
            dx, dy = F._rot(dx, dy, yaw)
            out.append(
                self.box(
                    name + "_" + tag, (x + dx, y + dy, z), size, mat, room=room, radius=r, yaw=yaw
                )
            )
        for side in (-1, 1):
            dx, dy = F._rot(side * (width / 2 + 0.43), 0.65, yaw)
            out += self.cabinet(name + f"_night{side}", room, x + dx, y + dy, 0.55, 0.48, 0.49, yaw)
            out += F.table_lamp(self.prefix + name + f"_lamp{side}", room, x + dx, y + dy, 0.52)
        return out

    def sofa(self, name, room, x, y, width=2.6, yaw=0):
        out = F.sofa(
            self.prefix + name,
            room,
            x,
            y,
            width=width,
            yaw=yaw,
            rgba=LINEN,
            mat=self.prefix + "_linen",
        )
        for item in out:
            self.detail(item, 0.045, 0.7)
        # 座面保持 0.35 米；接缝仅靠色差表现，不在座面上叠加承重厚垫。
        for i in range(1, 3):
            dx, dy = F._rot(0, -width / 2 + width * i / 3, yaw)
            out.append(
                self.box(
                    name + f"_seam{i}",
                    (x + dx, y + dy, 0.351),
                    (0.43, 0.004, 0.002),
                    "stone",
                    room=room,
                    radius=0,
                    collide=False,
                    yaw=yaw,
                )
            )
        return out

    def tree(self, name, x, y, height=7.0, spread=4.0, seed=0):
        rng = random.Random(seed)
        out = []

        def rod(tag, a, b, r):
            out.append(
                dict(
                    name=f"{self.prefix}_{name}_{tag}",
                    type="capsule",
                    fromto=(*a, *b),
                    radius=r,
                    mat=self.prefix + "_bark",
                    collide=True,
                )
            )

        rod("trunk", (x, y, 0), (x + 0.18, y, height * 0.63), height * 0.018)
        # Branched canopy with individually modelled leaves. Reuse four crowns across
        # the estate; leaf surfaces are merged meshes, not thousands of draw calls.
        crowns = [dict(vertex=[], texcoord=[], face=[]) for _ in range(2)]
        for i in range(13):
            angle = i * 2.399963229728653  # 黄金角让枝冠均匀分布，避免规则环形。
            reach = spread * (0.22 + 0.23 * rng.random())
            bx = x + math.cos(angle) * reach
            by = y + math.sin(angle) * reach
            bz = height * (0.57 + 0.32 * rng.random())
            rod(f"branch{i}", (x, y, height * 0.40), (bx, by, bz), height * 0.006)
            for leaf in range(125):
                phi = rng.uniform(0, 2 * math.pi)
                ct = rng.uniform(-1, 1)
                rr = rng.random() ** (1 / 3)
                st = math.sqrt(1 - ct * ct)
                center = (
                    bx - x + math.cos(phi) * st * rr * spread * 0.30,
                    by - y + math.sin(phi) * st * rr * spread * 0.28,
                    bz + ct * rr * height * 0.12,
                )
                a = rng.uniform(0, 2 * math.pi)
                tilt = rng.uniform(-0.7, 0.7)
                length = rng.uniform(0.16, 0.30)
                width = length * 0.48
                along = (math.cos(a), math.sin(a), tilt)
                across = (-math.sin(a), math.cos(a), -0.15)
                mesh = crowns[leaf % 2]
                q = len(mesh["vertex"])
                # Four triangles meet a slightly raised centre, creating a curled leaf.
                points = [(0, 0, 0.025), (1, 0, 0), (0.35, 1, 0), (-1, 0, 0), (-0.35, -1, 0)]
                for u, v, w in points:
                    mesh["vertex"].append(
                        tuple(
                            center[k]
                            + u * length * along[k]
                            + v * width * across[k]
                            + (w if k == 2 else 0)
                            for k in range(3)
                        )
                    )
                    mesh["texcoord"].append(((u + 1) / 2, (v + 1) / 2))
                mesh["face"] += [
                    (q, q + 1, q + 2),
                    (q, q + 2, q + 3),
                    (q, q + 3, q + 4),
                    (q, q + 4, q + 1),
                ]
        for i, mesh in enumerate(crowns):
            meshname = f"{self.prefix}_canopy_{seed}_{i}"
            self.meshes[meshname] = mesh
            out.append(
                dict(
                    name=f"{self.prefix}_{name}_canopy{i}",
                    type="mesh",
                    mesh_name=meshname,
                    pos=(x, y, 0),
                    mat=self.prefix + ("_leaf" if i == 0 else "_leaf_light"),
                    collide=False,
                )
            )
        return out


def interior_finish(layout, builder):
    """门窗收口、细木工、窗帘、灯具；碰撞地板保留，表面采用米制 UV。"""
    architecture = []
    p = builder.prefix
    for key, room in layout.ROOMS.items():
        if key.startswith("stair"):
            continue
        x0, y0, x1, y1 = room["rect"]
        z = layout.FLOOR_Z(room.get("floor", 0))
        # 仅对实际楼板加表面，挑空部分绝不补成整块。
        mat = (
            "stone"
            if any(s in key for s in ("bath", "entry", "gallery", "kitchen", "laundry"))
            else "oak"
        )
        room["floor_mat"] = p + "_" + mat
        room["floor_rgba"] = (1, 1, 1, 1)
        room["wall_mat"] = p + "_plaster"
        room["wall_rgba"] = WHITE
        for i, (a, b, c, d) in enumerate(room.get("floor_rects", [room["rect"]])):
            architecture.append(
                builder.box(
                    f"{key}_finish{i}",
                    ((a + c) / 2, (b + d) / 2, z + 0.001),
                    (c - a - 0.008, d - b - 0.008, 0.002),
                    mat,
                    radius=0,
                    tile=2.0,
                    collide=False,
                )
            )
        # 踢脚分段复用门窗洞口，避免在门前形成踢脚绊脚条。
        for side, horiz, fixed, lo, hi in [
            ("s", True, y0, x0, x1),
            ("n", True, y1, x0, x1),
            ("w", False, x0, y0, y1),
            ("e", False, x1, y0, y1),
        ]:
            cuts = []
            for door in layout.DOORS:
                if door.get("floor", room.get("floor", 0)) != room.get("floor", 0):
                    continue
                if door["orient"] == ("h" if horiz else "v") and abs(door["coord"] - fixed) < 1e-6:
                    cuts.append(
                        (
                            door["center"] - door["width"] / 2 - 0.06,
                            door["center"] + door["width"] / 2 + 0.06,
                        )
                    )
            for window in layout.WINDOWS:
                if (
                    window["room"] == key
                    and window["side"] == side
                    and window.get("sill", layout.WINDOW_SILL_H) < 0.15
                ):
                    cuts.append(
                        (
                            window["center"] - window["width"] / 2 - 0.05,
                            window["center"] + window["width"] / 2 + 0.05,
                        )
                    )
            runs = []
            cursor = lo + layout.WALL_THICK
            for a, b in sorted(cuts):
                if b < lo or a > hi:
                    continue
                if a > cursor:
                    runs.append((cursor, min(a, hi - layout.WALL_THICK)))
                cursor = max(cursor, b)
            if cursor < hi - layout.WALL_THICK:
                runs.append((cursor, hi - layout.WALL_THICK))
            inward = 1 if side in ("s", "w") else -1
            for i, (a, b) in enumerate(runs):
                if b - a < 0.04:
                    continue
                f = fixed + inward * (layout.WALL_THICK + 0.012)
                pos = ((a + b) / 2, f, z + 0.055) if horiz else (f, (a + b) / 2, z + 0.055)
                size = (b - a, 0.025, 0.11) if horiz else (0.025, b - a, 0.11)
                architecture.append(
                    builder.box(
                        f"{key}_{side}_skirt{i}", pos, size, "white", radius=0.008, collide=False
                    )
                )
        # 每间房的实物灯具只发亮；照明由有限数量的场景灯负责。
        if not room.get("no_ceiling"):
            architecture.append(
                builder.box(
                    f"{key}_ceiling_light",
                    ((x0 + x1) / 2, (y0 + y1) / 2, z + layout.WALL_HEIGHT - 0.045),
                    (min(1.5, (x1 - x0) * 0.25), 0.055, 0.035),
                    "light",
                    radius=0.012,
                    collide=False,
                    group=1,
                )
            )
    for index, w in enumerate(layout.WINDOWS):
        room = layout.ROOMS[w["room"]]
        if w["room"].startswith("stair"):
            continue
        x0, y0, x1, y1 = room["rect"]
        z = layout.FLOOR_Z(room.get("floor", 0))
        top = w.get("top", layout.WINDOW_TOP_H)
        sill = w.get("sill", layout.WINDOW_SILL_H)
        side = w["side"]
        horizontal = side in ("n", "s")
        fixed = {
            "n": y1 - layout.WALL_THICK - 0.10,
            "s": y0 + layout.WALL_THICK + 0.10,
            "e": x1 - layout.WALL_THICK - 0.10,
            "w": x0 + layout.WALL_THICK + 0.10,
        }[side]
        for end in (-1, 1):
            for fold in range(4):
                c = w["center"] + end * (w["width"] / 2 - 0.09) + fold * 0.045
                pos = (
                    (c, fixed, z + (top + sill) / 2)
                    if horizontal
                    else (fixed, c, z + (top + sill) / 2)
                )
                size = (0.058, 0.105, top - sill) if horizontal else (0.105, 0.058, top - sill)
                architecture.append(
                    builder.box(
                        f"curtain{index}_{end}_{fold}",
                        pos,
                        size,
                        "linen",
                        radius=0.025,
                        tile=0.6,
                        collide=False,
                    )
                )
    # A thin landing slab leaves daylight above the final tread's vertical face.
    # Close that face with a 20 mm timber fascia inside the landing, preserving
    # every validated tread top, pitch and structural collision shape.
    fascia_depth = 0.020
    for flight in getattr(layout, "STAIRS", []):
        dx, dy = flight["dir"]
        x, y = flight["start_xy"]
        end = (flight["risers"] - 1) * layout.STEP_RUN
        top = flight["base_z"] + flight["risers"] * layout.STEP_RISE
        last_tread = top - layout.STEP_RISE
        slab_bottom = top - layout.FLOOR_THICK
        for slab in getattr(layout, "LANDINGS", []):
            sx, sy, sz = slab["size"]
            px, py, pz = slab["pos"]
            if (
                abs(pz + sz / 2 - top) < 1e-6
                and abs(x + dx * end - px) <= sx / 2 + 1e-6
                and abs(y + dy * end - py) <= sy / 2 + 1e-6
            ):
                slab_bottom = pz - sz / 2
                break
        gap_height = slab_bottom - last_tread
        if gap_height <= 0:
            continue
        architecture.append(
            builder.box(
                flight["name"] + "_landing_fascia",
                (
                    x + dx * (end + fascia_depth / 2),
                    y + dy * (end + fascia_depth / 2),
                    (slab_bottom + last_tread) / 2,
                ),
                (
                    fascia_depth if dx else flight["width"],
                    flight["width"] if dx else fascia_depth,
                    gap_height,
                ),
                "oak",
                radius=0,
                collide=False,
            )
        )
    return architecture
