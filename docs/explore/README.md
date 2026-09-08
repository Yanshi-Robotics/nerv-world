# World Explore export

Explore presents the residential geometry, floors, rooms and facilities for inspection in a
browser. The exported model is a static view of the generated starting state. It does not run
physics or execute furniture actions; live operation belongs to the consuming NERV interface.

## Export and verification

Prepare the scene's furniture assets using the [interaction asset setup](../interactions/README.md#asset-setup),
then run these commands from the world repository:

```bash
pip install -r requirements-explore.txt
python tools/export_explore.py --scene apt
python tools/export_explore.py --scene house
python tools/check_explore.py
```

Each export writes `scene.glb` and `manifest.json` into `.cache/explore/<scene>/`. The scene's
`world.yaml` declares that manifest path relative to `assets_root`. These cache files include
third-party mesh derivatives and remain untracked. They are regenerated locally; the original
furniture, textures and asset locks remain the source assets.

The manifest records a SHA-256 fingerprint of scene code, generated MJCF, recursive XML
includes, asset locks and referenced geometry and textures. It also records each output's
hash and byte length. Consumers can reject stale or missing exports instead of presenting a
model that no longer matches the scene. Rerun the exporter after changing source files or assets.

## Coordinates and geometry

Catalogue coordinates are in metres with Z pointing upward, matching MuJoCo. The GLB has a
single root rotation of −90 degrees about X to use glTF's Y-up convention. The manifest contains
that transform in column-major order. Floor and room bounds, facility anchors and route points
remain in the catalogue coordinate system.

The exporter reads compiled visual meshes, primitive shapes, normals, UV coordinates, colours
and textures. It excludes the robot and hidden collision-only geometry. Shapes are batched by
material, floor membership, room, display role and facility to reduce browser draw calls. Each
node retains `levels`, `room`, `role`, `facility`, `facilities` and original `geoms` in its extras.
`facilities` can contain multiple controls that share one physical part, such as the two sink
handle axes. Furniture roles remain intact when a browser cuts away upper walls.

Phong appearance is approximated with glTF metallic-roughness materials. Browser illumination
and transparency differ from the native MuJoCo camera. Texture size defaults to 1024 pixels
per image and is configurable with `--texture-pixels`; source image files are untouched.

## Runtime integration

Load `SceneRuntime` with `scenes.manifest.load_operator()`, then instantiate it with the
consumer's model, data and scene key. Call `interaction.update()` before physics, `observe_step()`
after every physics step, and `update_task()` at the desired display rate. Read `catalogue()`
and `task_status()` under the same synchronization used for model access. `set_time(phase,
renderer)` changes native lighting and uploads textures to that renderer. Consumers with
multiple renderers must update the texture data in each rendering context.

The catalogue provides English and Chinese labels, facility operations and specific inspection
instructions. Its stair checkpoints require stopping on level ground; they do not certify G1
stair climbing. House routes include the gate approach, lawn access, complete pool circuit,
west and east paths, and rear garden. The pool's water surface is visual and does not support
weight. The pool circuit shares its first two points with the pool approach,
keeping the front corner farther from the pergola posts. The gate is a fixed closed boundary.
Apt provides entrance/gallery, living/dining and kitchen routes. Kitchen access stays on the
lowest floor beneath the eastern stair landing;
the verified minimum headroom is 1.775 m. Furniture movement can change route clearance.

The CPU checker verifies source freshness, embedded assets, finite geometry and normals, UV
attributes, complete visual coverage, coordinate transforms and display classification.
Browser frame rate, visual quality and native camera behaviour require separate runtime checks.
