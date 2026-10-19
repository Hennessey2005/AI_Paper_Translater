# -*- coding: utf-8 -*-
"""paper-translate 命令行入口。

用法:
    paper-translate paper.pdf                 # 全流程（解析+公式+图表理解+翻译）
    paper-translate paper.pdf --offline       # 仅本地阶段（解析+公式），不调 API
    paper-translate paper.pdf -o out/         # 指定输出目录
    paper-translate paper.pdf --cache-dir d/  # 复用已有解析缓存（跳过最贵的 S1）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .orchestrator import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="paper-translate",
        description="PDF 论文 → 深度理解包（中文译文 + LaTeX 公式注册表 + 图表内容描述）")
    p.add_argument("pdf", help="输入 PDF 路径")
    p.add_argument("-o", "--output", default=None, help="输出目录（默认 output/<pdf名>/）")
    p.add_argument("--cache-dir", default=None, help="解析缓存目录（复用可跳过 S1）")
    p.add_argument("--tier", default=None, help="MinerU 档位 basic|standard|flash（默认读配置）")
    p.add_argument("--offline", action="store_true", help="离线模式：跳过图表理解与翻译（不调 API）")
    p.add_argument("--config", default=None, help="配置文件路径（默认 config/config.yaml）")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    if args.tier:
        cfg["tier"] = args.tier

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"输入不存在: {pdf}")
        return 2
    out_dir = Path(args.output) if args.output else Path("output") / pdf.stem

    print(f"paper-translate: {pdf.name}  tier={cfg.get('tier')}  offline={args.offline}")
    report = run_pipeline(pdf, out_dir, cfg,
                          cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                          offline=args.offline)
    print(f"\n完成（{report['total_seconds']}s）")
    for k, v in report["outputs"].items():
        print(f"  {k}: {v}")
    ok = all(report["checks"].values())
    print("自检:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
