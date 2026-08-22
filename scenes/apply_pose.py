"""把 layout 声明的**姿态**（目前只有坐姿）摆到机器人身上，并推物理让它沉降到稳态。

⭐ 为什么需要这个模块 —— 三条约束把做法逼成了现在这样：

1. **产物里没有关键帧，也不该有。** `make_house.py` **有意不 import mujoco**
   （生成场景的依赖守在 `mujoco numpy pillow`，而它连 mujoco 都不用），
   所以它算不出 `nq`，也就写不出 `<keyframe>`。
   ⚠️ 家具的静止姿态可以用 `<joint ref>` 解决（那是免关键帧的 `qpos0`），
   但**机器人的姿态不行**——机器人是 `<include>` 进来的，它的 XML 不归本仓改。

2. **所以姿态按「关节名 → 角度」声明，运行期再拼 qpos。**
   ⛔ 绝不按下标声明。下标会随机器人型号、随 MuJoCo 版本、随谁往场景里多加一个关节而变；
   名字不会。换成 Go2 时它一个腿关节名都对不上，`apply()` 就只摆底座、返回 0，
   调用方据此跳过——**退化得安静而正确**，不会把力矩写到别的关节上。

3. **解析摆出来的姿态不是稳态，必须跑到收敛再用。**
   实测（2026-08-22）：G1 按"髋 −1.57 / 膝 +1.57 / 踝 0"摆到 0.35 m 的座面上，
   推 3 秒物理后骨盆会**上抬 4.6 cm、躯干前倾 10°**——它往靠背里靠进去了。
   ⇒ 直接拿解析姿态出图，看着就是"悬在沙发上方"。`settle()` 就是干这个的。

用法（`tools/make_docs_images.py` 的 POSED 镜头、以及自检都走这里）：

    from scenes import apply_pose
    n = apply_pose.apply(m, d, layout.SIT_POSES["gr_sofa"])
    apply_pose.settle(m, d, gains=apply_pose.load_gains(contract_path), seconds=3.0)
"""
from __future__ import annotations

import json
import math

import mujoco
import numpy as np


def load_gains(contract_path: str) -> dict[str, tuple[float, float, float]]:
    """从策略契约读 (kp, kd, 力矩上限)。⛔ 别在本仓另写一份增益——契约是唯一真相源。"""
    c = json.load(open(contract_path, encoding="utf-8"))
    out: dict[str, tuple[float, float, float]] = {}
    for grp in c["actuators"].values():
        for n, kp, kd, eff in zip(grp["joint_names"], grp["stiffness"],
                                  grp["damping"], grp["effort_limit"]):
            out[n] = (float(kp), float(kd), float(eff))
    return out


def _first_free_joint(m) -> int:
    """机器人的浮动基。⭐ 机器人是产物里第一个 `<include>` 进来的，所以它必是第 0 个 free joint。

    ⚠️ 仍然**查一遍**而不是写死 0：家具将来挂上 freejoint 之后，"第几个"这种假设
       正是会静默错位的那类；查出来的下标错了会当场报错，写死的不会。
    """
    for j in range(m.njnt):
        if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
            return j
    raise ValueError("模型里没有自由关节——这份产物里没有机器人？")


def apply(m, d, pose: dict) -> int:
    """把姿态写进 `d.qpos`，返回**认出来的关节数**。⛔ 只按名字写，绝不按下标。

    认不出来的关节直接跳过（换了机器人就是这种情况），由调用方决定要不要接受。
    """
    d.qpos[:] = m.qpos0
    d.qvel[:] = 0.0
    a = m.jnt_qposadr[_first_free_joint(m)]
    d.qpos[a:a + 3] = pose["base_xyz"]
    h = float(pose.get("base_yaw", 0.0)) / 2.0
    d.qpos[a + 3:a + 7] = [math.cos(h), 0.0, 0.0, math.sin(h)]
    n = 0
    for name, ang in pose["joints"].items():
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name)
        if j < 0:
            continue                       # 别的机器人没这个关节 —— 正常，跳过
        d.qpos[m.jnt_qposadr[j]] = float(ang)
        n += 1
    mujoco.mj_forward(m, d)
    return n


def settle(m, d, gains: dict, seconds: float = 3.0) -> dict:
    """用契约的 kp/kd 定点保持当前姿态，推物理到稳态。返回一份可以拿去做判据的度量。

    ⛔ 隐式 PD：`kd` **写进 `dof_damping`**、力矩只发 `kp·(q*−q)`。
       写成外部力矩 `−kd·qd` 会让关节速度从第一步就高频振铃（`robots/manifest.py`
       在 g1 那条上写了这个红线，那边是部署器，这里是同一件事）。
    ⚠️ 本函数**改 model 的 `dof_damping`**。出图/自检各自新建一个 model，不共用，所以没关系；
       ⛔ 别在一个长期存活的 model 上调它。
    """
    names = [n for n in gains if mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n) >= 0]
    if not names:
        return {"matched": 0}
    jid = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n) for n in names]
    qadr = np.array([m.jnt_qposadr[j] for j in jid])
    dadr = np.array([m.jnt_dofadr[j] for j in jid])
    # 执行器按**传动目标**反查，⛔ 不按名字：执行器名和关节名不一定一样
    j2a = {int(m.actuator_trnid[a, 0]): a for a in range(m.nu)
           if m.actuator_trntype[a] == mujoco.mjtTrn.mjTRN_JOINT}
    missing = [n for n, j in zip(names, jid) if j not in j2a]
    if missing:
        raise ValueError(f"这些关节没有对应执行器，驱动不了：{missing}")
    aid = np.array([j2a[j] for j in jid])
    kp = np.array([gains[n][0] for n in names])
    kd = np.array([gains[n][1] for n in names])
    tmax = np.array([gains[n][2] for n in names])
    for i, dof in enumerate(dadr):
        m.dof_damping[dof] = kd[i]

    base = m.jnt_qposadr[_first_free_joint(m)]
    p0 = d.qpos[base:base + 3].copy()
    tgt = d.qpos[qadr].copy()
    for _ in range(int(seconds / m.opt.timestep)):
        d.ctrl[aid] = np.clip(kp * (tgt - d.qpos[qadr]), -tmax, tmax)
        mujoco.mj_step(m, d)
    p1 = d.qpos[base:base + 3]
    q = d.qpos[base + 3:base + 7]
    # 躯干 z 轴与世界 z 轴的夹角。⛔ R[2][2] = 1 − 2(x²+y²)，用的是 q[1]/q[2]。
    #    ⚠️ 误用 q[2]/q[3] 时，yaw=90° 的姿态会恒等于 90°——像"倒了"其实好好的。
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * (q[1] ** 2 + q[2] ** 2)))))
    return {"matched": len(names), "rise": float(p1[2] - p0[2]),
            "slide": float(math.hypot(p1[0] - p0[0], p1[1] - p0[1])),
            "tilt_deg": tilt, "ncon": int(d.ncon)}
