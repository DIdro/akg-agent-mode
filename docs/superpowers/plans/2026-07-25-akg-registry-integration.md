# Интеграция агента с Реестр_факта — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Данные агента (Дзен/ВК-органика/Тенчат) автоматически попадают в лист «Реестр_факта» → PDF, замещая серверный сбор Pull+map по этим каналам.

**Architecture:** Агент маппит `ChannelResult` в строки формата реестра и POST-ит на новый native-эндпоинт; нода кладёт в `staticData.agent_rows`; Pull+map подмешивает их по неделя+канал вместо своего сбора. Две части: агентская (наш репо, Tasks 1–4) и серверная (akg-native Маши, Tasks 5–7).

**Tech Stack:** Python 3.11 + Playwright (агент), Node (native-нода `server.js`), Google Sheets (Apps Script — не трогаем), pytest.

Спека: `docs/superpowers/specs/2026-07-25-akg-registry-integration-design.md`.

## Global Constraints

- Рабочая директория репо агента: `c:\Users\Alex\Documents\ai-work\akg\agent-mode\`. venv: `.venv\Scripts\python`.
- Колонки реестра, что пишет агент: A `week_start` (DD.MM.YYYY), F `channel` (дословно), K `Охват`, M `подписчики соцсетей` (прирост), W `Комментарий`. Остальное не трогаем.
- `channel` (F) ОБЯЗАН дословно совпадать с колонкой «Канал (детальный)» справочника клиента.
- Маппинг Охвата (K): Дзен ← показы; ВК-сообщество ← Охват контента; ВК блог ← просмотры канала; ВК-видео ← просмотры видео; Тенчат ← охват записей.
- Период: Дзен/ВК — точная отчётная неделя; Тенчат — «последние 7 дней» + пометка в W + `needs_review`.
- Строки каналов со `status` ≠ `ok` — НЕ включаются (не затираем хорошие данные).
- ВК-реклама (VK Ads) — НЕ трогаем, остаётся в Pull+map.
- Серверная часть — боевой прод клиента: тест на копии таблицы Маши (`1124sH2A…`) до боевой.
- Секрет вебхука не коммитить (в `config_local.py` / env, вне git).

---

### Task 1: registry_name в конфиге каналов

**Files:**
- Modify: `config.py`, `config_local.example.py`
- Test: `tests/test_config_registry.py`

**Interfaces:**
- Produces: каждый канал в `config.CHANNELS` может иметь `registry` — либо строку (одна строка реестра), либо dict `{подметрика: имя}` для ВК (сообщество/блог/видео → разные каналы реестра). Плюс `WEBHOOK_URL=None`, `WEBHOOK_KEY=None` по умолчанию.

- [ ] **Step 1: Тест — конфиг несёт registry-имена и webhook-поля**

`tests/test_config_registry.py`:

```python
import config


def test_webhook_defaults_none():
    assert config.WEBHOOK_URL is None
    assert config.WEBHOOK_KEY is None


def test_channels_have_registry_names():
    # dzen — одна строка реестра; vk — несколько (по вкладкам)
    assert isinstance(config.CHANNELS["dzen"]["registry"], str)
    vk_reg = config.CHANNELS["vk"]["registry"]
    assert isinstance(vk_reg, dict)
    assert "community" in vk_reg and "channel" in vk_reg and "video" in vk_reg
    assert isinstance(config.CHANNELS["tenchat"]["registry"], str)
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv\Scripts\python -m pytest tests/test_config_registry.py -v`
Expected: FAIL (KeyError `registry` / AttributeError WEBHOOK_URL)

- [ ] **Step 3: Дополнить `config.py`**

В `config.py` добавить перед блоком `try: from config_local`:

```python
# Отправка строк в Реестр_факта (native-эндпоинт). None = не отправлять.
WEBHOOK_URL = os.environ.get("AKG_WEBHOOK_URL")   # напр. https://n8n.crm-techno.ru/native/webhook/agent-metrics
WEBHOOK_KEY = os.environ.get("AKG_WEBHOOK_KEY")   # секрет ?key=

# Имена каналов в колонке F «Канал (детальный)» реестра.
# dzen/tenchat — одна строка; vk — несколько (вкладки → разные каналы реестра).
CHANNELS["dzen"]["registry"] = "Корп. блог Дзен"
CHANNELS["vk"]["registry"] = {
    "community": "Корп. ВК-сообщество",
    "channel":   "Корп. ВК блог",
    "video":     "Корп. ВК-видео",
}
CHANNELS["tenchat"]["registry"] = "Тенчат ЛБ"
```

(на машине клиента имена/URL переопределяются в `config_local.py`.)

В `config_local.example.py` добавить раздел-комментарий с примером `registry`
и `AKG_WEBHOOK_URL`/`AKG_WEBHOOK_KEY`.

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv\Scripts\python -m pytest tests/test_config_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add config.py config_local.example.py tests/test_config_registry.py
git commit -m "config: registry-имена каналов + WEBHOOK_URL/KEY для записи в Реестр_факта"
```

---

### Task 2: core/registry_rows.py — маппер ChannelResult → строки реестра

**Files:**
- Create: `core/registry_rows.py`
- Test: `tests/test_registry_rows.py`

**Interfaces:**
- Consumes: `config.CHANNELS[*]["registry"]`, `core.result.ChannelResult`.
- Produces: `to_registry_rows(results: list[ChannelResult], week: str, start, end) -> list[dict]`.
  Каждая строка: `{"week_start": "DD.MM.YYYY", "channel": <F>, "reach": int, "subs_social": int|None, "comment": str, "source": "agent-mode", "week": "YYYY-Www"}`.
  Правила: пропускать каналы со `status != "ok"`; ВК разворачивать в ≤3 строки
  (community/channel/video) по непустым метрикам; Тенчат — пометка периода в comment + `needs_review` flag в отдельном поле `_needs_review`.

- [ ] **Step 1: Падающие тесты маппера**

`tests/test_registry_rows.py`:

```python
from datetime import date
from core.registry_rows import to_registry_rows
from core.result import ChannelResult


def _dzen_ok():
    return ChannelResult(channel="dzen", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="xlsx",
        metrics={"shows": 87, "reads": 5, "subs": 0, "posts_count": 12,
                 "subscribers": 45, "posts": []})


def _vk_ok():
    return ChannelResult(channel="vk", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="vision",
        metrics={"content_reach": 5, "content_views": 28, "members": 0,
                 "channel_views": 12, "video_views": 3})


def _tenchat_ok():
    return ChannelResult(channel="tenchat", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="ok", source="xhr",
        needs_review=True,
        metrics={"reach": 0, "views": 0, "subscribers": 0})


def _failed():
    return ChannelResult(channel="dzen", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19", status="failed")


def test_dzen_row_maps_shows_to_reach():
    rows = to_registry_rows([_dzen_ok()], "2026-W29", date(2026,7,13), date(2026,7,19))
    d = next(r for r in rows if r["channel"] == "Корп. блог Дзен")
    assert d["reach"] == 87            # показы
    assert d["subs_social"] == 0       # подписки-прирост из XLSX
    assert d["week_start"] == "13.07.2026"
    assert "12 публ" in d["comment"] and "45" in d["comment"]


def test_vk_expands_into_three_channels():
    rows = to_registry_rows([_vk_ok()], "2026-W29", date(2026,7,13), date(2026,7,19))
    by = {r["channel"]: r for r in rows}
    assert by["Корп. ВК-сообщество"]["reach"] == 5      # охват контента
    assert by["Корп. ВК блог"]["reach"] == 12           # просмотры канала
    assert by["Корп. ВК-видео"]["reach"] == 3           # просмотры видео


def test_vk_skips_empty_subtab():
    # channel_views=None → строки «Корп. ВК блог» нет
    r = _vk_ok(); r.metrics["channel_views"] = None
    rows = to_registry_rows([r], "2026-W29", date(2026,7,13), date(2026,7,19))
    assert not any(x["channel"] == "Корп. ВК блог" for x in rows)


def test_tenchat_marks_period_in_comment():
    rows = to_registry_rows([_tenchat_ok()], "2026-W29", date(2026,7,13), date(2026,7,19))
    t = rows[0]
    assert t["channel"] == "Тенчат ЛБ"
    assert "7 дней" in t["comment"]
    assert t["_needs_review"] is True


def test_failed_channel_produces_no_rows():
    rows = to_registry_rows([_failed()], "2026-W29", date(2026,7,13), date(2026,7,19))
    assert rows == []
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv\Scripts\python -m pytest tests/test_registry_rows.py -v`
Expected: FAIL (`No module named core.registry_rows`)

- [ ] **Step 3: Реализовать `core/registry_rows.py`**

```python
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
    specs = [
        ("content_reach", "community", "members"),
        ("channel_views", "channel",   None),
        ("video_views",   "video",     None),
    ]
    rows = []
    for reach_key, reg_key, subs_key in specs:
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
        reg = config.CHANNELS.get(res.channel, {}).get("registry")
        if reg is None:
            continue
        if res.channel == "dzen":
            out.append(_dzen_row(res, reg, week, ws))
        elif res.channel == "vk":
            out.extend(_vk_rows(res, reg, week, ws))
        elif res.channel == "tenchat":
            out.append(_tenchat_row(res, reg, week, ws))
    return out
```

- [ ] **Step 4: Прогнать — зелено**

Run: `.venv\Scripts\python -m pytest tests/test_registry_rows.py tests/ -q`
Expected: все PASS

- [ ] **Step 5: Commit**

```
git add core/registry_rows.py tests/test_registry_rows.py
git commit -m "registry_rows: маппер ChannelResult -> строки Реестр_факта"
```

---

### Task 3: ВК — выставление точной недели через датапикер

**Files:**
- Modify: `channels/vk.py`
- Test: живой прогон (селекторы датапикера верифицируются вживую)

**Interfaces:**
- Consumes: `start`, `end` (даты недели) в `collect(...)`.
- Produces: перед снятием метрик ВК выставляет период дашборда = [start, end]
  через датапикер (клик по тексту периода → произвольный диапазон датами →
  «Показать»). Если датапикер не поддался — `needs_review=True` + пометка (как
  сейчас), не блокировать.

- [ ] **Step 1: Прочитать текущий `channels/vk.py`** — понять, где после
  `page.goto(dashboard)` начинается обход вкладок; туда вставить установку периода.

- [ ] **Step 2: Реализовать функцию `_set_period(page, start, end) -> bool`**

Открыть датапикер (клик по элементу с текстом периода вида `DD.MM – DD.MM` в
шапке дашборда), в календаре выбрать start и end (или ввести в текстовые поля
диапазона `DD.MM.YYYY — DD.MM.YYYY`), нажать «Показать». Вернуть True при успехе.
Разведка показала: пресеты («Прошлая неделя») + произвольный диапазон + кнопка
«Показать». Точные селекторы уточнить в живом прогоне (Step 4). Обернуть в
try/except → False. В `collect()`: вызвать `_set_period`; при False —
`res.needs_review=True` и пометка в `res.error`, продолжить сбор (дашборд
покажет дефолтный период).

- [ ] **Step 3: Обновить проверку периода** — `_period_matches` уже есть; после
  `_set_period` актуальный период должен совпасть с неделей → тогда без пометки.

- [ ] **Step 4: Живой прогон + доводка селекторов**

Run: `.venv\Scripts\python collect.py --channels vk --week 2026-W29`
Открыть `out/2026-W29/vk_community.png` — период в шапке должен стать
`13.07 – 19.07` (не дефолтные 7 дней). Если датапикер не сработал — поправить
селекторы по факту (как при первичной разведке ВК) и повторить (не зациклить —
1–2 итерации; ВК бережём от rate-limit). Сверить цифры за точную неделю.

- [ ] **Step 5: Commit**

```
git add channels/vk.py
git commit -m "ВК: выставление точной отчётной недели через датапикер дашборда"
```

---

### Task 4: collect.py — отправка строк на native-эндпоинт

**Files:**
- Modify: `collect.py`
- Create: `core/webhook.py`
- Test: `tests/test_webhook.py`

**Interfaces:**
- Consumes: `to_registry_rows(...)`, `config.WEBHOOK_URL`, `config.WEBHOOK_KEY`.
- Produces: `core.webhook.post_rows(url, key, week, rows) -> tuple[bool, str]` —
  POST JSON `{week, rows, source}` на `url?key=<key>`; возвращает (ok, сообщение).
  `collect.main()` после сбора: если `WEBHOOK_URL` задан — смаппить и отправить,
  результат в консоль/summary.

- [ ] **Step 1: Тест post_rows (без сети — monkeypatch urllib)**

`tests/test_webhook.py`:

```python
import json
from core import webhook


def test_post_rows_sends_payload(monkeypatch):
    captured = {}

    class FakeResp:
        status = 200
        def read(self): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(webhook.urllib.request, "urlopen", fake_urlopen)
    ok, msg = webhook.post_rows("https://x/native/webhook/agent-metrics", "SEC",
                                "2026-W29", [{"channel": "Корп. блог Дзен", "reach": 87}])
    assert ok is True
    assert "key=SEC" in captured["url"]
    assert captured["body"]["week"] == "2026-W29"
    assert captured["body"]["rows"][0]["reach"] == 87


def test_post_rows_handles_error(monkeypatch):
    def boom(req, timeout=0): raise OSError("network down")
    monkeypatch.setattr(webhook.urllib.request, "urlopen", boom)
    ok, msg = webhook.post_rows("https://x", "k", "2026-W29", [])
    assert ok is False
    assert "network down" in msg
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv\Scripts\python -m pytest tests/test_webhook.py -v`
Expected: FAIL (`No module named core.webhook`)

- [ ] **Step 3: `core/webhook.py`**

```python
"""POST строк реестра на native-эндпоинт агента (stdlib, без зависимостей)."""
import json
import urllib.request
import urllib.parse


def post_rows(url: str, key: str | None, week: str, rows: list[dict]) -> tuple[bool, str]:
    full = url + (("?" + urllib.parse.urlencode({"key": key})) if key else "")
    payload = json.dumps({"week": week, "rows": rows, "source": "agent-mode"}).encode()
    req = urllib.request.Request(full, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()[:200]
            return (200 <= r.status < 300), f"HTTP {r.status}: {body}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
```

- [ ] **Step 4: Подключить в `collect.py`** (после блока сводки)

```python
from core.registry_rows import to_registry_rows
from core.webhook import post_rows
...
    # Отправка в Реестр_факта, если настроен вебхук
    if config.WEBHOOK_URL:
        rows = to_registry_rows(results, week, start, end)
        if rows:
            ok, msg = post_rows(config.WEBHOOK_URL, config.WEBHOOK_KEY, week, rows)
            print(f"\nОтправка в Реестр_факта: {'ok' if ok else 'СБОЙ'} "
                  f"({len(rows)} строк) — {msg}")
        else:
            print("\nОтправка в Реестр_факта: нет строк (нет каналов в статусе ok)")
```

- [ ] **Step 5: Прогнать всё + commit**

Run: `.venv\Scripts\python -m pytest tests/ -q` → все PASS
```
git add core/webhook.py collect.py tests/test_webhook.py
git commit -m "collect: отправка строк реестра на native-эндпоинт (webhook)"
```

---

### Task 5: Серверная нода Agent_Metrics_Code.js + роут

**Files (на сервере akg-native, у Маши — через SSH):**
- Create: `~/AKG/akg-native/nodes/Agent_Metrics_Code.js`
- Modify: `~/AKG/akg-native/server.js` (регистрация ноды + роут)
- Local mirror: скопировать оба файла в `docs/server/` нашего репо для истории.

**Interfaces:**
- Consumes: POST `{week, rows:[{channel, week_start, reach, subs_social, comment, ...}], source}`.
- Produces: `staticData.agent_rows[week] = {channel: row}`; история подписчиков
  `staticData.agent_subs_history[channel]` для Δ; отдаёт `{ok, stored}`.

- [ ] **Step 1: Прочитать `server.js`** — как регистрируются ноды (`NODES.dzenSnapshot=compileNode(...)`) и роуты (`{m:'POST', p:'/webhook/...', node:...}`); как `$getWorkflowStaticData('global')` доступен в ноде. Скопировать паттерн из `Dzen_Snapshot_Code.js`.

- [ ] **Step 2: Написать `Agent_Metrics_Code.js`** по образцу Dzen_Snapshot:
  валидировать `Array.isArray(body.rows)`; для каждой строки — если `subs_social`
  прислан как «текущее число» (флаг `subs_absolute:true`), посчитать Δ из
  `agent_subs_history[channel]` (последняя запись прошлой недели), иначе взять как
  есть; сложить в `sd.agent_rows[week][channel]`; вернуть `{ok:true, stored:[...]}`.
  (Точная форма — по факту server.js API; уточнить в Step 1.)

- [ ] **Step 3: Зарегистрировать роут** в `server.js`: `NODES.agentMetrics =
  compileNode('Agent_Metrics_Code.js')` + `{m:'POST', p:'/webhook/agent-metrics', node: NODES.agentMetrics}`. Добавить key-проверку по образцу существующих защищённых роутов (если есть) или в ноде.

- [ ] **Step 4: Локальный тест ноды** (на сервере, без боевого Pull+map):
  `curl -X POST 'http://localhost:<port>/webhook/agent-metrics?key=...' -d '{"week":"2026-W29","rows":[{"channel":"Корп. блог Дзен","reach":87,"subs_social":0,"comment":"тест"}]}'`
  → `{ok:true}`; проверить, что в `data/staticData.json` появился `agent_rows`.

- [ ] **Step 5: Зеркало в репо + commit**
```
# скопировать серверные файлы в docs/server/ репо агента
git add docs/server/Agent_Metrics_Code.js docs/server/server.js.diff
git commit -m "server: нода agent-metrics (приём строк реестра) — зеркало"
```

---

### Task 6: Правка Pull+map — замещение каналов из agent_rows

**Files (сервер):**
- Modify: `~/AKG/akg-native/nodes/Pull_+_map_to_detailed_channels.js`
- Local mirror: diff в `docs/server/`.

**Interfaces:**
- Consumes: `staticData.agent_rows[week]`.
- Produces: в выдаче `akg-report-rows` строки Дзен/ВК-органики/Тенчата берутся из
  `agent_rows`, собственный сбор этих каналов не выполняется.

- [ ] **Step 1: Разобрать Pull+map** — найти: (а) где определяется `week`; (б)
  функции сбора Дзена (`fetchDzen`/dzen-блок ~1090–1200), ВК-сообществ
  (`fetchVkCommunities` ~1280–1400), Тенчата (если есть); (в) где всё сводится в
  итоговый `out`/`return`. Записать номера строк.

- [ ] **Step 2: Список замещаемых имён каналов** — собрать set имён из
  `agent_rows` (это и есть «замещённые»). Перед добавлением серверных Дзен/ВК-орг
  строк — пропускать те, чей `channel` есть в `agent_rows[week]`.

- [ ] **Step 3: Подмешать agent_rows** — в конце формирования строк:
  `const ar = (sd.agent_rows||{})[week] || {}; for (const row of Object.values(ar)) out.push(normalizeRow(row));`
  где `normalizeRow` приводит присланную строку к полной форме строки Pull+map
  (недостающие поля = 0/'', как в существующих строках). Отфильтровать из
  собственного сбора каналы, покрытые agent_rows.

- [ ] **Step 4: Бэкап + деплой** — перед правкой скопировать
  `Pull_+_map_to_detailed_channels.js` в `~/AKG/akg-native/backups/`; применить
  правку; перезапустить сервер (docker restart / как в README akg-native).

- [ ] **Step 5: Self-check** — `curl 'http://localhost:<port>/webhook/akg-report-rows?week=2026-W29'`
  → в ответе строки «Корп. блог Дзен» и т.д. с агентскими цифрами (reach=87),
  без дублей от собственного сбора. Зеркало-diff в репо + commit.

---

### Task 7: Сквозной тест на копии таблицы → PDF

**Files:** нет (проверка).

- [ ] **Step 1: Настроить агент на native** — в `config_local.py`
  `AKG_WEBHOOK_URL`=native `/webhook/agent-metrics`, `AKG_WEBHOOK_KEY`=секрет.

- [ ] **Step 2: Прогон агента** `--all --week 2026-W29`; убедиться «Отправка в
  Реестр_факта: ok».

- [ ] **Step 3: Проверить staticData** на сервере — `agent_rows[2026-W29]` содержит
  строки Дзен/ВК/Тенчат.

- [ ] **Step 4: Дёрнуть akg-report-rows** — строки агента присутствуют.

- [ ] **Step 5: Прогнать Apps Script копии таблицы** (`1124sH2A…`) на тестовой
  неделе — убедиться, что строки легли в F/K/M/W правильно, дедуп неделя+канал
  сработал, «Комментарий» не затёрт. Затем прогнать owner-report на копии → PDF
  содержит эти каналы. Зафиксировать вердикт. Боевую таблицу подключать только
  после зелёного теста на копии.

## Self-Review

- Spec coverage: замещение (T6), готовые строки (T2/T4), нода (T5), маппинг колонок
  A/F/K/M/W (T2), период Дзен/ВК/Тенчат (T3 + маппер пометки), дельта подписчиков
  (T5 история), тест на копии (T7), не трогаем Apps Script/PDF/ВК-рекламу (T6 scope).
- Placeholder-scan: серверные Tasks 5–6 содержат «уточнить по факту server.js/Pull+map»
  — это НЕ placeholder кода, а обязательный разбор боевого файла первым шагом задачи
  (91КБ Pull+map нельзя воспроизвести в плане дословно; Step 1 каждой серверной
  задачи = чтение точных функций). Агентские Tasks 1–4 — полный код.
- Type consistency: `to_registry_rows(results, week, start, end)`, `post_rows(url, key,
  week, rows)`, поля строки `week_start/channel/reach/subs_social/comment/week/source/_needs_review`
  — единообразны между T2 и T4.
