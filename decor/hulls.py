"""给指定资产生成**真碰撞体**：把视觉网格做凸分解（CoACD），结果写进 lock。

⭐ 这一步解决的是「家具的碰撞和它长的样子对不上」——本仓最久的一个缺口。

## 为什么不能直接把视觉网格的碰撞打开

直觉上，家具已经有真网格了，把 `contype` 打开不就有真碰撞了吗？**不行**，原因很具体：

`decor/convert.py` 是**按材质**拆部件的（glTF 的 primitive 本来就按材质分组）。
所以 `p0.obj / p1.obj / …` 是**贴图分组，不是几何分组**。
而 MuJoCo 对每张碰撞网格只取它的**凸包**。两件事一叠加，结果是凸包把空腔整个吞掉。

实测各部件的凸度（体素填充实体积 ÷ 凸包体积，2026-08-22）：

    dining_chair  p0  0.30      ← 整把椅子就一个部件，凸包 = 一坨实心块
    armchair      p0  0.12      ← 骨架，吞掉 88%
    coffee_table  p0  0.22      ← 桌面 + 桌腿的凸包 = 一个实心圆柱
    bed           p8  0.07

⇒ 直接开碰撞，只是把「一个实心盒」换成「一个实心凸包」。椅腿之间、椅面下方照样是实的。

## CoACD 做了什么（实测，餐椅）

    阈值 0.05 → 32 块 / 10.3 s / 保真度 1.13
    阈值 0.10 → 15 块 /  8.1 s / 保真度 0.96      ← 甜点，本模块默认
    阈值 0.20 →  8 块 /  5.8 s / 保真度 0.76
    （不分解）→  1 块          / 保真度 0.30

俯视高度图从「整个占地一律 97 cm 的实心砖」变成「座面 44–47 cm + 靠背 85–98 cm」，
座面下方 26 cm 横打一条射线也真的穿得过去了（原来会撞在 0.383 m 处）。

## ⛔⛔ 一个不写就静默出错的地方：`solref`

MuJoCo 的**默认接触太软**。实测：一块 3.9 kg 的板从 1.20 m 砸到座面上（着面 3.7 m/s），
会**直接穿过 49 mm 厚的座面凸块**掉到地上。阈值很陡——每步位移 3.2 mm 还好、4.1 mm 就穿。

⚠️ 减小时间步**没用**（dt 降到 0.0005 照样穿），加 `margin` 也**没用**。
✅ 有效的只有一条：碰撞 geom 上写 `solref="0.005 1"`。

⛔ 所以 `make_house` 发射这些凸块时**必须**带上 `solref`，且有一道门禁盯着
（`check_scene.check_collision_solref`）。不写它的后果是：慢慢坐下去一切正常、
摔一跤砸上去就穿模，而且**编译不报错、慢速测试全绿**。

⚠️ 这不是「几何太薄」——实测凸块最薄边 30 mm、座面那块 49 mm。是接触刚度的问题。

## ⛔ 不是所有家具都上

判据照业界做法（RoboCasa / Habitat / Isaac 都如此）：**只让任务真正涉及的物体**有精确碰撞。
墙边的柜子、床、植物维持原来的隐身盒就好——机器人不跟它们发生精细交互，
而每多一件都要多花 qhull 与接触检测。清单就是下面的 `COLLIDE`，**它是一份有意的取舍，
不是资产的属性**，所以住在这里而不是 `decor/manifest.py`。

## 用法

⛔ 这一步的依赖**不在生成器那三个**（`mujoco numpy pillow`）里，要额外装两个：

    pip install coacd trimesh          # coacd 是 MIT，只依赖 numpy

    python -m decor.hulls              # 缺谁补谁
    python -m decor.hulls --force      # 全部重做
    python -m decor.hulls --only dining_chair

产物落在 `decor/assets/<key>/hulls/hN.obj`，**和网格字节一样不入库**
（`decor/assets/` 整个在 .gitignore 里）。lock 里只记块数、阈值和每块的 sha256，
所以裸 clone 上 `check_lock_hulls` 照样能对账。

⚠️ 跑完**必须看它最后打印的保真度**：「跑完了」和「跑对了」是两回事——
`decor/calibrate.py` 末尾那句对账就是同一个道理，这里照抄了那个规矩。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

from . import lock

# ── 哪些资产要真碰撞，用什么阈值 ────────────────────────────────────────
# ⭐ 这是一份**有意的取舍清单**，不是资产属性：只有机器人会跟它精细交互的东西才进来。
# ⚠️ 阈值越小块越多、越贴合，但 qhull 与接触检测也越贵。0.10 是实测的甜点
#    （15 块 / 保真度 0.96）；只有形状特别简单的才放宽。
COLLIDE: dict[str, float] = {
    "dining_chair": 0.10,   # 餐厅 8 把共用同一套凸块（网格按资产共享，重复摆放几乎免费）
    "armchair": 0.10,       # 大客厅两把单椅，机器人要能坐
    "coffee_table": 0.10,   # 茶几：底下要能穿过去，桌面要能放东西
}

# CoACD 的其余参数。⛔ `seed` 固定 —— 同样的输入必须出同样的凸块，
# 否则每次重跑 lock 里的 sha256 都变，对账就失去意义。
COACD_SEED = 0
COACD_MAX_HULL = 24          # 上界；阈值到了自然会少于它

# ⭐ 读那一侧（凸块清单、字节在不在、必须写的 solref）住在 `decor/lock.py`——
#    因为 `make_house.py` 要读它，而那个模块必须只用 stdlib。这里只负责**生成**。
HULL_SUBDIR = lock.HULL_SUBDIR


def hull_dir(key: str) -> str:
    return os.path.join(lock.ASSET_DIR, key, HULL_SUBDIR)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_obj(path: str, verts, faces) -> None:
    """只写 v / f —— 凸块不需要 UV、法线、材质，碰撞体也用不上。"""
    with open(path, "w", encoding="utf-8") as f:
        for p in verts:
            f.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        for t in faces:
            f.write(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}\n")


def _solid_volume(mesh, pitch_div: int = 48) -> float | None:
    """开放网格算不出体积（本仓 20 件资产**没有一件是水密的**），改用体素填充估。

    ⚠️ 这只是个**量级**参考，用来判断分解得好不好，不参与任何几何计算。
    """
    try:
        pitch = float(max(mesh.extents)) / pitch_div
        return mesh.voxelized(pitch=pitch).fill().filled_count * pitch ** 3
    except Exception:
        return None


def _decompose(key: str, threshold: float, force: bool) -> dict | None:
    """对一件资产的所有部件跑 CoACD，返回要写进 lock 的那个 dict。"""
    import numpy as np
    import trimesh
    import coacd

    coacd.set_log_level("error")
    out_dir = hull_dir(key)
    os.makedirs(out_dir, exist_ok=True)
    if force:
        for stale in os.listdir(out_dir):
            if stale.endswith(".obj"):
                os.remove(os.path.join(out_dir, stale))

    files: list[dict] = []
    solid_sum = hull_sum = 0.0
    n = 0
    for p in lock.parts(key):
        src = os.path.join(lock.ASSET_DIR, key, p["obj"])
        mesh = trimesh.load(src, force="mesh", process=False)
        sv = _solid_volume(mesh)
        pieces = coacd.run_coacd(
            coacd.Mesh(mesh.vertices, mesh.faces),
            threshold=threshold, max_convex_hull=COACD_MAX_HULL,
            preprocess_mode="auto", seed=COACD_SEED,
        )
        for v, f in pieces:
            v, f = np.asarray(v), np.asarray(f)
            name = f"h{n}.obj"
            path = os.path.join(out_dir, name)
            _write_obj(path, v, f)
            files.append({"obj": f"{HULL_SUBDIR}/{name}", "sha256": _sha256(path),
                          "tris": int(len(f))})
            hull_sum += abs(trimesh.Trimesh(v, f).volume)
            n += 1
        if sv:
            solid_sum += sv
    if not files:
        return None
    return {
        "threshold": threshold,
        "count": len(files),
        # ⭐ 保真度 = 实体积 ÷ 凸块并集体积。越接近 1 越贴合真实形状；
        #    不分解时餐椅只有 0.30。⚠️ 它是审计信息，生成器不读它。
        "fidelity": round(solid_sum / hull_sum, 3) if hull_sum > 0 else None,
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="给 COLLIDE 里的资产生成 CoACD 碰撞凸块")
    ap.add_argument("--force", action="store_true", help="已经有的也重做")
    ap.add_argument("--only", default="", help="只做某一件（调试用）")
    args = ap.parse_args()

    try:
        import coacd  # noqa: F401
        import trimesh  # noqa: F401
    except ImportError as e:
        print(f"⛔ 缺 {e.name}。这一步的依赖不在生成器那三个里，单独装：\n"
              f"   pip install coacd trimesh")
        return 1

    data = lock.load()
    todo = [k for k in COLLIDE if not args.only or k == args.only]
    missing = [k for k in todo if not lock.bytes_present(k)]
    if missing:
        print(f"⚠️ 这几件的网格字节不在磁盘上，先跑 python -m decor.fetch：{missing}")
        todo = [k for k in todo if k not in missing]
    if not todo:
        print("⚠️ 没有可做的资产")
        return 1

    for key in todo:
        if not args.force and lock.hulls_present(key):
            rec = data[key][HULL_SUBDIR]
            print(f"·  {key:14s} 已有 {rec['count']} 块（阈值 {rec['threshold']}），跳过")
            continue
        rec = _decompose(key, COLLIDE[key], args.force)
        if rec is None:
            print(f"⛔ {key}：一块都没出来")
            return 1
        data[key][HULL_SUBDIR] = rec
        print(f"✅ {key:14s} {rec['count']:>3} 块  阈值 {rec['threshold']}  "
              f"面数 {sum(f['tris'] for f in rec['files']):>6}  保真度 {rec['fidelity']}")

    with open(lock.LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

    # ⭐ 自证一句 —— 照 `decor/calibrate.py` 末尾那个规矩：
    #    「跑完了」不等于「跑对了」，把判据当场打出来，别等三版之后才发现分解得很差。
    # ⚠️ 判据是**离 1.0 最远**那一件，不是数值最小那一件：保真度 1.27 同样值得看一眼
    #    （体素填充在薄结构上会高估，偏大通常是估计误差；偏小才是真的分解太粗）。
    scored = [(k, data[k][HULL_SUBDIR].get("fidelity")) for k in todo]
    scored = [(k, f) for k, f in scored if f is not None]
    if scored:
        worst_key, worst = max(scored, key=lambda kv: abs(kv[1] - 1.0))
        print(f"\n   离 1.0 最远的保真度：{worst}（{worst_key}）"
              f"{'  ⛔ 低于 0.6 说明分解太粗，把阈值调小' if worst < 0.6 else ''}")
    print(f"   ⛔ 别忘了：发射这些凸块的 geom 必须带 solref=\"{lock.HULL_SOLREF}\"，"
          f"否则快速撞击会穿模（见本模块顶部）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
