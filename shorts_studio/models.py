from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    channel_name: str = Field(default="My Shorts Channel", min_length=1, max_length=80)
    niche: str = Field(min_length=2, max_length=120)
    topic: str | None = Field(default=None, max_length=180)
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
    topic: str | None = Field(default=None, max_length=180)
