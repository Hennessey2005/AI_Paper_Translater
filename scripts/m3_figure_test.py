# -*- coding: utf-8 -*-
"""M3 验证：图表理解端到端（配对 → VLM 描述 → figures.md/json）。

用法:
    .venv\\Scripts\\python.exe scripts\\m3_figure_test.py

验收点:
    1. 5 个视觉块全部配对图注（2 image + 2 chart + 1 table）
    2. VLM 返回 JSON 解析成功率 100%
    3. 每个图表有中文描述；chart/table 提取出数据表
    4. 成本日志落盘（tokens 统计）
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from paper_translate.config import load_config
from paper_translate.clients.vlm import VLMClient, log_event
from paper_translate.s3_figures import collect_visuals, analyze, emit_figures

CACHE = ROOT / "output" / "_cache" / "274e841542934760"
OUT = ROOT / "output" / "figures_test"
LOG = ROOT / "log" / "m3_run.jsonl"


def main() -> int:
    cfg = load_config()
    api = cfg["api"]
    mj = json.loads((CACHE / "middle_json.json").read_text(encoding="utf-8"))

    # 1) 收集与配对
    visuals = collect_visuals(mj, CACHE)
    valid = [v for v in visuals if not v.skipped]
    print(f"[1] 视觉块: {len(visuals)} 个（有效 {len(valid)}，跳过 {len(visuals)-len(valid)}）")
    for v in visuals:
        tag = "SKIP" if v.skipped else "OK"
        print(f"    {v.id} [{v.kind}] {tag} fig_no={v.fig_no} cap={v.caption[:50]!r}")

    # 2) VLM 分析
    client = VLMClient(api["base_url"], api["api_key"], api["vlm_model"])
    t0 = time.perf_counter()
    usage = analyze(visuals, CACHE, client, LOG)
    dt = time.perf_counter() - t0
    print(f"[2] VLM 分析完成: {usage['calls']} 次调用, {dt:.0f}s, "
          f"tokens {usage['in']}+{usage['out']}, 失败 {usage['fail']}")

    # 3) 结果检查
    ok_parse = sum(1 for v in valid if not v.error)
    has_desc = sum(1 for v in valid if len(v.description) > 50)
    has_data = sum(1 for v in valid if v.kind in ("chart", "table") and v.data_table)
    low_conf = [v.id for v in valid if v.confidence < 0.7]
    print(f"[3] JSON解析 {ok_parse}/{len(valid)}; 有效描述 {has_desc}/{len(valid)}; "
          f"chart/table 数据表 {has_data}; 低置信 {low_conf or '无'}")

    # 4) 输出
    emit_figures(visuals, OUT, CACHE)
    log_event(LOG, {"stage": "s3", "level": "info", "msg": "done",
                    "valid": len(valid), "parse_ok": ok_parse,
                    "has_desc": has_desc, "has_data": has_data,
                    "tokens_in": usage["in"], "tokens_out": usage["out"],
                    "duration_s": round(dt, 1)})
    print(f"[4] 产物已写入 {OUT}")

    ok = (len(valid) == 5 and ok_parse == 5 and has_desc == 5 and has_data >= 2)
    print("\n===== M3 验收:", "PASS" if ok else "FAIL", "=====")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
