"""Результат сбора по одному каналу + запись в out/<week>/."""
import json
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
    # Для ВК: registry-имена выбранного аккаунта (--vk-account); переопределяет
    # config.CHANNELS["vk"]["registry"] при маппинге в строки реестра.
    registry_override: dict | None = None


def write_result(res: ChannelResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not res.collected_at:
        res.collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    path = out_dir / f"{res.channel}.json"
    path.write_text(json.dumps(asdict(res), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
