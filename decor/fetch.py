#!/usr/bin/env python3
"""下载并转换装饰网格 → decor/assets/（⛔ gitignore，字节不入库）。

    python -m decor.fetch              # 下载缺的
    python -m decor.fetch --force      # 全部重来
    python -m decor.fetch --verify     # 只校验，不下载

⛔ **许可闸是可执行代码**：上游实际返回的许可不在 `manifest.LICENSE_ALLOWLIST` 里，
   或者和登记表声明的不一致，**直接拒绝写入**，不是打个警告了事。
   ⚠️ Objaverse 里混着 `by-nc`（调研时第二个沙发就撞上了），而且
   **Sketchfab 的 search 接口返回的 license 是 None**——必须逐个查
   `api.sketchfab.com/v3/models/<uid>` 拿真 slug。

产物：
  decor/assets/<key>/p{i}.obj        一个文件一张网格（⛔ 多物体 OBJ 会静默损坏）
  decor/assets/<key>/p{i}.png        对应的贴图（没有就没有）
  decor/assets/<key>/LICENSE.txt     许可与出处，随字节一起躺着
  decor/decor.lock.json              **入库**：期望清单 + sha256 + 归一化包围盒
  decor/ATTRIBUTION.md               **入库**：自动生成的署名表
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request

from . import convert
from .manifest import ASSETS, LICENSE_ALLOWLIST, OBJAVERSE_SLUG

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(HERE, "assets")
LOCK = os.path.join(HERE, "decor.lock.json")
ATTRIB = os.path.join(HERE, "ATTRIBUTION.md")

UA = "alice-house/0.8 (+https://github.com/Yanshi-Robotics/alice-house) scene-asset-fetcher"
PH_FILES = "https://api.polyhaven.com/files/{id}"
PH_INFO = "https://api.polyhaven.com/info/{id}"
OBJ_PATHS = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/object-paths.json.gz"
OBJ_GLB = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/{path}"
SKETCHFAB = "https://api.sketchfab.com/v3/models/{uid}"

_paths_cache: dict | None = None


def _get(url: str, timeout: int = 300, tries: int = 3) -> bytes:
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


# ---------------------------------------------------------------- 上游解析
def _polyhaven(spec: dict) -> tuple[bytes, str, str, str]:
    """→ (glTF 字节, file_type, 实际许可, 作者)。Poly Haven 全站 CC0。"""
    aid, res = spec["source_id"], spec.get("res", "2k")
    files = json.loads(_get(PH_FILES.format(id=aid)))
    node = files["gltf"][res]["gltf"]
    # ⚠️ Poly Haven 发的是 .gltf + 分离的 .bin + textures/，不是单文件 .glb。
    #    trimesh 需要同目录的伴生文件，所以把 include 里的都抓下来一起喂。
    base = json.loads(_get(node["url"]).decode("utf-8"))
    assets = {}
    for rel, meta in (node.get("include") or {}).items():
        assets[os.path.basename(rel)] = _get(meta["url"])
    info = json.loads(_get(PH_INFO.format(id=aid)))
    author = ", ".join((info.get("authors") or {}).keys()) or "Poly Haven"
    return (json.dumps(base).encode("utf-8"), "gltf", "CC0-1.0", author), assets


def _objaverse(spec: dict) -> tuple[bytes, str, str, str]:
    """→ (GLB 字节, 'glb', 实际许可, 作者)。⛔ 许可逐件查 Sketchfab。"""
    global _paths_cache
    uid = spec["source_id"]
    meta = json.loads(_get(SKETCHFAB.format(uid=uid)))
    slug = ((meta.get("license") or {}).get("slug") or "").lower()
    lic = OBJAVERSE_SLUG.get(slug, f"UNKNOWN({slug or 'none'})")
    author = ((meta.get("user") or {}).get("displayName")) or "unknown"
    if _paths_cache is None:
        import gzip
        _paths_cache = json.loads(gzip.decompress(_get(OBJ_PATHS)))
    path = _paths_cache.get(uid)
    if not path:
        raise RuntimeError(f"uid {uid} 不在 Objaverse 的 object-paths 里")
    return (_get(OBJ_GLB.format(path=path)), "glb", lic, author), {}


# ---------------------------------------------------------------- 主流程
def fetch_one(key: str, spec: dict) -> dict:
    src = spec["source"]
    (data, ftype, actual_lic, author), extra = (
        _polyhaven(spec) if src == "polyhaven" else _objaverse(spec))

    # ⛔ 许可闸 —— 两道：上游实际许可必须在白名单里，且必须和登记表声明的一致
    if actual_lic not in LICENSE_ALLOWLIST:
        raise PermissionError(
            f"{key}（{src}:{spec['source_id']}）上游许可是 {actual_lic}，"
            f"不在白名单 {sorted(LICENSE_ALLOWLIST)} 里——拒绝写入")
    if actual_lic != spec["license"]:
        raise PermissionError(
            f"{key} 登记表写的是 {spec['license']}，上游实际是 {actual_lic}"
            f"——不一致，拒绝写入（可能是作者改了许可）")

    sc = convert.load_scene(data, ftype) if not extra else _load_with_assets(data, extra)
    if "target" in spec:
        convert.scale_to(sc, spec["target"]["axis"], spec["target"]["metres"])
    out = os.path.join(ASSET_DIR, key)
    os.makedirs(out, exist_ok=True)
    parts, tris = [], 0
    mesh_parts, real_size = convert.parts(sc, spec["max_tris"])
    for i, (mesh, png, off, half) in enumerate(mesh_parts):
        obj = convert.export_obj(mesh)
        open(os.path.join(out, f"p{i}.obj"), "wb").write(obj)
        rec = {"obj": f"p{i}.obj", "tris": len(mesh.faces), "sha256": _sha(obj),
               "offset": [round(v, 5) for v in off], "half": [round(v, 5) for v in half]}
        if png:
            open(os.path.join(out, f"p{i}.png"), "wb").write(png)
            rec["png"] = f"p{i}.png"
        parts.append(rec)
        tris += len(mesh.faces)
    # ⛔ 尺寸必须取**导出产物的**包围盒，不是 sc.extents——
    #    后者是变换前的场景范围，和写出去的 OBJ 对不上（碗因此在场景里立了起来）。
    size = list(real_size)
    with open(os.path.join(out, "LICENSE.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{spec.get('label', key)}\n来源：{src} / {spec['source_id']}\n"
                 f"作者：{author}\n许可：{actual_lic}\n"
                 f"加工：Y-up→Z-up、按材质拆成单网格 OBJ、减面到 {spec['max_tris']} 面/组、居中\n")
    return {"source": src, "source_id": spec["source_id"], "license": actual_lic,
            "author": author, "label": spec.get("label", key),
            "parts": parts, "tris": tris, "size": [round(v, 4) for v in size]}


class _MemResolver:
    """内存里的伴生文件表。

    ⚠️ Poly Haven 发的是 `.gltf` + 分离的 `.bin` + `textures/`，**不是单文件 .glb**。
       trimesh 载入时会回头找这些伴生文件，得给它一个 resolver。
       用最小的字典式实现而不是 ZipResolver——后者要的是路径/字节流，不是 ZipFile 对象，
       传错了报的是 `argument of type 'ZipFile' is not iterable`，跟根因半点关系没有。
    """

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def get(self, name):
        import urllib.parse
        key = os.path.basename(urllib.parse.unquote(str(name).split("?")[0]))
        if key not in self.files:
            raise KeyError(f"伴生文件缺失：{name}（有 {sorted(self.files)[:6]}）")
        return self.files[key]

    # ⚠️ trimesh 的 glTF 加载器用的是**下标**访问（`resolver[name]`），不是 `.get()`。
    #    只实现 get 会报 "'_MemResolver' object is not subscriptable"——
    #    这个报错跟"伴生文件"半点关系没有，光看它想不到根因。
    __getitem__ = get

    def __contains__(self, name):
        return os.path.basename(str(name)) in self.files

    def namespaced(self, _prefix):
        return self


def _load_with_assets(gltf_bytes: bytes, extra: dict):
    import io as _io
    import trimesh
    sc = trimesh.load(_io.BytesIO(gltf_bytes), file_type="gltf",
                      resolver=_MemResolver(extra), force="scene")
    sc.apply_transform(convert._rot_x90())      # ⛔ Y-up → Z-up
    return sc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--only", nargs="*", help="只处理这几个 key")
    a = ap.parse_args()
    lock = json.load(open(LOCK)) if os.path.exists(LOCK) else {}
    keys = a.only or list(ASSETS)

    if a.verify:
        bad = 0
        for k in keys:
            rec = lock.get(k)
            if not rec:
                print(f"  ⛔ {k} 不在 lock 里"); bad += 1; continue
            for p in rec["parts"]:
                fp = os.path.join(ASSET_DIR, k, p["obj"])
                ok = os.path.exists(fp) and _sha(open(fp, "rb").read()) == p["sha256"]
                if not ok:
                    print(f"  ⛔ {k}/{p['obj']} 缺失或校验不过"); bad += 1
        print("全部一致" if not bad else f"⛔ {bad} 项不一致")
        return

    os.makedirs(ASSET_DIR, exist_ok=True)
    for k in keys:
        if k in lock and not a.force and os.path.isdir(os.path.join(ASSET_DIR, k)):
            print(f"   跳过 {k}（已有）"); continue
        try:
            rec = fetch_one(k, ASSETS[k])
        except PermissionError as exc:
            print(f"   ⛔ 许可闸拦下 {k}：{exc}"); continue
        except Exception as exc:                       # noqa: BLE001
            print(f"   ⛔ {k} 失败：{type(exc).__name__} {str(exc)[:120]}"); continue
        lock[k] = rec
        print(f"   {k:14s} {rec['license']:12s} {len(rec['parts'])} 部件 "
              f"{rec['tris']:7d} 面  尺寸 {rec['size']}")
    json.dump(lock, open(LOCK, "w"), indent=2, ensure_ascii=False, sort_keys=True)
    _write_attribution(lock)
    print(f"清单 {LOCK}（{len(lock)} 项）；署名 {ATTRIB}")


_RC_REPO = "nvidia/PhysicalAI-Robotics-Manipulation-Objects-Kitchen-MJCF"


def _count_tris(key: str, rec: dict) -> int:
    """从落盘的 OBJ 数面数。给 lock 里没有 `tris` 字段的资产（RoboCasa 那几件）用。"""
    import os
    n = 0
    for part in rec.get("parts", []):
        path = os.path.join(ASSET_DIR, key, part["obj"])
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="ignore") as f:
                n += sum(1 for ln in f if ln.startswith("f "))
    return n


def _write_attribution(lock: dict) -> None:
    lines = ["# 装饰网格的来源与许可\n",
             "⛔ 本文件由 `python -m decor.fetch` 自动生成，请勿手改。\n",
             "本仓的 MIT 许可**不覆盖**下列第三方资产；每件的许可见各自目录的 LICENSE.txt。\n",
             "所有资产都经过：Y-up→Z-up、按材质拆成单网格 OBJ、减面、居中。\n",
             "| 资产 | 来源 | 作者 | 许可 | 面数 |", "|---|---|---|---|---|"]
    for k in sorted(lock):
        r = lock[k]
        # ⚠️ `author` / `tris` 只有走本文件这条管线的资产才有。RoboCasa 的电器是
        #    `decor/robocasa.py` **直接写进 lock 的**（绕过 manifest 与本文件），没有这两个字段。
        #    ⛔ 2026-08-08 之前这里无条件取 `r['author']`，于是每次 `python -m decor.fetch`
        #    都在**写完 lock 之后**崩在 KeyError 上——lock 是对的，署名表却一直没更新，
        #    而且屏幕上先打完一整张成功汇总表才抛异常，很容易被当成"跑完了"。
        author = r.get("author") or "—"
        tris = r.get("tris") or _count_tris(k, r)
        lines.append(f"| {r['label']} | {r['source']} / `{r['source_id']}` | "
                     f"{author} | **{r['license']}** | {tris} |")
    # ⭐ RoboCasa 那几件的**出处与移植口径**也由这里生成。
    #    ⛔ 2026-08-08 之前这一段是手写贴在文件末尾的，而文件头就写着"自动生成，请勿手改"——
    #    等哪天 fetch 真的跑通（在此之前它每次都崩在 KeyError 上），这段就会被整段抹掉，
    #    而它承载的是 **CC-BY 要求的署名**。手写内容放在自动生成的文件里，迟早会丢。
    if any(r.get("source") == "robocasa" for r in lock.values()):
        lines += ["", "## 厨房电器的出处（RoboCasa / NVIDIA 镜像）", "",
                  f"来源：HuggingFace 数据集 `{_RC_REPO}` 的 `fixtures_lightwheel/` 目录，**CC-BY-4.0**。",
                  "移植器 `decor/robocasa.py` **只取视觉网格与贴图**，不引入任何 "
                  "`<joint>` / `<actuator>` / `<option>`——实测移植前后 `nu=29 nq=36 nv=35` 逐位不变。"]
    open(ATTRIB, "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
