"""读 decor.lock.json —— ⛔ **只用 stdlib**，`make_house.py` 会 import 它。

生成场景的依赖必须守在 `mujoco numpy pillow`；下载和转换那一套（trimesh / urllib /
fast-simplification）只住在 `decor/fetch.py` 与 `decor/convert.py`。

lock 里存的是**期望清单**：每件资产有哪些部件、各自的 sha256、归一化之后的包围盒尺寸。
⭐ 包围盒是关键——生成器靠它算"包含性缩放"，而且**不需要资产字节也不需要 mujoco**
就能算，所以裸 clone 上照样能跑那条自检。
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK_PATH = os.path.join(HERE, "decor.lock.json")
ASSET_DIR = os.path.join(HERE, "assets")

_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = json.load(open(LOCK_PATH, encoding="utf-8")) if os.path.exists(LOCK_PATH) else {}
    return _cache


def has(key: str) -> bool:
    return key in load()


def parts(key: str) -> list[dict]:
    """[{obj, tris, sha256, png?}, ...]"""
    return load().get(key, {}).get("parts", [])


def size(key: str) -> tuple[float, float, float]:
    """归一化之后的包围盒全长 (x, y, z)。"""
    s = load().get(key, {}).get("size") or [1.0, 1.0, 1.0]
    return (float(s[0]), float(s[1]), float(s[2]))


def bytes_present(key: str) -> bool:
    """字节在不在磁盘上。⛔ 字节是 gitignore 的，裸 clone 上必然不在。"""
    ps = parts(key)
    if not ps:
        return False
    return all(os.path.exists(os.path.join(ASSET_DIR, key, p["obj"])) for p in ps)


def rel_path(key: str, filename: str) -> str:
    """相对仓根的路径，例如 decor/assets/vase_a/p0.obj。"""
    return os.path.join("decor", "assets", key, filename).replace(os.sep, "/")


def part_offset(key: str, i: int) -> tuple[float, float, float]:
    """第 i 个部件的中心相对整件中心的偏移（归一化坐标系，未缩放）。

    ⚠️ 必须用它：MuJoCo 编译时把每张 mesh 按自身重心重新定位，
       所有部件塞在同一个 pos 上会让多部件资产散架。
    """
    p = parts(key)[i]
    # ⭐ 优先用 `com`（`decor/calibrate.py` 从 MuJoCo 的 `mesh_pos` 实测出来的重心）。
    #    ⛔ 不能用 `offset`（包围盒中心）：MuJoCo 编译时按**重心**把顶点平移到原点，
    #       两者在非闭合网格上能差几十厘米甚至几米（实测最大 312 cm），
    #       用错的话多部件资产就系统性地探出碰撞盒。
    o = p.get("com") or p.get("offset") or [0.0, 0.0, 0.0]
    return (float(o[0]), float(o[1]), float(o[2]))
