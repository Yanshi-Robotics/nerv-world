"""量出每张装饰网格在 **OBJ 文件坐标**里的真实包围盒，写回 decor.lock.json。

⭐ 为什么需要这一步：`decor/fetch.py` 写进 lock 的包围盒取自导出**之前**的 trimesh 对象，
   和真正落盘的 OBJ 差着导出时的取舍（实测白瓷花瓶差 14%）。差多少因资产而异，
   照那份数据缩放，网格就会系统性地探出碰撞盒，而且**编译不报错、渲染看着也正常**。
   这里编译一个只含这些网格的探针模型，从编译后的真实顶点重算——**实测值，不是猜的常数。**

⛔⛔ 两个反直觉的地方，都是 2026-08-07 用实测推翻旧结论时才弄清的，改这个文件前必读：

  1. **MuJoCo 编译 `<mesh>` 时会把顶点搬进惯性系**——既平移到重心（量存 `m.mesh_pos`），
     也**旋转到惯性主轴系**（量存 `m.mesh_quat`）。所以 `m.mesh_vert` 读出来的顶点
     **既不是文件坐标、也不只是平移过的文件坐标**。要还原必须两样都转回去：
     `v_file = v @ R(mesh_quat).T + mesh_pos`。
     ⛔ 老版本只加了 `mesh_pos`、漏了旋转，于是记下来的包围盒是"轴被置换过"的——
     床记成 0.66×2.21×2.15（真值 1.69×2.06×0.78）、抽油烟机的轴整个换了位。
     后果是全屋家具被缩小 1.0–4.2 倍，**48 项自检一条都没红**。

  2. **这个重定位量不需要任何人补偿回去，MuJoCo 自己会补。** 编译器把 `mesh_pos/mesh_quat`
     抄进该 geom 的 `geom_pos/geom_quat`，所以 `<geom type="mesh" pos="0 0 0">` 在世界里
     出现的位置，就是它在 OBJ 文件里的坐标（实测世界 bbox 与文件 bbox 逐位相同）。
     ⛔ 曾经有一版让生成器摆位时"改用 `com`"——那是**第二次**施加同一个量，
     多部件资产的部件会各自往外飞自己的重心那么远（条案两条柜腿各飞 ±0.49 m）。
     所以 `com` 现在只作为审计信息留在 lock 里，**生成器不读它**。

⚠️ 网格探出碰撞盒时，**放大碰撞盒完全没用**：`_fit_scale` 会把网格按比例一起撑大，
   超出量原封不动。也不要靠压缩缩放系数硬压——那只是把问题挪到下一件资产。
   正确的排查顺序是：先跑 `check_scene.py`，看 `check_lock_reconciles`
   （lock 自己对不对得上账）和 `check_decor_inside_box`（网格是不是真的装在盒子里）。

用法（⛔ 要 mujoco，所以不住在生成器依赖里）：
    python -m decor.calibrate
"""
from __future__ import annotations

import json
import os

from . import lock


def main() -> int:
    data = lock.load()
    keys = [k for k in data if lock.bytes_present(k)]
    if not keys:
        print("⚠️ 磁盘上没有资产字节，先跑 python -m decor.fetch")
        return 1

    # 探针模型：每张 OBJ 一个 mesh，scale=1（lock 里的 offset 也是未缩放坐标）
    rows = []
    for k in keys:
        for i, p in enumerate(lock.parts(k)):
            rows.append((k, i, os.path.join(lock.ASSET_DIR, k, p["obj"])))
    xml = "<mujoco><asset>" + "".join(
        f'<mesh name="m{n}" file="{path}"/>' for n, (_, _, path) in enumerate(rows)
    ) + "</asset><worldbody/></mujoco>"

    import mujoco
    import numpy as np
    m = mujoco.MjModel.from_xml_string(xml)

    for n, (k, i, _) in enumerate(rows):
        # ⭐ mesh_pos = MuJoCo 把顶点平移到原点时用掉的量 = 该网格的重心在文件坐标里的位置。
        #    ⚠️ 只留着供审计/排查看，**生成器不读它**——见下面那段。
        com = np.asarray(m.mesh_pos[n], dtype=float)
        data[k]["parts"][i]["com"] = [float(v) for v in com]
        # ⭐⭐ 顺带把 offset/half 也按**编译后的真实顶点**重算一遍。
        #    ⛔ 不能沿用 `decor/fetch.py` 写的那份：它记的是导出**之前**的 trimesh 包围盒，
        #       和落盘的 OBJ 差着导出时的取舍（实测白瓷花瓶差 14%）。差多少因资产而异，
        #       结果就是网格系统性地探出碰撞盒，而且**编译不报错、渲染看着也正常**。
        #
        # ⛔⛔ 2026-08-07 修的那个 bug 就在这三行里，代价是全屋家具缩小 1.0–4.2 倍：
        #    MuJoCo 编译 <mesh> 时**不只平移到重心，还会把顶点旋转到惯性主轴系**
        #    （旋转量存在 `m.mesh_quat`）。老代码只把 com 加了回去、没把旋转转回来，
        #    于是算出的包围盒是"轴被置换过"的——床记成 0.66×2.21×2.15（真值
        #    1.69×2.06×0.78）、条案记成 1.31×0.81×2.44（真值 2.44×0.52×0.68）。
        #    回转体（花瓶、胸像）转了也一样，所以"大部分看着都对"，越不对称的错得越离谱。
        #    ⭐ 判据是 `check_scene.py` 的 `check_lock_reconciles`：并集跨度必须等于 size。
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, np.asarray(m.mesh_quat[n], dtype=float))
        v = m.mesh_vert[m.mesh_vertadr[n]:m.mesh_vertadr[n] + m.mesh_vertnum[n]]
        v_file = v @ rot.reshape(3, 3).T + com     # 转回 OBJ 文件坐标
        lo, hi = v_file.min(axis=0), v_file.max(axis=0)
        data[k]["parts"][i]["offset"] = [float((a + b) / 2.0) for a, b in zip(lo, hi)]
        data[k]["parts"][i]["half"] = [float((b - a) / 2.0) for a, b in zip(lo, hi)]

    with open(lock.LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

    print(f"✅ 已标定 {len(rows)} 张网格，写回 {os.path.basename(lock.LOCK_PATH)}")
    # ⭐ 自证一句：各部件 offset±half 的并集必须等于整件 size。这就是
    #    `check_scene.py::check_lock_reconciles` 的判据，在这里先报一次，
    #    免得"标定跑完了"和"标定跑对了"被当成一回事（旧 bug 正是这么活下来的）。
    worst_gap, worst_key = 0.0, "—"
    for k in keys:
        ps = data[k]["parts"]
        lo = [min(p["offset"][j] - p["half"][j] for p in ps) for j in range(3)]
        hi = [max(p["offset"][j] + p["half"][j] for p in ps) for j in range(3)]
        gap = max(abs((h - lv) - s) for h, lv, s in zip(hi, lo, data[k]["size"]))
        if gap > worst_gap:
            worst_gap, worst_key = gap, k
    print(f"   最坏「并集跨度 vs size」对账差：{worst_gap*100:.1f} cm（{worst_key}）"
          f"{'  ⛔ 超过 5 cm 说明标定没算对' if worst_gap > 0.05 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
