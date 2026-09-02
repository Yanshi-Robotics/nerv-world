# AGENTS.md · 本仓的 agent 入口

先读这一份，然后直接跳到你这次要用的那一节——不必通读。

## 这个仓是什么（以及不是什么）

**alice-house** = 一套**用代码生成**的室内仿真场景资产库 + 两台机器人模型 + 训练好的运动策略。
改屋子只改一份布局定义再重跑生成器，场景与消费方读的是同一份真相源，坐标不可能在两处对不上。

它**不是**：

- **不是应用**：没有运行期服务、没有 API、没有用户输入——它是**别的项目 import 的资产**。
  主要消费方：[anima-zero](https://github.com/Yanshi-Robotics/anima-zero) 的 `sim-house-nav` 世界。
- **不是训练仓**：这里只**装**训练产物（ONNX + 契约），训练本身在
  [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion)。
- **不是给某一台机器人定制的考题**：场景是「现实」，四足眼高约 0.4 m、人形约 1.25 m，
  谁看不见高处是**机器人侧**的局限，不是场景要迁就的事。
- **不是素材库**：外部网格与贴图的**字节一件都不入库**。`decor/` 与 `make_view.py` 是
  「拉取 + 转换」的脚本，字节落在 gitignore 的目录里。裸 clone 照样能生成全部场景。

现有四个地方：**house1** 单层大平层（考平层导航）、**house2** 三层带楼梯（考爬楼）、
**apt1** 62 层曼哈顿大平层（**考窗外**——三面落地玻璃，看得见但够不着）、
**apt2** 62–63 层复式顶层豪宅（**考够得着**——家具有真碰撞，沙发机器人真坐得下）。

## 任务 → 去哪查

| 你想…… | 改 / 读 | 为什么是这个 |
|---|---|---|
| 改屋子（房间、门窗、家具、出生点） | `scenes/<场景>/layout.py`，然后重跑 `tools/make_house.py --scene <场景>` | `build/<场景>-<机器人>.xml` 是**产物**，手改会被下一次重跑覆盖 |
| 加一个新地方 | `scenes/manifest.py` 追加一条 + 建 `scenes/<key>/layout.py` | 变体名与产物名的规则住 `scenes/manifest.py`，⛔ 别在别处再拼一份 |
| ⭐ 让某件家具有**真碰撞**（不是一个实心盒） | 在 `decor/hulls.py` 的 `COLLIDE` 里登记 → 跑 `python -m decor.hulls`（要先 `pip install coacd trimesh`） → layout 里给它 `F.mesh_piece(..., collide=True)` | 部件是**按材质**拆的、MuJoCo 又只取凸包，所以"把 contype 打开"没用（实测凸度只有 0.12–0.30）。⛔ 凸块必须带 `solref`，否则快速撞击穿模而慢速测试全绿 |
| ⭐ 让机器人**坐得下**某件家具 | layout 里加 `SEATS` 条目；沙发用 `F.sofa()` 手写基本体（⛔ 别用真网格） | 座面高上限 **0.36 m** 是从 G1 腿长实测出来的（0.40 滑落 / 0.45 直接倒）；而 `_fit_scale` 只做均匀缩放，压座面会把整件缩成玩具 |
| ⭐ 摆一个姿态出图 / 做判据 | layout 的 `SIT_POSES`（**按关节名**）+ `scenes/apply_pose.py` | 产物里的机器人站在世界原点，静态渲染拍不到"坐着"；⛔ 按下标声明会随机器人型号静默错位 |
| ⛔ 改楼梯 | **先读 [`scenes/house2/楼梯设计.md`](scenes/house2/楼梯设计.md)**，再改 `layout.py` 顶部那几个参数 | 一部双跑楼梯 = 五段、其中两段是平台；踏板数 = 踢面数−1。这两条都栽过跟头，尺寸全是推出来的，单独改一个会让别处悄悄对不上 |
| 自己进去看看 | `python tools/walkthrough.py --scene house2`（`T` 透视 / `F` 飞行 / 数字键跳层） | 第一人称漫游，带碰撞与重力；`--selftest` 是不开窗口的自动版 |
| 场景改完验一下 | `python tools/check_scene.py` | 它**查产物不查声明**（射线实测楼梯能不能走），必跑 |
| 摆家具怕挡路 | 摆完跑一次 `check_scene.py` 看「可通行性」那项 | 判据是**整层只准有一个连通块**——⛔ 不是"两件家具之间多宽"，那种问法会被床头柜↔床炸出上百条假阳性 |
| 机器人该站哪 | layout 的 `ROBOT_HOME_XY` / `ROBOT_HOME_YAW`（「保姆间」） | ⛔ 和 `START_POS_XY`（任务出生点）是两个量，别合并 |
| 知道某台机器人是什么（模型 / 出生高度 / 相机 / 脚的 body） | `robots/manifest.py` | 机器人事实的**单一真相源** |
| 知道某个策略怎么用 | ⛔ **不在本仓**（2026-09-02 起）：策略住消费方的发布架，`contract.json` + `release.yaml` | 本仓只放场景与本体 |
| 换 README 里的配图 | `tools/make_docs_images.py` 里的机位，然后重跑它 | 图不许手工截，机位是代码 |
| 加或改家具几何 | `scenes/furniture.py` | 家具零件的生成函数都在这 |
| 改贴图 | `tools/make_textures.py` | 贴图是生成物，不是素材库 |
| 加一张新贴图 | 放 `textures/`，**做成正方形** | ⛔ 贴到基本体上的必须是 `type="cube"`（2d 在竖直面上会被沿局部 Z 拖成条纹）；而 cube 要求 PNG 是 gridsize 的整数倍，非方形会**编译期报错**。生成器按图片实际尺寸自动判，不用手写名单 |
| ⛔ 给家具穿真网格外衣 / 加装饰资产 | `decor/manifest.py` 登记 → `python -m decor.fetch` → **`python -m decor.calibrate`** → layout 里改用 `F.mesh_piece(...)` | 网格是**外衣**，碰撞真相仍是原来的盒子；漏跑 calibrate 网格会摆偏、被射线自检判红（见红线一节） |
| 改 apt1 的窗外景色（天空 / 建筑群 / 航拍） | `tools/make_view.py`（`--sky` / `--nyc` / `--naip`），产物落 `textures/house3/` 与 `scenes/apt1/nyc_massing.py` | ⛔ 天空盒六面到世界方向的对应是**实测**出来的、而且全是反的，改之前先跑 `--calib` |
| 加厨房电器 | `decor/robocasa.py` 里的 `FIXTURES` 换型号，`--list` 看有哪些 | ⛔ 不能直接 `<include>` 那份 MJCF：它会**撞 body 名**（每件电器根 body 都叫 `object`）、用 `<option>` 静默覆盖积分器设置、撞 `<default>` 类名。⚠️ 但"`nu`/`nq`/`nv` 一变就坏"这半句**实测不成立**——消费方是按关节名与传动目标建映射的（apt2 加了 184 个碰撞 geom，`nu` 仍是 29） |
| 看版本改了什么 | [`CHANGELOG.md`](CHANGELOG.md) | 本仓已公开、有外部消费方，CHANGELOG 是写给使用者的 |

## 目录地图

| 路径 | 装什么 |
|---|---|
| `scenes/manifest.py` | **有哪些地方**（与 `robots/manifest.py` 成对：那边是有哪些身体）。两者正交，交叉组合生成 |
| `scenes/<场景>/layout.py` | **那个地方的唯一布局定义**：房间矩形、门窗洞、家具摆位、出生点；多层场景另有楼层与楼梯 |
| `tools/check_scene.py` | 场景自检：能不能被 MuJoCo 加载、**整条上楼路线走不走得通**、四个接头闭不闭合、门够不够宽、⭐ **每间屋机器人走不走得进去** |
| `tools/walkthrough.py` | 第一人称漫游（WASD + 鼠标），用来人眼验收；`--selftest` 无窗口自测 |
| `scenes/furniture.py` | 家具/零件的几何生成函数（所有场景共用） |
| `tools/make_house.py` | 布局 → MJCF 场景生成器（**一个「场景 × 机器人」组合一份文件**） |
| `tools/make_textures.py` · `tools/make_docs_images.py` | 贴图生成 · README 配图渲染（机位写在代码里） |
| `tools/make_view.py` | **apt1 的窗景**：`--sky --sky-phase` 天空六面（分时段）· `--nyc` 2716 栋真实曼哈顿建筑 · `--naip` 中央公园航拍 · `--calib` 天空盒定向标定 |
| `tools/make_time_stills.py` · `scenes/apply_time_preset.py` | **apt1 的四时段**：前者出 `T-*.png` 静帧并给预设把门（亮度单调下降）；后者是「灯怎么打」的唯一应用逻辑（运行期写字段，产物不变） |
| `tools/fetch_assets.py` | 下载 CC0 室内材质（ambientCG），带 SHA-256 记账与 `--verify` |
| `decor/` | **真家具网格管线**：`manifest.py` 登记表 + 可执行许可白名单、`fetch.py` 下载转换、`convert.py` glTF→OBJ、`calibrate.py` ⛔ 实测重心、`robocasa.py` 厨房电器移植器、⭐ `hulls.py` **CoACD 凸分解出真碰撞体**、`lock.py` 只读访问器（stdlib，生成器 import 它）。⛔ `decor/assets/` 的字节 gitignore，永不入库（凸块也一样） |
| `scenes/apply_pose.py` | ⭐ 把 layout 的 `SIT_POSES`（**按关节名**声明）装到机器人身上并**推物理到稳态**。产物里没有关键帧、也不该有——`make_house.py` 有意不 import mujoco |
| `scenes/apt1/nyc_massing.py` | 由 `make_view.py --nyc` 生成的建筑体量表（**入库**，因为数据源无 share-alike） |
| `build/<场景>-<机器人>.xml` | **产物**（入库的交付物，不是构建缓存）：完整可跑场景，含屋外景色 + `<include>` 进来的那台机器人。⛔ 里面的相对路径按"住在仓根下恰好一层"算死了，别把 `build/` 挪走 |
| `robots/manifest.py` | 机器人清单与事实源；`robots/g1/`、`robots/go2/` 是模型资产 |
| `textures/` · `docs/` | 生成出来的贴图 · 配图与文档。⚠️ apt1 的贴图住 `textures/house3/`、材质名带 `h3_` 前缀 —— 那是这个场景的**资产命名空间**，沿用它最早的名字，有意不跟着 key 改 |

## 怎么跑起来

```bash
pip install mujoco numpy pillow

python -m mujoco.viewer --mjcf=build/house1-go2.xml   # 单层大平层（四足那份）
python -m mujoco.viewer --mjcf=build/house2-g1.xml    # 三层小楼带楼梯（人形那份）
python -m mujoco.viewer --mjcf=build/apt1-g1.xml   # 62 层俯瞰中央公园（人形那份）

python tools/make_textures.py        # 改过贴图才需要
python tools/make_house.py                       # 全场景 × 全机器人
python tools/make_house.py --scene house2 --robot g1
python tools/check_scene.py                      # ⭐ 生成之后必跑
python tools/walkthrough.py --scene house2       # 自己走进去看（--selftest = 无窗口自测）
ALICE_SCENE=house2 python tools/make_docs_images.py   # 重出 README 配图
python tools/make_time_stills.py --scene apt1         # 四时段静帧（同时是验收门）
```

apt1 的贴图与 2716 栋楼**已入库**，clone 下来直接能编译；下面这些只在想改它们时才跑。
⚠️ **家具网格是例外**：字节永不入库，裸 clone 上 apt1 的家具是素盒子，直到你拉下来。

```bash
pip install trimesh fast-simplification   # 只有下载/转换那一侧要它，⛔ 生成器不许 import

python tools/fetch_assets.py            # CC0 室内材质
python tools/make_view.py --all         # 天空六面 · 公园航拍 · 2716 栋楼
python -m decor.fetch             # 家具网格（Poly Haven CC0 + Objaverse CC-BY，逐件核许可）
python -m decor.robocasa          # 厨房电器（RoboCasa，CC-BY-4.0）
python -m decor.calibrate         # ⛔ 上面两条只要跑过，这条必跑（见红线）
```

**要让机器人真走起来**：策略不在本仓。消费方（如 NERV）从自己的策略发布架拿 `policy.onnx`，
严格照同目录 `contract.json` 拼观测、按 `release.yaml` 里的力矩模式发力矩；场景与本体则通过
环境变量（如 `ALICE_HOUSE_ROOT`）指到本仓，不写死路径。

## 红线（改之前必看）

### ⛔ 几何不手写

`<场景>-<机器人>.xml` 是**产物**，不许手改。改屋子只改对应的 `scenes/<场景>/layout.py`
再重跑 `make_house.py`。改完跑 `check_scene.py`——它查的是产物，不是你在布局里的声明。
手改产物的下场：下一次重跑就被覆盖，而且场景与消费方的坐标真相源从此分叉。

同理，README 的配图不许手工截——机位写在 `make_docs_images.py` 里，改了场景重跑那个脚本。

### ⛔ 单一真相源，谁也别抄谁

| 事实 | 住哪儿 | 别在哪儿重复 |
|---|---|---|
| 房间矩形 / 门窗 / 家具 / 出生点 | `scenes/<场景>/layout.py` | 别写进产物 xml |
| 有哪些场景、产物叫什么名字 | `scenes/manifest.py` | 消费方也调它的 `scene_filename()`，⛔ 两边别各拼各的 |
| 机器人是什么（模型/出生高度/相机/脚的 body） | `robots/manifest.py` | 别写进消费方的代码 |
| 关节顺序 / 增益 / 观测格式 / 控制周期 / 力矩模式 | 消费方发布架里各策略的 `contract.json` + `release.yaml` | **别抄进 manifest**——本仓不存策略 |

### ⛔ 力矩模式跟着策略走，不在本仓

Go2 是显式 PD（部署器自己算 `−kd·qd`、模型阻尼清零），G1 是隐式 PD
（`kd` 写进 `dof_damping`、力矩只发 `kp` 那项）。这是**训练侧的事实**，2026-09-02 起随策略
住在消费方发布架的 `release.yaml`（`pd_mode`）里；凭印象填会让机器人在部署里 1 秒内倒。
⚠️ `tools/make_docs_images.py` 的坐姿沉降需要一份契约，用 `ALICE_HOUSE_CONTRACT_JSON` 指过去。

### ⛔ 第三方资产的许可不许动

`robots/go2/` 与 `robots/g1/` 来自 MuJoCo Menagerie（BSD-3-Clause）。
许可文件、来源说明（`G1_MODEL_UPSTREAM.md`）必须随资产一起留在仓里。
G1 是用 `import_from_menagerie.py` 导入的——**改上游模型走那个脚本**，别手改 `g1.xml`。

⛔ **装饰网格的字节一律不入库。** `decor/manifest.py` 里的许可白名单是**可执行代码**：
上游许可不在白名单里，`decor/fetch.py` 直接拒绝写入，不是打个警告了事。
⚠️ Objaverse 的许可**不是一律 CC-BY**（调研时第二个沙发就撞上 `by-nc`），
而且 **Sketchfab 的 search 接口返回的 license 是 `None`**——必须逐个查
`api.sketchfab.com/v3/models/<uid>` 拿真 slug。加资产时别跳过这一步。

⛔ **建筑数据别改用 OpenStreetMap。** 覆盖率相当，但把派生出来的坐标表提交进 MIT 仓
构成 ODbL 的「派生数据库」，share-alike 会附着到 `scenes/apt1/nyc_massing.py` 上。
现用的 NYC Open Data 走 Local Law 11 of 2012，**没有 share-alike**。

### ⛔ 装饰网格是外衣，不许碰碰撞

apt1 的家具在原来的盒子外面套了一张真网格。规矩只有一条：
**网格必须完全装进它所装饰的盒子**，于是所有射线读数逐位不变。
`check_decor_ray_invariance` 强制这一条——**它判不过就不许放行**。

- ⛔ **`mj_ray` 不看 `contype`**。「纯视觉」对物理成立、对射线不成立，
  而消费方的雷达和导航探测走的都是 `mj_ray`。
- ⛔ **隐藏碰撞盒只能用 `group`（本仓用 4，见下表），绝不能把 rgba 的 alpha 设成 0**——
  实测 alpha=0 会让 `mj_ray` **跳过**这个 geom，碰撞盒被悄悄挖空，而编译不报错。
- ⛔⛔ **geom 分组是本仓与消费方共用的一张表，房子这边只准用 0 / 1 / 4 / 5**：

  | 组 | 归谁 | 画不画 |
  |----|------|--------|
  | 0 | 房子可见部分（墙 / 地板 / 门窗框 / 玻璃 / 裸家具 / 装饰网格） | 画 |
  | 1 | 天花板（各场景 layout 的 `CEILING_GROUP`） | 画 |
  | **2 / 3** | ⛔ **机器人**的视觉 / 碰撞网格（MuJoCo Menagerie 惯例）—— 房子不许占 | 2 画、3 不画 |
  | 4 | 房子的隐身碰撞盒（`make_house.HIDDEN_BOX_GROUP`） | 不画 |
  | 5 | 预留 | 不画 |

  `group` 在 MuJoCo 里本来只管**画不画**，但消费方（anima-zero 的 sim-house-nav）还得靠它把
  「机器人自己」和「房子」分开——它的激光测距要滤掉打在自己身上的射线，而 `mj_ray` 的过滤接口
  **只吃一个 6 位分组掩码**，没法按 geom 或 body 子树过滤。占了 2 或 3，消费方的自检会**当场拒绝启动**。
  ⛔ 硬上界 **≤ 5**：分组掩码固定 6 个槽，≥6 会被静默丢掉，那些碰撞盒对激光就成了透明的——
  和 alpha=0 是同一类坑，但连报错都没有。
- ⛔ **网格探出盒子时，把盒子改大没有用**：包含性缩放会把网格按比例一起撑大，
  超出量原封不动。**也不要去拧缩放系数**——那只是把问题挪到下一件资产。
  正确的排查顺序是照着两道闸门走：
  1. `check_lock_reconciles` 红 → lock 里的包围盒本身就错了，重跑 `python -m decor.calibrate`；
  2. `check_decor_inside_box` 红 → 缩放或摆位错了，去看 `make_house` 的
     `_asset_span()`（跨度算对没有）和 `_decor_geoms()`（偏移加了几遍）。
- ⚠️ **碰撞盒的比例要贴近网格自己的比例。** 缩放是均匀的、按三轴最紧的一比取值，
  盒子哪一维偏瘦整件就照那一维缩。（实测：条案网格 2.44×0.52×0.68 塞进
  1.40×0.38×0.84 的盒子，只剩 57%，盒子里空一大截。）
- ⚠️ **只有 `contype=0` 且 `conaffinity=0` 时 MuJoCo 才完全跳过 qhull**——
  任何一个非零都会为每张网格建凸包。这一对属性是整件事便宜的唯一原因。

### 提交纪律

- 本仓是公开作品集，**commit 不带 `Co-Authored-By`**；push 由作者发话。
- 显式 `git add`，别 `git add -A`（工作区里有不入库的本地笔记）。
- 目录一动，所有 `..` 相对路径重新数一遍。
  （2026-07-26 真踩过：场景目录扁平化后 `make_docs_images.py` 的输出路径还是 `../docs/images`，
  配图被写到仓库外面去了，脚本照常打印"完成"、README 的图一张没更新。）

---

## 上游共享规范（版本锚点）

本仓继承 `agent-rules` 的共享规范，**固定在 release tag，不指向 `main`**：

- `agent-rules` version: **`v0.4.0`**
- machine entry: [agent-rules/AGENTS.md](https://github.com/jeffliulab/agent-rules/blob/v0.4.0/AGENTS.md)
- 检索索引（会话开始加载一次）: [`_skeleton.md`](https://github.com/jeffliulab/agent-rules/blob/v0.4.0/_skeleton.md)

读法：先读本文件（项目级覆盖）→ 再按上游 machine entry 的协议加载 `_skeleton.md`、**按需**取节点
（别批量预载，≤5 个）→ 上游读完之后**本仓规则优先**。与本仓相关的上游节点：`global`、
`workflows.git`、`workflows.github`（本仓是公开仓）、`principles.engineering`。
⚠️ 本仓**不是** ROS 2 项目，也不是训练项目，`stacks.robotics` / `stacks.python-ml`
只在真的动到策略训练时才需要。升级 = 改上面那个 tag，然后拿新版本校一遍本仓。

### 与上游规范的偏离（明确登记）

| 上游规则 | 本仓怎么做 | 为什么 |
|---|---|---|
| 根目录必备 `.env.example` | **不设** | 本仓是纯资产库，没有任何运行期环境变量。放一个空文件是仪式，不是规范。 |
| pre-1.0 走 rapid-versioning 三件套 | **用 `CHANGELOG.md`**（Keep a Changelog） | 本仓已公开、有外部消费方，CHANGELOG 是写给使用者看的；三件套是写给自己看的。规范允许就近覆盖。 |
| `stacks/python-ml.md` 的训练目录约束 | 不适用 | 本仓只**装**训练产物（ONNX + 契约），训练本身在 [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion)。 |

---

本地工作副本里若有同目录 `CLAUDE.md`，请一并阅读——那是作者的内部开发笔记，有意不入库。
