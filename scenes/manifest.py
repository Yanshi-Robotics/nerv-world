"""Canonical residence catalogue: apt and house.

Scene registration and generated file paths are separate from robot registration.
Room geometry belongs to each scene's layout.py. Retired numbered variants are
recoverable from Git history and are deliberately absent from this catalogue.
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # nerv-world 仓根


SCENES: dict[str, dict] = {
    "apt": {
        "label": "曼哈顿复式公寓（24 空间、四时段、可交互家具）",
        "layout": "scenes/apt/layout.py",
        "floors": 2,
        "note": "62—63 层复式，中央公园窗景、双高客厅、双跑楼梯与真实家具碰撞；支持检查器家具交互。",
    },
    "house": {
        "label": "加州山坡豪宅（三层住宅、草坪与泳池）",
        "layout": "scenes/house/layout.py",
        "floors": 3,
        "note": "带封闭宅地的三层豪宅。住宅、庭院和外大门间有连续通路；泳池下沉，山坡社区仅作远景。",
    },
}

DEFAULT_SCENE = "apt"

_cache: dict[str, object] = {}


def get(key: str) -> dict:
    """场景登记项；不认识的 key 直接报错，不猜、不退回默认。"""
    if key not in SCENES:
        raise KeyError(f"未知场景 {key!r}。已登记：{', '.join(sorted(SCENES))}")
    return SCENES[key]


def keys() -> list[str]:
    return sorted(SCENES)


def load_layout(key: str):
    """按 key 加载该场景的 layout 模块（加载一次即缓存）。

    ⚠️ 加载期间把**仓根**塞进 sys.path：各场景的 layout 都
    `from scenes import furniture as F`（家具零件库住 `scenes/furniture.py`，所有场景共用），
    `shots.py` 还会 `from scenes import manifest` —— 两者都要求仓根在 sys.path 上。
    外部消费方（anima-zero 的世界服务）是从别处按路径加载的，不补就找不到；
    补上之后消费方不必知道资产库的内部布局。

    ⛔ 注入的是**仓根**，不是 `scenes/` 目录。注入 `scenes/` 会让本模块同时能以
    `scenes.manifest` 和 `manifest` 两个名字各被 import 一遍，`SCENES` 与 `_cache`
    当场分家——而 `_cache` 是有状态的，双份缓存是最难查的那类 bug。
    """
    if key in _cache:
        return _cache[key]
    path = os.path.join(ROOT, get(key)["layout"])
    if not os.path.exists(path):
        raise FileNotFoundError(f"场景 {key!r} 的 layout 不在 {path}")
    spec = importlib.util.spec_from_file_location(f"alice_house_layout_{key}", path)
    mod = importlib.util.module_from_spec(spec)
    injected = ROOT not in sys.path
    if injected:
        sys.path.insert(0, ROOT)
    try:
        spec.loader.exec_module(mod)
    finally:
        if injected:
            sys.path.remove(ROOT)
    _cache[key] = mod
    return mod


def load_sibling(key: str, module: str):
    """加载某个场景目录下的另一个模块（如 `shots`）。

    与 layout 同样处理：临时把**仓根**塞进 sys.path，因为场景模块会
    `from scenes import ...` 拿共用库（`scenes/furniture.py`、本模块）。
    ⛔ 同样不能改成注入 `scenes/`，理由见 `load_layout` 的 docstring。
    """
    path = os.path.join(ROOT, os.path.dirname(get(key)["layout"]), f"{module}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"场景 {key!r} 没有 {module}.py（应在 {path}）")
    spec = importlib.util.spec_from_file_location(f"alice_house_{key}_{module}", path)
    mod = importlib.util.module_from_spec(spec)
    injected = ROOT not in sys.path
    if injected:
        sys.path.insert(0, ROOT)
    try:
        spec.loader.exec_module(mod)
    finally:
        if injected:
            sys.path.remove(ROOT)
    return mod


# ⭐ 产物住哪一层 —— 全仓唯一真相源（`make_house.py` 读它来算 `../` 前缀）。
# ⛔ 改它会同时改变：产物落点、产物里 `<include>` 与 `<texture file>` 的 `../` 层数、
#    以及 `robots/*/[key].xml` 里 `meshdir` 的 `../` 层数（那三处必须同时对上，
#    因为它们共用同一个基准：**主模型 XML 所在目录**）。改之前先读 `make_house._root_rel`。
OUT_SUBDIR = "build"


def load_operator():
    """Load the world-owned runtime without requiring a consumer package import."""
    path=os.path.join(ROOT,"scenes","operator.py")
    spec=importlib.util.spec_from_file_location("nerv_world_operator",path)
    module=importlib.util.module_from_spec(spec)
    injected=ROOT not in sys.path
    if injected:sys.path.insert(0,ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        if injected:sys.path.remove(ROOT)
    return module


def scene_filename(scene_key: str, robot_key: str) -> str:
    """(场景, 机器人) 对应的产物 —— **相对仓根**的路径，含 `build/` 目录。

    ⭐ 唯一正确的用法是 `os.path.join(<资产库仓根>, scene_filename(...))`。
       仓内 15 处调用点与仓外消费方（anima-zero 的世界服务）都是这么写的，所以
       v0.10 把产物挪进 `build/` 时，**消费方一个字都不用改**。

    ⛔ 名字里的 "filename" 是历史包袱：v0.10 起返回的是 `build/apt-g1.xml` 这种
       **带目录**的相对路径，不是裸文件名。⛔ **别改名** —— 消费方按这个名字调它，
       改名就是一次跨仓破坏；名字得给兼容性让路。
    ⛔ **别在这里开第二个函数**（`scene_basename()` 之类）：两个函数就会有两份规则，
       而这里是产物名规则的**唯一真相源**。要裸文件名就自己 `os.path.basename()`。
    ⚠️ 固定用正斜杠（返回值会被拼进错误信息和文档）；Windows 上
       `os.path.join(root, "build/x.xml")` 照样打得开。
    """
    get(scene_key)  # Retired or unknown scene keys must not produce misleading paths.
    return f"{OUT_SUBDIR}/{scene_key}-{robot_key}.xml"
