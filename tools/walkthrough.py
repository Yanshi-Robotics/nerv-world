#!/usr/bin/env python3
"""第一人称漫游 —— 像玩 Minecraft 那样走进屋里看。

    python tools/walkthrough.py                      # 默认场景
    python tools/walkthrough.py --scene house       # 三层小楼，可以踩着楼梯上楼
    python tools/walkthrough.py --scene house --fly # 飞行模式（穿墙、自由升降）
    python tools/walkthrough.py --mouse-sens 40      # 鼠标转视角调慢一点

鼠标转头，WASD 走路，空格跳，Shift 跑。默认是**走路模式**：脚下踩实、撞墙走不过去、
台阶自动迈上去——所以楼梯是真能一级一级走上三楼的，不是飞上去。

    鼠标        转头（光标已锁进窗口，按 Esc 放出来）
                （嫌快/嫌慢：--mouse-sens <度>，默认 77 = 横扫满窗口转 77°）
    W A S D     前进 / 左移 / 后退 / 右移
    空格        跳
    Shift       按住跑
    F           飞行模式开关（飞行时穿墙，用来快速看全貌）
    T           透视开关（把所有东西变半透明，隔着墙看结构）
    R / Ctrl    飞行模式下升 / 降
    1 2 3 …     跳到第 N 层的出生点
    Tab         回出生点
    C           天花板开关（想俯瞰时关掉）
    P           打印当前坐标与所在房间
    Esc         放开鼠标（再点窗口收回）
    Q           退出

**为什么不用 `python -m mujoco.viewer`**：那个自带 viewer 的相机是"绕着一个目标点转"的
轨道语义，想进屋里看得一边转一边缩距离，很难落到某个房间中间，更别说在三层楼里上下。
这里自己开窗口，就为了拿到鼠标——FPS 的手感全在鼠标上。

普通场景只做 mj_forward；apt 的交互模式会推进家具物理。检查器中的机器人保持停机姿态，
不会自己走。视角行走的碰撞由射线计算，不是 MuJoCo 玩家刚体。
"""
from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
#    这条规矩是为了 review 时一眼看得出有没有漏改：任何落点错误都会在
#    tools/ 下长出一个目录（`ls tools/ | grep -v '\.py$'` 必须为空）。
sys.path.insert(0, ROOT)

from scenes import manifest as SCENES  # noqa: E402

# 机器人清单住仓根的 robots/manifest.py（跨场景共用），按路径加载——仓根不是包，import 不到。
# ⭐ 和 tools/make_house.py 用的是同一份、同一种加载方式，⛔ 别在这里另抄一份出生高度。
import importlib.util  # noqa: E402
_rspec = importlib.util.spec_from_file_location(
    "alice_robots_wt", os.path.join(ROOT, "robots", "manifest.py"))
ROBOTS = importlib.util.module_from_spec(_rspec); _rspec.loader.exec_module(ROBOTS)

# 眼高与 robots/manifest.py 里那两台机器人的实际相机高度一致。
EYE_HUMAN = 1.25
EYE_DOG = 0.38

WALK_SPEED = 2.4        # m/s，常速走
RUN_MULT = 2.2          # 按住 Shift 的倍率
FLY_SPEED = 4.5         # m/s，飞行模式
# ⭐ 鼠标灵敏度：单位是「鼠标横扫**整个窗口宽度**转多少度」，⛔ 不是"度/像素"。
#    2026-08-08 改的，两件事一起：
#    ① **默认减半**（原来 0.12 度/像素 × 1280 px 窗口 = 满窗扫一下转 154°，Jeff 嫌太飘）；
#    ② ⭐ **改成与分辨率无关**。原来按像素算，换个屏幕/换个窗口大小手感就变——
#       高分屏上同样的手部动作会多出一倍像素，转得就快一倍。按窗口宽度归一化之后，
#       "手划过屏幕一半 = 转多少度"在任何屏幕上都一样。
#    想微调用 `--mouse-sens`（数字越小越稳）。
MOUSE_SENS_DEG_PER_SCREEN = 77.0
PITCH_LIMIT = 89.0

BODY_RADIUS = 0.28      # 玩家"胖"多少：撞墙判定用的水平半径
STEP_UP_MAX = 0.30      # 能自动迈上去的台阶高度上限（house 踢面 0.16，够）

# ⭐ 撞墙探测的射线高度（相对**脚底**）。三根，**任一根命中就不让走**。
#    两端的边界是**算出来的**，不是试出来的——selftest 里有一条断言在守着：
#
#    · 下界 0.35 —— 一帧最远探到 `BODY_RADIUS + WALK_SPEED*RUN_MULT/60 = 0.368 m`，
#      在 house 的楼梯上（踏面 STEP_RUN=0.30）这段距离里地面最多升**两级**
#      = 2 × STEP_RISE(0.16) = 0.32 m。射线低于它就会打到前面第二级台阶，走两步卡死。
#      ⚠️ 实测 0.31 就已经卡在 (3.94, 4.54) 上不去了，余量只有 3 cm，别再往下调。
#      它同时 > STEP_UP_MAX(0.30)，语义上也自洽：能自动迈上去的东西不该被当成墙。
#    · 上界 1.00 —— 站在半层中间平台上时脚底在 STOREY_H/2 = 1.44 m，
#      而这一层的墙顶只到 WALL_HEIGHT = 2.73 m。射线高于 1.29 m 就从墙顶掠过去，
#      人会直接走进墙里再掉下楼（"取眼睛高度"当年踩的就是这个）。
#    · 中间 0.70 —— ⭐ 2026-08-07 加的第三根，为的是让**矮家具真的挡人**：
#      茶几 0.50 / 长凳 0.44 / 餐桌 0.75 / 床 0.82 / 台面 0.92 全都矮于 1.0 m，
#      以前一根胸口射线从它们头顶掠过去，人直接穿桌而过——于是走一圈下来会误以为
#      "这些柜子没有碰撞"。**场景的碰撞一直是对的**（家具全是 contype=1），
#      错的是这个漫游工具的探路方式。
#    ⚠️ 代价是可能被椅子腿卡住。那是真实情况，卡住按 F 飞过去即可。
PROBE_HS = (0.35, 0.70, 1.00)
PROBE_H = PROBE_HS[-1]  # 兼容旧引用；新代码一律用 PROBE_HS
GRAVITY = 9.8
JUMP_V = 3.2


class Player:
    """玩家状态与移动规则。抽出来是为了能在无窗口环境下自测方向和碰撞。"""

    def __init__(self, layout, eye_h: float, floor: int = 0, fly: bool = False,
                 mouse_sens: float = MOUSE_SENS_DEG_PER_SCREEN, screen_w: float = 1280.0):
        self.layout = layout
        self.eye_h = eye_h
        self.fly = fly
        self.mouse_sens = mouse_sens     # 满窗横扫转多少度
        self.screen_w = screen_w         # 当前窗口宽度(px)，开窗后会被实际值覆盖
        self.yaw = math.degrees(getattr(layout, "START_YAW", 0.0))
        self.pitch = 0.0
        self.vz = 0.0
        self.on_ground = False
        self.goto_floor(floor)
        self._last_room = object()

    # ── 位置 ────────────────────────────────────────────────────────────
    def goto_floor(self, floor: int) -> None:
        x, y = self.layout.START_POS_XY
        floor_z = getattr(self.layout, "FLOOR_Z", None)
        base = float(floor_z(floor)) if floor_z else 0.0
        if floor in getattr(self.layout, 'FLOOR_ENTRIES', {}):
            (x, y), base = self.layout.FLOOR_ENTRIES[floor]
        self.feet = [x, y, base + 0.02]     # 脚底位置；眼睛在它上面 eye_h
        self.vz = 0.0

    @property
    def eye(self) -> list[float]:
        return [self.feet[0], self.feet[1], self.feet[2] + self.eye_h]

    @property
    def forward(self) -> tuple[float, float, float]:
        """视线方向。与 MuJoCo 自由相机同一套约定：
        forward = (cos(el)cos(az), cos(el)sin(az), sin(el))。"""
        a, e = math.radians(self.yaw), math.radians(self.pitch)
        return (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))

    @property
    def heading(self) -> tuple[float, float]:
        """水平前进方向——俯仰不影响走路，否则仰头一走就飞起来。"""
        a = math.radians(self.yaw)
        return (math.cos(a), math.sin(a))

    def room(self) -> str:
        fn = self.layout.room_at
        e = self.eye
        try:
            key = fn(e[0], e[1], e[2])
        except TypeError:
            key = fn(e[0], e[1])
        return self.layout.room_label(key)

    def announce_room(self) -> str | None:
        room = self.room()
        if room != self._last_room:
            self._last_room = room
            return room
        return None

    # ── 视角 ────────────────────────────────────────────────────────────
    def look(self, dx: float, dy: float) -> None:
        """dx/dy 是鼠标位移（像素）。⭐ 除以窗口宽度先归一化，再乘"满屏转多少度"。

        ⚠️ 俯仰用**同一个**系数（不是按窗口高度归一化）——否则窄窗口里上下比左右灵敏，
           手感会拧巴。FPS 的惯例就是两轴同灵敏度。
        """
        k = self.mouse_sens / max(1.0, self.screen_w)
        self.yaw -= dx * k
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch - dy * k))

    # ── 移动 ────────────────────────────────────────────────────────────
    def move(self, probe, ax: float, ay: float, dt: float, running: bool, up: float) -> None:
        """ax/ay = 前后/左右输入（-1..1）；probe 是一个 (起点, 方向) → 距离 的函数。"""
        hx, hy = self.heading
        # 右手边 = 前进方向顺时针 90°
        vx = hx * ax + hy * ay
        vy = hy * ax - hx * ay
        norm = math.hypot(vx, vy)
        if norm > 1e-9:
            vx, vy = vx / norm, vy / norm

        if self.fly:
            speed = FLY_SPEED * (RUN_MULT if running else 1.0)
            self.feet[0] += vx * speed * dt
            self.feet[1] += vy * speed * dt
            self.feet[2] += up * speed * dt
            self.vz = 0.0
            return

        speed = WALK_SPEED * (RUN_MULT if running else 1.0)
        if norm > 1e-9:
            self._step_horizontal(probe, vx, vy, speed * dt)
        self._settle_vertical(probe, dt)

    def _step_horizontal(self, probe, vx: float, vy: float, dist: float) -> None:
        """先探路再走：**任一根**探针在 BODY_RADIUS 内撞到东西就不动。

        ⚠️ 三根高度的取值依据见 PROBE_HS——上下界都是从 STEP_RUN/STEP_RISE 和
           WALL_HEIGHT/STOREY_H 算出来的，改楼梯参数要回去重算（selftest 会当场判红）。
        """
        for h in PROBE_HS:
            hit = probe([self.feet[0], self.feet[1], self.feet[2] + h], (vx, vy, 0.0))
            if 0.0 <= hit < BODY_RADIUS + dist:
                return
        self.feet[0] += vx * dist
        self.feet[1] += vy * dist

    def _settle_vertical(self, probe, dt: float) -> None:
        """脚下找地：从"能迈上去的最高处"往下打射线，落到实地上。"""
        top = self.feet[2] + STEP_UP_MAX
        hit = probe([self.feet[0], self.feet[1], top], (0.0, 0.0, -1.0))
        ground = None if hit < 0 else top - hit

        self.vz -= GRAVITY * dt
        self.feet[2] += self.vz * dt

        if ground is not None and self.feet[2] <= ground + 1e-4:
            self.feet[2] = ground
            self.vz = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

    def jump(self) -> None:
        if self.on_ground and not self.fly:
            self.vz = JUMP_V
            self.on_ground = False


def park_robot(m, d, layout, robot_key: str) -> None:
    """把产物里那台机器人搬到它的**停机位**（layout 的 `ROBOT_HOME_XY`，即「保姆间」）。

    ⛔ 为什么必须在运行期做：产物 XML 里的机器人站在**世界原点** —— 它的 body pos 写在
       共用的 `robots/<key>/<key>.xml` 里、被 `<include>` 原样插进来，生成器碰不到；
       而 `make_house.py` 有意不依赖 mujoco，算不出 `nq` 也就写不出 `<keyframe>`。
       **摆位本来就是运行期的事**：另一个消费方（anima-zero 的 `sim-house-nav/sim.py`）
       也是自己写 qpos 的，做法和这里一模一样。

    ⚠️ 2026-08-08 之前这一步**根本没有**，那台机器人一直杵在原点：apt1 撞进画廊长凳
       22.7 cm、house1 撞进冰箱和两面墙（96 个接触点），house 纯粹因为原点恰好是空地
       才看着正常。是 Jeff 走进去撞见了才发现的——**没有任何一项自检管过这件事**。

    ⛔ 和 `START_POS_XY` 不是一回事：那是**任务出生点**（消费方跑导航从那儿起步），
       这是**停机位**。两者有意分开，见 layout 里那段注释。
    """
    home = getattr(layout, "ROBOT_HOME_XY", None)
    if home is None:
        return
    floor = getattr(layout, "ROBOT_HOME_FLOOR", 0)
    floor_z = getattr(layout, "FLOOR_Z", None)
    base = float(floor_z(floor)) if floor_z else 0.0
    z = base + float(ROBOTS.get(robot_key)["start_height"])
    yaw = float(getattr(layout, "ROBOT_HOME_YAW", 0.0))
    d.qpos[0:3] = [home[0], home[1], z]
    d.qpos[3:7] = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]


def selftest(scene_key: str, eye_h: float) -> int:
    """无窗口自测：方向、碰撞、踩地、上楼梯。

    方向约定很容易搞反（本项目在楼梯扶手上已经栽过一次），所以不靠推理，
    全部拿射线实测。
    """
    import numpy as np
    import mujoco

    os.environ.setdefault("MUJOCO_GL", "egl")
    layout = SCENES.load_layout(scene_key)
    path = os.path.join(ROOT, SCENES.scene_filename(scene_key, "g1"))
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    park_robot(m, d, layout, "g1")
    mujoco.mj_forward(m, d)

    def probe(origin, direction) -> float:
        if getattr(layout, "PHYSICAL_WALKTHROUGH", False):
            from scenes.collision import collision_ray
            return collision_ray(m, d, origin, direction)[0]
        gid = np.zeros(1, dtype=np.int32)
        return mujoco.mj_ray(m, d, np.array(origin, dtype=float),
                             np.array(direction, dtype=float), None, 1, -1, gid)

    ok = True
    p = Player(layout, eye_h)

    # 0) 探针高度的两条边界 —— 纯算术，不打射线。
    #    ⭐ 把 PROBE_HS 那段注释里的推导变成可证的：改了楼梯参数或走速，这里会当场变红，
    #       而不是等到有人在楼梯上卡住、或者穿墙掉下楼才发现。
    rise = float(getattr(layout, "STEP_RISE", 0.0))
    run = float(getattr(layout, "STEP_RUN", 0.0))
    reach = BODY_RADIUS + WALK_SPEED * RUN_MULT / 60.0
    lo_need = math.ceil(reach / run) * rise if run > 0 else STEP_UP_MAX
    multi = getattr(layout, "N_FLOORS", 1) > 1
    hi_cap = (float(layout.WALL_HEIGHT) - float(layout.STOREY_H) / 2.0) if multi else float("inf")
    good = PROBE_HS[0] > lo_need and PROBE_HS[-1] < hi_cap
    print(f"  探针高度合法：最低 {PROBE_HS[0]:.2f} > 一帧内台阶最多升的 {lo_need:.2f} m、"
          f"最高 {PROBE_HS[-1]:.2f} < 半层平台处的墙顶 "
          f"{'∞' if hi_cap == float('inf') else f'{hi_cap:.2f}'} m {'✅' if good else '⛔'}")
    ok &= good

    # 1) 前进方向 = 视线方向
    def ahead(pl):
        return probe(pl.eye, pl.forward)
    for _ in range(60):
        if ahead(p) > 1.5:
            break
        p.yaw += 6.0
    before = ahead(p)
    p.move(probe, 1.0, 0.0, 0.2, False, 0.0)
    moved = before - ahead(p)
    good = 0.3 < moved < 0.7
    print(f"  W 朝着视线走：前方 {before:.2f} → {ahead(p):.2f} m（缩短 {moved:+.2f}）{'✅' if good else '⛔ 方向反了'}")
    ok &= good

    # 2) 撞墙挡得住
    p2 = Player(layout, eye_h)
    for _ in range(60):
        if 0 < ahead(p2) < 3.0:
            break
        p2.yaw += 6.0
    for _ in range(200):
        p2.move(probe, 1.0, 0.0, 0.05, False, 0.0)
    gap = ahead(p2)
    good = gap > 0.05
    print(f"  撞墙挡得住：一路顶着墙走 200 步后离墙 {gap:.2f} m {'✅' if good else '⛔ 穿墙了'}")
    ok &= good

    # 3) 脚下踩实（不掉穿地板）
    p3 = Player(layout, eye_h)
    for _ in range(120):
        p3.move(probe, 0.0, 0.0, 1 / 60, False, 0.0)
    base = float(layout.FLOOR_Z(0)) if hasattr(layout, "FLOOR_Z") else 0.0
    good = abs(p3.feet[2] - base) < 0.05
    print(f"  站得住：静置 2 秒后脚底 z={p3.feet[2]:.3f}（地面 {base:.3f}）{'✅' if good else '⛔ 掉下去了'}")
    ok &= good

    # 4) 多层：真的从这一层**走到上一层**
    # ⛔ 早先这里只沿"第一跑"走 400 帧看升高够不够，于是回头跑没接到平台上时它照样过。
    #    现在照 layout 给的唯一权威路线 stair_route() 一段段走完，落点必须是上一层楼面。
    if getattr(layout, "N_FLOORS", 1) > 1 and getattr(layout, "stair_route", None):
        for floor in range(layout.N_FLOORS - 1):
            pts = layout.stair_route(floor)
            p4 = Player(layout, eye_h)
            p4.feet = [pts[0][0], pts[0][1], pts[0][2] + 0.02]
            stuck = None
            for tx, ty, _tz in pts[1:]:
                for _ in range(900):
                    dx, dy = tx - p4.feet[0], ty - p4.feet[1]
                    if math.hypot(dx, dy) < 0.12:
                        break
                    p4.yaw = math.degrees(math.atan2(dy, dx))
                    p4.move(probe, 1.0, 0.0, 1 / 60, False, 0.0)
                else:
                    stuck = (tx, ty)
                    break
            target = layout.FLOOR_Z(floor + 1)
            good = stuck is None and abs(p4.feet[2] - target) < 0.10
            detail = (f"卡在去 (x={stuck[0]:.2f}, y={stuck[1]:.2f}) 的路上" if stuck
                      else f"落点 {p4.feet[2]:.3f} m（应 {target:.3f}）")
            print(f"  走得上 {floor}→{floor + 1} 层：{detail}{'✅' if good else '⛔'}")
            ok &= good

    # 5) 出生点在屋里
    p5 = Player(layout, eye_h)
    room = p5.room()
    good = room != "屋外"
    print(f"  出生点房间识别：「{room}」{'✅' if good else '⛔ 出生点在屋外'}")
    ok &= good

    print("✅ 自测通过" if ok else "⛔ 自测不通过")
    return 0 if ok else 1


def run_viewer(scene_key: str, robot: str, eye_h: float, floor: int,
               fly: bool, xray: bool = False,
               mouse_sens: float = MOUSE_SENS_DEG_PER_SCREEN) -> int:
    import glfw
    import mujoco
    import numpy as np

    layout = SCENES.load_layout(scene_key)
    path = os.path.join(ROOT, SCENES.scene_filename(scene_key, robot))
    if not os.path.exists(path):
        print(f"找不到 {os.path.basename(path)}，先生成：\n"
              f"    python tools/make_house.py --scene {scene_key} --robot {robot}", file=sys.stderr)
        return 1

    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    park_robot(m, d, layout, robot)
    mujoco.mj_forward(m, d)

    if not glfw.init():
        print("glfw 起不来——这个脚本要有显示器（远程的话记得开 X11 转发）", file=sys.stderr)
        return 1
    win_w, win_h = 1280, 800
    window = glfw.create_window(win_w, win_h, f"alice-house · {scene_key}", None, None)
    glfw.make_context_current(window)
    glfw.swap_interval(1)

    # ⚠️ 用 glfw 报的**实际**窗口宽度，不是上面那个请求值：窗口管理器可能给别的尺寸，
    #    而灵敏度是按窗口宽度归一化的，拿错数手感就不对。
    win_w = glfw.get_window_size(window)[0] or win_w
    player = Player(layout, eye_h, floor, fly, mouse_sens=mouse_sens, screen_w=float(win_w))
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)
    opt = mujoco.MjvOption()
    if xray:
        opt.flags[mujoco.mjtVisFlag.mjVIS_TRANSPARENT] = True
    scene = mujoco.MjvScene(m, maxgeom=20000)
    ctx = mujoco.MjrContext(m, mujoco.mjtFontScale.mjFONTSCALE_150)

    interaction = physics = cycle = None
    if getattr(layout, 'INTERACTIVE', False):
        from scenes.interaction import Interaction, InspectionPhysics
        interaction = Interaction(m, d)
        physics = InspectionPhysics(m, d, interaction)
        opt.geomgroup[4] = 0  # analytic collision shells are never visual surfaces
    if getattr(layout, 'LIGHTS_BY_TIME', None):
        from scenes.time_cycle import TimeCycle
        from types import SimpleNamespace
        renderer_adapter = SimpleNamespace(_mjr_context=ctx, _gl_context=SimpleNamespace(
            make_current=lambda: glfw.make_context_current(window)))
        cycle = TimeCycle(m, scene_key, renderer_adapter)

    def direction():
        yaw, pitch = np.radians([player.yaw, player.pitch])
        return np.array([np.cos(yaw)*np.cos(pitch), np.sin(yaw)*np.cos(pitch), np.sin(pitch)])

    def selection():
        return interaction.select(player.eye, direction()) if interaction else None

    state = {"last": None, "captured": True, "quit": False,
             "joint_index": 0, "grab_distance": 1.0}
    glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)

    def probe(origin, direction) -> float:
        if getattr(layout, "PHYSICAL_WALKTHROUGH", False):
            from scenes.collision import collision_ray
            return collision_ray(m, d, origin, direction)[0]
        gid = np.zeros(1, dtype=np.int32)
        return mujoco.mj_ray(m, d, np.array(origin, dtype=float),
                             np.array(direction, dtype=float), None, 1, -1, gid)

    def on_cursor(_win, x, y):
        if not state["captured"]:
            state["last"] = None
            return
        if state["last"] is not None:
            player.look(x - state["last"][0], y - state["last"][1])
        state["last"] = (x, y)

    def on_mouse_button(_win, button, action, _mods):
        if action == glfw.PRESS and not state["captured"]:
            state["captured"] = True
            state["last"] = None
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)

    def on_key(_win, key, _sc, action, _mods):
        if action != glfw.PRESS:
            return
        if key == glfw.KEY_ESCAPE:
            state["captured"] = False
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_NORMAL)
        elif key == glfw.KEY_Q:
            state["quit"] = True
        elif key == glfw.KEY_SPACE:
            player.jump()
        elif key == glfw.KEY_F:
            player.fly = not player.fly
            print(f"   {'飞行' if player.fly else '走路'}模式")
        elif key == glfw.KEY_T:
            flag = mujoco.mjtVisFlag.mjVIS_TRANSPARENT
            opt.flags[flag] = not opt.flags[flag]
            print(f"   透视{'开' if opt.flags[flag] else '关'}")
        elif key == glfw.KEY_C:
            g = getattr(layout, "CEILING_GROUP", 1)
            opt.geomgroup[g] = 0 if opt.geomgroup[g] else 1
            print(f"   天花板{'关' if not opt.geomgroup[g] else '开'}")
        elif key == glfw.KEY_TAB:
            player.goto_floor(0)
            print("   回到出生点")
        elif key == glfw.KEY_P:
            e = player.eye
            print(f"   x={e[0]:.2f} y={e[1]:.2f} z={e[2]:.2f} 朝向{player.yaw % 360:.0f}°"
                  f"  在「{player.room()}」")
        elif interaction and key == glfw.KEY_J:
            state['joint_index'] += 1
        elif interaction and key in (glfw.KEY_E, glfw.KEY_LEFT_BRACKET, glfw.KEY_RIGHT_BRACKET):
            target = selection()
            if target and target['body'] not in interaction.free_bodies:
                name = target['names'][state['joint_index'] % len(target['names'])]
                fraction = interaction.status(name)['fraction']
                wanted = (0.0 if fraction > 0.5 else 1.0) if key == glfw.KEY_E else np.clip(
                    fraction + (0.15 if key == glfw.KEY_RIGHT_BRACKET else -0.15), 0, 1)
                interaction.command(name, float(wanted))
        elif interaction and key == glfw.KEY_G:
            if interaction.held:
                interaction.release()
            else:
                target = selection()
                if target and target['body'] in interaction.free_bodies:
                    interaction.grab(target['body'], target['point'])
                    state['grab_distance'] = target['distance']
        elif interaction and key == glfw.KEY_BACKSPACE:
            interaction.cancel()
            interaction.results.clear()
            mujoco.mj_resetData(m, d)
            park_robot(m, d, layout, robot)
            mujoco.mj_forward(m, d)
            physics.accumulated = 0.0
        elif cycle and key == glfw.KEY_L:
            phases = cycle.phases
            cycle.set(phases[(phases.index(cycle.phase)+1) % len(phases)])
            mujoco.mj_forward(m,d)  # Refresh moved light positions even in a static scene.
        elif glfw.KEY_1 <= key <= glfw.KEY_9:
            n = getattr(layout, "N_FLOORS", 1)
            f = key - glfw.KEY_1
            if f < n:
                player.goto_floor(f)
                print(f"   跳到第 {f + 1} 层出生点")
            else:
                print(f"   这个场景只有 {n} 层")

    glfw.set_cursor_pos_callback(window, on_cursor)
    glfw.set_mouse_button_callback(window, on_mouse_button)
    glfw.set_key_callback(window, on_key)

    print(f"场景 {scene_key}：{SCENES.get(scene_key)['label']}")
    print("鼠标转头 · WASD 走 · 空格跳 · Shift 跑 · F 飞行 · T 透视 · 数字键跳层 · "
          "C 天花板 · P 报坐标 · Esc 放鼠标 · Q 退出")
    print(f"当前：{'飞行' if fly else '走路'}模式，透视{'开' if xray else '关'}\n")
    if interaction:
        print('E 开合/按压 · [ ] 调整开度 · J 切换同一部件的关节 · G 抓取/松手 · '
              'L 切换时段 · Backspace 复位家具。瞄准 2 米内可见的活动部件。')
    elif cycle:
        print('L 切换白天、清晨、黄昏与夜间。')

    down = lambda k: glfw.get_key(window, k) == glfw.PRESS  # noqa: E731
    prev = glfw.get_time()
    while not glfw.window_should_close(window) and not state["quit"]:
        now = glfw.get_time()
        dt = min(0.05, now - prev)      # 卡一下也不要让人一帧穿过墙
        prev = now

        ax = (1.0 if down(glfw.KEY_W) else 0.0) - (1.0 if down(glfw.KEY_S) else 0.0)
        ay = (1.0 if down(glfw.KEY_D) else 0.0) - (1.0 if down(glfw.KEY_A) else 0.0)
        up = (1.0 if down(glfw.KEY_R) else 0.0) - (1.0 if down(glfw.KEY_LEFT_CONTROL) else 0.0)
        running = down(glfw.KEY_LEFT_SHIFT) or down(glfw.KEY_RIGHT_SHIFT)
        player.move(probe, ax, ay, dt, running, up)
        if physics:
            if interaction.held:
                interaction.move_grab(player.eye + direction()*state['grab_distance'])
            physics.advance(dt)

        room = player.announce_room()
        if room:
            print(f"   → {room}")

        cam.lookat[:] = player.eye
        cam.distance = 1e-3          # 距离趋近 0 = 相机就站在眼睛那一点，即第一人称
        cam.azimuth, cam.elevation = player.yaw, player.pitch

        w, h = glfw.get_framebuffer_size(window)
        rect = mujoco.MjrRect(0, 0, w, h)
        mujoco.mjv_updateScene(m, d, opt, None, cam, mujoco.mjtCatBit.mjCAT_ALL, scene)
        mujoco.mjr_render(rect, scene, ctx)
        if interaction:
            # A small centre marker makes the actual selection ray visible.
            mujoco.mjr_rectangle(mujoco.MjrRect(w//2-5,h//2-1,10,2),1,1,1,.8)
            mujoco.mjr_rectangle(mujoco.MjrRect(w//2-1,h//2-5,2,10),1,1,1,.8)
        help_text = player.room()
        if interaction:
            help_text = f'{scene_key.upper()} inspection | {cycle.phase} | E operate | G grab | L time | Backspace reset'
            target = selection()
            if target:
                name = target['names'][state['joint_index'] % len(target['names'])]
                info = interaction.status(name)
                help_text += '\n' + name
                if 'fraction' in info:
                    help_text += f" | {info['fraction']:.0%} | {info['result']} | [ ] adjust | J joint"
            if interaction.held:
                help_text += '\nHolding object: G releases into gravity'
        mujoco.mjr_overlay(mujoco.mjtFont.mjFONT_NORMAL, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                           rect, help_text, "", ctx)
        glfw.swap_buffers(window)
        glfw.poll_events()

    if interaction:
        interaction.cancel()
    ctx.free()
    glfw.terminate()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default=SCENES.DEFAULT_SCENE, help=f"场景（{'/'.join(SCENES.keys())}）")
    ap.add_argument("--robot", default="g1", help="用哪份产物（屋里那台机器人只当比例尺）")
    ap.add_argument("--eye", type=float, default=EYE_HUMAN,
                    help=f"眼高 m（人形 {EYE_HUMAN} / 四足 {EYE_DOG}）")
    ap.add_argument("--floor", type=int, default=0, help="从第几层开始（0 起）")
    ap.add_argument("--fly", action="store_true", help="一开始就是飞行模式")
    ap.add_argument("--xray", action="store_true", help="一开始就打开透视")
    ap.add_argument("--mouse-sens", type=float, default=MOUSE_SENS_DEG_PER_SCREEN,
                    help=f"鼠标灵敏度：横扫满窗口转多少度（默认 {MOUSE_SENS_DEG_PER_SCREEN:.0f}，"
                         f"数字越小越稳）")
    ap.add_argument("--selftest", action="store_true", help="无窗口自测方向/碰撞/上楼梯")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.scene, args.eye)
    return run_viewer(args.scene, args.robot, args.eye, args.floor, args.fly, args.xray,
                      mouse_sens=args.mouse_sens)


if __name__ == "__main__":
    raise SystemExit(main())
