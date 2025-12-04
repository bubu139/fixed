import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateVideoRequest(BaseModel):
    node_id: str
    prompt: str
    provider: str = Field(default="mock", description="Video provider identifier")
    voice_id: Optional[str] = Field(
        default=None, description="Voice identifier for narration, if supported"
    )
    audio_url: Optional[str] = None


class VideoSegmentRead(BaseModel):
    id: uuid.UUID
    segment_index: int
    start_second: int
    end_second: int
    status: str
    provider_job_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class NodeVideoRead(BaseModel):
    id: uuid.UUID
    node_id: str
    prompt: str
    provider: str
    voice_id: Optional[str] = None
    audio_url: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    segments: List[VideoSegmentRead] = Field(default_factory=list)
    player_config: "PlayerConfig" | None = None

    class Config:
        orm_mode = True


class ProgressEvent(BaseModel):
    current_second: int


class ProviderVoice(BaseModel):
    id: str
    name: str
    locale: Optional[str] = None


class ProviderOption(BaseModel):
    name: str
    description: str
    supports_voice: bool = False
    voices: List[ProviderVoice] = Field(default_factory=list)


class PlayerConfig(BaseModel):
    skip_interval_seconds: int = 5
    playback_speeds: List[float] = Field(default_factory=lambda: [0.75, 1.0, 1.25, 1.5, 2.0])
    volume_step: float = 0.1


NodeVideoRead.update_forward_refs()
