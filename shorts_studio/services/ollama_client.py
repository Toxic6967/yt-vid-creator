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


def _ollama_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except Exception:
        pass
    text = (response.text or "").strip()
    return text[:1200] or f"HTTP {response.status_code}"


def unload_model() -> None:
    """Free Qwen before ComfyUI/Wan needs the GPU."""
    try:
        with httpx.Client(timeout=20) as client:
            client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": 0,
                },
            )
    except Exception:
        pass


def chat_json(system: str, user: str, *, temperature: float = 0.35) -> dict[str, Any]:
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "think": False,
        "keep_alive": "3m",
        "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": 6144,
            "num_predict": 2200,
        },
    }

    timeout = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=30.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{settings.ollama_base_url}/api/chat", json=payload)

            if response.status_code >= 500:
                first_error = _ollama_error_text(response)

                # 8 GB GPUs can run out of VRAM when ComfyUI and Ollama coexist.
                # Retry this one AI step in conservative CPU-safe mode instead
                # of failing the entire Short.
                retry_payload = dict(payload)
                retry_payload["keep_alive"] = 0
                retry_payload["options"] = {
                    "temperature": temperature,
                    "num_ctx": 4096,
                    "num_predict": 1600,
                    "num_gpu": 0,
                }
                retry = client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=retry_payload,
                )
                if retry.is_success:
                    response = retry
                else:
                    second_error = _ollama_error_text(retry)
                    raise OllamaError(
                        "Ollama returned HTTP 500. "
                        f"GPU attempt: {first_error}. "
                        f"Low-memory retry: {second_error}"
                    )

            response.raise_for_status()
            body = response.json()
            content = body["message"]["content"]
    except httpx.ReadTimeout as exc:
        raise OllamaError(
            f"Ollama is running, but '{settings.ollama_model}' took longer than 10 minutes "
            "to finish this AI step."
        ) from exc
    except OllamaError:
        raise
    except httpx.HTTPStatusError as exc:
        raise OllamaError(
            f"Ollama HTTP {exc.response.status_code}: {_ollama_error_text(exc.response)}"
        ) from exc
    except Exception as exc:
        raise OllamaError(
            f"Could not use Ollama at {settings.ollama_base_url}: {exc}"
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
