"""RoboCasa 厨房电器移植器 —— 把 MJCF 电器**拆成本仓 decor 管线认识的零件**。

来源：NVIDIA 在 HuggingFace 上的镜像 `nvidia/PhysicalAI-Robotics-Manipulation-Objects-Kitchen-MJCF`
（**CC-BY-4.0**，按类目分 zip，不用装 robosuite、不用认证）。

⭐ **为什么不直接 `<include>` 那份 MJCF**（五条，每一条都足以静默弄坏消费方）：

1. `<actuator><motor/></actuator>` —— 每件电器都带（灶具 8 个、抽油烟机 5 个、冰箱 3 个）。
   include 进来会改变 `nu` 和动作空间布局，**直接弄坏 `policies/*/contract.json` 和
   anima-zero 的 sim-house-nav**。
2. `<joint>` 到处都是（灶具 8 个）→ 改变 `nq`/`nv`，同上。
3. `<option timestep="0.002" gravity="..."/>` 在每份 XML 顶部，**会静默覆盖本模型的积分器设置**。
4. `<default class="visual"/"collision">` —— 类名和本仓重复，MuJoCo 直接拒绝编译。
5. ⛔ **每件电器的根 body 都叫 `object`** —— 搬两件就撞名。

✅ **本模块的做法**：只取**视觉网格 + 贴图**，把它们写成和 Poly Haven / Objaverse 资产
   完全一样的 `decor/assets/<key>/pN.obj + pN.png` 形式，并登记进 `decor.lock.json`。
   于是电器直接走 `F.mesh_piece(..., mesh="rc_stove")`，
   **包含性缩放、`decor/calibrate.py` 标定、射线不变性自检全部自动生效**——
   一行新的摆位代码都不用写，也不可能改变 `nu`/`nq`/`nv`（我们根本没引入任何 joint/actuator）。

⚠️ 代价说清楚：随之丢掉的是铰接（门/抽屉打不开）和灶具的 `<site>`。
   本轮的目标是"厨房看起来是真的"，不是"能开冰箱门"。要做操作任务时再单独接。

用法：
    python -m decor.robocasa --list           # 看有哪些电器
    python -m decor.robocasa                  # 按 FIXTURES 拓下来并转换
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from . import lock

REPO = "nvidia/PhysicalAI-Robotics-Manipulation-Objects-Kitchen-MJCF"
BASE = f"https://huggingface.co/datasets/{REPO}/resolve/main/fixtures_lightwheel"
LICENSE = "CC-BY-4.0"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".cache", "robocasa")

# 要移植哪几件。⚠️ 具体型号是**看着挑的**，换型号只改这里。
FIXTURES = {
    "rc_fridge": ("fridges", "Refrigerator031", "对开门冰箱"),
    "rc_stove": ("stoves", "Stove001", "四眼灶 + 烤箱"),
    "rc_sink": ("sinks", "Sink001", "水槽 + 龙头"),
    "rc_hood": ("hoods", "RangeHood002", "抽油烟机"),
}

_UA = {"User-Agent": "alice-house/0.8 (+https://github.com/Yanshi-Robotics/alice-house)"}


def _zip_path(cat: str) -> str:
    return os.path.join(CACHE, f"{cat}.zip")


def _download(cat: str) -> str:
    p = _zip_path(cat)
    if os.path.exists(p):
        return p
    os.makedirs(CACHE, exist_ok=True)
    url = f"{BASE}/{cat}.zip"
    print(f"  下载 {cat}.zip …")
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=600) as r, open(p + ".part", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(p + ".part", p)
    return p


def _body_chain(root: ET.Element):
    """(geom 元素, 它相对根 body 的累积平移) 的迭代器。

    ⚠️ 必须累积父 body 的 `pos`：门、抽屉、旋钮都住在各自的子 body 里，
       只读 geom 自己的 pos 会把整台电器摊平到一处。
    """
    def walk(el, acc):
        for ch in el:
            if ch.tag == "body":
                p = [float(v) for v in (ch.get("pos") or "0 0 0").split()]
                yield from walk(ch, [a + b for a, b in zip(acc, p)])
            elif ch.tag == "geom":
                p = [float(v) for v in (ch.get("pos") or "0 0 0").split()]
                yield ch, [a + b for a, b in zip(acc, p)]
            else:
                yield from walk(ch, acc)
    yield from walk(root, [0.0, 0.0, 0.0])


def _obj_bounds(data: bytes):
    """只读 OBJ 的 `v` 行算包围盒。⚠️ 纯 stdlib，不引 trimesh。"""
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for line in data.decode("utf-8", "replace").splitlines():
        if line.startswith("v "):
            xyz = [float(v) for v in line.split()[1:4]]
            for k in range(3):
                lo[k] = min(lo[k], xyz[k])
                hi[k] = max(hi[k], xyz[k])
    if lo[0] == float("inf"):
        return None
    return lo, hi


def transplant(key: str, cat: str, model: str, label: str) -> dict | None:
    """把一件电器拆成 decor 零件，返回它的 lock 条目。"""
    z = zipfile.ZipFile(_download(cat))
    prefix = f"{cat}/{model}/"
    xml_name = prefix + "model.xml"
    if xml_name not in z.namelist():
        print(f"  ⛔ {key}: 压缩包里没有 {xml_name}")
        return None
    root = ET.fromstring(z.read(xml_name))

    # 资产表：mesh 名 → 文件；material 名 → 贴图文件
    mesh_file = {m.get("name"): m.get("file") for m in root.iter("mesh") if m.get("file")}
    tex_file = {t.get("name"): t.get("file") for t in root.iter("texture") if t.get("file")}
    mat_tex = {m.get("name"): tex_file.get(m.get("texture"))
               for m in root.iter("material") if m.get("texture")}

    out_dir = os.path.join(lock.ASSET_DIR, key)
    os.makedirs(out_dir, exist_ok=True)
    parts, seen = [], set()
    wb = root.find("worldbody")
    for g, off in _body_chain(wb if wb is not None else root):
        mn = g.get("mesh")
        # ⛔ 只收视觉网格：RoboCasa 的 collision 组是一堆凸分解碎块，
        #    搬过来既难看又没用（我们的碰撞真相仍然是 layout 里的盒子）。
        if not mn or mn not in mesh_file or "_vis" not in mn:
            continue
        if mn in seen:
            continue
        seen.add(mn)
        src = prefix + mesh_file[mn]
        if src not in z.namelist():
            continue
        data = z.read(src)
        b = _obj_bounds(data)
        if b is None:
            continue
        lo, hi = b
        i = len(parts)
        with open(os.path.join(out_dir, f"p{i}.obj"), "wb") as f:
            f.write(data)
        png = None
        tf = mat_tex.get(g.get("material") or "")
        if tf and (prefix + tf) in z.namelist():
            png = f"p{i}.png"
            with open(os.path.join(out_dir, png), "wb") as f:
                f.write(z.read(prefix + tf))
        parts.append({
            "obj": f"p{i}.obj", "png": png,
            # offset/half 先按 OBJ 自己的包围盒 + 父 body 平移填；
            # ⚠️ 真值由 `python -m decor.calibrate` 从**编译后的顶点**重算覆盖。
            "offset": [(l + h) / 2.0 + o for l, h, o in zip(lo, hi, off)],
            "half": [(h - l) / 2.0 for l, h in zip(lo, hi)],
        })
    if not parts:
        print(f"  ⛔ {key}: 一张视觉网格都没取到")
        return None

    lo = [min(p["offset"][k] - p["half"][k] for p in parts) for k in range(3)]
    hi = [max(p["offset"][k] + p["half"][k] for p in parts) for k in range(3)]
    print(f"  ✅ {key}（{label}）：{len(parts)} 张网格，"
          f"包围盒 {' × '.join(f'{h - l:.2f}' for l, h in zip(lo, hi))} m")
    return {"source": "robocasa", "source_id": f"{cat}/{model}", "license": LICENSE,
            "label": label, "parts": parts, "size": [h - l for l, h in zip(lo, hi)]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="列出压缩包里有哪些型号")
    a = ap.parse_args(argv)

    if a.list:
        for cat in sorted({c for c, _, _ in FIXTURES.values()}):
            z = zipfile.ZipFile(_download(cat))
            names = sorted({n.split("/")[1] for n in z.namelist()
                            if n.count("/") >= 2 and n.startswith(cat + "/")})
            print(f"{cat}: {len(names)} 个 —— {', '.join(names)}")
        return 0

    data = lock.load()
    for key, (cat, model, label) in FIXTURES.items():
        e = transplant(key, cat, model, label)
        if e:
            data[key] = e
    with open(lock.LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"\n已写回 {os.path.basename(lock.LOCK_PATH)}。"
          f"⛔ 接着必须跑 `python -m decor.calibrate` 用编译后的真实顶点覆盖包围盒。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
