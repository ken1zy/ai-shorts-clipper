"""Разбор аргументов командной строки."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-shorts-clipper",
        description="Нарезка вертикальных Shorts из длинного видео.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Путь к исходному видеофайлу",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Базовое имя выходного файла",
    )
    parser.add_argument(
        "--lufs",
        type=float,
        default=None,
        help="Целевая громкость в LUFS",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Подробный вывод",
    )
    return parser


def parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)
