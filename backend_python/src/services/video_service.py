import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import BackgroundTasks, HTTPException
from sqlmodel import Session, select

from src.db import SessionLocal
from src.schemas.video import CreateVideoRequest, PlayerConfig, ProviderOption, ProviderVoice
from src.video_models import NodeVideo, VideoSegment
from .video_providers.base import VideoProvider
from .video_providers.google_veo import GoogleVeoProvider
from .video_providers.mock import MockVideoProvider

SEGMENT_DURATION_SECONDS = 30
SEGMENT_TRIGGER_OFFSET_SECONDS = 20
DEFAULT_PROVIDER = "google-veo"

PROVIDERS: dict[str, dict] = {
    "mock": {
        "provider": MockVideoProvider(),
        "info": ProviderOption(
            name="mock",
            description="Mock provider for development; replace with Veo/Runway/Pika in production",
            supports_voice=True,
            voices=[
                ProviderVoice(id="vi_female_1", name="Giọng nữ miền Bắc", locale="vi-VN"),
                ProviderVoice(id="vi_male_1", name="Giọng nam miền Bắc", locale="vi-VN"),
            ],
        ),
    },
    "google-veo": {
        "provider": GoogleVeoProvider(),
        "info": ProviderOption(
            name="google-veo",
            description="Google Veo via google-genai for high-quality video synthesis",
            supports_voice=False,
            voices=[],
        ),
    },
}


def _resolve_provider(provider_name: str) -> VideoProvider:
    provider_entry = PROVIDERS.get(provider_name)
    if not provider_entry:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_name}")
    return provider_entry["provider"]


def _create_segment(
    session: Session,
    video: NodeVideo,
    segment_index: int,
    status: str = "pending",
) -> VideoSegment:
    start_second = segment_index * SEGMENT_DURATION_SECONDS
    end_second = start_second + SEGMENT_DURATION_SECONDS
    segment = VideoSegment(
        node_video_id=video.id,
        segment_index=segment_index,
        start_second=start_second,
        end_second=end_second,
        status=status,
    )
    session.add(segment)
    session.commit()
    session.refresh(segment)
    return segment


def _update_video_status(session: Session, video: NodeVideo) -> None:
    segments: List[VideoSegment] = session.exec(
        select(VideoSegment).where(VideoSegment.node_video_id == video.id)
    ).all()
    if all(seg.status == "done" for seg in segments):
        video.status = "done"
    elif any(seg.status == "failed" for seg in segments):
        video.status = "failed"
    else:
        video.status = "processing"
    video.updated_at = datetime.utcnow()
    session.add(video)
    session.commit()


async def _process_segment_job(
    segment_id: str, prompt: str, audio_url: Optional[str], provider_name: str
) -> None:
    with SessionLocal() as session:
        segment = session.get(VideoSegment, segment_id)
        if not segment:
            return
        provider_instance = _resolve_provider(provider_name)
        job_id = await provider_instance.create_video_segment(
            prompt, SEGMENT_DURATION_SECONDS, audio_url
        )
        segment.provider_job_id = job_id
        segment.status = "processing"
        segment.updated_at = datetime.utcnow()
        session.add(segment)
        session.commit()

    while True:
        status_payload = await provider_instance.get_job_status(job_id)
        with SessionLocal() as session:
            segment = session.get(VideoSegment, segment_id)
            if not segment:
                return
            segment.status = status_payload.get("status", "processing")
            segment.video_url = status_payload.get("video_url")
            segment.error_message = status_payload.get("error_message")
            segment.updated_at = datetime.utcnow()
            session.add(segment)
            video = session.get(NodeVideo, segment.node_video_id)
            if video:
                _update_video_status(session, video)
            session.commit()

            if segment.status in {"done", "failed"}:
                break
        await asyncio.sleep(1)


def create_video(
    session: Session, payload: CreateVideoRequest, background_tasks: BackgroundTasks
) -> NodeVideo:
    _resolve_provider(payload.provider)
    video = NodeVideo(
        node_id=payload.node_id,
        prompt=payload.prompt,
        provider=payload.provider,
        voice_id=payload.voice_id,
        audio_url=payload.audio_url,
        status="processing",
    )
    session.add(video)
    session.commit()
    session.refresh(video)

    first_segment = _create_segment(session, video, segment_index=0, status="processing")
    background_tasks.add_task(
        asyncio.run,
        _process_segment_job(
            first_segment.id, payload.prompt, payload.audio_url, payload.provider
        ),
    )
    return video


def get_video(session: Session, video_id: str) -> NodeVideo:
    video = session.get(NodeVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Node video not found")
    video.segments  # trigger relationship load
    return video


def list_segments(session: Session, video_id: str) -> List[VideoSegment]:
    statement = (
        select(VideoSegment)
        .where(VideoSegment.node_video_id == video_id)
        .order_by(VideoSegment.segment_index)
    )
    return session.exec(statement).all()


def trigger_next_segment(
    session: Session, video_id: str, current_second: int, background_tasks: BackgroundTasks
) -> Optional[VideoSegment]:
    video = get_video(session, video_id)
    if current_second < 0:
        raise HTTPException(status_code=400, detail="current_second must be non-negative")

    # Determine current segment index based on playback time
    current_index = current_second // SEGMENT_DURATION_SECONDS
    position_in_segment = current_second % SEGMENT_DURATION_SECONDS

    if position_in_segment < SEGMENT_TRIGGER_OFFSET_SECONDS:
        return None

    next_segment_index = current_index + 1
    existing = session.exec(
        select(VideoSegment).where(
            VideoSegment.node_video_id == video.id,
            VideoSegment.segment_index == next_segment_index,
        )
    ).first()
    if existing:
        return existing

    segment = _create_segment(session, video, next_segment_index, status="processing")
    background_tasks.add_task(
        asyncio.run,
        _process_segment_job(segment.id, video.prompt, video.audio_url, video.provider),
    )
    return segment


def available_providers() -> List[ProviderOption]:
    return [meta["info"] for meta in PROVIDERS.values()]


def build_player_config() -> PlayerConfig:
    return PlayerConfig()
