"""Анализ видео через Gemini API — первая версия, один клип."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

from src.config import Config

SYSTEM_PROMPT = (
    "На экране видео есть таймкод — читай start_time и end_time строго по нему. "
    "Найди один самый смешной или динамичный момент для Shorts. "
    "Длительность клипа от 20 до 50 секунд."
)

GEMINI_PROXY_FILENAME = "for_gemini_output.mp4"
POLL_INTERVAL_SEC = 2.0
MAX_UPLOAD_WAIT_SEC = 600.0


class ClipResponse(BaseModel):
    """Ответ модели — один лучший клип."""

    start_time: float = Field(..., description="Начало в секундах")
    end_time: float = Field(..., description="Конец в секундах")
    description: str = Field(..., min_length=1)
    viral_score: int = Field(..., ge=1, le=10)


def _build_timecode_filter(height: int) -> str:
    drawtext = (
        "drawtext=text='%{pts\\:hms}'"
        ":x=h*0.05:y=h*0.05"
        ":fontsize=h*0.12"
        ":fontcolor=white"
        ":box=1:boxcolor=black@0.8:boxborderw=5"
    )
    return f"scale=-2:{height},{drawtext}"


def _create_gemini_proxy(video_path: str, config: Config) -> Path:
    """Рендерит лёгкую копию с burn-in таймкодом для Gemini."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise RuntimeError("FFmpeg не найден в PATH")

    source = Path(video_path).resolve()
    output_path = source.parent / GEMINI_PROXY_FILENAME
    video_filter = _build_timecode_filter(config.GEMINI_PROXY_HEIGHT)

    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-y",
        "-i",
        str(source),
        "-vf",
        video_filter,
        "-vcodec",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "28",
        "-acodec",
        "aac",
        "-b:a",
        "64k",
        str(output_path),
    ]

    logger.info("Proxy {}p с таймкодом → {}", config.GEMINI_PROXY_HEIGHT, output_path)
    subprocess.run(command, check=True, capture_output=True)
    return output_path


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
    """Создаёт proxy с таймкодом, отправляет в Gemini, возвращает один клип."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    uploaded_file = None
    proxy_path: Path | None = None

    try:
        proxy_path = _create_gemini_proxy(video_path, config)
        logger.info("Отправка proxy в Gemini: {}", proxy_path)

        uploaded_file = client.files.upload(file=str(proxy_path))
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

        if proxy_path is not None and proxy_path.exists():
            try:
                proxy_path.unlink()
            except Exception as exc:
                logger.warning("Не удалось удалить proxy: {}", exc)
