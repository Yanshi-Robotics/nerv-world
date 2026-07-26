# Project Agent Entry

本仓继承 `agent-rules` 的共享规范。

## Version Pin

- `agent-rules` version: **`v0.3.0`**
- upstream machine entry: [agent-rules/AGENTS.md](https://github.com/jeffliulab/agent-rules/blob/v0.3.0/AGENTS.md)
- upstream skeleton（检索索引，会话开始加载一次）: [`_skeleton.md`](https://github.com/jeffliulab/agent-rules/blob/v0.3.0/_skeleton.md)

⛔ **不要指向 `main`。** 升级 = 改上面这个 tag，然后拿新版本校一遍本仓。

## Read Order

1. 先读本文件（项目级覆盖）。
2. 再读上游 machine entry，按它的协议加载 `_skeleton.md`，**按需**取节点，别批量预载（≤5 个）。
3. 本仓相关的上游节点：`global`、`workflows.git`、`workflows.github`（本仓是公开仓）、
   `principles.engineering`。⚠️ 本仓**不是** ROS 2 项目，也不是训练项目，
   `stacks.robotics` / `stacks.python-ml` 只在真的动到策略训练时才需要。
4. 上游规则读完之后，本仓的规则**优先**。

---

## 这个仓是什么

**alice-house** = 一套用代码生成的室内仿真场景资产库 + 两台机器人模型 + 训练好的运动策略。
它**不是**一个应用，没有运行期服务、没有 API、没有用户输入——它是**别的项目 import 的资产**。
主要消费方：[anima-zero](https://github.com/jeffliulab/anima-zero) 的 `sim-house-nav` 世界。

## 本仓的红线（改之前必看）

### ⛔ 几何不手写

`house-*.xml` 是**产物**，不许手改。改屋子只改 `layout.py` 再重跑 `make_house.py`。
手改产物的下场：下一次重跑就被覆盖，而且场景与消费方的坐标真相源从此分叉。

同理，README 的配图不许手工截——机位写在 `make_docs_images.py` 里，改了场景重跑那个脚本。

### ⛔ 单一真相源，谁也别抄谁

| 事实 | 住哪儿 | 别在哪儿重复 |
|---|---|---|
| 房间矩形 / 门窗 / 家具 / 出生点 | `layout.py` | 别写进 `house-*.xml`（那是产物） |
| 机器人是什么（模型/出生高度/相机/力矩模式） | `robots/manifest.py` | 别写进消费方的代码 |
| 关节顺序 / 增益 / 观测格式 / 控制周期 | 各策略目录下的 `contract.json` | **别抄进 manifest**——抄两份必然对不上 |

### ⛔ 按真实做，不为某一种机器人定制

场景是「现实」，不是给某台机器的考题。四足眼高约 0.4 m、人形约 1.25 m——
为迁就矮的去压低家具，换高的就全得重做。看不见高处是**机器人侧**的局限。

### ⛔ `pd_mode` 搞反当场倒

Go2 是显式 PD（部署器自己算 `−kd·qd`、模型阻尼清零），G1 是隐式 PD
（`kd` 写进 `dof_damping`、力矩只发 `kp` 那项）。这一项是**训练侧的事实**，
契约里没导出，所以住在 manifest；凭印象填会让机器人在部署里 1 秒内倒。

### ⛔ 第三方资产的许可不许动

`robots/go2/` 与 `robots/g1/` 来自 MuJoCo Menagerie（BSD-3-Clause）。
许可文件、来源说明（`G1_MODEL_UPSTREAM.md`）必须随资产一起留在仓里。
G1 是用 `import_from_menagerie.py` 导入的——**改上游模型走那个脚本**，别手改 `g1.xml`。

### 提交纪律

- 本仓是公开作品集，**commit 不带 `Co-Authored-By`**。
- 目录一动，所有 `..` 相对路径重新数一遍。
  （2026-07-26 真踩过：场景目录扁平化后 `make_docs_images.py` 的输出路径还是 `../docs/images`，
  配图被写到仓库外面去了，脚本照常打印"完成"、README 的图一张没更新。）

---

## 与上游规范的偏离（明确登记）

| 上游规则 | 本仓怎么做 | 为什么 |
|---|---|---|
| 根目录必备 `.env.example` | **不设** | 本仓是纯资产库，没有任何运行期环境变量。放一个空文件是仪式，不是规范。 |
| pre-1.0 走 rapid-versioning 三件套 | **用 `CHANGELOG.md`**（Keep a Changelog） | 本仓已公开、有外部消费方，CHANGELOG 是写给使用者看的；三件套是写给自己看的。规范允许就近覆盖。 |
| `stacks/python-ml.md` 的训练目录约束 | 不适用 | 本仓只**装**训练产物（ONNX + 契约），训练本身在 [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion)。 |

## ⚠️ 给 agent 的一条环境提示

上游 `GLOBAL.md` 写 Linux 上规范库应在 `/home/agent-rules`，**本机实际在 `~/agent-rules`**
（即 `/home/jeff/agent-rules`）。按实际位置读，别按文档里的路径找。
