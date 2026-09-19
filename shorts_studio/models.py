from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    channel_name: str = Field(default="My Shorts Channel", min_length=1, max_length=80)
    niche: str = Field(min_length=2, max_length=160)
    topic: str | None = Field(default=None, max_length=220)
    voice: str = Field(default="en-AU-WilliamNeural", max_length=80)
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
    tone: str = Field(default="Fast gaming documentary", max_length=120)
    voice: str = Field(default="en-AU-WilliamNeural", max_length=80)
    target_seconds: int = Field(default=32, ge=20, le=45)
    trend_weight: int = Field(default=70, ge=0, le=100)
    evergreen_weight: int = Field(default=20, ge=0, le=100)
    experiment_weight: int = Field(default=10, ge=0, le=100)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=500)
    headline: str = Field(default="", max_length=90)
    aspect: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1)$")
