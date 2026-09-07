"""2026-09-07: real renderer error checks for canonical residence light/texture bindings.
Run from the nerv-world root with MUJOCO_GL=egl on the host GPU queue.
"""
import json
import sys

sys.path.insert(0, '.')
import mujoco
from scenes import manifest
from scenes.time_cycle import TimeCycle

results = {}
for key in manifest.keys():
    model = mujoco.MjModel.from_xml_path(manifest.scene_filename(key, 'g1'))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    with mujoco.Renderer(model, 480, 640) as renderer:
        assert mujoco.mjr_getError() == 0, key
        cycle = TimeCycle(model, key, renderer) if hasattr(manifest.load_layout(key), 'LIGHTS_BY_TIME') else None
        results[key] = {}
        for phase in cycle.phases if cycle else ('day',):
            if cycle:
                assert not cycle.set(phase)
            renderer.update_scene(data)
            renderer.render()
            error = mujoco.mjr_getError()
            results[key][phase] = error
            assert error == 0, (key, phase, error)
print(json.dumps(dict(passed=True, gl_errors=results), indent=2))
