"""
Audio proxy router — TTS and STT endpoints.

All audio calls go through the backend so the API key is never exposed to the
browser and CORS issues are avoided.
"""
import io
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from ..auth import get_db_with_rls
from ..models import LLMSettings

router = APIRouter(prefix="/api/audio", tags=["audio"])
logger = logging.getLogger(__name__)


def _get_active_settings(db: DBSession) -> LLMSettings:
    s = db.query(LLMSettings).filter(LLMSettings.is_active.is_(True)).first()
    if not s:
        raise HTTPException(404, "No active LLM profile")
    return s


@router.post("/speech")
async def text_to_speech(
    input: str = Form(...),
    model: Optional[str] = Form(None),
    voice: Optional[str] = Form(None),
    speed: Optional[float] = Form(1.0),
    db: DBSession = Depends(get_db_with_rls),
):
    """
    Proxy POST to {base_url}/audio/speech.
    Returns audio/mpeg stream for in-browser playback.
    """
    settings = _get_active_settings(db)
    payload = {
        "model": model or settings.tts_model or "tts-1",
        "voice": voice or settings.tts_voice or "alloy",
        "input": input,
        "speed": speed or settings.tts_speed or 1.0,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(
                f"{settings.base_url.rstrip('/')}/audio/speech",
                headers={"Authorization": f"Bearer {settings.api_key}"},
                json=payload,
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("TTS error: %s — %s", e.response.status_code, e.response.text[:200])
            raise HTTPException(e.response.status_code, "TTS provider error")
    return StreamingResponse(
        io.BytesIO(r.content),
        media_type=r.headers.get("content-type", "audio/mpeg"),
    )


@router.post("/transcriptions")
async def speech_to_text(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    db: DBSession = Depends(get_db_with_rls),
):
    """
    Proxy POST to {base_url}/audio/transcriptions.
    Returns {"text": "...transcription..."}.
    """
    settings = _get_active_settings(db)
    audio_bytes = await file.read()
    effective_lang = language or settings.stt_language
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(
                f"{settings.base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.api_key}"},
                files={"file": (file.filename or "audio.webm", audio_bytes, file.content_type or "audio/webm")},
                data={
                    "model": model or settings.stt_model or "whisper-1",
                    **({"language": effective_lang} if effective_lang not in (None, "auto") else {}),
                },
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("STT error: %s — %s", e.response.status_code, e.response.text[:200])
            raise HTTPException(e.response.status_code, "STT provider error")
    return r.json()
