from datetime import date

from core.report import render_console, write_summary_csv, write_summary_md, _rows
from core.result import ChannelResult


def _sample():
    return [
        ChannelResult(channel="dzen", week="2026-W29",
                      period_from="2026-07-13", period_to="2026-07-19",
                      metrics={"shows": 87, "reads": 5, "subscribers": 45,
                               "posts": [{"title": "x"}]},
                      source="xlsx", status="ok"),
        ChannelResult(channel="vk", week="2026-W29",
                      period_from="2026-07-13", period_to="2026-07-19",
                      metrics={"content_reach": 5, "channel_views": None},
                      source="vision", status="ok", needs_review=True),
    ]


def test_rows_skips_posts_list_and_labels_metrics():
    rows = _rows(_sample(), "2026-W29")
    # список posts не попадает в сводку
    assert all(r["Метрика"] != "posts" for r in rows)
    # человекочитаемые подписи
    labels = {r["Метрика"] for r in rows}
    assert "Показы" in labels
    assert "Охват контента" in labels
    # None рендерится как «—», а не пусто/ошибка
    ch = next(r for r in rows if r["Метрика"] == "Просмотры канала")
    assert ch["Значение"] == "—"
    # флаг проверки проброшен для ВК
    vk_rows = [r for r in rows if r["Канал"] == "vk"]
    assert all(r["Проверить"] == "да" for r in vk_rows)


def test_console_contains_numbers_and_status():
    txt = render_console(_sample(), "2026-W29", date(2026, 7, 13), date(2026, 7, 19),
                         out_dir=None)
    assert "DZEN" in txt and "87" in txt
    assert "проверить" in txt  # ВК помечен needs_review


def test_csv_is_semicolon_utf8sig(tmp_path):
    path = write_summary_csv(_sample(), "2026-W29", tmp_path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")          # utf-8-sig BOM для русского Excel
    text = raw.decode("utf-8-sig")
    assert ";" in text.splitlines()[0]              # разделитель — точка с запятой
    assert "Канал;Статус" in text.splitlines()[0]


def test_md_written(tmp_path):
    path = write_summary_md(_sample(), "2026-W29", date(2026, 7, 13), date(2026, 7, 19),
                            tmp_path)
    md = path.read_text(encoding="utf-8")
    assert "# Сводка сбора" in md
    assert "| Показы | 87 |" in md
