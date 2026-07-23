"""ВК: вкладки статистики сообщества (дашборд vk.ru/groups/dashboard) -> скриншот -> vision.

Разведка (docs/recon/vk.md, живая проверка 2026-07-23) заменяет старый URL
`vk.com/{screen}?w=stats` (заглушка) на актуальный дашборд:
    https://vk.ru/groups/dashboard/@{screen}?sectionId=<section>&subsectionId=<subsection>
Вкладки переключаются сменой query-параметров URL, а не кликом по тексту вкладки —
надёжнее (не зависит от локали/раскладки текста).

Период в шапке дашборда (календарь) НЕ выставляем кликами: живая проверка
показала, что кнопка периода может подолгу (>30с) оставаться disabled, пока
дашборд догружает данные — риск зависания коллектора ради второстепенной
удобности. Вместо этого читаем период, который реально показан на экране
(по умолчанию — «последние 7 дней»), и если он не совпадает с запрошенной
неделей — фиксируем это в res.error/needs_review, не блокируя сбор
(см. бриф задачи 5: фрагильный пикер периода — не блокер).

У nppsatek нет вкладки «Канал» (VK Видео-канал доступен не всем сообществам) —
поэтому channel_views всегда None, без ошибки и без скриншота.
"""
import re
from pathlib import Path

from core.result import ChannelResult
from vision import extract_metrics
import config

PERIOD_RE = re.compile(r"(\d{2}\.\d{2})\s*[–-]\s*(\d{2}\.\d{2})")

# (sectionId, subsectionId, файл скрина, {ключ метрики: что искать на экране})
# Подписи сверены вживую на дашборде nppsatek (docs/recon/vk.md).
TABS = [
    ("top_community", "stat_board_general", "vk_community.png", {
        "visits": "Посещения — число под заголовком «Посещения» (вкладка Сообщество → Общее)",
        "content_views": "Просмотры контента — число под заголовком «Просмотры контента»",
        "content_reach": "Охват контента — число под заголовком «Охват контента»",
        "members": "Подписчики — число под заголовком «Подписчики» (нижний ряд метрик)",
    }),
    ("top_posts", "stat_board_general", "vk_posts.png", {
        "posts_reach": ("Охват — число под заголовком «Охват» на вкладке Посты → Общее "
                         "(это НЕ «Просмотры» — там отдельное число рядом)"),
    }),
    ("top_video", "stat_board_general", "vk_video.png", {
        "video_views": ("Просмотры — число под заголовком «Просмотры» на вкладке Видео → Общее "
                         "(это НЕ «Охват» — там отдельное число слева)"),
    }),
]


def _read_period_text(page) -> str:
    """Best-effort: текст периода, реально показанный в шапке дашборда."""
    try:
        return page.get_by_text(PERIOD_RE).first.inner_text(timeout=5000)
    except Exception:
        return ""


def _period_matches(wanted: str, actual: str) -> bool:
    """Совпадает ли запрошенный период (например «13.07–19.07») с тем, что
    реально показано в шапке дашборда (нормализуем дефис/en-dash)."""
    if not actual:
        return False
    return wanted in actual.replace("-", "–")


def _dashboard_load_failed(page) -> bool:
    """ВК иногда рендерит явный баннер отказа вместо данных (перегрузка/rate-limit
    на его стороне) — отличаем это от "просто ещё грузится", чтобы не врать в
    res.error про несовпадение периода, когда на деле данные не пришли вовсе."""
    try:
        return page.get_by_text("Не удалось загрузить данные", exact=False).count() > 0
    except Exception:
        return False


def _shoot_and_extract(page, shot_path: Path, expected: dict) -> tuple[dict, bool, bool]:
    """Скриншот + vision с ретраями: время прогрузки дашборда ВК ощутимо
    "плавает" от вкладки к вкладке (иногда «Сообщество» с 7 графиками готова
    за 3с, иногда «Посты» ещё крутит спиннер и через 8с) — вместо гадания с
    одним фиксированным sleep пробуем несколько раз с растущей паузой.
    Третий элемент — сработал ли явный баннер отказа ВК."""
    metrics, needs_review = {k: None for k in expected}, True
    load_failed = False
    for wait_ms in (3000, 5000, 8000):
        page.wait_for_timeout(wait_ms)
        page.screenshot(path=str(shot_path), full_page=True)
        metrics, needs_review = extract_metrics(shot_path, expected)
        if any(v is not None for v in metrics.values()):
            load_failed = False
            break
        load_failed = _dashboard_load_failed(page)
        if load_failed:
            break  # баннер отказа не исчезнет от ожидания — не жжём вызовы vision зря
    return metrics, needs_review, load_failed


# VK-клиент на каждой полной загрузке дашборда параллельно дёргает десятки
# несвязанных со статистикой ручек (мессенджер, стикеры, аватарки, реклама,
# подсказки) — это легко упирается в собственный rate-limit ВК
# ("Too many requests per second") и мешает как раз нужному getOwnerStats.
# Блокируем этот шум на уровне запросов страницы — статистике он не нужен.
#
# ВАЖНО: statsDashboard.* (getOwnerStats/getDashboardSections/getBootstrapData)
# и batch.call НИКОГДА не блокируются — это либо сама нужная статистика, либо
# может её нести (батч рискованно фильтровать по имени метода). Список ниже —
# только те методы, что реально видели в разведке как чистый шум.
_NOISE_PATTERNS = (
    "method/stickers.", "method/messages.", "method/vmoji.",
    "method/queue.subscribe", "method/store.hasNewItems", "queuev4",
)


def _is_noise(url: str) -> bool:
    """Чистая проверка: блокировать ли запрос как несвязанный со статистикой шум.
    statsDashboard.* и batch.call — защищены (никогда не блокируются), т.к. это
    сама нужная статистика или может её нести."""
    if "statsDashboard" in url:
        return False
    if "batch.call" in url:
        return False
    return any(p in url for p in _NOISE_PATTERNS)


def _block_noise(route):
    if _is_noise(route.request.url):
        route.abort()
    else:
        route.continue_()


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="vk", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat(),
                        source="vision")
    out_dir.mkdir(parents=True, exist_ok=True)
    screen = config.CHANNELS["vk"]["screen_name"]
    base = f"https://vk.ru/groups/dashboard/@{screen}"
    page = ctx.new_page()
    page.route("https://web.api.vk.ru/**", _block_noise)
    warnings = []
    try:
        # У nppsatek нет вкладки «Канал» (VK Видео-канал) — фиксируем None,
        # без похода на несуществующую вкладку.
        res.metrics["channel_views"] = None

        actual_period = ""
        try:
            page.goto(f"{base}?sectionId=top_community&subsectionId=stat_board_general",
                       wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if "groups/dashboard" not in page.url:
                # Реальный редирект с дашборда (не таймаут) — это истёкшая
                # сессия, а не rate-limit; тут действительно нечего собирать.
                res.status = "auth_required"
                res.error = "Сессия ВК истекла — запустите collect.py --login"
                return res
            actual_period = _read_period_text(page)
        except Exception as e:
            # Бутстрап-навигация упала (таймаут под rate-limit и т.п.), но это
            # НЕ признак истёкшей сессии — не валим весь канал, каждая вкладка
            # ниже сама делает свою навигацию и может восстановиться.
            warnings.append(f"bootstrap goto: {type(e).__name__}: {e}")
            res.needs_review = True

        for section_id, subsection_id, shot_name, expected in TABS:
            try:
                url = f"{base}?sectionId={section_id}&subsectionId={subsection_id}"
                if page.url != url:
                    # Полная навигация ВК каждый раз перезапускает тяжёлый бутстрап
                    # SPA (мессенджер/стикеры/аватарки — десятки параллельных
                    # вызовов), который сам легко упирается в rate-limit ВК
                    # ("Too many requests per second") и мешает getOwnerStats.
                    # Не дёргаем повторно ту же вкладку, где уже стоим
                    # (первая в TABS совпадает со стартовой страницей).
                    page.goto(url, wait_until="domcontentloaded")
                shot = out_dir / shot_name
                metrics, review, load_failed = _shoot_and_extract(page, shot, expected)
                res.screenshots.append(shot_name)
                res.metrics.update(metrics)
                res.needs_review = res.needs_review or review
                if load_failed:
                    warnings.append(
                        f"{section_id}/{subsection_id}: дашборд ВК показал "
                        f"«Не удалось загрузить данные» (перегрузка/rate-limit на стороне ВК) — "
                        f"метрики этой вкладки не сняты, повторите сбор позже")
            except Exception as e:
                warnings.append(f"{section_id}/{subsection_id}: {type(e).__name__}: {e}")
                for key in expected:
                    res.metrics.setdefault(key, None)
                res.needs_review = True

        wanted = f"{start:%d.%m}–{end:%d.%m}"
        if not _period_matches(wanted, actual_period):
            warnings.append(
                f"дашборд показывает период по умолчанию «{actual_period or '?'}», "
                f"а не запрошенную неделю {wanted} — календарь ВК не выставляли "
                f"(кнопка периода ненадёжно долго остаётся disabled на живом дашборде)")
            res.needs_review = True

        if warnings:
            res.error = "; ".join(warnings)

        # Полная потеря данных (все метрики, кроме заведомо-None channel_views,
        # так и остались None) — это не "частично деградировавший, но живой"
        # сбор, а провал; см. прецедент channels/dzen.py.
        collected_keys = [k for k in res.metrics if k != "channel_views"]
        if collected_keys and all(res.metrics[k] is None for k in collected_keys) and res.error:
            res.status = "failed"
        return res
    finally:
        page.close()
