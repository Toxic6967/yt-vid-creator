from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from ..config import MEDIA_OUTPUT_DIR, settings
from ..db import update_media_job
from .media_director import enhance_image_prompt, enhance_video_prompt


class ComfyUIError(RuntimeError):
    pass


def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "base_url": settings.comfyui_base_url,
        "image_ready": False,
        "video_ready": False,
        "video_workflow": settings.comfyui_video_workflow,
        "checkpoints": [],
        "video_models": {
            "diffusion": "wan2.1_t2v_1.3B_fp16.safetensors",
            "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "vae": "wan_2.1_vae.safetensors",
        },
        "missing_video_models": [],
    }
    try:
        with httpx.Client(timeout=4) as client:
            response = client.get(f"{settings.comfyui_base_url}/system_stats")
            response.raise_for_status()
            result["ok"] = True
            try:
                info = client.get(
                    f"{settings.comfyui_base_url}/object_info/CheckpointLoaderSimple"
                )
                if info.is_success:
                    payload = info.json()
                    node = payload.get("CheckpointLoaderSimple", payload)
                    required = ((node.get("input") or {}).get("required") or {})
                    spec = required.get("ckpt_name")
                    choices = []
                    if isinstance(spec, list) and spec:
                        if isinstance(spec[0], list):
                            choices = spec[0]
                        elif all(isinstance(x, str) for x in spec):
                            choices = spec
                    result["checkpoints"] = choices[:40]
                    result["image_ready"] = bool(choices)
            except Exception:
                pass

            workflow_exists = Path(settings.comfyui_video_workflow).exists()
            if workflow_exists:
                try:
                    missing = []
                    model_checks = (
                        ("UNETLoader", "unet_name", result["video_models"]["diffusion"]),
                        ("CLIPLoader", "clip_name", result["video_models"]["text_encoder"]),
                        ("VAELoader", "vae_name", result["video_models"]["vae"]),
                    )
                    for node_name, field_name, expected in model_checks:
                        resp = client.get(f"{settings.comfyui_base_url}/object_info/{node_name}")
                        resp.raise_for_status()
                        payload = resp.json()
                        node = payload.get(node_name, payload)
                        required = ((node.get("input") or {}).get("required") or {})
                        spec = required.get(field_name)
                        choices = []
                        if isinstance(spec, list) and spec:
                            if isinstance(spec[0], list):
                                choices = spec[0]
                            elif all(isinstance(x, str) for x in spec):
                                choices = spec
                        if expected not in choices:
                            missing.append(expected)
                    result["missing_video_models"] = missing
                    result["video_ready"] = not missing
                except Exception as exc:
                    result["video_check_error"] = str(exc)
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _checkpoint_name() -> str:
    state = health()
    if not state.get("ok"):
        raise ComfyUIError(
            f"ComfyUI is not running at {settings.comfyui_base_url}. "
            "Start ComfyUI first."
        )
    available = state.get("checkpoints") or []
    configured = settings.comfyui_image_checkpoint.strip()
    if configured:
        if available and configured not in available:
            raise ComfyUIError(
                f"Configured checkpoint '{configured}' was not found in ComfyUI."
            )
        return configured
    if not available:
        raise ComfyUIError(
            "ComfyUI is running but no image checkpoint is installed. "
            "Install an image checkpoint in ComfyUI/models/checkpoints."
        )
    return available[0]


def _image_size(aspect: str) -> tuple[int, int]:
    # Conservative sizes for an 8 GB GPU. The final Shorts renderer can upscale/crop.
    return {
        "9:16": (576, 1024),
        "16:9": (1024, 576),
        "1:1": (768, 768),
    }[aspect]


def _standard_image_workflow(
    prompt: str,
    negative_prompt: str,
    aspect: str,
    steps: int,
    cfg: float,
    seed: int,
) -> tuple[dict[str, Any], str]:
    ckpt = _checkpoint_name()
    width, height = _image_size(aspect)
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ShortsStudio/ai_image",
                "images": ["8", 0],
            },
        },
    }
    return workflow, ckpt


def _replace_placeholders(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _replace_placeholders(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_placeholders(v, replacements) for v in value]
    if isinstance(value, str):
        if value in replacements:
            return replacements[value]
        out = value
        for key, replacement in replacements.items():
            out = out.replace(key, str(replacement))
        return out
    return value


def _video_workflow(
    prompt: str,
    negative_prompt: str,
    aspect: str,
    seconds: int,
    motion_strength: float,
    seed: int,
) -> dict[str, Any]:
    path = Path(settings.comfyui_video_workflow)
    if not path.exists():
        raise ComfyUIError(
            "No local AI-video workflow is installed yet. "
            f"Expected an API-format ComfyUI workflow at: {path}"
        )
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ComfyUIError(f"Could not read video workflow: {exc}") from exc

    width, height = ((480, 832) if aspect == "9:16" else (832, 480))
    # Keep 1.3B generations practical on an 8 GB GPU.
    # 33-81 frames at 16 fps gives roughly 2-5 seconds of real motion.
    frames = max(33, min(81, int(seconds * 16) + 1))
    return _replace_placeholders(
        workflow,
        {
            "__PROMPT__": prompt,
            "__NEGATIVE__": negative_prompt,
            "__SEED__": seed,
            "__WIDTH__": width,
            "__HEIGHT__": height,
            "__FRAMES__": frames,
            "__SECONDS__": seconds,
            "__MOTION_STRENGTH__": motion_strength,
        },
    )


def _queue_workflow(workflow: dict[str, Any]) -> str:
    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{settings.comfyui_base_url}/prompt", json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise ComfyUIError(f"ComfyUI rejected the generation workflow: {exc}") from exc
    prompt_id = body.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError(f"ComfyUI returned no prompt_id: {body}")
    return str(prompt_id)


def _history(prompt_id: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=15) as client:
        response = client.get(f"{settings.comfyui_base_url}/history/{prompt_id}")
        response.raise_for_status()
        payload = response.json()
    return payload.get(prompt_id) if isinstance(payload, dict) else None


def _artifact_refs(history: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    outputs = history.get("outputs") or {}
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("videos", "gifs", "images", "audio"):
            value = node_output.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and item.get("filename"):
                    refs.append(
                        {
                            "filename": item["filename"],
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        }
                    )
    return refs


def _wait_for_artifact(prompt_id: str, timeout_seconds: int) -> dict[str, str]:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        try:
            history = _history(prompt_id)
        except Exception:
            history = None
        if history:
            status = history.get("status") or {}
            if status.get("status_str") == "error":
                raise ComfyUIError(f"ComfyUI generation failed: {status}")
            refs = _artifact_refs(history)
            if refs:
                return refs[-1]
        time.sleep(1.5)
    raise ComfyUIError("Timed out waiting for ComfyUI to finish generation.")


def _download_artifact(ref: dict[str, str], destination: Path) -> Path:
    params = {
        "filename": ref["filename"],
        "subfolder": ref.get("subfolder", ""),
        "type": ref.get("type", "output"),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=90) as client:
        response = client.get(f"{settings.comfyui_base_url}/view", params=params)
        response.raise_for_status()
        destination.write_bytes(response.content)
    return destination


def generate_ai_image(
    prompt: str,
    negative_prompt: str,
    aspect: str,
    steps: int,
    cfg: float,
    job_id: str,
    seed: int | None = None,
) -> dict[str, Any]:
    seed = int(seed) if seed is not None else random.randint(0, 2_147_483_647)
    workflow, checkpoint = _standard_image_workflow(
        prompt, negative_prompt, aspect, steps, cfg, seed
    )
    prompt_id = _queue_workflow(workflow)
    ref = _wait_for_artifact(prompt_id, timeout_seconds=900)
    suffix = Path(ref["filename"]).suffix or ".png"
    output = MEDIA_OUTPUT_DIR / f"{job_id}{suffix}"
    _download_artifact(ref, output)
    return {
        "path": str(output),
        "prompt_id": prompt_id,
        "seed": seed,
        "checkpoint": checkpoint,
    }


def generate_ai_video(
    prompt: str,
    negative_prompt: str,
    aspect: str,
    seconds: int,
    motion_strength: float,
    job_id: str,
    seed: int | None = None,
) -> dict[str, Any]:
    state = health()
    if not state.get("ok"):
        raise ComfyUIError("ComfyUI is not running.")
    if not state.get("video_ready"):
        missing = ", ".join(state.get("missing_video_models") or [])
        raise ComfyUIError(
            "Local AI video is not ready."
            + (f" Missing Wan model files: {missing}" if missing else "")
        )
    seed = int(seed) if seed is not None else random.randint(0, 2_147_483_647)
    workflow = _video_workflow(prompt, negative_prompt, aspect, seconds, motion_strength, seed)
    prompt_id = _queue_workflow(workflow)
    ref = _wait_for_artifact(prompt_id, timeout_seconds=3600)
    suffix = Path(ref["filename"]).suffix or ".mp4"
    output = MEDIA_OUTPUT_DIR / f"{job_id}{suffix}"
    _download_artifact(ref, output)
    return {"path": str(output), "prompt_id": prompt_id, "seed": seed}


def run_image_job(job_id: str, request: dict[str, Any]) -> None:
    try:
        update_media_job(job_id, status="running", progress=10, error=None)
        request = dict(request)
        request.pop("variations", None)
        style = request.pop("style", "roblox_bright")
        purpose = request.pop("purpose", "scene_visual")
        enhance = bool(request.pop("enhance_prompt", True))
        if enhance:
            directed = enhance_image_prompt(request["prompt"], style=style, purpose=purpose)
            request["prompt"] = directed["prompt"]
            generated_negative = directed["negative_prompt"]
            request["negative_prompt"] = ", ".join(
                x for x in (request.get("negative_prompt", "").strip(), generated_negative) if x
            )
        elif not request.get("negative_prompt"):
            request["negative_prompt"] = "text, logo, watermark, blurry, low quality, clutter"
        update_media_job(job_id, progress=25)
        result = generate_ai_image(job_id=job_id, **request)
        update_media_job(
            job_id,
            status="ready",
            progress=100,
            output_path=result["path"],
            error=None,
        )
    except Exception as exc:
        update_media_job(job_id, status="failed", progress=100, error=str(exc))


def run_video_job(job_id: str, request: dict[str, Any]) -> None:
    try:
        update_media_job(job_id, status="running", progress=10, error=None)
        request = dict(request)
        request.pop("variations", None)
        style = request.pop("style", "roblox_bright")
        camera = request.pop("camera", "auto")
        purpose = request.pop("purpose", "b_roll")
        enhance = bool(request.pop("enhance_prompt", True))
        if enhance:
            directed = enhance_video_prompt(
                request["prompt"],
                style=style,
                camera=camera,
                purpose=purpose,
                seconds=int(request["seconds"]),
            )
            request["prompt"] = directed["prompt"]
            generated_negative = directed["negative_prompt"]
            request["negative_prompt"] = ", ".join(
                x for x in (request.get("negative_prompt", "").strip(), generated_negative) if x
            )
        elif not request.get("negative_prompt"):
            request["negative_prompt"] = "text, logo, watermark, flicker, morphing, blur"
        update_media_job(job_id, progress=25)
        result = generate_ai_video(job_id=job_id, **request)
        update_media_job(
            job_id,
            status="ready",
            progress=100,
            output_path=result["path"],
            error=None,
        )
    except Exception as exc:
        update_media_job(job_id, status="failed", progress=100, error=str(exc))
