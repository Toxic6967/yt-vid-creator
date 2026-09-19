from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    channel_name: str = Field(default="My Shorts Channel", min_length=1, max_length=80)
    niche: str = Field(min_length=2, max_length=160)
    topic: str | None = Field(default=None, max_length=220)
    voice: str = Field(default="auto-youthful-male", max_length=80)
    target_seconds: int = Field(default=32, ge=20, le=45)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RegenerateRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=220)


class ChannelProfileRequest(BaseModel):
    channel_name: str = Field(min_length=1, max_length=80)
    niche: str = Field(min_length=2, max_length=160)
    tone: str = Field(default="Fast, exciting Roblox gaming documentary", max_length=120)
    audience: str = Field(default="Kids / young Roblox players (roughly 8-14); energetic, clear, exciting, never babyish", min_length=3, max_length=180)
    voice: str = Field(default="auto-youthful-male", max_length=80)
    target_seconds: int = Field(default=32, ge=20, le=45)
    trend_weight: int = Field(default=70, ge=0, le=100)
    evergreen_weight: int = Field(default=20, ge=0, le=100)
    experiment_weight: int = Field(default=10, ge=0, le=100)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=500)
    headline: str = Field(default="", max_length=90)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")


class AIImageRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=1200)
    negative_prompt: str = Field(default="blurry, low quality, watermark, text artifacts", max_length=800)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")
    steps: int = Field(default=24, ge=8, le=60)


class AIVideoRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=1600)
    negative_prompt: str = Field(default="blurry, low quality, distorted motion, watermark", max_length=800)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9)$")
    seconds: int = Field(default=5, ge=3, le=10)
