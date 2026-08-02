[![Language: English](https://img.shields.io/badge/Language-English-2f81f7?style=flat-square)](README.md) [![语言: 简体中文](https://img.shields.io/badge/语言-简体中文-e67e22?style=flat-square)](README_zh.md)

# alice-house · A House for Robots to Live In

[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE) [![Simulator](https://img.shields.io/badge/simulator-MuJoCo-blue?style=flat-square)](https://mujoco.org) [![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](https://www.python.org) [![Version](https://img.shields.io/badge/version-v0.6-lightgrey?style=flat-square)](CHANGELOG.md)

> 🤖 **If you are an AI agent, read [AGENTS.md](AGENTS.md) first** — the machine-facing entry point:
> what this repo is, where each fact lives, the entry commands, and the red lines.

**Procedurally generated indoor scenes, shipped with two Unitree robots and trained locomotion policies — clone it and they actually walk around, up the stairs included.**

**Alice's house** — an indoor scene generated entirely from code, for robots to look around in, walk through, search, and work in.

Not one line of geometry is hand-written: rooms, doors, windows, stairs, furniture and textures all
come out of one layout definition per place (`scenes/<name>/layout.py`). Change a house by changing
its layout and re-running the generator; the scene and whatever consumes it read the same source of
truth, so coordinates can never disagree in two places.

There are **two places** so far — a single-floor apartment and a three-storey house with stairs —
and one robot can be dropped into either. Scenes and robots are two independent registries that get
crossed at generation time.

It also ships **robots** (Unitree Go2 quadruped, Unitree G1 humanoid) and their trained **locomotion policies** — so they really take steps, they don't teleport.

> Where the name comes from: Alice is robot number one in this series. This is her house.
> It may grow into an island one day — house, hillside trail, dock — with Alice visiting each.

---

## Table of Contents

- [What's Inside](#whats-inside) · [Robots](#robots) · [Floor Plan & Screenshots](#floor-plan)
- [Design Principles](#design-principles)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [One Scene per Robot](#one-scene-per-robot)
- [Versioning](#versioning) · [License](#license)

---

## What's Inside

### Places

| Key | Layout | Size | Why it exists |
|---|---|---|---|
| **house1** | 3 bedrooms, 2 living areas, 2 baths — single floor | 12 spaces / 364 m² | Modelled after a real floor plan: open living-dining, master suite (walk-in closet + ensuite with freestanding tub), separate wet/dry kitchens. Flat ground throughout |
| **house2** | Entry / living / kitchen, bedroom / study / bath, attic studio / storage — **three storeys** | 11 spaces / 381 m² | Built for height. A humanoid's stair climbing, cross-floor navigation and "fell on the stairs" failures cannot be tested on flat ground |

### Robots

| Key | Body | Eye height | Notes |
|---|---|---|---|
| **go2** | Unitree Go2 quadruped | ~0.38 m | Head-mounted forward camera; flat-ground velocity policy |
| **g1** | Unitree G1 humanoid (29 dof) | ~1.25 m | 1.38 m standing; head camera on the torso, pitched 10° down |

The same room looks very different through these two pairs of eyes — which is exactly why the scene is **built to be realistic, not tailored to one robot**.

### Spaces

Master bath (freestanding tub) · walk-in closet · kid's room (ensuite) · master bedroom ·
corridor · guest bath · second bedroom · dining room (with a western-kitchen island) ·
Chinese kitchen (with drying area) · living room · entry hall · laundry

### Floor Plan

Ceiling hidden, viewed from above — you can read the whole circulation: the master suite and
kid's room (quiet zone) sit west, a corridor runs east-west, and the living room, entry and
service rooms (active zone) sit east.

![Floor plan](docs/images/house1/A1-户型俯视图.png)

### Common Areas

The wall between living and dining is removed entirely; the TV stands where that wall used to be
and acts as a soft divider — the way open-plan apartments usually do it.

| Living-dining opened up | Living room |
|---|---|
| ![Living-dining](docs/images/house1/B1-客餐厅打通.png) | ![Living room](docs/images/house1/B2-客厅.png) |

### Bedrooms & Service Rooms

| Master bedroom | Master bath (freestanding tub) |
|---|---|
| ![Master bedroom](docs/images/house1/C1-主卧.png) | ![Master bath](docs/images/house1/C3-主卫+浴缸.png) |

| Kid's room | Chinese kitchen |
|---|---|
| ![Kid's room](docs/images/house1/D1-小孩房.png) | ![Kitchen](docs/images/house1/E1-中厨.png) |

The kitchen shot is worth a second look: the counter run goes along the west wall
(dishwasher · sink · stove · oven), tall storage and the fridge sit against the north wall,
and the middle is left clear to walk through. **This was re-laid out on 2026-07-25** — before
that, a full-height cabinet wall sat in the middle of the room and blocked a door, cutting
45 m² into three pieces; the robot dog would crawl into a 54 cm gap and get stuck.

### house2 — Three Storeys and a Staircase

![Three-storey exterior](docs/images/house2/X1-整栋外景.png)

The staircase is the reason this place exists, and it is built the way a **real** staircase is
built, not as "two rows of steps".

A half-turn stair is **five parts, two of which are landings** — floor landing → up flight →
half-landing → return flight → the floor landing above. Neither landing is optional: without the
half-landing the two flights never meet; without the floor landing you arrive to thin air. Each
part's **last tread meets the next part's starting landing edge-to-edge, exactly one riser below**,
so the stair is continuous by construction rather than by remembering to line things up.

| On the floor landing, facing the up flight | Mid-flight, the well wall on your right |
|---|---|
| ![Foot of the stairs](docs/images/house2/S1-楼层平台望向上行跑.png) | ![Mid-flight](docs/images/house2/S2-站在上行跑中间.png) |

| ⭐ Half-landing: the return flight starts at your feet | Same landing, looking back down the up flight |
|---|---|
| ![Flights joined](docs/images/house2/S3-中间平台-回头跑从脚下起步.png) | ![Looking back](docs/images/house2/S4-中间平台-回望上行跑.png) |

| The whole stair, from the doorway | Top floor: no flight above, so a solid parapet |
|---|---|
| ![From the door](docs/images/house2/X2-从门口平视楼梯.png) | ![Parapet](docs/images/house2/X3-顶层梯口栏板俯视.png) |

You step off onto the **floor landing** — the only part of the shaft that is floored on the upper
storeys; everything else stays open for the flights coming up:

![Floor landing on storey 1](docs/images/house2/S5-二层楼层平台.png)

Dimensions follow the Chinese residential code GB 50096-2011 §6.3: 0.16 m riser, 0.30 m tread,
1.20 m flight width, 1.40 m landing depth, 2.63 m headroom. The 2.88 m storey height is **derived
from the stair** (2 × 9 × 0.16). Between the two flights is a solid 0.12 m wall rather than an open
well — an open well is exactly the width that traps a robot's foot. Upstairs the shaft is floored
only across the **floor landing**; where the flights come up it stays open.

The derivation, the code clauses it follows, and the two ways this got built wrong are all in
[`scenes/house2/楼梯设计.md`](scenes/house2/楼梯设计.md) (Chinese). **Read it before changing the stair.**

| Ground floor | Floor 1 | Floor 2 |
|---|---|---|
| ![Living room](docs/images/house2/R1-底层客厅.png) | ![Bedroom](docs/images/house2/R2-二层主卧.png) | ![Attic studio](docs/images/house2/R3-三层工作间.png) |

A top-down view only catches the topmost storey (the three floor plans overlap), so this is floor 2:

![Three-storey plan](docs/images/house2/A1-三层楼-顶视.png)

### Through the Robot's Eyes

What this scene ultimately serves is a robot's camera. The shots below are from the
**quadruped's head camera** (0.38 m); the last one is the same kitchen at **humanoid eye
height** (1.25 m, the G1's actual camera height) for comparison.

| Spawned in the entry | Living room (facing the TV wall) | Corridor |
|---|---|---|
| ![Entry](docs/images/house1/G1-狗视角-出生在玄关.png) | ![Living room](docs/images/house1/G2-狗视角-看电视.png) | ![Corridor](docs/images/house1/G5-狗视角-过道.png) |

| Looking into the kitchen from the door | The city outside | Same kitchen, humanoid eye height |
|---|---|---|
| ![Kitchen door](docs/images/house1/G3-狗视角-厨房门口.png) | ![Outside](docs/images/house1/G4-狗视角-窗外城市.png) | ![Humanoid view](docs/images/house1/H1-人形视角-中厨.png) |

### How the Screenshots Are Made

**Don't hand-capture them.** Every camera pose lives in `make_docs_images.py`; re-run it
whenever the scene changes:

```bash
python make_docs_images.py        # all of them
python make_docs_images.py E1 G3  # only the ones you name
```

Background: the first set of screenshots was framed by hand one at a time. One kitchen
re-layout later they were all stale, and nobody remembered where the cameras had been.

---

## Design Principles

**No hand-written geometry — everything is generated from the layout definition.** Change the
house by changing `layout.py` and re-running the generator. The scene and its consumers (e.g. a
world service deciding "which room is the robot in") read the same source of truth.

**⛔ Build for realism, not for one particular robot.** The scene is *reality*, not an exam paper
written for one machine. A quadruped's camera sits around 0.4 m; a humanoid's is above 1.2 m —
**lower the furniture to suit the dog and you have to redo everything when the humanoid arrives.**
Not being able to see high things is a limitation *on the robot side*, to be solved by looking
around, looking up, or moving — not by mounting the range hood at knee height.

> This principle is a correction. An earlier version said "recognisable features must sit in the
> 0.3–0.9 m band" — that was taking one specific robot's viewpoint as the design target.

**Place things the way they really are: along the walls, keep the middle clear.** In real homes
cabinets and wardrobes hug the walls and the middle of the room is where people walk. **Don't
leave a large piece of furniture stranded in the middle of a room** — measured the hard way on
2026-07-25: a full-height cabinet left in the middle of the kitchen cut a 45 m² room into three
pieces connected only by a 54 cm and a 90 cm gap, and the robot got wedged.

Worth noting: in a real kitchen the oven and dishwasher **are** built in under the counter
(0.1–0.9 m) and the fridge **does** stand on the floor — they happen to land where a low camera
can see them. That is a consequence of realism, not a concession to anyone.

**Furniture is assembled from parts, not primitives.** A chair = seat + back + two stiles + four
legs + front and rear rails; a floor lamp = weighted base + slim pole + collar + shade + finial.
See `furniture.py`.

**Capped.** There is a ceiling — look up and you see a roof, not sky. The ceiling lives in its own
geom group so it can be switched off in one line for top-down renders.

**There's a world outside the windows.** Near trees and grass → mid-ground buildings → a distant
city skyline backdrop (matte-painting style).

---

## Project Structure

```
scenes/
  manifest.py       ⭐ which places exist (paired with robots/manifest.py; the two cross freely)
  house1/layout.py  ⭐ single source of truth for that place (room rects / doors / windows / furniture / scenery)
  house1/shots.py   camera poses for that place's screenshots
  house2/layout.py  three-storey house: storeys, flights, landings, well wall, parapet
  house2/shots.py
  house2/楼梯设计.md ⭐ how the stair dimensions are derived, which code clauses, what got built wrong
robots/
  manifest.py       ⭐ single source of truth for robots (model / spawn height / camera / policy / how torque is applied)
  go2/              Unitree Go2 model (with head camera)
  g1/               Unitree G1 humanoid, 29 dof (imported from Menagerie by import_from_menagerie.py)
furniture.py        parametric furniture part library (chairs / tables / lamps / vases / plants…)
make_textures.py    procedural textures (wood floor / tile / marble / carpet / fabric / city skyline / wall art)
make_house.py       layout + robot → <scene>-<robot>.xml (MJCF)
check_scene.py      ⭐ scene self-check: verifies the product, not the claim. Run it after generating
walkthrough.py      first-person walkthrough for eyeballing a scene (WASD + mouse, collision + gravity)
make_docs_images.py renders the README screenshots (poses live in shots.py; one command re-renders)
house1-g1.xml · house2-g1.xml …   generated scenes (one file per scene x robot)
policies/           trained locomotion policies (ONNX + contract)
textures/ · docs/images/<scene>/  generated textures · README screenshots
```

## Quick Start

```bash
git clone https://github.com/jeffliulab/alice-house.git
cd alice-house
pip install mujoco numpy pillow

# Take a look at the house (scenes are already generated — just open them)
python -m mujoco.viewer --mjcf=house1-go2.xml    # single-floor apartment, with the quadruped
python -m mujoco.viewer --mjcf=house2-g1.xml     # three-storey house with stairs, with the humanoid

python walkthrough.py --scene house2             # or walk in yourself (first person)
```

Re-generate after changing the house:

```bash
python make_textures.py                        # textures (only if you changed them)
python make_house.py                           # every place x every robot
python make_house.py --scene house2 --robot g1 # just the three-storey house, humanoid
python check_scene.py                          # ⭐ always run this after generating
ALICE_SCENE=house2 python make_docs_images.py  # re-render the screenshots
```

`check_scene.py` is not a formality. It compiles every product in MuJoCo, then **ray-probes the
whole climb** — floor landing → up flight → half-landing → return flight → the storey above →
the door — sampling every 4.7 cm and requiring solid ground everywhere, no step taller than one
riser, and an end point exactly one storey higher. A separate check verifies the **four joints**
(each flight's last tread against the next landing: edge-to-edge, one riser apart).

Both checks exist for a reason. The earlier version probed each flight **in isolation**, so when
the return flight was attached to the shaft's far wall instead of the half-landing — a stair split
into two disconnected pieces — it reported **green**: walking around, there *was* a path.
**Proving a path exists does not prove it is a staircase.**

To actually **make a robot walk**: `policies/` holds trained ONNX policies with a
`contract.json` next to each (joint order, gains, observation layout — all of it). Feed a policy
a velocity command `(vx, vy, wz)` and it returns joint targets. For a working deployer, see
`world/sim-house-nav/sim.py` in [anima-zero](https://github.com/jeffliulab/anima-zero).

## One File per (Place, Robot)

`house1-go2.xml`, `house2-g1.xml` … each combination gets its own file. Why not one: a robot's
mesh path is baked in at MJCF compile time, so two robots cannot share a model, and neither can
two places.

**Places and robots are two independent registries** — `scenes/manifest.py` and
`robots/manifest.py` — crossed at generation time. The same G1 walks in either house; the same
house hosts either robot. The filename rule lives in `scenes/manifest.py` and consumers call it
rather than re-deriving it, so a rename cannot desynchronise the two sides.

**`robots/manifest.py` is the single source of truth for "what this robot is"** — where the model
lives, how high it spawns, what the camera is called, how torque is applied. Adding a robot means
appending one entry and re-running the generator.

⚠️ The manifest deliberately **does not repeat** anything already in the policy contract
(`contract.json`: joint order, gains, observation layout, control period). The contract is the
source of truth for those; copying them would guarantee they drift apart.

⛔ **The two robots apply torque in opposite ways** — recorded as `pd_mode` in the manifest, and
getting it backwards makes the robot fall over immediately. The Go2 was trained with explicit PD
(the deployer computes `−kd·qd` itself and zeroes the model's damping); the G1 with implicit PD
(`kd` goes into `dof_damping` for MuJoCo to apply, and the torque carries only the `kp` term).

## Changing a House / Adding New Places

Edit the room rectangles, doors, windows and furniture in `scenes/<name>/layout.py` and re-run the
generator, then `check_scene.py`. The part libraries (furniture, textures) are reused as-is.

Adding a **new place** means appending an entry to `scenes/manifest.py` and writing
`scenes/<key>/layout.py`. The generator does not change. A multi-storey place adds three things
on top of the flat-scene model — a `floor` key per room, a `FLOOR_Z(n)`, plus `STAIRS` (flights),
`LANDINGS` (half-landings), `WELL_WALLS` and `GUARDS` — and two keys that open the shaft
vertically: `no_ceiling` on the lower storeys, `floor_rects` on the upper ones so the floor landing
stays solid while the flights below stay open. How the stair is walked is described **once**, by
`stair_route(floor)`; the self-check and the walkthrough both follow it. Two independent copies of
that answer is precisely what went wrong before.

⚠️ **Stair dimensions are derived, not chosen.** Steps first → storey height → stairwell →
building footprint, never the other way round — set storey height and stair independently and the
top step ends up hanging in mid-air, which is exactly what happened in the predecessor project and
went unnoticed until a ball-roll test. Two more rules learned the hard way: **a flight has
`risers − 1` treads** (the top one *is* the landing); and treads are 0.30 m because a G1 foot is
~0.25 m and 0.26 m leaves a one-centimetre margin that a blind policy will miss.

---

## Versioning

See [CHANGELOG.md](CHANGELOG.md). Currently **v0.6**.

## License

The scene generator, furniture and texture libraries, robot manifest, locomotion policies and
documentation in this repository are **MIT** licensed (see [LICENSE](LICENSE)).

Third-party assets bundled here keep their own licenses: the Unitree Go2 and G1 models come from
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) under BSD-3-Clause — see
`robots/go2/GO2_MODEL_LICENSE` and `robots/g1/G1_MODEL_LICENSE`. What we changed in the G1 model
and why is written up in `robots/g1/G1_MODEL_UPSTREAM.md`.

## Acknowledgments

Unitree Robotics for the Go2 and G1 models · Google DeepMind for
[MuJoCo](https://mujoco.org) and [Menagerie](https://github.com/google-deepmind/mujoco_menagerie).
