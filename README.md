[![Language: English](https://img.shields.io/badge/Language-English-2f81f7?style=flat-square)](README.md) [![语言: 简体中文](https://img.shields.io/badge/语言-简体中文-e67e22?style=flat-square)](README_zh.md)

# alice-house · A House for Robots to Live In

[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE) [![Simulator](https://img.shields.io/badge/simulator-MuJoCo-blue?style=flat-square)](https://mujoco.org) [![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](https://www.python.org) [![Version](https://img.shields.io/badge/version-v0.15-lightgrey?style=flat-square)](CHANGELOG.md)

> 🤖 **If you are an AI agent, read [AGENTS.md](AGENTS.md) first** — the machine-facing entry point:
> what this repo is, where each fact lives, the entry commands, and the red lines.

**Procedurally generated indoor scenes, shipped with two Unitree robots and trained locomotion policies — clone it and they actually walk around, up the stairs included.**

**Alice's house** — an indoor scene generated entirely from code, for robots to look around in, walk through, search, and work in.

Not one line of geometry is hand-written: rooms, doors, windows, stairs, furniture and textures all
come out of one layout definition per place (`scenes/<name>/layout.py`). Change a house by changing
its layout and re-running the generator; the scene and whatever consumes it read the same source of
truth, so coordinates can never disagree in two places.

There are **four places** so far — a single-floor apartment, a three-storey house with stairs, a
62nd-floor Manhattan apartment whose windows look out over Central Park, and the duplex penthouse
above it where the furniture has **real collision** (the robot can sit on the sofa) — and one robot
can be dropped into any of them. Scenes and robots are two independent registries that get crossed
at generation time.

It also ships **robots** (Unitree Go2 quadruped, Unitree G1 humanoid) and their trained **locomotion policies** — so they really take steps, they don't teleport.

> Where the name comes from: Alice is robot number one in this series. This is her house.
> It may grow into an island one day — house, hillside trail, dock — with Alice visiting each.

---

## Table of Contents

- [What's Inside](#whats-inside) · [Robots](#robots) · [Floor Plan & Screenshots](#floor-plan)
- [apt1 — 232 Metres Up, Facing Central Park](#apt1--232-metres-up-facing-central-park)
- [apt2 — A Duplex Penthouse Where the Furniture Is Within Reach](#apt2--a-duplex-penthouse-where-the-furniture-is-within-reach)
- [Design Principles](#design-principles) · [Real Meshes as Clothing](#real-meshes-as-clothing)
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
| **apt1** | Full-floor Manhattan apartment, **62nd storey** — foyer / gallery / great room / dining / kitchen / primary suite / guest rooms | 13 spaces / 345 m² | Built for **what's outside**. Floor-to-ceiling glass on three sides, 232 m of air below, and a real aerial of Central Park in front. Tests perception where the visual signal is overwhelmingly out of reach |
| **apt2** | Duplex penthouse, **62nd–63rd storeys** — double-height great room + a real two-flight staircase | 24 spaces / 690 m² | Built for **what's within reach**. In the other three scenes every piece of furniture is a welded solid block; a robot can only bump into it. Here the dining chairs, armchairs and coffee table get **real collision** via convex decomposition (a ray passes between the chair legs), and the sofa is authored to the G1's leg length — seat at 0.35 m, so **the robot can actually sit on it** |

**Build order: house1 → house2 → apt1 → apt2.**

The names are inconsistent **on purpose**. `house1` and `house2` were the first two places
built in this repo, and they keep their original names — they are where the whole idea
(not one line of geometry written by hand, all of it generated from code) first worked.
house1 has only one floor, but it is still a house.
The third place is a Manhattan **apartment** on the 62nd floor rather than a house, so
naming by type starts there: `apt1`. `apt2` is the duplex penthouse directly above it,
built 2026-08-22 (design draft: [`docs/apt2-设计草案.md`](docs/apt2-设计草案.md)).

⛔ **Keys are not renamed lightly**: a key is the identifier a downstream consumer (the world
service) uses to pick a scene, so renaming one is a cross-repo break. apt1 was called `house3`
before v0.10; that rename put "this is an apartment" into the name, and it is the **only**
scene rename this repo has ever done.
⚠️ Its textures still live in `textures/house3/` and its material names still carry the `h3_`
prefix — that is the scene's **asset namespace** (and its original name), kept on purpose.

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

### apt1 — 232 Metres Up, Facing Central Park

![Manhattan apartment, ceiling hidden](docs/images/apt1/A1-户型俯视图.png)

house1 tests flat navigation, house2 tests climbing. **apt1 tests the window.** Three sides are
floor-to-ceiling glass, the floor slab sits 232.5 m above the street, and everything a camera sees
through that glass is unreachable — no amount of walking changes it.

| The whole view wall, great room | Down the 15 m sight line, from the front door |
|---|---|
| ![View wall](docs/images/apt1/V2-大客厅-整面观景墙.png) | ![Enfilade](docs/images/apt1/V1-贯通轴线-从入户门望公园.png) |

**None of that view is a matte painting.** It is built in four layers, and where each layer takes
over was decided by parallax arithmetic — move 8 m sideways and a building 120 m away shifts 61
pixels, one at 600 m shifts 12, one at 3 km shifts 2.4. Below ~600 m it has to be real geometry:

| Layer | What it is | Source |
|---|---|---|
| Sky | Real photographed sky, as six cube faces | [Poly Haven](https://polyhaven.com) HDRI (CC0) |
| 120–600 m | 12 named towers at their real heights (Central Park Tower 472.4 m, 111 W57 435.3 m…) | NYC Open Data |
| 0.6–4 km | **2716 real Manhattan buildings**, massing only | NYC Open Data building footprints |
| Ground | Real USGS aerial photography of Central Park, rotated 29.05° onto the street grid | USGS NAIP (public domain) |

⚠️ The building data must be filtered with `last_status_type` **including `'Merged'`** — 111 West
57th Street inherits the 1924 Steinway Hall record and is otherwise silently dropped, taking one of
the three needles that define the current Billionaires' Row silhouette with it.

#### Proving it isn't a backdrop

Two shots, same heading, camera moved 6 m east. Watch the near window mullions travel against the
park behind them: **near and far move by different amounts**, which a painted backdrop cannot do.
This is the whole reason the mid-ground is real geometry instead of a photograph.

| Camera 3 m west of centre | Same heading, 6 m east |
|---|---|
| ![Parallax left](docs/images/apt1/P1-视差对照-左.png) | ![Parallax right](docs/images/apt1/P2-视差对照-右.png) |

#### The building itself, and what it stands next to

The host tower is modelled too — you are inside a real massing, not a floating box. It sits **34 m
from the park's south edge** (the width of Central Park South), because the self-check caught the
first attempt: originally placed 120 m out — around 57th Street — with an entire row of real
buildings standing between the apartment and the park.

| The host tower from outside | Over the window frame, straight down | Central Park, full width |
|---|---|---|
| ![Host tower](docs/images/apt1/X1-本楼外景.png) | ![Looking down](docs/images/apt1/X2-越过窗框俯瞰公园.png) | ![Park panorama](docs/images/apt1/X3-公园全景.png) |

#### Inside

The plan is an enfilade: front door → gallery → great room line up on one axis, giving a 15 m
sight line that ends on the park. The gallery is a 12 m hanging wall; the great room opens to
dining and kitchen.

![Great room, dining and kitchen](docs/images/apt1/A2-客厅餐厅厨房.png)

| Gallery — 12 m of hanging wall | Dining room | Kitchen island |
|---|---|---|
| ![Gallery](docs/images/apt1/V3-画廊-12米展线.png) | ![Dining](docs/images/apt1/V4-餐厅望公园.png) | ![Kitchen](docs/images/apt1/V8-厨房中岛.png) |

| Primary bedroom, corner window | Guest room, facing Midtown | Spawn point, quadruped's eye height |
|---|---|---|
| ![Primary bedroom](docs/images/apt1/V5-主卧转角窗.png) | ![Guest room](docs/images/apt1/V6-客卧望中城.png) | ![Dog view](docs/images/apt1/V7-狗视角-玄关出生点.png) |

That last one is the point of the whole scene: at 0.38 m the quadruped sees mostly floor, skirting
and the underside of furniture — and a band of sky it can never reach. The same room through the
humanoid's 1.25 m camera is a different room.

Indoors, apt1 is the first place dressed with **real furniture meshes** rather than assembled
primitives. See [Real Meshes as Clothing](#real-meshes-as-clothing) for how they are attached
without changing a single collision.

#### Room by Room

Thirteen spaces on one floor, in three bands. The north band gets the park; the south band gets
Midtown; the spine in the middle gets no window at all — which is exactly what makes it
interesting for a robot that navigates by camera.

| Band | Rooms |
|---|---|
| **North — the view** | Primary bedroom · Dining room · Great room · Kitchen — all four against the view wall |
| **Middle spine — no windows** | Dressing room · Gallery (12.6 m hanging wall) · East hall — lamp-lit all day |
| **South — the city** | Primary bath · Guest room · Guest bath · Foyer · Laundry · Study |

| Study — desk against the southeast corner windows | Primary bath — freestanding tub, onyx wall |
|---|---|
| ![Study](docs/images/apt1/V9-书房.png) | ![Primary bath](docs/images/apt1/V11-主卫-独立浴缸.png) |

The laundry is deliberately **the robot's room**: a 0.95 m door onto the gallery's main line,
machines crowded at the south end, and the north half kept empty as a dock (`ROBOT_HOME_XY`) —
the robot waits there without standing in anyone's way. (The dressing room and the service rooms
photograph poorly — plain boxes — so they get words here, not cameras.)

#### A Day in apt1

The same floor is four different places at four times of day. The products on disk stay
byte-identical — **daylight is the product**; morning, dusk and night are *runtime presets*
(`scenes/apply_time_preset.py`) that rewrite light fields, material emission, the skybox and the
facade textures on the already-loaded model:

![Four times of day](docs/images/apt1/time-presets/T0-四时段对比.png)

| Morning 6:40 | Day |
|---|---|
| ![Morning](docs/images/apt1/time-presets/T-morning.png) | ![Day](docs/images/apt1/time-presets/T-day.png) |

| Dusk 19:35 | Night 23:10 |
|---|---|
| ![Dusk](docs/images/apt1/time-presets/T-dusk.png) | ![Night](docs/images/apt1/time-presets/T-night.png) |

- **Morning** — cool north sky, plus one warm shaft cutting across the kitchen island from the
  east window.
- **Day** — the product itself, untouched.
- **Dusk** — a north-facing flat never sees the sunset; it sees the **Upper West Side turn gold**
  across the park while the east side cools to mauve, and the west windows throw one long amber
  streak across the bedroom floor. That asymmetry *is* the sense of direction.
- **Night** — thousands of individually lit windows (a night facade texture, not an emission
  trick), warm practicals indoors, and Central Park as a **black hole** — the strongest single
  signature of the New York night.

Two hard-won facts are baked into the presets. First, MuJoCo's renderer only lights
**headlight + 7 model lights** (`mjMAXLIGHT=100` is scene *capacity*, not rendering capacity) —
so every phase is a re-aim of the same seven slots, and the `check_lights_render` gate goes red
if a scene ever declares more. Second, the robot's own XML ships a nameless directional light
that turns out to own ~68 % of the pixels; night begins by switching it off.

The stills double as the acceptance gate — mean brightness must fall monotonically
day → morning → dusk → night, and no room may drop to black:

```bash
python tools/make_time_stills.py --scene apt1
```

### apt2 — A Duplex Penthouse Where the Furniture Is Within Reach

![Robot sitting on the sofa](docs/images/apt2/S1-机器人坐在沙发上.png)

In the other three scenes every piece of furniture is welded to the world with zero degrees of
freedom — and for the mesh-clothed ones, the collision body is **a single solid box wrapping the
whole thing**. A robot can only bump into it: it cannot push it, pick it up, or sit on it.

apt2 exists to fix that. The shot above is not staged: the robot is placed in a seated pose and
then **3 seconds of physics are simulated** before the frame is taken. The pelvis rises 4.6 cm,
slides 3.1 cm horizontally, and the torso tilts 11.4° — it really is sitting.

#### Why it could not sit before: the parts are split by *material*

The intuitive fix is "the furniture already has a real mesh, just turn collision on". **That does
not work.** `decor/convert.py` splits parts **by material** (glTF primitives are grouped that way),
while MuJoCo only ever uses the **convex hull** of a collision mesh. Together, the hull swallows the
cavity whole:

| Asset | Convexity (solid volume ÷ hull volume) |
|---|---|
| Dining chair | 0.30 |
| Armchair frame | 0.12 |
| Round coffee table | 0.22 |
| Bed upholstery | 0.07 |

⇒ Turning collision on merely replaces "one solid box" with "one solid hull". The space between the
chair legs is still solid.

The fix is **CoACD convex decomposition** (`decor/hulls.py`, run once offline; the hulls are not
committed). Both columns below are measured **straight off the two shipped artifacts** — rays cast
downward, reading the height of the first surface hit (cm; `·` = reached the floor):

```
 apt1 · armchair (one hidden box)     apt2 · dining chair (17 CoACD hulls)
  110  110  110  110  110  110  110    ·   94   95   95   95   94    ·   ← backrest
  110  110  110  110  110  110  110    ·   78   87   87   86   79    ·
  110  110  110  110  110  110  110    ·   36   45   46   46   36    ·   ← seat
  110  110  110  110  110  110  110    ·   43   45   45   45   43    ·
  110  110  110  110  110  110  110    ·   43   43   43   43   43    ·

  a uniform 110 cm across the whole     backrest 94–95, seat 43–46, and the
  footprint — a 0.90×1.06×1.10 brick    floor visible at the edges — a chair
```

And one horizontal ray, same height, both scenes:

| Height | apt1 armchair (one box) | apt2 dining chair (hulls) |
|---|---|---|
| 0.45 m (seat height) | hits the box | hits `furn_dn_w1__h8` at 0.737 m — **the chair really is there** |
| 0.26 m (**below** the seat) | hits `furn_gr_ch1` at **0.721 m** — blocked by the solid box | **passes straight through the chair**, travelling 15.25 m before hitting the library shelving |

⇒ The same ray: blocked in one scene, through the chair legs in the other. That is the whole
meaning of "real collision".

| Six chairs with real collision | Great room: armchairs and table too |
|---|---|
| ![Dining](docs/images/apt2/V3-餐厅-六把真碰撞餐椅.png) | ![Great room](docs/images/apt2/V2-大客厅-三开间落地窗.png) |

**Cost is not the problem**, and that too is measured:

| | ngeom | of which collision hulls | Realtime factor |
|---|---|---|---|
| apt1 (all furniture is hidden boxes) | 3329 | 0 | 15.7× |
| **apt2 (12 items with real collision)** | 3719 | **184** | **14.1×** |

Real collision across the whole apartment costs about 10%. ⭐ The key is that `nmeshgraph` is
**independent of item count** — meshes are shared per asset, so six identical dining chairs declare
one set of hulls and repeated placement is essentially free.

⚠️ But don't say "meshes are free" any more: MuJoCo **skips qhull entirely** when
`contype=0 and conaffinity=0`, which is the only reason the purely visual coats are cheap. Turn
collision on and qhull runs.

#### ⛔ One thing that fails silently if you skip it

MuJoCo's **default contact is too soft**: a 3.9 kg slab dropped from 1.20 m onto a 49 mm-thick seat
hull **passes straight through** to the floor. The threshold is sharp — 3.2 mm of travel per step is
fine, 4.1 mm punches through. ⚠️ A smaller timestep does not help, and neither does `margin` (both
measured). Only one thing works: `solref="0.005 1"`.

Skip it and you get "sitting down slowly is fine, falling onto it clips through" — while **the model
compiles without complaint and every slow test passes**. Hence a dedicated acceptance gate.

#### The sofa deliberately does **not** use CoACD

The criterion is *who decides this piece's dimensions*. What a dining chair looks like is the
artist's call, so fidelity to the mesh is what matters. But a sofa's seat height is decided by
**the robot**. Measured off the G1: shank 0.318 m + ankle 0.033 m ⇒ with the knee at 90° and the
sole flat, the seat wants to be ≈ **0.351 m**. Placing the G1 in a seated pose, holding it with the
policy contract's gains, and stepping 3 seconds of physics:

| Seat height | Result |
|---|---|
| 0.30 m | ✅ stays seated |
| **0.35 m** | ✅ stays seated |
| 0.40 m | ❌ slides off (torso tilts 33.6°) |
| 0.45 m | ❌ falls over (80.5°) |

⇒ **The ceiling is 0.36 m.** Fetch a real sofa mesh and its seat sits wherever the artist put it,
and `_fit_scale` only does **uniform** scaling — squashing the seat down to 0.35 shrinks the entire
sofa and wrecks its proportions. So the sofa is authored from primitives (`furniture.sofa()`) with
the seat pinned at 0.35 and a depth of 0.45.

⭐ An unexpected corollary: **real human furniture is simply too tall for a 1.32 m G1** — the Poly
Haven dining chair's seat measures 42.3–46.1 cm and the armchair's 53.0–70.9 cm, both inside the
failure band. They keep their real collision (the robot can bump them and slide a foot between the
legs); they just don't appear on the "sittable" list.

#### The double-height room and that staircase

| The void, seen from a camera hanging in it | Two-flight stair | 63rd-floor gallery |
|---|---|---|
| ![Void](docs/images/apt2/X3-双高客厅-挑空.png) | ![Stair](docs/images/apt2/V5-楼梯间-从楼下往上看.png) | ![Gallery](docs/images/apt2/V6-上层环廊.png) |

The vertical dimensions are derived in the **opposite direction** from house2, and they have to be:
the storey height is pinned by apt1's `FLOOR_TO_FLOOR = 3.75` (`ELEV = 62 × 3.75`; change it and the
entire city outside shifts). So the storey height is fixed and the **riser height is derived**,
leaving one integer free — how many risers per storey.

| Risers/storey | Rise | Per flight | Run length | Slope | |
|---|---|---|---|---|---|
| 20 | 0.18750 | 10 | 2.70 | 32.01° | ❌ over the 0.175 code limit |
| 22 | 0.17045 | 11 | 3.00 | 29.60° | ✅ but right at the limit |
| **24** | **0.15625** | **12** | **3.30** | **27.51°** | ✅ chosen |

The city outside is **referenced directly from apt1** (`SKYBOX` / `SKYLINE` / `GROUND_SLABS`), and
the building footprint is bit-identical to apt1's (23.0 × 15.0 m), so the facade dimensions and the
park-sightline constants are reused unchanged.

| Top view (the void reaches down to floor 62) | Enfilade axis | Primary bedroom corner |
|---|---|---|
| ![Top](docs/images/apt2/A1-户型俯视图.png) | ![Axis](docs/images/apt2/V1-贯通轴线-从入户门望公园.png) | ![Bedroom](docs/images/apt2/V7-主卧转角窗.png) |

#### How the sitting shot is produced

⛔ It cannot be rendered statically like the others — **the robot in the artifact stands at the world
origin** (placement is a runtime concern). So the pose is declared in the layout's `SIT_POSES` **by
joint name** (⛔ never by index — indices drift silently when the robot changes), assembled by
`scenes/apply_pose.py`, and **stepped to a settled state** before the frame is taken:

```bash
ALICE_SCENE=apt2 python tools/make_docs_images.py S1
#   settled: pelvis +0.046 m / slide 0.031 m / tilt 11.4° / contacts 11
```

The metrics are printed alongside the render because "the picture looks right" and "the robot is
actually seated" are two different claims.

⚠️ **Not done yet**: furniture **articulation** (fridge doors and drawers still don't open) and a
**manipulation policy** (the current G1 policy is flat-ground locomotion — the robot is *placed* in
the seated pose, it does not walk over and sit down by itself).
See [`待办事项-可交互家具.md`](待办事项-可交互家具.md).

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
ALICE_SCENE=apt1 python tools/make_docs_images.py        # all of that scene's shots
ALICE_SCENE=apt1 python tools/make_docs_images.py V9 V11 # only the ones you name
python tools/make_time_stills.py --scene apt1            # the four times of day (also the gate)
```

The scene comes from the `ALICE_SCENE` environment variable (defaults to the default scene, which
is probably not the one you just changed).

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
city skyline backdrop. In apt1 that backdrop is replaced by real data all the way out.

### Real Meshes as Clothing

house1 and house2 build every piece of furniture out of primitives. apt1 keeps doing that — and
then puts a **downloaded mesh on top as clothing**. The box underneath is still the collision
truth; the mesh is purely visual (`contype="0" conaffinity="0"`).

The rule that makes this safe is a **containment invariant**: every mesh is scaled to fit
completely *inside* the box it dresses, so any ray that could hit the mesh hits the box first, and
**every ray reading is bit-for-bit what it was before the furniture got dressed**. This matters
because `mj_ray` does **not** honour `contype` — "it's only visual" is true for physics and false
for ray casting, and every consumer's lidar and navigation probe goes through `mj_ray`.

That invariant is enforced by a self-check, not by good intentions: `check_decor_ray_invariance`
fires rays from outside every dressed piece and requires the readings with and without the meshes
to match exactly.

Two traps found the hard way, both of which compile clean and render fine:

- ⛔ **Hiding the collision box with `rgba` alpha = 0 deletes it from `mj_ray`.** The box still
  collides, so physics looks right, while navigation and lidar quietly see straight through the
  furniture. Put it in a non-drawn `group` instead — `group` controls drawing only; rays are
  unaffected. ⛔ But not just any number: **2 and 3 belong to the robot** (MuJoCo Menagerie
  convention). If the house takes one of them, a consumer can no longer tell "the robot" from
  "the house" and will refuse to start. The house uses **4**
  (`make_house.HIDDEN_BOX_GROUP`), and it must stay ≤ 5 — the group mask has only six slots.
- ⛔ **Making the box bigger does not fix a mesh that pokes out**, because the fit scale grows the
  mesh proportionally and the overshoot stays. The real cause is how MuJoCo compiles a `<mesh>`,
  and it bites **twice**: it moves the vertices into the inertial frame — translating to the centre
  of mass **and rotating to the principal axes** — so what you read back from `mesh_vert` is
  neither file coordinates nor merely translated file coordinates; and it then **compensates for
  that move itself** (copying it into `geom_pos`/`geom_quat`), so placement must **not** apply it
  again. Miss the rotation and the recorded bounds come out with their axes permuted (the bed was
  recorded as 0.66 × 2.21 × 2.15 against a true 1.69 × 2.06 × 0.78); apply the translation twice
  and every part of a multi-part asset flies outward by its own centre of mass.
  `decor/calibrate.py` measures the true bounds from a compiled probe model and writes them back
  into the lock file, and two checks in `check_scene.py` — lock self-reconciliation, and measuring
  the mesh vertices directly — keep both mistakes from coming back.

Asset bytes are **not** stored in this repository. `decor/manifest.py` lists what to fetch,
`decor/fetch.py` downloads it behind an **executable licence gate** — anything whose upstream
licence is outside the allow-list is refused, not merely warned about — and `decor.lock.json`
records a SHA-256 per part. A bare clone still generates every scene; the pieces simply stay
undressed.

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
  apt1/layout.py  62nd-floor Manhattan apartment: glazing, the four view layers, real furniture
  apt1/shots.py
  apt1/nyc_massing.py  ⭐ 2716 real Manhattan buildings (generated by make_view.py --nyc; committed)
  furniture.py      parametric furniture part library (chairs / tables / lamps / vases / plants…), shared by every scene
decor/              ⭐ real furniture meshes — scripts committed, asset bytes never
  manifest.py       what to fetch + the executable licence allow-list
  fetch.py          download → convert → decimate → write decor.lock.json + ATTRIBUTION.md
  convert.py        glTF/GLB → one-mesh-per-material OBJ + PNG (needs trimesh; the generator never imports it)
  calibrate.py      ⛔ measures each mesh's real centre of mass and bounds from a compiled probe model
  robocasa.py       RoboCasa kitchen appliances → decor parts (strips joints/actuators/option)
  assets/           gitignored — the bytes live here after fetching
robots/
  manifest.py       ⭐ single source of truth for robots (model / spawn height / camera / policy / how torque is applied)
  go2/              Unitree Go2 model (with head camera)
  g1/               Unitree G1 humanoid, 29 dof (imported from Menagerie by import_from_menagerie.py)
tools/              entry-point scripts, all run from the repo root: `python tools/<name>.py`
  make_house.py       layout + robot → build/<scene>-<robot>.xml (MJCF)
  check_scene.py      ⭐ scene self-check: verifies the product, not the claim. Run it after generating
  walkthrough.py      first-person walkthrough for eyeballing a scene (WASD + mouse, collision + gravity)
  make_docs_images.py renders the README screenshots (poses live in shots.py; one command re-renders)
  make_textures.py    procedural textures (wood floor / tile / marble / carpet / fabric / city skyline / wall art)
  make_view.py        apt1's window view: --sky --sky-phase (HDRI → cube faces, per time of day) · --nyc (building footprints) · --naip (aerial) · --calib
  make_time_stills.py the four times of day: renders T-*.png + T0 collage, and gates the presets (brightness must fall monotonically)
  fetch_assets.py     downloads the CC0 interior materials (ambientCG), with SHA-256 bookkeeping and --verify
build/              ⭐ **deliverables** (tracked, not a build cache): <scene>-<robot>.xml
                    ⛔ the relative paths inside them assume "exactly one level below the repo
                    root" — don't move this directory
textures/ · docs/images/<scene>/  generated textures · README screenshots
                    ⚠️ apt1's textures live in textures/house3/ and its material names carry the
                    h3_ prefix — that is the scene's asset namespace, keeping its original name
                    on purpose (see "Build order" above)
```

## Quick Start

```bash
git clone https://github.com/Yanshi-Robotics/alice-house.git
cd alice-house
pip install mujoco numpy pillow

# Take a look at the house (scenes are already generated — just open them)
python -m mujoco.viewer --mjcf=build/house1-go2.xml    # single-floor apartment, with the quadruped
python -m mujoco.viewer --mjcf=build/house2-g1.xml     # three-storey house with stairs, with the humanoid
python -m mujoco.viewer --mjcf=build/apt1-g1.xml     # 62nd floor over Central Park, with the humanoid

python tools/walkthrough.py --scene apt1             # or walk in yourself (first person)
```

Re-generate after changing the house:

```bash
python tools/make_textures.py                        # textures (only if you changed them)
python tools/make_house.py                           # every place x every robot
python tools/make_house.py --scene house2 --robot g1 # just the three-storey house, humanoid
python tools/check_scene.py                          # ⭐ always run this after generating
ALICE_SCENE=house2 python tools/make_docs_images.py  # re-render the screenshots
```

Optional. apt1's textures and its 2716 buildings are **already committed**, so it compiles
straight from a clone; the commands below only need re-running if you want to change them. The
furniture meshes are the exception — their bytes are never stored, so on a fresh clone apt1's
furniture stays as plain boxes until you fetch them:

```bash
pip install trimesh fast-simplification           # only needed by the fetch/convert side

python tools/fetch_assets.py                            # CC0 interior materials (ambientCG)
python tools/make_view.py --all                         # sky cube faces · Central Park aerial · 2716 buildings
python -m decor.fetch                             # furniture meshes (Poly Haven CC0 + Objaverse CC-BY)
python -m decor.robocasa                          # kitchen appliances (RoboCasa, CC-BY)
python -m decor.calibrate                         # ⛔ always run after either of the two above
python tools/make_house.py && python tools/check_scene.py     # regenerate and verify
```

⛔ `decor/calibrate.py` is not optional after fetching. It measures each mesh's real centre of
mass and bounds from a compiled probe model; without it the meshes sit slightly wrong and poke out
of their collision boxes, which the ray-invariance check will reject.

`check_scene.py` is not a formality. It compiles every product in MuJoCo, then **ray-probes the
whole climb** — floor landing → up flight → half-landing → return flight → the storey above →
the door — sampling every 4.7 cm and requiring solid ground everywhere, no step taller than one
riser, and an end point exactly one storey higher. A separate check verifies the **four joints**
(each flight's last tread against the next landing: edge-to-edge, one riser apart).

Both checks exist for a reason. The earlier version probed each flight **in isolation**, so when
the return flight was attached to the shaft's far wall instead of the half-landing — a stair split
into two disconnected pieces — it reported **green**: walking around, there *was* a path.
**Proving a path exists does not prove it is a staircase.**

**Policies do not live here (since 2026-09-02).** Trained locomotion policies are training
products, not scene assets; consumers keep them on their own policy shelf as `policy.onnx` +
`contract.json` + `release.yaml` (torque mode, command ranges, command deadband, turning behaviour).
This repository ships places and robot bodies only. For a working deployer see
[NERV](https://github.com/Yanshi-Robotics/nerv), the successor of anima-zero.

## One File per (Place, Robot)

`house1-go2.xml`, `house2-g1.xml` … each combination gets its own file. Why not one: a robot's
mesh path is baked in at MJCF compile time, so two robots cannot share a model, and neither can
two places.

**Places and robots are two independent registries** — `scenes/manifest.py` and
`robots/manifest.py` — crossed at generation time. The same G1 walks in either house; the same
house hosts either robot. The filename rule lives in `scenes/manifest.py` and consumers call it
rather than re-deriving it, so a rename cannot desynchronise the two sides.

**`robots/manifest.py` is the single source of truth for "what this robot is"** — where the model
lives, how high it spawns, what the camera is called, which bodies are its feet. Adding a robot means
appending one entry and re-running the generator.

⚠️ The manifest deliberately **does not repeat** anything that belongs to a policy (joint order,
gains, observation layout, control period, torque mode, command ranges). Those live with the policy
on the consumer's shelf; copying them here would guarantee they drift apart.

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

See [CHANGELOG.md](CHANGELOG.md). Currently **v0.14**.

## License

Code and assets are licensed separately. Four tiers:

**1 · Code — MIT** (see [LICENSE](LICENSE)). The scene generator (`make_house.py`,
`make_textures.py`, `check_scene.py`, `walkthrough.py`, `make_docs_images.py`), the furniture
library, the scene layouts, and the manifests.

**2 · Assets authored here — MIT.** The procedurally generated textures in `textures/`, the
generated `<scene>-<robot>.xml` products. These are
produced by code in this repository from no external source material.

**3 · Third-party assets bundled here — each keeps its own license.** They are *not* covered by
the MIT license above. Every such asset ships in its own directory with its own license file:

| Path | Source | License |
|---|---|---|
| `robots/go2/` | [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) — Unitree Robotics | BSD-3-Clause — see `robots/go2/GO2_MODEL_LICENSE` |
| `robots/g1/` | [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) — Unitree Robotics | BSD-3-Clause — see `robots/g1/G1_MODEL_LICENSE` |

What we changed in the G1 model and why is written up in `robots/g1/G1_MODEL_UPSTREAM.md`.

apt1's window view is built from **data**, not bytes copied out of someone's dataset. Two sources
are redistributed here (the derived coordinate tables in `scenes/apt1/nyc_massing.py`); the rest
is fetched on your machine:

| What | Source | Terms |
|---|---|---|
| 2716 building footprints (bounding boxes only) | NYC Open Data `5zhs-2jue` | Local Law 11 of 2012, Admin Code §23-502(d): no registration, no licence, no restriction on use — **and no share-alike**. Attribution kept in `textures/house3/ATTRIBUTION.md` |
| Central Park aerial photography | USGS NAIP | **Public domain** (US federal work) |
| Sky cube faces, interior materials | Poly Haven · ambientCG | **CC0-1.0** — the derived PNGs *are* committed (`textures/house3/`), since apt1 will not compile without them |
| Furniture meshes | Poly Haven | **CC0-1.0** — fetched, not stored |
| Bed and nightstand meshes | Objaverse (@elba) | **CC-BY-4.0**, verified per object — fetched, not stored |
| Kitchen appliances | RoboCasa via NVIDIA's HuggingFace mirror | **CC-BY-4.0** — fetched, not stored |

⛔ **OpenStreetMap is deliberately not the source** for the building data. Coverage is comparable —
it was largely imported *from* this same city dataset — but committing a 2716-row coordinate table
derived from OSM would constitute a "Derivative Database" under ODbL, attaching share-alike to that
file inside an MIT repository.

**4 · Third-party datasets this repository does NOT redistribute.** Some scenes can be dressed
with meshes and textures from external datasets. Their owners license them on their own terms,
and in several cases forbid redistribution outright, so **none of their bytes are stored here** —
fetch scripts download them into gitignored directories on your machine, under the terms you
accept directly from the upstream provider. Nothing in this repository grants you any rights to
them.

> **A note on why this repo stays MIT.** Relicensing to non-commercial would not unlock the
> datasets people usually ask about: 3D-FRONT/3D-FUTURE and PartNet-Mobility forbid public
> redistribution as a *contract* term, and BEHAVIOR-1K ships its assets encrypted. A license
> *you* adopt cannot enlarge rights *someone else* granted you. Meanwhile NonCommercial would
> propagate to rendered images — including this README's figures. Keeping code permissive and
> fetching restricted data at runtime is the same pattern Habitat, RoboCasa, ManiSkill and
> BEHAVIOR-1K all use.

## Acknowledgments

Unitree Robotics for the Go2 and G1 models · Google DeepMind for
[MuJoCo](https://mujoco.org) and [Menagerie](https://github.com/google-deepmind/mujoco_menagerie).
