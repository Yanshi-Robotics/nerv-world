# Canonical residences

The maintained scene keys are **apt** and **house**. The generator, walkthrough,
image tools, build files and NERV world descriptions use these names.

| Previous name | Current state |
|---|---|
| apt2 | Continued as apt, with the original apartment's applicable features preserved |
| house2 | Continued as house, retaining the three-storey hillside estate |
| apt1 | Retired from the catalogue, source layouts, generated builds and current gallery |
| house1 | Retired from the catalogue, source layouts, generated builds and current gallery |

There are no aliases that silently substitute a different layout. Unknown or retired keys
raise an error. New commands use `--scene apt` or `--scene house`; NERV sessions use the
same world names. Asset identifiers such as `textures/house3/`, `h3_`, `a2_` and `h2_`
remain stable because they identify textures and geometry, not selectable scenes.

## Preserved apartment features

The environment now lives in [manhattan.py](../../../scenes/environments/manhattan.py)
and [nyc_massing.py](../../../scenes/environments/nyc_massing.py), independent of a retired
floor plan. The saved city data was moved without downloading or recalculating it.

- Floor 62 remains at a 232.5 m elevation, with a 3.75 m floor spacing and the same
  Central Park position, aerial imagery, street ground, sky and host-tower geometry.
- All 2728 buildings remain, including 2716 city footprints and 12 supplementary landmarks.
  Mesh batches retain individual building bounds, heights and district membership.
- Morning, day, dusk and night preserve sky and facade changes, east/west light direction,
  district tint differences, nighttime park darkening, illuminated windows and indoor fill.
  Switching presets leaves furniture physics unchanged.
- Collidable glazing, two robot variants, room navigation and first-person inspection remain.
  Eight artworks and two same-direction parallax cameras are adapted to the duplex walls.
- Wardrobes, storage, washer and dryer, toilets, mirrors, a hollow bathtub, shower enclosure
  and fixed elevator doors restore the service rooms' purposes. These added fixtures are
  static; their visual presence does not imply new manipulation or appliance simulation.
- The duplex retains its two-flight stair, upper gallery, double-height living room,
  physically supported sofa pose, 22 appliance joints and nine movable furniture/prop bodies.

[baseline.json](baseline.json) records the pre-retirement asset and environment hashes.
`tools/check_residences.py` checks them along with building bounds, district membership,
generated scenes, estate routes, the closed gate and hollow pool/bath geometry.
Current checks and actual camera measurements are in the [validation record](validation.md).

## Recover the old maps

The complete four-scene version is saved in the published revision
[`7fb134f53c293474a8ead488e653f6fdc09c50ff`](https://github.com/Yanshi-Robotics/nerv-world/tree/7fb134f53c293474a8ead488e653f6fdc09c50ff).
Use a separate checkout of that revision to reproduce old layouts and screenshots; do not
restore only an old XML into the current scene catalogue. Downloaded furniture bytes remain
outside Git and use the asset setup documented in that revision.

The old furniture TODO has been removed after its active constraints and development work
moved into the [interaction guide](../../interactions/README.md). The old apartment design
draft is also retired. Its proposed outdoor apartment pool was not implemented and is not
claimed as a completed feature. Historical changelog entries and raw validation reports keep
the original names and measurements.

## NERV sessions and running nodes

The parent NERV update registers both canonical worlds and rejects reuse of a body attached
to a different world. It does not automatically stop or rebind a running robot node.
Externally attached body nodes are checked against their current health response.

A running NERV process holds its registry and models in memory. Updating the checkout does
not reload them. The operator must stop the affected world/body nodes and restart the
NERV backend through its normal service controls before selecting the new names.
That operation is separate from committing or pushing these files.

Create a new apt or house session through the NERV page after the new registry is loaded.
The existing session store freezes the previous active session for that body. Do not rewrite
old session world fields, images, messages or epochs: they describe the world used at the time.
