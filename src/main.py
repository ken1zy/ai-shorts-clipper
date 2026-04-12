"""Точка входа — полный пайплайн нарезки Shorts."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from src.ai_analyzer import ClipItem, analyze_cartoon
from src.audio_master import master_audio
from src.cli import parse_cli
from src.config import Config
from src.layout_builder import build_vertical_clip
from src.scene_snapper import snap_timestamps

console = Console()


@dataclass
class RenderedClip:
    clip: ClipItem
    output_path: Path
    snapped_start: float
    snapped_end: float


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level=level,
        colorize=True,
    )


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

    total_steps = 1 + len(clips) * 3
    rendered: list[RenderedClip] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("AI Analysis (Gemini)", total=total_steps)
        progress.advance(task_id)

        for index, clip in enumerate(clips, start=1):
            output_path = _resolve_output_path(input_path, output_base, index)
            prefix = f"[{index}/{len(clips)}]"

            progress.update(task_id, description=f"{prefix} Scene snap + layout + audio")
            logger.info(
                "{} score={}: {:.2f}–{:.2f} с → {}",
                prefix,
                clip.viral_score,
                clip.start_time,
                clip.end_time,
                output_path.name,
            )

            rendered.append(
                _process_clip(input_path, clip, output_path, config, target_lufs)
            )
            progress.advance(task_id, advance=3)

    return rendered


def _print_summary(rendered: list[RenderedClip]) -> None:
    lines = ["[bold green]Готово![/bold green]\n"]
    for index, item in enumerate(rendered, start=1):
        lines.append(
            f"[bold]#{index}[/bold] score={item.clip.viral_score}/10 | "
            f"[cyan]{item.snapped_start:.2f}[/cyan]–[cyan]{item.snapped_end:.2f}[/cyan] с\n"
            f"  {item.clip.description}\n"
            f"  → [bold]{item.output_path}[/bold]\n"
        )

    console.print(
        Panel(
            "".join(lines),
            title=f"AI Shorts Clipper — {len(rendered)} клип(ов)",
            border_style="green",
        )
    )


def main() -> int:
    args = parse_cli()
    _configure_logging(args.verbose)

    try:
        config = Config()
    except Exception as exc:
        console.print(f"[bold red]Ошибка конфигурации:[/bold red] {exc}")
        return 1

    if not config.GEMINI_API_KEY:
        console.print("[bold red]GEMINI_API_KEY[/bold red] не задан в .env")
        return 1

    input_path = args.input.resolve()
    output_base = args.output.resolve() if args.output else None

    if args.lufs is not None:
        config.DEFAULT_TARGET_LUFS = args.lufs

    if not input_path.is_file():
        console.print(f"[bold red]Файл не найден:[/bold red] {input_path}")
        return 1

    output_hint = (
        _resolve_output_path(input_path, output_base, 1).name
        if output_base
        else f"{input_path.stem}_short_N.mp4"
    )

    console.print(
        Panel(
            f"Вход:   [cyan]{input_path}[/cyan]\n"
            f"Выход:  [cyan]{output_hint}[/cyan]\n"
            f"LUFS:   [cyan]{config.DEFAULT_TARGET_LUFS}[/cyan]\n"
            f"Порог:  viral_score >= [cyan]{config.MIN_VIRAL_SCORE}[/cyan]",
            title="AI Shorts Clipper",
            border_style="blue",
        )
    )

    try:
        rendered = run_pipeline(input_path, output_base, config)
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/yellow]")
        return 130
    except Exception as exc:
        logger.exception("Ошибка пайплайна")
        console.print(f"[bold red]Ошибка:[/bold red] {exc}")
        return 1

    if not rendered:
        console.print(
            Panel(
                f"[yellow]Клипы с score >= {config.MIN_VIRAL_SCORE} не найдены[/yellow]",
                title="AI Shorts Clipper",
                border_style="yellow",
            )
        )
        return 0

    _print_summary(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
