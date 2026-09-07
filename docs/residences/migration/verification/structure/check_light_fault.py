"""2026-09-07 regression: re-enable the included studio light and reject 9 GL slots.
Run from the nerv-world root. Uses a real compiled model; no graphics context needed.
"""
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, '.')
import mujoco
from scenes import manifest
from tools import check_scene

model = mujoco.MjModel.from_xml_path(manifest.scene_filename('apt', 'g1'))
layout = manifest.load_layout('apt')
assert check_scene.check_lights_render('apt', layout) == []
robot_lamp = next(i for i in range(model.nlight) if model.light(i).name == '')
model.light_active[robot_lamp] = True
with patch.object(mujoco, 'MjModel', SimpleNamespace(from_xml_path=lambda _: model)):
    with patch.object(check_scene, '_modelled_robots', return_value=['g1']):
        failures = check_scene.check_lights_render('apt', layout)
assert len(failures) == len(layout.LIGHTS_BY_TIME), failures
assert all('8' in error for error in failures), failures
print(json.dumps(dict(passed=True, injected_failures=failures), ensure_ascii=False, indent=2))
