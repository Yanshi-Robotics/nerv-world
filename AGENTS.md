# AGENTS.md · 本仓的 agent 入口

先读这一份，然后直接跳到你这次要用的那一节——不必通读。

## 这个仓是什么（以及不是什么）

**alice-house** = 一套**用代码生成**的室内仿真场景资产库 + 两台机器人模型 + 训练好的运动策略。
改屋子只改一份布局定义再重跑生成器，场景与消费方读的是同一份真相源，坐标不可能在两处对不上。

它**不是**：

- **不是应用**：没有运行期服务、没有 API、没有用户输入——它是**别的项目 import 的资产**。
  主要消费方：[anima-zero](https://github.com/jeffliulab/anima-zero) 的 `sim-house-nav` 世界。
- **不是训练仓**：这里只**装**训练产物（ONNX + 契约），训练本身在
  [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion)。
- **不是给某一台机器人定制的考题**：场景是「现实」，四足眼高约 0.4 m、人形约 1.25 m，
  谁看不见高处是**机器人侧**的局限，不是场景要迁就的事。

## 任务 → 去哪查

| 你想…… | 改 / 读 | 为什么是这个 |
|---|---|---|
| 改屋子（房间、门窗、家具、出生点） | `scenes/<场景>/layout.py`，然后重跑 `make_house.py --scene <场景>` | `<场景>-<机器人>.xml` 是**产物**，手改会被下一次重跑覆盖 |
| 加一个新地方（house3…） | `scenes/manifest.py` 追加一条 + 建 `scenes/<key>/layout.py` | 变体名与产物名的规则住 `scenes/manifest.py`，⛔ 别在别处再拼一份 |
| 场景改完验一下 | `python check_scene.py` | 它**查产物不查声明**（射线实测楼梯能不能走），必跑 |
| 知道某台机器人是什么（模型 / 出生高度 / 相机 / 力矩模式） | `robots/manifest.py` | 机器人事实的**单一真相源** |
| 知道某个策略怎么用（关节序 / 增益 / 观测布局 / 控制周期） | `policies/<名字>/contract.json` | 契约是策略侧的单一真相源，**别抄进 manifest** |
| 换 README 里的配图 | `make_docs_images.py` 里的机位，然后重跑它 | 图不许手工截，机位是代码 |
| 加或改家具几何 | `furniture.py` | 家具零件的生成函数都在这 |
| 改贴图 | `make_textures.py` | 贴图是生成物，不是素材库 |
| 看版本改了什么 | [`CHANGELOG.md`](CHANGELOG.md) | 本仓已公开、有外部消费方，CHANGELOG 是写给使用者的 |

## 目录地图

| 路径 | 装什么 |
|---|---|
| `scenes/manifest.py` | **有哪些地方**（与 `robots/manifest.py` 成对：那边是有哪些身体）。两者正交，交叉组合生成 |
| `scenes/<场景>/layout.py` | **那个地方的唯一布局定义**：房间矩形、门窗洞、家具摆位、出生点；多层场景另有楼层与楼梯 |
| `check_scene.py` | 场景自检：能不能被 MuJoCo 加载、楼梯能不能走通、门够不够宽 |
| `furniture.py` | 家具/零件的几何生成函数 |
| `make_house.py` | 布局 → MJCF 场景生成器（**一个「场景 × 机器人」组合一份文件**） |
| `make_textures.py` · `make_docs_images.py` | 贴图生成 · README 配图渲染（机位写在代码里） |
| `house1-g1.xml` · `house2-g1.xml` … | **产物**：完整可跑场景（含屋外景色 + `<include>` 进来的那台机器人） |
| `robots/manifest.py` | 机器人清单与事实源；`robots/g1/`、`robots/go2/` 是模型资产 |
| `policies/<名字>/` | 训练好的 `policy.onnx` + 与它配套的 `contract.json` |
| `textures/` · `docs/` | 生成出来的贴图 · 配图与文档 |

## 怎么跑起来

```bash
pip install mujoco numpy pillow

python -m mujoco.viewer --mjcf=house1-go2.xml   # 单层大平层（四足那份）
python -m mujoco.viewer --mjcf=house2-g1.xml    # 三层小楼带楼梯（人形那份）

python make_textures.py        # 改过贴图才需要
python make_house.py                       # 全场景 × 全机器人
python make_house.py --scene house2 --robot g1
python check_scene.py                      # ⭐ 生成之后必跑
python make_docs_images.py     # 重出 README 配图
```

**要让机器人真走起来**：拿 `policies/<名字>/policy.onnx`，严格照同目录 `contract.json` 拼观测、
按契约里的增益发力矩。消费方通常不把本仓当路径写死，而是通过 `HOUSENAV_ASSETS_ROOT` 指到这里。

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
| 机器人是什么（模型/出生高度/相机/力矩模式） | `robots/manifest.py` | 别写进消费方的代码 |
| 关节顺序 / 增益 / 观测格式 / 控制周期 | 各策略目录下的 `contract.json` | **别抄进 manifest**——抄两份必然对不上 |

### ⛔ `pd_mode` 搞反当场倒

Go2 是显式 PD（部署器自己算 `−kd·qd`、模型阻尼清零），G1 是隐式 PD
（`kd` 写进 `dof_damping`、力矩只发 `kp` 那项）。这一项是**训练侧的事实**，
契约里没导出，所以住在 manifest；凭印象填会让机器人在部署里 1 秒内倒。

### ⛔ 第三方资产的许可不许动

`robots/go2/` 与 `robots/g1/` 来自 MuJoCo Menagerie（BSD-3-Clause）。
许可文件、来源说明（`G1_MODEL_UPSTREAM.md`）必须随资产一起留在仓里。
G1 是用 `import_from_menagerie.py` 导入的——**改上游模型走那个脚本**，别手改 `g1.xml`。

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
