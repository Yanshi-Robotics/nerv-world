"""house2 的配图镜头清单。

镜头是**场景专属事实**（站在哪、看哪儿只对这一栋楼成立），所以跟着场景走，
不放在生成脚本里——house1 同理，见 `scenes/house1/shots.py`。

⚠️ 眼高必须和 `robots/manifest.py` 里那台机器人**实际**的相机高度对得上，
否则配图说"人形看到的"其实是个不存在的机位。

⛔ **一切坐标都从 layout 现算，这个文件里不许出现楼梯/层高的裸数字。**
   早先这里写了 `STOREY = 3.15`，和 layout 各存一份；层高一改，配图就全站错了楼层，
   而脚本照常输出、看图的人也看不出来。同一个数只准有一处真相源。

这栋楼的重点是楼梯，所以镜头以"能不能看清楚**两跑是怎么被平台接起来的**"为准来选：
从底层望上去、站在上行跑中间、站在中间平台、以及到达上一层回望。
"""
from __future__ import annotations

from scenes import manifest as _SCENES

_L = _SCENES.load_layout("house2")

DOG_EYE = 0.38      # 四足机器狗头部相机高度(m)
HUMAN_EYE = 1.25    # 人形 G1 头部相机高度(m)，装在 torso_link 上

# ── 从 layout 现算的关键位置（别在下面写裸数字）──
_STOREY = _L.STOREY_H                        # 层高 2.88
_UP_X = _L._UP_X                             # 上行跑中心线 3.94
_DOWN_X = _L._DOWN_X                         # 回头跑中心线 5.26
_SHAFT_MID_X = _L._WELL_X                    # 梯井中线 4.60
_FLOOR_LANDING_Y = _L._IN_Y0 + _L.LANDING_DEPTH / 2.0        # 楼层平台中心 1.44
_MID_LANDING_Y = _L._MID_LANDING_Y0 + _L.LANDING_DEPTH / 2.0  # 中间平台中心 5.24
_MID_LANDING_Z = _L.RISERS_PER_FLIGHT * _L.STEP_RISE          # 中间平台标高 1.44
_FLIGHT_MID_Y = (_L._FLOOR_LANDING_Y1 + _L._MID_LANDING_Y0) / 2.0   # 梯段中点 3.34
_FLIGHT_MID_Z = _L.STEP_RISE * (_L.TREADS_PER_FLIGHT / 2.0)         # 站在梯段中点的踏面高
_N_ROOM_X = (_L.WEST_X + _L.STAIR_X0) / 2.0        # 北侧房间的横向中心
_N_ROOM_Y = (_L.STAIR_Y0 + _L.NORTH_Y) / 2.0       # 北侧房间的进深中心

# ── 俯视：(编号, 文件名, 看向哪, 视野距离m, 说明) ──
# ⚠️ 三层的平面是重叠的，纯俯视只能拍到最上面那层。所以这里只留一张整体俯视
#    （拍的是顶层），楼内情况靠下面的站位镜头看。
TOPDOWN = [
    ("A1", "A1-三层楼-顶视.png", (0.0, 0.8), 27, "整栋俯视（关掉天花板，看到的是顶层）"),
]

# ── 站位：(编号, 文件名, 站在哪(x,y,z), 朝向角度, 说明) ──
#    朝向：0=朝 +x(东)，90=朝 +y(北)，180=朝西，270=朝南
#    ⭐ 这一栏比 house1 多一个 z：三层楼必须说清站在第几层。
EYE = [
    ("S1", "S1-楼层平台望向上行跑.png", (_UP_X, _L._IN_Y0 + 0.3, HUMAN_EYE), 90,
     "0 层楼层平台，正对上行跑（进门就站这儿，抬头就是第一级）"),
    ("S2", "S2-站在上行跑中间.png", (_UP_X, _FLIGHT_MID_Y, _FLIGHT_MID_Z + HUMAN_EYE), 90,
     "踩在上行跑中部，看向中间平台——右手边那道就是梯井隔墙"),
    # ⚠️ S3/S4 分左右两条道各站一次，不站梯井中线——站中线正对隔墙，
    #    拍出来是一根杵在画面正中的柱子，什么也说明不了（第一版就是这样）。
    ("S3", "S3-中间平台-回头跑从脚下起步.png",
     (_DOWN_X, _L._MID_LANDING_Y0 + 0.45, _MID_LANDING_Z + HUMAN_EYE), 270,
     "⭐ 站在中间平台的回头跑那一侧：下一跑就贴着平台边起步、往上爬——这就是「两跑被平台接起来」"),
    ("S4", "S4-中间平台-回望上行跑.png",
     (_UP_X, _L._MID_LANDING_Y0 + 0.45, _MID_LANDING_Z + HUMAN_EYE), 270,
     "同一块平台的另一侧：刚爬上来的那一跑从脚下往下走"),
    # ⚠️ 站梯井中线，不贴东墙：贴墙拍出来半幅画面被墙糊住（第一版就是）。
    ("S5", "S5-二层楼层平台.png",
     (_SHAFT_MID_X, _FLOOR_LANDING_Y, _STOREY + HUMAN_EYE), 270,
     "1 层楼层平台，朝出口方向——脚下这块局部楼板就是上来不掉下去的原因"),
    ("R1", "R1-底层客厅.png", (_N_ROOM_X, _N_ROOM_Y, HUMAN_EYE), 0, "0 层客厅"),
    ("R2", "R2-二层主卧.png", (_N_ROOM_X, _N_ROOM_Y, _STOREY + HUMAN_EYE), 0, "1 层主卧"),
    ("R3", "R3-三层工作间.png", (_N_ROOM_X, _N_ROOM_Y, 2 * _STOREY + HUMAN_EYE), 0,
     "2 层阁楼工作间"),
]

# ── 外景：(编号, 文件名, 相机位置, 看向哪, 说明) ──
# 用"给定机位 + 看向某点"，不是绕目标转的自由相机语义（那套容易把相机放进墙里）。
EXTERIOR = [
    ("X1", "X1-整栋外景.png", (17.0, -13.0, 9.0), (0.0, 0.8, 3.2), "整栋三层外景"),
    # ⭐ 侧立面：从梯井正东方向平视，一眼看清"踏板首尾相接、两跑靠平台连起来"
    ("X2", "X2-从门口平视楼梯.png",
     (_SHAFT_MID_X, _FLIGHT_MID_Y - 6.0, _MID_LANDING_Z + 0.6),
     (_SHAFT_MID_X, _FLIGHT_MID_Y, _MID_LANDING_Z + 0.3),
     "从楼梯间门口平视：左边是上行跑（踢面处不露缝）、中间是梯井隔墙、右边是回头跑的底面"),
    # ⭐ 顶层梯口：必须**俯视**才看得出栏板拦住的是什么，而站位镜头只能平视，
    #    所以这一张走"给定机位 + 看向某点"这一路。
    ("X3", "X3-顶层梯口栏板俯视.png",
     (_SHAFT_MID_X, _L._IN_Y0 + 0.2, 2 * _STOREY + 1.55),
     (_UP_X, _L._FLOOR_LANDING_Y1 + 0.9, 2 * _STOREY - 0.8),
     "2 层梯口往下看：西侧那条道上面没有梯段接上去了，所以用一道栏板封住"),
]
