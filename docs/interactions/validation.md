# apt2 interaction validation

Historical validation before canonical migration, preserved with its original names and
measurements. See the [current validation](../residences/migration/validation.md).


Tested on 2026-09-07 with MuJoCo 3.12.0, the NERV Python environment and an NVIDIA
RTX 5070 Ti. Furniture inspection, robot walking and camera performance are separate checks.
The [source checksums](verification/source-sha256.json) identify the tested scene and core code.

## Results

| Check | Result | Evidence |
|---|---|---|
| Appliance physics, G1 and Go2 | All 22 joints reached their open and closed targets: 44 targets per robot variant | [G1](verification/physics/g1.json), [Go2](verification/physics/go2.json) |
| Movable props | Nine free bodies loaded; the can was lifted by force, released and returned to the counter | Same physics records |
| Failed actions and reset | Distance, occlusion, blocked timeout, cancellation and force cleanup passed | Same physics records |
| Scene structure | Room access, stair continuity, headroom, furniture collisions, glazing and exposed edges passed | [Scene checks](verification/checks/scene.txt), [walkthrough](verification/checks/walkthrough.txt) |
| Reference scenes | 171 protected files and four regenerated house1/apt1 robot XML files matched byte for byte | [Reference checks](verification/checks/references.json) |
| Native inspector | Door operation, four lighting switches, grab/release and reset passed in a real GLFW context | [Results](verification/render/inspector.json), [harness](verification/render/check_inspector.py) |
| Night lighting | All 24 rooms had readable floor samples; lowest room mean was 25.3/255 against a minimum of 8/255 | [Lighting measurements](verification/render/lighting.json) |
| NERV regression | 22 selected tests passed, including seven controlled-robot/free-object cases | [Test output](verification/checks/nerv-tests.txt) |

The appliance controller uses bounded forces and implicit damping; it does not set joint
positions to satisfy the target. The physics check verifies finite states, opening fractions
and contact penetration below 1 cm. Source damping is restored when an action ends.
The can test does not establish that all nine movable objects have been individually manipulated.

The sink rim intentionally overlaps the four stone strips around its cutout. The scene check
allows only those named overlaps; the basin remains open and both handle axes passed the
physical sweep. Four lighting switches preserve furniture positions and velocities, and
returning to day restores the initial visual state.

## Runtime and robot walking

Both runs used two concurrent 640 × 480 camera streams configured for 12 fps. Each measurement
window lasted approximately 30 seconds after warmup. The implementation under test was the
production NERV WorldSim, released G1 CPU policy and actual MJPEG route generators, connected
without a network listener.

| Run | Head camera | Chase camera | Simulation / wall time | Robot result |
|---|---:|---:|---:|---|
| Standing | 11.90 fps | 11.90 fps | 0.99998 | No fall or policy error |
| Walking | 11.83 fps | 11.83 fps | 0.99992 | Requested 1 m; measured 1.207 m in 2.65 s, no fall |

Both exceeded the acceptance targets of 10.8 fps and 0.95 simulation / wall time.
The complete scene contained 2,254 geometries and 596 meshes. G1 retained 29 actuators;
the Go2 scene retained 12. Passive furniture did not add robot actuators.

[Standing report](verification/runtime/standing.json) · [Walking report](verification/runtime/walking.json) ·
[Head image](verification/runtime/walking-head.png) · [Chase image](verification/runtime/walking-chase.png)

This is a short local runtime measurement, not an endurance test or a full browser-to-brain
acceptance run. The walking result confirms basic locomotion with passive furniture in the
model; it does not validate autonomous manipulation or all apartment routes.

## Images and lighting

The [interaction gallery](../images/apt2/interactions) renders measured door and drawer states
after force-controlled operations reach their targets. The refrigerator and oven interior
views expose their actual cavities. The kitchen appears in all four lighting presets.

At the fixed exterior-view camera, average luminance was 101.5 for day, 93.4 for morning,
86.6 for dusk and 31.6 for night. The night check inspected both floors from within every room,
with three to five usable floor views per room. It included surface finishes in the floor
mask and did not rely on a roof view of the duplex.

The saved G1 sofa pose was settled for three seconds: vertical change 0.046 m, horizontal
slide 0.030 m and final tilt 11.51 degrees. This demonstrates physical support for the saved
pose, not a policy that sits down. [Pose measurements](../images/apt2/seated-poses.json)

## Reproduction and limits

Use the commands in the [interaction guide](README.md#reproduction-and-checks). Add `--walk 1`
to the runtime benchmark for the walking regression. The GLFW integration harness runs from
the repository root and needs a desktop display; it invokes production key callbacks in a
hidden window, without capturing the user's keyboard or mouse.

The native inspector parks the robot while furniture physics runs. WASD moves the inspection
camera. NERV can simulate these passive objects, but it has no furniture-operation UI or
robot grasping, opening, sitting-down or stair-climbing skill. Water, heat, cooking and fan
operation are not simulated. Existing resident services were not restarted during these checks.

The protected baseline was `0c1fdcebdeb21134b368b170fbe7a12810e812a2`.
house2 models and images were unchanged by this interaction update. The reference checker
also retained its estate route, closed-boundary and non-supporting-water tests.
