# apt furniture interaction

apt is the scene for developing household interaction. Its native walkthrough supports
physical appliance operation, movable task objects and reversible lighting presets.
The current interaction controller is operated by a person inspecting the scene.

## Available objects

| Object | Motion | Joint count |
|---|---|---:|
| Refrigerator | Two doors and four drawers | 6 |
| Stove and oven | Oven door, sliding rack and six rotary controls | 8 |
| Sink | Handle temperature axis, handle opening axis and swiveling spout | 3 |
| Range hood | Five buttons with millimetre travel | 5 |

Six dining chairs and three task props—a can, fruit and book—are independent free bodies.
Their visual meshes and collision shapes move together. Chairs, armchairs and coffee tables
retain the existing decomposed collision shapes, including gaps below their seats and tops.
Armchairs and coffee tables remain fixed. Cabinet fronts, island stools, wardrobes,
washer/dryer doors, bathroom fixtures and elevator doors remain static.

The sofa retains the 0.35 m seat and saved G1 pose. Ordinary chairs retain their furniture
scale; they have not been shrunk to make G1 sitting easier.

![Open refrigerator](../images/apt/interactions/fridge-open.png)

## Controls

```bash
python tools/walkthrough.py --scene apt --robot g1
```

| Input | Action |
|---|---|
| Mouse / WASD | Look and move the inspection camera |
| E | Open/close a selected joint, or press/release a button |
| [ / ] | Decrease/increase the selected joint's target by 15% of its range |
| J | Select another joint belonging to the same part, such as the sink handle |
| G | Grab/release a movable object at the pointed surface |
| L | Cycle day, morning, dusk and night |
| Backspace | Cancel interaction and reset furniture to the generated starting state |
| Tab | Return the inspection camera to its starting point |
| Esc / Q | Release the mouse / exit |

Aim at an actual moving part within two metres. Walls, closed doors and other geometry
block selection. Open refrigerator doors before pulling out their drawers, and open the
oven before extending the rack. The overlay shows the selected joint, measured opening
and action result. A blocked action times out instead of passing through the obstacle.

Dragging applies a limited force at the selected point. Moving the camera too quickly can
make an object lag, rotate or collide. Releasing an object restores unsupported motion under gravity.
The inspector parks the robot while stepping furniture physics; its camera does not actuate
the G1. A reset intentionally returns all furniture to its initial state, whereas changing
the time preset preserves the current furniture positions.

## Physical representation

The original RoboCasa body hierarchy, joint axes, limits, damping, friction and named sites
are recorded in [articulation.lock.json](../../decor/articulation.lock.json). Appliance
collision is built from the source's boxes and cylinders. No enclosing collision box spans
an open door, drawer or oven cavity. The sink is installed in a real worktop cutout.

The generator converts angular limits to the robot model's compiler units and scales linear
travel with the asset. It preserves fixed glass children under their moving doors. Adjacent
body exclusions cover native hinge and runner overlaps; other collisions remain active.
The source's defaults, actuators, global options and keyframes are not imported.

The controller applies bounded forces through MuJoCo. Joint damping is integrated implicitly
to keep small knobs stable, and the source damping is restored when an action ends. Actions
do not write `qpos`. The deliberate scene reset is separate. A joint's `ref` specifies its
reference coordinate; changing it alone does not visually open the door.

Dining-chair collision comes from CoACD convex decomposition, not from enabling collision on
a mesh split by material. The latter would fill concave spaces with convex hulls. Existing
firm-contact settings (`solref="0.005 1"`) remain on the furniture collision parts and are
checked by the scene verifier. Movable collision parts have priority 1 so their contact
settings also apply against the otherwise softer static worktops.

Grab targets advance at up to 0.5 m/s. If a held point falls more than twice the
controller's expected steady carrying lag behind that target, the controller releases
its force and reports `blocked`. The measured object position remains available to the
operator. This also handles a cursor dragged through a wall without forcing the object
through it. Releasing or cancelling clears the controller's own force.

The four appliances reuse the existing 28 OBJ parts without reprocessing their vertices.
The new extraction record contains archive, source XML and part checksums, source URLs and
CC-BY-4.0 attribution. The original [decor lock](../../decor/decor.lock.json) and inherited city and robot
assets are preserved.

## Asset setup

The repository includes authored textures, the city environment and the articulation metadata.
Downloaded furniture bytes belong in ignored `decor/assets/` and `.cache/` directories.
To reproduce the detailed scene after a fresh clone:

```bash
pip install mujoco numpy pillow glfw trimesh fast-simplification coacd
python -m decor.fetch
python -m decor.robocasa
python -m decor.calibrate
python -m decor.hulls
python tools/make_house.py --scene apt
python tools/check_scene.py --scene apt
```

`decor.calibrate` measures mesh alignment. `decor.hulls` builds the chair and table collision
parts. These preparation steps can update lock metadata; review the resulting diff when
upgrading assets. The city and interior textures are already tracked and need no
network regeneration.

Run `python -m decor.articulation` only when rebuilding the appliance metadata from its
upstream archives. It checks that the source parts match the imported OBJ bytes and rejects
unsupported body transforms. The committed metadata suffices for normal scene generation.

The simpler fresh-clone mode retains appliance joints and analytic shapes. Full-fidelity
chair gaps and photographic furniture require the downloaded meshes and decomposed hulls.

## NERV and robot skills

NERV identifies the controlled robot from its actuated body tree, allowing passive scene
objects to have their own free joints. Furniture adds no robot actuators: G1 still has 29,
and the generated Go2 variant has 12. NERV currently registers the G1 variant of apt.

The world supplies `scenes.operator.SceneRuntime` for NERV's operator interface, separate from
robot motor commands and brain tools. The same runtime supplies the facility catalogue, measured
joint state, bounded-force interaction, task evaluation and reversible time presets. Its consumer
owns simulation stepping, synchronization, camera access and operator control. The read-only
[Explore export](../explore/README.md) uses that catalogue to display floors, rooms, fixtures,
passage checkpoints and inspection routes.

The refrigerator task uses the right compartment's middle shelf, selected in `FRIDGE_TASK` in
the apt layout. Its target volume is derived from the compiled shelf, divider, side wall and
back-wall collision parts. To complete it, open the cold-compartment door, place the entire can
inside the marked volume, release it onto that specific shelf, wait at least 0.5 simulated
seconds for stable support, and close the door. The evaluator checks actual geometry, velocity,
contact normal and support force. It rejects held, partially inserted, unsupported, moving or
wrong-shelf placements. Contact penetration over 1 cm invalidates the attempt until reset;
the consumer must call `observe_step()` after each physics step to capture brief violations.

`SceneRuntime.reset()` cancels forces and clears task state without resetting physics. A full
scene reset belongs to the consumer: cancel control first, reset MuJoCo data, restore the robot
starting state, run forward dynamics and clear the runtime. A time change preserves furniture
state. Appliance doors are passive hinges after an action ends; a drawer can physically push
an unlocked door open, so reaching its target is assessed together with the resulting contacts.

The released G1 policy provides walking and turning. It does not provide grasping, opening,
sitting down or stair climbing. Autonomous manipulation requires a suitable hand model and
trained policies, followed by validation in this scene. Operator-applied forces and saved poses
do not establish those robot skills. Water flow, temperature, cooking and fan operation remain
outside the scene mechanics; turning a knob changes its measured angle only.

## Reproduction and checks

```bash
python tools/check_interactions.py --robot g1 --output temp/interactions/g1.json
python tools/check_interactions.py --robot go2 --output temp/interactions/go2.json
python tools/check_operator.py
python tools/check_interaction_cases.py
python tools/check_residences.py
python tools/render_interactions.py
python tools/make_time_stills.py --scene apt
python tools/render_residences.py --scene apt --contract ../policies/g1-29dof-turn/contract.json
python tools/benchmark_residences.py --scene apt --seconds 30 --output temp/interactions/runtime
```

Rendering and the runtime benchmark need an available graphics context. Follow the host's GPU
queue policy. The runtime command requires the NERV parent repository and released G1 policy;
it starts no network listeners and does not restart resident services.

[Interaction and Explore CPU checks](../explore/verification/README.md) ·
[Residence rendering validation](../residences/migration/validation.md) · [Residence guide](../residences/README.md)
