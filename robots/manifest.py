"""alice-house 里有哪些机器人 —— 换身体要知道的全部事实，收在这一处。

**这里只放"这台机器人是什么"（资产事实），不放"我打算怎么开它"（控制参数）。**
判据：换个消费方（换个世界、换个任务）还成立的，是事实，放这里；
只对某一个消费方成立的（走多快、多近刹车、一次最多走几米），是那个消费方的配置，放它自己那儿。

**也不放策略契约里已经有的东西**（关节顺序、增益、力矩上限、观测项顺序与缩放、要不要拼历史帧、
控制周期）——那些的单一真相源是各自 `policy_dir` 下的 `contract.json`（由训练环境导出）。
在这儿再抄一份就成了"改一处忘另一处"的隐患。这里只放契约里**没有**的：
模型文件在哪、出生多高、相机叫什么、力矩怎么发。

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
        "chase_body": "base",            # 第三视角跟拍挂在哪个部件上（给人看，ANIMA 看不到）
        "policy_dir": "policies/go2-velocity-flat",
        # ⛔ 力矩怎么发：训练侧是**显式 PD** → 部署侧自己算 tau = kp·(q*−q) − kd·qd，
        #    并把模型里的关节阻尼/库仑摩擦清零（那是给"手搓控制器"准备的，训练时不存在）。
        #    和 G1 正好相反，搞反了狗当场走不动/抖翻，别凭印象填。
        "pd_mode": "explicit",
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
        "policy_dir": "policies/g1-29dof-turn",
        # ⛔ 训练侧是 **ImplicitActuator（隐式 PD）** → 部署侧必须把 kd 写进 model.dof_damping
        #    让 MuJoCo 半隐式积分去施加，力矩只发 kp·(q*−q)。
        #    写成外部力矩 −kd·qd 会让关节速度从第一步就高频振铃 → 策略收到垃圾观测 → 约 1 秒倒。
        #    这是 locomotion 项目 2026-07-24 花一整天诊断换来的结论，别再试第二遍。
        "pd_mode": "implicit",
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
