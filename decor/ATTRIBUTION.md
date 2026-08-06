# 装饰网格的来源与许可

⛔ 本文件由 `python -m decor.fetch` 自动生成，请勿手改。

本仓的 MIT 许可**不覆盖**下列第三方资产；每件的许可见各自目录的 LICENSE.txt。

所有资产都经过：Y-up→Z-up、按材质拆成单网格 OBJ、减面、居中。

| 资产 | 来源 | 作者 | 许可 | 面数 |
|---|---|---|---|---|
| 现代单椅 | polyhaven / `modern_arm_chair_01` | Vibrant Nordic | **CC0-1.0** | 8916 |
| 软包大床 Bed_Astrid（@elba） | objaverse / `bb98964881dd4c639efbb3838f9ba4de` | Эльба Мебель | **CC-BY-4.0** | 50543 |
| 木碗 | polyhaven / `wooden_bowl_01` | Oliver Harries | **CC0-1.0** | 5999 |
| 大理石胸像（画廊基座） | polyhaven / `marble_bust_01` | Rico Cilliers | **CC0-1.0** | 11999 |
| 优雅吊灯 | polyhaven / `Chandelier_02` | Kirill Sannikov | **CC0-1.0** | 12804 |
| 圆形大理石茶几 | polyhaven / `coffee_table_round_01` | Ulan Cabanilla | **CC0-1.0** | 4044 |
| 现代木柜（条案） | polyhaven / `modern_wooden_cabinet` | Patrik Pangerl | **CC0-1.0** | 18575 |
| 现代皮质餐椅（×8，必须减面） | polyhaven / `dining_chair_02` | James Ray Cock | **CC0-1.0** | 4999 |
| 现代灯具 | polyhaven / `modern_ceiling_lamp_01` | James Ray Cock | **CC0-1.0** | 5602 |
| 床头柜 Tumb Astrid（@elba） | objaverse / `02c6fbe74d9d4d33b2c17c942fe99344` | Эльба Мебель | **CC-BY-4.0** | 7284 |
| 抱枕 | polyhaven / `throw_pillows_01` | Serhii Khromov | **CC0-1.0** | 6362 |
| 盆栽 | polyhaven / `potted_plant_01` | Rico Cilliers | **CC0-1.0** | 41295 |
| 发财树 | polyhaven / `pachira_aquatica_01` | Rob Tuytel, Rico Cilliers | **CC0-1.0** | 63516 |
| 白瓷高瓶（现代） | polyhaven / `ceramic_vase_01` | James Ray Cock | **CC0-1.0** | 4000 |
| 彩绘陶瓶 | polyhaven / `ceramic_vase_02` | James Ray Cock | **CC0-1.0** | 3999 |
| 现代壶形瓶 | polyhaven / `ceramic_vase_04` | James Ray Cock | **CC0-1.0** | 4000 |

## 厨房电器（RoboCasa / NVIDIA 镜像）

来源：HuggingFace 数据集 `nvidia/PhysicalAI-Robotics-Manipulation-Objects-Kitchen-MJCF`
（`fixtures_lightwheel/` 目录，**CC-BY-4.0**）。
移植器 `decor/robocasa.py` **只取视觉网格与贴图**，不引入任何 `<joint>` / `<actuator>` / `<option>`
——实测移植前后 `nu=29 nq=36 nv=35` 逐位不变。

| 资产 | 型号 | 许可 | 网格数 |
|---|---|---|---|
| 对开门冰箱 | `fridges/Refrigerator031` | **CC-BY-4.0** | 9 |
| 四眼灶 + 烤箱 | `stoves/Stove001` | **CC-BY-4.0** | 10 |
| 水槽 + 龙头 | `sinks/Sink001` | **CC-BY-4.0** | 3 |
| 抽油烟机 | `hoods/RangeHood002` | **CC-BY-4.0** | 6 |
