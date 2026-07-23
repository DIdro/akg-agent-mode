"""Дзен: XLSX «Статистика публикаций» из Студии через живой профиль."""
import re
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

from core.result import ChannelResult
from core.xlsx import parse_xlsx
import config

MSK = timezone(timedelta(hours=3))
TYPES = ["article", "brief"]
# Колонки XLSX Студии: 0=дата 1=тип 2=заголовок 3=url 4=дочитывания 5=показы
# 6=открытия 7=время(мин) 8=комментарии 9=подписки 10=лайки
COLS = {"reads": 4, "shows": 5, "opens": 6, "time_min": 7,
        "comments": 8, "subs": 9, "likes": 10}


def _ms(d, end=False):
    t = time(23, 59, 59) if end else time(0, 0, 0)
    return int(datetime.combine(d, t, tzinfo=MSK).timestamp() * 1000)


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="dzen", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat())
    out_dir.mkdir(parents=True, exist_ok=True)
    # publisherId — из public_url в конфиге (последний сегмент пути)
    pub = config.CHANNELS["dzen"]["public_url"].rstrip("/").rsplit("/", 1)[-1]
    page = ctx.new_page()
    try:
        stat_url = (f"https://dzen.ru/profile/editor/id/{pub}/publications-stat"
                    f"?statType=publications&intervalType=custom"
                    f"&intervalStart={_ms(start)}&intervalEnd={_ms(end, True)}")
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

        totals = {k: 0 for k in COLS}
        posts = []
        errors = []
        type_failed = False
        for typ in TYPES:
            url = (f"https://dzen.ru/editor-api/v2/publisher-publications-rich-stat-xls"
                   f"?intervalStart={_ms(start)}&intervalEnd={_ms(end, True)}"
                   f"&publisherId={pub}&type={typ}")
            try:
                r = ctx.request.get(url, headers={"X-Csrf-Token": csrf, "Referer": stat_url})
            except Exception as e:
                type_failed = True
                errors.append(f"xlsx[{typ}] {e}")
                continue
            if r.status != 200:
                type_failed = True
                errors.append(f"xlsx[{typ}] HTTP {r.status}")
                continue
            blob = r.body()
            (out_dir / f"dzen_{typ}.xlsx").write_bytes(blob)
            rows = parse_xlsx(blob)
            for row in rows[3:]:   # [title, header, totals, посты...]
                if len(row) <= max(COLS.values()):
                    continue
                post = {k: int(float(row[i] or 0)) for k, i in COLS.items()}
                post["title"] = row[2] if len(row) > 2 else ""
                post["type"] = typ
                posts.append(post)
                for k in totals:
                    totals[k] += post[k]

        res.metrics = {**totals, "posts_count": len(posts)}
        res.metrics["posts"] = posts
        res.source = "xlsx"
        if errors:
            res.error = "; ".join(errors)
        if type_failed:
            # Часть типов (article/brief) не собралась — метрики неполные,
            # даже если по другому типу данные есть и status остаётся "ok".
            res.needs_review = True

        # Подписчики — с публичной страницы канала (по спеке)
        from vision import parse_metric_value
        page.goto(config.CHANNELS["dzen"]["public_url"], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        sub_m = re.search(r"([\d\s.,]+\s*[KkКкMmМм]?)\s*подписчик",
                          page.inner_text("body"))
        res.metrics["subscribers"] = parse_metric_value(sub_m.group(1)) if sub_m else None

        if not posts and res.error:
            res.status = "failed"
        return res
    finally:
        page.close()
