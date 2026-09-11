#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 — 批量翻译 (DeepSeek API, 可断点续跑)

输入: baseline/units.tsv (uid, en, ...)
输出: 译文/units_zh.tsv  (uid, en, zh, status, model, flags)  —— 追加式, 重启自动跳过已完成
     翻译不落 zhCN 文件, 那一步由 build_zhcn.py 做 (键回填)。

用法:
  python translate.py --limit 40            # 冒烟测试
  python translate.py                       # 全量 (多线程)
  python translate.py --model deepseek-v4-pro --only-failed
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import (BASELINE_DIR, ROOT, TRANS_DIR, install_excepthook,
                     markup_counts, setup_logging)

log = setup_logging("translate", "translate")
install_excepthook(log)

API = "https://api.deepseek.com/v1/chat/completions"
OUT_TSV = os.path.join(TRANS_DIR, "units_zh.tsv")
GLOSSARY_TSV = os.path.join(ROOT, "术语表.tsv")
LOCK = threading.Lock()

# 不译: 这些字符串不需要(或不该)翻译
SKIP_FLAGS = {"punct-only", "no-letters", "markup-only"}

KEEP_TERMS = [
    "Oh No It's Zombies", "ONIZ", "Semicedevin", "Jeetestu", "Chulleyboy",
    "Discord", "Patreon", "Shopify", "TLMC", "Hive Mind", "Battle.net",
]


def get_api_key() -> str:
    """优先环境变量, 其次机器级注册表(与 hermes 启动脚本同源)。不落盘。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        out = subprocess.run(
            ["reg", "query", r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
             "/v", "DEEPSEEK_API_KEY"],
            capture_output=True, text=True, timeout=20).stdout
        if "REG_SZ" in out:
            return out.split("REG_SZ")[-1].strip()
    except Exception:
        log.error("读取注册表失败:\n%s", traceback.format_exc())
    raise RuntimeError("找不到 DEEPSEEK_API_KEY(环境变量与 HKLM 注册表均无)")


def load_glossary() -> Tuple[str, str]:
    """返回 (术语表提示文本, 映射字典用于校验)"""
    lines = []
    mapping = {}
    with open(GLOSSARY_TSV, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            en = (row.get("en") or "").strip()
            zh = (row.get("zh") or "").strip()
            if not en or not zh:
                continue
            mapping[en] = zh
            lines.append(f"{en} = {zh}")
    return "\n".join(lines), mapping


SYSTEM_TMPL = """你是《星际争霸2》街机地图《Oh No It's Zombies: Abyssal Depths》(ONIZ 海底监狱僵尸生存图)的本地化译者。
把英文游戏文本翻成**简体中文**，供中文玩家在游戏内阅读。

硬性规则:
1. 只翻译文本本身，不改动、不新增、不删除任何标记: <n/>(换行)、<c val="XXXXXX">…</c>(颜色)、<s val="XXXX">…</s>(样式)、<IMG path="…">、~X~(占位)、##xx##(变量)。标记在原串的位置必须保持。
2. 译文里**不要出现英文单词**(专有名词例外)。以句号/感叹号结尾的句子保留标点风格；片段串(如 " seconds."、": ")按中文习惯处理(如 " 秒。"、"：" )，保留必要的空格与标点以免拼接错位。
3. 术语必须与下表完全一致(同一词不得出现两种译法):
{glossary}
4. 下列专有名词保持原文不译: {keep}
5. 风格: 游戏内提示语简短有力; 警报类保持紧张感; 幽默/吐槽句保留原味, 不要过度书面化。
6. **准确性优先于文采**: 直译优先, 不要使用成语或文学化意译; 数据/校验类短语(如 "Must not already be present")按字面准确翻译。
7. 数字、单位、颜色代码、% 号保持原样。

输出格式: 只输出一个 JSON 数组，元素为 {{"id": <输入id>, "zh": "<译文>"}}，不要任何解释、不要 markdown 代码块。id 必须与输入一一对应。"""


def build_user_payload(items: List[Dict]) -> str:
    return json.dumps([{"id": it["uid"], "en": it["en"]} for it in items], ensure_ascii=False)


def parse_response(text: str) -> Dict[str, str]:
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\[.*\]", t, re.S)
    if not m:
        raise ValueError("响应中没有 JSON 数组: " + text[:300])
    arr = json.loads(m.group(0))
    out = {}
    for it in arr:
        if isinstance(it, dict) and "id" in it and "zh" in it:
            out[str(it["id"])] = str(it["zh"])
    return out


def call_api(key: str, model: str, system: str, user: str, retries: int = 4) -> Dict[str, str]:
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(API, timeout=180,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"model": model, "temperature": 1.0, "stream": False,
                                    "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": user}]})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return parse_response(content)
        except Exception as e:
            last = e
            wait = min(30, 1.5 ** attempt + random.random())
            log.warning("第 %d/%d 次调用失败: %s —— %.1fs 后重试", attempt, retries, e, wait)
            time.sleep(wait)
    raise RuntimeError(f"调用彻底失败: {last}")


def validate(en: str, zh: str, glossary: Dict[str, str]) -> List[str]:
    """返回告警列表(不阻断, 记入 flags)"""
    w = []
    if not zh or not zh.strip():
        w.append("empty-zh")
    if markup_counts(en) != markup_counts(zh):
        w.append("markup-mismatch")
    if zh and len(zh) > max(40, len(en) * 3):
        w.append("too-long")
    if zh and zh.strip() == en.strip() and len(en) > 12:
        w.append("untranslated")
    for term in KEEP_TERMS:
        pass
    # 术语一致性: 原文出现该术语但译文未用指定中文
    for en_t, zh_t in glossary.items():
        if en_t in en and re.search(r"[A-Za-z]", en_t) and len(en_t) > 3:
            if en_t.lower() in en.lower() and zh_t not in zh and len(zh_t) > 1:
                w.append(f"glossary?{en_t}")
                break
    return w


def load_done() -> Dict[str, str]:
    done = {}
    if os.path.exists(OUT_TSV):
        with open(OUT_TSV, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row.get("status") == "ok" and row.get("zh"):
                    done[row["uid"]] = row["zh"]
    return done


def append_rows(rows: List[Dict]) -> None:
    os.makedirs(TRANS_DIR, exist_ok=True)
    new = not os.path.exists(OUT_TSV)
    with LOCK:
        with open(OUT_TSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="\t")
            if new:
                w.writerow(["uid", "en", "zh", "status", "model", "flags"])
            for r in rows:
                w.writerow([r["uid"], r["en"], r["zh"], r["status"], r["model"], r["flags"]])


def needs_translation(it: Dict) -> bool:
    flags = set((it.get("flags") or "").split(","))
    if flags & SKIP_FLAGS:
        return False
    if not it["en"].strip():
        return False
    if not re.search(r"[A-Za-z]", it["en"]):
        return False
    return True


def make_batches(items: List[Dict], max_chars: int = 2200, max_items: int = 35) -> List[List[Dict]]:
    batches, cur, cur_chars = [], [], 0
    for it in items:
        n = len(it["en"]) + len(it["uid"]) + 20
        if cur and (cur_chars + n > max_chars or len(cur) >= max_items):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(it)
        cur_chars += n
    if cur:
        batches.append(cur)
    return batches


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--limit", type=int, default=0, help="只翻前 N 个单元(冒烟)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only-failed", action="store_true")
    args = ap.parse_args()

    key = get_api_key()
    glossary_text, glossary = load_glossary()
    system = SYSTEM_TMPL.format(glossary=glossary_text, keep=", ".join(KEEP_TERMS))
    log.info("模型=%s 术语=%d 条 workers=%d", args.model, len(glossary), args.workers)

    units = list(csv.DictReader(open(os.path.join(BASELINE_DIR, "units.tsv"), encoding="utf-8"), delimiter="\t"))
    done = load_done()
    todo = [u for u in units if needs_translation(u) and u["uid"] not in done]
    log.info("翻译单元 %d 个, 已完成 %d, 待翻 %d", len(units), len(done), len(todo))
    if args.only_failed:
        failed = {r["uid"] for r in csv.DictReader(open(OUT_TSV, encoding="utf-8"), delimiter="\t")
                  if r.get("status") != "ok"}
        todo = [u for u in todo if u["uid"] in failed]
    if args.limit:
        todo = todo[:args.limit]

    batches = make_batches(todo)
    log.info("分 %d 批", len(batches))
    stats = {"ok": 0, "warn": 0, "fail": 0, "batch_fail": 0}

    def work(batch, idx):
        try:
            res = call_api(key, args.model, system, build_user_payload(batch))
            rows = []
            for it in batch:
                zh = res.get(it["uid"], "")
                flags = validate(it["en"], zh, glossary)
                status = "ok" if zh and not flags else ("warn" if zh else "fail")
                rows.append({"uid": it["uid"], "en": it["en"], "zh": zh, "status": status,
                             "model": args.model, "flags": ",".join(flags)})
            append_rows(rows)
            n_ok = sum(1 for r in rows if r["status"] == "ok")
            n_warn = sum(1 for r in rows if r["status"] == "warn")
            n_fail = sum(1 for r in rows if r["status"] == "fail")
            with LOCK:
                stats["ok"] += n_ok; stats["warn"] += n_warn; stats["fail"] += n_fail
            log.info("批 %3d/%d 完成: ok=%d warn=%d fail=%d", idx, len(batches), n_ok, n_warn, n_fail)
        except Exception:
            with LOCK:
                stats["batch_fail"] += 1
            log.error("批 %d 失败:\n%s", idx, traceback.format_exc())

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, b, i) for i, b in enumerate(batches, 1)]
        for _ in as_completed(futs):
            pass
    log.info("完成: %s, 耗时 %.1fs", stats, time.time() - t0)
    return 0 if stats["fail"] == 0 and stats["batch_fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
