# Canonical residence validation

Validated locally on 2026-09-07 with MuJoCo 3.12.0. Output paths in the captured logs are
normalized to repository-relative paths; measured values are unchanged. The maintained scene names are `apt`
and `house`, each generated for G1 and Go2. The previous four-map revision is preserved at
`7fb134f53c293474a8ead488e653f6fdc09c50ff`; see the [recovery instructions](README.md).

## Preserved features and physical checks

| Check | Result |
|---|---|
| Catalogue | Exactly apt and house; retired keys are rejected |
| Environment baseline | 17 environment fields, original four-phase environment values and 138 asset hashes match the saved revision |
| City geometry | All 2728 buildings retained exactly once, with the same bounds and elevations; park-side district memberships preserved |
| Apartment details | Eight wall artworks; approximately 3.67 m camera separation for the parallax pair; service fixtures present |
| Apartment bath | 35 points inside the tub hit its lower base, four rim samples hit the rim; no enclosing solid tub box |
| Scene checks | Both maps pass every applicable structure, asset, collision, furniture, stair and lighting check |
| Walkthrough | Wall blocking, standing support and every floor transition pass the native inspector self-test |
| House estate | 586 route samples, 1800 perimeter samples and 336 pool samples pass; making water collidable is detected by fault injection |
| Render light budget | Seven active model lights plus headlight; apt checked in all four phases, house in day; re-enabling the robot studio lamp correctly fails |
| UV materials | All explicitly UV-mapped textured geom instances use 2D textures: 1259 in apt and 781 in house, for each robot variant |
| NERV regression tests | 31 selected tests pass, including nine body/world binding unit tests |

Evidence: [feature report](verification/features.json), [scene checks](verification/structure/scenes.txt),
[apt walkthrough](verification/structure/walkthrough-apt.txt),
[house walkthrough](verification/structure/walkthrough-house.txt),
[light fault injection](verification/structure/light-fault.txt),
[NERV tests](verification/structure/nerv-tests.txt).

Furniture checks cover all 22 appliance joints in both directions, nine movable bodies,
force-based grabbing and release, obstruction handling, cancellation, reset and time switching
without changing physical state. Both [G1](verification/interactions/g1.json) and
[Go2](verification/interactions/go2.json) pass. These are operator-driven scene mechanics;
they do not demonstrate autonomous robot manipulation.

The [real GLFW callback check](verification/render/inspector.txt) opens a refrigerator door,
cycles all four time phases without changing joint positions, grabs/releases a prop, and resets
furniture through the production keyboard callbacks. It uses a hidden native window and does
not capture the user's keyboard or mouse.

## Native rendering

The apt and house galleries were regenerated from the canonical definitions. Views cover the
interiors, stairs, bath, wardrobes, laundry, parallax pair, mansion exterior, lawn, pool,
closed gate and hillside neighborhood. G1 seated poses are settled in physics; the measured
pose has 0.046 m vertical displacement, 0.030 m slide and 11.51 degrees of tilt.

The city batches previously used explicit mesh UVs with cube textures. Facade sides now use
2D tiles extracted from the original local atlases, with a separate roof surface and metre-based
UVs. Original atlas bytes and city coordinates are preserved. House plaster meshes also use a
separate 2D material. This matches the classic renderer's
[2D texture path for explicit mesh coordinates](https://github.com/google-deepmind/mujoco/blob/13827e9ee56f097f57acf69ae52b078f9839682d/src/render/classic/render_gl3.c#L119-L148).
The [derivative texture record](../../../textures/residences/city/sources.json) includes sources,
licensing and hashes.

The included G1 studio lamp is disabled by the scene default before the robot include.
Authored scene lights explicitly select their active state. This reserves a slot for the
headlight without changing the robot model. Compiled activity is checked rather than counting
XML declarations. All apt phases and house day render with
[zero OpenGL errors](verification/render/gl-errors.txt).

| Time-of-day check | Measured result |
|---|---|
| Fixed-view mean RGB brightness | Day 96.4 > morning 93.1 > dusk 85.0 > night 27.3 |
| Night floor visibility | All 24 spaces pass; lowest measured room mean is 25.2/255, above the 8/255 threshold |
| Actual night facade texture effect | Keeping night lighting but restoring day facade textures changes the full-frame mean absolute pixel value by 3.570/255 |

The texture comparison tests rendered pixels, so merely changing a preset dictionary cannot
pass it. See the [full measurements](verification/render/time-presets.txt) and
[four-phase image](../../images/apt/time-presets/T0-四时段对比.png).
House currently has a daylight rig; it does not expose the apartment's four time presets.

## Real-time camera measurements

Each run uses the production NERV WorldSim, the released G1 walking policy on CPU and the actual
head/chase MJPEG route generators. Both cameras run together at 640 × 480 with a configured
12 fps target. Tests start no network listeners and use no existing session.

| Run | Head fps | Chase fps | Simulation / wall time | Result |
|---|---:|---:|---:|---|
| apt, standing, 30 s | 11.83 | 11.83 | 0.99994 | Pass |
| house, standing, 30 s | 11.93 | 11.93 | 1.00023 | Pass |
| apt, after a 1 m walking command, 30 s | 11.80 | 11.80 | 0.99991 | Pass |

All runs exceed 10.8 fps per camera and a 0.95 real-time ratio. The walking command reports
1.206 m of measured travel and no fall. Final compiled G1 models contain 2887 geoms / 1066 meshes
for apt and 3665 geoms / 595 meshes for house.

Raw records and camera frames: [apt](verification/runtime/apt/runtime.json),
[house](verification/runtime/house/runtime.json), [walking](verification/walking/apt/runtime.json).
These are bounded 30-second measurements, not a long-duration load test. Route sampling and
inspector stair movement do not prove that the released flat-ground G1 policy can autonomously
climb stairs or traverse the complete estate.

## Reproduction

A clean export containing only staged repository files regenerated and compiled all four
scene/robot combinations without downloaded furniture. The [fresh-checkout result](verification/structure/fresh-checkout.json)
confirms the simplified mode documented in Quick Start; it does not claim full mesh fidelity.

Run the commands from the nerv-world root after the [asset setup](../../interactions/README.md#asset-setup):

```bash
python tools/make_city_textures.py
python tools/make_house.py
python tools/check_scene.py
python tools/check_residences.py
python tools/check_interactions.py --robot g1
python tools/check_interactions.py --robot go2
python tools/walkthrough.py --scene apt --selftest
python tools/walkthrough.py --scene house --selftest
python docs/residences/migration/verification/structure/check_light_fault.py
```

Graphics checks require the host's graphics context and GPU queue:

```bash
MUJOCO_GL=egl python tools/make_time_stills.py --scene apt
MUJOCO_GL=egl python tools/render_residences.py --scene apt --contract ../policies/g1-29dof-turn/contract.json
MUJOCO_GL=egl python tools/render_residences.py --scene house
MUJOCO_GL=egl python tools/render_interactions.py
MUJOCO_GL=egl python docs/residences/migration/verification/render/check_gl.py
MUJOCO_GL=glfw python docs/residences/migration/verification/render/check_inspector.py
python tools/benchmark_residences.py --scene apt house --seconds 30 --output temp/residence-check/runtime
```

## Running-service boundary

The source and isolated runtime checks use apt and house. The existing resident backend,
world and body processes were not restarted; their in-memory registry/model may still use
apt2. Existing session records were not changed.
The canonical names need a separately authorized service reload before resident browser
acceptance. No old session is rewritten to appear as a session in the new map.
