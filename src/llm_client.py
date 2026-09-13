"""OpenRouter / OpenAI-compatible vision client."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _client() -> OpenAI:
    # Prefer OpenRouter (available in this environment), then OpenAI.
    openrouter = os.environ.get("OPENROUTER_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openrouter:
        return OpenAI(
            api_key=openrouter,
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://github.com/bookable-payable"),
                "X-Title": "Bookable Payable",
            },
        )
    if openai_key:
        return OpenAI(api_key=openai_key)
    raise RuntimeError(
        "No API key found. Set OPENROUTER_API_KEY or OPENAI_API_KEY before running."
    )


def default_model() -> str:
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return os.environ.get("BOOKABLE_MODEL", "openai/gpt-4o-mini")
    return os.environ.get("BOOKABLE_MODEL", "gpt-4o-mini")


def chat_vision_json(
    system: str,
    user_text: str,
    image_data_urls: list[str],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 4,
) -> dict[str, Any]:
    """Send text + images; expect a JSON object response."""
    client = _client()
    model = model or default_model()
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            return _parse_json(raw)
        except Exception as e:  # noqa: BLE001 — retry API flakes
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Vision call failed after {max_retries} retries: {last_err}")


def chat_json(
    system: str,
    user_text: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    client = _client()
    model = model or default_model()
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return _parse_json(resp.choices[0].message.content or "{}")


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {"value": data}
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        raise
