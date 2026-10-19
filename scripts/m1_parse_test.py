# -*- coding: utf-8 -*-
"""M1 验证脚本：MinerU basic 档解析测试论文，校验产物结构。

用法:
    .venv\\Scripts\\python.exe scripts\\m1_parse_test.py [pdf路径]

验收点:
    1. schema == docvortex.middle 且 schema_version 存在
    2. 产物齐全: markdown.md / middle_json.json / structured_content.json / images/
    3. 块类型统计（期望出现 text/image/table/chart/equation 类块）
    4. 公式数量、图表数量与人工核对（本论文应有 ~4图 1表 11式）
"""
import json
import hashlib
import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 国内模型源（首跑下载模型用；auto 会先探测 HF）
os.environ.setdefault("MINERU_MODEL_SOURCE", "modelscope")


def sha1_16(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "2507.01821v1.pdf"
    cache_dir = ROOT / "output" / "_cache" / sha1_16(pdf)
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_path = ROOT / "log" / "m1_run.jsonl"

    def log(event: dict) -> None:
        event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(json.dumps(event, ensure_ascii=False))

    log({"stage": "s1", "level": "info", "msg": "start", "pdf": pdf.name, "tier": "basic"})

    from mineru.parser import parse
    from mineru.parser.writer import FileBasedDataWriter

    t0 = time.perf_counter()
    result = parse(str(pdf), tier="basic")
    t_parse = time.perf_counter() - t0

    result.save(FileBasedDataWriter(str(cache_dir)))
    t_total = time.perf_counter() - t0

    # ---- 校验 middle_json ----
    mj_path = cache_dir / "middle_json.json"
    if not mj_path.exists():
        # save() 可能落为其他名字，兜底查找
        cands = list(cache_dir.glob("*middle*.json"))
        mj_path = cands[0] if cands else None
    assert mj_path is not None, "middle_json 未产出"
    mj = json.loads(mj_path.read_text(encoding="utf-8"))

    schema = mj.get("schema")
    ok_schema = schema == "docvortex.middle"
    ext = (mj.get("extensions") or {}).get("mineru") or {}
    pages = mj.get("pages", [])

    type_hist: dict = {}
    for p in pages:
        for b in p.get("blocks", []):
            type_hist[b.get("type", "?")] = type_hist.get(b.get("type", "?"), 0) + 1

    imgs = sorted([p.name for p in (cache_dir / "images").glob("*")]) if (cache_dir / "images").exists() else []

    # ---- 产物清单 ----
    files = sorted(p.name for p in cache_dir.iterdir() if p.is_file())

    report = {
        "stage": "s1",
        "level": "info",
        "msg": "done",
        "pdf": pdf.name,
        "schema": schema,
        "schema_ok": ok_schema,
        "schema_version": mj.get("schema_version"),
        "tier_reported": ext.get("tier"),
        "parse_mode": ext.get("parse_mode"),
        "pages": len(pages),
        "is_full_document": mj.get("is_full_document"),
        "block_types": type_hist,
        "images": imgs,
        "files": files,
        "cache_dir": str(cache_dir),
        "t_parse_s": round(t_parse, 1),
        "t_total_s": round(t_total, 1),
    }
    log(report)

    # ---- 验收判定 ----
    checks = {
        "schema==docvortex.middle": ok_schema,
        "产物含markdown": any("markdown" in f for f in files),
        "产物含structured_content": any("structured" in f for f in files),
        "images/非空": len(imgs) > 0,
        "块类型含text": "text" in type_hist,
    }
    print("\n===== 验收清单 =====")
    all_ok = True
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
        all_ok &= bool(v)
    print(f"总耗时: parse {t_parse:.1f}s / 全流程 {t_total:.1f}s")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
