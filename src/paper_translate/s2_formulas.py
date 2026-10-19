# -*- coding: utf-8 -*-
"""S2 公式剥离：从 MinerU middle_json 提取公式 → 注册表 + LaTeX 归一化 + 语法回验 + 行内乱码扫描。

产出：
    formulas.json  公式注册表（供 S4 占位符与知识库溯源）
    formulas.md    人类可读清单
    formulas.tex   可编译的公式汇总
    garble_report.json  行内乱码检测报告（供 API 修复路由）
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------- 归一化

_TAG_RE = re.compile(r"\\tag\{[^}]*\}")
_LABEL_RE = re.compile(r"\\label\{[^}]*\}")
_ENV_WRAP_RE = re.compile(r"\\(begin|end)\{(split|aligned|array|[rlcp]\*?)\}")
_SPACE_CMDS_RE = re.compile(r"\\(quad|qquad|,|;|!|:)")
_FUNCS_RE = re.compile(r"\\(operatorname|mathsf|textrm|text|mbox|mathrm)\{")


def normalize_latex(s: str, drop_tag: bool = True) -> str:
    """LaTeX 归一化：去 tag/label/环境包装/空白命令，统一函数命令。用于比较与校验。"""
    s = _TAG_RE.sub("", s) if drop_tag else s
    s = _LABEL_RE.sub("", s)
    s = _ENV_WRAP_RE.sub(" ", s)
    s = s.replace("&", " ").replace("\\\\", " ")
    s = _SPACE_CMDS_RE.sub(" ", s)
    s = _FUNCS_RE.sub(r"\\mathrm{", s)
    # {\bf x} → \mathbf{x} 风格统一（尽力）
    s = re.sub(r"\{\s*\\bf\s+([A-Za-z])\s*\}", r"\\mathbf{\1}", s)
    # \mathrm{ s i g n } → \mathrm{sign}：函数名字母被空格拆开会渲染出间隙
    s = re.sub(r"(\\(?:operatorname|mathsf|textrm|text|mbox|mathrm)\s*\{)([^{}]*)(\})",
               lambda m: m.group(1) + m.group(2).replace(" ", "") + m.group(3), s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------- 语义等价归一（仅用于对照评分，不改变存储的 latex）

_EQUIV_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\\Re\b"), r"\\mathfrak{R}"),
    (re.compile(r"\\Im\b"), r"\\mathfrak{I}"),
    (re.compile(r"\\widebar\b"), r"\\overline"),
    # \cos 等标准函数 → \mathrm{name}，与 MinerU 的 \mathrm{cos} 对齐
    (re.compile(r"\\(cos|sin|tan|arctan|log|exp|max|min|det|dim|rank|sign|stack|GRU)\b"),
     r"\\mathrm{\1}"),
    (re.compile(r"\\mathrm\s*\{\s*([A-Za-z]+)\s*\}"), r"\\mathrm{\1}"),
]


def canonical_for_compare(s: str) -> str:
    """在 normalize_latex 基础上再做语义等价折叠：等价命令变体、空组、冗余括号。
    目的：让评分反映"识别错误"而非"写法差异"。"""
    s = normalize_latex(s)
    for pat, rep in _EQUIV_SUBS:
        s = pat.sub(rep, s)
    s = re.sub(r"\{\s*\}\s*", "", s)          # 空组 {}（aligned 对齐残留）
    s = re.sub(r"\{ (\\mathbf [^{}]*|\\overline [^{}]*) \}", r"\1", s)  # 冗余包裹组
    s = s.replace("~", " ")                    # LaTeX 不可断行空格，无语义
    # 分组括号不承载语义（两侧同受影响），比较前全部剥掉：
    s = re.sub(r"[{}]", "", s)
    # 去空白 → 用于比较
    return s.replace(" ", "")


# ---------------------------------------------------------------- 语法回验

# 严格校验失败后的降级清理（latex2mathml 不支持的命令）
_LENIENT_CLEANUPS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\\underbrace\s*\{([^{}]*)\}\s*_\s*\{([^{}]*)\}"), r"\1"),
    (re.compile(r"\\overbrace\s*\{([^{}]*)\}\s*\^\s*\{([^{}]*)\}"), r"\1"),
    (re.compile(r"\\(triangleq|doteq|lesssim|gtrsim|approximage)"), r"="),
    (re.compile(r"\\jmath"), r"j"),
    (re.compile(r"\\widebar"), r"\bar"),
    (re.compile(r"\\(?=[^\sA-Za-z])"), ""),  # 兜底：孤立反斜杠
]


class FormulaValidator:
    """基于 latex2mathml 的语法回验（MinerU 自带依赖，无需额外安装）。"""

    def __init__(self) -> None:
        from latex2mathml.converter import convert  # noqa: F401

        self._convert = convert

    def check(self, latex_norm: str) -> dict:
        """返回 {strict_ok, lenient_ok, error}。lenient 对不支持命令做降级后重试。"""
        r = {"strict_ok": False, "lenient_ok": False, "error": None}
        try:
            self._convert(latex_norm)
            r["strict_ok"] = True
            r["lenient_ok"] = True
            return r
        except Exception as e:  # latex2mathml 抛多种异常类型
            r["error"] = str(e)[:160]
        s = latex_norm
        for pat, rep in _LENIENT_CLEANUPS:
            s = pat.sub(rep, s)
        try:
            self._convert(s)
            r["lenient_ok"] = True
        except Exception as e:
            r["error"] = (r["error"] or "") + " | lenient: " + str(e)[:160]
        return r


# ---------------------------------------------------------------- 提取与注册表

TEXTUAL_TYPES = {"text", "paragraph_title", "aside_text", "page_footnote", "ref_text", "doc_title"}


@dataclass
class Formula:
    id: str
    page: int                # 1 起（人类习惯）
    page_idx: int            # 0 起（middle_json 原始）
    bbox: list[float]        # 归一化坐标 [x0,y0,x1,y1]
    latex: str               # MinerU 原始输出（含 \tag）
    latex_norm: str
    tag: str | None
    source: str = "equation_block"
    syntax: dict = field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    image_path: str = ""


def _content_to_text(content, limit: int = 100000) -> str:
    """middle_json 的 content 兼容两种形态：纯字符串（equation 等）与 span 列表（text 等）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for span in content:
            if isinstance(span, dict):
                parts.append(str(span.get("content", "")))
            else:
                parts.append(str(span))
        return " ".join(" ".join(parts).split())
    return str(content)


def _block_text(block: dict, limit: int = 200) -> str:
    return _content_to_text(block.get("content", []), limit=limit)[:limit]


def extract_formulas(middle_json: dict) -> list[Formula]:
    """遍历 pages/blocks，抽取 equation 块 → Formula 列表（附上下文与编号）。"""
    validator = FormulaValidator()
    formulas: list[Formula] = []
    for page in middle_json.get("pages", []):
        pidx = page.get("page_idx", 0)
        blocks = page.get("blocks", [])
        for i, b in enumerate(blocks):
            if b.get("type") != "equation":
                continue
            raw = _content_to_text(b.get("content", "")).strip()
            m = re.search(r"\\tag\{(\d+)\}", raw)
            tag = m.group(1) if m else None
            norm = normalize_latex(raw)
            seq = len(formulas) + 1
            ctx_b = _block_text(blocks[i - 1]) if i > 0 and blocks[i - 1].get("type") in TEXTUAL_TYPES else ""
            ctx_a = _block_text(blocks[i + 1]) if i + 1 < len(blocks) and blocks[i + 1].get("type") in TEXTUAL_TYPES else ""
            f = Formula(
                id=f"F-{pidx + 1:03d}-{seq:02d}",
                page=pidx + 1,
                page_idx=pidx,
                bbox=[round(v, 4) for v in b.get("bbox", [])],
                latex=raw.strip(),
                latex_norm=norm,
                tag=tag,
                syntax=validator.check(norm),
                context_before=ctx_b,
                context_after=ctx_a,
                image_path=b.get("image_path", ""),
            )
            formulas.append(f)
    return formulas


# ---------------------------------------------------------------- 行内乱码扫描

GARBLE_PATTERNS: dict[str, re.Pattern] = {
    # 数学字体缺 ToUnicode：x[n] → xrns（[ → r，] → s）。
    # 不设左边界以捕获复合粘连（signal + d[n] → signaldrns），用英文常见词黑名单防误报
    "math_bracket": re.compile(
        r"(?!(?:warns|turns|burns|barns|horns|corns|yarns|kerns|sterns|cairns|garns)\b)[a-z]rns\b"),
    # 集合花括号 → t...u：{32, 64, 96, 128} → t32, 64, 96, 128u
    "set_tu": re.compile(r"\bt[0-9][0-9,.\s]{1,40}u\b"),
    # 尖括号元组 → p...q：⟨B, T, 40, 5⟩ → pB, T, 40, 5q
    "tuple_pq": re.compile(r"\bp[A-Z][A-Za-z0-9,.\s]{1,40}q\b"),
    # 负号 → 尖音符：−20 → ´20 ；2−3 → 2 ´ 3
    "minus_acute": re.compile(r"´\s?\d|\d\s?´"),
}


def scan_inline_garble(middle_json: dict, max_examples: int = 5) -> dict:
    """扫描文本类块中的行内公式乱码，返回计数 + 样例 + 受影响块定位。"""
    counts: Counter = Counter()
    examples: dict[str, list[str]] = {k: [] for k in GARBLE_PATTERNS}
    affected_blocks: list[dict] = []
    for page in middle_json.get("pages", []):
        pidx = page.get("page_idx", 0)
        for b in page.get("blocks", []):
            if b.get("type") not in ("text", "paragraph_title"):
                continue
            text = _block_text(b, limit=100000)
            hit: dict[str, list[str]] = {}
            for name, pat in GARBLE_PATTERNS.items():
                for m in pat.finditer(text):
                    counts[name] += 1
                    if len(examples[name]) < max_examples:
                        s = max(0, m.start() - 30)
                        examples[name].append(text[s:m.end() + 30])
                    hit.setdefault(name, []).append(m.group(0))
            if hit:
                affected_blocks.append({
                    "page_idx": pidx,
                    "block_index": b.get("index"),
                    "bbox": b.get("bbox"),
                    "patterns": hit,
                    "snippet": text[:120],
                })
    return {
        "counts": dict(counts),
        "examples": examples,
        "affected_blocks": affected_blocks,
        "affected_block_total": len(affected_blocks),
    }


# ---------------------------------------------------------------- 输出

def emit(registry: list[Formula], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    data = [asdict(f) for f in registry]
    (out_dir / "formulas.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# 公式注册表", "",
             f"共 {len(registry)} 个展示公式。`strict` = latex2mathml 严格通过；`lenient` = 降级清理后通过。", ""]
    for f in registry:
        st = "strict" if f.syntax["strict_ok"] else ("lenient" if f.syntax["lenient_ok"] else "FAIL")
        tag_txt = f"式({f.tag})" if f.tag else "(无编号)"
        lines += [
            f"## {f.id}（{tag_txt}，第 {f.page} 页，{st}）", "",
            f"- LaTeX: `{f.latex}`",
            f"- 渲染图: {f.image_path}" if f.image_path else "- 渲染图: (无)",
            f"- 上文: {f.context_before[:80]}…",
            "", f"$${f.latex}$$", "",
        ]
    (out_dir / "formulas.md").write_text("\n".join(lines), encoding="utf-8")

    tex = ["\\documentclass{article}", "\\usepackage{amsmath,amssymb,bm}",
           "\\begin{document}"]
    for f in registry:
        tex += ["\\begin{equation}", _TAG_RE.sub("", f.latex).strip(), "\\end{equation}"]
    tex.append("\\end{document}")
    (out_dir / "formulas.tex").write_text("\n".join(tex), encoding="utf-8")
