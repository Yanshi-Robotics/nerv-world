[![Language: English](https://img.shields.io/badge/Language-English-2f81f7?style=flat-square)](README.md) [![语言: 简体中文](https://img.shields.io/badge/语言-简体中文-e67e22?style=flat-square)](README_zh.md)

# alice-house · 给机器人住的房子

[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE) [![Simulator](https://img.shields.io/badge/simulator-MuJoCo-blue?style=flat-square)](https://mujoco.org) [![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](https://www.python.org) [![Version](https://img.shields.io/badge/version-v0.4-lightgrey?style=flat-square)](CHANGELOG.md)

> 🤖 **如果你是 AI agent，请先读 [AGENTS.md](AGENTS.md)** —— 那是面向机器的入口：
> 这个仓是什么、每个事实住在哪、入口命令、以及红线。

**一套用代码生成的室内仿真场景，带两台宇树机器人和训练好的运动策略——克隆下来就能让它们在屋里真的迈腿走路。**

**Alice 的房子**——一套**用代码生成**的室内场景，让机器人在里面看、走、找东西、干活。

几何一行都不手写：房间、门窗、家具、贴图全部由 `layout.py` 这一份布局定义生成。
想改屋子就改布局、重跑生成器；场景和使用它的程序读同一份真相源，不会两处坐标打架。

配套还带**机器人**（宇树 Go2 四足、宇树 G1 人形）和训练好的**运动策略**——
克隆下来就能让它们在屋里真的迈腿走路，不是瞬移。

> 名字的来历：Alice 是这一系列里第一号机器人，这是她的房子。
> 以后可能扩成一座岛——房子、山路、码头都在上面，Alice 挨个去。

**MIT 许可**，随便用。仓里的宇树机器人模型来自 MuJoCo Menagerie，保留它们自己的
BSD-3-Clause 许可（见 `LICENSE` 末尾的说明）。

---

## 目录

- [里面有什么](#里面有什么) · [现有机器人](#现有机器人) · [户型与实拍](#户型)
- [设计原则](#设计原则)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [一台机器人一份场景](#一台机器人一份场景)
- [版本](#版本) · [许可](#许可)

---

## 里面有什么

| 户型 | 规模 | 说明 |
|---|---|---|
| 大平层三室两厅双卫 | 12 个空间 / 364 ㎡ | 参照真实户型图复刻；客餐一体、主卧套间（衣帽间+主卫带独立浴缸）、中西厨分离 |

### 现有机器人

| 编号 | 本体 | 眼高 | 说明 |
|---|---|---|---|
| **go2** | 宇树 Go2 四足机器狗 | ~0.38 m | 头部前视相机；平地速度策略 |
| **g1** | 宇树 G1 人形（29 自由度） | ~1.25 m | 站立 1.38 m；头部相机装在躯干上、下俯 10° |

同一间屋子在这两双眼睛里差别很大——这正是场景**按真实做、不为某一种机器人定制**的理由。

### 空间构成

主卫（独立浴缸）· 衣帽间 · 小孩房（含卫浴）· 主卧 · 过道 · 客卫 · 次卧 ·
餐厅（含西厨中岛）· 中厨（含晾晒）· 客厅 · 玄关 · 洗衣房

### 户型

关掉天花板俯视，可以看清整套动线：西侧是主卧套间与小孩房（静区），一条过道横贯东西，
东侧是客厅、玄关与服务区（动区）。

![户型俯视图](docs/images/A1-户型俯视图.png)

### 公共区

客厅与餐厅之间的墙整段拆除，电视立在原墙位置当软隔断——大平层的客餐一体做法。

| 客餐打通 | 客厅 |
|---|---|
| ![客餐厅打通](docs/images/B1-客餐厅打通.png) | ![客厅](docs/images/B2-客厅.png) |

### 居室与服务区

| 主卧 | 主卫（独立浴缸） |
|---|---|
| ![主卧](docs/images/C1-主卧.png) | ![主卫](docs/images/C3-主卫+浴缸.png) |

| 小孩房 | 中厨 |
|---|---|
| ![小孩房](docs/images/D1-小孩房.png) | ![中厨](docs/images/E1-中厨.png) |

中厨这张值得多看一眼：橱柜沿西墙一字排开（洗碗机·水槽·灶台·烤箱），储物高柜与冰箱贴北墙，
中间整条是通行区。**这是 2026-07-25 重排过的**——之前鞋帽间的整墙柜横在房间正中还堵着门，
把 45 ㎡ 切成三块，机器狗钻进 54 cm 的缝里就出不来。

### 机器人视角

场景最终要服务的是机器人的眼睛。下面几张都是**四足机器狗头部相机**看到的画面（高度 0.38 m），
最后一张是同一间厨房换成**人形眼高**（1.25 m，G1 头部相机的实际高度）的对照——同一个场景，不同机器人看到的
东西差别很大，所以场景按真实做、不为某一种机器人定制。

| 出生在玄关 | 客厅（正对电视墙） | 过道 |
|---|---|---|
| ![玄关](docs/images/G1-狗视角-出生在玄关.png) | ![客厅](docs/images/G2-狗视角-看电视.png) | ![过道](docs/images/G5-狗视角-过道.png) |

| 站在门口望进中厨 | 窗外的城市 | 人形视线高度看同一间中厨 |
|---|---|---|
| ![厨房门口](docs/images/G3-狗视角-厨房门口.png) | ![窗外](docs/images/G4-狗视角-窗外城市.png) | ![人形视角](docs/images/H1-人形视角-中厨.png) |

> 「站在门口望进中厨」这张就是实测里 ANIMA 宣布「已到厨房」时看到的画面——
> 吊柜、深色台面、不锈钢洗碗机门、右侧落地冰箱都在画面里。

### 图是怎么出的

**别手工截图。** 机位全写在 `make_docs_images.py` 里，改了场景就重跑：

```bash
python make_docs_images.py        # 全出
python make_docs_images.py E1 G3  # 只出指定几张
```

背景：第一版配图是一张张手摆机位截的，中厨一重排就全过时，还没人记得当初相机在哪。

---

## 设计原则

**几何不手写，全部由布局定义生成。** 改屋子只改 `layout.py`，重跑生成器即可——
场景与消费方（世界服务判断「机器人在哪间屋」）读同一份真相源，不会两处坐标打架。

**⛔ 按真实做，不为某一种机器人定制。** 场景是「现实」，不是给某台机器的考题。
四足机器狗的相机只有 ~0.5 m 高，人形是 1.5 m 以上——**为了迁就狗去压低家具，
换成人形就全得重做**。看不见高处是**机器人侧**的局限，该用环视、抬头、换机位去解决，
不是把抽油烟机装到膝盖上。

> 这条是纠正来的。早期版本这里写的是「识别特征必须铺在 0.3–0.9 m 高度带」——那是
> 拿一台特定机器人的视角当设计目标，方向错了（Jeff 2026-07-25 校正）。

**摆位要真实：沿墙布置，中间留通行区。** 真实住宅的橱柜、衣柜是贴着墙走的，屋子中间是人
走路的地方。**别让大件家具横在房间中央**——2026-07-25 实测踩过：12 空间合并时鞋帽间的
整墙柜留在了中厨正中（还堵着门），把 45 ㎡ 的房间切成三块、只靠 54 cm 和 90 cm 两条缝
连通，机器狗进去就卡死。真实厨房重排之后，问题自然消失。

顺带说明：真实厨房里烤箱、洗碗机**本来就嵌在台面下**（0.1–0.9 m），冰箱本来就落地——
它们恰好落在低视角能看到的位置，这是真实的结果，不是为谁让步。

**家具是组合件，不是基本体。** 一把椅子 = 座面 + 靠背 + 两根竖档 + 四条腿 + 前后横撑；
一盏落地灯 = 配重底盘 + 细杆 + 收口 + 灯罩 + 收头。见 `furniture.py`。

**封顶。** 有天花板，机器人抬头看到的是屋顶不是天空；天花板单独归一个 geom group，
出俯视图时整层关掉即可。

**窗外有世界。** 近处树木草地 → 中景楼房 → 远处城市天际线背景板（matte painting 手法）。

---

## 目录结构

```
layout.py           ⭐ 布局单一真相源（房间矩形/门窗/家具/窗外景物）
furniture.py        参数化家具构件库（椅子/桌子/灯具/花瓶/绿植…）
make_textures.py    程序化生成贴图（木地板/瓷砖/大理石/地毯/织物/城市天际线/挂画）
make_house.py       布局 + 机器人 → house-<机器人>.xml（MJCF）
make_docs_images.py 出 README 配图（机位写在代码里，改了场景一条命令重出）
house-go2.xml       生成产物（四足机器狗那份）
house-g1.xml        生成产物（人形那份）
textures/           生成的贴图
robots/
  manifest.py       ⭐ 机器人清单单一真相源（模型/出生高度/相机/策略/力矩怎么发）
  go2/              宇树 Go2 模型（含头部前视相机）
  g1/               宇树 G1 人形，29 自由度（由 import_from_menagerie.py 从 Menagerie 导入）
policies/           训练好的运动策略（ONNX + 契约）
docs/images/        README 配图
```

## 快速开始

```bash
git clone https://github.com/jeffliulab/alice-house.git
cd alice-house
pip install mujoco numpy pillow

# 看一眼这间屋子（场景已经生成好了，直接就能开）
python -m mujoco.viewer --mjcf=house-go2.xml     # 四足机器狗那份
python -m mujoco.viewer --mjcf=house-g1.xml      # 人形那份
```

改了屋子要重新生成：

```bash
python make_textures.py         # 贴图（改了纹理才需要重跑）
python make_house.py            # 每台机器人各生成一份场景
python make_house.py --robot g1 # 只生成人形那份
python make_docs_images.py      # 重出 README 配图
```

想让机器人**真的走起来**：`policies/` 下是训练好的 ONNX 策略，配 `contract.json`
（关节顺序、增益、观测格式全在里面）。喂它速度指令 `(vx, vy, wz)`，它吐关节目标角度。
一个跑通的部署器可以参考 [anima-zero](https://github.com/jeffliulab/anima-zero)
的 `world/sim-house-nav/sim.py`。

## 一台机器人一份场景

`house-go2.xml` / `house-g1.xml` 是同一间屋子、不同的住客。为什么不合成一份：
机器人的网格路径在 MJCF 编译期就定死了，两台塞不进同一个模型。

**机器人清单 `robots/manifest.py` 是「这台机器人是什么」的单一真相源**——模型在哪、
出生多高、相机叫什么、力矩怎么发。加一台新的就往里追加一条，再跑一次生成器。

⚠️ 清单里**不重复**策略契约（`contract.json`）已有的东西（关节顺序、增益、观测格式、
控制周期）——那些的真相源是契约，抄两份必然对不上。清单只放契约里没有的。

⛔ **两台机器人的力矩发法是相反的**，写在清单的 `pd_mode` 里，搞反了当场倒：
Go2 训练侧是显式 PD（部署器自己算 −kd·qd、模型阻尼清零），
G1 是隐式 PD（kd 写进 `dof_damping` 交给 MuJoCo，力矩只发 kp 那一项）。

## 改屋子 / 加新地方

改 `layout.py` 里的房间矩形、门窗、家具，重跑生成器即可。构件库（家具/贴图）直接复用。
想加**别的地方**（山路、码头……）也走同一套：新写一份布局定义，生成器不用动。

---

## 版本

见 [CHANGELOG.md](CHANGELOG.md)。当前 **v0.4**。

## 许可

本仓的场景生成器、家具与贴图构件库、机器人清单、运动策略和文档采用 **MIT**（见 [LICENSE](LICENSE)）。

打包在仓里的第三方资产保留各自的许可：宇树 Go2 与 G1 模型来自
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie)，
BSD-3-Clause，见 `robots/go2/GO2_MODEL_LICENSE` 与 `robots/g1/G1_MODEL_LICENSE`；
G1 我们改了什么、为什么改，写在 `robots/g1/G1_MODEL_UPSTREAM.md`。

## 致谢

宇树科技（Unitree Robotics）的 Go2 与 G1 模型 · Google DeepMind 的
[MuJoCo](https://mujoco.org) 与 [Menagerie](https://github.com/google-deepmind/mujoco_menagerie)。
