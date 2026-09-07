#!/usr/bin/env python3
"""Residence regressions: reference bytes, physical estate routes and pool hazards."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest  # noqa: E402
from scenes.collision import collision_ray  # noqa: E402
from tools import make_house  # noqa: E402

BASELINE = "0c1fdcebdeb21134b368b170fbe7a12810e812a2"  # Last saved scene-library revision before this upgrade.
BODY_RADIUS = 0.30
BODY_LEVELS = (0.30, 0.75, 1.35)
SAMPLE_SPACING = 0.20


def references(ref):
    paths = [
        "scenes/house1",
        "scenes/apt1",
        "docs/images/house1",
        "docs/images/apt1",
        "robots",
        "decor",
        "textures/house3",
    ]
    files = (
        subprocess.check_output(
            ["git", "ls-tree", "-rz", "--name-only", ref, "--", *paths], cwd=ROOT
        )
        .decode()
        .rstrip("\0")
        .split("\0")
    )
    for name in files:
        old = subprocess.check_output(["git", "show", f"{ref}:{name}"], cwd=ROOT)
        assert (ROOT / name).read_bytes() == old, f"Reference asset changed: {name}"
    hashes = {}
    for scene in ("house1", "apt1"):
        make_house.use_scene(scene)
        for robot in ("go2", "g1"):
            name = manifest.scene_filename(scene, robot)
            old = subprocess.check_output(["git", "show", f"{ref}:{name}"], cwd=ROOT)
            assert make_house.build(robot).encode() == old, f"Regenerated reference changed: {name}"
            assert (ROOT / name).read_bytes() == old, f"Reference build changed: {name}"
            hashes[name] = hashlib.sha256(old).hexdigest()
    return dict(source_files=len(files), generated=hashes)


def estate():
    layout = manifest.load_layout("house2")
    m = mujoco.MjModel.from_xml_path(str(ROOT / "build/house2-g1.xml"))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    def ray(p, v):
        return collision_ray(m, d, p, v)

    samples = 0
    for route in layout.ESTATE["routes"]:
        for a, b in zip(route, route[1:]):
            a = np.array(a, float)
            b = np.array(b, float)
            delta = b - a
            n = max(2, int(np.linalg.norm(delta) / SAMPLE_SPACING) + 1)
            for p in np.linspace(a, b, n):
                for dx, dy in (
                    (0, 0),
                    (BODY_RADIUS, 0),
                    (-BODY_RADIUS, 0),
                    (0, BODY_RADIUS),
                    (0, -BODY_RADIUS),
                ):
                    distance, g = ray((*(p + [dx, dy]), 0.20), (0, 0, -1))
                    assert 0 <= distance <= 0.205, (
                        f"Unsupported route at {p + [dx, dy]}: {distance}"
                    )
                for z in BODY_LEVELS:
                    for direction in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                        distance, g = ray((*p, z), direction)
                        assert distance < 0 or distance >= BODY_RADIUS - 0.002, (
                            f"Blocked route at {p}, z={z}: {m.geom(g).name}/{distance}"
                        )
                samples += 1
    sx, sy, ex, ey = layout.ESTATE["site"]
    boundary_samples = 0
    for z in BODY_LEVELS:
        for y in np.linspace(sy + 0.25, ey - 0.25, 140):
            for x, v in ((sx + 0.5, (-1, 0, 0)), (ex - 0.5, (1, 0, 0))):
                distance, g = ray((x, y, z), v)
                assert 0 <= distance <= 0.51, f"Estate side gap: {(x, y, z)}"
                boundary_samples += 1
        for x in np.linspace(sx + 0.25, ex - 0.25, 160):
            for y, v in ((sy + 0.5, (0, -1, 0)), (ey - 0.5, (0, 1, 0))):
                distance, g = ray((x, y, z), v)
                assert 0 <= distance <= 0.51, f"Estate end gap: {(x, y, z)}"
                boundary_samples += 1
    px, py, qx, qy = layout.ESTATE["pool"]
    pool_samples = 0
    for x in np.linspace(px + 0.4, qx - 0.4, 12):
        for y in np.linspace(py + 0.4, qy - 1.6, 28):
            distance, g = ray((x, y, 0.30), (0, 0, -1))
            assert abs(distance - (0.30 + layout.ESTATE["pool_depth"])) < 1e-6, (
                f"Pool has a hidden floor at {(x, y)}: {distance}"
            )
            assert "pool_bottom" in m.geom(g).name
            pool_samples += 1
    water = m.geom("h2_pool_water_finish").id
    assert not m.geom_contype[water] and not m.geom_conaffinity[water]
    # A regression that makes water collidable must change the same physical query.
    m.geom_contype[water] = 1
    bad, _ = ray(((px + qx) / 2, (py + qy) / 2, 0.30), (0, 0, -1))
    assert bad < 0.5, "Fault injection did not catch supporting water"
    m.geom_contype[water] = 0
    good, _ = ray(((px + qx) / 2, (py + qy) / 2, 0.30), (0, 0, -1))
    assert abs(good - 1.8) < 1e-6
    # Baths remain hollow: inaccessible footprint annotation must not fill geometry.
    for room in ("bathroom", "master_bath"):
        base = next(it for it in layout.FURNITURE if it["name"] == f"h2_{room}_tub_base")
        x, y, z = base["pos"]
        floor = layout.FLOOR_Z(layout.ROOMS[room]["floor"])
        dist, g = ray((x, y, floor + 0.7), (0, 0, -1))
        assert abs((floor + 0.7 - dist) - (floor + z + base["size"][2] / 2)) < 1e-6
    return dict(
        route_samples=samples,
        boundary_samples=boundary_samples,
        pool_samples=pool_samples,
        water_fault_injection=True,
        hollow_baths=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"reference_scenes": references(args.baseline), "house2_estate": estate()}
    for scene in ("house2", "apt2"):
        make_house.use_scene(scene)
        for robot in ("go2", "g1"):
            assert (
                make_house.build(robot).encode()
                == (ROOT / manifest.scene_filename(scene, robot)).read_bytes()
            ), f"Stale build: {scene}/{robot}"
    report["passed"] = True
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n")


if __name__ == "__main__":
    main()
