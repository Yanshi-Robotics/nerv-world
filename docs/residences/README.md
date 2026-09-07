# Residence scenes

`house` is a three-storey California hillside estate. Its 80 × 70 m property includes a
30 × 25 m lawn, a 15 × 6 m swimming pool, a driveway and a furnished house. The ground
floor connects the entrance, living suite, dining room and garden rooms. Bedrooms and
family spaces occupy the second floor; a studio, gym and viewing terrace occupy the third.
The original two-flight stair dimensions remain 0.16 m rise and 0.30 m tread, with
1.20 m flights, 1.40 m landings and a 2.88 m storey height.

![Estate and hillside](../images/house/X1-整栋外景.png)

The entrance is fixed open. Robots can cross the property and approach the closed outer
gate. Walls and the gate form a continuous collision boundary. The surrounding roads,
hills and neighboring houses are visual scenery with no accessible interiors.
The pool has separate walls, bottom, steps and water: water is visual only, with no
buoyancy or swimming simulation. The terrace provides a route around the basin.

![Pool terrace](../images/house/X5-泳池露台.png)

`apt` remains a 62nd–63rd floor Manhattan duplex with a double-height living room and
the existing Central Park orientation. Pale oak, limestone, linen, walnut and dark metal
are independently defined for the two upgraded scenes. Rounded furniture, cabinet panels,
bedding, curtain folds and skirting provide detail at robot camera distances.
Dining chairs, armchairs and coffee tables retain their decomposed collision shapes;
the living-room sofa retains its 0.35 m seat and existing G1 sitting pose.

![Duplex living room](../images/apt/V2-大客厅-三开间落地窗.png)

The duplex also supports [interactive kitchen fixtures, movable task objects and four lighting presets](../interactions/README.md).

## Reproduction

Run these commands from the scene-library root after installing the dependencies and
fetching the decor assets described in the main README. `make_house.py` generates both
G1 and Go2 variants; edit the layouts instead of editing generated XML.

```bash
python tools/make_residence_textures.py
python tools/make_house.py --scene house
python tools/make_house.py --scene apt
python tools/check_scene.py --scene house
python tools/check_scene.py --scene apt
python tools/check_residences.py
python tools/walkthrough.py --scene house --selftest
python tools/walkthrough.py --scene apt --selftest
```

The regression command checks saved city coordinates, building bounds, source assets,
district lighting groups and four time presets. It also verifies reproducible canonical
builds, estate routes, the closed boundary and the non-supporting pool surface.
See the [migration guide](migration/README.md) for retirement and recovery details.

## NERV

`house/world.yaml` registers the world for `humanoid-unitree-g1`, spawning at the
first-floor robot room. `apt/world.yaml` retains its existing configuration. Both use
640 × 480 images at a configured 12 fps with first-person and third-person cameras.
NERV discovers descriptors when its registry is constructed; an already running registry
must be reloaded by the operator before its world list includes a newly added descriptor.

With NERV's Python environment, the following command runs the released G1 policy,
paced physics and the actual two MJPEG generators. It opens no network ports and does
not interact with existing services. Submit rendering through any GPU scheduling system
required by the host.

```bash
python tools/benchmark_residences.py --seconds 30 --output temp/residence-runtime
```

The runtime report records each stream separately and measures simulation time against
wall time. MuJoCo's native renderer uses its own specular and shininess controls;
these scenes do not depend on a PBR postprocessing engine.

## Source definitions

- [house layout](../../scenes/house/layout.py) and [estate](../../scenes/house/estate.py): rooms, circulation, property and scenery.
- [apt refinement](../../scenes/apt/refinement.py): independent materials and furniture detail.
- [residential components](../../scenes/residence.py): rounded meshes, metric UVs and shared opt-in components.
- [asset record](assets.json): authored textures and reused asset licenses and hashes.
- [current validation results](migration/validation.md): collision checks, environment preservation and actual dual-camera measurements.
