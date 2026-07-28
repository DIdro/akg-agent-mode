"""Результат сбора по одному каналу + запись в out/<week>/."""
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ChannelResult:
    channel: str
    week: str
    period_from: str
    period_to: str
    metrics: dict = field(default_factory=dict)
    source: str = ""                    # xlsx | xhr | vision
    screenshots: list = field(default_factory=list)
    status: str = "ok"                  # ok | auth_required | failed
    needs_review: bool = False
    error: str | None = None
    collected_at: str = ""
    # registry-имена конкретного кабинета/сообщества, переопределяют
    # config.CHANNELS[...]["registry"] при маппинге в строки реестра:
    #   ВК — dict по вкладкам (сообщество/блог/видео), Дзен/Тенчат — строка.
    registry_override: dict | str | None = None
    # Метка для различения нескольких результатов одного канала (ВК: два
    # сообщества за один прогон) — идёт в имя файла out/ и в сводку. None —
    # один результат на канал (прежнее поведение).
    label: str | None = None


def write_result(res: ChannelResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not res.collected_at:
        res.collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    # Имя файла из label (если задан) — иначе несколько ВК-сообществ перетёрли бы
    # общий vk.json. Небезопасные для ФС символы → «_».
    stem = re.sub(r"[^\w.-]+", "_", res.label) if res.label else res.channel
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(asdict(res), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
