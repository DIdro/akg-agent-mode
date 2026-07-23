import pytest
from vision import parse_metric_value


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
    ("—", None),
    ("", None),
    ("N/A", None),
])
def test_parse_metric_value(raw, expected):
    assert parse_metric_value(raw) == expected
