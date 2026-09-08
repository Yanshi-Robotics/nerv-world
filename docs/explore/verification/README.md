# CPU validation record

Validation date: 2026-09-08 UTC. Environment: MuJoCo 3.12, Python 3.12,
NumPy 2.5.2 and trimesh 5.1.0. These checks use local models and CPU physics.
They do not establish browser frame rate, native rendered appearance, live NERV
performance or an autonomous robot manipulation skill.

## Recorded results

| Check | Result | Evidence |
|---|---|---|
| Scene structure | All 58 apt/house checks passed | `python tools/check_scene.py` |
| Inherited city, estate boundaries, pool and fixtures | Passed; 1787 house route samples, 1800 boundary samples and 336 pool-bottom samples | [residences.json](residences.json) |
| Runtime and task | Both scenes with G1 and Go2; reversible four-phase lighting; actual refrigerator placement; invalid placements and a brief hold between display updates rejected | [operator.json](operator.json) |
| Appliance cycles | 44 endpoint targets and 22 cancellations per robot, with every physics step observed | [G1](interactions-g1.json), [Go2](interactions-go2.json) |
| Extended interaction | 51 physical trajectories and 72 rejected invalid inputs; 620510 observed physics steps | [interaction-cases.json](interaction-cases.json) |
| Chair boundaries | Six table-leg approaches and six table-edge releases; all cancel and release checks passed | [chair-boundaries.json](chair-boundaries.json) |
| Explore | Fresh source fingerprints, self-contained GLB, geometry and material checks, facility references and flat routes | [explore.json](explore.json) |

The extended traces include centre and eccentric grabs followed by release for all nine
movable objects; table-leg contact and releases inside and beyond the table edge for the
can, fruit and book; four drawer attempts and one oven-rack attempt with the enclosing door
closed; and a carried can obstructing the refrigerator door. Their largest measured contact
penetration is 0.008464 m, below the 0.01 m limit. The largest linear speed is 3.9633 m/s.
Rotational speed is recorded separately from linear speed; free-body limits use actual mass
and inertia with the test's declared release-height envelope.

Closed-door attempts have two observed outcomes. The freezer drawers stop short and report
`blocked`; the refrigerator drawers and oven rack make real contact and push their unlocked
doors open. The carried-can barrier reports `blocked`, and cancelling it removes the
controller's force without changing position, velocity or simulation time.

The six chairs were also tested for approaching table legs and releasing at the table edge.
The four end chairs made actual table-leg contact. Both middle chairs met neighbouring
chairs before reaching a table leg, so their results are `other_boundary_obstructed`.
All six edge-release trajectories contacted the actual tabletop. Every trace continued
through cancellation and three seconds of free physics, ending in actual contact.

The original six overlong chair drags remain as negative cases. Each attempts the original
outward target and then the table-leg target, reports `blocked`, clears its force and
preserves the measured physical state when cancelled. Normal carry targets advance at up
to 0.5 m/s; excessive following lag ends a grab rather than accumulating force against an
obstacle. The existing native convex collision settings and 0.002 s timestep are retained.

A chair may rotate or topple after a single-point grab. The scene's saved robot pose is
parked during these inspection fixtures. These results do not establish a walking robot's
balance during furniture operation; the consuming NERV application validates that separately.

## Flat routes and export

Apt has three connected routes for the entrance/gallery, living/dining access and kitchen.
They have 153 samples in total with a 0.30 m body-radius check. The dining route stops just
inside its doorway to preserve standing and turning clearance from the chairs. The kitchen route remains
on the lowest floor under the eastern stair landing, where minimum headroom is 1.775 m.
House has six routes, including the complete pool circuit and rear-garden branch. Route
checks inspect the generated starting state; moving furniture can alter clearance.

The exported apt model contains 338 meshes and 450150 triangles, occupying 49308988 bytes.
House contains 493 meshes and 1060776 triangles, occupying 87310004 bytes. Both retain the
full selected visual geometry and contain embedded textures. Browser rendering and GPU
acceptance must be measured by the consuming application using these source fingerprints.
