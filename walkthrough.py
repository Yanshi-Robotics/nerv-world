#!/usr/bin/env python3
"""第一人称漫游 —— 像玩 Minecraft 那样走进屋里看。

    python walkthrough.py                      # 默认场景
    python walkthrough.py --scene house2       # 三层小楼，可以踩着楼梯上楼
    python walkthrough.py --scene house2 --fly # 飞行模式（穿墙、自由升降）

鼠标转头，WASD 走路，空格跳，Shift 跑。默认是**走路模式**：脚下踩实、撞墙走不过去、
台阶自动迈上去——所以楼梯是真能一级一级走上三楼的，不是飞上去。

    鼠标        转头（光标已锁进窗口，按 Esc 放出来）
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

⚠️ 这个脚本**不推物理**（只做 mj_forward）。屋里那台机器人保持初始姿态站着当比例尺，
不会自己走；走路的碰撞是拿射线自己算的，不是让 MuJoCo 去解算一个玩家刚体。
"""
from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from scenes import manifest as SCENES  # noqa: E402

# 眼高与 robots/manifest.py 里那两台机器人的实际相机高度一致。
EYE_HUMAN = 1.25
EYE_DOG = 0.38

WALK_SPEED = 2.4        # m/s，常速走
RUN_MULT = 2.2          # 按住 Shift 的倍率
FLY_SPEED = 4.5         # m/s，飞行模式
MOUSE_SENS = 0.12       # 度/像素
PITCH_LIMIT = 89.0

BODY_RADIUS = 0.28      # 玩家"胖"多少：撞墙判定用的水平半径
# ⭐ 撞墙探测的射线高度，相对**脚底**固定 1.0 m（胸口）。两个都试错过：
#    取膝盖（脚+0.35）→ 在楼梯上那条水平射线必然打到前面两级台阶，走两步卡死；
#    取眼睛 → 站到半层高的休息平台上时眼睛正好齐墙顶，射线从墙上掠过去，
#             人直接走进墙里再掉下楼。
#    固定 1.0 m 两头都躲开：台阶在 0.32 m 内最多升一个踢面、够不着它，
#    而墙从各自楼层的地面起算有 2.7 m 高，1.0 m 一定在墙身里。
PROBE_H = 1.0
STEP_UP_MAX = 0.30      # 能自动迈上去的台阶高度上限（house2 踢面 0.16，够）
GRAVITY = 9.8
JUMP_V = 3.2


class Player:
    """玩家状态与移动规则。抽出来是为了能在无窗口环境下自测方向和碰撞。"""

    def __init__(self, layout, eye_h: float, floor: int = 0, fly: bool = False):
        self.layout = layout
        self.eye_h = eye_h
        self.fly = fly
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
        self.yaw -= dx * MOUSE_SENS
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch - dy * MOUSE_SENS))

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
        """先探路再走：正前方 BODY_RADIUS 内有东西就不动。

        探测高度见 PROBE_H 的注释——那两行是这个函数踩过的两个坑。
        代价是矮家具（茶几、椅子）不挡人：对一个"进去看看"的工具反而更好，
        免得卡在椅子腿上出不来。
        """
        origin = [self.feet[0], self.feet[1], self.feet[2] + PROBE_H]
        hit = probe(origin, (vx, vy, 0.0))
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


def selftest(scene_key: str, eye_h: float) -> int:
    """无窗口自测：方向、碰撞、踩地、上楼梯。

    方向约定很容易搞反（本项目在楼梯扶手上已经栽过一次），所以不靠推理，
    全部拿射线实测。
    """
    import numpy as np
    import mujoco

    os.environ.setdefault("MUJOCO_GL", "egl")
    layout = SCENES.load_layout(scene_key)
    path = os.path.join(HERE, SCENES.scene_filename(scene_key, "g1"))
    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    def probe(origin, direction) -> float:
        gid = np.zeros(1, dtype=np.int32)
        return mujoco.mj_ray(m, d, np.array(origin, dtype=float),
                             np.array(direction, dtype=float), None, 1, -1, gid)

    ok = True
    p = Player(layout, eye_h)

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
               fly: bool, xray: bool = False) -> int:
    import glfw
    import mujoco
    import numpy as np

    layout = SCENES.load_layout(scene_key)
    path = os.path.join(HERE, SCENES.scene_filename(scene_key, robot))
    if not os.path.exists(path):
        print(f"找不到 {os.path.basename(path)}，先生成：\n"
              f"    python make_house.py --scene {scene_key} --robot {robot}", file=sys.stderr)
        return 1

    m = mujoco.MjModel.from_xml_path(path)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)

    if not glfw.init():
        print("glfw 起不来——这个脚本要有显示器（远程的话记得开 X11 转发）", file=sys.stderr)
        return 1
    window = glfw.create_window(1280, 800, f"alice-house · {scene_key}", None, None)
    glfw.make_context_current(window)
    glfw.swap_interval(1)

    player = Player(layout, eye_h, floor, fly)
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)
    opt = mujoco.MjvOption()
    if xray:
        opt.flags[mujoco.mjtVisFlag.mjVIS_TRANSPARENT] = True
    scene = mujoco.MjvScene(m, maxgeom=20000)
    ctx = mujoco.MjrContext(m, mujoco.mjtFontScale.mjFONTSCALE_150)

    state = {"last": None, "captured": True, "quit": False}
    glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)

    def probe(origin, direction) -> float:
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
        mujoco.mjr_overlay(mujoco.mjtFont.mjFONT_NORMAL, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                           rect, player.room(), "", ctx)
        glfw.swap_buffers(window)
        glfw.poll_events()

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
    ap.add_argument("--selftest", action="store_true", help="无窗口自测方向/碰撞/上楼梯")
    args = ap.parse_args()

    if args.selftest:
        return selftest(args.scene, args.eye)
    return run_viewer(args.scene, args.robot, args.eye, args.floor, args.fly, args.xray)


if __name__ == "__main__":
    raise SystemExit(main())
