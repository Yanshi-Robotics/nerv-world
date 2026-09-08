"""Scene-owned operator runtime. The consumer owns locking, stepping and leases."""

import mujoco
from scenes import manifest
from scenes.interaction import Interaction
from scenes.time_cycle import TimeCycle
from scenes.catalogue import Catalogue
from scenes.tasks import FridgeTask


class SceneRuntime:
    def __init__(self, model, data, scene_key):
        self.model, self.data, self.scene_key = model, data, scene_key
        self.interaction = Interaction(model, data)
        self._catalogue = Catalogue(model, data, scene_key, self.interaction)
        self._cycle = (
            TimeCycle(model, scene_key)
            if hasattr(manifest.load_layout(scene_key), "LIGHTS_BY_TIME")
            else None
        )
        config = getattr(self._catalogue.layout, "FRIDGE_TASK", None)
        self._task = (
            FridgeTask(model, data, self.interaction, self._catalogue.geometry, config)
            if config
            else None
        )

    @property
    def phases(self):
        return self._cycle.phases if self._cycle else ("day",)

    @property
    def phase(self):
        return self._cycle.phase if self._cycle else "day"

    def catalogue(self):
        result = self._catalogue.get()
        if self._task:
            target = self._task.target()
            result["facilities"].append(
                dict(
                    id="fridge_task_target",
                    label=target["label"],
                    room="kitchen",
                    floor=0,
                    kind="static",
                    operations=[],
                    anchor=target["world_anchor"],
                    bounds=target["world_bounds"],
                    description={
                        "en": "Task target above the middle shelf in the refrigerator's right compartment.",
                        "zh": "右侧冷藏室中层搁板上方的任务区域。",
                    },
                    test={
                        "en": "Place the entire can here, release it onto this shelf, wait for stable support, then close the door.",
                        "zh": "将罐体完整放入此处，释放到该搁板，待其稳定承托后关闭冷藏室门。",
                    },
                )
            )
        return result

    def set_time(self, phase, renderer=None):
        if phase not in self.phases:
            raise ValueError(f"Unknown time preset: {phase}")
        if self._cycle:
            self._cycle.renderer = renderer
            warnings = self._cycle.set(phase)
            # Renderer reads derived world light positions from mjData. Refresh
            # them even when physics is paused, without advancing its state.
            mujoco.mj_camlight(self.model, self.data)
            return warnings
        return []

    def update_task(self):
        return self._task.update() if self._task else self.task_status()

    def observe_step(self):
        """Update continuity after every mj_step without allocating display state."""
        if self._task:
            self._task.update(publish=False)

    def task_status(self):
        return (
            dict(self._task.state)
            if self._task
            else {"supported": False, "stage": "unavailable", "success": False}
        )

    def reset(self):
        self.interaction.cancel()
        self.interaction.results.clear()
        if self._task:
            self._task.reset()
