# АКГ Agent-Mode (Playwright) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright-агент, который после одного ручного логина собирает маркетинг-статистику из кабинетов Дзен / ВК / Тенчат в локальные JSON (тест на кабинетах Alex'а).

**Architecture:** Персистентный browser-профиль (`profile/`) + оркестратор `collect.py` + модуль на канал (`channels/dzen.py`, `channels/vk.py`, `channels/tenchat.py`) + `vision.py` (скриншот → цифры через Claude API). Извлечение по убыванию точности: файловый экспорт (Дзен XLSX) → XHR-JSON → скриншот+vision. Селекторы — только для навигации.

**Tech Stack:** Python 3.11+ (Windows), Playwright (sync API, Chromium, headed), anthropic SDK (модель `claude-opus-4-8`, structured outputs), pytest. Без сторонних xlsx-библиотек — парсинг XLSX на stdlib (zipfile+ElementTree, порт из проверенного скрипта Маши).

Спека: `docs/superpowers/specs/2026-07-23-akg-agent-mode-design.md`.

## Global Constraints

- Рабочая директория репо: `c:\Users\Alex\Documents\ai-work\akg\agent-mode\` — все пути ниже относительно неё.
- Windows: venv-питон вызывается как `.venv\Scripts\python`, pytest как `.venv\Scripts\python -m pytest`.
- `profile/` и `out/` в .gitignore (уже настроено) — тесты и код не должны требовать их наличия в git.
- Данные НИКУДА не отправляются, кроме Claude API (скриншоты для распознавания). Поле `webhook_url` в конфиге существует, но `None`.
- Период по умолчанию: последняя завершённая ISO-неделя; override `--week 2026-W30`.
- Тестовые кабинеты: Дзен `https://dzen.ru/id/69a6a56804c3ba5d0aadf101`, ВК `https://vk.ru/nppsatek`, Тенчат `https://tenchat.ru/2418763`.
- Vision: модель `claude-opus-4-8`, ключ через стандартное разрешение SDK (`ANTHROPIC_API_KEY` / `ant auth` профиль). Сомнительные распознавания → `needs_review: true`, не тихая запись.
- Браузер всегда headed (`headless=False`) — антибот + наблюдаемость.
- Задача 3 (разведка) — интерактивная, выполняется в основной сессии с Alex'ом через Playwright MCP, НЕ субагентом.

---

### Task 1: Каркас — период, конфиг, browser-хелпер, collect.py --login

**Files:**
- Create: `requirements.txt`, `config.py`, `core/period.py`, `core/browser.py`, `core/result.py`, `collect.py`, `channels/__init__.py`, `core/__init__.py`
- Test: `tests/test_period.py`, `tests/test_result.py`

**Interfaces:**
- Produces: `period.last_completed_week() -> tuple[str, date, date]` (напр. `("2026-W29", date(2026,7,13), date(2026,7,19))`); `period.parse_week("2026-W30") -> tuple[str, date, date]`
- Produces: `browser.open_profile(headless=False) -> BrowserContext` (persistent context на `profile/`)
- Produces: `result.ChannelResult` dataclass + `result.write_result(res, out_dir) -> Path`; статусы `"ok" | "auth_required" | "failed"`
- Produces: CLI `collect.py --login | --channels dzen,vk,tenchat | --all [--week 2026-W30]`

- [ ] **Step 1: Окружение**

```powershell
cd c:\Users\Alex\Documents\ai-work\akg\agent-mode
python -m venv .venv
.venv\Scripts\python -m pip install playwright anthropic pytest
.venv\Scripts\python -m playwright install chromium
```

Создать `requirements.txt`:

```
playwright
anthropic
pytest
```

- [ ] **Step 2: Написать падающие тесты периода**

`tests/test_period.py`:

```python
from datetime import date
from core.period import last_completed_week, parse_week


def test_parse_week():
    label, start, end = parse_week("2026-W29")
    assert label == "2026-W29"
    assert start == date(2026, 7, 13)   # понедельник
    assert end == date(2026, 7, 19)     # воскресенье


def test_last_completed_week_mid_week():
    # среда 2026-07-22 -> последняя завершённая неделя W29 (13-19 июля)
    label, start, end = last_completed_week(today=date(2026, 7, 22))
    assert label == "2026-W29"
    assert (start, end) == (date(2026, 7, 13), date(2026, 7, 19))


def test_last_completed_week_on_monday():
    # понедельник 2026-07-20 -> завершилась W29
    label, _, _ = last_completed_week(today=date(2026, 7, 20))
    assert label == "2026-W29"
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают**

Run: `.venv\Scripts\python -m pytest tests/test_period.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'core'`

- [ ] **Step 4: Реализовать `core/period.py`** (+ пустые `core/__init__.py`, `channels/__init__.py`)

```python
"""Расчёт отчётного периода (ISO-недели, как в клиентском пайплайне АКГ)."""
from datetime import date, timedelta


def parse_week(week_label: str) -> tuple[str, date, date]:
    """'2026-W29' -> (label, monday, sunday)."""
    year_s, week_s = week_label.split("-W")
    start = date.fromisocalendar(int(year_s), int(week_s), 1)
    return week_label, start, start + timedelta(days=6)


def last_completed_week(today: date | None = None) -> tuple[str, date, date]:
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    end = this_monday - timedelta(days=1)          # прошлое воскресенье
    start = end - timedelta(days=6)
    y, w, _ = start.isocalendar()
    return f"{y}-W{w:02d}", start, end
```

- [ ] **Step 5: Прогнать тесты периода**

Run: `.venv\Scripts\python -m pytest tests/test_period.py -v`
Expected: 3 passed

- [ ] **Step 6: Тест + реализация ChannelResult**

`tests/test_result.py`:

```python
import json
from pathlib import Path
from core.result import ChannelResult, write_result


def test_write_result(tmp_path: Path):
    res = ChannelResult(
        channel="vk", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19",
        metrics={"content_reach": 17600}, source="vision",
        screenshots=["vk_community.png"], status="ok",
    )
    p = write_result(res, tmp_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert p.name == "vk.json"
    assert data["metrics"]["content_reach"] == 17600
    assert data["needs_review"] is False
    assert data["collected_at"]  # проставлен
```

`core/result.py`:

```python
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


def write_result(res: ChannelResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not res.collected_at:
        res.collected_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    path = out_dir / f"{res.channel}.json"
    path.write_text(json.dumps(asdict(res), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

Run: `.venv\Scripts\python -m pytest tests/ -v` → Expected: all passed

- [ ] **Step 7: `config.py`, `core/browser.py`, `collect.py`**

`config.py`:

```python
from pathlib import Path

ROOT = Path(__file__).parent
PROFILE_DIR = ROOT / "profile"
OUT_DIR = ROOT / "out"

WEBHOOK_URL = None  # тестовая фаза: никуда не шлём

CHANNELS = {
    "dzen":    {"public_url": "https://dzen.ru/id/69a6a56804c3ba5d0aadf101"},
    "vk":      {"public_url": "https://vk.ru/nppsatek", "screen_name": "nppsatek"},
    "tenchat": {"public_url": "https://tenchat.ru/2418763"},
}

LOGIN_TABS = [
    "https://dzen.ru/profile/editor",
    "https://vk.ru/nppsatek",
    "https://tenchat.ru/auth",
]
```

`core/browser.py`:

```python
"""Единый персистентный Chromium-профиль. Все каналы работают в нём."""
from playwright.sync_api import sync_playwright, BrowserContext
from config import PROFILE_DIR


def open_profile(pw, headless: bool = False) -> BrowserContext:
    PROFILE_DIR.mkdir(exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1440, "height": 900},
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        args=["--disable-blink-features=AutomationControlled"],
    )
```

`collect.py`:

```python
"""Оркестратор агентского режима АКГ.

  python collect.py --login                  разовый ручной логин в кабинеты
  python collect.py --all                    все каналы за последнюю завершённую неделю
  python collect.py --channels vk,dzen --week 2026-W30
"""
import argparse
import sys
import traceback

from playwright.sync_api import sync_playwright

import config
from core.browser import open_profile
from core.period import last_completed_week, parse_week
from core.result import ChannelResult, write_result


def do_login() -> None:
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for url in config.LOGIN_TABS:
            ctx.new_page().goto(url)
        print("Залогиньтесь во всех вкладках, затем закройте окно браузера.")
        ctx.pages[0].wait_for_event("close", timeout=0)


def run_channel(name: str, ctx, week, start, end) -> ChannelResult:
    # импорт внутри: падение одного модуля не валит остальные
    if name == "dzen":
        from channels.dzen import collect as fn
    elif name == "vk":
        from channels.vk import collect as fn
    elif name == "tenchat":
        from channels.tenchat import collect as fn
    else:
        raise ValueError(f"unknown channel {name}")
    return fn(ctx, week=week, start=start, end=end,
              out_dir=config.OUT_DIR / week)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--channels", default="")
    ap.add_argument("--week", default=None, help="напр. 2026-W30")
    args = ap.parse_args()

    if args.login:
        do_login()
        return 0

    names = list(config.CHANNELS) if args.all else [
        c.strip() for c in args.channels.split(",") if c.strip()]
    if not names:
        ap.error("укажите --login, --all или --channels")

    week, start, end = parse_week(args.week) if args.week else last_completed_week()
    out_dir = config.OUT_DIR / week
    print(f"Период: {week} ({start} — {end})")

    summary = {}
    with sync_playwright() as pw:
        ctx = open_profile(pw)
        for name in names:
            try:
                res = run_channel(name, ctx, week, start, end)
            except Exception as e:                      # канал упал — фиксируем и едем дальше
                traceback.print_exc()
                res = ChannelResult(
                    channel=name, week=week,
                    period_from=start.isoformat(), period_to=end.isoformat(),
                    status="failed", error=f"{type(e).__name__}: {e}")
            write_result(res, out_dir)
            summary[name] = res.status
        ctx.close()

    print("\n=== Итог ===")
    for name, status in summary.items():
        print(f"  {name:8s} {status}")
    return 0 if all(s == "ok" for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Smoke-check CLI без каналов**

Run: `.venv\Scripts\python collect.py` → Expected: exit 2, сообщение argparse «укажите --login, --all или --channels»
Run: `.venv\Scripts\python -m pytest tests/ -v` → Expected: all passed

- [ ] **Step 9: Commit**

```powershell
git add -A
git commit -m "Каркас: период, ChannelResult, персистентный профиль, collect.py"
```

---

### Task 2: vision.py — нормализация чисел (TDD) + извлечение метрик со скриншота

**Files:**
- Create: `vision.py`
- Test: `tests/test_vision_parse.py`

**Interfaces:**
- Consumes: ничего из других задач (самостоятельный модуль)
- Produces: `vision.parse_metric_value(raw: str) -> int | None` — «17,6K»→17600, «16 000»→16000, «3.6K»→3600, «1,2M»→1200000, «504»→504, мусор→None
- Produces: `vision.extract_metrics(image_path: Path, expected: dict[str, str]) -> tuple[dict[str, int], bool]` — `expected` = {ключ: описание метрики на скриншоте}; возвращает (metrics, needs_review)

- [ ] **Step 1: Падающие тесты нормализации**

`tests/test_vision_parse.py`:

```python
import pytest
from vision import parse_metric_value


@pytest.mark.parametrize("raw,expected", [
    ("17,6K", 17600),
    ("17.6K", 17600),
    ("3,6К", 3600),          # кириллическая К
    ("16 000", 16000),
    ("16\u00a0000", 16000),  # неразрывный пробел
    ("504", 504),
    ("1,2M", 1200000),
    ("1,2М", 1200000),       # кириллическая М
    ("0", 0),
    ("—", None),
    ("", None),
    ("N/A", None),
])
def test_parse_metric_value(raw, expected):
    assert parse_metric_value(raw) == expected
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `.venv\Scripts\python -m pytest tests/test_vision_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vision'`

- [ ] **Step 3: Реализовать `vision.py`**

```python
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
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: all passed (extract_metrics юнитами не покрывается — проверится живым прогоном в Task 5)

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "vision.py: нормализация чисел + извлечение метрик со скриншота (Claude API)"
```

---

### Task 3: Разведка кабинетов (интерактивная, с Alex'ом) — НЕ для субагента

Выполняется в основной сессии Claude Code через Playwright MCP + руки Alex'а. Субагентам эту задачу не давать.

**Files:**
- Create: `docs/recon/dzen.md`, `docs/recon/vk.md`, `docs/recon/tenchat.md`

**Чек-лист разведки:**

- [ ] **Step 1: Логин.** Alex запускает `python collect.py --login` и логинится в Дзен, ВК, Тенчат; закрывает окно. Проверка: повторный запуск `--login` открывает кабинеты уже залогиненными.
- [ ] **Step 2: Дзен.** Через Playwright MCP (или руками с фиксацией URL): открыть Студию → Статистика публикаций; записать в `docs/recon/dzen.md`: точный URL страницы статистики (`/profile/editor/id/<publisher_id>/publications-stat`), publisher_id канала Alex'а, работает ли endpoint `editor-api/v2/publisher-publications-rich-stat-xls`, где на публичной странице канала число подписчиков (селектор/текст).
- [ ] **Step 3: ВК.** Открыть статистику сообщества nppsatek (админка → Статистика); записать в `docs/recon/vk.md`: URL статистики, точные названия вкладок (Сообщество/Посты/Видео/Канал — что реально есть у nppsatek), для каждой вкладки: где число «Охват контента»/«Просмотры», как выбирается период, и главное — список XHR-запросов с JSON-статистикой (Network): если JSON читаемый, зафиксировать URL-шаблон и структуру ответа.
- [ ] **Step 4: Тенчат.** Открыть свой профиль → найти статистику (или её отсутствие); записать в `docs/recon/tenchat.md`: URL, какие метрики вообще показываются, XHR или только DOM/скриншот.
- [ ] **Step 5: Commit** разведочных заметок: `git add docs/recon && git commit -m "Разведка кабинетов: Дзен, ВК, Тенчат"`

**Выход задачи:** три recon-файла. Task 4-6 читают их перед кодификацией и подставляют фактические URL/вкладки вместо предположений плана.

---

### Task 4: channels/dzen.py — XLSX из Студии

Поток известен из рабочего скрипта Маши (`~/AKG/dzen_snapshot.py` на 178.104.156.39; локальная копия логики — в этом плане). Отличие: вместо куки-файла используем живой браузер — заходим на страницу статистики, достаём csrf из HTML, скачиваем XLSX через `context.request` (шарит cookies профиля).

**Files:**
- Create: `channels/dzen.py`, `core/xlsx.py`
- Test: `tests/test_xlsx.py`

**Interfaces:**
- Consumes: `core.result.ChannelResult`, `config`, recon-файл `docs/recon/dzen.md` (publisher_id)
- Produces: `core.xlsx.parse_xlsx(blob: bytes) -> list[list[str]]`; `channels.dzen.collect(ctx, week, start, end, out_dir) -> ChannelResult`

- [ ] **Step 1: Падающий тест парсера XLSX**

`tests/test_xlsx.py` — собираем минимальный xlsx в памяти:

```python
import io
import zipfile
from core.xlsx import parse_xlsx

_CT = """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""
_SST = """<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
<si><t>Заголовок</t></si><si><t>Пост 1</t></si></sst>"""
_SHEET = """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c t="s"><v>0</v></c></row>
<row r="2"><c t="s"><v>1</v></c><c><v>42</v></c></row>
</sheetData></worksheet>"""


def _fake_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("xl/sharedStrings.xml", _SST)
        z.writestr("xl/worksheets/sheet1.xml", _SHEET)
    return buf.getvalue()


def test_parse_xlsx():
    rows = parse_xlsx(_fake_xlsx())
    assert rows[0] == ["Заголовок"]
    assert rows[1] == ["Пост 1", "42"]
```

Run: `.venv\Scripts\python -m pytest tests/test_xlsx.py -v` → Expected: FAIL (`No module named 'core.xlsx'`)

- [ ] **Step 2: `core/xlsx.py`** — порт stdlib-парсера из Машиного скрипта:

```python
"""Минимальный XLSX-ридер (порт из проверенного dzen_snapshot.py Маши)."""
import io
import zipfile
from xml.etree import ElementTree as ET

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parse_xlsx(blob: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        sst = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("s:si", NS):
                t = si.find(".//s:t", NS)
                sst.append(t.text if t is not None and t.text else "")
        sheet = next((n for n in z.namelist()
                      if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
        if not sheet:
            return []
        root = ET.fromstring(z.read(sheet))
        rows = []
        for r in root.findall(".//s:row", NS):
            cells = []
            for c in r.findall("s:c", NS):
                v = c.find("s:v", NS)
                if v is None or v.text is None:
                    cells.append("")
                elif c.get("t", "n") == "s":
                    cells.append(sst[int(v.text)])
                else:
                    cells.append(v.text)
            rows.append(cells)
        return rows
```

Run: `.venv\Scripts\python -m pytest tests/test_xlsx.py -v` → Expected: PASS

- [ ] **Step 3: `channels/dzen.py`**

Перед реализацией прочитать `docs/recon/dzen.md` и подставить publisher_id и фактический URL, если разведка показала отличия. Базовая реализация:

```python
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
    page = ctx.new_page()
    try:
        page.goto("https://dzen.ru/profile/editor", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "passport" in page.url or "/login" in page.url:
            res.status = "auth_required"
            res.error = "Сессия Дзена истекла — запустите collect.py --login"
            return res
        # publisher_id из URL редактора или из HTML
        html = page.content()
        m = re.search(r'"publisherId":"([a-f0-9]{24})"', html) or \
            re.search(r"/profile/editor/id/([a-f0-9]{24})", page.url + html)
        if not m:
            page.screenshot(path=str(out_dir / "dzen_fail.png"), full_page=True)
            res.status, res.error = "failed", "publisher_id не найден"
            res.screenshots.append("dzen_fail.png")
            return res
        pub = m.group(1)

        stat_url = (f"https://dzen.ru/profile/editor/id/{pub}/publications-stat"
                    f"?statType=publications&intervalType=custom"
                    f"&intervalStart={_ms(start)}&intervalEnd={_ms(end, True)}")
        page.goto(stat_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(out_dir / "dzen_stats.png"), full_page=True)
        res.screenshots.append("dzen_stats.png")

        csrf_m = re.search(r'"csrfToken":"([a-f0-9:]+)"', page.content())
        if not csrf_m:
            res.status, res.error = "failed", "csrfToken не найден (сессия?)"
            return res
        csrf = csrf_m.group(1)

        totals = {k: 0 for k in COLS}
        posts = []
        for typ in TYPES:
            url = (f"https://dzen.ru/editor-api/v2/publisher-publications-rich-stat-xls"
                   f"?intervalStart={_ms(start)}&intervalEnd={_ms(end, True)}"
                   f"&publisherId={pub}&type={typ}")
            r = ctx.request.get(url, headers={"X-Csrf-Token": csrf, "Referer": stat_url})
            if r.status != 200:
                res.error = f"xlsx[{typ}] HTTP {r.status}"
                continue
            blob = r.body()
            (out_dir / f"dzen_{typ}.xlsx").write_bytes(blob)
            rows = parse_xlsx(blob)
            for row in rows[3:]:   # [title, header, totals, посты...]
                if len(row) <= max(COLS.values()):
                    continue
                post = {k: int(row[i] or 0) for k, i in COLS.items()}
                post["title"] = row[2] if len(row) > 2 else ""
                post["type"] = typ
                posts.append(post)
                for k in totals:
                    totals[k] += post[k]

        res.metrics = {**totals, "posts_count": len(posts)}
        res.metrics["posts"] = posts
        res.source = "xlsx"

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
```

- [ ] **Step 4: Живой прогон Дзена**

Run: `.venv\Scripts\python collect.py --channels dzen`
Expected: `out/<week>/dzen.json` со status=ok (или с понятной ошибкой + скриншот, если поток отличился — тогда поправить по факту и повторить). Открыть JSON, сверить цифры глазами со Студией.

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "Дзен: XLSX-поток из Студии через персистентный профиль"
```

---

### Task 5: channels/vk.py — 4 вкладки статистики: скриншот+vision (XHR — если разведка дала читаемый JSON)

**Files:**
- Create: `channels/vk.py`

**Interfaces:**
- Consumes: `vision.extract_metrics`, `core.result.ChannelResult`, recon-файл `docs/recon/vk.md`
- Produces: `channels.vk.collect(ctx, week, start, end, out_dir) -> ChannelResult`; ключи метрик: `content_reach` (Сообщество), `posts_reach` (Посты), `video_views` (Видео), `channel_views` (Канал), `members` (участники)

- [ ] **Step 1: Прочитать `docs/recon/vk.md`.** Если разведка зафиксировала читаемый XHR-JSON — реализовать слушатель `page.on("response", ...)` по URL-шаблону из разведки и брать цифры из него (`source="xhr"`), скриншоты всё равно сохранять. Если нет — основной путь vision (код ниже). Названия/наличие вкладок взять из разведки (у nppsatek может не быть «Канала» — тогда метрика `None`, не ошибка).

- [ ] **Step 2: Реализовать `channels/vk.py`** (vision-путь; вкладки из recon подставить в TABS):

```python
"""ВК: вкладки статистики сообщества -> скриншот -> vision."""
from pathlib import Path

from core.result import ChannelResult
from vision import extract_metrics
import config

# (вкладка в UI, файл скрина, {ключ: что искать})  — сверить с docs/recon/vk.md
TABS = [
    ("Сообщество", "vk_community.png",
     {"content_reach": "Охват контента за период",
      "members": "Число участников/подписчиков сообщества"}),
    ("Посты", "vk_posts.png",
     {"posts_reach": "Суммарный охват/просмотры постов за период"}),
    ("Видео", "vk_video.png",
     {"video_views": "Просмотры видео за период"}),
    ("Канал", "vk_channel.png",
     {"channel_views": "Просмотры канала (VK Видео-канал) за период"}),
]


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="vk", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat(),
                        source="vision")
    out_dir.mkdir(parents=True, exist_ok=True)
    screen = config.CHANNELS["vk"]["screen_name"]
    page = ctx.new_page()
    try:
        page.goto(f"https://vk.com/{screen}?w=stats", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if "login" in page.url:
            res.status = "auth_required"
            res.error = "Сессия ВК истекла — collect.py --login"
            return res

        for tab_name, shot_name, expected in TABS:
            tab = page.get_by_text(tab_name, exact=True).first
            if tab.count() == 0:
                for key in expected:
                    res.metrics[key] = None
                continue
            tab.click()
            page.wait_for_timeout(3000)
            shot = out_dir / shot_name
            page.screenshot(path=str(shot), full_page=True)
            res.screenshots.append(shot_name)
            metrics, review = extract_metrics(shot, expected)
            res.metrics.update(metrics)
            res.needs_review = res.needs_review or review
        return res
    finally:
        page.close()
```

- [ ] **Step 3: Живой прогон ВК**

Run: `.venv\Scripts\python collect.py --channels vk`
Expected: `out/<week>/vk.json` + 2-4 скриншота; сверить извлечённые числа с самими скриншотами глазами. Расхождение → поправить промпт/ожидания в TABS, повторить.

- [ ] **Step 4: Commit**

```powershell
git add -A
git commit -m "ВК: сбор вкладок статистики через скриншот+vision"
```

---

### Task 6: channels/tenchat.py — по итогам разведки

**Files:**
- Create: `channels/tenchat.py`

**Interfaces:**
- Consumes: `vision.extract_metrics`, recon-файл `docs/recon/tenchat.md`
- Produces: `channels.tenchat.collect(ctx, week, start, end, out_dir) -> ChannelResult`

- [ ] **Step 1: Прочитать `docs/recon/tenchat.md`** — URL страницы статистики и состав метрик. Подставить в EXPECTED реально существующие метрики (из разведки), остальное не выдумывать.

- [ ] **Step 2: Реализовать** (та же форма, что vk.py, одна страница):

```python
"""Тенчат: страница статистики профиля -> скриншот -> vision."""
from pathlib import Path

from core.result import ChannelResult
from vision import extract_metrics
import config

STATS_URL = "https://tenchat.ru/profile/statistics"   # сверить с docs/recon/tenchat.md
EXPECTED = {                                           # заменить на метрики из разведки
    "views": "Просмотры профиля/публикаций за период",
    "subscribers": "Число подписчиков",
}


def collect(ctx, week, start, end, out_dir: Path) -> ChannelResult:
    res = ChannelResult(channel="tenchat", week=week,
                        period_from=start.isoformat(), period_to=end.isoformat(),
                        source="vision")
    out_dir.mkdir(parents=True, exist_ok=True)
    page = ctx.new_page()
    try:
        page.goto(STATS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        if "auth" in page.url or "login" in page.url:
            res.status = "auth_required"
            res.error = "Сессия Тенчата истекла — collect.py --login"
            return res
        shot = out_dir / "tenchat_stats.png"
        page.screenshot(path=str(shot), full_page=True)
        res.screenshots.append("tenchat_stats.png")
        res.metrics, res.needs_review = extract_metrics(shot, EXPECTED)
        return res
    finally:
        page.close()
```

- [ ] **Step 3: Живой прогон** — `.venv\Scripts\python collect.py --channels tenchat`, сверить глазами, поправить EXPECTED/URL по факту.

- [ ] **Step 4: Commit**

```powershell
git add -A
git commit -m "Тенчат: сбор статистики профиля через скриншот+vision"
```

---

### Task 7: Прогон-1 (все каналы) и критерий успеха

- [ ] **Step 1: Полный прогон**

Run: `.venv\Scripts\python collect.py --all`
Expected: три JSON в `out/<week>/`, статусы в итоговой сводке. Сверить каждый JSON с кабинетом глазами; расхождения чинить в соответствующем канале.

- [ ] **Step 2: Обновить README** — секцию «Запуск» привести к фактическим командам и добавить раздел «Что собирается» (список метрик по каналам).

- [ ] **Step 3: Commit**

```powershell
git add -A
git commit -m "Прогон-1: все каналы; актуализация README"
```

- [ ] **Step 4: Прогон-2 (через 1-2 дня, вручную Alex'ом или по напоминанию).** `python collect.py --all` без `--login`. Если все каналы ok без перелогина — критерий успеха теста выполнен, гипотеза «живой профиль лечит протухание» подтверждена. Зафиксировать вердикт в README (раздел «Статус»).
