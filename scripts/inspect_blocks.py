# -*- coding: utf-8 -*-
"""检查 middle_json 中视觉块与图注的邻接结构（M3 配对策略依据）。"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
mj = json.loads((ROOT / "output/_cache/274e841542934760/middle_json.json").read_text(encoding="utf-8"))


def txt(b, n=60):
    c = b.get("content")
    if isinstance(c, str):
        return c[:n]
    if isinstance(c, list):
        return " ".join(str(s.get("content", "")) for s in c if isinstance(s, dict))[:n]
    return str(c)[:n]


for p in mj["pages"]:
    if p["page_idx"] not in (1, 2, 3):
        continue
    print(f"===== page_idx={p['page_idx']} =====")
    for i, b in enumerate(p["blocks"]):
        t = b.get("type")
        if t in ("image", "chart", "table"):
            print(f"  [{i}] {t:8s} keys={list(b.keys())}")
            for k, v in b.items():
                if k not in ("content", "bbox"):
                    print(f"        {k} = {str(v)[:100]}")
        elif t in ("text", "paragraph_title"):
            print(f"  [{i}] {t:8s} | {txt(b)}")
