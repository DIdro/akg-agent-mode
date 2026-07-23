"""Извлечение цифр со скриншотов статистики через Claude API (vision).

parse_metric_value — детерминированная нормализация («17,6K» -> 17600).
extract_metrics — скриншот + список ожидаемых метрик -> словарь значений.
"""
import base64
import json
import re
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-8"

_MULT = {"k": 1_000, "к": 1_000, "m": 1_000_000, "м": 1_000_000}


def parse_metric_value(raw: str) -> int | None:
    s = (raw or "").strip().replace("\u00a0", " ")
    if not s:
        return None
    m = re.fullmatch(r"([\d\s]+(?:[.,]\d+)?)\s*([KkКкMmМм]?)", s)
    if not m:
        return None
    num = float(m.group(1).replace(" ", "").replace(",", "."))
    mult = _MULT.get(m.group(2).lower(), 1)
    return int(round(num * mult))


_SCHEMA = {
    "type": "object",
    "properties": {
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "raw_value": {"type": "string"},
                    "found": {"type": "boolean"},
                },
                "required": ["key", "raw_value", "found"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["metrics"],
    "additionalProperties": False,
}


def extract_metrics(image_path: Path, expected: dict[str, str]) -> tuple[dict, bool]:
    """expected: {'content_reach': 'Охват контента за период', ...}
    Возвращает ({key: int|None}, needs_review)."""
    client = anthropic.Anthropic()
    img_b64 = base64.standard_b64encode(image_path.read_bytes()).decode()
    media = "image/png" if image_path.suffix == ".png" else "image/jpeg"
    ask = "\n".join(f"- key={k}: {v}" for k, v in expected.items())

    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media, "data": img_b64}},
                {"type": "text", "text": (
                    "На скриншоте — вкладка статистики соцсети. Найди значения метрик:\n"
                    f"{ask}\n"
                    "Верни raw_value РОВНО как на экране (например «17,6K», «16 000»). "
                    "Если метрики на скриншоте нет — found=false, raw_value=''. "
                    "Не пересчитывай и не округляй.")},
            ],
        }],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    metrics: dict = {}
    needs_review = False
    got = {m["key"]: m for m in data["metrics"]}
    for key in expected:
        item = got.get(key)
        if not item or not item["found"]:
            metrics[key] = None
            needs_review = True
            continue
        val = parse_metric_value(item["raw_value"])
        metrics[key] = val
        if val is None:
            needs_review = True
    return metrics, needs_review
