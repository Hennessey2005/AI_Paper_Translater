# -*- coding: utf-8 -*-
"""M4 验证：S4 翻译 + S5 组装端到端。

用法:
    .venv\\Scripts\\python.exe scripts\\m4_translate_test.py

产出: output/paper_test/{译文.zh.md, 译文.bilingual.md, segments.json}
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from paper_translate.config import load_config
from paper_translate.clients.llm import LLMClient, log_event
from paper_translate.s3_figures import collect_visuals
from paper_translate.s4_translate import build_units, translate_units
from paper_translate.s5_assemble import assemble

CACHE = ROOT / "output" / "_cache" / "274e841542934760"
FIG_JSON = ROOT / "output" / "figures_test" / "figures.json"
OUT = ROOT / "output" / "paper_test"
LOG = ROOT / "log" / "m4_run.jsonl"


def main() -> int:
    cfg = load_config()
    api = cfg["api"]
    mj = json.loads((CACHE / "middle_json.json").read_text(encoding="utf-8"))
    figures = json.loads(FIG_JSON.read_text(encoding="utf-8"))
    fig_by_id = {f["id"]: f for f in figures}

    # 1) 构建单元（visual 对齐走 s3 的 collect_visuals，保证 id 一致）
    units = build_units(mj, figures)
    kinds = {}
    for u in units:
        kinds[u.kind] = kinds.get(u.kind, 0) + 1
    print(f"[1] 翻译单元: {len(units)} 个  分类={kinds}")
    # 校验 visual 对齐完整性
    n_visual_blocks = sum(1 for p in mj["pages"] for b in p["blocks"]
                          if b.get("type") in ("image", "chart", "table"))
    n_visual_units = sum(1 for u in units if u.kind == "visual"
                         and u.meta.get("figure_id"))
    print(f"    visual 对齐: {n_visual_units}/{n_visual_blocks}")

    # 2) 翻译（title + text）
    client = LLMClient(api["base_url"], api["api_key"], api["llm_model"] or api["vlm_model"])
    t0 = time.perf_counter()
    usage = translate_units(
        units, client,
        gloss_path=ROOT / "config" / "glossary.yaml",
        doc_title="Low-Complexity Neural Wind Noise Reduction for Audio Recordings（音频录制的低复杂度神经风噪抑制）",
        cache_path=CACHE / "translations.json",
        log_path=LOG,
    )
    dt = time.perf_counter() - t0
    print(f"[2] 翻译完成: API调用 {usage['calls']}（缓存命中 {usage['cache_hit']}）, "
          f"{dt:.0f}s, tokens {usage['in']}+{usage['out']}, 人工复核标记 {usage['flags']}")

    # 3) 组装 + 自检
    title_unit = next((u for u in units if u.kind == "title"), None)
    report = assemble(units, fig_by_id, CACHE, OUT,
                      title_zh=title_unit.zh if title_unit else None)
    print(f"[3] 自检: {report['checks']}")
    if report["manual_review"]:
        print(f"    需人工复核: {report['manual_review']}")

    log_event(LOG, {"stage": "s4", "level": "info", "msg": "done",
                    "units": len(units), "kinds": kinds,
                    "calls": usage["calls"], "cache_hit": usage["cache_hit"],
                    "tokens_in": usage["in"], "tokens_out": usage["out"],
                    "flags": usage["flags"], "checks": report["checks"],
                    "duration_s": round(dt, 1)})

    ok = (all(report["checks"].values()) and n_visual_units == n_visual_blocks == 5)
    print(f"[4] 产物已写入 {OUT}")
    print("\n===== M4 验收:", "PASS" if ok else "FAIL", "=====")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
