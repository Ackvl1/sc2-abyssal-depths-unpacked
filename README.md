# Abyssal Depths (SC2Map) 解包与结构分析 — 工作记录

> 日期：2026-09-04
> 目标：把暴雪官方合作任务地图 `Abyssal Depths FULL.SC2Map`（25MB，StormLib MPQ v3）解包为标准 `.SC2Components` 组件目录，便于 VS Code 直接阅读 / 编辑内部 XML / Galaxy / Layout / 字符串等文本资源。

---

## 1. 技术难点与解决

### 1.1 为什么现成工具全失败

| 工具 | 结果 | 原因 |
|---|---|---|
| 7-Zip (`7z x`) | `Can't open as archive` | 只认经典 MPQ v1/v2，不认 SC2 的 MPQ v3 |
| `mpyq` | 抛 `RuntimeError` 崩 | 只支持单一 zlib/bz2，遇到 StormLib 组合压缩字节直接挂 |
| `pystormlib` | `error 193` | 自带 32 位 DLL，本机 64 位 Python 加载失败 |
| 编译 / 下载 64 位 StormLib | 不可行 | 本机无 gcc/msys2/conda；GitHub 直连与 ghproxy 均超时 |

### 1.2 自研纯 Python 解压器（`storm_extract.py`）

SC2 地图用 **StormLib 组合压缩**。关键发现（逐一排查 sector 压缩字节得到）：

- 每个 sector **首字节 = 压缩类型标记**：
  - `0x02` → zlib（`zlib.decompress(data[1:], 15)`）
  - `0x08` → bzip2（`bz2.decompress(data[1:])`）
  - 其余（`0x89` / `0x0f` / `0x3d` / `0x5f` 等）→ **stored 哨兵**：整 sector 就是原始数据，**不剥首字节、不解压**
- 按 `sector_size = 512 << sector_size_shift` 读 position 表切分 sector
- 多 sector stored 文件要按 position 表拼接（不能整段当单块）

实现两个模块：
- `StormDecompress.decompress(data)` — 按上文规则解单 sector
- `read_raw_sectors(archive, name)` — 读 position 表、逐 sector 解压拼接

**结果：113 / 113 文件全部解出，0 失败；二进制资源（PNG/DDS/TGA/M3/OGG）完整性校验（magic / 长度守恒）全通过。**

---

## 2. 组件结构（SC2 四层模型）

解出的 `Abyssal Depths FULL.SC2Components/` 即标准组件布局：

### 数据层 `Base.SC2Data/GameData/*.xml`（21 文件，定义"是什么"）
声明式 XML，按实体类型拆文件。本图增量定义：

| 文件 | 实体 | 数量 |
|---|---|---|
| UnitData.xml | 单位 CUnit | 14 |
| AbilData.xml | 技能 CAbil | 24 |
| EffectData.xml | 效果 CEffect | 80 |
| BehaviorData.xml | 行为 | 34 |
| ActorData.xml | Actor（数据→外观映射） | 37 |
| WeaponData.xml | 武器 | 6 |
| UpgradeData.xml | 升级 | 5 |
| ValidatorData.xml | 校验器 | 18 |
| ButtonData.xml | 按钮 | 12 |
| Requirement*Data.xml | 科技需求 | 10 + 53 |
| ModelData/LightData/SoundData/... | 模型/光照/音效/足迹/移动器 | 少量 |

### 逻辑层 `MapScript.galaxy`（1.76MB / 31932 行 / 1397 函数）
- 全部函数带 GUID 前缀 `lib3977487D_*` → **由触发器 GUI 编译生成**（非手写）
- 引用 `libNtve`（原生）、`libHots`（合作任务）、`libCOMI`（ONIZ 自定义库）

### 外观 / 资源层 `Assets/`（二进制，Blender / 模型查看器看）
- `Textures/*.dds`：31 张贴图（虫群宿主水生皮、SgtHammer 风暴英雄贴图、dave/spectre 角色、雷达塔、UI 加载图；单张最大 8MB）
- `Models/*.m3`：2 个虫群宿主模型
- `Sounds/*.ogg`：胜利 BGM
- `*.tga`：小地图 / 传送地图 / 截图
- `1~5.png` + `screen-cap-1.png`：预览 / 截图

### 地形 / 放置 / 区域（地图几何）
- `t3Terrain.xml`（7747 行）+ `t3HeightMap` / `t3TextureMasks`(16MB) / `t3VertCol` / `t3Water` 等：高度 / 纹理 / 顶点色 / 水域（Abyssal Reef 改图）
- `Objects`（1.3MB，`<PlacedObjects>`）：所有放置物坐标与实例
- `Regions`（134KB，`<Regions>`）：触发器区域
- `CellAttribute_*`（6 个）：每玩家视野 / 碰撞栅格

### UI 层 `Base.SC2Data/UI/Layout/*.SC2Layout`（3 文件）
- `ONIZLoadScreen.SC2Layout`：自定义加载界面（地图名、玩法说明、Discord/Patreon 复制按钮、紫色调）
- `GameCountdownDisplay.SC2Layout`：把本体默认开局倒计时面板标 `CreationDeferred`，交给自定义界面接管
- `DescIndex.SC2Layout`：索引，把上面两个 `<Include>` 进来

### 本地化 `*.SC2Data/LocalizedData/`
- `GameStrings.txt`：英文 835 行（满），其余 11 种语言各仅 10 行（只翻了地图名 / 简介 / 补丁说明）
- `TriggerStrings.txt`（英文 3625 行）：触发器文本字符串表
- `ObjectStrings.txt` / `GameHotkeys.txt`

### 文档头 / 索引
- `ComponentList.SC2Components`：组件清单（编辑器按它装配）
- `DocumentHeader`（10KB，H2CS 二进制）：**依赖权威源**——改依赖须连它一起改（见下方"坑"）
- `DocumentInfo` / `MapInfo` / `BankList.xml` / `Preload.xml` / `PreloadAssetDB.txt`

---

## 3. 关键发现

1. **本图不是独立完整图** —— `DocumentInfo` 显示依赖 3 个外部 Mod：
   ```
   Mods/Oh No It's Zombies Abyssal Depths Map.SC2Mod
   Mods/Oh No It's Zombies Semice Mod.SC2Mod
   Mods/Oh No It's Zombies Semice Art Mod.SC2Mod
   ```
   所以 `.SC2Components` 只是**地图层增量**，核心单位 / 模型 / 大部分逻辑在那些 Mod 里（`Mods/` 目录）。
2. **本地化几乎没翻**：除英文外 11 种语言各 10 行。
3. **脚本是触发器编译产物**：3.2 万行带 `lib3977487D_` GUID 前缀。
4. **玩法主题**：纯虫族 + 僵尸生存（ONIZ 系列），含虫巢机库、变异链、毒气、虫洞、攻城、生产等。

---

## 4. 能力数据结构详解（AbilData 三连）

SC2 数据模型是 `技能(Abil) → 效果(Effect) → 行为(Behavior) → 单位(Unit)` 分层。**Abil 只说"触发什么"，Effect 才说"具体干什么"。**

### 4.1 `AbathurDeepTunnel4`（CAbilEffectTarget，对目标点施放）
- `PrepEffect=AlphaZombieBurrow`（钻地准备演出）
- `Effect[0]=AbathurDeepTunnelTeleportSet`（真正传送，定义在 EffectData）
- `Cost`：充能 `Abil/DeepTunnel` + 单位级冷却 120s
- `Range=500`，`PrepTime=0.0625`
- `CancelableArray[Prep]=1`（准备可取消），`UninterruptibleArray[Cast/Finish]=1`（传送不可打断）
- `CmdButtonArray[Execute]`：借本体 `AshWormBurrowMove` 图标，`State=Restricted`（无充能置灰）

### 4.2 `BroodLordHangar`（CAbilArmMagazine，T1 机库）
- `InfoArray[Ammo1]`：单弹仓槽，`Time=0.6`，`CountStart=0`，`Distance=0.75`
- 每发 `Energy=15` + 专属充能 + 科技 `ArmBroodlingEscortHighEnergy`
- 三阶段 `EffectArray`：`Create=EscortBroodlingLaunchSet2`（产护卫）、`Launch=BroodLordAddUnit`（发射）、`Release=BroodLordHangerSet`（收回）
- `ExternalAngle`：3 个发射角

### 4.3 `BroodLordHangar22`（CAbilArmMagazine，T2 强化档）
相比 T1：
- **双弹仓槽** `Ammo1` + `Ammo2`（分级科技 `HighEnergy22` / `HighEnergy3`）
- 每发能量 **15 → 2.5**（降 6 倍）
- **`AutoBuild=1` 自动产**（T1 手动点）
- 新增 `Death=InterceptorFate`（宿主死亡时护卫处理，T1 漏掉）
- `Leash=12`（护卫活动半径）
- **5 个发射角**（T1 仅 3 个）

---

## 5. 工具使用

### 解包任意 SC2Map
改 `run_extract.py` 里的 `SRC` / `OUT` 后运行：
```bash
python run_extract.py
```
输出：组件目录 + 完整性校验报告（BAD 数应为 0）。

### 用 VS Code 打开
双击 `用vscode打开.cmd`，或：
```bash
code "Abyssal Depths FULL.SC2Components"
```
文本文件（XML / Galaxy / Layout / Strings）直接可读；建议装 `talv.sc2galaxy` 插件获得 Galaxy 语法高亮。

### 重打包回可加载 SC2Map
> ⚠️ **坑**：纯 Python 写 MPQ 会把 v3 降级成 v0，银河编辑器拒载。
> 必须用 north3 项目里那套**正规 StormLib 写工具**（MPQ v2）重打包。本机无 gcc 暂未重打包。

---

## 6. 文件清单（顶层）

```
海底_Abyssal/
├── Abyssal Depths FULL.SC2Map          # 原始地图（MPQ v3，25MB）
├── Abyssal Depths FULL.SC2Components/  # 解包后的组件目录（本仓库主体）
├── storm_extract.py                    # 自研 StormLib sector 解压器
├── run_extract.py                      # 全量提取 + 校验驱动
├── 用vscode打开.cmd                     # 双击打开组件目录
├── Mods/                               # 外部依赖（ONIZ 系列 SC2Mod）
└── README.md                           # 本文件
```

---

## 7. 遗留 / 待办
- [ ] 解包并读 3 个外部 `Mods/*.SC2Mod`，拼成"地图层 + Mod 层"完整认知
- [ ] 本机编译 / 获取 64 位 StormLib，打通重打包闭环
- [ ] 把 `EffectData.xml` 的 `EscortBroodlingLaunchSet` / `AbathurDeepTunnelTeleportSet` 挖出，看 Create/传送的"里子"实现
