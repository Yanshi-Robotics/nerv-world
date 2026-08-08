"""装饰网格的资产登记表 —— 单一真相源。

⛔ **只用 stdlib**。`make_house.py` 会 import 这个模块，而生成场景的依赖必须守在
   `mujoco numpy pillow`；下载和转换那一套（trimesh / urllib）住在 `decor/fetch.py` 和
   `decor/convert.py`，生成器永远不碰。

⛔ **许可白名单是可执行代码，不是注释**：`fetch.py` 拒绝写入任何上游许可不在
   `LICENSE_ALLOWLIST` 里的字节。
   ⚠️ Objaverse 的许可**不是一律 CC-BY**：调研时第二个沙发就撞上 `by-nc`
   （uid `0aeac4f2…` @homelegance）。而且 **Sketchfab 的 search 接口返回的 license 是 None**，
   必须逐个查 `api.sketchfab.com/v3/models/<uid>` 拿真 slug。

字段说明：
  source     "polyhaven" | "objaverse"
  source_id  Poly Haven 的资产名，或 Objaverse 的 uid
  license    **声明**的许可；fetch 时会和上游实际返回的比对，不一致就拒绝
  target     这东西现实里多大 —— ⚠️ 外部素材单位五花八门（Objaverse 尤其），
             给一个真实尺寸让转换脚本据此缩放。Poly Haven 本身是米制，可省。
  max_tris   减面目标（每个材质组）。⚠️ 纯视觉网格不算凸包，所以这个数是给
             渲染和仓库体积定的，不是给编译定的。
"""
from __future__ import annotations

LICENSE_ALLOWLIST = {"CC0-1.0", "CC-BY-4.0", "CC-BY-3.0"}

# Objaverse 的 license slug → SPDX
OBJAVERSE_SLUG = {"cc0": "CC0-1.0", "by": "CC-BY-4.0", "by-sa": "CC-BY-SA-4.0",
                  "by-nc": "CC-BY-NC-4.0", "by-nc-sa": "CC-BY-NC-SA-4.0",
                  "by-nd": "CC-BY-ND-4.0", "by-nc-nd": "CC-BY-NC-ND-4.0"}

ASSETS: dict[str, dict] = {
    # ── ⭐ 花瓶摆件（Jeff 点名要真的）──────────────────────────────────
    # Poly Haven 的陶瓷花瓶只有 2.5k 面，**不用减面**，性价比最高的一档。
    "vase_a": {"source": "polyhaven", "source_id": "ceramic_vase_01", "license": "CC0-1.0",
               "res": "2k", "max_tris": 4000, "label": "白瓷高瓶（现代）"},
    "vase_b": {"source": "polyhaven", "source_id": "ceramic_vase_02", "license": "CC0-1.0",
               "res": "2k", "max_tris": 4000, "label": "彩绘陶瓶"},
    "vase_c": {"source": "polyhaven", "source_id": "ceramic_vase_04", "license": "CC0-1.0",
               "res": "2k", "max_tris": 4000, "label": "现代壶形瓶"},
    "bowl": {"source": "polyhaven", "source_id": "wooden_bowl_01", "license": "CC0-1.0",
             "res": "2k", "max_tris": 6000, "label": "木碗"},
    "bust": {"source": "polyhaven", "source_id": "marble_bust_01", "license": "CC0-1.0",
             "res": "2k", "max_tris": 12000, "label": "大理石胸像（画廊基座）"},
    "plant_a": {"source": "polyhaven", "source_id": "potted_plant_01", "license": "CC0-1.0",
                "res": "2k", "max_tris": 14000, "label": "盆栽"},
    # ⭐ 2026-08-07 复活。它的包围盒确实宽 6.87 m，但**那不是脏几何**：
    #    上游把**四棵不同大小的发财树并排摆在一个文件里**，每棵是"冠 + 盆"两个材质组。
    #        p0+p4 → x≈+2.91，高 1.90 m（最大）      p1+p5 → x≈+0.98，高 1.15 m
    #        p2+p6 → x≈−1.11，高 0.74 m（最小）      p3+p7 → x≈−3.06，高 1.30 m
    #    ⭐ 用法：`F.mesh_piece(..., mesh="plant_b", parts=(3, 7))` 只取一棵。
    #       `_asset_span()` 按子集求并集并把跨度中心减掉，**摆位自动归正**，
    #       不需要去 Blender 里切开，也不需要为每棵树各建一个 lock key。
    #    ⚠️ 当年撤它的判断（"多余的 LOD 实例，要先在 Blender 清一遍"）是错的——
    #       别再照那个结论把它撤第二次。
    "plant_b": {"source": "polyhaven", "source_id": "pachira_aquatica_01", "license": "CC0-1.0",
                "res": "2k", "max_tris": 14000, "label": "发财树（⚠️ 一包 4 棵，用 parts= 取一棵）"},
    "pillows": {"source": "polyhaven", "source_id": "throw_pillows_01", "license": "CC0-1.0",
                "res": "2k", "max_tris": 6000, "label": "抱枕"},

    # ── 英雄三间：大客厅 ─────────────────────────────────────────────
    "armchair": {"source": "polyhaven", "source_id": "modern_arm_chair_01", "license": "CC0-1.0",
                 "res": "2k", "max_tris": 9000, "label": "现代单椅"},
    "coffee_table": {"source": "polyhaven", "source_id": "coffee_table_round_01",
                     "license": "CC0-1.0", "res": "2k", "max_tris": 5000, "label": "圆形大理石茶几"},
    "console": {"source": "polyhaven", "source_id": "modern_wooden_cabinet", "license": "CC0-1.0",
                "res": "2k", "max_tris": 12000, "label": "现代木柜（条案）"},
    "floor_lamp": {"source": "polyhaven", "source_id": "modern_ceiling_lamp_01",
                   "license": "CC0-1.0", "res": "2k", "max_tris": 6000, "label": "现代灯具"},

    # ── 英雄三间：餐厅 ─────────────────────────────────────────────
    "dining_chair": {"source": "polyhaven", "source_id": "dining_chair_02", "license": "CC0-1.0",
                     "res": "2k", "max_tris": 5000, "label": "现代皮质餐椅（×8，必须减面）"},
    "chandelier": {"source": "polyhaven", "source_id": "Chandelier_02", "license": "CC0-1.0",
                   "res": "2k", "max_tris": 12000, "label": "优雅吊灯"},

    # ── 英雄三间：主卧（Objaverse @elba 软包床，CC-BY，已逐个核过许可）──
    # ⚠️ 这几件很重：Bed_Astrid 约 18 万面，其中两个枕头组就占 13.9 万——
    #    按材质组分别减面之后约 5 万，肉眼看不出差别。
    "bed": {"source": "objaverse", "source_id": "bb98964881dd4c639efbb3838f9ba4de",
            "license": "CC-BY-4.0", "target": {"axis": "y", "metres": 2.06},
            "max_tris": 8000, "label": "软包大床 Bed_Astrid（@elba）"},
    "nightstand": {"source": "objaverse", "source_id": "02c6fbe74d9d4d33b2c17c942fe99344",
                   "license": "CC-BY-4.0", "target": {"axis": "x", "metres": 0.50},
                   "max_tris": 6000, "label": "床头柜 Tumb Astrid（@elba）"},
}
