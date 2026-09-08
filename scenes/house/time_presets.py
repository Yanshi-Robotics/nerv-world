"""Authored hillside lighting; sun directions are display presets, not astronomy."""

PHASES = ("day", "morning", "dusk", "night")
SUN_DIRECTIONS = {
    "day": (0.35, 0.45, -0.82),
    "morning": (-0.88, 0.24, -0.35),
    "dusk": (0.88, 0.18, -0.26),
    "night": (0.25, 0.4, -0.88),
}
NIGHT_LAMP_HEIGHT = 6.0  # Wide pools of light without adding GL light slots.
NIGHT_ATTENUATION = "1 0 .006"  # Retains local light across a 15–20 m exterior approach.
NIGHT_LIGHT_ZONES = {
    "entry": "h2_fill_0_west",
    "path": "h2_fill_0_east",
    "gate": "h2_fill_1_west",
    "pool": "h2_fill_1_east",
}


def presets(layout):
    out = {"day": {}}
    # RGB values are authored scene lighting parameters.
    colors = {
        "morning": (
            ".48 .40 .30",
            ".11 .105 .095",
            ".07 .072 .08",
            ".25 .28 .34",
            ".24 .27 .33",
            0.04,
        ),
        "dusk": (".38 .20 .10", ".22 .16 .10", ".035 .025 .02", ".16 .14 .17", ".15 .14 .18", 0.35),
        "night": (
            ".34 .48 .68",
            ".26 .18 .11",
            ".008 .008 .014",
            ".08 .10 .15",
            ".12 .16 .22",
            0.7,
        ),
    }
    for phase, (sun, fill, ambient, head, headambient, emission) in colors.items():
        lights = {
            "h2_sun": dict(
                dir=SUN_DIRECTIONS[phase],
                diffuse=sun,
                specular=sun,
                ambient="0 0 0",
                castshadow=phase != "night",
            )
        }
        for f in range(layout["N_FLOORS"]):
            for wing in ("west", "east"):
                lights[f"h2_fill_{f}_{wing}"] = dict(
                    diffuse=fill, ambient=ambient, specular=".035 .025 .018"
                )
        out[phase] = dict(
            sky=phase,
            lights=lights,
            headlight=dict(diffuse=head, ambient=headambient, specular=".025 .025 .03"),
            materials={"h2_light": dict(rgba="1 .78 .46 1", emission=emission)},
        )
    # Broad moonlight keeps lawn/path surfaces legible beyond the four local
    # luminaires, while their pools of warm light retain the night composition.
    out["night"]["lights"]["h2_sun"]["ambient"] = ".20 .28 .40"
    # Reuse four daytime fills for actual exterior lighting at night. The two
    # remaining fills cover the upper floors; the headlight provides inspection
    # visibility indoors. Day restoration recovers every original position.
    areas = {a["name"]: a["rect"] for a in layout["EXTERIOR_AREAS"]}
    fore = areas["forecourt"]
    west = areas["west_walk"]
    terrace = areas["pool_terrace"]
    pool = layout["ESTATE"]["pool"]
    gate = layout["ESTATE"]["gate_center"]
    positions = {
        "entry": (layout["ENTRY_X"], fore[3], NIGHT_LAMP_HEIGHT),
        "path": ((west[0] + west[2]) / 2, (fore[1] + fore[3]) / 2, NIGHT_LAMP_HEIGHT),
        "gate": (gate[0], gate[1] + layout["ESTATE"]["gate_width"] / 2, NIGHT_LAMP_HEIGHT),
        "pool": ((terrace[0] + pool[0]) / 2, (pool[1] + pool[3]) / 2, NIGHT_LAMP_HEIGHT),
    }
    for zone, name in NIGHT_LIGHT_ZONES.items():
        out["night"]["lights"][name].update(
            pos=positions[zone],
            dir=(0, 0, -1),
            diffuse=".95 .76 .52",
            ambient=".08 .085 .10",
            specular=".08 .06 .035",
            attenuation=NIGHT_ATTENUATION,
            cutoff=90,
            castshadow=False,
        )
    for floor, wing in ((1, "west"), (2, "east")):
        out["night"]["lights"][f"h2_fill_2_{wing}"].update(
            pos=(0, 6, layout["FLOOR_Z"](floor) + layout["WALL_HEIGHT"] - 0.2)
        )
    return out
