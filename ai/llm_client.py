"""
ai/llm_client.py — Unified AI Client
======================================
Hỗ trợ nhiều AI provider: Gemini → Groq → OpenAI
Tự động fallback sang provider tiếp theo khi quota hết.

Để dùng thêm provider, thêm key vào .env:
  GROQ_API_KEY=gsk_...          # https://console.groq.com (free)
  OPENAI_API_KEY=sk-...         # https://platform.openai.com
"""

from __future__ import annotations
import os
import json
import time
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Token usage logger ───────────────────────────────────────────────────────
def _log_token(provider: str, model: str, prompt_tokens: int, completion_tokens: int):
    try:
        log_file = os.path.join(os.path.dirname(__file__), "..", "data", "token_usage.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        entry = {
            "timestamp": time.time(),
            "model": f"{provider}/{model}",
            "prompt_tokens": prompt_tokens,
            "candidate_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ── Simple response wrapper ──────────────────────────────────────────────────
class LLMResponse:
    def __init__(self, text: str, provider: str, model: str):
        self.text = text
        self.provider = provider
        self.model = model

    def __repr__(self):
        return f"<LLMResponse provider={self.provider} model={self.model} len={len(self.text)}>"


# ── Provider: Gemini ─────────────────────────────────────────────────────────
def _try_gemini(prompt: str) -> Optional[LLMResponse]:
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai as _genai
        client = _genai.Client(api_key=api_key)
        models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        for model in models:
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                text = response.text or ""
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    _log_token("gemini", model,
                               getattr(usage, "prompt_token_count", 0),
                               getattr(usage, "candidates_token_count", 0))
                print(f"[LLM] Gemini/{model} OK")
                return LLMResponse(text, "gemini", model)
            except Exception as e:
                err = str(e)
                if "RESOURCE_EXHAUSTED" in err or "429" in err:
                    print(f"[LLM] Gemini/{model} quota exceeded, trying next...")
                    continue
                raise
    except ImportError:
        print("[LLM] google-genai not installed, skipping Gemini")
    except Exception as e:
        print(f"[LLM] Gemini error: {e}")
    return None


# ── Provider: Groq ───────────────────────────────────────────────────────────
def _try_groq(prompt: str) -> Optional[LLMResponse]:
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        models = [
            "llama-3.3-70b-versatile",   # Free, excellent quality
            "llama-3.1-8b-instant",       # Free, fast
            "llama-3.2-3b-preview",       # Free, fast preview
        ]
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2048,
                )
                text = resp.choices[0].message.content or ""
                usage = resp.usage
                if usage:
                    _log_token("groq", model, usage.prompt_tokens, usage.completion_tokens)
                print(f"[LLM] Groq/{model} OK")
                return LLMResponse(text, "groq", model)
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() or "429" in err:
                    print(f"[LLM] Groq/{model} rate limit, trying next model...")
                    time.sleep(2)
                    continue
                raise
    except ImportError:
        print("[LLM] groq package not installed. Run: py -m pip install groq")
    except Exception as e:
        print(f"[LLM] Groq error: {e}")
    return None


# ── Provider: OpenAI ─────────────────────────────────────────────────────────
def _try_openai(prompt: str) -> Optional[LLMResponse]:
    load_dotenv(override=True)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        models = ["gpt-4o-mini", "gpt-3.5-turbo"]
        for model in models:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2048,
                )
                text = resp.choices[0].message.content or ""
                usage = resp.usage
                if usage:
                    _log_token("openai", model, usage.prompt_tokens, usage.completion_tokens)
                print(f"[LLM] OpenAI/{model} OK")
                return LLMResponse(text, "openai", model)
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() or "429" in err:
                    print(f"[LLM] OpenAI/{model} rate limit, trying next...")
                    continue
                raise
    except ImportError:
        print("[LLM] openai package not installed. Run: py -m pip install openai")
    except Exception as e:
        print(f"[LLM] OpenAI error: {e}")
    return None


# ── Public API ───────────────────────────────────────────────────────────────
_PROVIDER_ORDER = ["gemini", "groq", "openai"]
_PROVIDER_FNS = {
    "gemini": _try_gemini,
    "groq": _try_groq,
    "openai": _try_openai,
}

# Providers tạm thời bị disable trong session (quota hết)
_disabled: set = set()


def generate(prompt: str, prefer: Optional[str] = None) -> LLMResponse:
    """
    Gọi AI với fallback tự động qua các provider theo thứ tự ưu tiên.
    
    Args:
        prompt: Nội dung prompt
        prefer: Provider ưu tiên (None = dùng thứ tự mặc định)
    
    Returns:
        LLMResponse với .text, .provider, .model
    
    Raises:
        RuntimeError nếu tất cả provider đều thất bại
    """
    order = list(_PROVIDER_ORDER)
    if prefer and prefer in order:
        order.remove(prefer)
        order.insert(0, prefer)

    last_error = None
    for provider in order:
        if provider in _disabled:
            print(f"[LLM] {provider} disabled (quota), skipping")
            continue
        fn = _PROVIDER_FNS.get(provider)
        if not fn:
            continue
        try:
            result = fn(prompt)
            if result is not None:
                return result
        except Exception as e:
            last_error = e
            print(f"[LLM] {provider} failed: {e}")

    raise RuntimeError(
        f"All AI providers failed. Last error: {last_error}. "
        "Check API keys in .env (GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY)"
    )


def available_providers() -> list[str]:
    """Trả về danh sách provider có API key cấu hình."""
    load_dotenv(override=True)
    result = []
    if os.getenv("GEMINI_API_KEY"):
        result.append("gemini")
    if os.getenv("GROQ_API_KEY"):
        result.append("groq")
    if os.getenv("OPENAI_API_KEY"):
        result.append("openai")
    return result


def extract_json(text: str) -> str:
    """Tách JSON ra khỏi markdown code block nếu có."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
