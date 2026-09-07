"""house2 —— 三层小楼，带两组真正能走的双跑楼梯。

**为什么建它**：house1 是单层大平层，没有任何高差。人形机器人的爬楼能力、跨层导航、
以及"摔在楼梯上"这类真实失败模式，在那里一个都测不到。这个场景就是为高差建的。

**和 house1 的关系**：同一套数据模型、同一个生成器。多出来的只有几样——
每间屋写 `"floor": n`、楼层高度由 `FLOOR_Z(n)` 给、外加 `STAIRS` / `LANDINGS` /
`WELL_WALLS` / `GUARDS`。单层场景没有这些，生成器里的 `_zbase()` 就恒返回 0，
所以 house1 的产物逐字节不变。

⭐⭐ **楼梯的结构是这个文件最要紧的东西，改之前先读 `楼梯设计.md`。**
   那份文档记着这套尺寸是怎么推出来的、依据哪条规范、以及两次做错的经过。
   下面只写结论。

════════════════════════════════════════════════════════════════════════
一部双跑（U 型 / 半转）楼梯 = 五段，**其中两段是平台**
════════════════════════════════════════════════════════════════════════

    北 ↑            ┌─────────────────────────┐
                    │   ③ 中间休息平台 (半层高) │  ← 在这儿转 180°
                    ├────────────┬────────────┤
                    │ ② 上行跑 ↑ │ ④ 回头跑 ↑ │  ← 中间一道梯井隔墙
                    │  (西侧)    │  (东侧)     │
                    ├────────────┴────────────┤
                    │   ① 楼层平台 (楼面标高)   │  ← ⑤ 也是上一层的楼层平台
                    └───────────┬─────────────┘
                                门

**两块平台缺一不可。** 少了中间平台，两跑接不上（人走到上行跑顶端就没路了）；
少了楼层平台，人爬上来脚下是空的。

**判断"接没接上"只看一条**：上一段的最后一块踏板，和下一段的起始平台，
**平面上首尾相接、高度上正好差一个踢面**。四个接头都满足，楼梯必然连续——
不是靠人记得对齐，是算出来必然如此。`check_scene.py` 的 `check_joints`
与 `check_route` 会各验一遍。

⛔ **踏步块数 = 踢面数 − 1**，因为最上面那一级就是平台本身。
   这是行业标准算法（"the total number of treads is always one less than the number
   of risers because the landing is never counted under tread"）。多做一块，
   就等于在平台边上叠了一块同高的板。

⛔ **回头跑的起点是中间平台的南边缘**，不是楼梯井的北墙根。
   曾经写成北墙根：回头跑于是从人身后一米多远起步、中段悬在上行跑头顶，
   从平台看过去就是一排凌空的板子。而当时的自检**全绿**——因为它只沿单独一跑
   往下打射线，绕着走确实摸得到一条路。查"存在一条路径"证明不了"这是一部楼梯"。
"""
from __future__ import annotations

import math

from scenes.residence import Builder, material_set, interior_finish, WHITE, LINEN
from scenes import furniture as F  # noqa: E402  家具零件库住 scenes/furniture.py，所有场景共用

# ────────────────────────────────────────────────────────── 构造尺度
WALL_THICK = 0.14
DOOR_HEIGHT = 2.10
FLOOR_THICK = 0.05
CEILING_THICK = 0.10
CEILING_GROUP = 1      # ⚠️ 必须用默认可见的组（MuJoCo 默认不渲染 group 3）
CEILING_RGBA = (0.95, 0.95, 0.93, 1.0)

WINDOW_SILL_H = 0.95
WINDOW_TOP_H = 2.30
FLOOR_WINDOW_SILL = 0.06

N_FLOORS = 3

# ══════════════════════════════════════════════════════════ 楼梯参数
# 依据《住宅设计规范》GB 50096-2011 §6.3：
#   踏步宽 ≥0.26 m、踢面 ≤0.175 m、梯段净宽 ≥1.10 m、
#   平台净宽 ≥ 梯段净宽且 ≥1.20 m、梯段净高 ≥2.20 m、扶手高 ≥0.90 m。
# 每一条 check_scene.py 都会复核，改坏了当场红。

STEP_RISE = 0.16       # 踢面。规范上限 0.175 以下；配 0.30 踏面得 2R+G = 0.62，
                       # 正落在"走着舒服"的 0.60–0.66 区间中央
STEP_RUN = 0.30        # 踏面。规范下限 0.26；宇树 G1 脚长约 0.25 m，必须留真余量
STEP_WIDTH = 1.20      # 梯段净宽。规范 ≥1.10
LANDING_DEPTH = 1.40   # 两块平台的进深。规范 ≥ 梯段净宽且 ≥1.20

RISERS_PER_FLIGHT = 9  # ⭐ 一跑的**踢面数**（不是踏板数！）。层高由它反推
TREADS_PER_FLIGHT = RISERS_PER_FLIGHT - 1   # = 8 块实体踏板，第 9 级就是平台

# ⭐ 梯段板厚。每一级是一块**厚板**，顶面就是踏面——不是从楼层地面填上来的实心块。
#    ⛔ 板厚必须 > 踢面，否则相邻两级不再重叠，踢面处会露出缝，脚会踩进去。
#    做成厚板后底面跟着坡度斜下去，头顶净空处处相等 = 层高 − 板厚。
STEP_SLAB = 0.25
STEP_FRICTION = 1.0    # ⭐ 有意留的旋钮：上楼滑不滑是想扫的变量
STEP_RGBA = (0.72, 0.63, 0.50, 1.0)
STEP_MAT = "h2_oak"
LANDING_THICK = 0.10   # 中间平台的板厚（它是块楼板，不是踏步）

RAIL_HEIGHT = 0.95     # 扶手高出踏面中线。规范 ≥0.90
RAIL_THICK = 0.06
RAIL_RGBA = (0.19, 0.20, 0.19, 1.0)

# 梯井隔墙：两跑之间那道墙。
# ⛔ 这里**不留空槽**。真实楼梯的梯井常留 0.1–0.2 m 的缝，但那种缝正好能卡住
#    机器人的脚（G1 脚宽约 0.10 m）；而且两条道高差最大到 1.28 m，一侧踏空就是摔。
#    做成实墙：既没有缝，又给扶手一个安装面。
WELL_WALL_THICK = 0.12
WELL_WALL_RGBA = (0.86, 0.84, 0.81, 1.0)
WELL_WALL_MAT = "mat_wall"

# ── 层高：从楼梯推出来，⛔ 别倒过来先定层高再配楼梯 ──────────────────
# 一层的总高 **等于** 一组楼梯（两跑）爬的高度。这样"楼梯顶正好落在上一层地面"
# 是算出来的，不是靠人记得两处对齐。
# 前作那栋两层小楼正是栽在反过来做：层高与楼梯各自定死，顶步悬空 20 cm。
STOREY_H = 2 * RISERS_PER_FLIGHT * STEP_RISE            # = 18 × 0.16 = 2.88 m
WALL_HEIGHT = STOREY_H - CEILING_THICK - FLOOR_THICK    # 室内净高 = 2.73 m

# 头顶净空 = 层高 − 梯段板厚。两跑各占一条道、上下层同一条道相隔正好一个层高，
# 所以净空处处相等，不会"越走越矮"。
STAIR_HEADROOM = STOREY_H - STEP_SLAB                   # = 2.63 m > 规范 2.20


def FLOOR_Z(floor: int) -> float:
    """第 n 层地面的世界高度（0 层 = 0.0）。生成器按这个把每层抬上去。"""
    return floor * STOREY_H


# ── 楼梯井净尺寸：也是推出来的 ────────────────────────────────────────
# 净宽 = 两条梯段 + 中间那道隔墙
# 净深 = 楼层平台 + 梯段水平投影 + 中间平台
#        ⚠️ 梯段水平投影是 **(踢面数−1) × 踏面**，因为最上面一级是平台
_SHAFT_W = 2 * STEP_WIDTH + WELL_WALL_THICK                  # = 2.52 m
_SHAFT_D = 2 * LANDING_DEPTH + TREADS_PER_FLIGHT * STEP_RUN  # = 2.80 + 2.40 = 5.20 m

# 楼梯井贴着房子东北角。外框 = 净尺寸 + 四面墙（墙心压在矩形边上，每边占一整个墙厚）
STAIR_X1 = 6.0                                          # 东外墙 = 房子东边界
STAIR_X0 = STAIR_X1 - (_SHAFT_W + 2 * WALL_THICK)       # = 3.20
STAIR_Y0 = 0.6                                          # 南隔墙 = 南北两条房间带的分界
STAIR_Y1 = STAIR_Y0 + _SHAFT_D + 2 * WALL_THICK         # = 6.08

# ⭐ 房子的北边界**由楼梯定**。一部合规双跑楼梯就是要 5.2 m 进深，房子得让位。
NORTH_Y = 17.5
SOUTH_Y = -4.5
WEST_X = -15.0
EAST_X = 15.0

# 净空（内缩**整个**墙厚，不是半个：墙体占据 [边, 边±t] 一整条）
_IN_X0, _IN_X1 = STAIR_X0 + WALL_THICK, STAIR_X1 - WALL_THICK   # 3.34 … 5.86
_IN_Y0, _IN_Y1 = STAIR_Y0 + WALL_THICK, STAIR_Y1 - WALL_THICK   # 0.74 … 5.94

_UP_X = _IN_X0 + STEP_WIDTH / 2.0        # 上行跑中心线（西侧车道）= 3.94
_DOWN_X = _IN_X1 - STEP_WIDTH / 2.0      # 回头跑中心线（东侧车道）= 5.26
_WELL_X = (_IN_X0 + _IN_X1) / 2.0        # 梯井隔墙中心 = 4.60

# 三段 y 分界：楼层平台 → 梯段 → 中间平台
_FLOOR_LANDING_Y1 = _IN_Y0 + LANDING_DEPTH                       # 2.14
_MID_LANDING_Y0 = _FLOOR_LANDING_Y1 + TREADS_PER_FLIGHT * STEP_RUN  # 4.54

# 硬约束：算不上就启动即失败，宁可不生成，也别生成一部走不了的楼梯
assert abs((_MID_LANDING_Y0 + LANDING_DEPTH) - _IN_Y1) < 1e-9, "楼梯井进深和三段之和对不上"
assert LANDING_DEPTH >= max(STEP_WIDTH, 1.20), "平台进深小于梯段净宽或规范下限 1.20 m"
assert STEP_RISE <= 0.175 and STEP_RUN >= 0.26, "踏步尺寸超出 GB 50096 的范围"
assert STAIR_HEADROOM >= 2.20, f"梯段净高只有 {STAIR_HEADROOM:.2f} m，低于规范 2.20 m"

# 楼层平台的矩形（通宽一条南端带）。0 层不用它——那层整间屋都是实地；
# 1/2 层只铺这一块，其余留空给下面的梯段升上来。
# ⚠️ 三条边取**房间矩形**的边（不是净空边）：楼板本来就该压到墙心，和隔壁屋的楼板
#    严丝合缝地接上。第一版取净空边，于是门槛底下留了一条 0.14 m 宽的裂缝——
#    从楼上走出楼梯间那一步正好踩空。只有北边取净空里的梯段起跑线。
FLOOR_LANDING_RECT = (STAIR_X0, STAIR_Y0, STAIR_X1, _FLOOR_LANDING_Y1)

# 房间坐标仍是唯一真相源；三层主楼、真实宅地和远景分别声明。
B = Builder("h2")
TEXTURES_EXTRA, MATERIALS_EXTRA = material_set("h2")
DOOR_HEIGHT = 2.25
DOOR_FRAME_THICK = .065
DOOR_FRAME_RGBA = (.24,.24,.22,1)
WINDOW_FRAME_T = .045
WINDOW_FRAME_RGBA = (.18,.20,.20,1)
ART_FRAME_T = .035
ART_FRAME_RGBA = (.22,.20,.17,1)
GLASS_RGBA = (.72,.85,.90,.13)
GLASS_THICK = .018
STEP_MAT = "h2_oak"
WELL_WALL_MAT = "h2_plaster"
ROOMS = {}

def room(key, label, rect, floor, **extra):
    ROOMS[key] = dict(label=label,rect=rect,floor=floor,wall_rgba=WHITE,
                     floor_rgba=(1,1,1,1),wall_mat="h2_plaster",floor_mat="h2_oak",**extra)

# 一层：门厅与服务带、日常起居带、朝花园的公共起居带。
room("guest", "客房", (-15,-4.5,-6,.6),0)
room("entry", "门厅", (-6,-4.5,3.2,.6),0)
room("lobby0", "楼梯前厅", (3.2,-4.5,6,.6),0)
room("robot_home", "机器人停机房", (6,-4.5,10,.6),0)
room("laundry", "洗衣间", (10,-4.5,15,.6),0)
room("living_room", "客厅", (-15,.6,-6,6.08),0)
room("dining", "餐厅", (-6,.6,3.2,6.08),0)
room("kitchen", "厨房", (6,.6,15,6.08),0)
room("family_room", "花园起居室", (-15,6.08,-3,17.5),0)
room("gallery", "花园廊厅", (-3,6.08,6,17.5),0)
room("garden_room", "休闲厅", (6,6.08,15,17.5),0)
# 二层：保留楼梯核心，重新组织完整套间与工作区。
room("bedroom", "客卧", (-15,-4.5,-6,.6),1)
room("study", "书房", (-6,-4.5,3.2,.6),1)
room("lobby1", "二层前厅", (3.2,-4.5,6,.6),1)
room("bathroom", "客卫", (6,-4.5,15,.6),1)
room("bedroom_w", "西侧卧室", (-15,.6,-6,6.08),1)
room("family_lounge", "家庭厅", (-6,.6,3.2,6.08),1)
room("dressing", "衣帽间", (6,.6,15,6.08),1)
room("master_bedroom", "主卧", (-15,6.08,-3,17.5),1)
room("master_lounge", "主卧起居室", (-3,6.08,6,17.5),1)
room("master_bath", "主卫", (6,6.08,15,17.5),1)
# 三层退台，楼梯外壳尺寸保持一致。
room("lobby2", "观景前厅", (-11,-1,11,.6),2)
room("studio", "工作室", (-11,.6,3.2,6.08),2)
room("gym", "健身房", (6,.6,11,6.08),2)
room("sky_lounge", "观景休闲厅", (-11,6.08,0,15),2)
room("library", "阅读室", (0,6.08,11,15),2)
for f in range(N_FLOORS):
    extra = dict(no_ceiling=f < N_FLOORS-1)
    if f: extra['floor_rects']=[FLOOR_LANDING_RECT]
    room(f"stair_f{f}",f"{f+1}层楼梯间",(STAIR_X0,STAIR_Y0,STAIR_X1,STAIR_Y1),f,**extra)

# The estate foundation, exterior trim and windows read these same room bounds.
BUILDING_FOOTPRINTS=[]
for floor in range(N_FLOORS):
    rects=[r['rect'] for r in ROOMS.values() if r['floor']==floor]
    BUILDING_FOOTPRINTS.append((min(r[0] for r in rects),min(r[1] for r in rects),
                               max(r[2] for r in rects),max(r[3] for r in rects)))

DOORS=[]
# 相邻房间从共享边界计算门位置，楼层显式声明，绝不在上层意外开外门。
for ka,a in ROOMS.items():
    ax,ay,bx,by=a['rect']; f=a['floor']
    for kb,b in ROOMS.items():
        if kb<=ka or b['floor']!=f: continue
        cx,cy,dx,dy=b['rect']
        if abs(bx-cx)<1e-6 or abs(dx-ax)<1e-6:
            lo,hi=max(ay,cy),min(by,dy)
            if hi-lo<1.5: continue
            fixed=bx if abs(bx-cx)<1e-6 else ax
            # 梯间只能从南侧楼层平台进入，侧边是正在上升的梯段。
            if ka.startswith('stair') or kb.startswith('stair'): continue
            orient='v'
        elif abs(by-cy)<1e-6 or abs(dy-ay)<1e-6:
            lo,hi=max(ax,cx),min(bx,dx)
            if hi-lo<1.5: continue
            fixed=by if abs(by-cy)<1e-6 else ay
            if (ka.startswith('stair') or kb.startswith('stair')) and abs(fixed-STAIR_Y0)>1e-6: continue
            orient='h'
        else: continue
        width=min(2.4,hi-lo-.5)
        center=(lo+hi)/2
        if orient=='h' and hi-lo>4:
            width=1.8; center=hi-1.6
        if ka.startswith('stair') or kb.startswith('stair'): width=1.2; center=(lo+hi)/2
        DOORS.append(dict(orient=orient,coord=fixed,center=center,width=width,kind='door',floor=f,note=f'{ka}-{kb}'))
# Ground-floor public rooms form a connected living suite around the stair core.
_PUBLIC={'entry','living_room','dining','family_room','gallery','garden_room'}
for d in DOORS:
    ka,kb=d['note'].split('-')
    if d['floor']==0 and ka in _PUBLIC and kb in _PUBLIC:
        a,b=ROOMS[ka]['rect'],ROOMS[kb]['rect']; axis=0 if d['orient']=='h' else 1
        lo,hi=max(a[axis],b[axis]),min(a[axis+2],b[axis+2])
        d.update(center=(lo+hi)/2,width=hi-lo-.6,kind='open')
_STAIR_DOOR_X=_WELL_X
ENTRY_X=-1.4
DOORS.append(dict(orient='h',coord=SOUTH_Y,center=ENTRY_X,width=2.0,kind='door',floor=0,note='entry-forecourt'))
DOORS.append(dict(orient='v',coord=EAST_X,center=2.6,width=2.2,kind='door',floor=0,note='kitchen-pool_terrace'))
DOORS.append(dict(orient='h',coord=-1.,center=0.,width=2.,kind='door',floor=2,note='lobby2-view_terrace'))
DOORS.append(dict(orient='v',coord=WEST_X,center=3.6,width=2.,kind='door',floor=0,note='living_room-west_walk'))
FRONT_DOOR=dict(room='entry',side='s',center=ENTRY_X,width=2.,height=DOOR_HEIGHT,
                state='fixed_open',open_angle=90,mat='h2_walnut',rgba=WHITE,
                casing_mat='h2_stone',casing_rgba=WHITE,handle_mat='h2_metal',handle_rgba=WHITE)
WINDOWS=[]
for key,r in ROOMS.items():
    x0,y0,x1,y1=r['rect']; f=r['floor']
    bounds=BUILDING_FOOTPRINTS[f]
    for side,fixed,edge,lo,hi in [('w',x0,bounds[0],y0,y1),('s',y0,bounds[1],x0,x1),
                                   ('e',x1,bounds[2],y0,y1),('n',y1,bounds[3],x0,x1)]:
        if abs(fixed-edge)>1e-6 or key in ('entry','lobby2') and side=='s': continue
        # 一层厨房东侧保留实际出入口。
        if key=='kitchen' and side=='e' or key=='living_room' and side=='w': continue
        width=min(3.7,(hi-lo)*.60)
        if width<.8: continue
        WINDOWS.append(dict(room=key,side=side,center=(lo+hi)/2,width=width,sill=.16,top=WALL_HEIGHT-.18,glass=True))
START_POS_XY=(ENTRY_X,-2.5)
START_YAW=math.pi/2
ROBOT_HOME_XY=(8.,-2.7)
ROBOT_HOME_YAW=math.pi/2
ROBOT_HOME_FLOOR=0
FLOOR_ENTRIES={f:((_WELL_X,STAIR_Y0-.55),FLOOR_Z(f)) for f in range(N_FLOORS)}

# ══════════════════════════════════════════════════════════ 楼梯本体
# 每一跑写三样：**起跑线 = 它下面那块平台的边缘**、前进方向、起始标高。
#   `risers` 是踢面数；生成器出 `risers − 1` 块踏板，第 risers 级由平台充当。
STAIRS: list[dict] = []
LANDINGS: list[dict] = []
GUARDS: list[dict] = []

_HALF_STOREY = RISERS_PER_FLIGHT * STEP_RISE     # 1.44 m = 中间平台的标高

for _f in range(N_FLOORS - 1):                   # 0→1、1→2 各一组
    _base = FLOOR_Z(_f)
    # ② 上行跑：从**楼层平台的北缘**起步，往北爬到中间平台
    STAIRS.append({
        "name": f"stair{_f}_up", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_UP_X, _FLOOR_LANDING_Y1), "dir": (0.0, 1.0), "base_z": _base,
        # 靠西墙，敞开侧在东边（对着梯井隔墙）→ 扶手装在 +x 侧
        "rail_side": +1,
    })
    # ③ 中间休息平台：通宽，北端，顶面标高 = 半层
    LANDINGS.append({
        "name": f"stair{_f}_mid",
        "pos": ((_IN_X0 + _IN_X1) / 2.0,
                (_MID_LANDING_Y0 + _IN_Y1) / 2.0,
                _base + _HALF_STOREY - LANDING_THICK / 2.0),
        "size": (_IN_X1 - _IN_X0, _IN_Y1 - _MID_LANDING_Y0, LANDING_THICK),
    })
    # ④ 回头跑：⛔ 从**中间平台的南缘**起步（不是北墙根！），往南爬到上一层
    STAIRS.append({
        "name": f"stair{_f}_dn", "risers": RISERS_PER_FLIGHT, "width": STEP_WIDTH,
        "start_xy": (_DOWN_X, _MID_LANDING_Y0), "dir": (0.0, -1.0),
        "base_z": _base + _HALF_STOREY,
        # 靠东墙，敞开侧在西边 → 扶手装在 -x 侧。
        # ⚠️ rail_side 是**世界坐标轴**的符号，与前进方向无关。
        "rail_side": -1,
    })

# 梯井隔墙：只在梯段那一段（两块平台之间）立墙，通高到顶层天花板。
# 平台段不立——那儿正是转身的地方。
WELL_WALLS: list[dict] = [{
    "name": "stair_well_wall",
    "pos": (_WELL_X, (_FLOOR_LANDING_Y1 + _MID_LANDING_Y0) / 2.0,
            (FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT) / 2.0),
    "size": (WELL_WALL_THICK, _MID_LANDING_Y0 - _FLOOR_LANDING_Y1,
             FLOOR_Z(N_FLOORS - 1) + WALL_HEIGHT),
}]

# ⭐ 顶层梯口护栏：顶层西侧车道上面没有梯段接上去了，那里是个直通下面的洞
#    （从顶层楼面到下面一跑的踏面差 2.7 m）。真实楼梯这儿一定是围栏。
#    东侧车道**不用**围——那是下楼的口，人就是从那儿下去的。
#
# ⛔ 做成**实心矮墙**（栏板），不是两根横杆。两个理由：
#    ① 机器人会从杆缝里钻过去/卡进去，栏板才是真拦得住的；
#    ② 自检只能横着打射线找实体，两根细杆要求射线高度正好对上杆心——
#       那等于把检查绑死在某一版护栏的造型上，换个造型检查就假绿。
GUARD_HEIGHT = 1.05        # 规范：临空处栏板/栏杆净高不低于 1.05 m
GUARD_THICK = WELL_WALL_THICK
GUARDS.append({
    "name": "stair_top_guard",
    "pos": (_UP_X, _FLOOR_LANDING_Y1 + GUARD_THICK / 2.0,
            FLOOR_Z(N_FLOORS - 1) + GUARD_HEIGHT / 2.0),
    "size": (STEP_WIDTH, GUARD_THICK, GUARD_HEIGHT),
})

# ── 四个接头的自检（几何一算就知道，不用等 MuJoCo）─────────────────────
# 上一段最后一块踏板的顶面，与下一段起始平台，必须差正好一个踢面。
_last_tread_top = TREADS_PER_FLIGHT * STEP_RISE
assert abs((_HALF_STOREY - _last_tread_top) - STEP_RISE) < 1e-9, \
    "上行跑顶端到中间平台不是一个踢面 —— 楼梯断了"
assert abs((STOREY_H - (_HALF_STOREY + _last_tread_top)) - STEP_RISE) < 1e-9, \
    "回头跑顶端到上一层楼面不是一个踢面 —— 楼梯断了"


FURNITURE=[]
for key in ('guest','bedroom','bedroom_w','master_bedroom'):
    x0,y0,x1,y1=ROOMS[key]['rect']
    FURNITURE+=B.bed(key,key,x0+2.1,y1-1.55)
for key in ('living_room','family_room','family_lounge','garden_room','master_lounge','sky_lounge'):
    x0,y0,x1,y1=ROOMS[key]['rect']; x=x0+2.0; y=(y0+y1)/2
    FURNITURE+=B.sofa(key,key,x,y,width=2.9)
    FURNITURE+=F.mesh_piece('h2_'+key+'_coffee',key,x+1.5,y,size=(1.05,1.05,.397),mesh='coffee_table',collide=True)
    FURNITURE+=F.mesh_piece('h2_'+key+'_armchair',key,x+3.0,y-1.6,size=(.82,.987,1.023),mesh='armchair',collide=True,yaw=0)
    FURNITURE+=B.cabinet(key+'_console',key,x1-1.0,y,2.2,.52,.65,yaw=90)
for key in ('study','studio','library'):
    x0,y0,x1,y1=ROOMS[key]['rect']; x=x0+2.;y=y1-1.5
    FURNITURE+=F.table('h2_'+key+'_desk',key,x,y,2.1,.9,mat='h2_walnut')
    FURNITURE+=F.chair('h2_'+key+'_chair',key,x,y-1.,yaw=90,mat='h2_oak')
    FURNITURE+=B.cabinet(key+'_library',key,x1-1.2,y,2.2,.45,1.6,yaw=90)
    FURNITURE+=F.books_stack('h2_'+key+'_books',key,x+.5,y,.77)
# 餐厅长桌、六把真碰撞椅。
FURNITURE+=F.table('h2_dining_table','dining',-1.4,3.4,3.2,1.1,mat='h2_oak')
for i,x in enumerate((-2.5,-1.4,-.3)):
    for side in (-1,1):
        FURNITURE+=F.mesh_piece(f'h2_dining_chair{i}_{side}','dining',x,3.4+side*.95,
            size=(.434,.576,.973),mesh='dining_chair',yaw=0 if side==1 else 180,collide=True)
FURNITURE+=B.cabinet('kitchen_wall_left','kitchen',9.,5.45,1.7,.68,.90)
FURNITURE+=B.cabinet('kitchen_wall_right','kitchen',11.2,5.45,1.7,.68,.90)
FURNITURE+=B.cabinet('kitchen_island','kitchen',11.,3.,3.6,1.1,.92)
FURNITURE+=F.mesh_piece('h2_fridge','kitchen',14.3,5.1,size=(.916,.856,1.892),mesh='rc_fridge')
FURNITURE+=F.mesh_piece('h2_sink','kitchen',9.,5.35,z=1.09,size=(.775,.424,.408),mesh='rc_sink')
# Cut the stone counter around the actual sink envelope, retaining the basin.
FURNITURE=[it for it in FURNITURE if it['name']!='h2_kitchen_wall_left_top']
_SINK_X,_SINK_Y=9.,5.35
_COUNTER=(8.1325,5.0875,9.8675,5.8125)
_HOLE=(_SINK_X-.395,_SINK_Y-.22,_SINK_X+.395,_SINK_Y+.22)
_a,_b,_c,_d=_COUNTER;_e,_f,_g,_h=_HOLE
for i,(a,b,c,d) in enumerate([(_a,_b,_e,_d),(_g,_b,_c,_d),(_e,_b,_g,_f),(_e,_h,_g,_d)]):
    FURNITURE.append(B.box(f'kitchen_sink_counter{i}',((a+c)/2,(b+d)/2,.90),(c-a,d-b,.045),'stone',room='kitchen',radius=.006))
FURNITURE+=F.mesh_piece('h2_stove','kitchen',12.7,5.25,size=(.761,.704,1.133),mesh='rc_stove')
for key in ('bathroom','master_bath','laundry','dressing'):
    x0,y0,x1,y1=ROOMS[key]['rect']
    FURNITURE+=B.cabinet(key+'_cab',key,(x0+x1)/2,y1-.7,2.2,.65,.85 if 'bath' in key else 1.8)
    if 'bath' in key:
        # 空心浴缸：底板、四面侧壁，而不是实心白砖。
        x,y=x1-1.11,y0+1.6
        for tag,dx,dy,z,size in [('base',0,0,.15,(1.9,.9,.18)),('l',-.92,0,.35,(.10,.95,.5)),
             ('r',.92,0,.35,(.10,.95,.5)),('n',0,.43,.35,(1.8,.10,.5)),('s',0,-.43,.35,(1.8,.10,.5))]:
            fixture=B.box(key+'_tub_'+tag,(x+dx,y+dy,z),size,'ceramic',room=key,radius=.045)
            if tag=='base': fixture['enclosed_fixture']=True
            FURNITURE.append(fixture)
# 跑步机框架与跑带；不增加控制器或执行器。
FURNITURE.append(B.box('treadmill_base',(9.,3.5,.12),(1.,2.1,.16),'metal',room='gym',radius=.05))
for x in (8.52,9.48):
    FURNITURE.append(B.box('treadmill_upright'+str(x),(x,4.2,.68),(.065,.065,1.2),'metal',room='gym'))
FURNITURE.append(B.box('treadmill_panel',(9.,4.2,1.29),(1.,.24,.06),'metal',room='gym'))
for item in FURNITURE: B.detail(item,.025,1.2)
WALL_ARTS=[]
from types import SimpleNamespace as _Namespace
ARCHITECTURE=interior_finish(_Namespace(**globals()),B)
from scenes.house2.estate import build_estate
EXTERIOR_GEOMS,EXTERIOR_AREAS,BACKGROUND_GEOMS,ESTATE=build_estate(B,FLOOR_Z,STOREY_H,BUILDING_FOOTPRINTS)
TEXTURES_EXTRA += [ESTATE['grass_texture'],dict(name='h2_tex_pool',type='2d',file='textures/residences/pool_tile.png',colorspace='sRGB')]
MATERIALS_EXTRA += [dict(name='h2_grass',texture='h2_tex_grass',specular=.015,shininess=.05),
                    dict(name='h2_pool_tile',texture='h2_tex_pool',specular=.25,shininess=.4),
                    dict(name='h2_road',rgba='.30 .31 .29 1',specular=.02,shininess=.1)]
RES_MESHES=B.meshes
CITY_BACKDROP=None
SKYBOX={f'file{side}':f'textures/house3/sky_file{side}.png'
        for side in ('right','left','up','down','front','back')}
OUTDOOR_GROUND=None
TREES=[]
BUILDINGS=[]
TRUNK_RGBA=(.32,.26,.18,1)
FOLIAGE_RGBA=(.24,.36,.16,1)
PHYSICAL_WALKTHROUGH=True
LIGHT_BUDGET=7
LIGHTS=[dict(name='h2_sun',pos='-30 -45 60',dir='.35 .45 -.82',directional='true',
             diffuse='.48 .47 .45',specular='.18 .17 .14',castshadow='true')]
for floor in range(N_FLOORS):
    for wing,x in [('west',-7.),('east',8.)]:
        LIGHTS.append(dict(name=f'h2_fill_{floor}_{wing}',pos=f'{x} 6 {FLOOR_Z(floor)+WALL_HEIGHT-.20}',
            dir='0 0 -1',diffuse='.12 .12 .115',ambient='.095 .095 .09',specular='.04 .04 .04',
            attenuation='1 0 .02',castshadow='false'))
STATISTIC=dict(center='0 0 3',extent=12)
VISUAL=dict(znear=.001,zfar=120,shadowclip=4,shadowsize=2048,
            headlight_diffuse='.32 .32 .31',headlight_ambient='.43 .43 .42',headlight_specular='.04 .04 .04')
DECOR_MATERIAL_OVERRIDES={'armchair':{'1':dict(texture=None,rgba='.78 .74 .66 1',specular=.035,shininess=.10),
                                    '0':dict(specular=.2,shininess=.3)},
                          'dining_chair':{'all':dict(texture=None,rgba='.70 .63 .52 1',specular=.12,shininess=.24)}}

def floor_at(z):
    return max(0,min(N_FLOORS-1,int((z+.30)//STOREY_H)))

def room_at(x,y,z=None):
    floor=0 if z is None else floor_at(z)
    for key,r in ROOMS.items():
        a,b,c,d=r['rect']
        if r['floor']==floor and a<=x<=c and b<=y<=d: return key
    px,py,qx,qy=ESTATE['pool']
    if px<x<qx and py<y<qy and (z or 0)<STOREY_H: return 'swimming_pool'
    for area in EXTERIOR_AREAS:
        a,b,c,d=area['rect']
        if area['floor_z']-.3 <= (z or 0) < area['floor_z']+STOREY_H-.1 and a<=x<=c and b<=y<=d: return area['name']
    return None

def room_label(key):
    if key in ROOMS: return ROOMS[key]['label']
    if key=='swimming_pool': return '泳池'
    return next((a['label'] for a in EXTERIOR_AREAS if a['name']==key),'宅地外')

def stair_route(floor: int) -> list[tuple[float, float, float]]:
    """从第 `floor` 层走到第 `floor+1` 层的完整路线（世界坐标折线的拐点）。

    ⭐ 这是"楼梯到底连不连"的唯一权威描述：check_scene.py 沿着它逐点往下打射线，
    要求一路有实地、相邻高差不超过一个踢面。**别在别处再写一份**——
    上一版的 bug 正是"平台在一处、回头跑起点在另一处"，两处各写各的没人对得上。

    返回的每个点是 (x, y, 该点脚下应有的标高)。
    """
    base = FLOOR_Z(floor)
    return [
        # ① 楼层平台上，正对上行跑
        (_UP_X, _IN_Y0 + 0.25, base),
        # ② 上行跑起步线
        (_UP_X, _FLOOR_LANDING_Y1, base),
        # ③ 爬到中间平台的南缘（此处脚下已是平台标高）
        (_UP_X, _MID_LANDING_Y0, base + _HALF_STOREY),
        # ④ 在中间平台上横移到回头跑那条道（平台通宽，隔墙到此为止）
        (_UP_X, _IN_Y1 - 0.55, base + _HALF_STOREY),
        (_DOWN_X, _IN_Y1 - 0.55, base + _HALF_STOREY),
        # ⑤ 回到回头跑的起步线
        (_DOWN_X, _MID_LANDING_Y0, base + _HALF_STOREY),
        # ⑥ 爬到上一层的楼层平台
        (_DOWN_X, _FLOOR_LANDING_Y1, base + STOREY_H),
        # ⑦ 走到门口
        (_STAIR_DOOR_X, _IN_Y0 + 0.25, base + STOREY_H),
    ]


STAIR_SLOPE_DEG = math.degrees(math.atan2(STEP_RISE, STEP_RUN))
