# -*- coding: utf-8 -*-
"""配置加载。"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PATHS = [
    Path("config/config.yaml"),
    Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml",
]


def load_config(path: str | Path | None = None) -> dict:
    for p in ([Path(path)] if path else DEFAULT_PATHS):
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raise FileNotFoundError(f"配置文件未找到: {path or DEFAULT_PATHS}")
