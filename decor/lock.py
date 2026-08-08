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


# ⛔ 这里曾有一个 `part_offset(key, i)`，2026-08-07 删除。
#    它返回每个部件的重心，生成器拿去当摆位偏移——那是**第二次**施加 MuJoCo 自己
#    已经补偿掉的量（编译器把 mesh_pos/mesh_quat 抄进了 geom_pos/geom_quat）。
#    多部件资产的部件因此各自往外飞自己的重心那么远。
#    ✅ 正解：所有部件共用同一个偏移 `-_asset_span()[1]`，见 `make_house._decor_geoms`。
#    ⚠️ 别照着"多部件资产会散架"这个旧理由把它加回来——散架的真因是那时 offset 也是错的。
