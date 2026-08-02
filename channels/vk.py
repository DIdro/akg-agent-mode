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

Вкладка «Канал» (VK Видео-канал) доступна не всем сообществам: у agcapital есть
(снимаем channel_views/channel_subs), у nppsatek нет — тогда метрики канала
остаются None (vision вернёт found=false), без падения.
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
        "members": ("Подписчики — число под заголовком «Подписчики» в нижнем ряду плиток. "
                    "Это НЕ ВСЕГО/УБЫЛЬ за период (изменение), может быть отрицательным, "
                    "например «-4» — верни ровно как на экране, со знаком минус, если он есть. "
                    "НЕ бери число с графика «Количество подписчиков»."),
    }),
    ("top_posts", "stat_board_general", "vk_posts.png", {
        "posts_reach": ("Охват — число под заголовком «Охват» на вкладке Посты → Общее "
                         "(это НЕ «Просмотры» — там отдельное число рядом)"),
    }),
    ("top_video", "stat_board_general", "vk_video.png", {
        "video_views": ("Просмотры — число под заголовком «Просмотры» на вкладке Видео → Общее "
                         "(это НЕ «Охват» — там отдельное число слева)"),
    }),
    # Вкладка «Канал» (VK Видео-канал) есть не у всех сообществ (у тестового
    # nppsatek её нет — тогда метрики просто останутся None). У agcapital есть.
    ("top_channel", "stat_board_general", "vk_channel.png", {
        "channel_views": ("Просмотры — число под заголовком «Просмотры» в верхнем ряду "
                           "на вкладке «Канал» → Общее (это НЕ «Подписчики» рядом)"),
        "channel_subs": ("Подписчики — число под заголовком «Подписчики» в верхнем ряду "
                          "на вкладке «Канал» → Общее. Это НЕ ВСЕГО/УБЫЛЬ за период, "
                          "может быть отрицательным — верни ровно как на экране, со знаком."),
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
    реально показано в шапке дашборда. Нормализуем дефис/en-dash И пробелы —
    ВК рисует «13.07 – 19.07» (с пробелами), wanted идёт без них."""
    if not actual:
        return False
    # \s+ вместо replace(" "): ВК отбивает даты неразрывными пробелами (\xa0),
    # обычный replace их не убирал — ложный «период не совпал» (прецедент W31)
    norm = lambda s: re.sub(r"\s+", "", s.replace("-", "–"))
    return norm(wanted) in norm(actual)


def _dashboard_load_failed(page) -> bool:
    """ВК рендерит баннер «Не удалось загрузить данные» — но, как показала живая
    проверка, это ПРОМЕЖУТОЧНОЕ состояние загрузки: он висит первые несколько
    секунд и сменяется данными к ~8с. Поэтому баннер сам по себе НЕ повод
    сдаваться — трактуем его как отказ только если данные не пришли и после
    всех ретраёв ожидания (см. _shoot_and_extract)."""
    try:
        return page.get_by_text("Не удалось загрузить данные", exact=False).count() > 0
    except Exception:
        return False


def _shoot_and_extract(page, shot_path: Path, expected: dict) -> tuple[dict, bool, bool]:
    """Скриншот + vision с ретраями: дашборд ВК на старте показывает баннер
    «Не удалось загрузить данные», а сами цифры дорисовывает к ~8с (живая
    проверка). Поэтому НЕ бросаем на баннере — проходим все ступени ожидания,
    пока не увидим метрики. load_failed=True только если после последней
    попытки метрик по-прежнему нет и баннер всё ещё висит.
    Третий элемент результата — сработал ли (устойчивый) баннер отказа ВК."""
    metrics, needs_review = {k: None for k in expected}, True
    waits = (4000, 5000, 6000, 8000)
    for i, wait_ms in enumerate(waits):
        page.wait_for_timeout(wait_ms)
        page.screenshot(path=str(shot_path), full_page=True)
        metrics, needs_review = extract_metrics(shot_path, expected)
        if any(v is not None for v in metrics.values()):
            return metrics, needs_review, False
        # данных пока нет — просто ждём ещё; баннер на ранних итерациях
        # ожидаем и игнорируем (он транзиентный)
    # все ступени пройдены, метрик так и нет — теперь баннер значим
    return metrics, needs_review, _dashboard_load_failed(page)


# NB: раньше здесь стоял request-фильтр (page.route), блокировавший «шумные»
# запросы ВК (мессенджер/стикеры/аватарки) — задумывался как защита от
# собственного rate-limit ВК. Живая проверка 2026-07-24 показала обратное:
# именно он обрывал инициализацию SPA-дашборда, из-за чего ВК стабильно
# отдавал баннер «Не удалось загрузить данные» (ложно похожий на rate-limit).
# Без фильтра дашборд грузится штатно за ~8с. Фильтр удалён.


def _set_period(page, start, end) -> bool:
    """Выставить период дашборда = [start, end] через датапикер.

    Датапикер (разведка 2026-07-25): клик по тексту периода в шапке → панель с
    двумя календарями, полем диапазона и кнопкой «Показать». Пресеты («Прошлая
    неделя») НЕнадёжны — ВК считает «сегодня» по своему ТЗ и даёт не ту неделю;
    текстовый ввод не активирует «Показать». Рабочий путь — клик по дню начала и
    дню конца в календаре (левый календарь = текущий месяц; для недавней недели
    оба дня видны). «Показать» активируется только при валидном диапазоне.
    Возвращает True, если удалось нажать «Показать»; вызывающий сверяет
    фактический период (_period_matches) и при несовпадении помечает needs_review."""
    try:
        cur = _read_period_text(page)
        if not cur:
            return False
        page.get_by_text(cur, exact=False).first.click(timeout=5000)
        page.wait_for_timeout(1500)
        # Клик по дню начала и дню конца (.first = левый/текущий календарь в DOM).
        page.get_by_text(str(start.day), exact=True).first.click(timeout=3000)
        page.wait_for_timeout(400)
        # Неделя через границу месяца (напр. 27.07–02.08): день конца лежит в
        # ПРАВОМ календаре (следующий месяц) — .first попал бы в тот же месяц,
        # что и начало, и ВК прочитал бы клики как диапазон «02.07–27.07»
        # (прецедент W31). Берём последнее совпадение в DOM — ячейку правого
        # календаря; внутри одного месяца — прежний .first.
        end_days = page.get_by_text(str(end.day), exact=True)
        (end_days.last if end.month != start.month else end_days.first).click(timeout=3000)
        page.wait_for_timeout(600)
        show = page.get_by_text("Показать", exact=True).first
        clicked = False
        if show.count() and show.is_enabled():
            show.click(timeout=3000)
            page.wait_for_timeout(3000)
            clicked = True
        # Панель датапикера может остаться открытой (диапазон ВК применяет уже
        # по кликам на датах, а клик «Показать» иногда не долетает) — тогда она
        # перекрывает плитки метрик на скриншоте и vision их не видит
        # (прецедент W31). Esc только прячет попап, применённый период не
        # откатывает — закрываем безусловно.
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        return clicked
    except Exception:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
        except Exception:
            pass
        return False


def collect_all(ctx, week, start, end, out_dir: Path, only=None) -> list[ChannelResult]:
    """Собрать ВСЕ сообщества клиента за один заход (один ВК-аккаунт админит
    несколько сообществ — перелогин не нужен). Возвращает по ChannelResult на
    сообщество. Конфиг: CHANNELS["vk"]["communities"] = {key: {screen, registry}}.
    only=<key> — собрать только одно сообщество (напр. перезапуск упавшего).
    Без communities — прежнее одно-сообщественное поведение (screen_name)."""
    comms = config.CHANNELS["vk"].get("communities")
    if comms:
        items = [(k, c) for k, c in comms.items() if only in (None, k)]
        return [_collect_one(ctx, week, start, end, out_dir,
                             screen=c["screen"], registry_override=c["registry"],
                             label=f"vk:{c['screen']}", shot_prefix=c["screen"])
                for _, c in items]
    return [_collect_one(ctx, week, start, end, out_dir,
                         screen=config.CHANNELS["vk"]["screen_name"])]


def _collect_one(ctx, week, start, end, out_dir: Path, screen: str,
                 registry_override=None, label=None, shot_prefix="vk") -> ChannelResult:
    res = ChannelResult(channel="vk", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat(),
                        source="vision", registry_override=registry_override, label=label)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://vk.ru/groups/dashboard/@{screen}"
    page = ctx.new_page()
    warnings = []
    try:
        # «Просмотры/подписчики канала» теперь снимаются вкладкой «Канал»
        # (top_channel) в цикле TABS ниже; у сообществ без этой вкладки метрики
        # просто останутся None (vision вернёт found=false).

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
            # Выставляем точную отчётную неделю через датапикер (пресет
            # «Прошлая неделя» покрывает дефолтный запуск). Успех сверяем ниже
            # по actual_period; при несовпадении — needs_review + пометка.
            _set_period(page, start, end)
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
                # Префикс по сообществу: два сообщества за один прогон не должны
                # перетирать vk_community.png/… друг друга ("vk_community.png" →
                # "<screen>_community.png"; для одиночного сбора остаётся "vk_…").
                shot_file = f"{shot_prefix}_{shot_name.split('_', 1)[1]}"
                shot = out_dir / shot_file
                metrics, review, load_failed = _shoot_and_extract(page, shot, expected)
                res.screenshots.append(shot_file)
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
