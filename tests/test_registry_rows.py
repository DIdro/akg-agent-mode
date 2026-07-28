from datetime import date
from core.registry_rows import to_registry_rows
from core.result import ChannelResult


def _dzen_ok():
    return ChannelResult(channel="dzen", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="xlsx",
        metrics={"shows": 87, "reads": 5, "subs": 0, "posts_count": 12,
                 "subscribers": 45, "posts": []})


def _vk_ok():
    return ChannelResult(channel="vk", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="vision",
        metrics={"content_reach": 5, "content_views": 28, "members": 0,
                 "channel_views": 12, "video_views": 3})


def _tenchat_ok():
    return ChannelResult(channel="tenchat", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="xhr",
        needs_review=True,
        metrics={"reach": 0, "views": 0, "subscribers": 0})


def _failed():
    return ChannelResult(channel="dzen", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="failed")


def test_dzen_row_maps_shows_to_reach():
    rows = to_registry_rows([_dzen_ok()], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    d = next(r for r in rows if r["channel"] == "Корп. блог Дзен")
    assert d["reach"] == 87            # показы
    assert d["subs_social"] == 0       # подписки-прирост из XLSX
    assert d["week_start"] == "13.07.2026"
    assert "12 публ" in d["comment"] and "45" in d["comment"]


def test_vk_expands_into_three_channels():
    rows = to_registry_rows([_vk_ok()], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    by = {r["channel"]: r for r in rows}
    assert by["Корп. ВК-сообщество"]["reach"] == 5      # охват контента
    assert by["Корп. ВК блог"]["reach"] == 12           # просмотры канала
    assert by["Корп. ВК-видео"]["reach"] == 3           # просмотры видео
    # members сообщества — абсолютное число, нода посчитает Δ
    assert by["Корп. ВК-сообщество"]["subs_absolute"] is True
    assert "subs_absolute" not in by["Корп. ВК блог"]


def test_vk_skips_empty_subtab():
    # channel_views=None → строки «Корп. ВК блог» нет
    r = _vk_ok(); r.metrics["channel_views"] = None
    rows = to_registry_rows([r], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    assert not any(x["channel"] == "Корп. ВК блог" for x in rows)


def test_tenchat_marks_period_in_comment():
    rows = to_registry_rows([_tenchat_ok()], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    t = rows[0]
    assert t["channel"] == "Тенчат ЛБ"
    assert "7 дней" in t["comment"]
    assert t["_needs_review"] is True


def test_vk_uses_account_registry_override():
    r = _vk_ok()
    r.registry_override = {"community": "ВК ЛБ"}   # аккаунт 2 (только сообщество)
    r.metrics = {"content_reach": 17, "content_views": 40, "members": 5,
                 "channel_views": None, "video_views": None}
    rows = to_registry_rows([r], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    assert rows[0]["channel"] == "ВК ЛБ"
    assert rows[0]["reach"] == 17
    # channel/video = None → строк «Корп. ВК блог»/«Корп. ВК-видео» нет
    assert not any(x["channel"] == "Корп. ВК блог" for x in rows)


def test_dzen_uses_account_registry_override():
    # Второй Дзен-кабинет (ЛБ) пишется под своим именем канала (строка), а не
    # под дефолтным «Корп. блог Дзен».
    r = _dzen_ok()
    r.registry_override = "Дзен ЛБ"
    rows = to_registry_rows([r], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    assert rows[0]["channel"] == "Дзен ЛБ"
    assert rows[0]["reach"] == 87
    assert not any(x["channel"] == "Корп. блог Дзен" for x in rows)


def test_failed_channel_produces_no_rows():
    rows = to_registry_rows([_failed()], "2026-W29", date(2026, 7, 13), date(2026, 7, 19))
    assert rows == []
