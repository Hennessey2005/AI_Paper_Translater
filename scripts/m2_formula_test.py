# -*- coding: utf-8 -*-
"""M2 验证：MinerU 公式抽取 vs LaTeX 源码真值 对照测试。

用法:
    .venv\\Scripts\\python.exe scripts\\m2_formula_test.py

验收点:
    1. 公式数量与论文一致（11 个展示公式）
    2. 与源码真值逐条对齐（按 \\tag 编号），归一化相似度 ≥0.85 判 PASS
    3. 语法回验（latex2mathml）通过率 100%（strict 或 lenient）
    4. 行内乱码扫描：检出数量与 M1 人工观察一致量级
"""
import io
import json
import re
import sys
import time
import difflib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from paper_translate.s2_formulas import (
    extract_formulas, scan_inline_garble, emit, canonical_for_compare,
)

CACHE = ROOT / "output" / "_cache" / "274e841542934760"   # M1 产物
TEX_DIR = ROOT / "refs" / "latex_src" / "sections"
OUT = ROOT / "output" / "formulas_test"
LOG = ROOT / "log" / "m2_run.jsonl"


def log(event: dict) -> None:
    event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------- 真值提取 ----------------

def extract_ground_truth() -> list[dict]:
    """按 sections/*.tex 顺序提取 equation 环境，编号 = 出现顺序（1 起）。"""
    out = []
    for tex in sorted(TEX_DIR.glob("*.tex")):
        lines = [l for l in tex.read_text(encoding="utf-8").splitlines()
                 if not l.lstrip().startswith("%")]          # 去注释行（含被注释的公式）
        body = "\n".join(lines)
        for m in re.finditer(r"\\begin\{equation\}(.*?)\\end\{equation\}", body, re.S):
            src = m.group(1)
            lab = re.search(r"\\label\{([^}]*)\}", src)
            out.append({
                "no": len(out) + 1,
                "label": lab.group(1) if lab else None,
                "latex_raw": src.strip(),
                "latex_norm": canonical_for_compare(src),
            })
    return out


# ---------------- 相似度 ----------------

def token_set(s: str) -> set[str]:
    return set(re.findall(r"\\[A-Za-z]+|[A-Za-z]|\d+|[^\sA-Za-z\\0-9]", s))


def compare(hyp_norm: str, ref_norm: str) -> dict:
    # 去掉全部空白再比较：MinerU 输出风格为 `\widetilde { X }`，源码为 `\widetilde{X}`，
    # 空白不携带语义，去除后 SequenceMatcher 才反映真实结构差异
    h, r = hyp_norm.replace(" ", ""), ref_norm.replace(" ", "")
    seq = difflib.SequenceMatcher(None, h, r).ratio()
    th, tr = token_set(hyp_norm), token_set(ref_norm)
    jac = len(th & tr) / len(th | tr) if (th | tr) else 1.0
    score = 0.6 * seq + 0.4 * jac
    verdict = "PASS" if score >= 0.85 else ("CLOSE" if score >= 0.70 else "REVIEW")
    return {"seq": round(seq, 3), "token_jaccard": round(jac, 3),
            "score": round(score, 3), "verdict": verdict}


def main() -> int:
    mj = json.loads((CACHE / "middle_json.json").read_text(encoding="utf-8"))

    # 1) 抽取
    t0 = time.perf_counter()
    registry = extract_formulas(mj)
    print(f"[1] 抽取展示公式: {len(registry)} 个 ({time.perf_counter()-t0:.2f}s)")

    # 2) 真值
    gt = extract_ground_truth()
    print(f"[2] 源码真值公式: {len(gt)} 个")

    # 3) 按 tag 对齐比较
    by_tag = {f.tag: f for f in registry if f.tag}
    results = []
    for g in gt:
        f = by_tag.get(str(g["no"]))
        if f is None:
            results.append({"no": g["no"], "label": g["label"], "verdict": "MISSING"})
            continue
        cmp_r = compare(canonical_for_compare(f.latex), g["latex_norm"])
        results.append({"no": g["no"], "label": g["label"], "id": f.id,
                        "syntax": f.syntax, **cmp_r})
    n_pass = sum(1 for r in results if r.get("verdict") == "PASS")
    n_close = sum(1 for r in results if r.get("verdict") == "CLOSE")
    n_rev = sum(1 for r in results if r.get("verdict") in ("REVIEW", "MISSING"))
    n_syntax = sum(1 for f in registry if f.syntax["strict_ok"] or f.syntax["lenient_ok"])

    print(f"[3] 对照结果: PASS={n_pass}  CLOSE={n_close}  REVIEW/MISSING={n_rev}")
    print(f"    语法回验: {n_syntax}/{len(registry)} 通过(strict 或 lenient)")
    for r in results:
        if "score" in r:
            print(f"    式({r['no']}) {r.get('id')}: score={r['score']} "
                  f"(seq={r['seq']}, jac={r['token_jaccard']}) {r['verdict']} "
                  f"label={r.get('label')}")
            if r["verdict"] != "PASS":
                f = by_tag[str(r["no"])]
                g = gt[r["no"] - 1]
                print(f"      hyp: {f.latex_norm[:220]}")
                print(f"      ref: {g['latex_norm'][:220]}")
        else:
            print(f"    式({r['no']}): {r['verdict']}")

    # 4) 行内乱码扫描
    garble = scan_inline_garble(mj)
    print(f"[4] 行内乱码扫描: 计数={garble['counts']}  受影响块={garble['affected_block_total']}")
    for name, exs in garble["examples"].items():
        for e in exs[:3]:
            print(f"    [{name}] …{e}…")

    # 5) 输出
    emit(registry, OUT)
    (OUT / "garble_report.json").write_text(
        json.dumps(garble, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "compare_report.json").write_text(
        json.dumps({"results": results,
                    "summary": {"pass": n_pass, "close": n_close,
                                "review": n_rev, "syntax_ok": n_syntax,
                                "total": len(registry)}},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[5] 产物已写入 {OUT}")

    log({"stage": "s2", "level": "info", "msg": "done",
         "formulas": len(registry), "gt": len(gt),
         "pass": n_pass, "close": n_close, "review": n_rev,
         "syntax_ok": n_syntax, "garble_counts": garble["counts"]})

    # 验收：公式数一致 + 语法全过 + 无 REVIEW
    ok = (len(registry) == len(gt) == 11) and n_syntax == len(registry) and n_rev == 0
    print("\n===== M2 验收:", "PASS" if ok else "FAIL", "=====")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
