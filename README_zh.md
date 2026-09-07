# nerv-world

[![许可：MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE) [![仿真器：MuJoCo](https://img.shields.io/badge/simulator-MuJoCo-blue)](https://mujoco.org)

[English](README.md) · [简体中文](README_zh.md)

面向 MuJoCo 和 [NERV](https://github.com/Yanshi-Robotics/nerv) 的住宅场景库，提供宇树 G1 和 Go2 版本。
建筑、家具、碰撞体和机器人场景均由布局定义生成。下方配图来自 MuJoCo 原生渲染器。

![house2：山坡豪宅、草坪与泳池](docs/images/house2/X1-整栋外景.png)

[场景](#场景) · [快速开始](#快速开始) · [可交互家具](docs/interactions/README.md) · [住宅指南](docs/residences/README.md)

**AI agent**：修改仓库前请阅读 [AGENTS.md](AGENTS.md)。

## 场景

| 场景 | 空间 | 主要用途 |
|---|---|---|
| [house1](#house1) | 单层，12 个空间，约 364 m² | 导航与房间识别的标准场景 |
| [house2](#house2) | 三层加州豪宅，宅地约 80 × 70 m | 室内外通行、楼梯、庭院与泳池边界 |
| [apt1](#apt1) | 曼哈顿 62 层公寓，13 个空间 | 中央公园窗景与四时段光照 |
| [apt2](#apt2) | 62—63 层复式，24 个空间 | 精细室内、真实家具碰撞与操作者交互 |

house1 和 apt1 保留为标准场景。住宅开发集中在 house2 和 apt2；NERV 当前注册的住宅入口也为这两张地图。

### house1

最初的单层标准住宅，包括三间卧室、相连的客餐厅、带衣帽间和独立卫浴的主卧套间、中西厨区域、玄关及洗衣房。
全屋没有楼梯和高差，适合验证导航路径与房间识别。

| 户型 | 公共区：客餐厅 |
|---|---|
| ![house1 户型](docs/images/house1/A1-户型俯视图.png) | ![house1 客餐厅](docs/images/house1/B1-客餐厅打通.png) |

[house1 源定义](scenes/house1/layout.py) · [house1 其余配图](docs/images/house1)

### house2

新开发的加州山坡豪宅采用三层退台体量，配有露台和完整室内陈设，以暖白灰泥、浅色石材和木饰面构成建筑外观。
主楼前方设约 30 × 25 m 草坪和 15 × 6 m 泳池，并以车道、步道、树木和花池连接庭院各区。

入户门固定敞开。一层停机房、住宅、庭院和关闭的外大门之间具有连续可通行路线。
大门与外围围墙具有连续碰撞。泳池具有真实池壁、池底与台阶，水面不承重；道路、邻宅与下降的山坡构成不可进入的社区远景。

| 草坪与主楼 | 泳池露台 |
|---|---|
| ![house2 草坪](docs/images/house2/X4-草坪与主楼.png) | ![house2 泳池](docs/images/house2/X5-泳池露台.png) |
| 客厅 | 山坡社区 |
| ![house2 客厅](docs/images/house2/R1-底层客厅.png) | ![house2 社区远景](docs/images/house2/X6-山坡社区.png) |

[house2 布局](scenes/house2/layout.py) · [宅地定义](scenes/house2/estate.py) · [配图与复现](docs/residences/README.md)

### apt1

单层曼哈顿高层公寓位于约 232.5 m 标高，朝向中央公园。公园影像、周边建筑坐标、可见的本楼立面与具有碰撞的窗玻璃，
共同表现住宅与远处城市的空间关系。

**早晨、白天、黄昏、夜晚**四个预设会改变天空、灯光、建筑立面和窗玻璃材质。
它们是可选的光照状态，不包含连续时钟、天气或季节模拟。apt1 的布局、资产及生成场景保持不变。

![apt1 同机位四时段](docs/images/apt1/time-presets/T0-四时段对比.png)

[apt1 源定义](scenes/apt1/layout.py) · [apt1 配图](docs/images/apt1)

### apt2

apt2 在同一曼哈顿环境中扩展为两层复式，增加双高客厅、双跑楼梯和上层环廊。
浅橡木、胡桃木、石材与亚麻布艺形成室内材质体系，软包收边、床品、窗帘褶皱、窗洞进深及柜门细节改善了近距离观感。

| 双高客厅 | 沙发承托 G1 的坐姿 |
|---|---|
| ![apt2 双高客厅](docs/images/apt2/X3-双高客厅-挑空.png) | ![G1 在 apt2 沙发上的坐姿](docs/images/apt2/S1-机器人坐在沙发上.png) |

| 相对于 apt1 | apt2 的升级 |
|---|---|
| 空间 | 两层复式、双高客厅、上层环廊与连续楼梯 |
| 家具碰撞 | 餐椅、单椅、茶几采用凸分解碰撞，保留腿部空隙；沙发座面为 0.35 m，具有经过物理验证的 G1 坐姿 |
| 厨房 | 四件电器具有 22 个被动关节，覆盖冰箱门与抽屉、烤箱门与烤架、旋钮、龙头及烟机按钮 |
| 可移动物体 | 六把餐椅以及罐子、水果、书具有质量、重力和碰撞 |
| 时段 | 保留早晨、白天、黄昏、夜晚，复用城市资产并单独配置室内灯光；切换不会重置家具状态 |
| 检查器操作 | 瞄准附近活动部件后开合、调整开度，抓取物体并松手让其参与物理运动 |

| 冰箱开门、抽屉拉出 | 烤箱开门、烤架拉出 |
|---|---|
| ![apt2 冰箱交互](docs/images/apt2/interactions/fridge-open.png) | ![apt2 烤箱交互](docs/images/apt2/interactions/oven-open.png) |

![apt2 四时段](docs/images/apt2/time-presets/T0-四时段对比.png)

**交互范围**：家具操作和时段切换位于原生漫游检查器。NERV 可以载入这些被动物体并运行 G1 行走策略，
目前尚未提供家具操作接口，也没有 G1 自主抓取、开门、坐下或上楼梯技能。坐姿配图来自真实物理沉降，不代表自主坐下策略。
电器控制部件可以运动，但水流、加热、烹饪及通风尚未模拟。

[操作方法与能力说明](docs/interactions/README.md) · [apt2 布局](scenes/apt2/layout.py) · [验证记录](docs/interactions/validation.md)

## 快速开始

需要 Python 3.10 或更新版本。独立下载场景库后运行：

```bash
git clone https://github.com/Yanshi-Robotics/nerv-world.git
cd nerv-world
python -m venv .venv
source .venv/bin/activate
pip install mujoco numpy pillow glfw
python tools/make_house.py --scene apt2
python tools/walkthrough.py --scene apt2 --robot g1
```

首次下载时，尚未取得的家具网格会由简化几何代替。关节电器在此模式下仍保留基本体碰撞和关节。
复现完整家具请按[资产准备说明](docs/interactions/README.md#asset-setup)操作。
应先按本机可用资产重新生成场景，再打开对应 XML。

**WASD** 行走，鼠标转向，**空格**跳跃，**F** 切换检查器飞行。
在 apt2 中瞄准两米内的部件：**E** 开合或按压，**[ / ]** 调整开度，**J** 切换同一部件的其他关节，
**G** 抓取或松手，**L** 切换时段，**Backspace** 复位家具。**Esc** 释放鼠标，**Q** 退出。
这里移动的是检查视角，不是机器人的步态控制。

其他场景与机器人组合使用同一生成器：

```bash
python tools/make_house.py --scene house2 --robot go2
python -m mujoco.viewer --mjcf=build/house2-go2.xml
python tools/check_scene.py --scene apt2
python tools/check_interactions.py
python tools/walkthrough.py --scene apt2 --selftest
python tools/check_residences.py
```

在 NERV 中，本仓库位于 `worlds/` 子模块。[house2/world.yaml](house2/world.yaml) 和 [apt2/world.yaml](apt2/world.yaml)
定义场景与 G1 身体的组合。行走策略由独立的 [nerv-policies](https://github.com/Yanshi-Robotics/nerv-policies) 提供；
启动方式见 [NERV](https://github.com/Yanshi-Robotics/nerv)。

## 开发

修改 `scenes/<场景>/layout.py` 及其相关模块，再生成 `build/<场景>-<机器人>.xml`，不要手改生成文件。
场景清单和机器人清单相互独立，下载资产与临时产物不进入 Git。

- [住宅几何、配图与 NERV 检查](docs/residences/README.md)
- [家具交互结构与后续开发方向](docs/interactions/README.md)
- [变更记录](CHANGELOG.md)

## 许可

代码与原创程序化资产使用 [MIT 许可](LICENSE)。第三方内容保留原许可：[G1](robots/g1/G1_MODEL_LICENSE) 和
[Go2](robots/go2/GO2_MODEL_LICENSE) 模型使用 BSD-3-Clause；家具来源包括 Poly Haven CC0、Objaverse CC-BY-4.0
以及 RoboCasa CC-BY-4.0。外部家具文件在本机下载，不存入 Git。

具体来源、许可与校验值见[家具署名](decor/ATTRIBUTION.md)、[城市与纹理署名](textures/house3/ATTRIBUTION.md)、
[住宅资产记录](docs/residences/assets.json)及[关节资产记录](decor/articulation.lock.json)。
感谢 Unitree Robotics、Google DeepMind、MuJoCo 与 Menagerie 的维护者，以及记录中列出的资产作者。
