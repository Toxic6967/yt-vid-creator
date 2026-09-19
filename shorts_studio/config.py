from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SHORTS_STUDIO_DATA", ROOT_DIR / "data"))
OUTPUT_DIR = DATA_DIR / "outputs"
ASSET_DIR = DATA_DIR / "assets"
MUSIC_DIR = ASSET_DIR / "music"
SFX_DIR = ASSET_DIR / "sfx"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "shorts_studio.db"

for path in (DATA_DIR, OUTPUT_DIR, ASSET_DIR, MUSIC_DIR, SFX_DIR, CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Shorts Studio V1"
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("SHORTS_STUDIO_MODEL", "qwen3:8b")
    default_voice: str = os.getenv("SHORTS_STUDIO_VOICE", "en-AU-WilliamNeural")
    default_target_seconds: int = int(os.getenv("SHORTS_STUDIO_TARGET_SECONDS", "32"))
    max_source_chars: int = int(os.getenv("SHORTS_STUDIO_MAX_SOURCE_CHARS", "4200"))
    user_agent: str = os.getenv(
        "SHORTS_STUDIO_USER_AGENT",
        "ShortsStudioV1/1.0 (local personal creator tool; contact: local-user)",
    )


settings = Settings()
