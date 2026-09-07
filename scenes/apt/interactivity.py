"""apt task objects and kitchen fixtures, in metres and floor-local coordinates."""

from scenes import furniture as F
from scenes.residence import Builder
from decor import lock

# Layout parameters: keep appliance fronts facing the kitchen aisle (-Y).
STOVE_XY = (-8.4, 6.95)
FRIDGE_XY = (-10.7, 3.8)
SINK_XY = (-8.4, 4.2)
HOOD_Z = 2.05
COUNTER_HEIGHT = 0.92
SINK_Z = COUNTER_HEIGHT + 0.03  # Basin below stone; handle sweep clears the 35 mm worktop.
ISLAND_WIDTH, ISLAND_DEPTH = 2.60, 1.10
SINK_CUTOUT = (0.70, 0.36)  # Smaller than the native outer rim (0.77 × 0.42 m).
PLATE_THICKNESS = 0.035


def apply(source):
    b = Builder("a2i")
    furniture = []
    for item in source["FURNITURE"]:
        name = item["name"]
        if name.startswith(("a2_kt_run_", "a2_sink_")) or name == "a2_kt_fridge":
            continue
        if name in ("a2_kt_island_case", "a2_kt_island_top"):
            continue
        if name.startswith(("dn_w", "dn_e")) and item.get("mesh"):
            item = dict(item, movable=True, density=220)
        furniture.append(item)

    # Open island carcass; the sink opening is cut through its stone top.
    ix, iy = SINK_XY
    for tag, dx, size in (
        ("left", -ISLAND_WIDTH/2 + PLATE_THICKNESS/2,
         (PLATE_THICKNESS, ISLAND_DEPTH, COUNTER_HEIGHT)),
        ("right", ISLAND_WIDTH/2 - PLATE_THICKNESS/2,
         (PLATE_THICKNESS, ISLAND_DEPTH, COUNTER_HEIGHT)),
    ):
        furniture.append(b.box("island_"+tag, (ix+dx, iy, COUNTER_HEIGHT/2), size, "walnut", room="kitchen"))
    rail_height = 0.08  # Join the island panels immediately below the worktop.
    for side in (-1, 1):
        furniture.append(b.box('island_rail_'+str(side),
            (ix, iy+side*(ISLAND_DEPTH-PLATE_THICKNESS)/2, COUNTER_HEIGHT-rail_height/2),
            (ISLAND_WIDTH, PLATE_THICKNESS, rail_height), 'walnut', room='kitchen'))
    hole_w, hole_d = SINK_CUTOUT
    for tag, dx, dy, width, depth in (
        ("left", -(ISLAND_WIDTH+hole_w)/4, 0, (ISLAND_WIDTH-hole_w)/2, ISLAND_DEPTH),
        ("right", (ISLAND_WIDTH+hole_w)/4, 0, (ISLAND_WIDTH-hole_w)/2, ISLAND_DEPTH),
        ("back", 0, (ISLAND_DEPTH+hole_d)/4, hole_w, (ISLAND_DEPTH-hole_d)/2),
        ("front", 0, -(ISLAND_DEPTH+hole_d)/4, hole_w, (ISLAND_DEPTH-hole_d)/2),
    ):
        furniture.append(b.box("island_top_"+tag, (ix+dx, iy+dy, COUNTER_HEIGHT),
                               (width, depth, PLATE_THICKNESS), "stone", room="kitchen", radius=0.006))
    # The stove occupies a real gap, not a mesh laid over a full-height cupboard.
    run_left, run_right = -11.0, -5.8
    stove_width = lock.size("rc_stove")[0]
    for tag, low, high in (("west", run_left, STOVE_XY[0]-stove_width/2-0.025),
                           ("east", STOVE_XY[0]+stove_width/2+0.025, run_right)):
        furniture += b.cabinet("run_"+tag, "kitchen", (low+high)/2, STOVE_XY[1],
                               high-low, 0.65, COUNTER_HEIGHT)

    fixtures = (("fridge", "rc_fridge", FRIDGE_XY, None),
                ("stove", "rc_stove", STOVE_XY, None),
                ("sink", "rc_sink", SINK_XY, SINK_Z),
                ("hood", "rc_hood", STOVE_XY, HOOD_Z))
    for name, key, (x, y), z in fixtures:
        item = F.mesh_piece("a2_"+name, "kitchen", x, y, z=z, size=lock.size(key), mesh=key)[0]
        item["articulated"] = True
        furniture.append(item)

    # Small task objects retain inertia, gravity and contacts after release.
    for name, kind, pos, size, mat, density in (
        ("can", "cylinder", (-9.25, 4.30, 1.0125), (0.065, 0.065, 0.14), "a2_ceramic", 500),
        ("fruit", "sphere", (-9.15, 3.95, 0.99), (0.09, 0.09, 0.09), "a2_walnut", 550),
        ("book", "box", (-7.45, 4.25, 0.9575), (0.20, 0.14, 0.04), "a2_linen", 350),
    ):
        item = F._p("a2_"+name, "kitchen", kind, pos, size, (1, 1, 1, 1), mat=mat)
        item.update(movable=True, density=density)
        furniture.append(item)
    for item in furniture:
        if item.get("mat", "").startswith("a2i_"):
            item["mat"] = item["mat"].replace("a2i_", "a2_", 1)
    materials = {**source['DECOR_MATERIAL_OVERRIDES'],
        'rc_fridge': {
            # Light enamel makes the cavity readable; retain the steel door atlas.
            '0': dict(texture=None, rgba='.78 .80 .77 1', specular=.12, shininess=.25),
            **{str(n):dict(texture=None, rgba='.68 .72 .71 1', specular=.15, shininess=.3)
               for n in (2,3,6,7)},
            **{str(n):dict(texture=None, rgba='.88 .94 .96 .25', specular=.35, shininess=.7)
               for n in (5,8)},
        },
        'rc_sink': {'all':dict(texture=None, rgba='.42 .46 .47 1', specular=.65, shininess=.75)},
    }
    return dict(FURNITURE=furniture, RES_MESHES={**source["RES_MESHES"], **b.meshes},
                PHYSICAL_WALKTHROUGH=True, INTERACTIVE=True, DECOR_MATERIAL_OVERRIDES=materials)
