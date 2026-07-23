"""Тенчат: панель «Статистика профиля» (клик стрелки) -> XHR account/stats / vision.

Разведка (docs/recon/tenchat.md, живая проверка 2026-07-23): статистика — НЕ
отдельный URL (в отличие от догадки в брифе `/profile/statistics`), а панель
на собственном профиле https://tenchat.ru/2418763. Справа от кнопки
«Редактировать профиль» — маленькая (~40x40) кнопка-стрелка ↗ без текста
(≈ x1296 y340 при viewport 1440x900). Клик открывает панель «Статистика
профиля / За последние 7 дней» с метриками Охват записей / Просмотры /
Подписчики; URL при этом не меняется (модалка/панель, а не переход).

Тот же клик бьёт XHR GET .../gostinder/api/web/auth/account/stats (200,
JSON) — это первичный источник (надёжнее OCR по скриншоту). Есть похожий
`user/lead/stats` — это CRM-лиды, НЕ контентная статистика, игнорируем.

Период у Тенчата на этой панели фиксирован «последние 7 дней» и кликами
даты не выставляется (в отличие от произвольной отчётной недели) —
не блокируем сбор, а фиксируем это в res.error/needs_review, как и для
фрагильного пикера периода ВК (см. channels/vk.py).
"""
from pathlib import Path

from core.result import ChannelResult
from vision import extract_metrics
import config

STATS_XHR_SUFFIX = "/gostinder/api/web/auth/account/stats"
# Координата-фолбэк для кнопки-стрелки статистики на собственном профиле —
# используется, когда устойчивый локатор рядом с «Редактировать профиль»
# не находится (см. docs/recon/tenchat.md: «селектора-текста нет»).
FALLBACK_BUTTON_COORDS = (1296, 340)

EXPECTED = {
    "reach": "Охват записей за последние 7 дней",
    "views": "Просмотры за последние 7 дней",
    "subscribers": "Подписчики",
}


def map_stats_json(data: dict) -> dict:
    """Чистая функция: сырой JSON account/stats -> {reach, views, subscribers}.

    Реальная форма ответа (живой прогон 2026-07-23, профиль без записей):
        {"postViewCount": 0, "accountViewCount": 0, "subscribeCount": 0}
    Порядок и имена полей совпали с порядком/смыслом чисел в панели «Статистика
    профиля»: postViewCount — «Охват записей» (view-метрика самих записей/постов),
    accountViewCount — «Просмотры» (просмотры аккаунта в целом), subscribeCount —
    «Подписчики». Профиль пустой (0 записей) — все три числа = 0, так что это
    отображение подтверждено лишь по названиям/порядку полей, не по значениям;
    остаётся перепроверить на профиле с реальной активностью (см. task-6-report.md).
    Держим также несколько запасных вариантов имён на случай другой версии API."""

    def pick(*names):
        for n in names:
            if n in data and data[n] is not None:
                return data[n]
        return None

    return {
        "reach": pick("postViewCount", "reach", "recordsReach", "records_reach", "postsReach"),
        "views": pick("accountViewCount", "views", "viewsCount", "views_count"),
        "subscribers": pick(
            "subscribeCount", "subscribers", "subscribersCount", "subscribers_count", "followers"),
    }


def _click_stats_button(page) -> bool:
    """Ищет кнопку-стрелку статистики устойчивым локатором (иконка-кнопка без
    текста рядом с «Редактировать профиль»); при неудаче — клик по
    координате-фолбэку. Возвращает True, если клик состоялся."""
    try:
        edit_btn = page.get_by_text("Редактировать профиль", exact=False).first
        edit_btn.wait_for(timeout=5000)
        box = edit_btn.bounding_box()
        if box:
            x = box["x"] + box["width"] + 24
            y = box["y"] + box["height"] / 2
            page.mouse.click(x, y)
            return True
    except Exception:
        pass
    try:
        page.mouse.click(*FALLBACK_BUTTON_COORDS)
        return True
    except Exception:
        return False


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="tenchat", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat(),
                        source="vision")
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_url = config.CHANNELS["tenchat"]["public_url"]
    page = ctx.new_page()
    captured: dict = {}

    def _on_response(response):
        if STATS_XHR_SUFFIX in response.url and response.request.method == "GET":
            try:
                captured["json"] = response.json()
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        page.goto(profile_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "auth" in page.url or "login" in page.url:
            res.status = "auth_required"
            res.error = "Сессия Тенчата истекла — запустите collect.py --login"
            return res

        if not _click_stats_button(page):
            shot = out_dir / "tenchat_profile.png"
            page.screenshot(path=str(shot), full_page=True)
            res.screenshots.append("tenchat_profile.png")
            res.status = "failed"
            res.error = "Кнопка-стрелка статистики профиля не найдена"
            return res

        page.wait_for_timeout(2500)
        shot = out_dir / "tenchat_stats.png"
        page.screenshot(path=str(shot))
        res.screenshots.append("tenchat_stats.png")

        warnings = []
        if "json" in captured:
            res.metrics = map_stats_json(captured["json"])
            res.source = "xhr"
            if all(v is None for v in res.metrics.values()):
                # JSON пойман, но ни одно ожидаемое поле не распозналось
                # (другая версия API/имена полей) — не сдаёмся сразу в failed,
                # пробуем снять те же метрики через vision по уже сделанному
                # скриншоту панели.
                warnings.append(
                    f"account/stats JSON не содержал ожидаемых ключей: {captured['json']!r}"
                    " — фолбэк на vision")
                res.metrics, needs_review = extract_metrics(shot, EXPECTED)
                res.source = "vision"
                if needs_review:
                    warnings.append("vision тоже не распознал все метрики")
            elif any(v is None for v in res.metrics.values()):
                warnings.append(
                    f"account/stats JSON не содержал ожидаемых ключей: {captured['json']!r}")
        else:
            res.metrics, needs_review = extract_metrics(shot, EXPECTED)
            res.source = "vision"
            if needs_review:
                warnings.append("account/stats XHR не пойман — снято через vision, не все метрики")

        # Тенчат фиксирует эту панель на «последние 7 дней», без произвольного
        # периода — не совпадает с запрошенной отчётной неделей.
        warnings.append(
            "панель статистики Тенчата показывает фиксированный период "
            "«последние 7 дней», а не запрошенную неделю "
            f"{start.isoformat()}—{end.isoformat()}")
        res.needs_review = True
        res.error = "; ".join(warnings)

        if all(v is None for v in res.metrics.values()):
            res.status = "failed"
        return res
    finally:
        page.close()
