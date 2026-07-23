"""Расчёт отчётного периода (ISO-недели, как в клиентском пайплайне АКГ)."""
from datetime import date, timedelta


def parse_week(week_label: str) -> tuple[str, date, date]:
    """'2026-W29' -> (label, monday, sunday)."""
    year_s, week_s = week_label.split("-W")
    start = date.fromisocalendar(int(year_s), int(week_s), 1)
    return week_label, start, start + timedelta(days=6)


def last_completed_week(today: date | None = None) -> tuple[str, date, date]:
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    end = this_monday - timedelta(days=1)          # прошлое воскресенье
    start = end - timedelta(days=6)
    y, w, _ = start.isocalendar()
    return f"{y}-W{w:02d}", start, end
