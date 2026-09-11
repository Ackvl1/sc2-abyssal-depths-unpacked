#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SC2 本地化工具箱 — 共享库

功能:
  - 读 4 个包(FULL 地图组件夹 / 3 个 .SC2Mod) 的 LocalizedData 文本
  - MPQ 加密 sector 修正 (type-byte 前缀 bz2 / 原始 bz2 / 明文)
  - 键分类(玩家可见 / 编辑器专用 / 快捷键) 与标记提取
  - zhCN 文件写出 (UTF-8 BOM + CRLF, 与现网一致)

被 extract_baseline.py / translate.py / build_zhcn.py / verify.py 共用。
"""
from __future__ import annotations

import bz2
import codecs
import logging
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

LOG = logging.getLogger("sc2i18n")

# ---------------------------------------------------------------- 路径

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../海底_Abyssal/i18n
PROJ = os.path.dirname(ROOT)                                                # .../海底_Abyssal
FULL_FOLDER = os.path.join(PROJ, "Abyssal Depths FULL.SC2Components")
MODS_DIR = os.path.join(PROJ, "Mods")
BASELINE_DIR = os.path.join(ROOT, "baseline")
TRANS_DIR = os.path.join(ROOT, "译文")
LOG_DIR = os.path.join(ROOT, "logs")

# 包名 -> (类型, 路径)
PACKAGES: "Dict[str, Tuple[str, str]]" = {
    "FULLMap": ("folder", FULL_FOLDER),
    "MapMod": ("mpq", os.path.join(MODS_DIR, "Oh No It's Zombies Abyssal Depths Map.SC2Mod")),
    "SemiceMod": ("mpq", os.path.join(MODS_DIR, "Oh No It's Zombies Semice Mod.SC2Mod")),
    "SemiceArt": ("mpq", os.path.join(MODS_DIR, "Oh No It's Zombies Semice Art Mod.SC2Mod")),
}

# 需要处理的本地化文件(Hotkeys 不翻; TriggerStrings 仅编辑器可见)
TEXT_FILES = ("GameStrings", "ObjectStrings")
# 已存在需保留的 zhCN 行(地图/MapMod 的手工 10 行) → 由 build_zhcn 自动合并, 不在此硬编码


# ---------------------------------------------------------------- 日志

def setup_logging(name: str, filename: str = None) -> logging.Logger:
    """统一日志: 控制台 + i18n/logs/<filename>.log"""
    os.makedirs(LOG_DIR, exist_ok=True)
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    fh = logging.FileHandler(os.path.join(LOG_DIR, (filename or name) + ".log"), encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


def install_excepthook(log: logging.Logger) -> None:
    """未捕获异常写 traceback 到日志(用户要求: 不能静默吞异常)"""
    def _hook(etype, value, tb):
        log.error("未捕获异常: %s", "".join(traceback.format_exception(etype, value, tb)))
        sys.__excepthook__(etype, value, tb)
    sys.excepthook = _hook


# ---------------------------------------------------------------- MPQ 读取

def _read_mpq_file(archive, suffix: str) -> Optional[bytes]:
    """按后缀匹配读 MPQ 内一个文件(路径分隔符可能是 \\ 或 /)"""
    want = suffix.replace("/", "\\").lower()
    for n in archive.files:
        s = n.decode("utf-8", "replace")
        if s.replace("/", "\\").lower() == want:
            he = archive.get_hash_table_entry(s)
            be = archive.block_table[he.block_table_index]
            archive.file.seek(be.offset + archive.header["offset"])
            return archive.file.read(be.archived_size)
    return None


def decompress_blob(raw: Optional[bytes]) -> Optional[bytes]:
    """StormLib sector 解压: 原始 bz2 / 类型字节(被 XOR 污染) + bz2 / 明文"""
    if raw is None:
        return None
    if raw[:3] == b"BZh":
        return bz2.decompress(raw)
    if raw[1:4] == b"BZh":
        return bz2.decompress(raw[1:])
    return raw


def read_pkg_text(pkg: str, locale: str, fname: str) -> Optional[str]:
    """读某包的 <locale>.SC2Data/LocalizedData/<fname>.txt; 不存在返回 None"""
    kind, path = PACKAGES[pkg]
    if kind == "folder":
        p = os.path.join(path, f"{locale}.SC2Data", "LocalizedData", f"{fname}.txt")
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            raw = f.read()
    else:
        from mpyq import MPQArchive  # 延迟导入, 便于只跑纯文本工具
        archive = MPQArchive(path)
        raw = _read_mpq_file(archive, f"{locale}.SC2Data\\LocalizedData\\{fname}.txt")
    data = decompress_blob(raw)
    if data is None:
        return None
    return data.decode("utf-8-sig", "replace").replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------- 键分类

TRIG_EDITOR_HEADS = {"Category", "Variable", "Trigger", "FunctionDef", "ParamDef",
                     "PresetValue", "Structure", "CustomScript", "Library"}
# 内部标识符(资源名/自动生成表达式), 玩家不可见 → 不翻译
INTERNAL_HEADS = {"Sound", "Soundtrack", "Model", "Mover", "Light", "Footprint",
                  "Terrain", "Kinetic", "RequirementNode"}
NAME_SUBS = {"Name"}
TIP_SUBS = {"Tooltip", "Tip", "Subtitle", "Info", "LifeArmorName", "ShieldArmorName",
            "LifeArmorTooltip", "HighlightTooltip", "TargetMessage", "Description",
            "Desc", "Text", "Message", "Hint", "Label", "Title"}
# 这些 head 下的非 Name/Tooltip 段也算玩家可见(成就/大厅/UI 等)
VISIBLE_HEADS = {"Achievement", "Terrain", "Kinetic", "UI", "UserData", "Attribute",
                 "Variant"}


@dataclass
class KeyInfo:
    pkg: str
    fname: str
    key: str
    en: str
    cls: str = ""
    include: bool = False
    flags: List[str] = field(default_factory=list)


def classify(key: str) -> Tuple[str, bool]:
    """返回 (类别, 是否玩家可见需翻译)"""
    seg = [x for x in key.split("/") if x != ""]
    if not seg:
        return "empty-key", False
    head = seg[0]
    if head == "Param":
        if len(seg) > 1 and seg[1] == "Expression":
            return "param-expression", False     # 纯标记(<c val=...>~A~</c>)
        return "trigger-text", True              # 游戏内警报/聊天/面板文案
    if any(x.startswith("Editor") for x in seg[1:]) or any("EditorPrefix" in x or "EditorSuffix" in x
                                                          or "EditorDescription" in x for x in seg):
        return "editor-only", False
    if head in TRIG_EDITOR_HEADS:
        return "trigger-editor", False
    if "Hotkey" in seg:
        return "hotkey", False
    # 内部标识符(资源/音效/模型/自动生成表达式) — 玩家不可见, 不要求翻译
    if head in INTERNAL_HEADS and len(seg) > 1 and seg[1] == "Name":
        return "internal-name", False
    if len(seg) > 1 and seg[1] in NAME_SUBS:
        return "name", True
    if len(seg) > 1 and seg[1] in TIP_SUBS:
        return "tip", True
    if head in VISIBLE_HEADS or head.startswith("Attribute"):
        return "visible-other", True
    return "unknown", True                        # 保守: 未知键默认翻, 由人工表复核


MARKUP_PATTERNS = [
    re.compile(r"<n/>"),                                  # 换行
    re.compile(r"<c val=\"[0-9A-Fa-f]+\">"),               # 颜色开标签
    re.compile(r"</c>"),
    re.compile(r"<s val=\"[^\"]+\">"),                    # 样式开标签
    re.compile(r"</s>"),
    re.compile(r"<IMG [^>]*>", re.I),                      # 图文
    re.compile(r"~[A-Za-z]~"),                             # 占位(~A~)
    re.compile(r"##[^#]+##"),                              # 模板变量
]

MARKUP_LABELS = ["<n/>", "<c val=", "</c>", "<s val=", "</s>", "<IMG", "~词~", "##词##"]


def markup_counts(value: str) -> List[int]:
    return [len(p.findall(value)) for p in MARKUP_PATTERNS]


def parse_kv(text: str) -> List[Tuple[str, str]]:
    """解析 Key=Value 文本, 保持原顺序; 值为空的行保留"""
    out = []
    for line in text.split("\n"):
        line = line.lstrip("\ufeff")
        if not line.strip():
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out.append((k, v))
    return out


def value_flags(key: str, value: str) -> List[str]:
    flags = []
    if value.strip() == "":
        flags.append("empty-value")
    if value.strip() == key.strip():
        flags.append("value==key")
    if value.strip() in ("", "! "):
        flags.append("punct-only")
    if value.strip() and re.fullmatch(r"[^0-9A-Za-z\s]{0,3}", value.strip()):
        flags.append("punct-only")
    if value.strip() and not re.search(r"[A-Za-z\u4e00-\u9fff]", value):
        flags.append("no-letters")
    if all(c == 0 for c in markup_counts(value)) is False and not re.sub(
            r"<[^>]+>|~[A-Za-z]~|##[^#]+##", "", value).strip():
        flags.append("markup-only")
    return flags


def write_zhcn_text(path: str, pairs: Iterable[Tuple[str, str]]) -> int:
    """写 zhCN 文本: UTF-8 BOM + CRLF (与现网一致)"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [f"{k}={v}" for k, v in pairs]
    body = "\r\n".join(lines) + "\r\n"
    with open(path, "wb") as f:
        f.write(codecs.BOM_UTF8)
        f.write(body.encode("utf-8"))
    return len(lines)


def read_text_file_pairs(path: str) -> List[Tuple[str, str]]:
    with open(path, "rb") as f:
        data = f.read().decode("utf-8-sig", "replace")
    return parse_kv(data)
