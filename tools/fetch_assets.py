#!/usr/bin/env python3
"""下载 apt1 用的 CC0 材质贴图（ambientCG）→ textures/house3/。

⚠️ 贴图目录与 `h3_` 前缀沿用场景最早的名字 house3（资产命名空间，见 README「建造顺序」）；
场景 key 是 apt1。

和 `make_textures.py` 的分工：那个是**程序化生成**本仓自己的 20 张基础贴图（house1/house2 在用）；
这个是**下载第三方**的照片级材质，只给 apt1 用。
⛔ 两边名字不许撞——apt1 的一律带 `h3_` 前缀，撞名 MuJoCo 会当场拒绝编译（本仓踩过）。

许可：ambientCG 全站 **CC0 1.0**（"copy, modify, distribute and perform the assets,
even for commercial purposes, all without asking permission"）。署名不是义务，
但照惯例登记在 textures/house3/ATTRIBUTION.md。

⚠️ ambientCG 是**一个人在运营**，官方文档自己声明 API 不保证稳定
（"potentially not as reliable or stable as needed for an 'enterprise-level' application"）。
所以这个脚本把文件**下载到本地入库**，⛔ 不在构建时抓。

⚠️ 只取 Color（albedo）那一张。MuJoCo 内置渲染器是 Blinn-Phong，法线/粗糙度贴图吃不吃
是版本相关的——先按只有 albedo 做，需要再说。

用法：
    python tools/fetch_assets.py              # 下载缺的
    python tools/fetch_assets.py --force      # 全部重下
    python tools/fetch_assets.py --verify     # 只校验 SHA-256，不下载
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
import urllib.request
import zipfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))     # tools/
ROOT = os.path.dirname(HERE)                          # 仓根
# ⛔ tools/ 里不许再出现裸 HERE 做路径拼接 —— HERE 只用来推导 ROOT。
#    这条规矩是为了 review 时一眼看得出有没有漏改：任何落点错误都会在
#    tools/ 下长出一个目录（`ls tools/ | grep -v '\.py$'` 必须为空）。
OUT_DIR = os.path.join(ROOT, "textures", "house3")
LOCK = os.path.join(OUT_DIR, "materials.lock.json")
GET = "https://ambientcg.com/get?file={id}_{res}-PNG.zip"
TARGET_PX = 1024        # 1K 足够：室内材质在画面上很少超过这个采样率，2K 是纯浪费

# (本仓的贴图名, ambientCG 资产号, 分辨率档, 用在哪)
# ⚠️ 资产号是从 ambientCG 的 API 按热度查出来的，选择理由写在第四列——
#    换材质时照着这个理由挑，别只看编号。
MATERIALS = [
    ("h3_oak",        "WoodFloor070", "2K", "主木地板：米褐、干净的宽板，北带三间与主卧"),
    ("h3_oak_dark",   "WoodFloor064", "2K", "深色拼花：书房/衣帽间，和主地板拉开层次"),
    ("h3_marble",     "Marble021",    "2K", "亮面白大理石：画廊地面（12.6 m 展线要通透）"),
    ("h3_marble_blk", "Marble016",    "2K", "黑大理石：厨房台面与岛台，和白地面对比"),
    ("h3_travertine", "Travertine009","2K", "米黄洞石：玄关、东过厅、厨房地面"),
    ("h3_onyx",       "Onyx012",      "2K", "米色玛瑙：主卫墙面（独立浴缸那面）"),
    ("h3_linen",      "Fabric036",    "2K", "细密平织：沙发与床品软包"),
    ("h3_plaster",    "Plaster001",   "2K", "干净哑光石膏：全屋墙面（比程序化的那张细腻）"),
    ("h3_rug",        "Carpet016",    "2K", "米色地毯：大客厅与玄关地毯"),
]


# ⚠️ ambientCG 会用 403 拒掉默认的 `Python-urllib/3.x` User-Agent。
#    带一个能说明来路的 UA 是基本礼貌，也是它接受请求的前提。
UA = "alice-house/0.8 (+https://github.com/Yanshi-Robotics/alice-house) scene-asset-fetcher"


def _get(url: str, timeout: int = 300, tries: int = 3) -> bytes:
    """带 UA 的下载，网络抖动重试几次（本机偶发 DNS 解析失败）。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:                       # noqa: BLE001
            last = exc
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise last


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _color_png(zbytes: bytes, asset_id: str) -> bytes:
    """从 ambientCG 的 zip 里取出 Color 那张，缩到 TARGET_PX，转 8 位 sRGB PNG。"""
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        names = [n for n in z.namelist() if "_Color." in n]
        if not names:
            raise RuntimeError(f"{asset_id} 的 zip 里没有 *_Color.png（有：{z.namelist()[:6]}）")
        img = Image.open(io.BytesIO(z.read(names[0]))).convert("RGB")
    if img.width != TARGET_PX:
        img = img.resize((TARGET_PX, TARGET_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="已存在也重下")
    ap.add_argument("--verify", action="store_true", help="只校验 SHA-256")
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    lock = json.load(open(LOCK)) if os.path.exists(LOCK) else {}

    if a.verify:
        bad = 0
        for name, aid, res, why in MATERIALS:
            p = os.path.join(OUT_DIR, f"{name}.png")
            if not os.path.exists(p):
                print(f"  ⛔ 缺失 {name}.png"); bad += 1; continue
            got = _sha(open(p, "rb").read())
            want = lock.get(name, {}).get("sha256")
            print(f"  {'✅' if got == want else '⛔'} {name}  {got[:12]}")
            bad += got != want
        print("全部一致" if not bad else f"⛔ {bad} 项不一致")
        return

    print(f"下载 CC0 材质（ambientCG）→ {OUT_DIR}")
    for name, aid, res, why in MATERIALS:
        dst = os.path.join(OUT_DIR, f"{name}.png")
        if os.path.exists(dst) and not a.force:
            print(f"   跳过 {name}（已存在）")
            continue
        url = GET.format(id=aid, res=res)
        try:
            png = _color_png(_get(url), aid)
        except Exception as exc:                       # noqa: BLE001
            print(f"   ⛔ {name} ({aid}) 失败：{type(exc).__name__} {str(exc)[:80]}")
            continue
        open(dst, "wb").write(png)
        lock[name] = {"ambientcg_id": aid, "resolution": res, "license": "CC0-1.0",
                      "source": url, "target_px": TARGET_PX,
                      "sha256": _sha(png), "note": why}
        print(f"   {name:15s} ← {aid:14s} {len(png) // 1024:5d} KB   {why}")
    json.dump(lock, open(LOCK, "w"), indent=2, ensure_ascii=False, sort_keys=True)
    print(f"清单写入 {LOCK}（{len(lock)} 项）")


if __name__ == "__main__":
    main()
