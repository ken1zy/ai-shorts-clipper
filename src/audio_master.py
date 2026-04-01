"""Нормализация громкости аудио через FFmpeg (LUFS + лёгкая компрессия)."""

from __future__ import annotations

import ffmpeg
from loguru import logger


def master_audio(
    input_path: str,
    output_path: str,
    target_lufs: float = -14.0,
) -> None:
    """Приводит громкость к целевому LUFS, видео копируется без перекодирования."""
    loudnorm = f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11"
    compand = "compand=attacks=0.3:decays=0.8:points=-80/-80|-45/-15|-27/-9|-5/-5|0/-2"
    audio_filter = f"{loudnorm},{compand}"

    logger.info("Мастеринг: target_lufs={:.1f}", target_lufs)

    try:
        probe = ffmpeg.probe(input_path)
        has_audio = any(s.get("codec_type") == "audio" for s in probe["streams"])
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Не удалось прочитать файл: {input_path}") from exc

    video_input = ffmpeg.input(input_path)

    if has_audio:
        (
            ffmpeg.output(
                video_input.video,
                video_input.audio,
                output_path,
                vcodec="copy",
                af=audio_filter,
                acodec="aac",
                audio_bitrate="192k",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    else:
        logger.warning("Аудио нет — сохраняем только видео")
        (
            ffmpeg.output(video_input.video, output_path, vcodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )

    logger.success("Финальный файл: {}", output_path)
