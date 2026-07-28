"""Маппер ChannelResult -> строки формата «Реестр_факта».

Колонки, что пишет агент: week_start (A, DD.MM.YYYY), channel (F, дословно),
reach (K, Охват), subs_social (M, прирост подписчиков), comment (W).
ВК разворачивается в несколько строк (сообщество/блог/видео). Каналы не в
статусе ok пропускаются. Тенчат несёт пометку периода (платформа даёт только 7д).
"""
import config


def _ddmmyyyy(d) -> str:
    return f"{d:%d.%m.%Y}"


def _dzen_row(res, reg, week, ws) -> dict:
    m = res.metrics
    subs = m.get("subs")
    return {
        "week_start": ws, "channel": reg, "week": week,
        "reach": int(m.get("shows") or 0),
        "subs_social": None if subs is None else int(subs),
        "comment": (f"{m.get('posts_count', 0)} публ.; "
                    f"подписчиков всего {m.get('subscribers', '—')}; период {week}"),
        "source": "agent-mode", "_needs_review": bool(res.needs_review),
    }


def _vk_rows(res, reg: dict, week, ws) -> list[dict]:
    m = res.metrics
    # (ключ метрики охвата, ключ канала в reg, ключ подписчиков|None)
    # Подписчики — прирост/убыль за период (как у Дзена/Тенчата). Сообщество и
    # видео-канал несут СВОИ дельты отдельными строками: members / channel_subs.
    specs = [
        ("content_reach", "community", "members"),
        ("channel_views", "channel",   "channel_subs"),
        ("video_views",   "video",     None),
    ]
    rows = []
    for reach_key, reg_key, subs_key in specs:
        if reg_key not in reg:      # у аккаунта нет такого канала (напр. ЛБ — только community)
            continue
        reach = m.get(reach_key)
        if reach is None:
            continue
        row = {
            "week_start": ws, "channel": reg[reg_key], "week": week,
            "reach": int(reach),
            "subs_social": None if subs_key is None or m.get(subs_key) is None
                           else int(m[subs_key]),
            "comment": (f"просмотры контента {m.get('content_views', '—')}; период {week}"
                        if reg_key == "community" else f"период {week}"),
            "source": "agent-mode", "_needs_review": bool(res.needs_review),
        }
        rows.append(row)
    return rows


def _tenchat_row(res, reg, week, ws) -> dict:
    m = res.metrics
    subs = m.get("subscribers")
    # период у Тенчата фиксирован платформой — честная пометка
    end = res.period_to.replace("-", ".") if res.period_to else "?"
    return {
        "week_start": ws, "channel": reg, "week": week,
        "reach": int(m.get("reach") or 0),
        "subs_social": None if subs is None else int(subs),
        "comment": (f"просмотры {m.get('views', '—')}; "
                    f"⚠ период: последние 7 дней на {end} (платформа не даёт выбор)"),
        "source": "agent-mode", "_needs_review": True,
    }


def to_registry_rows(results, week: str, start, end) -> list[dict]:
    ws = _ddmmyyyy(start)
    out = []
    for res in results:
        if res.status != "ok":
            continue
        # Для ВК с несколькими аккаунтами имена берутся из выбранного аккаунта
        # (registry_override), иначе — из общего config.
        reg = getattr(res, "registry_override", None) \
            or config.CHANNELS.get(res.channel, {}).get("registry")
        if reg is None:
            continue
        if res.channel == "dzen":
            out.append(_dzen_row(res, reg, week, ws))
        elif res.channel == "vk":
            out.extend(_vk_rows(res, reg, week, ws))
        elif res.channel == "tenchat":
            out.append(_tenchat_row(res, reg, week, ws))
    return out
