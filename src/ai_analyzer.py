"""Анализ видео через Gemini API — первая версия, один клип."""

from __future__ import annotations

import time
from pathlib import Path

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

from src.config import Config

SYSTEM_PROMPT = (
    "Посмотри видео и найди один самый смешной или динамичный момент для Shorts. "
    "Длительность клипа от 20 до 50 секунд. "
    "Верни start_time и end_time в секундах от начала видео."
)

POLL_INTERVAL_SEC = 2.0
MAX_UPLOAD_WAIT_SEC = 600.0


class ClipResponse(BaseModel):
    """Ответ модели — один лучший клип."""

    start_time: float = Field(..., description="Начало в секундах")
    end_time: float = Field(..., description="Конец в секундах")
    description: str = Field(..., min_length=1)
    viral_score: int = Field(..., ge=1, le=10)


def _wait_until_active(client: genai.Client, uploaded_file) -> object:
    deadline = time.monotonic() + MAX_UPLOAD_WAIT_SEC
    while uploaded_file.state.name != "ACTIVE":
        if uploaded_file.state.name == "FAILED":
            raise RuntimeError(f"Загрузка в Gemini упала: {uploaded_file.name}")
        if time.monotonic() > deadline:
            raise TimeoutError("Слишком долго ждём активации файла")
        time.sleep(POLL_INTERVAL_SEC)
        uploaded_file = client.files.get(name=uploaded_file.name)
    return uploaded_file


def analyze_cartoon(video_path: str, config: Config) -> ClipResponse | None:
    """Загружает видео в Gemini и возвращает один топ-клип."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    uploaded_file = None

    try:
        source = Path(video_path).resolve()
        logger.info("Загрузка видео в Gemini: {}", source)

        uploaded_file = client.files.upload(file=str(source))
        uploaded_file = _wait_until_active(client, uploaded_file)

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[uploaded_file, "Найди лучший момент для Shorts."],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ClipResponse,
            ),
        )

        if response.parsed is not None:
            clip = response.parsed
        else:
            clip = ClipResponse.model_validate_json(response.text)

        logger.success(
            "Клип: {:.2f}–{:.2f} с | score={} — {}",
            clip.start_time,
            clip.end_time,
            clip.viral_score,
            clip.description,
        )
        return clip

    finally:
        if uploaded_file is not None and uploaded_file.name:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as exc:
                logger.warning("Не удалось удалить файл из облака: {}", exc)
