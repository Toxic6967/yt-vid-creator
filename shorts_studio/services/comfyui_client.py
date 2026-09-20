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


def _extract_choices(spec: Any) -> list[str]:
    if not isinstance(spec, list) or not spec:
        return []
    first = spec[0]
    if isinstance(first, list):
        return [str(x) for x in first]
    if all(isinstance(x, str) for x in spec):
        return [str(x) for x in spec]
    return []


def _basename(value: str) -> str:
    return str(value).replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _match_model_choice(choices: list[str], expected: str) -> str | None:
    for choice in choices:
        if choice.casefold() == expected.casefold():
            return choice
    expected_base = _basename(expected)
    for choice in choices:
        if _basename(choice) == expected_base:
            return choice
    return None




def _pick_image_checkpoint(choices: list[str], configured: str = "") -> str | None:
    configured = (configured or "").strip()
    if configured:
        matched = _match_model_choice(choices, configured)
        return matched or configured

    preferred_names = (
        "sd_xl_base_1.0.safetensors",
        "juggernaut",
        "dreamshaper",
        "sdxl",
    )
    for preferred in preferred_names:
        for choice in choices:
            if preferred in choice.lower():
                return choice

    candidates = [
        choice for choice in choices
        if all(marker not in choice.lower() for marker in ("ltx", "wan", "video"))
    ]
    return candidates[0] if candidates else None

def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "base_url": settings.comfyui_base_url,
        "image_ready": False,
        "video_ready": False,
        "video_workflow": settings.comfyui_video_workflow,
        "checkpoints": [],
        "image_checkpoint": None,
        "video_models": {
            "diffusion": "wan2.1_t2v_1.3B_fp16.safetensors",
            "text_encoder": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "vae": "wan_2.1_vae.safetensors",
        },
        "missing_video_models": [],
        "video_models_resolved": {},
        "video_model_choices": {},
        "story_image_ready": False,
        "story_image_workflow": settings.comfyui_story_image_workflow,
        "story_image_models": {
            "diffusion": "flux-2-klein-4b-fp8.safetensors",
            "text_encoder": "qwen_3_4b.safetensors",
            "vae": "flux2-vae.safetensors",
        },
        "story_image_models_resolved": {},
        "missing_story_image_models": [],
        "story_video_ready": False,
        "story_video_workflow": settings.comfyui_story_video_workflow,
        "story_video_models": {
            "checkpoint": "ltxv-2b-0.9.8-distilled-fp8.safetensors",
            "text_encoder": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        },
        "story_video_models_resolved": {},
        "missing_story_video_models": [],
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
                    choices = _extract_choices(spec)
                    result["checkpoints"] = choices[:80]
                    image_checkpoint = _pick_image_checkpoint(
                        choices,
                        settings.comfyui_image_checkpoint,
                    )
                    result["image_checkpoint"] = image_checkpoint
                    result["image_ready"] = bool(image_checkpoint)
            except Exception:
                pass

            workflow_exists = Path(settings.comfyui_video_workflow).exists()
            if workflow_exists:
                try:
                    missing = []
                    resolved = {}
                    model_choices = {}
                    model_checks = (
                        ("diffusion", "UNETLoader", "unet_name", result["video_models"]["diffusion"]),
                        ("text_encoder", "CLIPLoader", "clip_name", result["video_models"]["text_encoder"]),
                        ("vae", "VAELoader", "vae_name", result["video_models"]["vae"]),
                    )
                    for key, node_name, field_name, expected in model_checks:
                        resp = client.get(f"{settings.comfyui_base_url}/object_info/{node_name}")
                        resp.raise_for_status()
                        payload = resp.json()
                        node = payload.get(node_name, payload)
                        required = ((node.get("input") or {}).get("required") or {})
                        choices = _extract_choices(required.get(field_name))
                        model_choices[key] = choices[:80]
                        matched = _match_model_choice(choices, expected)
                        if matched:
                            resolved[key] = matched
                        else:
                            missing.append(expected)

                    result["video_model_choices"] = model_choices
                    result["video_models_resolved"] = resolved
                    result["missing_video_models"] = missing
                    result["video_ready"] = not missing
                except Exception as exc:
                    result["video_check_error"] = str(exc)
            story_image_workflow_exists = Path(settings.comfyui_story_image_workflow).exists()
            if story_image_workflow_exists:
                try:
                    missing_story_image = []
                    resolved_story_image = {}
                    checks = (
                        ("diffusion", "UNETLoader", "unet_name", result["story_image_models"]["diffusion"]),
                        ("text_encoder", "CLIPLoader", "clip_name", result["story_image_models"]["text_encoder"]),
                        ("vae", "VAELoader", "vae_name", result["story_image_models"]["vae"]),
                    )
                    for key, node_name, field_name, expected in checks:
                        resp = client.get(f"{settings.comfyui_base_url}/object_info/{node_name}")
                        resp.raise_for_status()
                        payload = resp.json()
                        node = payload.get(node_name, payload)
                        required = ((node.get("input") or {}).get("required") or {})
                        choices = _extract_choices(required.get(field_name))
                        matched = _match_model_choice(choices, expected)
                        if matched:
                            resolved_story_image[key] = matched
                        else:
                            missing_story_image.append(expected)

                    for node_name in (
                        "EmptyFlux2LatentImage",
                        "Flux2Scheduler",
                        "ReferenceLatent",
                        "SamplerCustomAdvanced",
                        "CFGGuider",
                        "RandomNoise",
                        "KSamplerSelect",
                        "ImageScaleToTotalPixels",
                        "GetImageSize",
                    ):
                        node_resp = client.get(f"{settings.comfyui_base_url}/object_info/{node_name}")
                        if not node_resp.is_success:
                            missing_story_image.append(f"ComfyUI node: {node_name}")

                    result["story_image_models_resolved"] = resolved_story_image
                    result["missing_story_image_models"] = missing_story_image
                    result["story_image_ready"] = not missing_story_image
                except Exception as exc:
                    result["story_image_check_error"] = str(exc)

            story_workflow_exists = Path(settings.comfyui_story_video_workflow).exists()
            if story_workflow_exists:
                try:
                    story_missing = []
                    story_resolved = {}

                    checkpoint_choices = result.get("checkpoints") or []
                    expected_checkpoint = result["story_video_models"]["checkpoint"]
                    matched_checkpoint = _match_model_choice(checkpoint_choices, expected_checkpoint)
                    if matched_checkpoint:
                        story_resolved["checkpoint"] = matched_checkpoint
                    else:
                        story_missing.append(expected_checkpoint)

                    clip_resp = client.get(f"{settings.comfyui_base_url}/object_info/CLIPLoader")
                    clip_resp.raise_for_status()
                    clip_payload = clip_resp.json()
                    clip_node = clip_payload.get("CLIPLoader", clip_payload)
                    clip_required = ((clip_node.get("input") or {}).get("required") or {})
                    clip_choices = _extract_choices(clip_required.get("clip_name"))
                    expected_text = result["story_video_models"]["text_encoder"]
                    matched_text = _match_model_choice(clip_choices, expected_text)
                    if matched_text:
                        story_resolved["text_encoder"] = matched_text
                    else:
                        story_missing.append(expected_text)

                    required_story_nodes = (
                        "LTXVImgToVideo",
                        "LTXVConditioning",
                        "LTXVScheduler",
                        "SamplerCustom",
                        "KSamplerSelect",
                        "CreateVideo",
                        "SaveVideo",
                    )
                    for node_name in required_story_nodes:
                        node_resp = client.get(f"{settings.comfyui_base_url}/object_info/{node_name}")
                        if not node_resp.is_success:
                            story_missing.append(f"ComfyUI node: {node_name}")

                    result["story_video_models_resolved"] = story_resolved
                    result["missing_story_video_models"] = story_missing
                    result["story_video_ready"] = not story_missing
                except Exception as exc:
                    result["story_video_check_error"] = str(exc)
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

    picked = _pick_image_checkpoint(available)
    if not picked:
        raise ComfyUIError(
            "ComfyUI has checkpoints installed, but none look like a normal image checkpoint. "
            "Install or restore SDXL in models/checkpoints."
        )
    return picked


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

    state = health()
    if not state.get("video_ready"):
        missing = ", ".join(state.get("missing_video_models") or [])
        raise ComfyUIError(
            "Local AI video is not ready."
            + (f" Missing Wan model files: {missing}" if missing else "")
        )

    resolved = state.get("video_models_resolved") or {}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}
        if class_type == "UNETLoader" and resolved.get("diffusion"):
            inputs["unet_name"] = resolved["diffusion"]
        elif class_type == "CLIPLoader" and resolved.get("text_encoder"):
            inputs["clip_name"] = resolved["text_encoder"]
        elif class_type == "VAELoader" and resolved.get("vae"):
            inputs["vae_name"] = resolved["vae"]

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




def _upload_input_image(image_path: Path) -> str:
    if not image_path.exists():
        raise ComfyUIError(f"Story keyframe image is missing: {image_path}")
    suffix = image_path.suffix.lower() or ".png"
    filename = f"shorts_studio_{uuid.uuid4().hex[:10]}{suffix}"
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".png": "image/png",
    }.get(suffix, "application/octet-stream")
    try:
        with image_path.open("rb") as fh, httpx.Client(timeout=90) as client:
            response = client.post(
                f"{settings.comfyui_base_url}/upload/image",
                files={"image": (filename, fh, mime)},
                data={"type": "input", "overwrite": "true"},
            )
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        raise ComfyUIError(f"Could not upload story keyframe to ComfyUI: {exc}") from exc
    return str(body.get("name") or filename)


def _story_i2v_workflow(
    prompt: str,
    negative_prompt: str,
    image_path: Path,
    seconds: int,
    seed: int,
) -> dict[str, Any]:
    path = Path(settings.comfyui_story_video_workflow)
    if not path.exists():
        raise ComfyUIError(f"Story image-to-video workflow missing: {path}")

    state = health()
    if not state.get("story_video_ready"):
        missing = ", ".join(state.get("missing_story_video_models") or [])
        raise ComfyUIError(
            "Cinematic story image-to-video is not ready."
            + (f" Missing: {missing}" if missing else "")
        )

    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ComfyUIError(f"Could not read story video workflow: {exc}") from exc

    uploaded_name = _upload_input_image(image_path)
    resolved = state.get("story_video_models_resolved") or {}

    frames = max(49, min(97, (round(max(2.0, min(4.0, seconds)) * 24) // 8) * 8 + 1))
    # Slightly taller native generation gives more useful vertical detail while
    # staying within the practical 8 GB LTX 2B FP8 range.
    width, height = 512, 896

    return _replace_placeholders(
        workflow,
        {
            "__LTX_CHECKPOINT__": resolved.get(
                "checkpoint", state["story_video_models"]["checkpoint"]
            ),
            "__LTX_TEXT_ENCODER__": resolved.get(
                "text_encoder", state["story_video_models"]["text_encoder"]
            ),
            "__INPUT_IMAGE__": uploaded_name,
            "__PROMPT__": prompt,
            "__NEGATIVE__": negative_prompt,
            "__SEED__": seed,
            "__WIDTH__": width,
            "__HEIGHT__": height,
            "__FRAMES__": frames,
            "__I2V_STRENGTH__": 0.94,
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



def generate_ai_image_from_reference(
    prompt: str,
    negative_prompt: str,
    reference_path: str | Path,
    aspect: str,
    steps: int,
    cfg: float,
    denoise: float,
    job_id: str,
    seed: int | None = None,
) -> dict[str, Any]:
    """SDXL img2img continuity pass for sequential story keyframes."""
    seed = int(seed) if seed is not None else random.randint(0, 2_147_483_647)
    ckpt = _checkpoint_name()
    width, height = _image_size(aspect)
    uploaded_name = _upload_input_image(Path(reference_path))

    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": float(denoise),
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["12", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        },
        "11": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["10", 0],
                "upscale_method": "lanczos",
                "width": width,
                "height": height,
                "crop": "center",
            },
        },
        "12": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["11", 0], "vae": ["4", 2]},
        },
        "13": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "14": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ShortsStudio/story_keyframe",
                "images": ["13", 0],
            },
        },
    }

    prompt_id = _queue_workflow(workflow)
    ref = _wait_for_artifact(prompt_id, timeout_seconds=900)
    suffix = Path(ref["filename"]).suffix or ".png"
    output = MEDIA_OUTPUT_DIR / f"{job_id}{suffix}"
    _download_artifact(ref, output)
    return {
        "path": str(output),
        "prompt_id": prompt_id,
        "seed": seed,
        "checkpoint": ckpt,
        "backend": "sdxl_img2img_continuity",
    }


def generate_story_keyframe(
    prompt: str,
    reference_path: str | Path,
    job_id: str,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a character-consistent Story frame with FLUX.2 Klein reference editing."""
    state = health()
    if not state.get("story_image_ready"):
        missing = ", ".join(state.get("missing_story_image_models") or [])
        raise ComfyUIError(
            "High-quality Story image engine is not ready."
            + (f" Missing: {missing}" if missing else "")
        )

    path = Path(settings.comfyui_story_image_workflow)
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ComfyUIError(f"Could not read Story image workflow: {exc}") from exc

    seed = int(seed) if seed is not None else random.randint(0, 2_147_483_647)
    uploaded = _upload_input_image(Path(reference_path))
    resolved = state.get("story_image_models_resolved") or {}

    workflow = _replace_placeholders(
        workflow,
        {
            "__FLUX2_MODEL__": resolved.get(
                "diffusion", state["story_image_models"]["diffusion"]
            ),
            "__FLUX2_TEXT_ENCODER__": resolved.get(
                "text_encoder", state["story_image_models"]["text_encoder"]
            ),
            "__FLUX2_VAE__": resolved.get(
                "vae", state["story_image_models"]["vae"]
            ),
            "__REFERENCE_IMAGE__": uploaded,
            "__PROMPT__": prompt,
            "__SEED__": seed,
        },
    )

    prompt_id = _queue_workflow(workflow)
    ref = _wait_for_artifact(prompt_id, timeout_seconds=1200)
    suffix = Path(ref["filename"]).suffix or ".png"
    output = MEDIA_OUTPUT_DIR / f"{job_id}{suffix}"
    _download_artifact(ref, output)
    return {
        "path": str(output),
        "prompt_id": prompt_id,
        "seed": seed,
        "backend": "flux2_klein_reference",
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



def generate_story_video_from_image(
    prompt: str,
    negative_prompt: str,
    image_path: str | Path,
    seconds: int,
    job_id: str,
    seed: int | None = None,
) -> dict[str, Any]:
    seed = int(seed) if seed is not None else random.randint(0, 2_147_483_647)
    workflow = _story_i2v_workflow(
        prompt,
        negative_prompt,
        Path(image_path),
        seconds,
        seed,
    )
    prompt_id = _queue_workflow(workflow)
    ref = _wait_for_artifact(prompt_id, timeout_seconds=3600)
    suffix = Path(ref["filename"]).suffix or ".mp4"
    output = MEDIA_OUTPUT_DIR / f"{job_id}{suffix}"
    _download_artifact(ref, output)
    return {
        "path": str(output),
        "prompt_id": prompt_id,
        "seed": seed,
        "backend": "ltx_i2v",
    }

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
