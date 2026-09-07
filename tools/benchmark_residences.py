#!/usr/bin/env python3
"""Run actual NERV G1 policy, paced physics and both MJPEG generators without ports.

Run with NERV's Python environment through the host's GPU queue. No resident
service is contacted or restarted. Outputs are evidence, not scene source assets.
"""

from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "src"))
os.environ.setdefault("MUJOCO_GL", "egl")


class LocalBus:
    """Pass actual commands and observations directly to the production WorldSim."""

    def __init__(self, sim):
        self.sim = sim

    def spawn(self, spec):
        return self.sim.spawn(asdict(spec))

    def read(self):
        from nerv.nerve.world import BusState

        return BusState(**self.sim.read())

    def write(self, command):
        return self.sim.write(asdict(command))

    def reset(self):
        return self.sim.reset()

    def rays(self, angles_deg, max_range_m):
        return self.sim.rays(angles_deg, max_range_m)

    def sensors(self):
        return self.sim.sensor_names()

    def epoch(self):
        return self.sim.epoch

    def close(self):
        pass


async def measure(scene, seconds, out, pose=None):
    from PIL import Image
    from nerv import paths
    from nerv.platform.registry import Registry
    from nerv.world.mujoco_node import (
        SceneLayout,
        WorldSim,
        _body_defaults_from_registry,
        build_app,
    )
    from nerv.body.families.humanoid import HumanoidBody
    from nerv.body.skills import SkillRunner, StopFlag

    registry = Registry(roots=[paths.REPO_ROOT])
    world = registry.world(scene)
    spec = registry.body("humanoid-unitree-g1")
    spawn = dict(world.spawn or {})
    layout = SceneLayout(world.assets_root, spawn.get("scene") or world.name)
    if pose is not None:
        spawn = dict(source="explicit", x=pose[0], y=pose[1], yaw=pose[2])
    sim = WorldSim(
        os.path.join(world.assets_root, world.supports[spec.name]),
        physics=dict(world.physics or {}),
        world_name=world.name,
        body_name=spec.name,
        layout=layout,
        spawn=spawn,
        ambient=[s.model_dump() for s in world.ambient],
        body_defaults=_body_defaults_from_registry(spec),
    )
    body = None
    streams = []
    folder = out / scene
    folder.mkdir(parents=True, exist_ok=True)
    try:
        body = HumanoidBody(spec.model_dump(), LocalBus(sim), SkillRunner(StopFlag()))
        sim.start()
        # build_app constructs route objects only. No Uvicorn/BusServer/listener.
        app = build_app(sim, [])
        routes = {r.path: r.endpoint for r in app.routes}
        responses = [await routes["/stream/{camera}"]("head_front"), await routes["/stream"]()]
        streams = [r.body_iterator for r in responses]
        for label, stream in zip(("head", "chase"), streams):
            frame = await anext(stream)
            encoded = frame.split(b"\r\n\r\n", 1)[1][:-2]
            Image.open(io.BytesIO(encoded)).save(folder / (label + "-warmup.png"))
        await asyncio.sleep(3.0)
        with sim._lock:
            sim_start = float(sim.data.time)
        start = time.perf_counter()
        deadline = start + seconds

        async def consume(label, stream):
            stamps = []
            sizes = set()
            last = None
            while time.perf_counter() < deadline:
                try:
                    frame = await asyncio.wait_for(
                        anext(stream), max(0.01, deadline - time.perf_counter())
                    )
                except asyncio.TimeoutError:
                    break
                now = time.perf_counter()
                if now > deadline:
                    break
                encoded = frame.split(b"\r\n\r\n", 1)[1][:-2]
                picture = Image.open(io.BytesIO(encoded))
                sizes.add(picture.size)
                stamps.append(now - start)
                last = picture.copy()
            if last is not None:
                last.save(folder / (label + ".png"))
            return dict(
                frames=len(stamps),
                fps=len(stamps) / seconds,
                sizes=sorted(sizes),
                completion_times=stamps,
            )

        head, chase = await asyncio.gather(
            consume("head", streams[0]), consume("chase", streams[1])
        )
        elapsed = time.perf_counter() - start
        with sim._lock:
            sim_end = float(sim.data.time)
        report = dict(
            scene=scene,
            spawn=spawn,
            seconds=elapsed,
            head=head,
            chase=chase,
            realtime_factor=(sim_end - sim_start) / elapsed,
            body_status=body.status(),
            world_status=sim.status(),
            ngeom=sim.model.ngeom,
            nmesh=sim.model.nmesh,
            physics_alive=sim.physics_alive(),
            method="Production NERV WorldSim + released G1 CPU policy + actual MJPEG route generators; no network listener",
        )
        report["passed"] = (
            head["fps"] >= 0.90 * sim.phys["stream_fps"]
            and chase["fps"] >= 0.90 * sim.phys["stream_fps"]
            and report["realtime_factor"] >= 0.95
            and not body.status().get("policy_error")
            and body.status().get("state", {}).get("fallen") is False
            and sim.physics_alive()
        )
        (folder / "runtime.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ("head", "chase", "body_status", "world_status")
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        print("fps:", head["fps"], chase["fps"], "body:", body.status(), flush=True)
        return report["passed"]
    finally:
        for stream in streams:
            await stream.aclose()
        if body is not None:
            body.close()
        sim.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", nargs="+", default=["house2", "apt2"])
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pose",
        nargs=3,
        type=float,
        metavar=("X", "Y", "YAW"),
        help="Optional ground-floor camera test spawn, in scene metres and radians",
    )
    args = parser.parse_args()
    ok = True
    for scene in args.scene:
        ok = asyncio.run(measure(scene, args.seconds, args.output, args.pose)) and ok
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
