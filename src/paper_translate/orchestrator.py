# -*- coding: utf-8 -*-
"""全流程编排：S1 解析 → S2 公式 → S3 图表 → S4 翻译 → S5 组装。

断点复用：
    - cache_dir 下已有 middle_json.json → 跳过 S1（最贵的本地解析）
    - cache_dir 下已有 translations.json → S4 全部走缓存（0 API 调用）
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .clients.llm import LLMClient, log_event
from .clients.vlm import VLMClient
from .config import load_config
from .s2_formulas import extract_formulas, emit as emit_formulas
from .s3_figures import analyze as analyze_figures, collect_visuals, emit_figures
from .s4_translate import build_units, translate_units
from .s5_assemble import assemble


def _find_middle_json(cache_dir: Path) -> Path | None:
    direct = cache_dir / "middle_json.json"
    if direct.exists():
        return direct
    hits = list(cache_dir.glob("*middle*.json"))
    return hits[0] if hits else None


def run_pipeline(pdf: Path, out_dir: Path, cfg: dict,
                 cache_dir: Path | None = None, offline: bool = False,
                 log_dir: Path | None = None) -> dict:
    t_start = time.perf_counter()
    pdf = Path(pdf)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir is None:
        # 默认按 PDF 内容哈希隔离缓存：同一论文重跑自动复用，不同论文互不污染
        import hashlib
        h = hashlib.sha1(pdf.read_bytes()).hexdigest()[:16]
        cache_dir = Path("output") / "_cache" / h
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(log_dir) if log_dir else Path("log")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    api = cfg.get("api", {})

    report: dict = {"pdf": pdf.name, "cache_dir": str(cache_dir), "stages": {}}

    def mark(stage: str, **kw):
        report["stages"][stage] = kw
        print(f"  [{stage}] " + " ".join(f"{k}={v}" for k, v in kw.items()))

    # ---------- S1 解析（MinerU basic 档，CPU） ----------
    os.environ.setdefault("MINERU_MODEL_SOURCE", "modelscope")
    mj_path = _find_middle_json(cache_dir)
    if mj_path:
        print(f"  [s1] 复用缓存 {mj_path}")
        mark("s1", mode="cache", file=mj_path.name)
    else:
        from mineru.parser import parse
        from mineru.parser.writer import FileBasedDataWriter

        tier = cfg.get("tier", "basic")
        t0 = time.perf_counter()
        result = parse(str(pdf), tier=tier)
        result.save(FileBasedDataWriter(str(cache_dir)))
        mark("s1", mode="parse", tier=tier, seconds=round(time.perf_counter() - t0, 1))
        mj_path = _find_middle_json(cache_dir)
    assert mj_path, "middle_json 未产出"
    mj = json.loads(mj_path.read_text(encoding="utf-8"))
    assert mj.get("schema") == "docvortex.middle", "协议版本不兼容，请检查 MinerU 版本"

    # ---------- S2 公式剥离（本地） ----------
    registry = extract_formulas(mj)
    emit_formulas(registry, out_dir / "formulas")
    mark("s2", formulas=len(registry),
         syntax_ok=sum(1 for f in registry if f.syntax["strict_ok"] or f.syntax["lenient_ok"]))

    # ---------- S3 图表理解（API；offline 跳过） ----------
    visuals = collect_visuals(mj, cache_dir)
    if offline:
        emit_figures(visuals, out_dir / "figures", cache_dir)
        mark("s3", mode="offline", figures=sum(1 for v in visuals if not v.skipped))
    else:
        vlm = VLMClient(api["base_url"], api["api_key"], api["vlm_model"])
        usage = analyze_figures(visuals, cache_dir, vlm, log_path)
        emit_figures(visuals, out_dir / "figures", cache_dir)
        mark("s3", figures=sum(1 for v in visuals if not v.skipped),
             tokens=f"{usage['in']}+{usage['out']}", fail=usage["fail"])

    figures_dicts = [dict(id=v.id, kind=v.kind, page_idx=v.page_idx, fig_no=v.fig_no,
                          bbox=v.bbox, image_path=v.image_path, caption=v.caption,
                          caption_zh=v.caption_zh, description=v.description,
                          data_table=v.data_table, confidence=v.confidence,
                          skipped=v.skipped) for v in visuals]

    # ---------- S4 翻译（API；offline 跳过） ----------
    units = build_units(mj, figures_dicts)
    title_src = next((u.src for u in units if u.kind == "title"), pdf.stem)
    if offline:
        mark("s4", mode="offline")
    else:
        llm = LLMClient(api["base_url"], api["api_key"],
                        api.get("llm_model") or api["vlm_model"])
        usage = translate_units(units, llm,
                                gloss_path=Path("config/glossary.yaml"),
                                doc_title=title_src,
                                cache_path=cache_dir / "translations.json",
                                log_path=log_path)
        mark("s4", calls=usage["calls"], cache_hit=usage["cache_hit"],
             tokens=f"{usage['in']}+{usage['out']}", flags=usage["flags"])

    # ---------- S5 组装 ----------
    fig_by_id = {f["id"]: f for f in figures_dicts}
    title_unit = next((u for u in units if u.kind == "title"), None)
    check = assemble(units, fig_by_id, cache_dir, out_dir,
                     title_zh=title_unit.zh if title_unit else None)
    mark("s5", **{k: (v if isinstance(v, (int, str)) else "PASS" if v else "FAIL")
                  for k, v in check["checks"].items()},
         review=check["manual_review"] or "无")

    report["checks"] = check["checks"]
    report["outputs"] = {
        "译文": str(out_dir / "译文.zh.md"),
        "对照": str(out_dir / "译文.bilingual.md"),
        "公式": str(out_dir / "formulas"),
        "图表": str(out_dir / "figures"),
        "溯源": str(out_dir / "segments.json"),
    }
    report["total_seconds"] = round(time.perf_counter() - t_start, 1)
    log_event(log_path, {"stage": "run", "level": "info", "msg": "done",
                         "pdf": pdf.name, "total_seconds": report["total_seconds"],
                         "checks": report["checks"]})
    return report
