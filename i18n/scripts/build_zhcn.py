#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 — 组装 zhCN 文本 + 补 ComponentList locale 声明

输入: baseline/keys.tsv, 译文/units_zh.tsv, 各包 enUS 原文
输出:
  Abyssal Depths FULL.SC2Components/zhCN.SC2Data/LocalizedData/*.txt   (就地, 地图组件夹)
  i18n/out/<pkg>/zhCN.SC2Data/LocalizedData/*.txt                      (3 个 Mod 的产出)
  i18n/out/<pkg>/ComponentList.SC2Components                           (已补 zhCN 声明)
  baseline/enus_md5.json                                               (首次运行记录 enUS 原版指纹)

规则:
  - enUS 一律不改动(校验见 verify.py)
  - zhCN 只写有译文的键; 已存在的 zhCN 键(手工 10 行等)全部保留
  - 值为空且键本身是英文正文的行(散文键) → 译文取自同文本的 en 值; 找不到则保持原样
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import traceback
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import (BASELINE_DIR, FULL_FOLDER, PACKAGES, PROJ, ROOT, TEXT_FILES,
                     TRANS_DIR, classify, install_excepthook, parse_kv,
                     read_pkg_text, setup_logging, write_zhcn_text)

log = setup_logging("build_zhcn", "build_zhcn")
install_excepthook(log)

OUT_DIR = os.path.join(ROOT, "out")
# 原版人工 zhCN 只属于地图层(FULLMap/MapMod), 不可套用到依赖 Mod
PROTECTED_PKGS = {"FULLMap", "MapMod"}
MD5_JSON = os.path.join(BASELINE_DIR, "enus_md5.json")


def load_translations() -> Dict[str, str]:
    """返回 en -> zh 映射 (以英文原文为键, 与 uid 编号解耦), 并叠加 overrides.tsv"""
    p = os.path.join(TRANS_DIR, "units_zh.tsv")
    m: Dict[str, str] = {}
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("zh") and r.get("en"):
                m[r["en"]] = r["zh"]
    ov = os.path.join(TRANS_DIR, "overrides.tsv")
    n_ov = 0
    if os.path.exists(ov):
        with open(ov, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("zh") and r.get("en"):
                    m[r["en"]] = r["zh"]
                    n_ov += 1
    log.info("载入译文 %d 条 (覆盖表 %d 条) <- %s", len(m), n_ov, p)
    return m


def load_units() -> Dict[str, str]:
    """en -> uid (用于把 enUS 的键回填到译文)"""
    p = os.path.join(BASELINE_DIR, "units.tsv")
    m = {}
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            m.setdefault(r["en"], r["uid"])
    return m


def record_md5() -> None:
    """记录 enUS 原版指纹(只记一次, 用于验证 enUS 未被改动)"""
    if os.path.exists(MD5_JSON):
        log.info("enUS 指纹已存在, 跳过记录")
        return
    rec = {}
    for pkg in PACKAGES:
        for fname in TEXT_FILES + ("TriggerStrings", "GameHotkeys"):
            text = read_pkg_text(pkg, "enUS", fname)
            if text is None:
                continue
            rec[f"{pkg}/{fname}"] = hashlib.md5(text.encode("utf-8")).hexdigest()
    os.makedirs(BASELINE_DIR, exist_ok=True)
    with open(MD5_JSON, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    log.info("记录 enUS 指纹 %d 项 -> %s", len(rec), MD5_JSON)


def patch_componentlist(pkg: str, text: str) -> Tuple[str, bool]:
    if 'Locale="zhCN"' in text:
        return text, False
    anchor = '    <DataComponent Type="text" Locale="enUS">GameText</DataComponent>'
    if anchor in text:
        new = text.replace(anchor, anchor + '\r\n    <DataComponent Type="text" Locale="zhCN">GameText</DataComponent>')
    elif "</Components>" in text:
        new = text.replace("</Components>", '    <DataComponent Type="text" Locale="zhCN">GameText</DataComponent>\r\n</Components>')
    else:
        return text, False
    log.info("%s: ComponentList 已补 zhCN text 声明", pkg)
    return new, True


def read_pkg_componentlist(pkg: str) -> str | None:
    kind, path = PACKAGES[pkg]
    if kind == "folder":
        p = os.path.join(path, "ComponentList.SC2Components")
        if os.path.exists(p):
            return open(p, "rb").read().decode("utf-8-sig", "replace")
        return None
    from mpyq import MPQArchive
    from lib_sc2 import _read_mpq_file, decompress_blob
    raw = _read_mpq_file(MPQArchive(path), "ComponentList.SC2Components")
    data = decompress_blob(raw)
    return data.decode("utf-8-sig", "replace") if data else None


def load_protected() -> Dict[str, str]:
    """原版人工 zhCN 条目(最高优先级, 不允许被机翻覆盖)

    来源: MapMod 的 .SC2Mod(未改动过) 里的 zhCN.SC2Data —— 与地图组件夹的原版 zhCN 逐项相同。
    另外可叠加 译文/protected.tsv (en=key 形式, 供后续人工修正)。
    """
    proto: Dict[str, str] = {}
    try:
        text = read_pkg_text("MapMod", "zhCN", "GameStrings")
        if text:
            proto.update(dict(parse_kv(text)))
            log.info("从 MapMod 原版提取到 %d 条人工 zhCN(受保护)", len(proto))
    except Exception:
        log.warning("读取原版 zhCN 失败:\n%s", traceback.format_exc())
    p = os.path.join(TRANS_DIR, "protected.tsv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("key"):
                    proto[r["key"]] = r.get("zh", "")
        log.info("叠加 protected.tsv -> 共 %d 条", len(proto))
    return proto


def build_package(pkg: str, tr: Dict[str, str], protected_all: Dict[str, str]) -> Dict[str, int]:
    protected = protected_all if pkg in PROTECTED_PKGS else {}
    stat = {"keys": 0, "translated": 0, "protected": 0, "untranslated": 0}
    for fname in TEXT_FILES:
        en_text = read_pkg_text(pkg, "enUS", fname)
        if en_text is None:
            continue
        pairs = parse_kv(en_text)
        out: List[Tuple[str, str]] = []
        seen = set()
        for key, en in pairs:
            seen.add(key)
            cls, include = classify(key)
            if key in protected:
                out.append((key, protected[key]))
                stat["protected"] += 1
            elif tr.get(en):
                out.append((key, tr[en]))
                stat["translated"] += 1
            elif not en.strip() and " " in key and tr.get(key):
                out.append((key, tr[key]))          # 散文键: 键本身是英文正文
                stat["translated"] += 1
            else:
                out.append((key, en))               # 无译文 → 与原文本一致(等价于回退 enUS)
                stat["untranslated"] += 1
            stat["keys"] += 1

        # 原版 zhCN 里有、enUS 里没有的键(如 MapInfo/Player00/Name) 一并保留
        for k, v in protected.items():
            if k not in seen:
                out.append((k, v))
                stat["protected"] += 1

        target = (os.path.join(FULL_FOLDER, "zhCN.SC2Data", "LocalizedData", f"{fname}.txt")
                  if pkg == "FULLMap" else
                  os.path.join(OUT_DIR, pkg, "zhCN.SC2Data", "LocalizedData", f"{fname}.txt"))
        n = write_zhcn_text(target, out)
        log.info("%s/%s zhCN: 写出 %d 行 (译 %d / 原版保留 %d / 未译 %d) -> %s",
                 pkg, fname, n, stat["translated"], stat["protected"], stat["untranslated"], target)
    return stat


def main() -> int:
    try:
        record_md5()
        tr = load_translations()
        protected = load_protected()
        summary = {}
        for pkg in PACKAGES:
            if not os.path.exists(PACKAGES[pkg][1]):
                log.warning("跳过不存在的包: %s", pkg)
                continue
            summary[pkg] = build_package(pkg, tr, protected)
            cl = read_pkg_componentlist(pkg)
            if cl is None:
                log.warning("%s: 没有 ComponentList(入口壳/依赖 Mod 属正常), 仅产出 zhCN 文本", pkg)
                continue
            new, changed = patch_componentlist(pkg, cl)
            if changed:
                tgt = (os.path.join(FULL_FOLDER, "ComponentList.SC2Components") if pkg == "FULLMap"
                       else os.path.join(OUT_DIR, pkg, "ComponentList.SC2Components"))
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                with open(tgt, "wb") as f:
                    import codecs
                    f.write(codecs.BOM_UTF8)
                    f.write(new.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
                log.info("%s -> %s", pkg, tgt)
        log.info("汇总: %s", json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception:
        log.error("组装失败:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
