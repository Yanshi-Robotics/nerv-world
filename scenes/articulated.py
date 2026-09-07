"""MJCF emission for opt-in furniture; static scene paths remain unchanged."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from decor import articulation, lock

COLLISION_DENSITY = 450  # kg/m³, effective cabinet/door construction density.
CONTACT_SOLREF = "0.005 1"  # Same firm contacts as the validated furniture hulls.


def numbers(values):
    return " ".join(f"{float(v):.10g}" for v in values)


def scaled(value, factor):
    return numbers(float(v) * factor for v in value.split())


def fixture(item, scale, quaternion, position, angle="radian"):
    """Return a namespaced body tree and explicit parent collision exclusions."""
    key = item["mesh"]["id"]
    entry = articulation.load()[key]
    prefix = "ix_" + item["name"]
    visible = lock.bytes_present(key)
    angular = 1.0 if angle == "radian" else 180 / math.pi
    root = ET.Element("body", name=prefix, pos=numbers(position), quat=numbers(quaternion))
    exclusions = []

    def emit(source, parent, parent_name):
        name = prefix + "__" + source["name"]
        body = ET.SubElement(parent, "body", name=name)
        # Source collision meshes overlap at hinges and drawer runners. Only
        # adjacent bodies are excluded; drawer-door and external contact remains.
        if source["joints"]:
            exclusions.append((parent_name, name))
        for joint in source["joints"]:
            attrs = dict(joint, name=prefix + "__" + joint["name"])
            attrs["pos"] = scaled(attrs.get("pos", "0 0 0"), scale)
            multiplier = scale if attrs.get("type") == "slide" else angular
            for k in ("range", "ref", "springref"):
                if k in attrs:
                    attrs[k] = scaled(attrs[k], multiplier)
            ET.SubElement(body, "joint", attrs)
        for n, source_geom in enumerate(source["collisions"]):
            attrs = dict(source_geom)
            for k in ("pos", "size", "fromto"):
                if k in attrs:
                    attrs[k] = scaled(attrs[k], scale)
            if "euler" in attrs:
                attrs["euler"] = scaled(attrs["euler"], angular)
            if "mass" in attrs:
                attrs["mass"] = str(float(attrs["mass"]) * scale**3)
            else:
                attrs["density"] = str(COLLISION_DENSITY)
            attrs.update(name=f"{name}__collision{n}", group="4" if visible else "0",
                         rgba="0.65 0.65 0.62 1", contype="1", conaffinity="1",
                         solref=CONTACT_SOLREF)
            ET.SubElement(body, "geom", attrs)
        if visible:
            for visual in source["visuals"]:
                i = visual["part"]
                part = lock.parts(key)[i]
                attrs = dict(visual["attributes"])
                if "pos" in attrs:
                    attrs["pos"] = scaled(attrs["pos"], scale)
                if "euler" in attrs:
                    attrs["euler"] = scaled(attrs["euler"], angular)
                tag = f"{key}_{i}_{scale:.4f}".replace(".", "_")
                attrs.update(name=f"dg_{item['name']}_{i}", type="mesh", mesh="dm_" + tag,
                             group="0", contype="0", conaffinity="0", density="0")
                if part.get("png"):
                    attrs["material"] = f"dmat_{key}_{i}"
                else:
                    attrs["rgba"] = numbers(item["rgba"])
                ET.SubElement(body, "geom", attrs)
        for site in source["sites"]:
            attrs = {k: v for k, v in site.items() if k != "class"}
            attrs["name"] = prefix + "__" + site["name"]
            for k in ("pos", "size"):
                if k in attrs:
                    attrs[k] = scaled(attrs[k], scale)
            # Named task sites are queryable, invisible markers, never colliders.
            attrs.update(group="5", rgba="0 0 0 0")
            ET.SubElement(body, "site", attrs)
        for child in source["children"]:
            emit(child, body, name)

    emit(entry["tree"], root, prefix)
    return ET.tostring(root, encoding="unicode"), exclusions


def movable(item, geometry):
    """Keep a piece's collision and visual parts together under one free body."""
    name = "ix_" + item["name"]
    root = ET.Element("body", name=name, pos=numbers(item["world_pos"]))
    ET.SubElement(root, "freejoint", name=name + "__free")
    for xml in geometry:
        if not xml.strip().startswith("<geom"):
            continue
        geom = ET.fromstring(xml)
        position = [float(x) for x in geom.get("pos", "0 0 0").split()]
        geom.set("pos", numbers(a - b for a, b in zip(position, item["world_pos"])))
        if geom.get("contype", "1") != "0":
            geom.set("density", str(item.get("density", 220)))
            geom.set("solref", CONTACT_SOLREF)
        root.append(geom)
    return ET.tostring(root, encoding="unicode")
