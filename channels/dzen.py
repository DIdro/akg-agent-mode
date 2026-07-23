"""Дзен: XLSX «Статистика публикаций» из Студии через живой профиль.

ВАЖНО про источник (сверено 2026-07-24): берём отчёт «по дате события» —
endpoint rich-stat-xls с filterType=by-event&from=<дата>&to=<дата>. Он отдаёт
события ЗА ПЕРИОД (как строка «Всего за N дней» и кнопка «Отчёт» в UI Студии).
НЕ путать с прежним вариантом ?intervalStart=<ms>&intervalEnd=<ms>&type=…,
который отдавал LIFETIME-статистику по постам (накопленную за всё время) —
её сумма завышала недельные показы в десятки раз.
"""
import re
from pathlib import Path

from core.result import ChannelResult
from core.xlsx import parse_xlsx
import config

# Колонки XLSX Студии: 0=дата 1=тип 2=заголовок 3=url 4=дочитывания 5=показы
# 6=открытия 7=время(мин) 8=комментарии 9=подписки 10=лайки
COLS = {"reads": 4, "shows": 5, "opens": 6, "time_min": 7,
        "comments": 8, "subs": 9, "likes": 10}


def _aggregate_posts(rows: list) -> list[dict]:
    """Чистая функция: строки XLSX publications-stat -> список постов с
    числовыми метриками по COLS. rows — полный список строк листа
    ([title, header, totals, посты...]); использует rows[3:]."""
    posts = []
    for row in rows[3:]:
        if len(row) <= max(COLS.values()):
            continue
        post = {k: int(float(row[i] or 0)) for k, i in COLS.items()}
        post["title"] = row[2] if len(row) > 2 else ""
        post["type"] = row[1] if len(row) > 1 else ""
        posts.append(post)
    return posts


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="dzen", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat())
    out_dir.mkdir(parents=True, exist_ok=True)
    # publisherId — из public_url в конфиге (последний сегмент пути)
    pub = config.CHANNELS["dzen"]["public_url"].rstrip("/").rsplit("/", 1)[-1]
    page = ctx.new_page()
    try:
        stat_url = (f"https://dzen.ru/profile/editor/id/{pub}/publications-stat"
                    f"?statType=publications")
        page.goto(stat_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "passport" in page.url or "/login" in page.url:
            res.status = "auth_required"
            res.error = "Сессия Дзена истекла — запустите collect.py --login"
            return res
        # Бывает, что вместо passport/login недостаточная сессия тихо
        # редиректит на публичную страницу канала (dzen.ru/id/...), а не на
        # логин — ловим это до проверки csrfToken, чтобы дать понятную
        # причину, а не "csrfToken не найден".
        if "publications-stat" not in page.url:
            page.screenshot(path=str(out_dir / "dzen_auth_redirect.png"), full_page=True)
            res.screenshots.append("dzen_auth_redirect.png")
            res.status = "auth_required"
            res.error = "Сессия Дзена истекла — запустите collect.py --login"
            return res
        page.screenshot(path=str(out_dir / "dzen_stats.png"), full_page=True)
        res.screenshots.append("dzen_stats.png")

        csrf_m = re.search(r'"csrfToken":"([a-f0-9:]+)"', page.content())
        if not csrf_m:
            page.screenshot(path=str(out_dir / "dzen_fail.png"), full_page=True)
            res.screenshots.append("dzen_fail.png")
            res.status, res.error = "failed", "csrfToken не найден (сессия?)"
            return res
        csrf = csrf_m.group(1)

        # Отчёт «по дате события» за период [start, end] — один файл на все типы
        # публикаций (incomePublicationType=all). Даты в формате YYYY-MM-DD.
        totals = {k: 0 for k in COLS}
        posts = []
        url = (f"https://dzen.ru/editor-api/v2/publisher-publications-rich-stat-xls"
               f"?incomePublicationType=all&filterType=by-event&publisherId={pub}"
               f"&from={start:%Y-%m-%d}&to={end:%Y-%m-%d}")
        try:
            r = ctx.request.get(url, headers={"X-Csrf-Token": csrf, "Referer": stat_url})
        except Exception as e:
            res.status, res.error = "failed", f"xlsx-отчёт: {type(e).__name__}: {e}"
            return res
        if r.status != 200:
            res.status, res.error = "failed", f"xlsx-отчёт HTTP {r.status}"
            return res
        blob = r.body()
        (out_dir / "dzen_by_event.xlsx").write_bytes(blob)
        rows = parse_xlsx(blob)
        for post in _aggregate_posts(rows):
            posts.append(post)
            for k in totals:
                totals[k] += post[k]

        res.metrics = {**totals, "posts_count": len(posts)}
        res.metrics["posts"] = posts
        res.source = "xlsx"

        # Подписчики — с публичной страницы канала (по спеке). Собранные выше
        # XLSX-метрики уже лежат в res — сбой этого блока (таймаут goto,
        # некорректный parse_metric_value) не должен их обнулять, поэтому
        # весь блок в try/except, а не unguarded.
        try:
            from vision import parse_metric_value
            page.goto(config.CHANNELS["dzen"]["public_url"], wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            sub_m = re.search(r"(\d[\d.,  ]*[KkКкMmМм]?)\s*подписчик",
                              page.inner_text("body"))
            res.metrics["subscribers"] = parse_metric_value(sub_m.group(1)) if sub_m else None
        except Exception as e:
            res.metrics["subscribers"] = None
            res.needs_review = True
            warn = f"подписчики не собраны: {type(e).__name__}: {e}"
            res.error = f"{res.error}; {warn}" if res.error else warn

        if not posts and res.error:
            res.status = "failed"
        return res
    finally:
        page.close()
