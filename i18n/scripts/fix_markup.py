#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标记修复 — 生成 译文/overrides.tsv (译文覆盖表)

背景: LLM 偶尔会多补/漏掉 SC2 富文本标记(<s val=...>/<c val=...>)。本脚本:
  1) 比对 enUS 原串与译文的标记计数, 找出不一致的翻译单元
  2) 自动修可机械修的(多余结尾 </s>)
  3) 手工覆盖表 译文/overrides_manual.tsv (en<TAB>zh) 优先
  4) 输出 译文/overrides.tsv 供 build_zhcn.py 覆盖使用; 仍未解决的打印出来要求人工处理

用法: python fix_markup.py
"""
from __future__ import annotations

import csv
import os
import re
import sys
import traceback
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import (BASELINE_DIR, ROOT, TRANS_DIR, install_excepthook,
                     markup_counts, setup_logging)

log = setup_logging("fix_markup", "fix_markup")
install_excepthook(log)

MANUAL = os.path.join(TRANS_DIR, "overrides_manual.tsv")
OUT = os.path.join(TRANS_DIR, "overrides.tsv")


def load_manual() -> Dict[str, str]:
    m = {}
    if os.path.exists(MANUAL):
        with open(MANUAL, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                en = (row.get("en") or "").strip()
                zh = row.get("zh") or ""
                if en and zh.strip():
                    m[en] = zh
    log.info("手工覆盖 %d 条", len(m))
    return m


def main() -> int:
    try:
        keys = list(csv.DictReader(open(os.path.join(BASELINE_DIR, "keys.tsv"), encoding="utf-8"), delimiter="\t"))
        zh = {r["en"]: r["zh"] for r in csv.DictReader(open(os.path.join(TRANS_DIR, "units_zh.tsv"),
                                                            encoding="utf-8"), delimiter="\t")
              if r.get("zh")}
        manual = load_manual()

        en_used = {}
        for r in keys:
            if r["include"] == "1":
                en_used.setdefault(r["en"], 0)
                en_used[r["en"]] += 1

        fixes: List[Tuple[str, str, str]] = []
        unresolved: List[Tuple[str, str, str]] = []
        for en, tgt in zh.items():
            if en not in en_used:
                continue
            cur = manual.get(en, tgt)
            if markup_counts(en) == markup_counts(cur):
                continue
            fixed = cur
            # 规则 1: 原文没有 </s> 而译文多了一个 → 去掉末尾多余的 </s>
            if markup_counts(en)[4] == 0 and markup_counts(fixed)[4] > 0:
                fixed2 = fixed.rstrip()
                if fixed2.endswith("</s>"):
                    fixed2 = fixed2[: -len("</s>")].rstrip()
                    if markup_counts(en) == markup_counts(fixed2):
                        fixes.append((en, fixed2, "auto: stripped surplus </s>"))
                        continue
            unresolved.append((en, tgt, f"en={markup_counts(en)} zh={markup_counts(cur)}"))

        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["en", "zh", "reason"])
            for en, z, why in fixes + [(k, v, "manual") for k, v in manual.items()]:
                w.writerow([en, z, why])
        log.info("写出 %s: 自动修 %d, 手工 %d, 未解决 %d", OUT, len(fixes), len(manual), len(unresolved))
        for en, tgt, why in unresolved:
            log.warning("未解决标记不一致 (%s):\n  EN: %s\n  ZH: %s", why, en[:200], tgt[:200])
        return 0 if not unresolved else 2
    except Exception:
        log.error("修复失败:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
