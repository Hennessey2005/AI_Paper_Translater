# -*- coding: utf-8 -*-
"""M4 选型对比：通用 LLM(指令约束) vs 专用翻译模型(Hunyuan-MT-7B)。

测试维度：
    T1 术语密度段（摘要）：流畅性、术语自然度
    T2 占位符段：⟦F-xxx⟧/⟦FIG-x⟧/⟦CITEx⟧ 是否原样保留（S4 保护机制的硬性要求）
    T3 术语表遵从：强制 glossary 译名（wind rejection→风噪抑制 等）是否被采用
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openai import OpenAI

from paper_translate.config import load_config

_cfg = load_config()["api"]
API_KEY = _cfg["api_key"]
BASE = _cfg["base_url"]
MODELS = {
    "DeepSeek-V4.1-Flash(通用)": ("deepseek-ai/DeepSeek-V4.1-Flash", "general"),
    "Hunyuan-MT-7B(专用)": ("tencent/Hunyuan-MT-7B", "mt"),
}

GLOSSARY = "wind rejection → 风噪抑制\nwind extraction → 风噪提取\nmask → 掩模\nspeech enhancement → 语音增强"

T1 = ("Wind noise significantly degrades the quality of outdoor audio recordings, yet remains "
      "difficult to suppress in real-time on resource-constrained devices. In this work, we propose "
      "a low-complexity single-channel deep neural network that leverages the spectral "
      "characteristics of wind noise. The proposed model, with only 249K parameters and roughly "
      "73 MHz of computational power, is suitable for embedded and mobile audio applications.")

T2 = ("Consider a recording scenario where a single microphone captures an acoustic scene "
      "comprising arbitrary sound sources and wind noise. The signal model is expressed as, "
      "\u27e6F-001-01\u27e7 where the desired signal may consist of speech components and non-speech "
      "components, as formulated in \u27e6F-002-02\u27e7. The MUSHRA listening results are "
      "illustrated in \u27e6FIG-004\u27e7 \u27e6CITE-27\u27e7.")

T3 = ("Although the WNR task resembles speech enhancement, it differs in its objective: the target "
      "signal consists of all sound sources, excluding the wind noise component. We investigate two "
      "paradigms: the wind rejection approach, where the network directly estimates the desired "
      "signal, and the wind extraction approach, where the network estimates a mask for the wind "
      "noise itself. Wind noise is generally concentrated in low-frequency regions with negligible "
      "presence in frequencies above 4 kHz.")

CASES = {"T1术语段": T1, "T2占位符段": T2, "T3术语表段": T3}
PLACEHOLDER_RE = None
import re
PLACEHOLDER_RE = re.compile(r"\u27e6[^\u27e7]+\u27e7")


def prompts(style: str, text: str, with_glossary: bool):
    g = f"\n术语表（必须严格采用以下译名）：\n{GLOSSARY}\n" if with_glossary else ""
    if style == "general":
        sys_p = ("你是专业的学术翻译引擎。将英文论文段落翻译为中文。规则："
                 "1) 忠实原文，学术用语规范；2) 术语表译名强制采用；"
                 "3) 形如 ⟦XXX⟧ 的占位符原样保留，不得翻译、改写或删除；"
                 "4) 引用编号[12]与数字单位不变；5) 只输出译文，不要任何解释或前言。")
        return [{"role": "system", "content": sys_p + g},
                {"role": "user", "content": text}]
    # Hunyuan-MT 官方推荐模板风格：单一指令，不带角色扮演
    user_p = ("把下面的文本翻译成中文，不要额外解释。" + g + "\n\n" + text)
    return [{"role": "user", "content": user_p}]


def run(cli, model, text, style, with_glossary):
    t0 = time.perf_counter()
    r = cli.chat.completions.create(
        model=model, messages=prompts(style, text, with_glossary),
        max_tokens=2048, temperature=0.2,
        extra_body={"enable_thinking": False},
    )
    dt = time.perf_counter() - t0
    out = (r.choices[0].message.content or "").strip()
    return {"text": out, "s": round(dt, 1),
            "tok_in": r.usage.prompt_tokens, "tok_out": r.usage.completion_tokens}


def main():
    cli = OpenAI(api_key=API_KEY, base_url=BASE, timeout=120)
    report = {}
    for case, text in CASES.items():
        n_ph = len(PLACEHOLDER_RE.findall(text))
        with_gloss = case == "T3术语表段"
        print(f"\n{'='*70}\n### {case}  (占位符数={n_ph if n_ph else '—'})")
        for label, (model, style) in MODELS.items():
            try:
                r = run(cli, model, text, style, with_gloss)
                ph_out = len(PLACEHOLDER_RE.findall(r["text"]))
                gloss_hits = sum(r["text"].count(t) for t in ("风噪抑制", "风噪提取")) if with_gloss else None
                print(f"\n--- {label}  [{r['s']}s, {r['tok_in']}+{r['tok_out']}tok]")
                print(r["text"])
                print(f">>> 占位符保留 {ph_out}/{n_ph}" if n_ph else "",
                      f">>> 术语命中(抑制/提取) {gloss_hits}/4+" if gloss_hits is not None else "")
                report.setdefault(case, {})[label] = {**r, "ph": f"{ph_out}/{n_ph}"}
            except Exception as e:
                import traceback
                print(f"\n--- {label}  ERROR: {str(e)[:150]}")
                traceback.print_exc()
                report.setdefault(case, {})[label] = {"error": str(e)[:150]}
    Path("log").mkdir(exist_ok=True)
    Path("log/m4_bakeoff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写入 log/m4_bakeoff.json")


if __name__ == "__main__":
    main()
