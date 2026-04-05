"""Точка входа — полный пайплайн нарезки Shorts."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.ai_analyzer import ClipItem, analyze_cartoon
from src.audio_master import master_audio
from src.cli import parse_cli
from src.config import Config
from src.layout_builder import build_vertical_clip
from src.scene_snapper import snap_timestamps


@dataclass
class RenderedClip:
    clip: ClipItem
    output_path: Path
    snapped_start: float
    snapped_end: float


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, format="{time:HH:mm:ss} | {level:<8} | {message}", level=level)


def _resolve_output_path(input_path: Path, output_base: Path | None, index: int) -> Path:
    if output_base is None:
        return input_path.with_name(f"{input_path.stem}_short_{index}.mp4")
    stem = output_base.stem
    if not stem.endswith("_short"):
        stem = f"{stem}_short"
    return output_base.parent / f"{stem}_{index}.mp4"


def _process_clip(
    input_path: Path,
    clip: ClipItem,
    output_path: Path,
    config: Config,
    target_lufs: float,
) -> RenderedClip:
    snapped_start, snapped_end = snap_timestamps(
        str(input_path),
        clip.start_time,
        clip.end_time,
        min_start_offset=config.MIN_START_OFFSET,
    )

    with tempfile.NamedTemporaryFile(suffix="_cropped.mp4", delete=False) as tmp:
        cropped_path = tmp.name

    try:
        build_vertical_clip(
            input_path=str(input_path),
            output_path=cropped_path,
            start_sec=snapped_start,
            end_sec=snapped_end,
        )
        master_audio(cropped_path, str(output_path), target_lufs=target_lufs)
    finally:
        Path(cropped_path).unlink(missing_ok=True)

    return RenderedClip(
        clip=clip,
        output_path=output_path,
        snapped_start=snapped_start,
        snapped_end=snapped_end,
    )


def run_pipeline(input_path: Path, output_base: Path | None, config: Config) -> list[RenderedClip]:
    target_lufs = config.DEFAULT_TARGET_LUFS
    clips = analyze_cartoon(str(input_path), config)
    if not clips:
        return []

    rendered: list[RenderedClip] = []
    for index, clip in enumerate(clips, start=1):
        output_path = _resolve_output_path(input_path, output_base, index)
        logger.info(
            "[{}/{}] Рендер score={}: {:.2f}–{:.2f} с → {}",
            index,
            len(clips),
            clip.viral_score,
            clip.start_time,
            clip.end_time,
            output_path.name,
        )
        rendered.append(_process_clip(input_path, clip, output_path, config, target_lufs))

    return rendered


def main() -> int:
    args = parse_cli()
    _configure_logging(args.verbose)

    try:
        config = Config()
    except Exception as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY не задан в .env", file=sys.stderr)
        return 1

    input_path = args.input.resolve()
    output_base = args.output.resolve() if args.output else None

    if args.lufs is not None:
        config.DEFAULT_TARGET_LUFS = args.lufs

    if not input_path.is_file():
        print(f"Файл не найден: {input_path}", file=sys.stderr)
        return 1

    try:
        rendered = run_pipeline(input_path, output_base, config)
    except KeyboardInterrupt:
        print("Прервано.")
        return 130
    except Exception as exc:
        logger.exception("Ошибка пайплайна")
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if not rendered:
        print("Клипы с viral_score >= порога не найдены.")
        return 0

    print(f"\nГотово: {len(rendered)} клип(ов)")
    for i, item in enumerate(rendered, start=1):
        print(
            f"  #{i} {item.snapped_start:.2f}–{item.snapped_end:.2f} с → {item.output_path}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
