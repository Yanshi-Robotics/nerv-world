"""Four phases combine the preserved Manhattan environment and duplex lighting."""

from copy import deepcopy
from scenes.apt.city_materials import extend_preset

PHASES = ("day", "morning", "dusk", "night")


def presets(reference, layout):
    result = {"day": {}}
    # Existing sky and city material assets are reused, never regenerated.
    colors = {
        "morning": (".35 .31 .25", ".55 .65 .82", ".30 .28 .25"),
        "dusk": (".28 .16 .08", ".50 .40 .46", ".38 .28 .19"),
        "night": (".06 .08 .12", ".55 .40 .26", ".70 .52 .34"),
    }
    for phase in PHASES[1:]:
        old = reference.LIGHTS_BY_TIME[phase]
        spec = {
            k: deepcopy(old[k])
            for k in ("sky", "headlight", "materials", "glass", "textures", "geom_tint")
            if k in old
        }
        extend_preset(spec)
        if phase == "morning":
            # The duplex's paler finishes need less ambient fill than apt1.
            spec["headlight"] = dict(
                diffuse=".30 .33 .40", ambient=".22 .25 .32", specular=".05 .05 .05"
            )
        sun, window, inside = colors[phase]
        spec["lights"] = {
            "sun_sw": dict(diffuse=sun, castshadow=phase != "night"),
            "sky_park_w": dict(diffuse=window),
            "sky_park_e": dict(diffuse=window),
            "gr_void": dict(diffuse=inside),
            "amb_gallery": dict(diffuse=inside),
            "amb_upper": dict(diffuse=inside),
            "amb_stair": dict(diffuse=inside),
        }
        if phase == "morning":
            # East-side low sun enters the duplex library, inside its glazing.
            x0, y0, x1, y1 = layout["ROOMS"]["library"]["rect"]
            spec["lights"]["sky_park_e"].update(
                pos=f"{x1 - 0.5:g} {(y0 + y1) / 2:g} 2.2",
                dir="-0.86 -0.20 -0.47",
                diffuse="1.00 .84 .62",
                specular=".14 .12 .09",
                attenuation=".34 .02 .003",
            )
        if phase == "dusk":
            # The kitchen now occupies the west corner; keep sunset direction.
            x0, y0, x1, y1 = layout["ROOMS"]["kitchen"]["rect"]
            spec["lights"]["sky_park_w"].update(
                pos=f"{x0 + 0.3:g} {(y0 + y1) / 2:g} 2.1",
                dir="0.90 -0.16 -0.40",
                diffuse="1.00 .62 .30",
                specular=".18 .12 .06",
                attenuation=".30 .02 .002",
            )
        if phase == "night":
            # Window fill lamps become warm kitchen/dining practicals.
            spec["lights"]["sky_park_w"].update(
                pos="-8.4 4.2 3.1", dir="0 0 -1", diffuse=".95 .72 .48"
            )
            spec["lights"]["sky_park_e"].update(
                pos="-2.9 4.5 3.1", dir="0 0 -1", diffuse=".80 .58 .38"
            )
        result[phase] = spec
    return result
