#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把汉化产物推送到 GitHub (Git Data API, 适合 github.com:443 被墙的网络)

鉴权: 优先 $GITHUB_TOKEN, 否则调 `gh auth token`(本机 gh 已登录 Ackvl1)。
提交方式: base_tree = 远端 main 的树 → 只新增/覆盖本次文件, 不删除既有内容。

用法:
  python push_github.py --dry-run     # 只列出将要上传的文件
  python push_github.py               # 真推
  python push_github.py --message "自定义提交信息"
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import traceback
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_sc2 import FULL_FOLDER, PROJ, ROOT, install_excepthook, setup_logging

log = setup_logging("push", "push_github")
install_excepthook(log)

REPO = "Ackvl1/sc2-abyssal-depths-unpacked"
BRANCH = "main"
API = "https://api.github.com"
MAX_BLOB = 90 * 1024 * 1024     # API 单 blob 上限 100MB, 留余量

DEFAULT_MSG = "i18n(zhCN): 玩家可见文本中文翻译 + 抽取/翻译/组装/校验工具链"

# 要上传的文件/目录(相对项目根), 排除日志与缓存
INCLUDE = [
    ("i18n/PRD-海底Abyssal汉化.md", "file"),
    ("i18n/README.md", "file"),
    ("i18n/术语表.tsv", "file"),
    ("i18n/scripts", "dir"),
    ("i18n/baseline", "dir"),
    ("i18n/译文", "dir"),
    ("i18n/out", "dir"),
]
INCLUDE_MAP_FILES = [
    ("Abyssal Depths FULL.SC2Components/zhCN.SC2Data/LocalizedData", "dir"),
    ("Abyssal Depths FULL.SC2Components/ComponentList.SC2Components", "file"),
]
EXCLUDE_EXT = {".pyc", ".log"}
EXCLUDE_DIRS = {"__pycache__", "logs"}


def _gh_bin() -> str | None:
    """定位 gh 可执行文件: PATH → 常见安装位置 → git-bash(MSYS 下 gh 无 .exe 后缀)"""
    import shutil
    for cand in (shutil.which("gh"), shutil.which("gh.exe")):
        if cand:
            return cand
    for cand in (os.path.expanduser("~/bin/gh"), os.path.expanduser("~/bin/gh.exe"),
                 r"C:\Program Files\GitHub CLI\gh.exe",
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "GitHub CLI", "gh.exe")):
        if cand and os.path.exists(cand):
            return cand
    return None


def get_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    gh = _gh_bin()
    if gh:
        out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
        log.warning("直接调用 gh 失败(rc=%s): %s", out.returncode, out.stderr[:200])
        # MSYS 环境下 gh 是无后缀 shell 脚本/二进制, 经 bash 调用更稳
        out = subprocess.run(["bash", "-lc", "gh auth token"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    raise RuntimeError("拿不到 GitHub token(既无 GITHUB_TOKEN, gh 也未登录)")


def collect() -> List[str]:
    files: List[str] = []
    for rel, kind in INCLUDE + INCLUDE_MAP_FILES:
        p = os.path.join(PROJ, rel)
        if not os.path.exists(p):
            log.warning("不存在, 跳过: %s", rel)
            continue
        if kind == "file":
            files.append(rel)
            continue
        for dp, dn, fn in os.walk(p):
            dn[:] = [d for d in dn if d not in EXCLUDE_DIRS]
            for f in fn:
                if os.path.splitext(f)[1].lower() in EXCLUDE_EXT:
                    continue
                full = os.path.join(dp, f)
                if os.path.getsize(full) > MAX_BLOB:
                    log.warning("超过单 blob 上限, 跳过: %s (%.1fMB)", full, os.path.getsize(full) / 1048576)
                    continue
                files.append(os.path.relpath(full, PROJ).replace("\\", "/"))
    return sorted(set(files))


def api(token: str, path: str, data=None, method: str = "GET", retries: int = 3):
    url = f"{API}/repos/{REPO}{path}"
    body = json.dumps(data).encode() if data is not None else None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, data=body, method=method)
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "sc2-i18n-push")
            with urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            detail = e.read().decode()[:400]
            if e.code in (502, 503, 429) and attempt < retries:
                log.warning("HTTP %s, %.0fs 后重试: %s", e.code, 3 * attempt, detail)
                time.sleep(3 * attempt)
                continue
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {detail}")
        except URLError as e:
            if attempt < retries:
                log.warning("网络错误, 重试: %s", e)
                time.sleep(3 * attempt)
                continue
            raise
    raise RuntimeError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--message", default=DEFAULT_MSG)
    args = ap.parse_args()

    try:
        files = collect()
        total = sum(os.path.getsize(os.path.join(PROJ, f)) for f in files)
        log.info("待上传 %d 个文件, 共 %.2f MB", len(files), total / 1048576)
        for f in files:
            log.info("  %8.1fKB  %s", os.path.getsize(os.path.join(PROJ, f)) / 1024, f)
        if args.dry_run:
            return 0

        token = get_token()
        ref = api(token, f"/git/refs/heads/{BRANCH}")
        base_sha = ref["object"]["sha"]
        base_tree = api(token, f"/git/commits/{base_sha}")["tree"]["sha"]
        log.info("远端 %s 头 %s (tree %s)", BRANCH, base_sha[:8], base_tree[:8])

        tree_items = []
        for i, f in enumerate(files, 1):
            raw = open(os.path.join(PROJ, f), "rb").read()
            r = api(token, "/git/blobs",
                    {"content": base64.b64encode(raw).decode(), "encoding": "base64"}, method="POST")
            tree_items.append({"path": f, "mode": "100644", "type": "blob", "sha": r["sha"]})
            log.info("[%d/%d] blob %7.1fKB %s", i, len(files), len(raw) / 1024, f)

        tree = api(token, "/git/trees", {"tree": tree_items, "base_tree": base_tree}, method="POST")
        commit = api(token, "/git/commits",
                     {"message": args.message, "tree": tree["sha"], "parents": [base_sha]}, method="POST")
        api(token, f"/git/refs/heads/{BRANCH}", {"sha": commit["sha"]}, method="PATCH")
        log.info("推送成功: %s/commit/%s", f"https://github.com/{REPO}", commit["sha"])
        return 0
    except Exception:
        log.error("推送失败:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
