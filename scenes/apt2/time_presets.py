"""Four lighting phases for the duplex's own seven lamps; apt1 stays read-only."""

from copy import deepcopy

PHASES = ("day", "morning", "dusk", "night")


def presets(reference):
    result = {"day": {}}
    # Existing sky and city material assets are reused, never regenerated.
    colors = {
        "morning": (".35 .31 .25", ".55 .65 .82", ".30 .28 .25"),
        "dusk": (".28 .16 .08", ".50 .40 .46", ".38 .28 .19"),
        "night": (".06 .08 .12", ".55 .40 .26", ".70 .52 .34"),
    }
    for phase in PHASES[1:]:
        old = reference.LIGHTS_BY_TIME[phase]
        spec = {k:deepcopy(old[k]) for k in ("sky", "headlight", "materials", "glass", "textures") if k in old}
        if phase == 'morning':
            # The duplex's paler finishes need less ambient fill than apt1.
            spec['headlight'] = dict(diffuse='.30 .33 .40', ambient='.22 .25 .32',
                                     specular='.05 .05 .05')
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
        if phase == "night":
            # Window fill lamps become warm kitchen/dining practicals.
            spec["lights"]["sky_park_w"].update(pos="-8.4 4.2 3.1", dir="0 0 -1",
                                                   diffuse=".95 .72 .48")
            spec["lights"]["sky_park_e"].update(pos="-2.9 4.5 3.1", dir="0 0 -1",
                                                   diffuse=".80 .58 .38")
        result[phase] = spec
    return result
