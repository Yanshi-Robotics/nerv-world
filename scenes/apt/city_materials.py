"""Explicit 2D textures for city meshes; primitive host-tower geoms keep cubemaps."""

from copy import deepcopy

TEXTURE_ROOT = "textures/residences/city"
MATERIAL_ALIASES = {
    name: "a2_city_" + name.removeprefix("mat_h3_")
    for name in ("mat_h3_limestone", "mat_h3_facade", "mat_h3_glass_dark", "mat_h3_glass_cool")
}
ROOF_MATERIAL = "a2_city_roof"


def assets(environment):
    textures = [
        dict(
            name="a2_city_tex_" + kind,
            type="2d",
            colorspace="sRGB",
            file=f"{TEXTURE_ROOT}/{kind}.png",
        )
        for kind in ("glass", "stone", "roof")
    ]
    materials = []
    for source, name in MATERIAL_ALIASES.items():
        material = deepcopy(next(m for m in environment.MATERIALS_EXTRA if m["name"] == source))
        kind = "glass" if "glass" in source else "stone"
        material.update(
            name=name, texture="a2_city_tex_" + kind, texuniform="false", texrepeat="1 1"
        )
        materials.append(material)
    materials.append(
        dict(
            name=ROOF_MATERIAL,
            texture="a2_city_tex_roof",
            texuniform="false",
            texrepeat="1 1",
            specular="0.05",
            shininess="0.1",
            emission="0.1",
        )
    )
    return textures, materials


def extend_preset(spec):
    materials = spec.setdefault("materials", {})
    for original, alias in MATERIAL_ALIASES.items():
        if original in materials:
            materials[alias] = deepcopy(materials[original])
    if spec.get("textures"):
        spec["textures"].update(
            {
                "a2_city_tex_" + kind: f"{kind}_night.png"
                for kind in ("glass", "stone", "roof")
            }
        )
        materials[ROOF_MATERIAL] = dict(emission=0.05, rgba="0.35 0.38 0.45 1")
