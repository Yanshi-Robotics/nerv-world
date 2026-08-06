"""glTF/GLB → MuJoCo 能吃的 OBJ + PNG。

⚠️ 这个模块要 `trimesh`，⛔ 生成器**不许** import 它（生成场景的依赖必须只有
   `mujoco numpy pillow`）。只有 `decor/fetch.py` 会用。

四个**实测**踩过的坑，每一个都会静默出错：

1. ⛔ **trimesh 不做 Y-up → Z-up。** 实测：Klassika 浴缸 `scene.extents = [1.60, 0.55, 0.80]`
   —— Y 才是高度，浴缸不可能宽 55 cm。glTF 规范是 Y-up，但 trimesh 的加载器不转。
   必须在 **scene 上、`dump()` 之前**转。不转的话家具就是躺着的，而且什么都不报错。
2. ⛔ **多物体 OBJ 会在 MuJoCo 里静默损坏。** 实测喂一个 3 物体 OBJ：
   `nmeshface` 从 93120 掉到 **2520**（只取了第一块），但 `nmeshtexcoord` 是三块之和 52684。
   **编译不报错，渲染出来是乱的。** → **一个 OBJ 只放一张网格**，按材质拆。
3. ⚠️ **`dump()` 之后必须重新居中。** 它保留资产作者摆的世界坐标，Objaverse 的位置是任意的
   （那张床原本在 x≈−4.4）。
4. ⛔ **减面会丢 UV。** `trimesh.simplify_quadric_decimation` 只是
   `fast-simplification` 的薄封装，而后者的核心 API 只返回 (点, 面)，顶点属性一律丢掉。
   必须走 `simplify(..., return_collapses=True)` + `replay_simplification()` 拿
   `indice_mapping` 自己重映射 UV。**这是最容易白花一下午的地方。**
"""
from __future__ import annotations

import io

import numpy as np


def _rot_x90() -> np.ndarray:
    import trimesh
    return trimesh.transformations.rotation_matrix(np.pi / 2.0, [1, 0, 0])


def load_scene(data: bytes, file_type: str):
    """载入 GLB/glTF 并转成 Z-up。返回 trimesh.Scene。"""
    import trimesh
    sc = trimesh.load(io.BytesIO(data), file_type=file_type, force="scene")
    sc.apply_transform(_rot_x90())          # ⛔ 坑 1：Y-up → Z-up，必须在 dump 之前
    return sc


def scale_to(sc, axis: str, metres: float) -> None:
    """按"这东西现实里多大"归一化尺度。Objaverse 的单位五花八门（常见是厘米）。"""
    ext = sc.extents
    i = {"x": 0, "y": 1, "z": 2}[axis]
    if ext[i] <= 0:
        return
    k = metres / float(ext[i])
    sc.apply_scale(k)


def decimate(mesh, max_tris: int):
    """减面并**保住 UV**（坑 4）。面数已经够少就原样返回。"""
    import fast_simplification as fs
    n = len(mesh.faces)
    if n <= max_tris:
        return mesh
    uv = getattr(mesh.visual, "uv", None)
    reduction = 1.0 - max_tris / n
    # ⚠️ fast-simplification 的 C 扩展要 **float32 顶点 + int32 面**，而 trimesh 给的是
    #    float64 + int64。直接喂会报 `Buffer dtype mismatch, expected 'float' but got 'double'`
    #    ——这个报错完全看不出是"类型没转"，而且只有真正触发减面的资产才会撞上，
    #    面数本来就少的那些一路绿灯，很容易误判成"管线是通的"。
    verts = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int32)
    if uv is None:
        pts, fcs = fs.simplify(verts, faces, reduction)
        mesh.vertices, mesh.faces = pts, fcs
        return mesh
    # ⛔ 有 UV 就必须走 collapse-replay，否则贴图坐标全废（而且不报错）
    _p, _f, collapses = fs.simplify(verts, faces, reduction, return_collapses=True)
    pts, fcs, indice_mapping = fs.replay_simplification(verts, faces, collapses)
    import trimesh
    out = trimesh.Trimesh(vertices=pts, faces=fcs, process=False)
    out.visual = trimesh.visual.TextureVisuals(
        uv=np.asarray(uv)[indice_mapping], material=mesh.visual.material)
    return out


def parts(sc, max_tris: int) -> tuple[list[tuple[object, bytes | None]], tuple[float, float, float]]:
    """把 scene 拆成 [(网格, 贴图PNG字节或None), ...] + 整件的包围盒尺寸。

    ⭐ glTF 的 primitive 本来就是按材质分的，`sc.geometry` 直接就是我们要的分组，
       不用自己按材质切。

    ⛔ **所有部件必须按同一个偏移居中**（坑 3 的正确版本）。
       第一版给每个部件各自 `apply_translation(-自己的中心)`——多材质的资产会**散架**：
       扶手椅的坐垫和框架各自被挪到原点、叠在一起。
       而且它当时还让 lock 里记的尺寸（取自 `sc.extents`）和导出的 OBJ 对不上，
       结果是碗在场景里**立起来了**（实际包围盒 0.12×0.33×0.34，记的却是 0.31×0.31×0.09）。
       ⚠️ 这个错**编译不报错、自检也未必抓得到**，只有摆进场景一看才发现。
       返回值多带一份"整件的包围盒"，就是为了让 lock 记的和产物真正一致。
    """
    meshes = sc.dump()                       # dump() 会把节点变换烘进去
    lo = np.min([m.bounds[0] for m in meshes], axis=0)
    hi = np.max([m.bounds[1] for m in meshes], axis=0)
    centre = (lo + hi) / 2.0
    out = []
    for m in meshes:
        m.apply_translation(-centre)         # ⭐ 同一个偏移，相对位置保住
        m = decimate(m, max_tris)
        # ⚠️ 还要记下这个部件**自己的中心相对整件中心的偏移**。
        #    因为 MuJoCo 编译时会把每张 mesh 按自身重心重新定位——
        #    如果发射时把所有部件都放在同一个 pos，多部件资产的相对位置就丢了
        #    （条案的两条腿会跑到柜体中心）。这个偏移让生成器能把它们摆回去。
        off = tuple(float(v) for v in m.bounds.mean(axis=0))
        half = tuple(float(v) for v in (m.bounds[1] - m.bounds[0]) / 2.0)
        png = None
        mat = getattr(m.visual, "material", None)
        img = getattr(mat, "baseColorTexture", None)    # ⚠️ PBRMaterial 没有 .image
        if img is not None:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            png = buf.getvalue()
        out.append((m, png, off, half))
    return out, tuple(float(v) for v in (hi - lo))


def export_obj(mesh) -> bytes:
    """导出单张网格的 OBJ（带 vt）。⛔ 一个文件一张网格，见坑 2。"""
    from trimesh.exchange.obj import export_obj as _eo
    txt = _eo(mesh, include_texture=False, write_texture=False)
    return txt.encode("utf-8")


def footprint(mesh) -> tuple[float, float, float]:
    """归一化后的包围盒尺寸（x, y, z 全长）—— 生成器靠它算包含性缩放。"""
    lo, hi = mesh.bounds
    return tuple(float(v) for v in (hi - lo))
