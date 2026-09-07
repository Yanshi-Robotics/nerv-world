"""Apartment furniture, finishes and city meshes, derived from the room layout."""

from copy import deepcopy
from types import SimpleNamespace

from scenes import furniture as F
from scenes.residence import Builder, material_set, interior_finish, rounded_mesh
from scenes.apt.city_materials import assets as city_assets, MATERIAL_ALIASES, ROOF_MATERIAL
from scenes.environments import manhattan


def apply(source):
    keys = (
        "ROOMS",
        "DOORS",
        "WINDOWS",
        "FURNITURE",
        "TEXTURES_EXTRA",
        "MATERIALS_EXTRA",
        "HOST_TOWER",
        "SKYBOX",
        "VISUAL",
        "LIGHTS",
    )
    result = {k: deepcopy(source[k]) for k in keys}
    b = Builder("a2")
    textures, materials = material_set("a2")
    result["TEXTURES_EXTRA"] += textures
    result["MATERIALS_EXTRA"] += materials
    city_textures, city_materials = city_assets(manhattan)
    result["TEXTURES_EXTRA"] += city_textures
    result["MATERIALS_EXTRA"] += city_materials
    layout = SimpleNamespace(**{**source, **result})
    furniture = []
    for item in layout.FURNITURE:
        name = item["name"]
        room = item["room"]
        x, y, z = item["pos"]
        if name.startswith("gr_plant_"):
            continue
        if name in ("gb_bed", "pb_bed"):
            furniture += b.bed(name, room, x, y, width=1.72)
            continue
        if name == "lb_shelf":
            w, d, h = item["size"]
            for tag, dx, dz, sz in [
                ("l", -w / 2 + 0.035, h / 2, (0.07, d, h)),
                ("r", w / 2 - 0.035, h / 2, (0.07, d, h)),
            ]:
                furniture.append(b.box("library_" + tag, (x + dx, y, dz), sz, "walnut", room=room))
            for i in range(6):
                zz = 0.10 + i * (h - 0.20) / 5
                furniture.append(
                    b.box(f"library_shelf{i}", (x, y, zz), (w, d, 0.045), "oak", room=room)
                )
                if i < 5:
                    for j in range(7):
                        furniture.append(
                            b.box(
                                f"library_book{i}_{j}",
                                (x - w * 0.40 + j * w * 0.115, y, zz + 0.15),
                                (0.065, d * 0.8, 0.26),
                                "linen" if j % 3 else "walnut",
                                room=room,
                                radius=0.003,
                            )
                        )
            continue
        if name in ("kt_island", "kt_run"):
            w, d, h = item["size"]
            furniture += b.cabinet(name, room, x, y, w, d, h)
            continue
        mat = item.get("mat", "")
        if name.startswith("dn_table"):
            item["mat"] = "a2_oak"
            item["rgba"] = (1, 1, 1, 1)
        elif "linen" in mat or "sofa" in name:
            item["mat"] = "a2_linen"
        elif "oak_dark" in mat:
            item["mat"] = "a2_walnut"
        elif "oak" in mat:
            item["mat"] = "a2_oak"
        elif "marble" in mat:
            item["mat"] = "a2_marble"
        elif "screen" in name:
            pass
        elif not item.get("mesh"):
            item["mat"] = "a2_walnut"
        b.detail(item, 0.035 if "sofa" in name else 0.015, 1.2)
        furniture.append(item)
    # 真实盆栽取单株，不把四棵打包网格当一棵树使用。
    furniture += F.mesh_piece(
        "a2_gr_plant",
        "great_room",
        5.0,
        7.0,
        size=(0.503, 0.607, 0.735),
        mesh="plant_b",
        parts=(2, 6),
    )
    # 原场景厨房仅有台面；补完整电器与结构化水槽，不用外衣掩盖实心台面。
    furniture += F.mesh_piece(
        "a2_kt_fridge", "kitchen", -10.7, 2.7, size=(0.70, 0.65, 1.65), mesh="rc_fridge"
    )
    # 中岛上的水槽有独立底板和四壁，微小高度只影响台面，不影响地面通行。
    for tag, dx, dy, sz in [
        ("bottom", 0, 0, (0.64, 0.40, 0.025)),
        ("n", 0, 0.21, (0.68, 0.03, 0.07)),
        ("s", 0, -0.21, (0.68, 0.03, 0.07)),
        ("w", -0.33, 0, (0.03, 0.40, 0.07)),
        ("e", 0.33, 0, (0.03, 0.40, 0.07)),
    ]:
        furniture.append(
            b.box(
                "sink_" + tag,
                (-8.4 + dx, 4.2 + dy, 0.96),
                sz,
                "metal",
                room="kitchen",
                radius=0.006,
            )
        )
    furniture.append(
        b.box(
            "sink_faucet",
            (-8.4, 4.48, 1.10),
            (0.035, 0.035, 0.33),
            "metal",
            room="kitchen",
            radius=0.015,
        )
    )
    # 之前空置的卫浴、衣帽和洗衣空间补足其用途所需的实物。
    for key, r in layout.ROOMS.items():
        x0, y0, x1, y1 = r["rect"]
        if "bath" in key or key == "powder":
            width = min(1.5, (x1 - x0) - 0.7)
            furniture += b.cabinet(
                key + "_vanity", key, (x0 + x1) / 2, y0 + 0.65, width, 0.50, 0.82, yaw=180
            )
            if "bath" in key:
                furniture.append(
                    b.box(
                        key + "_basin",
                        ((x0 + x1) / 2, y0 + 0.65, 0.89),
                        (0.50, 0.37, 0.08),
                        "ceramic",
                        room=key,
                        radius=0.035,
                    )
                )
        if key == "study":
            furniture += F.books_stack("a2_st_books", key, x0 + 1.3, y1 - 0.8, 0.78)
    from scenes.apt.service_rooms import furnish
    furniture += furnish(layout, b)
    layout.FURNITURE = furniture
    architecture = interior_finish(layout, b)
    # 环廊栏板保留原碰撞，顶面新增细木扶手，避免改变临空防护。
    for guard in source["GUARDS"]:
        x, y, z = guard["pos"]
        sx, sy, sz = guard["size"]
        architecture.append(
            b.box(
                guard["name"] + "_cap",
                (x, y, z + sz / 2 + 0.015),
                (sx + 0.015, sy + 0.015, 0.03),
                "walnut",
                radius=0.01,
                collide=False,
            )
        )
    # Preserve every city building coordinate and height, batching visual boxes by
    # material and district to reduce thousands of individual render submissions.
    # Unit face UVs preserve facade scale per building, including narrow towers.
    from scenes.environments.manhattan import bands_for_building
    city_batches = {}
    roof_batches = {}
    band_names = {name: [] for name in source["GEOM_BANDS"] if name != "host"}
    band_buildings = {name: [] for name in band_names}
    district_size = 500.0  # metres: keeps batches spatially bounded for camera culling.
    facade_tile_m = 4 * source["FLOOR_TO_FLOOR"]  # Original atlas covers four storeys.
    for name, x, y, sx, sy, top, mat in source["SKYLINE"]:
        bands = bands_for_building(name, x, y)
        for band in bands:
            band_buildings[band].append(name)
        key = (mat, int(x // district_size), int(y // district_size), bands)
        batch = city_batches.setdefault(key, dict(vertex=[], texcoord=[], face=[], buildings=[]))
        roof = roof_batches.setdefault(key, dict(vertex=[], texcoord=[], face=[], inertia="shell"))
        batch["buildings"].append(name)
        height = top + source["ELEV"]
        shape = rounded_mesh((sx, sy, height), radius=0)
        offset = len(batch["vertex"])
        batch["vertex"] += [
            (vx + x, vy + y, vz - source["ELEV"] + height / 2) for vx, vy, vz in shape["vertex"][:16]
        ]
        batch["texcoord"] += [((vy if i < 8 else vx)/facade_tile_m, (vz+height/2)/facade_tile_m)
                              for i, (vx, vy, vz) in enumerate(shape["vertex"][:16])]
        batch["face"] += [tuple(offset + k for k in face) for face in shape["face"][:8]]
        offset = len(roof["vertex"])
        roof["vertex"] += [(vx+x, vy+y, top) for vx, vy, _ in shape["vertex"][20:24]]
        roof["texcoord"] += [(vx/facade_tile_m, vy/facade_tile_m) for vx, vy, _ in shape["vertex"][20:24]]
        roof["face"] += [tuple(offset+k-20 for k in face) for face in shape["face"][10:12]]
    city_geoms = []
    batch_buildings = {}
    for i, ((mat, _x, _y, bands), mesh) in enumerate(city_batches.items()):
        name = f"a2_city_batch{i}"
        batch_buildings[name] = mesh.pop("buildings")
        b.meshes[name] = mesh
        roof_name = name+"_roof"
        b.meshes[roof_name] = roof_batches[(mat, _x, _y, bands)]
        for band in bands:
            band_names[band].extend((name, roof_name))
        city_geoms.append(
            dict(name=name, type="mesh", mesh_name=name, pos=(0, 0, 0), mat=MATERIAL_ALIASES[mat], collide=False)
        )
        city_geoms.append(dict(name=roof_name, type="mesh", mesh_name=roof_name,
                               pos=(0, 0, 0), mat=ROOF_MATERIAL, collide=False))
    result.update(
        ROOMS=layout.ROOMS,
        FURNITURE=furniture,
        ARCHITECTURE=architecture,
        RES_MESHES=b.meshes,
        SKYLINE_GEOMS=city_geoms,
        GEOM_BANDS={**{name: {"names": tuple(names)} for name, names in band_names.items()},
                    "host": {"names": tuple(t["name"] for t in source["HOST_TOWER"])}},
        CITY_BAND_BUILDINGS=band_buildings,
        CITY_BATCH_BUILDINGS=batch_buildings,
    )
    result["STEP_MAT"] = "a2_oak"
    result["RAIL_RGBA"] = (0.19, 0.20, 0.19, 1.0)
    result["VISUAL"].update(
        headlight_diffuse=".30 .30 .28",
        headlight_ambient=".38 .38 .36",
        headlight_specular=".04 .04 .04",
        shadowsize=2048,
    )
    # 真实材质分组：软垫浅亚麻，木框保留原纹理和柔和高光。
    result["DECOR_MATERIAL_OVERRIDES"] = {
        "armchair": {
            "1": dict(texture=None, rgba=".78 .74 .66 1", specular=0.035, shininess=0.1),
            "0": dict(specular=0.2, shininess=0.3),
        },
        # Its original UVs form a baked atlas, not metric wood coordinates. A
        # neutral oak finish avoids stretching a floorboard texture over it.
        "dining_chair": {
            "all": dict(texture=None, rgba=".70 .63 .52 1", specular=0.12, shininess=0.24)
        },
        "coffee_table": {"all": dict(specular=0.22, shininess=0.42)},
    }
    return result
