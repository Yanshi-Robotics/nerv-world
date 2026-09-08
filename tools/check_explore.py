#!/usr/bin/env python3
"""CPU checks for Explore source freshness, geometry, materials and node metadata."""

from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest
from scenes.operator import SceneRuntime
from scenes.explore import classify, source_files, source_hash, sha256, TO_GLB


def load_glb(path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", raw)
    assert magic == b"glTF" and version == 2 and length == len(raw)
    size, kind = struct.unpack_from("<I4s", raw, 12)
    assert kind == b"JSON"
    tree = json.loads(raw[20 : 20 + size])
    offset = 20 + size
    size, kind = struct.unpack_from("<I4s", raw, offset)
    assert kind == b"BIN\0"
    return tree, raw[offset + 8 : offset + 8 + size]


def check(scene, classification_only=False):
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename(scene, "g1")))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    runtime = SceneRuntime(m, d, scene)
    catalogue = runtime.catalogue()
    rooms = {room["id"] for room in catalogue["rooms"]}
    assert all(f.get("room") is None or f["room"] in rooms for f in catalogue["facilities"])
    visible = [g for g in range(m.ngeom) if m.geom_group[g] in (0, 1)]
    classes = {m.geom(g).name: classify(m, d, g, runtime._catalogue) for g in visible}
    for name, info in classes.items():
        if name.startswith(("furn_", "dg_", "hc_", "ix_")):
            assert info["role"] == "furniture", (name, info)
        if name.startswith(("floor_", "slab")):
            assert info["role"] == "floor", (name, info)
        if info["role"] == "floor":
            assert info["levels"] == [info["floor"]], (name, info)
    assert any(c["role"] == "floor" for c in classes.values())
    assert any(c["role"] == "furniture" for c in classes.values())
    for name in ("stair_well_wall", "stair_top_guard", "stair0_up_rail"):
        assert classes[name]["role"] == "wall", (name, classes[name])
    for name in ("stair0_up_s0", "stair0_mid"):
        assert classes[name]["role"] == "stairs", (name, classes[name])
    for name, info in classes.items():
        if name.startswith("stair_f") and name.endswith("_floor"):
            assert info["role"] == "floor", (name, info)
    if scene == "apt":
        assert [f["label"]["en"] for f in catalogue["floors"]] == ["Floor 1 / 62F", "Floor 2 / 63F"]
        chairs = [f for f in catalogue["facilities"] if f["id"].startswith("ix_dn_")]
        assert len(chairs) == 6 and all("dining chair" in f["label"]["en"] for f in chairs)
        for prefix in ("furn_gr_sofa_back", "furn_a2_library_", "furn_kt_st0_", "furn_dn_table_"):
            found = [c for n, c in classes.items() if n.startswith(prefix)]
            assert found and all(c["role"] == "furniture" for c in found), prefix
        target = next(f for f in catalogue["facilities"] if f["id"] == "fridge_task_target")
        assert np.allclose(target["bounds"], runtime.task_status()["target"]["world_bounds"])
        sink = [
            f["id"] for f in catalogue["facilities"] if f.get("joint") and "sink__handle" in f["id"]
        ]
        assert len(sink) == 2
        assert any(set(sink).issubset(c["facilities"]) for c in classes.values())
    else:
        assert next(r for r in catalogue["rooms"] if r["id"] == "view_terrace")["floor"] == 2
        for boundary in ("estate_gate", "swimming_pool"):
            assert any(boundary in c["facilities"] for c in classes.values())
        for name, expected in (
            ("h2_view_terrace_floor_finish", "floor"),
            ("h2_terrace_guard_front_finish", "wall"),
            ("h2_entry_canopy_finish", "roof"),
            ("h2_entry_soffit_finish", "ceiling"),
        ):
            assert classes[name]["role"] == expected, (name, classes[name])
        assert all(not f["label"]["en"].startswith("Rc ") for f in catalogue["facilities"])
    assert sum(f["id"].startswith("passage_") for f in catalogue["facilities"]) == len(
        runtime._catalogue.layout.DOORS
    )
    assert sum(f["id"].startswith("stairs_stop_") for f in catalogue["facilities"]) == len(
        catalogue["floors"]
    )
    report = dict(scene=scene, classification=dict(Counter(c["role"] for c in classes.values())))
    from tools.check_residences import flat_routes

    report["flat_routes"] = flat_routes(m, d, runtime._catalogue.layout)
    if classification_only:
        return report
    directory = ROOT / ".cache/explore" / scene
    exported = json.loads((directory / "manifest.json").read_text())
    sources = source_files(scene)
    assert exported["sources"] == sources, "Stale source map; rerun export_explore.py"
    assert exported["source_hash"] == source_hash(sources)
    assert exported["coordinate_system"]["to_glb"] == TO_GLB
    asset = exported["assets"][0]
    path = directory / asset["path"]
    assert path.resolve().is_relative_to(directory.resolve())
    assert path.stat().st_size == asset["bytes"] and sha256(path) == asset["hash"]
    tree, binary = load_glb(path)
    assert all("uri" not in b for b in tree["buffers"])
    assert all("uri" not in image and "bufferView" in image for image in tree.get("images", []))
    transform = next(n["matrix"] for n in tree["nodes"] if n.get("name") == "mujoco")
    assert np.allclose(transform, TO_GLB)
    components = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def accessor(index):
        a = tree["accessors"][index]
        view = tree["bufferViews"][a["bufferView"]]
        assert "byteStride" not in view, "Unexpected interleaving"
        return np.frombuffer(
            binary,
            dtype=components[a["componentType"]],
            count=a["count"] * widths[a["type"]],
            offset=view.get("byteOffset", 0) + a.get("byteOffset", 0),
        ).reshape(a["count"], widths[a["type"]])

    emitted = []
    triangles = 0
    for node in tree["nodes"]:
        if "mesh" not in node:
            continue
        info = node["extras"]
        names = info["geoms"]
        emitted.extend(names)
        for name in names:
            assert name in classes, name
            assert all(
                info[key] == classes[name][key] for key in ("levels", "role", "room", "facility")
            ), name
        for primitive in tree["meshes"][node["mesh"]]["primitives"]:
            attrs = primitive["attributes"]
            positions = accessor(attrs["POSITION"])
            normals = accessor(attrs["NORMAL"])
            assert np.isfinite(positions).all() and np.isfinite(normals).all()
            assert np.allclose(np.linalg.norm(normals, axis=1), 1, atol=0.001)
            indices = accessor(primitive["indices"]).ravel()
            assert indices.max() < len(positions) and len(indices) % 3 == 0
            triangles += len(indices) // 3
            material = tree["materials"][primitive["material"]]
            if "baseColorTexture" in material.get("pbrMetallicRoughness", {}):
                uv = accessor(attrs["TEXCOORD_0"])
                assert uv.shape == (len(positions), 2) and np.isfinite(uv).all()
    assert len(emitted) == len(set(emitted)) and set(emitted) == set(classes), (
        "Missing, duplicated or robot geometry"
    )
    report.update(
        meshes=len(tree["meshes"]),
        triangles=triangles,
        bytes=asset["bytes"],
        source_hash=exported["source_hash"],
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=manifest.keys())
    parser.add_argument("--classification-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = [
        check(scene, args.classification_only)
        for scene in ([args.scene] if args.scene else manifest.keys())
    ]
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output)
