#!/usr/bin/env python3
"""Canonical residences: inherited environment, real estate routes and pool hazards."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest  # noqa: E402
from scenes.collision import collision_ray  # noqa: E402
from tools import make_house  # noqa: E402

BASELINE = ROOT / "docs/residences/migration/baseline.json"
BODY_RADIUS = 0.30
BODY_LEVELS = (0.30, 0.75, 1.35)
SAMPLE_SPACING = 0.20


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def references(path):
    from scenes.environments import manhattan
    from scenes.apply_time_preset import _band_geoms
    from scenes.time_cycle import TimeCycle

    baseline = json.loads(Path(path).read_text())
    for name, expected in baseline["assets"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    for name, expected in baseline["environment"].items():
        assert digest(getattr(manhattan, name)) == expected, name
    for phase, expected in baseline["time"].items():
        assert digest(manhattan.LIGHTS_BY_TIME[phase]) == expected, phase
    layout = manifest.load_layout("apt")
    for name in (
        "SKYLINE",
        "GROUND_SLABS",
        "ELEV",
        "FLOOR_TO_FLOOR",
        "PARK_NEAR_Y",
        "PARK_W",
        "PARK_L",
        "CITY_SPAN",
        "SKYBOX",
        "GLASS_THICK",
    ):
        assert digest(getattr(layout, name)) == baseline["environment"][name], name
    buildings = {row[0]: row for row in layout.SKYLINE}
    emitted = [name for names in layout.CITY_BATCH_BUILDINGS.values() for name in names]
    assert len(emitted) == len(set(emitted)) == baseline["building_count"]
    assert set(emitted) == set(buildings)
    for batch, names in layout.CITY_BATCH_BUILDINGS.items():
        # Check each box against its original footprint and absolute elevation.
        vertices = np.asarray(layout.RES_MESHES[batch]["vertex"]).reshape(len(names), -1, 3)
        for name, chunk in zip(names, vertices):
            _, x, y, width, depth, top, _ = buildings[name]
            assert np.allclose(chunk.min(axis=0), (x - width / 2, y - depth / 2, -layout.ELEV))
            assert np.allclose(chunk.max(axis=0), (x + width / 2, y + depth / 2, top))
        roof = np.asarray(layout.RES_MESHES[batch + "_roof"]["vertex"]).reshape(len(names), -1, 3)
        for name, chunk in zip(names, roof):
            _, x, y, width, depth, top, _ = buildings[name]
            assert np.allclose(chunk.min(axis=0), (x - width / 2, y - depth / 2, top))
            assert np.allclose(chunk.max(axis=0), (x + width / 2, y + depth / 2, top))
    assert {k: len(v) for k, v in layout.CITY_BAND_BUILDINGS.items()} == baseline["city_bands"]
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename("apt", "g1")))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    band_counts = {name: len(_band_geoms(m, layout, name)) for name in layout.GEOM_BANDS}
    assert all(band_counts.values())
    cycle = TimeCycle(m, "apt")
    qpos, qvel = d.qpos.copy(), d.qvel.copy()
    collisions = m.geom_contype.copy(), m.geom_conaffinity.copy()
    for phase in layout.PHASES:
        assert layout.LIGHTS_BY_TIME[phase].get("geom_tint", []) == manhattan.LIGHTS_BY_TIME[
            phase
        ].get("geom_tint", [])
        cycle.set(phase)
        assert np.array_equal(d.qpos, qpos) and np.array_equal(d.qvel, qvel)
        assert np.array_equal(m.geom_contype, collisions[0]) and np.array_equal(
            m.geom_conaffinity, collisions[1]
        )
        for tint in layout.LIGHTS_BY_TIME[phase].get("geom_tint", []):
            ids = _band_geoms(m, layout, tint["where"])
            rgba = tint["rgba"]
            expected = np.fromstring(rgba, sep=" ") if isinstance(rgba, str) else np.asarray(rgba)
            assert np.allclose(m.geom_rgba[ids], expected)
    cycle.set("day")
    assert np.array_equal(m.geom_rgba, cycle.base["geom_rgba"])
    assert len(layout.WALL_ARTS) == baseline["wall_art_count"]
    for i in range(len(layout.WALL_ARTS)):
        assert m.geom(f"art{i}").id >= 0
    shots = manifest.load_sibling("apt", "shots")
    pair = [shot for shot in shots.EYE if shot[0] in ("P1", "P2")]
    assert len(pair) == 2 and pair[0][3] == pair[1][3]
    assert pair[0][2][0] != pair[1][2][0]
    assert set(manifest.keys()) == {"apt", "house"}
    for retired in ("apt1", "apt2", "house1", "house2"):
        try:
            manifest.load_layout(retired)
        except KeyError:
            pass
        else:
            raise AssertionError(f"Retired scene remains registered: {retired}")
    return dict(
        source_revision=baseline["revision"],
        preserved_assets=len(baseline["assets"]),
        buildings=len(emitted),
        city_bands=baseline["city_bands"],
        rendered_bands=band_counts,
        wall_art=len(layout.WALL_ARTS),
        time_phases=list(layout.PHASES),
        parallax_distance_m=shots.PARALLAX_DISTANCE,
    )


def mesh_texture_bindings(model):
    """Explicit mesh UVs select GL_TEXTURE_2D; binding a cubemap is invalid."""
    checked = 0
    for geom in range(model.ngeom):
        if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        if model.mesh_texcoordadr[model.geom_dataid[geom]] < 0 or model.geom_matid[geom] < 0:
            continue
        for texture in model.mat_texid[model.geom_matid[geom]]:
            if texture >= 0:
                assert model.tex_type[texture] == mujoco.mjtTexture.mjTEXTURE_2D, model.geom(
                    geom
                ).name
                checked += 1
    return checked


def apartment_fixtures():
    from scenes.apt.service_rooms import TUB_BOTTOM_TOP, TUB_RIM_TOP, TUB_SIZE

    layout = manifest.load_layout("apt")
    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename("apt", "g1")))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    base = next(it for it in layout.FURNITURE if it["name"] == "a2_primary_tub_base")
    x, y, _ = base["pos"]
    z = layout.FLOOR_Z(layout.ROOMS["primary_bath"]["floor"])
    samples = 0
    for dx in np.linspace(-TUB_SIZE[0] / 4, TUB_SIZE[0] / 4, 5):
        for dy in np.linspace(-TUB_SIZE[1] / 3, TUB_SIZE[1] / 3, 7):
            dist, geom = collision_ray(m, d, (x + dx, y + dy, z + 1), (0, 0, -1))
            assert abs(z + 1 - dist - (z + TUB_BOTTOM_TOP)) < 1e-6
            assert m.geom(geom).name == "furn_a2_primary_tub_base"
            samples += 1
    for it in layout.FURNITURE:
        if it["name"] in {"a2_primary_tub_" + side for side in "nswe"}:
            px, py, _ = it["pos"]
            dist, _ = collision_ray(m, d, (px, py, z + 1), (0, 0, -1))
            assert abs(z + 1 - dist - (z + TUB_RIM_TOP)) < 1e-6
    for name in ("washer_body", "dryer_body", "primary_bath_wc_lid", "guest_bath_wc_lid"):
        assert m.geom("furn_a2_" + name).id >= 0
    return dict(hollow_tub_samples=samples, tub_rim_samples=4, static_service_fixtures=True)


def estate():
    layout = manifest.load_layout("house")
    m = mujoco.MjModel.from_xml_path(str(ROOT / "build/house-g1.xml"))
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
    report = {
        "inherited_features": references(args.baseline),
        "house_estate": estate(),
        "apartment_fixtures": apartment_fixtures(),
        "mesh_texture_bindings": {},
    }
    for scene in manifest.keys():
        make_house.use_scene(scene)
        for robot in ("go2", "g1"):
            assert (
                make_house.build(robot).encode()
                == (ROOT / manifest.scene_filename(scene, robot)).read_bytes()
            ), f"Stale build: {scene}/{robot}"
            m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename(scene, robot)))
            report["mesh_texture_bindings"][f"{scene}/{robot}"] = mesh_texture_bindings(m)
    report["passed"] = True
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n")


if __name__ == "__main__":
    main()
