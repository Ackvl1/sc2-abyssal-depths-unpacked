# 海底 Abyssal（ONIZ）中文化 — 产物与使用说明

> 状态：**本机（办公机）部分已完成** —— 抽取 / 翻译 / 组装 / 校验全链路通过（断言 A1–A5 全绿）。
> 缺的最后两环：重打包进 MPQ + 实机验证，**必须在家机**做（本机 WDAC 拦未签名 exe、无 gcc）。

## 一、产物清单（在哪）

| 文件 | 说明 |
|---|---|
| `术语表.tsv` | 133 条术语（单位/设施/机制/UI），翻译时强制统一 |
| `baseline/keys.tsv` | 4 个包 enUS 的全部键（17,248 行，含分类与是否玩家可见） |
| `baseline/units.tsv` | 去重后的翻译单元（7,147 条） |
| `baseline/enus_md5.json` | enUS 原版指纹（校验 enUS 未被改动） |
| `译文/units_zh.tsv` | **译文主体**（8,982 条，含 status/flags） |
| `译文/overrides.tsv` | 标记修复覆盖表（自动 3 + 手工 2） |
| `译文/overrides_manual.tsv` | 手工修正（颜色标记丢失的富文本串） |
| `out/SemiceMod/`<br>`out/SemiceArt/`<br>`out/MapMod/` | 各依赖 Mod 的 `zhCN.SC2Data/LocalizedData/*.txt` + 打好补丁的 `ComponentList.SC2Components` |
| `Abyssal Depths FULL.SC2Components/zhCN.SC2Data/…` | 地图层 zhCN（就地写入）+ 补过 locale 声明的 ComponentList |

中文覆盖：地图层 99.3%（840/846 玩家可见键）、Semice Mod 100%（8,156/8,156）、Art Mod 100%（3/3）。
未译的部分是**故意不译的**：内部资源名（`Sound/Name/*`、`RequirementNode/Name/*` 自动生成表达式）、纯符号串（`"!"`、`": "`、空格）、编辑器专用文本。

## 二、家机要做的两步

### 1) 重打包（StormLib）

```bash
# 依赖 Mod：把 zhCN 文本 + 补丁后的 ComponentList 注入原包
mpq_inject.exe "Oh No It's Zombies Semice Mod.SC2Mod" zhCN.SC2Data\LocalizedData\GameStrings.txt  out/SemiceMod/zhCN.SC2Data/LocalizedData/GameStrings.txt
mpq_inject.exe "Oh No It's Zombies Semice Mod.SC2Mod" zhCN.SC2Data\LocalizedData\ObjectStrings.txt out/SemiceMod/zhCN.SC2Data/LocalizedData/ObjectStrings.txt
mpq_inject.exe "Oh No It's Zombies Semice Mod.SC2Mod" ComponentList.SC2Components                   out/SemiceMod/ComponentList.SC2Components
# MapMod / ArtMod 同理；地图(out/ 里没有)用组件夹 zhCN 走 mpq_create 整包重建
```

注意（踩过的坑）：
- 替换已有文件必须带 `MPQ_FILE_REPLACEEXISTING`（否则 HET 表断言崩溃）
- 路径分隔符用 `\`（Mod 内是反斜杠）；先关掉 `SC2Editor_x64.exe` / `SC2_x64.exe`，否则报 errcode 32 文件被占用
- 地图若整包重建：`mpq_create.exe <out.SC2Map> <组件夹>`，`dwMaxFileCount=0x1000`

### 2) 实机验证

中文客户端进图 → 技能名/单位名/武器柜/警报/聊天应为中文；编辑器打开看 `EditorLogs/*Alerts.txt` 无新增致命告警。
**待实测的开放问题**：地图层 zhCN 的同名键能否覆盖 Mod 层 enUS（本方案不依赖它，每层各自带中文）。

## 三、回归/增量流程（脚本，幂等可重跑）

```bash
cd i18n/scripts
python extract_baseline.py     # 抽 enUS 基准（含分类）
python translate.py --workers 8 # 机翻（断点续跑；已译单元自动跳过）
python fix_markup.py          # 富文本标记修复 → overrides.tsv
python build_zhcn.py          # 组装 zhCN（原版 10 行人工条目受保护，不被机翻覆盖）
python verify.py              # 断言 A1–A5
python push_github.py         # Git Data API 推送到 GitHub
```

作者更新地图后：重跑 `extract_baseline.py` → `translate.py`（只翻新增键）→ `fix_markup.py` → `build_zhcn.py` → `verify.py`。

## 四、断言（verify.py）

| 断言 | 内容 |
|---|---|
| A1 | zhCN 键 ⊆ enUS 键（`MapInfo/PlayerXX/Name` 等原版人工键除外） |
| A2 | 玩家可见键覆盖率 ≥ 98% |
| A3 | `<n/>`/`<c>`/`<s>`/`<IMG>` 标记数量与原文一致（原版人工条目豁免） |
| A4 | UTF-8 BOM + CRLF + 无重复键 + 键侧无 `=` |
| A5 | enUS 逐字节未被改动（md5 比对） |

## 五、术语约定（节选，完整见 `术语表.tsv`）

Extractor=萃取机 / Virophage=噬菌体 / cocoon=虫茧 / Hive Mind=虫巢意志 / creep=菌毯 / strain=株系 /
Infestation=感染 / Security Mainframe=安全主控 / Containment Facility=收容设施 / Weapons Locker=武器柜 /
Psi Disrupter=幽能干扰器 / Alpha Zombie=阿尔法僵尸 / Abomination=憎恶 / Cerberus=地狱犬 / Oculus=眼魔
