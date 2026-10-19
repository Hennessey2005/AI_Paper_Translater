# -*- coding: utf-8 -*-
"""VLM / LLM 客户端（OpenAI 兼容协议：硅基流动、bigmodel 等）。

- 图片走 base64 data URL
- Qwen3 系列默认关闭 thinking（enable_thinking=False），避免长思考拖慢结构化抽取
- 指数退避重试；返回 usage 供成本统计
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from openai import OpenAI


def _data_url(image_path: Path) -> str:
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    suffix = image_path.suffix.lstrip(".").lower()
    if suffix == "jpg":
        suffix = "jpeg"
    return f"data:image/{suffix};base64,{b64}"


class VLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 120.0, max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries
        self._cli = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def chat_image(self, image_path: Path, system: str, user: str,
                   max_tokens: int = 2000) -> dict:
        """发送 单图+文本 请求。返回 {text, usage:{in,out}, duration_s, retries}。"""
        content = [
            {"type": "image_url", "image_url": {"url": _data_url(image_path)}},
            {"type": "text", "text": user},
        ]
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": content}]
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            t0 = time.perf_counter()
            try:
                r = self._cli.chat.completions.create(
                    model=self.model, messages=messages, max_tokens=max_tokens,
                    extra_body={"enable_thinking": False},
                )
                u = r.usage
                return {
                    "text": r.choices[0].message.content or "",
                    "usage": {"in": u.prompt_tokens, "out": u.completion_tokens},
                    "duration_s": round(time.perf_counter() - t0, 1),
                    "retries": attempt,
                }
            except Exception as e:  # 网络/限流 → 指数退避
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"VLM 调用失败（{self.max_retries} 次重试后）: {last_err}")


def parse_model_json(text: str) -> dict:
    """从模型回复解析 JSON；容忍 ```json 围栏与尾随说明（json_repair 为 MinerU 自带依赖）。"""
    import json_repair

    obj = json_repair.loads(text)
    if isinstance(obj, dict):
        return obj
    # 兜底：截取第一个 { 到最后一个 }
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        obj = json_repair.loads(text[i:j + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"模型输出无法解析为 JSON 对象: {text[:120]}…")


def log_event(log_path: Path, event: dict) -> None:
    event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
