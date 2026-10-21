# -*- coding: utf-8 -*-
"""输出目录命名：从解析结果提取论文真实标题 → 文件系统安全目录名。

规则（v2.1 P0-A）：
    - 标题取 middle_json 第一个 doc_title 块（S1 产物，零额外成本），无则回退 PDF 文件名
    - 目录用源语言标题定名；中文标题改名放 P2（避免破坏 segments.json 与断点续跑路径）
    - 同名区分：目录内写 .paper_hash 标记（PDF 内容 sha1）——同篇复用目录续跑，
      异篇撞标题则追加 _<hash6> 后缀
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .s2_formulas import _content_to_text

# Windows 目录名非法字符 + ASCII 控制符；CJK 与常规标点保留
_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = ({"CON", "PRN", "AUX", "NUL"}
                 | {f"COM{i}" for i in range(1, 10)}
                 | {f"LPT{i}" for i in range(1, 10)})
MAX_TITLE_LEN = 80      # 截断防 MAX_PATH 溢出（根目录 + 标题 + formulas/… 子层）


def extract_doc_title(middle_json: dict) -> str | None:
    """返回第一个非空 doc_title 块文本；不存在返回 None（调用方负责回退）。"""
    for page in middle_json.get("pages", []):
        for b in page.get("blocks", []):
            if b.get("type") == "doc_title":
                txt = _content_to_text(b.get("content", "")).strip()
                if txt:
                    return txt
    return None


def sanitize_dirname(name: str) -> str:
    """任意标题 → 安全目录名。非法字符转空格、折叠空白、截断、去尾点/空格。

    结果不可用时返回空串，由调用方回退。
    """
    s = unicodedata.normalize("NFC", name)
    s = _FORBIDDEN_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s[:MAX_TITLE_LEN].rstrip(" .")          # Windows 不允许尾随点/空格
    if not s:
        return ""
    if s.split(".")[0].upper() in _WIN_RESERVED:  # 防止整名撞保留设备名
        s += "_"
    return s


def resolve_out_dir(root: Path, title: str | None, fallback_stem: str,
                    pdf_hash: str) -> Path:
    """按 标题+内容哈希 确定最终输出目录（不落盘，仅选址）。

    优先级：标题目录 → 文件名目录（标题缺失时）；被异篇占用则追加 _<hash6>、_<hash6>_2…
    """
    base = (sanitize_dirname(title) if title else "") \
        or sanitize_dirname(fallback_stem) or "paper"
    candidates = [base, f"{base}_{pdf_hash[:6]}"] + [f"{base}_{pdf_hash[:6]}_{i}"
                                                    for i in range(2, 100)]
    for name in candidates:
        cand = root / name
        marker = cand / ".paper_hash"
        if not cand.exists():
            return cand
        if marker.exists():
            try:
                if marker.read_text(encoding="utf-8").strip() == pdf_hash:
                    return cand                    # 同篇论文 → 复用目录（断点续跑）
            except OSError:
                pass
        # 目录被其他论文占用（或有名无标记的手工目录）→ 看下一个候选
    raise RuntimeError(f"无法为 {base!r} 分配空闲输出目录")


def write_hash_marker(out_dir: Path, pdf_hash: str) -> None:
    """建目录后写入身份标记，供后续运行识别同篇论文。"""
    (out_dir / ".paper_hash").write_text(pdf_hash + "\n", encoding="utf-8")
