"""Точка входа — пока только проверка конфига и аргументов."""

from __future__ import annotations

import sys

from src.cli import parse_cli
from src.config import Config


def main() -> int:
    args = parse_cli()

    try:
        config = Config()
    except Exception as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY не задан в .env", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Вход: {args.input.resolve()}")
        print(f"LUFS: {args.lufs or config.DEFAULT_TARGET_LUFS}")

    print("CLI готов, пайплайн пока не подключён.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
