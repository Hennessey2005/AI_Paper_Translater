# -*- coding: utf-8 -*-
"""P0-A 回归：标题提取 / 目录名净化 / 撞名路由（v2.1）。

用法: python scripts/title_naming_test.py
依赖 output/_cache/ 下两个已解析缓存（1706.03762v7 / 2507.01821v1）。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paper_translate.title_naming import (  # noqa: E402
    MAX_TITLE_LEN, extract_doc_title, resolve_out_dir, sanitize_dirname)

fails: list[str] = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        got={got!r}\n        want={want!r}"))
    if not ok:
        fails.append(name)


print("== sanitize_dirname ==")
check("普通英文标题原样", sanitize_dirname("Attention Is All You Need"),
      "Attention Is All You Need")
check("非法字符转空格并折叠", sanitize_dirname('Deep Learning: A/B <good> "q" | y ? *'),
      "Deep Learning A B good q y")
check("控制符剥离", sanitize_dirname("Title\x00\x1f End"), "Title End")
check("尾随点/空格剥离", sanitize_dirname("Title...  "), "Title")
check("超长截断", len(sanitize_dirname("Word " * 40)) <= MAX_TITLE_LEN, True)
check("CJK 保留", sanitize_dirname("基于 深度学习的 NLP（综述）"), "基于 深度学习的 NLP（综述）")
check("保留设备名避让", sanitize_dirname("CON"), "CON_")
check("全非法回退空串", sanitize_dirname('<>:|?*'), "")

print("== 精确非法字符映射 ==")
check("冒号/斜杠等→空格折叠", sanitize_dirname("A: B/C \\ D|E"), "A B C D E")
check("截断后去尾点空格", sanitize_dirname(("X" * 79) + " ..."), "X" * 79)

print("== extract_doc_title（真实缓存） ==")
cases = {
    "output/_cache/a639448e61be3ab2/middle_json.json": "Attention Is All You Need",
    "output/_cache/274e841542934760/middle_json.json": None,  # 仅打印核实
}
for rel, want in cases.items():
    p = Path(rel)
    if not p.exists():
        print(f"  SKIP  {rel}（缓存不存在）")
        continue
    mj = json.loads(p.read_text(encoding="utf-8"))
    t = extract_doc_title(mj)
    if want is None:
        print(f"  INFO  {p.parent.name} → {t!r}")
        check("提取非空", bool(t), True)
    else:
        check(p.parent.name, t, want)

check("无标题块回退 None", extract_doc_title({"pages": [{"blocks": [{"type": "text", "content": []}]}]}), None)

print("== resolve_out_dir 撞名路由 ==")
H1, H2 = "aaaaaaaa11111111", "bbbbbbbb22222222"
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    check("空闲 → 标题目录", resolve_out_dir(root, "T1", "f.pdf", H1), root / "T1")
    (root / "T1").mkdir()
    (root / "T1" / ".paper_hash").write_text(H1)
    check("同篇 → 复用", resolve_out_dir(root, "T1", "f.pdf", H1), root / "T1")
    check("异篇撞标题 → 哈希后缀", resolve_out_dir(root, "T1", "g.pdf", H2),
          root / f"T1_{H2[:6]}")
    (root / "T2").mkdir()  # 有名无标记的手工目录
    check("无标记目录 → 避让", resolve_out_dir(root, "T2", "f.pdf", H1),
          root / f"T2_{H1[:6]}")
    check("标题缺失 → 回退文件名", resolve_out_dir(root, None, "my_paper", H1),
          root / "my_paper")

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
