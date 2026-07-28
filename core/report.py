"""Сводка результатов прогона: читаемая таблица в консоль + файлы summary.md / summary.csv.

CSV — под русский Excel: разделитель `;` и кодировка utf-8-sig (BOM), иначе
кириллица и колонки едут.
"""
from pathlib import Path

# Человекочитаемые подписи метрик (ключи каналов уникальны, кроме subscribers,
# который в обоих контекстах — «Подписчики»).
LABELS = {
    # Дзен
    "reads": "Дочитывания и просмотры",
    "shows": "Показы",
    "opens": "Открытия",
    "time_min": "Время просмотра, мин",
    "comments": "Комментарии",
    "subs": "Подписки (прирост)",
    "likes": "Лайки",
    "posts_count": "Публикаций",
    "subscribers": "Подписчики (всего)",
    # ВК
    "visits": "Посещения",
    "content_views": "Просмотры контента",
    "content_reach": "Охват контента",
    "members": "Подписчики сообщества (прирост)",
    "posts_reach": "Охват постов",
    "video_views": "Просмотры видео",
    "channel_views": "Просмотры канала",
    "channel_subs": "Подписчики канала (прирост)",
    # Тенчат
    "reach": "Охват записей",
    "views": "Просмотры",
}

# Метрики-значения показываем; служебные/списочные поля скрываем.
_HIDE = {"posts"}


def _name(res) -> str:
    """Отображаемое имя: label (напр. «vk:agcapital» для конкретного
    сообщества), иначе — канал."""
    return res.label or res.channel


def _metric_items(res) -> list[tuple[str, object]]:
    """Пары (подпись, значение) метрик канала в порядке словаря, без служебных."""
    out = []
    for key, val in res.metrics.items():
        if key in _HIDE:
            continue
        out.append((LABELS.get(key, key), val))
    return out


def _fmt(val) -> str:
    return "—" if val is None else str(val)


def render_console(results: list, week: str, start, end, out_dir: Path) -> str:
    """Читаемая сводка прогона для печати в консоль."""
    lines = [f"\n=== Сводка {week} ({start} — {end}) ==="]
    for res in results:
        flags = []
        if res.needs_review:
            flags.append("проверить")
        flag_s = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"\n{_name(res).upper():16s} {res.status}"
                     f"  (source={res.source or '—'}){flag_s}")
        for label, val in _metric_items(res):
            lines.append(f"    {label:.<28s} {_fmt(val)}")
        if res.error:
            lines.append(f"    ! {res.error[:160]}")
    lines.append(f"\nФайлы: {out_dir}")
    return "\n".join(lines)


def _rows(results: list, week: str) -> list[dict]:
    """Длинный формат: строка на (канал, метрика) — удобно фильтровать в Excel."""
    rows = []
    for res in results:
        for label, val in _metric_items(res):
            rows.append({
                "Канал": _name(res),
                "Статус": res.status,
                "Период": week,
                "Метрика": label,
                "Значение": _fmt(val),
                "Проверить": "да" if res.needs_review else "",
            })
    return rows


def write_summary_csv(results: list, week: str, out_dir: Path) -> Path:
    """summary.csv — `;`-разделитель + utf-8-sig под русский Excel."""
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.csv"
    rows = _rows(results, week)
    cols = ["Канал", "Статус", "Период", "Метрика", "Значение", "Проверить"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return path


def write_summary_md(results: list, week: str, start, end, out_dir: Path) -> Path:
    """summary.md — по секции на канал, таблица метрика|значение."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "summary.md"
    lines = [f"# Сводка сбора — {week} ({start} — {end})", ""]
    lines.append("| Канал | Статус | Источник | Проверить |")
    lines.append("|---|---|---|---|")
    for res in results:
        lines.append(f"| {_name(res)} | {res.status} | {res.source or '—'} | "
                     f"{'да' if res.needs_review else ''} |")
    lines.append("")
    for res in results:
        lines.append(f"## {_name(res)}")
        lines.append("")
        lines.append("| Метрика | Значение |")
        lines.append("|---|---|")
        for label, val in _metric_items(res):
            lines.append(f"| {label} | {_fmt(val)} |")
        if res.error:
            lines.append("")
            lines.append(f"> ⚠️ {res.error}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
