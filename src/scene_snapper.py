"""Притяжка таймкодов к границам сцен через PySceneDetect."""

from __future__ import annotations

from loguru import logger
from scenedetect import ContentDetector, detect


def _extract_cut_points(video_path: str) -> list[float]:
    scene_list = detect(video_path, ContentDetector())
    cut_points: list[float] = []
    for index, (start_time, _) in enumerate(scene_list):
        if index == 0:
            continue
        cut_points.append(round(start_time.get_seconds(), 3))
    logger.debug("Найдено {} склеек", len(cut_points))
    return sorted(cut_points)


def _snap_to_previous(
    cut_points: list[float],
    raw_start: float,
    min_start_offset: float,
) -> float:
    previous = [p for p in cut_points if p <= raw_start]
    if not previous:
        return round(raw_start, 3) if raw_start >= min_start_offset else 0.0

    candidate = max(previous)
    if raw_start >= min_start_offset and candidate < min_start_offset:
        logger.warning(
            "Притяжка start отклонена — зона интро < {:.1f} с",
            min_start_offset,
        )
        return round(raw_start, 3)
    return candidate


def _snap_to_subsequent(cut_points: list[float], raw_end: float) -> float:
    subsequent = [p for p in cut_points if p >= raw_end]
    if not subsequent:
        return round(raw_end, 3)
    return min(subsequent)


def snap_timestamps(
    video_path: str,
    raw_start: float,
    raw_end: float,
    min_start_offset: float = 12.0,
) -> tuple[float, float]:
    """Притягивает start к предыдущей склейке, end — к следующей."""
    if raw_end <= raw_start:
        raise ValueError("raw_end должен быть больше raw_start")

    cut_points = _extract_cut_points(video_path)
    snapped_start = round(_snap_to_previous(cut_points, raw_start, min_start_offset), 3)
    snapped_end = round(_snap_to_subsequent(cut_points, raw_end), 3)

    if snapped_end <= snapped_start:
        logger.warning("Интервал схлопнулся после притяжки — оставляем исходные таймкоды")
        snapped_start = round(raw_start, 3)
        snapped_end = round(raw_end, 3)

    logger.info(
        "Притяжка: {:.3f}–{:.3f} → {:.3f}–{:.3f}",
        raw_start,
        raw_end,
        snapped_start,
        snapped_end,
    )
    return snapped_start, snapped_end
