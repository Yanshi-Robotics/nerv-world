"""Reversible runtime light/texture presets, without resetting physics state."""

import mujoco
from scenes.apply_time_preset import apply
from scenes import manifest

MODEL_FIELDS = (
    "light_active", "light_pos", "light_dir", "light_diffuse", "light_specular",
    "light_ambient", "light_castshadow", "light_attenuation", "light_cutoff",
    "mat_rgba", "mat_emission", "mat_specular", "mat_shininess", "mat_reflectance",
    "geom_rgba", "geom_matid", "tex_data",
)
HEADLIGHT_FIELDS = ("diffuse", "ambient", "specular")


class TimeCycle:
    def __init__(self, model, scene_key, renderer=None):
        self.model, self.scene_key, self.renderer = model, scene_key, renderer
        self.base = {k: getattr(model, k).copy() for k in MODEL_FIELDS}
        self.headlight = {k:getattr(model.vis.headlight,k).copy() for k in HEADLIGHT_FIELDS}
        self.phase = "day"
        self.phases = tuple(manifest.load_layout(scene_key).LIGHTS_BY_TIME)

    def set(self, phase):
        if phase not in self.phases:
            raise ValueError(f'Unknown time preset: {phase}')
        # Restoring the baseline also lets the skybox matcher start from day on
        # every switch. No qpos/qvel fields are touched, even with open drawers.
        for k, value in self.base.items():
            getattr(self.model, k)[:] = value
        for k, value in self.headlight.items():
            getattr(self.model.vis.headlight, k)[:] = value
        if self.renderer:
            self.renderer._gl_context.make_current()
            for texture in range(self.model.ntex):
                mujoco.mjr_uploadTexture(self.model, self.renderer._mjr_context, texture)
        warnings = apply(self.model, self.renderer, phase, scene_key=self.scene_key)
        self.phase = phase
        return warnings
