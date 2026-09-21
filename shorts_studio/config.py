from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STORAGE_MARKER = ROOT_DIR / ".shorts_studio_storage"


def _storage_root() -> Path | None:
    env = os.getenv("SHORTS_STUDIO_STORAGE_ROOT", "").strip()
    if env:
        return Path(env)
    try:
        if STORAGE_MARKER.exists():
            value = STORAGE_MARKER.read_text(encoding="utf-8").lstrip("\ufeff").strip()
            if value:
                return Path(value)
    except Exception:
        pass
    return None


STORAGE_ROOT = _storage_root()
DATA_DIR = Path(
    os.getenv(
        "SHORTS_STUDIO_DATA",
        str((STORAGE_ROOT / "data") if STORAGE_ROOT else (ROOT_DIR / "data")),
    )
)
OUTPUT_DIR = DATA_DIR / "outputs"
ASSET_DIR = DATA_DIR / "assets"
MUSIC_DIR = ASSET_DIR / "music"
SFX_DIR = ASSET_DIR / "sfx"
KOKORO_DIR = ASSET_DIR / "kokoro"
CACHE_DIR = DATA_DIR / "cache"
MEDIA_OUTPUT_DIR = OUTPUT_DIR / "media"
WORKFLOW_DIR = ROOT_DIR / "workflows"
DB_PATH = DATA_DIR / "shorts_studio.db"
VOICE_ROOT = (STORAGE_ROOT / "voice") if STORAGE_ROOT else (ASSET_DIR / "voice")
CHATTERBOX_DIR = VOICE_ROOT / "chatterbox"
CHATTERBOX_PYTHON = CHATTERBOX_DIR / ".venv" / "Scripts" / "python.exe"
ROBLOX_ASSET_DIR = ASSET_DIR / "roblox_official"
ROBLOX_R15_FBX = ROBLOX_ASSET_DIR / "BlockyCharacter.fbx"

for path in (DATA_DIR, OUTPUT_DIR, MEDIA_OUTPUT_DIR, ASSET_DIR, MUSIC_DIR, SFX_DIR, KOKORO_DIR, CACHE_DIR, WORKFLOW_DIR, ROBLOX_ASSET_DIR):
    path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Shorts Studio V5"
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("SHORTS_STUDIO_MODEL", "qwen3:8b")
    default_voice: str = os.getenv("SHORTS_STUDIO_VOICE", "auto-youthful-male")
    default_target_seconds: int = int(os.getenv("SHORTS_STUDIO_TARGET_SECONDS", "58"))
    comfyui_base_url: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    comfyui_image_checkpoint: str = os.getenv("COMFYUI_IMAGE_CHECKPOINT", "")
    comfyui_video_workflow: str = os.getenv("COMFYUI_VIDEO_WORKFLOW", str(WORKFLOW_DIR / "video_api.json"))
    comfyui_story_video_workflow: str = os.getenv(
        "COMFYUI_STORY_VIDEO_WORKFLOW",
        str(WORKFLOW_DIR / "ltx_i2v_api.json"),
    )
    comfyui_story_image_workflow: str = os.getenv(
        "COMFYUI_STORY_IMAGE_WORKFLOW",
        str(WORKFLOW_DIR / "flux2_klein_story_api.json"),
    )
    comfyui_story_dual_image_workflow: str = os.getenv(
        "COMFYUI_STORY_DUAL_IMAGE_WORKFLOW",
        str(WORKFLOW_DIR / "flux2_klein_story_dual_api.json"),
    )
    kokoro_model_path: str = os.getenv(
        "SHORTS_STUDIO_KOKORO_MODEL",
        str(KOKORO_DIR / "kokoro-v1.0.onnx"),
    )
    kokoro_voices_path: str = os.getenv(
        "SHORTS_STUDIO_KOKORO_VOICES",
        str(KOKORO_DIR / "voices-v1.0.bin"),
    )
    chatterbox_python: str = os.getenv(
        "SHORTS_STUDIO_CHATTERBOX_PYTHON",
        str(CHATTERBOX_PYTHON),
    )
    chatterbox_device: str = os.getenv(
        "SHORTS_STUDIO_CHATTERBOX_DEVICE",
        "cuda",
    )
    blender_executable: str = os.getenv(
        "SHORTS_STUDIO_BLENDER",
        "",
    )
    roblox_r15_fbx: str = os.getenv(
        "SHORTS_STUDIO_R15_FBX",
        str(ROBLOX_R15_FBX),
    )
    default_visual_mode: str = os.getenv(
        "SHORTS_STUDIO_VISUAL_MODE",
        "animated",
    )
    max_source_chars: int = int(os.getenv("SHORTS_STUDIO_MAX_SOURCE_CHARS", "2400"))
    user_agent: str = os.getenv(
        "SHORTS_STUDIO_USER_AGENT",
        "ShortsStudioV1/1.0 (local personal creator tool; contact: local-user)",
    )


settings = Settings()
