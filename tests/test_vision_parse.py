import pytest
from vision import parse_metric_value, extract_metrics


@pytest.mark.parametrize("raw,expected", [
    ("17,6K", 17600),
    ("17.6K", 17600),
    ("3,6К", 3600),          # кириллическая К
    ("16 000", 16000),
    ("16 000", 16000),  # неразрывный пробел
    ("504", 504),
    ("1,2M", 1200000),
    ("1,2М", 1200000),       # кириллическая М
    ("0", 0),
    ("-4", -4),              # прирост/убыль подписчиков — отрицательное
    ("−4", -4),              # U+2212 minus sign
    ("– 12", -12),           # en dash + пробел
    ("-1,2K", -1200),        # отрицательное с множителем
    ("—", None),             # одиночное тире (без цифр) — не число
    ("", None),
    ("N/A", None),
    ("500\n3", None),        # внутренний перенос строки — не чистое число
])
def test_parse_metric_value(raw, expected):
    assert parse_metric_value(raw) == expected


def test_extract_metrics_degrades_gracefully_on_api_error(tmp_path, monkeypatch):
    """extract_metrics должен вернуть все метрики=None + needs_review=True при ошибке API."""
    # Создаём фиктивный PNG файл
    png_path = tmp_path / "x.png"
    png_path.write_bytes(b"\x89PNG fake")

    expected = {"a": "desc", "b": "desc"}

    # Монкепатч: заменяем Anthropic на функцию, которая выбрасывает исключение
    import vision
    def raise_error(*args, **kwargs):
        raise RuntimeError("Mock API error")

    monkeypatch.setattr(vision.anthropic, "Anthropic", raise_error)

    # Вызываем и проверяем graceful degradation
    result, needs_review = extract_metrics(png_path, expected)

    assert result == {"a": None, "b": None}
    assert needs_review is True
