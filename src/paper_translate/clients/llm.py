# -*- coding: utf-8 -*-
"""LLM 文本客户端（OpenAI 兼容）。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from openai import OpenAI

from .vlm import make_http_client


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 120.0, max_retries: int = 3,
                 temperature: float = 0.2, proxy: str | None = None):
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature
        self._cli = OpenAI(api_key=api_key, base_url=base_url,
                           http_client=make_http_client(proxy, timeout))

    def chat(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            t0 = time.perf_counter()
            try:
                r = self._cli.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    max_tokens=max_tokens, temperature=self.temperature,
                    extra_body={"enable_thinking": False},
                )
                u = r.usage
                return {"text": (r.choices[0].message.content or "").strip(),
                        "tok_in": u.prompt_tokens, "tok_out": u.completion_tokens,
                        "duration_s": round(time.perf_counter() - t0, 1),
                        "retries": attempt}
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM 调用失败（{self.max_retries} 次重试后）: {last_err}")


def log_event(log_path: Path, event: dict) -> None:
    Path(log_path).parent.mkdir(exist_ok=True)
    event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
