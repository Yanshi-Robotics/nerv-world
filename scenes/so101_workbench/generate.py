"""Build manipulation arenas from one layout and object catalogue.

Scene parameters live in JSON. Imported robot assets remain unmodified. Flexible
objects use native MuJoCo flexes; annular disks are convex sectors with a real hole.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.json")
CATALOG = Path(__file__).with_name("objects.json")
IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
# Palette only: colors encode disk identity, never a computed task outcome.
DISK_COLORS = [
    (0.65, 0.25, 0.7, 1),
    (0.25, 0.45, 0.9, 1),
    (0.2, 0.7, 0.6, 1),
    (0.95, 0.65, 0.2, 1),
    (0.9, 0.3, 0.3, 1),
]


def vec(values):
    return " ".join(f"{float(v):.9g}" for v in values)


def element(parent, tag, **attributes):
    return ET.SubElement(
        parent,
        tag,
        {k: vec(v) if isinstance(v, (list, tuple)) else str(v) for k, v in attributes.items()},
    )


def camera_axes(position, target, up):
    import numpy as np

    z = np.asarray(position, float) - np.asarray(target, float)
    z /= np.linalg.norm(z)
    x = np.cross(np.asarray(up, float), z)
    if np.linalg.norm(x) < 1e-8:
        raise ValueError("camera up vector is parallel to viewing direction")
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return [*x, *y]


def read_configuration(config=CONFIG, catalog=CATALOG):
    cfg = json.loads(Path(config).read_text())
    objects = json.loads(Path(catalog).read_text())
    if cfg.get("schema_version") != 1:
        raise ValueError("unsupported workbench configuration schema")
    for key, obj in objects.items():
        if not IDENTIFIER.fullmatch(key):
            raise ValueError(f"invalid object identifier: {key}")
        if obj["kind"] not in ("box", "cylinder", "flex_volume", "flex_sheet", "mesh"):
            raise ValueError(f"unsupported object kind: {obj['kind']}")
        for value in [*obj["size_m"], obj["mass_kg"]]:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key}: sizes and mass must be finite positive numbers")
        if obj["kind"].startswith("flex_"):
            dim = 3 if obj["kind"] == "flex_volume" else 2
            if len(obj["grid"]) != 3 or any(int(n) != n or n < 2 for n in obj["grid"][:dim]):
                raise ValueError(f"{key}: invalid flex grid")
            if not 0 <= obj["poisson"] < 0.5 or obj["young_pa"] <= 0:
                raise ValueError(f"{key}: invalid elasticity")
            if dim == 2 and obj["grid"][2] != 1:
                raise ValueError(f"{key}: sheet grid must have one layer")
        if obj["kind"] == "mesh":
            mesh = Path(obj["mesh_file"]).expanduser()
            obj["mesh_file"] = str((Path(catalog).resolve().parent / mesh).resolve())
    return cfg, objects


def build(preset, output, *, replacements=None, config=CONFIG, catalog=CATALOG):
    cfg, objects = read_configuration(config, catalog)
    if preset not in cfg["presets"]:
        raise ValueError(f"unknown preset {preset!r}")
    scene = copy.deepcopy(cfg["presets"][preset])
    replacements = replacements or {}
    slots = {obj["id"] for obj in scene["objects"]}
    if set(replacements) - slots:
        raise ValueError(f"unknown object slots: {set(replacements) - slots}")
    for obj in scene["objects"]:
        obj["type"] = replacements.get(obj["id"], obj["type"])
        if obj["type"] not in objects:
            raise ValueError(f"unknown object {obj['type']!r}")
    out = Path(output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    robot_path = (ROOT / cfg["robot"]["model"]).resolve()
    robot = ET.parse(robot_path).getroot()
    model = ET.Element("mujoco", model=f"so101-{preset}")
    compiler = copy.deepcopy(robot.find("compiler"))
    compiler.set(
        "meshdir",
        os.path.relpath(robot_path.parent / compiler.get("meshdir", "assets"), out.parent),
    )
    model.append(compiler)
    physics = cfg["physics"]
    element(
        model,
        "option",
        timestep=physics["timestep_s"],
        gravity=physics["gravity"],
        integrator=physics["integrator"],
        iterations=physics["iterations"],
    )
    for child in robot:
        if child.tag in ("default", "asset", "contact", "equality", "actuator", "sensor"):
            model.append(copy.deepcopy(child))
    asset = model.find("asset")
    if asset is None:
        asset = ET.SubElement(model, "asset")
    element(
        asset,
        "texture",
        name="bench_grid",
        type="2d",
        builtin="checker",
        rgb1=[0.19, 0.22, 0.27],
        rgb2=[0.23, 0.26, 0.31],
        width=256,
        height=256,
    )
    element(asset, "material", name="floor_material", texture="bench_grid", texrepeat=[4, 4])
    world = ET.SubElement(model, "worldbody")
    table = cfg["table"]
    surface = table["height_m"]
    for child in robot.find("worldbody"):
        c = copy.deepcopy(child)
        if c.tag == "body" and c.get("name") == cfg["robot"]["base_body"]:
            c.set("pos", vec([*cfg["robot"]["position_xy"], surface]))
            yaw = cfg["robot"]["yaw_rad"]
            c.set("quat", vec([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]))
            camera = next(
                cam for cam in c.iter("camera") if cam.get("name") == cfg["robot"]["wrist_camera"]
            )
            camera.set("name", "wrist")
        world.append(c)
    element(world, "light", pos=[0, -0.3, 2], dir=[0, 0, -1], diffuse=[0.8, 0.8, 0.8])
    element(world, "geom", name="floor", type="plane", size=[2, 2, 0.02], material="floor_material")
    x, y = table["center_xy"]
    sx, sy = table["size_xy"]
    t = table["thickness_m"]
    element(
        world,
        "geom",
        name="table",
        type="box",
        pos=[x, y, surface - t / 2],
        size=[sx / 2, sy / 2, t / 2],
        rgba=table["rgba"],
    )
    leg = table["leg_width_m"]
    for i, (dx, dy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        element(
            world,
            "geom",
            name=f"leg_{i}",
            type="box",
            pos=[x + dx * (sx / 2 - leg), y + dy * (sy / 2 - leg), (surface - t) / 2],
            size=[leg / 2, leg / 2, (surface - t) / 2],
            rgba=[0.22, 0.25, 0.3, 1],
        )
    for name, cam in cfg["cameras"].items():
        element(
            world,
            "camera",
            name=name,
            pos=cam["position"],
            xyaxes=camera_axes(cam["position"], cam["target"], cam["up"]),
            fovy=cam["fovy_deg"],
        )
    metadata = {
        "schema_version": 1,
        "preset": preset,
        "label": scene["label"],
        "source_config_sha256": hashlib.sha256(Path(config).read_bytes()).hexdigest(),
        "source_catalog_sha256": hashlib.sha256(Path(catalog).read_bytes()).hexdigest(),
        "surface_z": surface,
        "objects": [],
        "baskets": [],
        "validation": cfg["validation"],
        "initial_joints": cfg["robot"]["initial_joints"],
    }
    for basket in scene["baskets"]:
        meta = add_basket(world, basket, cfg["basket"], surface)
        metadata["baskets"].append(meta)
    for slot in scene["objects"]:
        metadata["objects"].append(add_object(world, asset, slot, objects[slot["type"]], cfg, out))
    if preset == "hanoi-five":
        metadata["hanoi"] = add_hanoi(world, asset, cfg["hanoi"], surface)
    visual = element(model, "visual")
    element(visual, "headlight", ambient=[0.3, 0.3, 0.3], diffuse=[0.6, 0.6, 0.6])
    element(visual, "global", offwidth=1280, offheight=960)
    ET.indent(model)
    ET.ElementTree(model).write(out, encoding="utf-8", xml_declaration=True)
    metadata["arena"] = out.name
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def add_basket(world, basket, spec, surface):
    x, y = basket["xy"]
    sx, sy = spec["inner_size_xy"]
    h = spec["height_m"]
    w = spec["wall_m"]
    body = element(world, "body", name=basket["id"], pos=[x, y, surface])
    walls = [
        ("bottom", [0, 0, w / 2], [sx / 2 + w, sy / 2 + w, w / 2]),
        ("left", [-sx / 2 - w / 2, 0, h / 2], [w / 2, sy / 2 + w, h / 2]),
        ("right", [sx / 2 + w / 2, 0, h / 2], [w / 2, sy / 2 + w, h / 2]),
        ("back", [0, -sy / 2 - w / 2, h / 2], [sx / 2, w / 2, h / 2]),
        ("front", [0, sy / 2 + w / 2, h / 2], [sx / 2, w / 2, h / 2]),
    ]
    for name, pos, size in walls:
        element(
            body,
            "geom",
            name=f"{basket['id']}_{name}",
            type="box",
            pos=pos,
            size=size,
            rgba=basket["rgba"],
        )
    return {**basket, "inner_size_xy": [sx, sy], "bottom_z": surface + w, "rim_z": surface + h}


def add_object(world, asset, slot, spec, cfg, output):
    name = slot["id"]
    sx, sy, sz = spec["size_m"]
    radius = spec.get("radius_m", 0)
    z = cfg["table"]["height_m"] + sz / 2 + radius + cfg["validation"]["surface_tolerance_m"]
    common = {"name": name, "pos": [*slot["xy"], z]}
    contact = {
        "friction": cfg["physics"]["object_friction"],
        "solref": cfg["physics"]["contact_solref"],
    }
    kind = spec["kind"]
    if kind.startswith("flex_"):
        grid = spec["grid"]
        dim = 3 if kind == "flex_volume" else 2
        spacing = [s / (n - 1) if n > 1 else sz for s, n in zip(spec["size_m"], grid)]
        if dim == 2:
            # The unused third grid axis must also clear the compiler's radius check.
            spacing[2] = max(spacing[:2])
        flex = element(
            world,
            "flexcomp",
            **common,
            type="grid",
            dim=dim,
            count=grid,
            spacing=spacing,
            mass=spec["mass_kg"],
            radius=radius,
            rgba=spec["rgba"],
        )
        element(
            flex,
            "elasticity",
            young=spec["young_pa"],
            poisson=spec["poisson"],
            damping=spec["elastic_damping_s"],
            **({"thickness": sz} if dim == 2 else {}),
        )
        element(flex, "contact", selfcollide=spec["self_collision"], **contact)
    else:
        body = element(world, "body", **common)
        element(body, "freejoint", name=f"{name}_free")
        kwargs = {
            "type": kind,
            "size": [sx / 2, sy / 2, sz / 2] if kind == "box" else [sx / 2, sz / 2],
        }
        if kind == "mesh":
            meshfile = Path(spec["mesh_file"]).expanduser().resolve()
            if not meshfile.is_file():
                raise ValueError(f"object mesh missing: {meshfile}")
            element(
                asset,
                "mesh",
                name=f"{name}_mesh",
                file=os.path.relpath(meshfile, output.parent),
                scale=spec.get("mesh_scale", [1, 1, 1]),
            )
            kwargs = {"type": "mesh", "mesh": f"{name}_mesh"}
        element(
            body,
            "geom",
            name=f"{name}_geom",
            mass=spec["mass_kg"],
            rgba=spec["rgba"],
            **contact,
            **kwargs,
        )
    return {
        **slot,
        "kind": kind,
        "label": spec["label"],
        "size_m": spec["size_m"],
        "mass_kg": spec["mass_kg"],
        "flex": name if kind.startswith("flex_") else None,
        "body": None if kind.startswith("flex_") else name,
        "material_note": spec.get("note", "Rigid collision approximation."),
    }


def add_hanoi(world, asset, spec, surface):
    base_h = spec["base_height_m"]
    peg_h = spec["peg_height_m"]
    h = spec["disk_height_m"]
    for i, xy in enumerate(spec["peg_xy"]):
        element(
            world,
            "geom",
            name=f"peg_base_{i}",
            type="cylinder",
            pos=[*xy, surface + base_h / 2],
            size=[max(spec["disk_radii_m"]) + spec["peg_radius_m"], base_h / 2],
            rgba=[0.55, 0.4, 0.25, 1],
        )
        element(
            world,
            "geom",
            name=f"peg_{i}",
            type="cylinder",
            pos=[*xy, surface + base_h + peg_h / 2],
            size=[spec["peg_radius_m"], peg_h / 2],
            rgba=[0.85, 0.85, 0.8, 1],
        )
    disks = []
    count = spec["segments"]
    inner = spec["hole_radius_m"]
    if inner <= spec["peg_radius_m"] or count < 8:
        raise ValueError("disk hole must clear peg; ring needs >=8 sectors")
    for i, r in enumerate(spec["disk_radii_m"]):
        if r <= inner:
            raise ValueError("disk radius must exceed hole radius")
        name = f"disk_{i}"
        body = element(
            world,
            "body",
            name=name,
            pos=[*spec["peg_xy"][spec["source_peg"]], surface + base_h + (i + 0.5) * h],
        )
        element(body, "freejoint", name=f"{name}_free")
        for k in range(count):
            angles = [2 * math.pi * k / count, 2 * math.pi * (k + 1) / count]
            points = [
                [rad * math.cos(a), rad * math.sin(a), z]
                for z in (-h / 2, h / 2)
                for rad in (inner, r)
                for a in angles
            ]
            mesh = f"{name}_sector_{k}"
            element(asset, "mesh", name=mesh, vertex=[v for p in points for v in p])
            element(
                body,
                "geom",
                name=mesh,
                type="mesh",
                mesh=mesh,
                mass=spec["mass_kg"] / count,
                rgba=DISK_COLORS[i % len(DISK_COLORS)],
            )
        disks.append({"body": name, "radius_m": r, "height_m": h})
    return {
        **spec,
        "disks": disks,
        "base_z": surface + base_h,
        "minimum_symbolic_moves": 2 ** len(disks) - 1,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(json.loads(CONFIG.read_text())["presets"]))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--object", action="append", default=[], metavar="SLOT=CATALOG_ID")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.all and not args.preset:
        parser.error("choose --preset or --all")
    if args.all and (args.object or args.output):
        parser.error("--all cannot be combined with --object/--output")
    overrides = {}
    for value in args.object:
        key, sep, item = value.partition("=")
        if not sep:
            parser.error("--object requires SLOT=CATALOG_ID")
        overrides[key] = item
    presets = json.loads(args.config.read_text())["presets"] if args.all else [args.preset]
    for preset in presets:
        output = args.output or ROOT / "build" / f"so101-{preset}.xml"
        metadata = build(
            preset, output, replacements=overrides, config=args.config, catalog=args.catalog
        )
        if args.output is None:
            cfg, _ = read_configuration(args.config, args.catalog)
            descriptor = {
                "name": f"so101-{preset}",
                "kind": "sim",
                "engine": "mujoco",
                "label": f"SO-101: {metadata['label']}",
                "assets_root": "worlds",
                "supports": {"arm-lerobot-so101": f"build/so101-{preset}.xml"},
                "spawn": {"initial_joints": metadata["initial_joints"]},
                "ambient": [],
                "physics": {"dt": cfg["physics"]["timestep_s"], **cfg["runtime"]},
            }
            directory = ROOT / descriptor["name"]
            directory.mkdir(exist_ok=True)
            # JSON is a YAML subset; keep the asset generator free of a YAML dependency.
            (directory / "world.yaml").write_text(json.dumps(descriptor, indent=2) + "\n")
            if preset == "hanoi-five":
                task = (
                    "Move all five rings from the initial side peg to the opposite side peg. "
                    "Move only one top ring at a time and never put a larger ring on a smaller ring. "
                    "This scene supplies no automatic ring-moving skill."
                )
            else:
                task = "Place each visible object completely inside its assigned basket, then release it.\n\n"
                task += "\n".join(
                    f"- {o['label']} into the {o['basket']} basket." for o in metadata["objects"]
                )
            constraints = (
                "This is a physics scene, not a trained task policy. The body exposes measured joints "
                "and the top/wrist cameras with bounded joint/gripper commands. Do not assume the real "
                "ACT has a matching simulation deployment. Operator overview, object coordinates and "
                "task scores are not agent observations. Deformable materials are uncalibrated approximations."
            )
            (directory / "guidance.md").write_text(task + "\n\n" + constraints + "\n")
        print(json.dumps({"preset": preset, "arena": str(output), "objects": metadata["objects"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
