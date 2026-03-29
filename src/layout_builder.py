"""Сборка вертикального кадра 9:16 — 16:9 сверху на чёрном фоне 1080x1920."""

from __future__ import annotations

import ffmpeg
from loguru import logger

# Масштаб по ширине 1080, pad до 1920 — видео прижато к верхнему краю
VIDEO_FILTER = "scale=1080:-1,pad=1080:1920:0:0:black"


def build_vertical_clip(
    input_path: str,
    output_path: str,
    start_sec: float,
    end_sec: float,
) -> None:
    """Вырезает фрагмент и собирает layout 9:16 без обрезки по бокам."""
    if end_sec <= start_sec:
        raise ValueError("end_sec должен быть больше start_sec")

    duration = end_sec - start_sec
    logger.info("Layout 9:16: {:.3f}–{:.3f} с", start_sec, end_sec)

    stream = ffmpeg.input(input_path, ss=start_sec, t=duration)
    try:
        (
            ffmpeg.output(
                stream,
                output_path,
                vf=VIDEO_FILTER,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                preset="medium",
            )
            .overwrite_output()
            .run(quiet=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else str(exc)
        raise RuntimeError(f"FFmpeg layout error: {stderr}") from exc

    logger.success("Клип сохранён: {}", output_path)
