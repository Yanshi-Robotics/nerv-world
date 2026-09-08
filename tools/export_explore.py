#!/usr/bin/env python3
"""Export actual MuJoCo visual geometry to an untracked, read-only browser GLB."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import mujoco
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenes import manifest
from scenes.operator import SceneRuntime
from scenes.explore import (
    SCHEMA_VERSION,
    COORDINATES,
    TO_GLB,
    source_files,
    source_hash,
    sha256,
    classify,
)

TEXTURE_PIXELS = 1024  # Export display textures at a bounded size; original files stay untouched.
RADIAL_SEGMENTS = 24  # Rounded primitive silhouette budget for browser display.


def export(scene_key, robot="g1", texture_pixels=TEXTURE_PIXELS):
    import trimesh
    from trimesh.visual.material import PBRMaterial

    m = mujoco.MjModel.from_xml_path(str(ROOT / manifest.scene_filename(scene_key, robot)))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    runtime = SceneRuntime(m, d, scene_key)
    scene = trimesh.Scene(base_frame="world")
    scene.graph.update(frame_to="mujoco", matrix=np.array(TO_GLB).reshape(4, 4).T)
    extras = {}
    cache = {}
    images = {}
    materials = {}
    batches = {}
    roots = {
        int(m.body_rootid[m.jnt_bodyid[m.actuator_trnid[a, 0]]])
        for a in range(m.nu)
        if int(m.actuator_trntype[a])
        in (mujoco.mjtTrn.mjTRN_JOINT, mujoco.mjtTrn.mjTRN_JOINTINPARENT)
    }

    def material(g):
        mid = int(m.geom_matid[g])
        rgba = m.geom_rgba[g].copy()
        if mid >= 0 and np.allclose(rgba, [0.5, 0.5, 0.5, 1]):
            rgba = m.mat_rgba[mid].copy()
        key = (mid, tuple(rgba))
        if key in materials:
            return materials[key]
        tid = -1 if mid < 0 else int(m.mat_texid[mid, mujoco.mjtTextureRole.mjTEXROLE_RGB])
        if tid < 0 and mid >= 0:
            tid = int(m.mat_texid[mid, mujoco.mjtTextureRole.mjTEXROLE_RGBA])
        image = None
        if tid >= 0:
            if tid not in images:
                w, h, n = int(m.tex_width[tid]), int(m.tex_height[tid]), int(m.tex_nchannel[tid])
                adr = int(m.tex_adr[tid])
                pixels = m.tex_data[adr : adr + w * h * n].reshape(h, w, n)
                # Model cube textures repeat a surface tile; skyboxes are not geoms.
                if m.tex_type[tid] == mujoco.mjtTexture.mjTEXTURE_CUBE:
                    pixels = pixels[:w]
                image = Image.fromarray(pixels[:, :, 0] if n == 1 else pixels).convert(
                    "RGBA" if n == 4 else "RGB"
                )
                image.thumbnail((texture_pixels, texture_pixels), Image.Resampling.LANCZOS)
                images[tid] = image
            image = images[tid]
        emission = 0 if mid < 0 else float(m.mat_emission[mid])
        # MuJoCo's Phong shininess is mapped monotonically to display roughness.
        roughness = (
            0.8 if mid < 0 else max(0.12, float(np.sqrt(2 / (2 + 128 * m.mat_shininess[mid]))))
        )
        mat = PBRMaterial(
            name=f"material_{len(materials)}",
            baseColorFactor=rgba,
            baseColorTexture=image,
            roughnessFactor=roughness,
            metallicFactor=0,
            emissiveFactor=(rgba[:3] * emission).tolist(),
            alphaMode="BLEND" if rgba[3] < 0.999 else "OPAQUE",
            doubleSided=bool(rgba[3] < 0.999),
        )
        materials[key] = (mat, tid)
        return mat, tid

    def geometry(g):
        kind = int(m.geom_type[g])
        s = m.geom_size[g]
        mid = int(m.geom_dataid[g])
        mat, tid = material(g)
        key = (int(kind), mid if kind == mujoco.mjtGeom.mjGEOM_MESH else tuple(s), mat.name)
        if key in cache:
            return cache[key]
        uv = None
        if kind == mujoco.mjtGeom.mjGEOM_MESH:
            va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
            vertices = m.mesh_vert[va : va + vn]
            faces = m.mesh_face[fa : fa + fn]
            # MJCF OBJ position/normal/UV indices are independent. Expand corners
            # before GLB export so UV seams and source normals remain exact.
            points = vertices[faces].reshape(-1, 3)
            normals = None
            if m.mesh_normalnum[mid]:
                na = m.mesh_normaladr[mid]
                ni = m.mesh_facenormal[fa : fa + fn]
                normals = m.mesh_normal[na + ni].reshape(-1, 3)
            if m.mesh_texcoordnum[mid]:
                ta = m.mesh_texcoordadr[mid]
                ti = m.mesh_facetexcoord[fa : fa + fn]
                if np.any(ti < 0):
                    raise ValueError(f"Incomplete UVs: {m.mesh(mid).name}")
                uv = m.mesh_texcoord[ta + ti].reshape(-1, 2)
            mesh = trimesh.Trimesh(
                points, np.arange(len(points)).reshape(-1, 3), vertex_normals=normals, process=False
            )
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            mesh = trimesh.creation.box(extents=2 * s)
        elif kind == mujoco.mjtGeom.mjGEOM_SPHERE:
            mesh = trimesh.creation.icosphere(subdivisions=2, radius=s[0])
        elif kind == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
            mesh = trimesh.creation.icosphere(subdivisions=2)
            mesh.apply_scale(s)
        elif kind == mujoco.mjtGeom.mjGEOM_CYLINDER:
            mesh = trimesh.creation.cylinder(radius=s[0], height=2 * s[1], sections=RADIAL_SEGMENTS)
        elif kind == mujoco.mjtGeom.mjGEOM_CAPSULE:
            mesh = trimesh.creation.capsule(
                radius=s[0], height=2 * s[1], count=[RADIAL_SEGMENTS, RADIAL_SEGMENTS]
            )
        elif kind == mujoco.mjtGeom.mjGEOM_PLANE:
            extent = np.array(
                [
                    max(s[0], runtime._catalogue.layout.STOREY_H * 8),
                    max(s[1], runtime._catalogue.layout.STOREY_H * 8),
                    0.005,
                ]
            )
            mesh = trimesh.creation.box(extents=2 * extent)
        else:
            raise ValueError(f"Unsupported visual geom {m.geom(g).name}: {kind}")
        if kind != mujoco.mjtGeom.mjGEOM_MESH:
            points = mesh.vertices[mesh.faces].reshape(-1, 3)
            normals = np.repeat(mesh.face_normals, 3, axis=0)
            if kind in (mujoco.mjtGeom.mjGEOM_SPHERE, mujoco.mjtGeom.mjGEOM_ELLIPSOID):
                radii = np.repeat(s[0], 3) if kind == mujoco.mjtGeom.mjGEOM_SPHERE else s
                normals = points / (radii * radii)
                normals /= np.linalg.norm(normals, axis=1, keepdims=True)
            mesh = trimesh.Trimesh(
                points, np.arange(len(points)).reshape(-1, 3), vertex_normals=normals, process=False
            )
        if tid >= 0:
            if uv is None:
                # Per-face planar coordinates retain seams on primitive boxes.
                points = mesh.vertices[mesh.faces].reshape(-1, 3)
                normals = mesh.vertex_normals[mesh.faces].reshape(-1, 3)
                projection_normals = np.repeat(mesh.face_normals, 3, axis=0)
                axes = np.argmax(np.abs(projection_normals), axis=1)
                uv = np.empty((len(points), 2))
                for axis in range(3):
                    selected = axes == axis
                    plane_axes = [a for a in range(3) if a != axis]
                    uv[selected] = points[selected][:, plane_axes]
                    if not m.mat_texuniform[m.geom_matid[g]]:
                        span = np.maximum(np.ptp(mesh.vertices[:, plane_axes], axis=0), 1e-9)
                        uv[selected] = (
                            uv[selected] - mesh.vertices[:, plane_axes].min(axis=0)
                        ) / span
                repeat = m.mat_texrepeat[m.geom_matid[g]]
                uv = uv * repeat
                mesh = trimesh.Trimesh(
                    points,
                    np.arange(len(points)).reshape(-1, 3),
                    vertex_normals=normals,
                    process=False,
                )
            mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=mat)
        else:
            mesh.visual = trimesh.visual.TextureVisuals(material=mat)
        geom_name = f"visual_{len(cache)}"
        scene.geometry[geom_name] = mesh
        cache[key] = geom_name
        return geom_name

    for g in range(m.ngeom):
        if m.geom_group[g] not in (0, 1) or int(m.body_rootid[m.geom_bodyid[g]]) in roots:
            continue
        geom = geometry(g)
        name = m.geom(g).name or f"geom_{g}"
        transform = np.eye(4)
        transform[:3, :3] = d.geom_xmat[g].reshape(3, 3)
        transform[:3, 3] = d.geom_xpos[g]
        info = classify(m, d, g, runtime._catalogue)
        batch_key = (
            scene.geometry[geom].visual.material.name,
            tuple(info["levels"]),
            info["role"],
            info["room"],
            info["facility"],
        )
        batches.setdefault(batch_key, []).append((name, geom, transform, info))
    templates = dict(scene.geometry)
    scene = trimesh.Scene(base_frame="world")
    scene.graph.update(frame_to="mujoco", matrix=np.array(TO_GLB).reshape(4, 4).T)
    for number, group in enumerate(batches.values()):
        vertices = []
        normals = []
        faces = []
        uv = []
        offset = 0
        for name, geom, transform, info in group:
            mesh = templates[geom]
            vertices.append(mesh.vertices @ transform[:3, :3].T + transform[:3, 3])
            normals.append(mesh.vertex_normals @ transform[:3, :3].T)
            faces.append(mesh.faces + offset)
            offset += len(mesh.vertices)
            if mesh.visual.uv is not None:
                uv.append(mesh.visual.uv)
        combined = trimesh.Trimesh(
            np.concatenate(vertices),
            np.concatenate(faces),
            vertex_normals=np.concatenate(normals),
            process=False,
        )
        combined.visual = trimesh.visual.TextureVisuals(
            uv=np.concatenate(uv) if uv else None, material=templates[group[0][1]].visual.material
        )
        name = f"batch_{number}"
        scene.add_geometry(combined, node_name=name, geom_name=name, parent_node_name="mujoco")
        extras[name] = {**group[0][3], "geoms": [entry[0] for entry in group]}

    def metadata(tree):
        for node in tree.get("nodes", []):
            if node.get("name") in extras:
                node["extras"] = extras[node["name"]]

    output = ROOT / ".cache/explore" / scene_key
    output.mkdir(parents=True, exist_ok=True)
    glb = output / "scene.glb"
    glb.write_bytes(
        trimesh.exchange.gltf.export_glb(scene, include_normals=True, tree_postprocessor=metadata)
    )
    sources = source_files(scene_key, robot)
    result = {
        **runtime.catalogue(),
        "schema_version": SCHEMA_VERSION,
        "coordinate_system": COORDINATES,
        "source_hash": source_hash(sources),
        "sources": sources,
        "assets": [dict(path="scene.glb", hash=sha256(glb), bytes=glb.stat().st_size)],
        "statistics": dict(
            nodes=len(extras),
            meshes=len(batches),
            source_geoms=sum(len(g) for g in batches.values()),
            textures=len(images),
        ),
    }
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=manifest.keys(), required=True)
    parser.add_argument("--robot", default="g1")
    parser.add_argument("--texture-pixels", type=int, default=TEXTURE_PIXELS)
    args = parser.parse_args()
    if args.texture_pixels < 32:
        parser.error("--texture-pixels must be at least 32")
    result = export(args.scene, args.robot, args.texture_pixels)
    print(
        json.dumps(
            {k: result[k] for k in ("scene", "source_hash", "assets", "statistics")}, indent=2
        )
    )
