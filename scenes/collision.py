"""Physical rays include hidden hulls but exclude visual water and finishes."""

from __future__ import annotations
import copy
import threading
import weakref

_VIEWS = weakref.WeakKeyDictionary()
_LOCK = threading.Lock()


def collision_ray(model, data, origin, direction):
    """Ray-only model view; never mutate the model shared with rendering.

    Skipping past visual faces would step inside coincident physical surfaces.
    The copied model preserves every body/geom index for live MjData transforms.
    Rebuild if collision masks change, including during fault-injection checks.
    """
    import mujoco
    import numpy as np

    signature = (model.geom_contype.tobytes(), model.geom_conaffinity.tobytes())
    with _LOCK:
        cached = _VIEWS.get(model)
        if cached is None or cached[0] != signature:
            view = copy.copy(model)
            view.geom_group[:] = np.where(
                (model.geom_contype != 0) | (model.geom_conaffinity != 0), 0, 5
            )
            cached = (signature, view)
            _VIEWS[model] = cached
    vec = np.asarray(direction, dtype=float)
    vec = vec / np.linalg.norm(vec)
    gid = np.zeros(1, dtype=np.int32)
    distance = mujoco.mj_ray(
        cached[1],
        data,
        np.asarray(origin, dtype=float),
        vec,
        np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8),
        1,
        -1,
        gid,
    )
    return float(distance), int(gid[0])
