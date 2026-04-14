# AI Shorts Clipper

Автоматическая нарезка вертикальных Shorts/Reels/TikTok из длинных видео (мультики, стримы, подкасты).

Скрипт сам находит «вирусные» моменты через Gemini, подрезает границы по склейкам сцен и собирает финальный ролик 9:16 с нормализованным звуком.

## Стек

| Компонент | Назначение |
|-----------|------------|
| **Gemini 2.0 Flash** | Анализ видео, поиск клипов по burn-in таймкоду |
| **PySceneDetect** | Притяжка start/end к границам сцен |
| **FFmpeg** | Proxy с таймкодом, layout 1080×1920, loudnorm |
| **Pydantic** | Строгая схема ответа от модели |
| **Rich + Loguru** | CLI с прогрессбаром и логами |

## Архитектура

```
Входное видео
    │
    ▼
┌─────────────────────┐
│  ai_analyzer.py     │  FFmpeg proxy + drawtext → Gemini → список клипов
└─────────┬───────────┘
          │ ClipItem[]
          ▼
┌─────────────────────┐
│  scene_snapper.py   │  PySceneDetect: snap start/end к склейкам
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  layout_builder.py  │  scale 1080 + pad 1920 (16:9 сверху)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  audio_master.py    │  loudnorm −14 LUFS + compand
└─────────┬───────────┘
          ▼
   output_short_N.mp4
```

## Требования

- Python 3.11+
- FFmpeg в `PATH`
- API-ключ Google Gemini

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # и вписать GEMINI_API_KEY
```

## Запуск

```bash
python -m src.main path/to/video.mp4
python -m src.main video.mp4 -o clips/my_short --lufs -16 -v
```

Выходные файлы: `<имя>_short_1.mp4`, `_short_2.mp4`, …

## Конфигурация (.env)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `GEMINI_API_KEY` | — | Ключ API (обязательно) |
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | Модель для анализа |
| `GEMINI_PROXY_HEIGHT` | `480` | Высота proxy для Gemini |
| `DEFAULT_TARGET_LUFS` | `-14.0` | Целевая громкость |
| `MIN_START_OFFSET` | `12.0` | Защита от заставки в начале (сек) |
| `MIN_VIRAL_SCORE` | `8` | Минимальный score клипа |

## Как работает отбор клипов

1. На proxy вшивается таймкод (`drawtext`) — модель читает точные секунды.
2. Gemini возвращает JSON-массив `clips` с `viral_score` 1–10.
3. Берём только клипы с score ≥ 8, длительностью 20–50 секунд.
4. Границы притягиваются к ближайшим склейкам сцен.

## Структура проекта

```
src/
  config.py          — настройки из .env
  cli.py             — argparse
  ai_analyzer.py     — Gemini + proxy
  scene_snapper.py   — PySceneDetect
  layout_builder.py  — FFmpeg 9:16 layout
  audio_master.py    — LUFS normalization
  main.py            — оркестрация пайплайна
```

## Лицензия

MIT
