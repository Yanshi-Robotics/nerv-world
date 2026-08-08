"""alice-house 里有哪些**场景** —— 换地方要知道的全部事实，收在这一处。

和 `robots/manifest.py` 是一对：那边是"有哪些身体"，这边是"有哪些地方"。
同一台机器人可以放进任何一个场景，所以两者正交，各自登记、交叉组合生成。

**这里只放"这个场景是什么"**（叫什么、layout 模块在哪、有几层、给谁看的），
不放房间矩形/家具/出生点——那些是场景自己 `layout.py` 的事。

⭐ 2026-08-02 重新引入多场景目录。CHANGELOG [0.4] 曾主动把 `domus01/` 拍平到仓根，
当时的判断是"一个世界里有多个地方"而不是"多套户型并列"；Jeff 2026-08-02 拍板改回
CARLA 式的多场景（house1 / house2 / …），本文件是那次决定的落地。
⛔ 别再拍平：拍平就等于假设永远只有一个地方。

加一个新场景：往 `SCENES` 里**追加**一条（⛔ 追加不替换），建 `scenes/<key>/layout.py`，
再跑 `python make_house.py --scene <key>`。
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # alice-house 仓根


SCENES: dict[str, dict] = {
    "house2": {
        "label": "三层小楼（带两组可通行楼梯）",
        "layout": "scenes/house2/layout.py",
        "floors": 3,
        "note": "为人形的爬楼与跨层导航建的。楼梯踏面按 G1 脚长留了真余量，层高从楼梯反推。",
    },
    "house1": {
        "label": "单层大平层（12 空间，约 364 ㎡）",
        "layout": "scenes/house1/layout.py",
        "floors": 1,
        "note": "首个场景。无高差、无楼梯，适合导航与房间识别。",
    },
    "house3": {
        "label": "曼哈顿高层豪宅大平层（13 空间，约 345 ㎡，62 层）",
        "layout": "scenes/house3/layout.py",
        "floors": 1,
        "note": "北面整墙落地窗俯瞰中央公园。考的是视觉信息极强、且窗外是 232 米空气的环境；"
                "落地窗有可碰撞玻璃，不然机器人会直接走出去。",
    },
}

DEFAULT_SCENE = "house1"

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


def scene_filename(scene_key: str, robot_key: str) -> str:
    """(场景, 机器人) 对应的产物文件名。

    ⚠️ 消费方（anima-zero 的世界服务）按同样的规则去找，两边别各写各的——
    改名要两边一起改。
    """
    return f"{scene_key}-{robot_key}.xml"
