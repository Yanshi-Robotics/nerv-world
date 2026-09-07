"""Extract RoboCasa kinematics without changing the static decor lock or asset bytes.

Run ``python -m decor.articulation`` after the existing RoboCasa fetch. The small
lock records source checksums, body hierarchy, analytic collisions and sites.
No upstream defaults, options, actuators or keyframes enter the generated scene.
"""

from __future__ import annotations

import hashlib
import json
from itertools import count
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from decor import lock
from decor.robocasa import BASE, FIXTURES, LICENSE, _download

LOCK_PATH = Path(__file__).with_name("articulation.lock.json")
GEOM_FIELDS = {"type", "size", "pos", "quat", "euler", "axisangle", "fromto",
               "mass", "density", "friction", "solimp", "solref"}


def extract(key, category, model):
    archive = Path(_download(category))
    with zipfile.ZipFile(archive) as z:
        prefix = f"{category}/{model}/"
        source = z.read(prefix + "model.xml")
        root = ET.fromstring(source)
        angle = root.find("compiler").get("angle", "degree")
        if angle != "radian":
            raise ValueError(f"{key}: source angle must be explicitly radian")
        meshes = {m.get("name"): m.get("file") for m in root.findall("asset/mesh")}
        parts = lock.parts(key)
        by_hash = {hashlib.sha256((Path(lock.ASSET_DIR) / key / p["obj"]).read_bytes()).hexdigest(): i
                   for i, p in enumerate(parts)}
        defaults = {d.get("class"): d.find("geom").attrib
                    for d in root.findall("default/default") if d.find("geom") is not None}
        seen_parts = set()
        anonymous = count()

        def body(el, serial):
            attrs = dict(el.attrib)
            attrs.setdefault("name", f"root{next(anonymous)}")
            if any(k in attrs for k in ("quat", "euler", "axisangle", "xyaxes", "zaxis")):
                raise ValueError("Static decor conversion has no rotated body support")
            if any(float(v) != 0 for v in attrs.get("pos", "0 0 0").split()):
                raise ValueError("Static decor and articulated meshes need a common frame")
            out = dict(name=attrs["name"], joints=[dict(j.attrib) for j in el.findall("joint")],
                       visuals=[], collisions=[], sites=[], children=[])
            for g in el.findall("geom"):
                mn = g.get("mesh")
                if mn and "_vis" in mn:
                    digest = hashlib.sha256(z.read(prefix + meshes[mn])).hexdigest()
                    if digest not in by_hash:
                        raise ValueError(f"{key}/{mn}: mesh bytes differ from the static import")
                    i = by_hash[digest]
                    seen_parts.add(i)
                    out["visuals"].append(dict(part=i, attributes={k:v for k,v in g.attrib.items()
                                                                  if k in ("pos", "quat", "euler")}))
                elif g.get("class") == "collision":
                    values = {**defaults.get("collision", {}), **g.attrib}
                    if values.get("type", "box") not in ("box", "cylinder", "sphere", "capsule", "ellipsoid"):
                        raise ValueError(f"{key}: unsupported source collision {values}")
                    out["collisions"].append({k:v for k,v in values.items() if k in GEOM_FIELDS})
            out["sites"] = [dict(s.attrib) for s in el.findall("site") if s.get("name")]
            out["children"] = [body(ch, n) for n, ch in enumerate(el.findall("body"))]
            return out

        tree = body(root.find("worldbody"), 0)
        if seen_parts != set(range(len(parts))):
            raise ValueError(f"{key}: not every static mesh has a kinematic owner")
        return dict(source=f"{BASE}/{category}.zip", source_model=f"{category}/{model}/model.xml",
                    license=LICENSE, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    xml_sha256=hashlib.sha256(source).hexdigest(), angle=angle,
                    parts=[dict(obj=p["obj"], sha256=hashlib.sha256(
                        (Path(lock.ASSET_DIR) / key / p["obj"]).read_bytes()).hexdigest()) for p in parts],
                    tree=tree)


def load():
    return json.loads(LOCK_PATH.read_text())["fixtures"]


def main():
    result = {k: extract(k, cat, model) for k, (cat, model, _) in FIXTURES.items()}
    LOCK_PATH.write_text(json.dumps(dict(schema_version=1, fixtures=result), indent=2) + "\n")
    print(f"Recorded {len(result)} fixtures in {LOCK_PATH.name}; static asset bytes unchanged")


if __name__ == "__main__":
    main()
