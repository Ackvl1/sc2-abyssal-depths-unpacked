#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1/M2 — 基准抽取

从 4 个包的 enUS GameStrings/ObjectStrings 抽出"待翻清单":
  baseline/keys.tsv    每个包的每个键一行 (pkg, file, key, en, cls, include, flags)
  baseline/units.tsv   去重后的翻译单元 (uid, en, n_keys, pkgs, cls, flags) —— 翻译按此表进行
  baseline/summary.json 统计

用法:
  python extract_baseline.py            # 全量
  python extract_baseline.py --stats    # 只打印统计
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import traceback
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import (BASELINE_DIR, PACKAGES, TEXT_FILES, KeyInfo, classify,
                     install_excepthook, parse_kv, read_pkg_text, setup_logging,
                     value_flags)

log = setup_logging("extract", "extract_baseline")
install_excepthook(log)


def collect() -> "list[KeyInfo]":
    rows: "list[KeyInfo]" = []
    for pkg in PACKAGES:
        if not os.path.exists(PACKAGES[pkg][1]):
            log.warning("包不存在, 跳过: %s -> %s", pkg, PACKAGES[pkg][1])
            continue
        for fname in TEXT_FILES:
            text = read_pkg_text(pkg, "enUS", fname)
            if text is None:
                log.info("%s/%s: 无 enUS 文本", pkg, fname)
                continue
            pairs = parse_kv(text)
            n_inc = 0
            for key, en in pairs:
                cls, include = classify(key)
                ki = KeyInfo(pkg, fname, key, en, cls, include, value_flags(key, en))
                rows.append(ki)
                n_inc += 1 if include else 0
            log.info("%s/%s: %d 行, 其中玩家可见 %d 行", pkg, fname, len(pairs), n_inc)
    return rows


def write_keys(rows: "list[KeyInfo]") -> str:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    path = os.path.join(BASELINE_DIR, "keys.tsv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["pkg", "file", "key", "en", "cls", "include", "flags"])
        for r in rows:
            w.writerow([r.pkg, r.fname, r.key, r.en, r.cls, int(r.include), ",".join(r.flags)])
    log.info("写出 %s (%d 行)", path, len(rows))
    return path


def write_units(rows: "list[KeyInfo]") -> str:
    """按英文原文去重 → 翻译单元表"""
    by_val: "dict[str, dict]" = {}
    for r in rows:
        if not r.include:
            continue
        d = by_val.setdefault(r.en, {"cls": Counter(), "pkgs": set(), "keys": [], "flags": set()})
        d["cls"][r.cls] += 1
        d["pkgs"].add(r.pkg)
        d["keys"].append(f"{r.pkg}:{r.fname}:{r.key}")
        d["flags"].update(r.flags)

    path = os.path.join(BASELINE_DIR, "units.tsv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["uid", "en", "n_keys", "pkgs", "cls", "flags"])
        for i, (en, d) in enumerate(sorted(by_val.items(), key=lambda kv: (-len(kv[1]["keys"]), kv[0])), 1):
            w.writerow([f"u{i:05d}", en, len(d["keys"]), "|".join(sorted(d["pkgs"])),
                        d["cls"].most_common(1)[0][0], ",".join(sorted(d["flags"]))])
    log.info("写出 %s (%d 个唯一翻译单元)", path, len(by_val))
    return path


def write_summary(rows: "list[KeyInfo]") -> str:
    inc = [r for r in rows if r.include]
    summary = {
        "packages": {p: PACKAGES[p][1] for p in PACKAGES},
        "lines_total": len(rows),
        "lines_player_visible": len(inc),
        "unique_units": len({r.en for r in inc}),
        "by_class": dict(Counter(r.cls for r in rows).most_common()),
        "by_class_visible": dict(Counter(r.cls for r in inc).most_common()),
        "by_pkg_visible": dict(Counter(r.pkg for r in inc).most_common()),
        "flag_counts": dict(Counter(f for r in inc for f in r.flags).most_common()),
        "chars_total_en": sum(len(r.en) for r in inc),
    }
    path = os.path.join(BASELINE_DIR, "summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log.info("写出 %s", path)
    return path


def print_stats() -> None:
    with open(os.path.join(BASELINE_DIR, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    print(json.dumps(s, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    if args.stats:
        print_stats()
        return 0
    try:
        rows = collect()
        write_keys(rows)
        write_units(rows)
        write_summary(rows)
        print_stats()
        return 0
    except Exception:
        log.error("抽取失败:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
