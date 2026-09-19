from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import settings


class OllamaError(RuntimeError):
    pass


def health() -> dict[str, Any]:
    try:
        with httpx.Client(timeout=2.5) as client:
            response = client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            payload = response.json()
        names = [m.get("name", "") for m in payload.get("models", [])]
        return {
            "ok": True,
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_model,
            "model_installed": any(
                name == settings.ollama_model or name.startswith(settings.ollama_model + ":")
                for name in names
            ),
            "installed_models": names[:12],
        }
    except Exception as exc:
        return {
            "ok": False,
            "base_url": settings.ollama_base_url,
            "model": settings.ollama_model,
            "model_installed": False,
            "error": str(exc),
        }


def chat_json(system: str, user: str, *, temperature: float = 0.35) -> dict[str, Any]:
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature, "num_ctx": 8192},
    }
    try:
        with httpx.Client(timeout=180) as client:
            response = client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
    except Exception as exc:
        raise OllamaError(
            f"Could not use Ollama at {settings.ollama_base_url}. "
            f"Make sure Ollama is running and '{settings.ollama_model}' is installed. {exc}"
        ) from exc

    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise OllamaError(f"Ollama returned invalid JSON: {content[:500]}") from exc
