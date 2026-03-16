"""Анализ видео через Gemini API с burn-in таймкодом."""

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
    "Проанализируй видео по таймкоду на экране. "
    "Твоя цель — найти самые вирусные, динамичные или смешные моменты для Shorts. "
    "Оценивай каждый момент по шкале 1–10. "
    "Отбирай ТОЛЬКО сцены с оценкой 8+ (High Quality Bar). "
    "Если таких моментов 1 — верни 1 клип, если 4 — верни 4. "
    "Если ничего годного нет — верни пустой список. "
    "Не бери заставку в начале. "
    "Длительность каждого клипа от 20 до 50 секунд. "
    "start_time и end_time считывай строго с таймкода на экране. "
    "Верни JSON с массивом clips."
)

GEMINI_PROXY_FILENAME = "for_gemini_output.mp4"
POLL_INTERVAL_SEC = 2.0
MAX_UPLOAD_WAIT_SEC = 600.0
MIN_CLIP_DURATION_SEC = 20.0
MAX_CLIP_DURATION_SEC = 50.0


class ClipItem(BaseModel):
    """Один вирусный фрагмент."""

    start_time: float = Field(..., description="Начало в секундах")
    end_time: float = Field(..., description="Конец в секундах")
    description: str = Field(..., min_length=1)
    viral_score: int = Field(..., ge=1, le=10)


class ClipsResponse(BaseModel):
    """Список лучших клипов от модели."""

    clips: list[ClipItem] = Field(default_factory=list)


def _build_timecode_filter(height: int) -> str:
    drawtext = (
        "drawtext=text='%{pts\\:hms}'"
        ":x=h*0.05:y=h*0.05"
        ":fontsize=h*0.12"
        ":fontcolor=white"
        ":box=1:boxcolor=black@0.8:boxborderw=5"
    )
    return f"scale=-2:{height},{drawtext}"


def _run_ffmpeg_proxy(source: Path, output_path: Path, video_filter: str) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise RuntimeError("FFmpeg не найден в PATH")

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

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logger.error("FFmpeg stderr: {}", exc.stderr)
        raise RuntimeError("Не удалось создать proxy с таймкодом") from exc


def _create_gemini_proxy(video_path: str, config: Config) -> Path:
    source = Path(video_path).resolve()
    output_path = source.parent / GEMINI_PROXY_FILENAME
    video_filter = _build_timecode_filter(config.GEMINI_PROXY_HEIGHT)

    logger.info("Proxy {}p с таймкодом → {}", config.GEMINI_PROXY_HEIGHT, output_path)
    _run_ffmpeg_proxy(source, output_path, video_filter)
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


def _is_valid_clip(clip: ClipItem) -> bool:
    if clip.end_time <= clip.start_time:
        return False
    duration = clip.end_time - clip.start_time
    return MIN_CLIP_DURATION_SEC <= duration <= MAX_CLIP_DURATION_SEC


def filter_top_clips(clips: list[ClipItem], config: Config) -> list[ClipItem]:
    """Оставляет валидные клипы с viral_score >= порога."""
    valid = [
        clip
        for clip in clips
        if _is_valid_clip(clip) and clip.viral_score >= config.MIN_VIRAL_SCORE
    ]
    return sorted(valid, key=lambda c: c.viral_score, reverse=True)


def analyze_cartoon(video_path: str, config: Config) -> list[ClipItem]:
    """Proxy → Gemini → список топ-клипов."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    uploaded_file = None
    proxy_path: Path | None = None

    try:
        proxy_path = _create_gemini_proxy(video_path, config)
        uploaded_file = client.files.upload(file=str(proxy_path))
        uploaded_file = _wait_until_active(client, uploaded_file)

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[uploaded_file, "Верни топ-клипы в JSON."],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ClipsResponse,
            ),
        )

        if response.parsed is not None:
            parsed = response.parsed
        else:
            parsed = ClipsResponse.model_validate_json(response.text)

        clips = filter_top_clips(parsed.clips, config)

        for index, clip in enumerate(clips, start=1):
            logger.success(
                "Топ-клип #{}: {:.2f}–{:.2f} с | score={} — {}",
                index,
                clip.start_time,
                clip.end_time,
                clip.viral_score,
                clip.description,
            )

        return clips

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
