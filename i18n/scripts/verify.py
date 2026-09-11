#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 校验 — 断言驱动(全绿才进重打包)

断言:
  A1 键集合: 每包 zhCN 的键 ⊆ 该包 enUS 的键 (手工条目除外, 单独列出)
  A2 覆盖率: 玩家可见键的译出率 >= --min-coverage (默认 0.98)
  A3 标记守恒: zhCN 值相对 enUS 值的 <n/> <c> <s> <IMG> 数量一致
  A4 格式: UTF-8 BOM + CRLF + 无重复键 + 无 '=' 出现在键侧
  A5 enUS 未被改动: md5 与 baseline/enus_md5.json 一致
用法: python verify.py
"""
from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import json
import os
import sys
import traceback
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import (BASELINE_DIR, FULL_FOLDER, PACKAGES, ROOT, TEXT_FILES,
                     classify, install_excepthook, markup_counts, parse_kv,
                     read_pkg_text, setup_logging)

log = setup_logging("verify", "verify")
install_excepthook(log)
MD5_JSON = os.path.join(BASELINE_DIR, "enus_md5.json")
OUT_DIR = os.path.join(ROOT, "out")

problems: List[str] = []
warns: List[str] = []


def zhcn_path(pkg: str, fname: str) -> str:
    return (os.path.join(FULL_FOLDER, "zhCN.SC2Data", "LocalizedData", f"{fname}.txt")
            if pkg == "FULLMap" else
            os.path.join(OUT_DIR, pkg, "zhCN.SC2Data", "LocalizedData", f"{fname}.txt"))


def load_protected() -> set:
    """原版人工 zhCN 键(来自未改动的 MapMod) —— 这些键允许与 enUS 标记不同, 不参与断言"""
    try:
        text = read_pkg_text("MapMod", "zhCN", "GameStrings")
        s = {k for k, _ in parse_kv(text)} if text else set()
        log.info("受保护的原版 zhCN 键: %d 个", len(s))
        return s
    except Exception:
        log.warning("读取原版 zhCN 失败: %s", traceback.format_exc())
        return set()


def check_a1_a2_a3_a4(pkg: str, protected: set) -> Dict:
    st = {"keys": 0, "visible": 0, "translated": 0, "unknown_keys": 0, "markup_bad": 0,
          "covered": 0.0, "skipped_symbol": 0, "protected": 0}
    for fname in TEXT_FILES:
        en_text = read_pkg_text(pkg, "enUS", fname)
        if en_text is None:
            continue
        p = zhcn_path(pkg, fname)
        if not os.path.exists(p):
            problems.append(f"A1 {pkg}/{fname}: zhCN 文件缺失 {p}")
            continue
        raw = open(p, "rb").read()
        if not raw.startswith(codecs.BOM_UTF8):
            problems.append(f"A4 {pkg}/{fname}: 缺少 UTF-8 BOM")
        if b"\r\n" not in raw:
            problems.append(f"A4 {pkg}/{fname}: 行尾不是 CRLF")
        text = raw.decode("utf-8-sig", "replace")
        zh_pairs = parse_kv(text)
        keys = [k for k, _ in zh_pairs]
        if len(keys) != len(set(keys)):
            problems.append(f"A4 {pkg}/{fname}: 存在重复键")
        if any("=" in k for k in keys):
            problems.append(f"A4 {pkg}/{fname}: 键里出现 '='")
        zh_map = dict(zh_pairs)
        en_map = dict(parse_kv(en_text))

        for k in zh_map:
            if k not in en_map:
                warns.append(f"A1 {pkg}/{fname}: zhCN 多出键(手工条目?) {k}")
                st["unknown_keys"] += 1
        for k, en in en_map.items():
            cls, visible = classify(k)
            st["keys"] += 1
            if k in protected and pkg in ("FULLMap", "MapMod"):
                st["protected"] += 1            # 原版人工中文, 允许与 enUS 文案/标记不同
                continue
            if not visible:
                continue
            if not __import__("re").search(r"[A-Za-z]", en):
                st["skipped_symbol"] += 1          # 纯符号/数字串, 无需翻译
                continue
            st["visible"] += 1
            zh = zh_map.get(k, "")
            if not zh.strip() or zh == en:
                if en.strip() and " " not in k:
                    pass
                continue
            if zh != en:
                st["translated"] += 1
            if markup_counts(en) != markup_counts(zh):
                st["markup_bad"] += 1
                problems.append(f"A3 {pkg}/{fname}: 标记不一致 key={k} en={markup_counts(en)} zh={markup_counts(zh)}")
        st["covered"] = st["translated"] / st["visible"] if st["visible"] else 1.0
    return st


def check_a5() -> None:
    if not os.path.exists(MD5_JSON):
        warns.append("A5: 无 enUS 指纹基线, 跳过")
        return
    rec = json.load(open(MD5_JSON, encoding="utf-8"))
    for k, md5 in rec.items():
        pkg, fname = k.split("/", 1)
        text = read_pkg_text(pkg, "enUS", fname)
        if text is None:
            problems.append(f"A5 {k}: enUS 读取失败")
            continue
        cur = hashlib.md5(text.encode("utf-8")).hexdigest()
        if cur != md5:
            problems.append(f"A5 {k}: enUS 被改动! md5 {md5} -> {cur}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-coverage", type=float, default=0.98)
    args = ap.parse_args()
    try:
        protected = load_protected()
        for pkg in PACKAGES:
            if not os.path.exists(PACKAGES[pkg][1]):
                warns.append(f"包不存在, 跳过: {pkg}")
                continue
            st = check_a1_a2_a3_a4(pkg, protected)
            log.info("%-11s 键 %5d | 玩家可见 %5d | 已译 %5d | 覆盖 %.1f%% | 标记错 %d | 原版保护 %d",
                     pkg, st["keys"], st["visible"], st["translated"], st["covered"] * 100,
                     st["markup_bad"], st["protected"])
            if st["covered"] < args.min_coverage:
                problems.append(f"A2 {pkg}: 覆盖率 {st['covered']:.1%} < {args.min_coverage:.0%}")
        check_a5()

        for w in warns:
            log.warning(w)
        if problems:
            for p in problems:
                log.error("FAIL %s", p)
            log.error("校验失败: %d 项", len(problems))
            return 1
        log.info("全部断言通过 (A1-A5)")
        return 0
    except Exception:
        log.error("校验异常:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
