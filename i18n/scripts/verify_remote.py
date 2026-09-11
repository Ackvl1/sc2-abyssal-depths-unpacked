#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回读远端 GitHub, 校验本轮上传的 zhCN 产物与本地逐字节一致"""
from __future__ import annotations
import base64, hashlib, os, subprocess, sys

PROJ = r"D:\Users\ex_chenjp28\Downloads\海底_Abyssal"
REPO = "Ackvl1/sc2-abyssal-depths-unpacked"

def gh_bin():
    for c in (os.path.expanduser("~/bin/gh"), r"D:\Users\ex_chenjp28\bin\gh", "gh", "gh.exe"):
        if c in ("gh", "gh.exe") or os.path.exists(c):
            try:
                r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    return c
            except Exception:
                pass
    raise SystemExit("找不到 gh")

GH = gh_bin()
FILES = [
    "Abyssal Depths FULL.SC2Components/zhCN.SC2Data/LocalizedData/GameStrings.txt",
    "Abyssal Depths FULL.SC2Components/zhCN.SC2Data/LocalizedData/ObjectStrings.txt",
    "Abyssal Depths FULL.SC2Components/ComponentList.SC2Components",
    "i18n/out/SemiceMod/zhCN.SC2Data/LocalizedData/GameStrings.txt",
    "i18n/out/SemiceMod/zhCN.SC2Data/LocalizedData/ObjectStrings.txt",
    "i18n/out/SemiceMod/ComponentList.SC2Components",
    "i18n/out/SemiceArt/zhCN.SC2Data/LocalizedData/GameStrings.txt",
    "i18n/out/MapMod/zhCN.SC2Data/LocalizedData/GameStrings.txt",
    "i18n/译文/units_zh.tsv", "i18n/术语表.tsv", "i18n/README.md",
]

head = subprocess.run([GH, "api", f"repos/{REPO}/commits/main", "--jq", ".sha"],
                      capture_output=True, text=True).stdout.strip()
print("远端 main 头:", head)
ok = bad = 0
for f in FILES:
    r = subprocess.run([GH, "api", f"repos/{REPO}/contents/{f}?ref=main", "--jq", ".content"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("✗ 远端缺失:", f, r.stderr[:150]); bad += 1; continue
    remote = base64.b64decode(r.stdout.strip().replace("\n", ""))
    local = open(os.path.join(PROJ, f), "rb").read()
    same = hashlib.md5(remote).hexdigest() == hashlib.md5(local).hexdigest()
    print(("✓" if same else "✗ 不一致"), f"{len(remote):>8}B", f)
    ok += same; bad += (not same)
print(f"\n远端校验: 一致 {ok} / 异常 {bad}")
sys.exit(0 if bad == 0 else 1)
