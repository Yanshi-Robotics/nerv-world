"""Explore source fingerprints and geometry classification; no rendering dependency."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import re
from scenes import manifest

ROOT = Path(manifest.ROOT)
SCHEMA_VERSION = 1
# Column-major rotation: MuJoCo (x,y,z) becomes glTF (x,z,-y).
TO_GLB = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
COORDINATES = dict(units="m", up_axis="Z", glb_up_axis="Y", to_glb=TO_GLB)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_files(scene, robot="g1"):
    """Hash authored code, lock records and every MJCF file dependency actually used."""
    manifest.get(scene)
    files = set(ROOT.joinpath("scenes").glob("*.py"))
    files.update(ROOT.joinpath("scenes", scene).glob("*.py"))
    files.update(ROOT.joinpath("scenes/environments").glob("*.py"))
    files.update(
        ROOT.joinpath(p)
        for p in (
            "tools/make_house.py",
            "tools/export_explore.py",
            "tools/make_house_sky.py",
            "tools/make_residence_textures.py",
            "tools/make_city_textures.py",
            "tools/make_textures.py",
            "requirements-explore.txt",
            "decor/decor.lock.json",
            "decor/articulation.lock.json",
            "decor/lock.py",
            "decor/articulation.py",
            "robots/manifest.py",
            f"{scene}/world.yaml",
        )
    )
    xml = ROOT / manifest.scene_filename(scene, robot)
    trees = []

    def include(path):
        path = path.resolve()
        if path in files:
            return
        files.add(path)
        tree = ET.parse(path)
        trees.append(tree)
        for el in tree.iter("include"):
            include(path.parent / el.attrib["file"])

    include(xml)
    meshdir = texturedir = xml.parent
    for tree in trees:
        for c in tree.iter("compiler"):
            if c.get("meshdir"):
                meshdir = (xml.parent / c.get("meshdir")).resolve()
            if c.get("texturedir"):
                texturedir = (xml.parent / c.get("texturedir")).resolve()
    for tree in trees:
        for e in tree.iter():
            if e.tag not in ("mesh", "texture", "hfield"):
                continue
            for k, value in e.attrib.items():
                if k == "file" or k.startswith("file"):
                    base = meshdir if e.tag == "mesh" else texturedir
                    p = (base / value).resolve()
                    if not p.is_relative_to(ROOT):
                        raise ValueError(f"Asset outside world root: {p.name}")
                    files.add(p)
    # Time textures are runtime dependencies, including the baseline faces.
    layout = manifest.load_layout(scene)
    from scenes.apply_time_preset import sky_files

    files.update(Path(p) for p in sky_files(layout).values())
    for preset in getattr(layout, "LIGHTS_BY_TIME", {}).values():
        if preset.get("sky"):
            files.update(Path(p) for p in sky_files(layout, preset["sky"]).values())
        for name, filename in preset.get("textures", {}).items():
            decl = next(t for t in layout.TEXTURES_EXTRA if t.get("name") == name)
            files.add(ROOT / Path(decl["file"]).parent / filename)
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(files)}


def source_hash(sources):
    return hashlib.sha256(
        json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def classify(model, data, gid, catalogue):
    L = catalogue.layout
    name = model.geom(gid).name or f"geom_{gid}"
    bounds = catalogue.geometry.bounds([gid])
    center = bounds.mean(axis=0)
    room = L.room_at(*center)
    floor = L.floor_at(center[2])
    levels = [
        f
        for f in range(L.N_FLOORS)
        if bounds[1, 2] > L.FLOOR_Z(f) - 0.02 and bounds[0, 2] < L.FLOOR_Z(f) + L.STOREY_H - 0.02
    ]
    facilities = [key for key, ids in catalogue.facility_geoms.items() if gid in ids]
    facility = facilities[0] if facilities else None
    # Procedural furnishings are not all hotspots. Their generated names still
    # distinguish them from walls, windows and curtains in architectural trim.
    furnishing = name.startswith(("furn_", "dg_", "hc_", "ix_"))
    role = "furniture" if facility or furnishing else "wall"
    source_name = name.removesuffix("_finish")
    if model.geom_group[gid] == L.CEILING_GROUP:
        role = "ceiling"
    if (
        not facility
        and not furnishing
        and re.search(r"(^floor_|^slab|_floor(?:[0-9_]|$))", source_name)
    ):
        role = "floor"
    # The stair room also owns walls, floors and handrails. Only the actual
    # generated treads and landing platforms remain whole in a cutaway.
    stair_surfaces = {
        f"{flight['name']}_s{i}"
        for flight in L.STAIRS for i in range(flight["risers"])
    } | {landing["name"] for landing in L.LANDINGS}
    if source_name in stair_surfaces:
        role = "stairs"
    if "roof" in name and not name.startswith("a2_city"):
        role = "roof"
    exterior = {x["name"]: x for x in getattr(L, "EXTERIOR_GEOMS", [])}
    background_names = {x["name"] for x in getattr(L, "BACKGROUND_GEOMS", [])}
    if source_name in exterior:
        source = exterior[source_name]
        role = source.get("explore_role", "exterior")
        floor = source.get("explore_floor", floor)
    if source_name in background_names or name.startswith(("nyc", "a2_city", "h3_ground", "park_")):
        role = "background"
    if role == "background":
        levels = []
        room = None
    elif role == "floor":
        levels = [floor]
    return dict(
        floor=floor, levels=levels, room=room, facility=facility, facilities=facilities, role=role
    )
