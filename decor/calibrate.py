"""量出 MuJoCo 对每张装饰网格施加的**重定位量**，写回 decor.lock.json。

⭐ 为什么需要这一步（这是本轮最贵的一个教训）：
   `decor/convert.py` 导出 OBJ 时，把所有部件按**整件包围盒中心**统一居中，并把每个部件
   自己的**包围盒中心**记成 `offset`。生成器照这个 offset 摆位。
   ⛔ 但 MuJoCo 编译 `<mesh>` 时会把顶点按**重心**（center of mass）平移到原点——
   `包围盒中心 ≠ 重心`，差多少取决于几何分布，非闭合网格上尤其大。
   于是每个部件都被系统性地挪偏，多部件资产就会探出它的碰撞盒。

⚠️ 这个偏差**不能靠放大碰撞盒补**：`_fit_scale` 会把网格按比例一起撑大，超出量原封不动。
   我在这上面白转了六轮才想明白。也不能靠压缩缩放系数硬压——那只是把问题挪到下一件资产。

✅ 正解：MuJoCo 自己把这个平移量存在 `m.mesh_pos` 里。编译一个只含这些网格的探针模型读出来，
   写进 lock 当 `com`，生成器摆位时改用它。**这是实测值，不是猜的常数。**

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
    m = mujoco.MjModel.from_xml_string(xml)

    for n, (k, i, _) in enumerate(rows):
        # ⭐ mesh_pos = MuJoCo 把顶点平移到原点时用掉的量 = 该网格的重心在文件坐标里的位置
        com = [float(v) for v in m.mesh_pos[n]]
        data[k]["parts"][i]["com"] = com
        # ⭐⭐ 顺带把 offset/half 也按**编译后的真实顶点**重算一遍。
        #    ⛔ 不能沿用 `decor/fetch.py` 写的那份：它记的是导出**之前**的 trimesh 包围盒，
        #       和落盘的 OBJ 差着导出时的取舍（实测白瓷花瓶差 14%）。差多少因资产而异，
        #       结果就是网格系统性地探出碰撞盒，而且**编译不报错、渲染看着也正常**。
        v = m.mesh_vert[m.mesh_vertadr[n]:m.mesh_vertadr[n] + m.mesh_vertnum[n]]
        lo, hi = v.min(axis=0), v.max(axis=0)      # 已被减去 com，加回去才是文件坐标
        data[k]["parts"][i]["offset"] = [float((a + b) / 2.0 + c) for a, b, c in zip(lo, hi, com)]
        data[k]["parts"][i]["half"] = [float((b - a) / 2.0) for a, b in zip(lo, hi)]

    with open(lock.LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

    worst = max(
        (max(abs(a - b) for a, b in zip(p["com"], p.get("offset", [0, 0, 0]))), k)
        for k in keys for p in data[k]["parts"])
    print(f"✅ 已标定 {len(rows)} 张网格，写回 {os.path.basename(lock.LOCK_PATH)}")
    print(f"   最大「重心 vs 包围盒中心」偏差：{worst[0]*100:.1f} cm（{worst[1]}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
