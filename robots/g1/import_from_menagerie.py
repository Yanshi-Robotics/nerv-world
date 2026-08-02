#!/usr/bin/env python3
"""把宇树 G1（29 自由度）从 MuJoCo Menagerie 导进 alice-house —— 可重跑，别手改产物。

**为什么要有这个脚本**：上游模型不能原样用，得改三处。改动写成代码而不是手改文件，
是为了说清楚"我们到底动了上游什么"，以及上游更新时能一键重来。

三处改动（每一处都有非做不可的理由）：

1. **执行器 `<position>` → `<motor>`**。上游用位置执行器（`ctrl` 是目标角度，MuJoCo 自己算力矩）；
   我们的部署器按训练侧口径**自己算力矩**再写进 `ctrl`（隐式 PD：kd 进 `dof_damping`，
   力矩只发 `kp·(q*−q)`）。往位置执行器里写力矩＝写了个荒唐的目标角度，实测 0.4 秒就倒。
   ⚠️ 不写 `ctrlrange`：力矩上限的**单一真相源是 contract.json**（部署器按它 clip），
   在 XML 里再抄一份就成了改一处忘另一处的隐患。

2. **加一只头部前视相机**。上游模型没有相机，而 ANIMA 全靠这只眼睛看世界。
   装在 `torso_link` 上（跟着腰转，和真人一样），高度按站立时约 1.25 m 定。

3. **不用改 geom 分组**（记在这儿免得下次又去查）：上游已经是 menagerie 惯例——
   视觉 group 2、碰撞 group 3，和房子用的 0（结构家具）/1（天花板）不冲突。
   世界侧的激光测距靠这个分组把"射线打到墙"和"射线打到自己胳膊"分开，撞上就拒绝启动。

上游来源与许可：MuJoCo Menagerie 的 `unitree_g1`（BSD-3-Clause，见同目录 G1_MODEL_LICENSE）。

⚠️ 2026-08-02 起 `--source` 是**必填**的。它原先默认指向隔壁 `unitree-g1-locomotion`
仓里的一份 menagerie 副本，而那个仓已归档并删除本地——留着一个猜不中的默认路径，
只会让人拿到一句"文件不存在"而不知道该给什么。自己从上游拉一份：

    git clone --depth 1 https://github.com/google-deepmind/mujoco_menagerie
    python import_from_menagerie.py --source mujoco_menagerie/unitree_g1

（产物已经在本仓里了，只有上游更新时才需要重跑。）
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 头部相机 ----
# 装在 torso_link 上。torso_link 在默认站姿下位于世界 z=0.844，整机最高点 1.379 m（实测）。
CAM_BODY = "torso_link"
CAM_EYE_HEIGHT_M = 1.25      # 想要的世界眼高（约在胸口以上、头顶以下）
CAM_TORSO_Z_M = 0.844        # 默认站姿下 torso_link 的世界高度（实测，用于换算局部偏移）
CAM_FORWARD_M = 0.10         # 往前伸出多少（脱开躯干本体，免得镜头贴在自己胸口上）
CAM_PITCH_DOWN_DEG = 10.0    # 视线下俯角：人形站得高，平视只看得见墙，略微下看才看得见家具和地面
CAM_FOVY_DEG = 95            # 与 Go2 那只一致，两种身体的视野可比


def camera_xml() -> str:
    """生成 <camera> 元素。xyaxes 第一组＝镜头右方向，第二组＝镜头上方向（MuJoCo 沿 −z 看）。"""
    a = math.radians(CAM_PITCH_DOWN_DEG)
    # 视线 = 机体 +x 方向下俯 a → 上方向 = (sin a, 0, cos a)
    up_x, up_z = math.sin(a), math.cos(a)
    z = round(CAM_EYE_HEIGHT_M - CAM_TORSO_Z_M, 4)
    return (f'      <camera name="head_front" pos="{CAM_FORWARD_M:g} 0 {z:g}" '
            f'xyaxes="0 -1 0  {up_x:.4f} 0 {up_z:.4f}" fovy="{CAM_FOVY_DEG}"/>\n')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        required=True,
        help="menagerie 的 unitree_g1 目录（必填；见本文件头部怎么拉一份）",
    )
    args = ap.parse_args()
    src_xml = os.path.join(args.source, "g1.xml")
    if not os.path.exists(src_xml):
        print(f"找不到上游模型 {src_xml}")
        return 1

    s = open(src_xml, encoding="utf-8").read()

    # ① 位置执行器 → 力矩执行器
    s, n_act = re.subn(r'<position class="[^"]*" name="([^"]+)" joint="([^"]+)"\s*/>',
                       r'<motor name="\1" joint="\2"/>', s)
    if n_act == 0:
        print("⚠️ 一个 <position> 执行器都没换到——上游格式变了，先看清楚再说，拒绝产出半成品。")
        return 1

    # ② 头部相机（插在 torso_link 这个 body 的开头）
    if "head_front" not in s:
        pat = re.compile(r'(<body name="' + CAM_BODY + r'"[^>]*>\n)')
        s, n_cam = pat.subn(lambda m: m.group(1) + camera_xml(), s, count=1)
        if n_cam != 1:
            print(f"⚠️ 没找到 body «{CAM_BODY}»，相机没装上。上游结构变了，拒绝产出半成品。")
            return 1

    # ③ meshdir：产物被仓根的 house-g1.xml include，路径要从**仓根**算起（不是从本目录）
    s = s.replace('meshdir="assets"', 'meshdir="robots/g1/meshes"')
    s = ('<!-- 本文件由 import_from_menagerie.py 从 MuJoCo Menagerie 的 unitree_g1 生成，请勿手改。\n'
         '     改了什么、为什么改，见那个脚本的文件头。上游许可见同目录 G1_MODEL_LICENSE。-->\n') + s

    open(os.path.join(HERE, "g1.xml"), "w", encoding="utf-8").write(s)

    # 网格与许可
    meshes = os.path.join(HERE, "meshes")
    if os.path.isdir(meshes):
        shutil.rmtree(meshes)
    shutil.copytree(os.path.join(args.source, "assets"), meshes)
    for name, dst in (("LICENSE", "G1_MODEL_LICENSE"), ("README.md", "G1_MODEL_UPSTREAM.md")):
        p = os.path.join(args.source, name)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(HERE, dst))

    n_mesh = len(os.listdir(meshes))
    print(f"生成 {os.path.join(HERE, 'g1.xml')}")
    print(f"  执行器 position→motor：{n_act} 个")
    print(f"  头部相机：装在 {CAM_BODY}，眼高约 {CAM_EYE_HEIGHT_M} m，下俯 {CAM_PITCH_DOWN_DEG}°")
    print(f"  网格：{n_mesh} 个 → meshes/")
    print("  许可与上游说明：G1_MODEL_LICENSE / G1_MODEL_UPSTREAM.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
