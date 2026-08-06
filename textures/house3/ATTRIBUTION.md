# house3 窗景贴图的来源与许可

本目录的贴图由仓库根的 `make_view.py` 生成。**本仓的 MIT 许可不覆盖第三方素材**，
逐项来源如下。

## park_aerial.png · city_ground.png

**来源**：USGS NAIP（National Agriculture Imagery Program）正射影像，经由
[The National Map ImageServer](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer)
取得（`exportImage`，EPSG:3857）。

**许可**：**公共领域（Public Domain）**。NAIP 影像是美国联邦政府（USDA）的作品，
按 17 U.S.C. §105 不受版权保护。署名不是法律义务，但作为惯例我们照旧注明来源。

**做过的加工**（如实登记）：
1. 以中央公园中心（40.7824, −73.9657）为心抓取正方形区域；
2. **旋转 29.05°** —— 曼哈顿街网偏东约 29°，公园在正射影像里是斜的，
   而场景里公园是正南北。旋转角由公园南北界中点的经纬度算出，不是目测的；
3. 按 `PARK_W × PARK_L` 裁出公园条带；城市底图另抓 16000 m 见方；
4. 城市底图外圈叠加了一层向天空色渐隐（地平线雾），⚠️ 这是我们加的，不是影像原貌。

**为什么选它**：全网不存在宽松许可的、从高层俯瞰中央公园的 360° 全景照片
（Wikimedia 的等距柱状投影全景分类共 543 张，没有一张美国大城市）。
而正射影像恰好是**俯视**的——正是本方案唯一需要照片的朝向，也正是许可最干净的那一类。

## sky_file*.png（天空盒六面）

**来源**：Poly Haven HDRI `kloofendal_48d_partly_cloudy_puresky`，取其**已色调映射的 8 位 JPG**
（`https://dl.polyhaven.org/file/ph-assets/HDRIs/extra/Tonemapped%20JPG/<id>.jpg`）。

**许可**：**CC0**。Poly Haven 原文："You do not need to give credit or attribution when using
them (although it is appreciated)."

**做过的加工**（如实登记）：
1. ⛔ **横向旋转 180°** —— 这张是南非拍的（纬度约 −26°），**南半球正午太阳在北**。
   本场景朝北看公园，不转的话中央公园正上方会挂一个 40.77°N 任何时刻都不可能出现的太阳。
2. 等距柱状 → 六个 90° 视场的立方面，2048 px/面。
   ⛔ **面到世界方向的对应是实测出来的**（`make_view.SKY_FACE_FOR_DIR`）：
   相机朝 +X 看到的是 `L` 面、朝 +Z 看到的是 `D` 面——**up↔down、left↔right 全部对调**。
   照 MuJoCo 文档的字面命名去填，天空会上下翻转 + 左右镜像，**而且渲染出来照样很好看**。

## h3_*.png（室内材质 9 张）

**来源**：[ambientCG](https://ambientcg.com/)，资产号、SHA-256 与选择理由逐条记在
同目录的 `materials.lock.json`；下载脚本是仓根的 `fetch_assets.py`。

**许可**：**CC0 1.0**。ambientCG 原文："You can copy, modify, distribute and perform the assets,
even for commercial purposes, all without asking permission."

**做过的加工**：只取 Color（albedo）那一张；缩到 1024²；转 8 位 sRGB PNG。
⚠️ 没有下法线/粗糙度贴图——MuJoCo 内置渲染器是 Blinn-Phong，那些吃不吃是版本相关的。

## facade_glass.png · facade_limestone.png

程序化生成（`make_view.facade_cube()`），无外部素材，**随本仓 MIT**。
⚠️ 是 3×4 的立方网格图（`gridlayout=".U..LFRB.D.."`），**顶面单独给了屋顶贴图**——
单文件 cube 会把窗格也贴到顶上，而这场景是从 62 层往下看，矮楼全戴着窗格当屋顶。

## scenes/house3/nyc_massing.py（不在本目录，但一并登记）

**来源**：NYC Open Data 建筑轮廓（数据集 `5zhs-2jue`，DoITT 航测），2716 栋。
**许可**：纽约市 **Local Law 11 of 2012**（Admin Code §23-502(d)）——"数据集必须无注册、
无许可、无使用限制"，**没有 share-alike**；再发布须注明来源、版本与改动。
⚠️ 它没有 SPDX 可写的许可标识，所以这里记法条引用。
**做过的加工**：经纬度 → 以本楼为原点的场景坐标（按公园长轴 29.05° 转正）、取轮廓的
轴对齐包围盒、高度 = (ground_elevation + height_roof) 英尺换算成米再减去本层离街面的高度。
⛔ 只保留五个数，多边形用完即弃。

## calib_*.png（若存在）

天空盒方向标定用的纯色面，程序化生成，**随本仓 MIT**。用完即可删。

---

⚠️ 重新生成：`python make_view.py --all`（需联网抓 NAIP）。
不联网时 `python make_view.py --procedural` 出一套程序化的兜底贴图，质量差很多但不依赖网络。
