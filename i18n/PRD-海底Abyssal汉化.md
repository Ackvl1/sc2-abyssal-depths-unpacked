# PRD：海底 Abyssal（ONIZ）中文化工程

> **Status**: Draft v1 — 2026-09-11
> 范围已确认：**只翻玩家可见字符串**；**双轨落地（保留 enUS 原版 + 新增 zhCN）**；上传范围待重打包跑通后再定。
> 侦查数据来源：对 4 个包的实测解包/解码（详见附录 A）。

---

## Problem Statement

《Oh No It's Zombies: Abyssal Depths》是英文街机图，中文客户端（Locale zhCN）下除地图名/简介 10 行外**全部回退显示英文**——技能名、单位名、武器柜按钮、游戏内警报与聊天文案均为英文。中国玩家需要一份中文版，且不能破坏英文原版（作者仍在更新）。

现有本地化缺口（实测）：

| 包 | 语言目录 | enUS 内容 | zhCN 现状 |
|---|---|---|---|
| `Abyssal Depths FULL.SC2Map`（25MB） | 全 12 语言 | GameStrings 835 / ObjectStrings 380 / TriggerStrings 3625 / Hotkeys 11 | 10 行手工 stub |
| `…Abyssal Depths Map.SC2Mod`（17.5MB） | 全 12 语言 | 与地图逐项相同（835/380/3625/11） | 10 行 stub |
| `…Semice Mod.SC2Mod`（136MB） | **仅 enUS** | GameStrings 6097 / ObjectStrings 8718 / Hotkeys 647 / Product 1 | **完全没有** |
| `…Semice Art Mod.SC2Mod`（146MB） | **仅 enUS** | GameStrings 3 行 | 无 |

社区无现成 ONIZ 汉化补丁（已检索确认），必须自建。

---

## 目标（Goals）

1. 产出可直接分发的**中文版 Abyssal Depths**：中文客户端进图后，玩家可见文本 100% 中文。
2. **英文原版零损失**：enUS 文件逐字节不变，中文只新增在 zhCN 层。
3. 全部产物（译文、术语表、脚本、组件夹、汉化包）进 GitHub 仓库可复现，任何一步可由脚本重跑。
4. 翻译可增量维护：作者更新图后，只需按 key 差量补译。

## 非目标（Non-Goals）

- 不翻编辑器内部文本：`*/EditorPrefix`、`*/EditorSuffix`、`*/EditorDescription`（5,107 行）与 `TriggerStrings`（7,250 行，Category/Variable/Trigger/FunctionDef 等）——玩家看不见。
- 不翻快捷键 `Button/Hotkey`（670 行，键位非文本）。
- 不改数值/逻辑/依赖/资源，只动本地化层与 ComponentList 的 locale 声明。
- 不逆编译触发器字节码。

---

## 翻译范围（Range）

去重后 **≈7,500 条唯一字符串**（对应 ~10,500 行待写）：

| 类别 | 行数 | 唯一值 | 例 |
|---|---|---|---|
| 名称 `*/Name/*` | 7,554 | 6,176 | `Unit/Name/BroodLordHangar2`、`Upgrade/Name/MechanicSuit` |
| 提示/说明 Tooltip / Tip / Subtitle / Info / LifeArmorName | 1,055 | 688 | `Button/Tooltip/…`、`Behavior/Tooltip/…` |
| 触发器·UI 文案 `Param/Value/lib_3977487D_*` | 1,851 | 609 | 游戏内警报、聊天、面板文字（含 `<s val="AlertItem">`） |
| 大厅属性 `Attribute00x/*`、`Variant*` | 78 | 29 | 大厅可选属性名 |
| 杂项桶（含成就名、`Button/Subtitle` 长描述、`Abil/TargetMessage` 图文） | ~1,600 | 逐条判定 | `Achievement/Name/*`、`Abil/TargetMessage/attack2`（含 `<IMG path=...>`） |

**每个包实际只写 2 个文件**：`zhCN.SC2Data/LocalizedData/GameStrings.txt` + `ObjectStrings.txt`
（Hotkeys 不翻；TriggerStrings 仅编辑器可见，不翻；`GameStringsProduct.txt` 只有 1 行，按需复制。）

### must-preserve（机器校验）

- `<n/>` 336 处、`<c val="XXXXXX">` 313 处、`<s val="XXXXX">` 200 处、`<IMG path="...">`、`~A~` 占位、`##id##` 之类模板变量 → 数量与结构必须与原串一致。
- 26 条纯符号/短串（`" seconds."`、`"!"`、`": "`、`" \n"`）→ 保留符号，仅必要时补译。
- 畸形行：GameStrings 中存在**英文原文当键、值为空**的行（如 `All nearby zombies gain 1 life regen and 1 armor=`）→ 译文写入**值位**，键不变。
- 文件编码：UTF-8 **带 BOM**、行尾 **CRLF**（与现网一致）。

---

## Implementation Decisions

### D1 — 双轨落地：enUS 原样 + zhCN 新增
- enUS 保持逐字节不变（校验 md5）。
- zhCN 只写**要覆盖的 key**；引擎按 key 合并，zhCN 缺失的 key 自动 fallback enUS，因此不要求与 enUS 等长。
- 地图层与 Map Mod 已有的 10 行 zhCN（地图名/简介/3 条补丁说明/4 个玩家名）**原样保留**，仅追加。

### D2 — 每包各写自己的 zhCN（不做跨层覆盖假设）
玩家可见字符串分别存在于地图层、Map Mod、Semice Mod 两侧（例如警报文案两层都有）。为保证不出现"部分中文部分英文"，**每个包的 zhCN 覆盖该包 enUS 的玩家可见键集合**。
> ⚠️ 待家机实测的开放问题：地图层 zhCN 同名 key 是否能压过 Mod 层 enUS。本方案不依赖该语义（每层自带中文），但重打包后要实测记录结论。

### D3 — ComponentList 补 locale 声明
`Semice Mod` / `Semice Art Mod` 现仅声明：
```xml
<DataComponent Type="text" Locale="enUS">GameText</DataComponent>
```
新增 zhCN 数据后必须追加：
```xml
<DataComponent Type="text" Locale="zhCN">GameText</DataComponent>
```
（`Abyssal Depths FULL.SC2Map` 与 `Map Mod` 的 ComponentList 需核对后同样处理；`Map Mod` 本身无 ComponentList，属正常。）

### D4 — 术语表先行（Glossary First）
先定词表再翻，禁止同词两译。初版：
Mining Droid=采矿机器人 / Repair Drone=维修无人机 / Virophage=噬菌体 / Extractor=萃取机 / cocoon=茧 / Hive Mind=虫巢意志 / creep=菌毯 / strain=株系 / infestation=感染 / Security Mainframe=安全主控 / Weapons Locker=武器柜 / opt-in=报名 / Surrender=投降 / Supply=补给 / Vespene=瓦斯 …
（终版随 PRD 评审落成 `i18n/术语表.tsv`。）

### D5 — 翻译执行
- 分片（每片 ≤ N 键、保留原文与 key 不变）→ LLM 翻译（DeepSeek）→ 术语表约束 → 译文只回填 value。
- 逐片落盘 `i18n/译文/<pkg>/<file>.<lang>.partial.txt`，**每片追加写盘**，中断可续（不一次性长跑）。
- 幂等：同键重复翻译结果一致（保存中间态，跳过已译片）。

### D6 — 重打包（在用户家机执行）
本机限制：WDAC 拦未签名 exe、无 gcc ⇒ 只能产出"组件夹 + zhCN 文本"。
家机路线（已打通）：StormLib `mpq_create.exe`（MPQ v2，`dwMaxFileCount=0x1000`）整包重建；或 `mpq_inject.exe` + `MPQ_FILE_REPLACEEXISTING` 定点注入 zhCN。
- 编辑器/游戏进程会锁文件（errcode 32），重打包前 `taskkill SC2Editor_x64.exe / SC2_x64.exe`。

### D7 — 上传
- 文本产物（zhCN 文本、术语表、脚本、组件夹源码）：本机 `push_api.py` 走 api.github.com（本机 github.com:443 被墙）。
- 二进制（.SC2Map / .SC2Mod，>100MB）：Git Data API 不支持 LFS ⇒ 走**家机 git+lfs 直推**；上传范围待重打包跑通后定。
- 仓库：`Ackvl1/sc2-abyssal-depths-unpacked`（现 master 无 commit，`.gitignore` 已排除 `Mods/`）。

---

## Testing Decisions

这是"数据工程 + 文本工程"，TDD 采用**断言驱动**（全绿才进下一步）：

1. **键集合断言**：每个包 `zhCN` 键 ⊆ 该包 `enUS` 键；玩家可见键的覆盖率 = 100%（编辑器键不要求）。
2. **enUS 不变断言**：重打包后从 MPQ 回读 enUS 四个文件，md5 与原始一致。
3. **标记守恒断言**：逐条比对 `<n/>`/`<c val=>`/`<s val=>`/`<IMG`/`~A~` 计数与配对结构，零缺失。
4. **格式断言**：UTF-8 **BOM** 存在、行尾 CRLF、无重复键、无空键、无 `=` 出现在键侧。
5. **结构断言**：重打包后 MPQ 可被 mpyq 打开（`MPQArchive(path, listfile=False)`）、`DocumentInfo`/`ComponentList` 可读、format_version ∈ {2,3} 且 archive_size 合理。
6. **实机验收（人工，家机）**：中文客户端进图 → 技能名/单位名/武器柜/警报/聊天为中文；编辑器打开无致命告警；`GameLogs/ScriptError.txt` 无新增致命错误（F9 测试文档链路）。
7. **可复现断言**：清空 `i18n/译文/` 后重跑 pipeline，产出与提交版一致。

---

## 里程碑

| # | 交付物 | 在哪台机 |
|---|---|---|
| M1 | `i18n/术语表.tsv` + 基准抽取脚本（enUS → 待翻清单 TSV，含分类） | 办公机 |
| M2 | 玩家可见键清单（去重 7,500）+ 杂项桶人工判定表 | 办公机 |
| M3 | 译文（分片落盘、可续跑）+ 校验脚本（断言 1–4） | 办公机 |
| M4 | 各包 `zhCN.SC2Data/LocalizedData/*.txt` + ComponentList 补丁 + 组件夹 | 办公机 |
| M5 | 重打包 .SC2Map/.SC2Mod（StormLib，断言 5） | **家机** |
| M6 | 实机验证（断言 6）+ 上传 GitHub（断言 7） | 家机 + 办公机 |

---

## 风险与未验证项

| 风险 | 影响 | 处置 |
|---|---|---|
| 跨层 locale 覆盖语义未验证 | 可能出现"部分中文" | D2 每包各写 zhCN，不依赖该语义；M6 实测记录 |
| `Param/Value` 文案与触发器 GUID 绑定 | 键错位 = 文案串台 | 键一律不改，只改 value；断言 3 兜底 |
| 畸形行（键=英文原文、值为空） | 该句翻译丢失 | 单列清单人工处理 + 断言 1 覆盖 |
| 136MB/146MB 重打包耗时/占用 | 家机操作成本 | 优先 `mpq_inject` 定点注入 zhCN（只动 2 个文件），必要时才整包重建 |
| 单文件 >100MB 上传 | API 推送失败 | 二进制走家机 git+LFS；文本走 API |
| 作者后续更新 | 译文过期 | 键级差量补译脚本（M1 抽取脚本可复用） |

---

## 附录 A — 侦查原始数据

- 解包工具：`storm_extract.py` / `Mods/extract_sc2map.py`（纯 Python StormLib sector 解压器）
- Mod 加密 sector 修正脚本：`Mods/_tmp_extract_enus.py` → 输出 `Mods/SemiceMod_Components/enUS.SC2Data/LocalizedData_FIXED/`（GameStrings 6097 / ObjectStrings 8718 / Hotkeys 647）
- 密钥相关：`Param/Value/*` 为触发器文案，key = `lib_3977487D_<GUID8>`
- 上传脚本：`push_api.py`（Git Data API，branch `main`，repo `Ackvl1/sc2-abyssal-depths-unpacked`）
- 参考技能：`sc2-galaxy-editor-modding`（本机 Hermes 技能库）、`north3-map/04_SC2技能文档/sc2-mpq-editor`（StormLib 工具链）
