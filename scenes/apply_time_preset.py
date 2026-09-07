"""时段光照应用器 —— 把 layout 的 LIGHTS_BY_TIME 写进已加载的 mjModel。

⭐ 「灯该怎么打」的**应用逻辑只有这一份**：本仓的出图工具和消费方（anima-zero 的
sim-house-nav 录制引擎）都按文件路径加载本模块调 `apply()`。⛔ 别在别处再抄一遍
字段写入——那就是「同一个量存两处」，本仓被它咬过不止一次。

设计约束（与 layout 的 LIGHTS_BY_TIME 注释配对）：
- 预设**不能凭空创造任何东西**：引用的灯名/材质名/geom 名必须在产物里已存在，
  查不到就 raise——静默跳过 = 「调了灯但没生效」这种最难查的错。
- ⛔ 渲染器只点亮 headlight + 前 7 盏 active 灯（实测），超预算当场 raise。
- 本模块**不做复原**：跨段串色的正解是每段重新 from_xml_path，不指望改回去。
"""
from __future__ import annotations

import importlib.util
import os
import sys

import mujoco
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓根


def _layout(scene_key: str):
    """按路径加载 scenes/manifest.py 再取 layout（本模块自己也可能是被路径加载的，
    不能指望包导入成立）。"""
    path = os.path.join(_ROOT, "scenes", "manifest.py")
    spec = importlib.util.spec_from_file_location("ah_manifest_for_preset", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_layout(scene_key)


def _f(v) -> np.ndarray:
    """"0.5 0.5 0.5" / (0.5, 0.5, 0.5) → float 数组。"""
    if isinstance(v, str):
        return np.array([float(x) for x in v.split()], float)
    return np.array(v, float)


def _light_id(m, name: str) -> int:
    i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_LIGHT, name)
    if i < 0:
        raise ValueError(f"预设引用了产物里不存在的灯 {name!r}——预设只能是产物的补丁，"
                         "不能凭空创造（多半是打错字，或产物没重新生成）")
    return i


def _mat_id(m, name: str) -> int:
    i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_MATERIAL, name)
    if i < 0:
        raise ValueError(f"预设引用了产物里不存在的材质 {name!r}")
    return i


def _apply_light(m, i: int, attrs: dict) -> None:
    for k, v in attrs.items():
        if k == "pos":
            m.light_pos[i] = _f(v)
        elif k == "dir":
            d = _f(v)
            m.light_dir[i] = d / np.linalg.norm(d)   # MJCF 编译时会归一化，运行期得自己来
        elif k == "diffuse":
            m.light_diffuse[i] = _f(v)
        elif k == "specular":
            m.light_specular[i] = _f(v)
        elif k == "cutoff":
            m.light_cutoff[i] = float(v)
        elif k == "attenuation":
            m.light_attenuation[i] = _f(v)
        elif k == "castshadow":
            m.light_castshadow[i] = 1 if v else 0
        elif k == "active":
            m.light_active[i] = 1 if v else 0
        else:
            raise ValueError(f"灯属性 {k!r} 不认识（认识：pos/dir/diffuse/specular/"
                             "cutoff/attenuation/castshadow/active）")


def _band_geoms(m, L, where: str) -> list[int]:
    band = L.GEOM_BANDS.get(where)
    if band is None:
        raise ValueError(f"geom_tint 的 where={where!r} 不在 GEOM_BANDS 里")
    ids: list[int] = []
    if "names" in band:
        for n in band["names"]:
            g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, n)
            if g < 0:
                raise ValueError(f"GEOM_BANDS[{where!r}] 点名的 geom {n!r} 不在产物里")
            ids.append(g)
        return ids
    prefix = band["prefix"]
    for g in range(m.ngeom):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
        if not name or not name.startswith(prefix):
            continue
        x, y = float(m.geom_pos[g][0]), float(m.geom_pos[g][1])
        if "x_max" in band and not x < band["x_max"]:
            continue
        if "x_min" in band and not x > band["x_min"]:
            continue
        if "x_abs_max" in band and not abs(x) < band["x_abs_max"]:
            continue
        if "y_min" in band and not y > band["y_min"]:
            continue
        ids.append(g)
    if not ids:
        raise ValueError(f"GEOM_BANDS[{where!r}] 一个 geom 都没筛到——前缀或阈值错了")
    return ids


def _swap_skybox(m, renderer, phase_suffix: str, warns: list[str]) -> None:
    """把天空盒六面换成 `textures/house3/sky_<时段>_file*.png`。

    ⛔ 两个都是实测过的坑：
    ① MuJoCo 的**天空盒面序反常**（Y 轴朝上制作、渲染时绕 +X 转 90°）——这里不猜面序，
      拿产物里**已加载的白天六面**和磁盘上的白天 PNG 逐面匹配出真实顺序，再按同序写入；
    ② 只写 `tex_data` 不上传 GPU = **静默失效**（画面一字不变）——必须经 renderer 的
      GL 上下文调 `mjr_uploadTexture`。renderer 为 None（dry-run）时跳过并留告警。
    """
    from PIL import Image

    skyid = next((t for t in range(m.ntex)
                  if m.tex_type[t] == mujoco.mjtTexture.mjTEXTURE_SKYBOX), None)
    if skyid is None:
        warns.append("⚠️ 产物里没有 skybox 贴图，换天空跳过")
        return
    W = int(m.tex_width[skyid])
    H = int(m.tex_height[skyid])
    nch = int(m.tex_nchannel[skyid])
    nface = H // W
    if nface != 6 or nch != 3:
        warns.append(f"⚠️ skybox 形状出乎意料（{W}×{H}×{nch}），换天空跳过")
        return
    adr = int(m.tex_adr[skyid])
    block = m.tex_data[adr: adr + H * W * nch].reshape(6, W, W, nch)

    tex_dir = os.path.join(_ROOT, "textures", "house3")
    attrs = ("fileright", "fileleft", "fileup", "filedown", "filefront", "fileback")

    def _load(prefix: str) -> dict[str, np.ndarray]:
        out = {}
        for a in attrs:
            p = os.path.join(tex_dir, f"{prefix}{a}.png")
            if not os.path.isfile(p):
                raise FileNotFoundError(
                    f"缺天空盒面 {p}（先跑 tools/make_view.py --sky --sky-phase <时段>）")
            img = np.asarray(Image.open(p).convert("RGB"))
            if img.shape[0] != W:
                raise ValueError(f"{p} 是 {img.shape[1]}×{img.shape[0]}，"
                                 f"而产物里的天空盒面是 {W}×{W}——运行期 tex_data 整段覆盖，"
                                 "尺寸必须逐位相同")
            out[a] = img
        return out

    day = _load("sky_")
    new = _load(f"sky_{phase_suffix}_")
    # 逐面匹配出「内存槽位 → 文件名」的真实顺序（拿白天那套对，误差最小者胜）
    order: list[str] = []
    for i in range(6):
        small = block[i][::16, ::16].astype(float)
        best, best_err = None, None
        for a in attrs:
            err = float(np.mean(np.abs(day[a][::16, ::16].astype(float) - small)))
            if best_err is None or err < best_err:
                best, best_err = a, err
        if best_err is None or best_err > 8.0:
            warns.append(f"⚠️ 天空盒第 {i} 面和白天 PNG 对不上（err={best_err:.1f}）——"
                         "产物的天空和磁盘文件不同步？换天空跳过")
            return
        order.append(best)
    if sorted(order) != sorted(attrs):
        warns.append(f"⚠️ 天空盒面序匹配出重复（{order}），换天空跳过")
        return
    for i, a in enumerate(order):
        block[i] = new[a]
    if renderer is None:
        warns.append("⚠️ 没有 renderer，天空写进了 tex_data 但**没上传 GPU**（dry-run 无妨；"
                     "渲染时必须传 renderer）")
        return
    # 上传（⛔ 少这两行 = 静默失效）
    renderer._gl_context.make_current()
    mujoco.mjr_uploadTexture(m, renderer._mjr_context, skyid)


def _swap_gridcube(m, renderer, L, tex_name: str, night_file: str, warns: list[str]) -> None:
    """把一张网格排布的 cube 贴图（塔楼立面那种 gridsize/gridlayout）换成夜间版。

    面序不猜：把**原盘上那张白天网格图**按 layout 声明的 gridlayout 拆成候选格，
    和 tex_data 里的每个槽位实测匹配出「槽位 → 网格格子」的真实顺序，再按同序写入
    夜间图的对应格子。四个侧面内容相同（匹配退化）无妨——写进去的也相同。
    """
    from PIL import Image

    ti = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TEXTURE, tex_name)
    if ti < 0:
        raise ValueError(f"textures 引用了产物里不存在的贴图 {tex_name!r}")
    spec = next((t for t in getattr(L, "TEXTURES_EXTRA", ()) if t.get("name") == tex_name), None)
    if spec is None:
        raise ValueError(f"layout.TEXTURES_EXTRA 里找不到 {tex_name!r} 的声明（要读它的 gridlayout）")
    if int(m.tex_type[ti]) == int(mujoco.mjtTexture.mjTEXTURE_2D):
        path = (os.path.join(_ROOT, os.path.dirname(spec["file"]), night_file)
                if os.sep not in night_file else os.path.join(_ROOT, night_file))
        nch = int(m.tex_nchannel[ti])
        with Image.open(path) as image:
            pixels = np.asarray(image.convert("RGBA" if nch == 4 else "RGB"))
        expected = (int(m.tex_height[ti]), int(m.tex_width[ti]), nch)
        if pixels.shape != expected:
            raise ValueError(f"{tex_name}: replacement texture shape {pixels.shape} != {expected}")
        adr = int(m.tex_adr[ti])
        m.tex_data[adr:adr+pixels.size] = pixels.ravel()
        if renderer is None:
            warns.append(f"⚠️ 没有 renderer，{tex_name} 写进了 tex_data 但没上传 GPU")
        else:
            renderer._gl_context.make_current()
            mujoco.mjr_uploadTexture(m, renderer._mjr_context, ti)
        return
    W = int(m.tex_width[ti])
    H = int(m.tex_height[ti])
    nch = int(m.tex_nchannel[ti])
    nslot = H // W
    adr = int(m.tex_adr[ti])
    block = m.tex_data[adr: adr + H * W * nch].reshape(nslot, W, W, nch)

    def _cells(path: str) -> list[np.ndarray]:
        img = np.asarray(Image.open(path).convert("RGB"))
        cells = []
        cols = len(spec["gridlayout"]) // int(spec["gridsize"].split()[0])
        for i, ch in enumerate(spec["gridlayout"]):
            if ch == ".":
                continue
            r, c = divmod(i, cols)
            cell = img[r * W:(r + 1) * W, c * W:(c + 1) * W]
            if cell.shape[:2] != (W, W):
                raise ValueError(f"{path} 的格子尺寸 {cell.shape[:2]} ≠ 槽位 {W}×{W}"
                                 "——运行期 tex_data 整段覆盖，尺寸必须逐位相同")
            cells.append(cell)
        return cells

    day_cells = _cells(os.path.join(_ROOT, spec["file"]))
    night_cells = _cells(os.path.join(_ROOT, os.path.dirname(spec["file"]), night_file)
                         if os.sep not in night_file else os.path.join(_ROOT, night_file))
    if len(day_cells) != nslot:
        warns.append(f"⚠️ {tex_name}: 网格格数 {len(day_cells)} ≠ 内存槽数 {nslot}，换装跳过")
        return
    for s in range(nslot):
        small = block[s][::8, ::8].astype(float)
        errs = [float(np.mean(np.abs(c[::8, ::8].astype(float) - small))) for c in day_cells]
        best = int(np.argmin(errs))
        if errs[best] > 8.0:
            warns.append(f"⚠️ {tex_name} 槽 {s} 与白天网格图对不上（err={errs[best]:.1f}），换装跳过")
            return
        block[s] = night_cells[best]
    if renderer is None:
        warns.append(f"⚠️ 没有 renderer，{tex_name} 写进了 tex_data 但没上传 GPU")
        return
    renderer._gl_context.make_current()
    mujoco.mjr_uploadTexture(m, renderer._mjr_context, ti)


def apply(model, renderer, phase: str, scene_key: str = "apt",
          light_patch: dict | None = None) -> list[str]:
    """把 `phase` 的光照预设写进 model。返回告警列表（空 = 全部如实生效）。

    renderer 只在换天空盒时用（贴图要经它的 GL 上下文上传）；不换天空可传 None。
    """
    warns: list[str] = []
    L = _layout(scene_key)
    presets = getattr(L, "LIGHTS_BY_TIME", None)
    if presets is None:
        return [f"⚠️ 场景 {scene_key!r} 的 layout 没有 LIGHTS_BY_TIME，按白天渲染"]
    if phase not in presets:
        raise ValueError(f"未知时段 {phase!r}，可选：{tuple(presets)}")
    spec = presets[phase]
    m = model

    if spec or light_patch:
        # ⛔ 关掉机器人自带的那盏无名主光（index 0，占 68% 像素）；day 段不动它，
        #    保持与已入库 README 配图一致。
        if getattr(L, "LIGHT0_IS_ROBOT_LIGHT", False) and spec:
            if mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_LIGHT, 0) is not None:
                warns.append("⚠️ 第 0 盏灯有名字——「无名 = 机器人灯」的约定被打破了，没关它")
            else:
                m.light_active[0] = 0

    if not spec:
        pass                                # day：产物即真相
    else:
        lights: dict = spec.get("lights", {})
        budget = getattr(L, "LIGHT_BUDGET", 7)
        if len(lights) > budget:
            raise ValueError(f"时段 {phase!r} 用了 {len(lights)} 盏灯 > 预算 {budget}"
                             "（渲染器只点亮前 7 盏，多出来的静默不亮）")
        for name, attrs in lights.items():
            _apply_light(m, _light_id(m, name), attrs)
        for name in spec.get("lights_off", ()):
            m.light_active[_light_id(m, name)] = 0
        hl = spec.get("headlight")
        if hl:
            m.vis.headlight.diffuse[:] = _f(hl["diffuse"])
            m.vis.headlight.ambient[:] = _f(hl["ambient"])
            m.vis.headlight.specular[:] = _f(hl["specular"])
        for name, attrs in spec.get("materials", {}).items():
            i = _mat_id(m, name)
            for k, v in attrs.items():
                if k == "rgba":
                    m.mat_rgba[i] = _f(v)
                elif k == "emission":
                    m.mat_emission[i] = float(v)
                elif k == "specular":
                    m.mat_specular[i] = float(v)
                elif k == "shininess":
                    m.mat_shininess[i] = float(v)
                elif k == "reflectance":
                    m.mat_reflectance[i] = float(v)
                else:
                    raise ValueError(f"材质属性 {k!r} 不认识")
        for tint in spec.get("geom_tint", ()):
            rgba = _f(tint["rgba"])
            for g in _band_geoms(m, L, tint["where"]):
                m.geom_rgba[g] = rgba
        glass = spec.get("glass")
        if glass:
            rgba = _f(glass["rgba"])
            if rgba[3] <= 0.02:
                raise ValueError("⛔ 玻璃 alpha 不许 ≤0.02（alpha=0 曾让 mj_ray 跳过玻璃、"
                                 "碰撞盒被悄悄挖空——232 米自由落体那个坑）")
            gi = _mat_id(m, glass["bind_material"])
            n_bound = 0
            for g in range(m.ngeom):
                name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
                if name and name.startswith("glass"):
                    m.geom_matid[g] = gi
                    n_bound += 1
            if n_bound == 0:
                raise ValueError("一块 glass* geom 都没找到")
            m.mat_rgba[gi] = rgba
            for k in ("specular", "shininess", "reflectance", "emission"):
                if k in glass:
                    getattr(m, f"mat_{k}")[gi] = float(glass[k])
        for tex_name, night_file in spec.get("textures", {}).items():
            _swap_gridcube(m, renderer, L, tex_name, night_file, warns)
        sky = spec.get("sky")
        if sky:
            _swap_skybox(m, renderer, sky, warns)

    for name, attrs in (light_patch or {}).items():
        _apply_light(m, _light_id(m, name), attrs)
    return warns
