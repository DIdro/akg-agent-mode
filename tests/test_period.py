from datetime import date
from core.period import last_completed_week, parse_week


def test_parse_week():
    label, start, end = parse_week("2026-W29")
    assert label == "2026-W29"
    assert start == date(2026, 7, 13)   # понедельник
    assert end == date(2026, 7, 19)     # воскресенье


def test_last_completed_week_mid_week():
    # среда 2026-07-22 -> последняя завершённая неделя W29 (13-19 июля)
    label, start, end = last_completed_week(today=date(2026, 7, 22))
    assert label == "2026-W29"
    assert (start, end) == (date(2026, 7, 13), date(2026, 7, 19))


def test_last_completed_week_on_monday():
    # понедельник 2026-07-20 -> завершилась W29
    label, _, _ = last_completed_week(today=date(2026, 7, 20))
    assert label == "2026-W29"
