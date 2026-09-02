"""alice-house 里有哪些机器人 —— 换身体要知道的全部事实，收在这一处。

**这里只放"这台机器人是什么"（资产事实），不放"我打算怎么开它"（控制参数）。**
判据：换个消费方（换个世界、换个任务）还成立的，是事实，放这里；
只对某一个消费方成立的（走多快、多近刹车、一次最多走几米），是那个消费方的配置，放它自己那儿。

**也不放任何与运动策略有关的东西**（2026-09-02 起）：策略文件、力矩模式、命令范围、命令死区、
转弯特性——那些是**训练产物的属性**，住在消费方指定的策略发布架里
（每份策略目录 = `policy.onnx` + `contract.json` + `release.yaml`）。
本仓只放**场景与机器人本体**的资产事实：模型文件在哪、出生多高、相机叫什么、脚是哪几个 body。

场景（房间矩形、出生点在哪）住在仓根的 `layout.py`；机器人住这里——
因为同一台机器人可以放进任何一个场景，而出生点是每个场景各自的事。

加一台新机器人：往 `ROBOTS` 里**追加**一条（⛔ 追加不替换），把下面每个字段都填对，
再跑一次 `make_house.py --robot <key>`。
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # alice-house 仓根


ROBOTS: dict[str, dict] = {
    # ───────────────────────────────────────────────────────────── 四足机器狗
    "go2": {
        "label": "四足机器狗（宇树 Go2）",
        "xml": "robots/go2/go2.xml",
        "meshdir": "robots/go2/meshes",
        # 出生时躯干中心离地多高(m)。太低会把脚嵌进地板、一放开就被接触力弹飞。
        "start_height": 0.445,
        "camera": "head_front",          # 模型里那只前视相机的名字（ANIMA 唯一的眼睛）
        # 第三视角跟拍（给人看的旁观镜头，ANIMA 看不到）：挂在哪个部件上、退多远、抬多高。
        # ⚠️ **必须按机器人分**：狗站立约 0.4 m、人形 1.38 m，同一组机位对狗偏高、对人形偏低。
        #    退的距离大致是身长的两三倍、抬的高度大致到身高的一倍半，画面里才既看得清它、
        #    又看得见它面前那片空间。
        "chase_body": "base",
        "chase_back_m": 1.6,             # 退到身后多远（狗矮，退太远就看不清它了）
        "chase_up_m": 0.7,               # 抬多高（俯角约 24°）
    },
    # ───────────────────────────────────────────────────────────── 人形
    "g1": {
        "label": "人形机器人（宇树 G1，29 自由度）",
        "xml": "robots/g1/g1.xml",
        "meshdir": "robots/g1/meshes",
        # 训练侧默认根高（contract.json 的 default_root_pos_w[2]）。站立总高实测 1.379 m。
        "start_height": 0.80,
        "camera": "head_front",          # 由 robots/g1/import_from_menagerie.py 装上，眼高约 1.25 m
        "chase_body": "torso_link",
        "chase_back_m": 2.6,             # 人形高，得退远些才装得下整个人
        "chase_up_m": 1.7,               # 抬到比头顶略高（俯角约 33°）
        # 脚部 body 名（落脚事件检测按 body 子树取 geom 集合，⛔ 不按名字猜 geom id）
        "foot_bodies": ("left_ankle_roll_link", "right_ankle_roll_link"),
    },
}

DEFAULT_ROBOT = "go2"


def get(key: str) -> dict:
    """按 key 取一台机器人的清单条目；名字不对就报出有哪些可选，不静默回退到默认那台
    （静默回退＝你以为在跑人形、其实跑的是狗，最难查的那种错）。"""
    if key not in ROBOTS:
        raise KeyError(f"没有名叫「{key}」的机器人。现有：{', '.join(ROBOTS)}")
    return ROBOTS[key]


def path(key: str, field: str) -> str:
    """把清单里的相对路径拼成绝对路径（相对仓根）。"""
    return os.path.join(ROOT, get(key)[field])
