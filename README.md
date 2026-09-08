# nerv-world

[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE) [![Simulator: MuJoCo](https://img.shields.io/badge/simulator-MuJoCo-blue)](https://mujoco.org)

[English](README.md) · [简体中文](README_zh.md)

Residential environments for MuJoCo and [NERV](https://github.com/Yanshi-Robotics/nerv),
with Unitree G1 and Go2 variants. Layout definitions generate the architecture, furniture,
collision geometry and robot scenes. Native MuJoCo screenshots show the simulated scenes;
the World Explore images show the separate Three.js browser guide.

![house: hillside mansion, lawn and pool](docs/images/house/X1-整栋外景.png)

[Scenes](#scenes) · [Quick Start](#quick-start) · [World Explore](#world-explore) · [Interactive furniture](docs/interactions/README.md) · [Residence guide](docs/residences/README.md)

**AI agents:** read [AGENTS.md](AGENTS.md) before changing the repository.

## Scenes

| Scene | Setting | Main purpose |
|---|---|---|
| [apt](#apt) | Manhattan duplex on floors 62–63, 24 spaces | Central Park views, four lighting phases, physical furniture and operator interaction |
| [house](#house) | Three-storey California mansion on an 80 × 70 m property | Four lighting phases, courtyard routes, lawn, pool and a closed property boundary |

These are the two maintained residential maps. apt combines the duplex and its interaction
capabilities with the original apartment's city environment and time-of-day effects.
house continues the hillside estate. Numbered maps are retired; see the
[migration and recovery guide](docs/residences/migration/README.md) for saved versions.

### apt

apt extends the same Manhattan setting into a duplex with a double-height living room,
a two-flight staircase and an upper gallery. Pale oak, walnut, stone and linen finishes,
rounded upholstery, bedding, curtain folds, window reveals and cabinet details improve the
view at room scale and robot camera height.

| Double-height living room | G1 supported by the sofa |
|---|---|
| ![apt double-height living room](docs/images/apt/V2-大客厅-三开间落地窗.png) | ![G1 seated on apt sofa](docs/images/apt/S1-机器人坐在沙发上.png) |

| Capability | Implementation in apt |
|---|---|
| Space | Two floors, double-height living room, upper gallery and connected staircase |
| Furniture collision | Decomposed chair, armchair and coffee-table shapes retain leg gaps; the sofa has a 0.35 m seat and a tested G1 seated pose |
| Kitchen | Four appliances with 22 passive joints: refrigerator doors and drawers, oven door and rack, knobs, faucet and hood buttons |
| Movable objects | Six dining chairs plus a can, fruit and book have mass, gravity and collision |
| Time presets | Morning, day, dusk and night use the shared city assets with apt's own lighting; switching preserves furniture state |
| Operator controls | NERV Scene testing and the native inspector operate nearby parts, adjust opening, move objects and release them into physics |

| Refrigerator open, drawers extended | Oven open, rack extended |
|---|---|
| ![apt refrigerator interaction](docs/images/apt/interactions/fridge-open.png) | ![apt oven interaction](docs/images/apt/interactions/oven-open.png) |

![apt four lighting presets](docs/images/apt/time-presets/T0-四时段对比.png)

NERV's **Scene testing** panel operates the 22 appliance joints and nine movable objects with
bounded forces, measured motion and collision feedback. An exclusive control lease stops and
disarms the robot before testing; normal robot commands remain unavailable until testing ends
and the operator arms it again. Selection checks visible surfaces within two metres of the
operator camera, including occlusion by walls and closed doors. Cancellation or lease expiry
clears the interaction forces.

The refrigerator task requires the whole can inside the marked middle-shelf volume in the
right compartment, released onto that shelf and stably supported before the door is closed.
Its evaluator checks geometry, motion and actual contacts; holding the can in place does not
complete the task. See the [running NERV validation](https://github.com/Yanshi-Robotics/nerv/tree/main/docs/validation/world-explore)
for physical repetitions, browser operation and interruption tests.

The native walkthrough retains its own inspection controls. The released G1 policy provides
walking and turning; autonomous grasping, opening, sitting down and stair climbing require
additional robot skills. The seated image is a pose settled in physics, not a sit-down policy.
Appliance controls move physically; water flow, heating, cooking and ventilation are not simulated.

[Interaction controls and capabilities](docs/interactions/README.md) · [apt layout](scenes/apt/layout.py) · [Verification](docs/residences/migration/validation.md)


The apartment preserves its approximately 232.5 m elevation, Central Park aerial imagery,
2716 building boxes derived from NYC footprint and height data and 12 supplementary landmarks, visible host tower, collidable
glazing and real window-view parallax. Eight artworks are placed on the duplex's solid walls.
Wardrobes, storage, washer and dryer, both bathrooms' toilets and mirrors, and a hollow
primary bathtub with a separate shower complete the service spaces. These additions are
static; the physically operable appliances are listed above. Private elevator doors
are fixed architectural elements; elevator travel is not simulated.

| Phase | Appearance |
|---|---|
| Morning | Cool sky and ambient light, with low warm light entering from the east |
| Day | Bright park, clear city facades and natural interior illumination |
| Dusk | Warm western light; distinct cool and warm tones across the two park-side districts |
| Night | Lit city windows, darkened park and host tower, and warm interiors with visible floors |

These are selectable presets, not a continuous clock, weather or seasonal simulation.
Use NERV's time selector or press **L** in the native walkthrough to change them without
changing furniture opening, position or velocity.

| Left window view | Same direction after moving approximately 3.67 m right |
|---|---|
| ![Left parallax camera](docs/images/apt/P1-公园视差.png) | ![Right parallax camera](docs/images/apt/P2-公园视差.png) |

### house

The newly developed California hillside mansion has three stepped floors, warm plaster,
stone and timber finishes, terraces and a furnished interior. An approximately 30 × 25 m
lawn and 15 × 6 m pool sit below the house, with a driveway, paths, trees and planting beds.

The entrance stays open. Continuous traversable routes connect the ground-floor robot room,
the house, the grounds and the closed outer gate. The gate and perimeter walls have continuous
collision geometry. The pool has a real basin and steps; its water surface does not support
weight. Roads, neighboring houses and descending hills form an inaccessible community backdrop.
Layout-defined inspection routes cover the gate, lawn, pool approach and circuit, side paths
and rear garden. Stair entrances are stopping checkpoints for the flat-ground G1 policy.

Morning, day, dusk and night are selectable in both NERV and the native walkthrough. Night
lighting covers the entrance, gate, west path and pool terrace while retaining the dark sky.
Time switching changes the lighting without resetting the robot or furniture.

| Lawn and house | Pool terrace |
|---|---|
| ![house lawn](docs/images/house/X4-草坪与主楼.png) | ![house pool](docs/images/house/X5-泳池露台.png) |
| Living room | Hillside neighborhood |
| ![house living room](docs/images/house/R1-底层客厅.png) | ![house neighborhood](docs/images/house/X6-山坡社区.png) |

![house west pool terrace at night, rendered by MuJoCo](docs/images/explore/house-west_pool-night.png)

The west pool terrace at night, captured with MuJoCo's native renderer.

[house layout](scenes/house/layout.py) · [Estate definition](scenes/house/estate.py) · [Gallery and reproduction](docs/residences/README.md)

## Quick Start

Python 3.10 or later is required. From a standalone checkout:

```bash
git clone https://github.com/Yanshi-Robotics/nerv-world.git
cd nerv-world
python -m venv .venv
source .venv/bin/activate
pip install mujoco numpy pillow glfw
python tools/make_house.py --scene apt
python tools/walkthrough.py --scene apt --robot g1
```

A fresh clone generates simplified furniture where downloaded meshes are unavailable.
The articulated appliances retain analytic collision bodies and joints in this mode.
To reproduce the detailed furniture, use the [asset setup](docs/interactions/README.md#asset-setup).
Do not open a downloaded generated XML before regenerating it for your local assets.

Walk with **WASD**, look with the mouse, jump with **Space**, and use **F** for inspection flight.
In apt, aim within two metres: **E** operates a part, **[ / ]** adjusts its opening, **J** selects
another joint on the same part, **G** grabs/releases a movable object, **L** cycles time presets,
and **Backspace** resets furniture. **Esc** releases the mouse; **Q** exits.
This camera movement is an inspection tool, not robot locomotion.

Other scene and robot combinations use the same generator:

```bash
python tools/make_house.py --scene house --robot go2
python -m mujoco.viewer --mjcf=build/house-go2.xml
python tools/check_scene.py --scene apt
python tools/check_interactions.py
python tools/walkthrough.py --scene apt --selftest
python tools/check_residences.py
```

For NERV, this repository is the `worlds/` submodule. The descriptors in
[house/world.yaml](house/world.yaml) and [apt/world.yaml](apt/world.yaml) select the scene
and G1 body. Locomotion policies live in [nerv-policies](https://github.com/Yanshi-Robotics/nerv-policies),
not in this repository. See [NERV](https://github.com/Yanshi-Robotics/nerv) for its launcher.

## World Explore

Open **Nerv World Explore** from NERV's sidebar to browse either map without starting a
simulation. The Three.js guide provides orbit, pan and zoom, floor cutaways, room search,
facility highlights and inspection instructions. It displays the generated starting layout
with daytime materials; selecting a fixture focuses the view without operating it or changing
a running world. Use Scene testing in an active simulation for physical actions.

![apt floor cutaway in the Three.js World Explore guide](docs/images/explore/apt-cutaway.png)

![house courtyard in the Three.js World Explore guide](docs/images/explore/house-courtyard.png)

Both guide images show the browser display, whose lighting differs from the native cameras.
After the [furniture asset setup](docs/interactions/README.md#asset-setup), prepare its resources
from this repository:

```bash
pip install -r requirements-explore.txt
python tools/make_house.py --scene apt
python tools/make_house.py --scene house
python tools/export_explore.py --scene apt
python tools/export_explore.py --scene house
python tools/check_explore.py
```

Each export writes `scene.glb` and `manifest.json` to `.cache/explore/<scene>/`. NERV checks
source fingerprints and asset hashes; missing, stale or modified exports produce an error.
Regenerate after changing scene sources or assets. Downloaded furniture and derived GLBs remain
outside Git. See the [export guide](docs/explore/README.md) and [world-library checks](docs/explore/verification/README.md).

## Development

Edit `scenes/<scene>/layout.py` and its supporting modules, then regenerate
`build/<scene>-<robot>.xml`. Never hand-edit the generated XML. Scene and robot manifests keep
the two selections independent. Downloaded assets and temporary outputs remain outside Git.

- [Residence geometry, rendering and NERV checks](docs/residences/README.md)
- [Interactive furniture architecture and task evaluation](docs/interactions/README.md)
- [NERV interaction, route, camera and browser validation](https://github.com/Yanshi-Robotics/nerv/tree/main/docs/validation/world-explore)
- [Changelog](CHANGELOG.md)

## License

Code and original procedural assets use the [MIT license](LICENSE). Third-party material
retains its own terms: [G1](robots/g1/G1_MODEL_LICENSE) and [Go2](robots/go2/GO2_MODEL_LICENSE)
models use BSD-3-Clause; furniture sources include Poly Haven CC0, Objaverse CC-BY-4.0 and
RoboCasa CC-BY-4.0. External furniture bytes are fetched locally and are not stored in Git.

See the [furniture attribution](decor/ATTRIBUTION.md), [city and texture attribution](textures/house3/ATTRIBUTION.md),
[residence asset record](docs/residences/assets.json) and [articulation source record](decor/articulation.lock.json)
for sources, licenses and hashes. Thanks to Unitree Robotics, Google DeepMind, the MuJoCo
and Menagerie maintainers, and the listed asset authors.
