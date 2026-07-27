# Отчёт по команде + ВК 2 аккаунта — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development или superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Анна из Claude Code триггерит формирование+отправку PDF (не cron), и агент собирает ВК из двух аккаунтов клиента с ручным перелогином.

**Architecture:** Агент получает команды `collect.py --channels vk --vk-account N` (сбор ВК по аккаунту) и `collect.py --report` (дёргает native-эндпоинт). Native-эндпоинт `generate-report` (обработчик в server.js на 5.187) по ssh запускает на 178 генерацию PDF (`make_report.py`) и отправку по SMTP с отдельного ящика (`send_report.py`). Старый cron/Apps Script-триггер убираются.

**Tech Stack:** Python 3.11 + Playwright (агент), Node (server.js), Python smtplib (отправка), pytest.

Спека: `docs/superpowers/specs/2026-07-28-akg-report-on-demand-design.md`.
**Отличие от спеки:** отправка — SMTP с другого ящика (не Apps Script web-app; Alex сменил решение 2026-07-28).

## Global Constraints

- Репо агента: `c:\Users\Alex\Documents\ai-work\akg\agent-mode\`. venv: `.venv\Scripts\python`.
- Серверы: native `5.187.1.162` (`/opt/akg-native/`, docker, root); pipeline `178.104.156.39` (`~/AKG/owner-report-pipeline/`, mariiastar). Пароли — в документе доступов (не в git).
- SHARED_KEY вебхуков — плейсхолдер `<SHARED_KEY>` в git, реальный на сервере.
- SMTP-креды отправки и email получателя — в `config`/env на 178 (`~/AKG/owner-report-pipeline/.report_env`), НЕ в git.
- ВК-аккаунты: `accounts[N]` в `config_local.py`; `--vk-account N` собирает сообщества этого аккаунта под текущей ВК-сессией; строки каналов со `status`≠`ok` не шлются.
- Старый cron `run_weekly.sh` (178) убираем ТОЛЬКО когда новый путь работает end-to-end. Apps Script `sendOwnerReportWeekly` trigger — отключает Маша/Ирина (Google-доступ), задокументировать.
- Тест отправки — на тестового получателя, не собственника.

---

### Task 1: ВК — два аккаунта (config + vk.py + маппер)

**Files:**
- Modify: `config.py`, `config_local.example.py`, `channels/vk.py`, `core/registry_rows.py`, `collect.py`
- Test: `tests/test_registry_rows.py` (дополнить), `tests/test_vk_account.py`

**Interfaces:**
- Produces: `config.CHANNELS["vk"]["accounts"]` = `{ "N": {"screen": str, "registry": {...}} }` (опционально; если нет — старый одиночный `registry`).
- Produces: `collect.py --vk-account N` → `run_channel("vk", ..., vk_account="N")`; `channels.vk.collect(ctx, week, start, end, out_dir, account=None)`.
- Produces: `registry_rows._vk_rows(res, reg, week, ws)` берёт `reg` из результата (res несёт выбранный registry-словарь).

- [ ] **Step 1: Тест выбора аккаунта в маппере**

Дополнить `tests/test_registry_rows.py`: ВК-результат с `res.registry_override` (словарь имён выбранного аккаунта) маппится в эти имена.

```python
def test_vk_uses_account_registry_override():
    r = _vk_ok()
    r.registry_override = {"community": "ВК ЛБ"}   # аккаунт 2
    r.metrics = {"content_reach": 17, "content_views": 40, "members": 5,
                 "channel_views": None, "video_views": None}
    rows = to_registry_rows([r], "2026-W29", date(2026,7,13), date(2026,7,19))
    assert rows[0]["channel"] == "ВК ЛБ"
    assert rows[0]["reach"] == 17
    assert not any(x["channel"] == "Корп. ВК блог" for x in rows)  # video/channel None
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv\Scripts\python -m pytest tests/test_registry_rows.py::test_vk_uses_account_registry_override -v`
Expected: FAIL (registry_override не учитывается).

- [ ] **Step 3: ChannelResult.registry_override + маппер**

В `core/result.py` добавить поле dataclass: `registry_override: dict | None = None`.
В `core/registry_rows.py` `to_registry_rows`: для vk — `reg = res.registry_override or config.CHANNELS["vk"].get("registry")`. `_vk_rows(res, reg, ...)` без изменений сигнатуры логики.

- [ ] **Step 4: vk.py — параметр account**

`channels/vk.py` `collect(ctx, week, start, end, out_dir, account=None)`:
- если `account` и `config.CHANNELS["vk"].get("accounts")` — взять `acc = accounts[account]`, `screen = acc["screen"]`, проставить `res.registry_override = acc["registry"]`; список вкладок TABS фильтровать по ключам registry (community/channel/video — собирать только те, что в registry аккаунта).
- иначе — прежнее поведение (один `screen_name`, старый `registry`).

- [ ] **Step 5: collect.py — флаг --vk-account**

`collect.py`: `ap.add_argument("--vk-account")`; в `run_channel` пробросить `vk_account` в `channels.vk.collect(..., account=vk_account)` (только для vk).

- [ ] **Step 6: config — пример accounts**

`config_local.example.py`: добавить пример `CHANNELS["vk"]["accounts"] = {...}` (два аккаунта). `config.py` — не менять дефолт (кабинеты Alex — один аккаунт).

- [ ] **Step 7: Прогнать все тесты + commit**

Run: `.venv\Scripts\python -m pytest tests/ -q` → PASS
```
git add config.py config_local.example.py channels/vk.py core/result.py core/registry_rows.py collect.py tests/
git commit -m "ВК: сбор из нескольких аккаунтов (--vk-account N, registry по аккаунту)"
```

---

### Task 2: collect.py --report + core/report_trigger.py

**Files:**
- Create: `core/report_trigger.py`
- Modify: `collect.py`
- Test: `tests/test_report_trigger.py`

**Interfaces:**
- Produces: `report_trigger.trigger_report(base_url, key, week) -> tuple[bool, str]` — POST на `<base>/generate-report?key=`, тело `{week}`; возвращает (ok, сообщение).
- Produces: `collect.py --report [--week]` — дёргает эндпоинт, печатает результат.

- [ ] **Step 1: Тест trigger_report (monkeypatch urllib)**

`tests/test_report_trigger.py`:

```python
import json
from core import report_trigger


def test_trigger_report_posts_week(monkeypatch):
    cap = {}
    class R:
        status = 200
        def read(self): return b'{"ok":true,"generated":true,"sent":true}'
        def __enter__(self): return self
        def __exit__(self,*a): return False
    def fake(req, timeout=0):
        cap["url"]=req.full_url; cap["body"]=json.loads(req.data.decode()); return R()
    monkeypatch.setattr(report_trigger.urllib.request, "urlopen", fake)
    ok,msg = report_trigger.trigger_report("https://x/native/webhook/generate-report","K","2026-W29")
    assert ok and "key=K" in cap["url"] and cap["body"]["week"]=="2026-W29"


def test_trigger_report_error(monkeypatch):
    def boom(req, timeout=0): raise OSError("down")
    monkeypatch.setattr(report_trigger.urllib.request, "urlopen", boom)
    ok,msg = report_trigger.trigger_report("https://x","K","2026-W29")
    assert not ok and "down" in msg
```

- [ ] **Step 2: Запустить — падает**

Run: `.venv\Scripts\python -m pytest tests/test_report_trigger.py -v` → FAIL (нет модуля).

- [ ] **Step 3: core/report_trigger.py**

```python
"""Триггер генерации+отправки отчёта через native-эндпоинт (stdlib)."""
import json
import urllib.request
import urllib.parse


def trigger_report(base_url: str, key: str | None, week: str) -> tuple[bool, str]:
    url = base_url + (("?" + urllib.parse.urlencode({"key": key})) if key else "")
    payload = json.dumps({"week": week}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return (200 <= r.status < 300), f"HTTP {r.status}: {r.read().decode()[:300]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
```

- [ ] **Step 4: collect.py --report**

`config.py`: `REPORT_URL = os.environ.get("AKG_REPORT_URL")` (base `…/webhook/generate-report`).
`collect.py`: `ap.add_argument("--report", action="store_true")`; в начале `main()` после парсинга — если `args.report`: определить week (parse_week/last_completed_week), вызвать `trigger_report(config.REPORT_URL, config.WEBHOOK_KEY, week)`, напечатать результат, `return`.

- [ ] **Step 5: Тесты + commit**

Run: `.venv\Scripts\python -m pytest tests/ -q` → PASS
```
git add core/report_trigger.py collect.py config.py tests/test_report_trigger.py
git commit -m "collect: команда --report (триггер генерации+отправки через эндпоинт)"
```

---

### Task 3: send_report.py на 178 (SMTP-отправка)

**Files (сервер 178, mariiastar):**
- Create: `~/AKG/owner-report-pipeline/send_report.py`
- Create: `~/AKG/owner-report-pipeline/.report_env` (SMTP-креды, chmod 600, вне git)
- Local mirror: `docs/server/send_report.py` (без кред).

**Interfaces:**
- `python send_report.py --pdf <path> --week <week> [--to <email>]` — шлёт PDF по SMTP.
  Креды/получатель из env (`.report_env`): `SMTP_HOST/PORT/USER/PASS/FROM`, `REPORT_TO`.

- [ ] **Step 1: Прочитать** как формируется тема/тело письма в Apps Script `sendOwnerReportFor_` (на 178 `~/AKG/migrate_to_original/Code.gs`) — воспроизвести тему/текст в send_report.py.

- [ ] **Step 2: send_report.py** — stdlib `smtplib`+`email`: читает env, прикрепляет PDF, шлёт `REPORT_TO`. При отсутствии env/PDF — понятная ошибка (exit≠0).

- [ ] **Step 3: `.report_env`** на 178 с реальными кредами другого ящика (дать Alex), chmod 600. Зеркало в репо — с плейсхолдерами.

- [ ] **Step 4: Локальный тест** на 178: сгенерить PDF (`make_report.py --week <тест> --out /tmp/t.pdf`), `python send_report.py --pdf /tmp/t.pdf --week <тест> --to <свой email>` → письмо дошло.

- [ ] **Step 5: Commit зеркала**
```
git add docs/server/send_report.py
git commit -m "server: send_report.py (SMTP-отправка отчёта с отдельного ящика) — зеркало"
```

---

### Task 4: native-эндпоинт generate-report (5.187) + ssh 5.187→178

**Files (сервер 5.187, root):**
- Modify: `/opt/akg-native/server.js` (роут-обработчик generate-report)
- ssh-ключ 5.187→178.
- Local mirror: `docs/server/generate-report.route.js` + обновить `docs/server/DEPLOY.md`.

**Interfaces:**
- `POST /webhook/generate-report?key=<SHARED_KEY>` тело `{week}` → ssh 178:
  `run_weekly-подобное` (make_report --week --out /tmp + send_report.py). Ответ
  `{ok, generated, sent, error?}`.

- [ ] **Step 1: ssh-ключ 5.187→178** — на 5.187 `ssh-keygen`, добавить pubkey в `~mariiastar/.ssh/authorized_keys` на 178 (у нас доступ к обоим), проверить `ssh mariiastar@178 echo ok` с 5.187.

- [ ] **Step 2: Обработчик generate-report** в `server.js` (по образцу STORAGE_ROUTES — там есть `require`/`child_process`): проверить key; `child_process.execFile('ssh', ['mariiastar@178.104.156.39', 'bash -lc "cd ~/AKG/owner-report-pipeline && ./gen_and_send.sh <week>"'], {timeout: 170000})`; распарсить stdout (ok/generated/sent), вернуть JSON.

- [ ] **Step 3: gen_and_send.sh** на 178 — обёртка: `make_report.py --week --out /tmp/r_<week>.pdf` затем `send_report.py --pdf … --week …`; печатает машиночитаемый статус (`GENERATED=1 SENT=1`), exit-код.

- [ ] **Step 4: Синтаксис server.js** (`docker run --rm -v /opt/akg-native:/chk:ro node:20-alpine node --check /chk/server.js`), бэкап, rebuild+up.

- [ ] **Step 5: Smoke** — `curl -X POST '…/generate-report?key=…' -d '{"week":"<тест>"}'` → `{ok, generated, sent}` на тестового получателя; проверить письмо. Commit зеркала + DEPLOY.md.

---

### Task 5: Убрать старый cron + документировать Google-действие

**Files (178) + docs.**

- [ ] **Step 1:** Убедиться, что Tasks 1–4 работают end-to-end (генерация+отправка по команде).
- [ ] **Step 2:** На 178 убрать строку `run_weekly.sh` из crontab (`crontab -e` / `crontab -l | grep -v run_weekly | crontab -`). Оставить `dzen_snapshot`/backup.
- [ ] **Step 3:** В `docs/server/DEPLOY.md` записать: Апс-Скрипт `sendOwnerReportWeekly` trigger должна отключить Маша/Ирина (Apps Script → Триггеры → удалить) — иначе дубль-отправка от summonerx222. До отключения — риск дублей.
- [ ] **Step 4:** Commit доков.

---

### Task 6: Сквозной тест

- [ ] **Step 1:** Агент настроен: `config_local.py` с `accounts` (ВК 2 акк) + `AKG_REPORT_URL`/`AKG_WEBHOOK_KEY`.
- [ ] **Step 2:** ВК: `collect.py --channels vk --vk-account 1` → перелогин → `--vk-account 2`; в таблице «Корп. ВК-сообщество» и «ВК ЛБ».
- [ ] **Step 3:** `collect.py --report --week <тест>` → эндпоинт вернул `{ok, generated, sent}`, письмо тестовому получателю дошло с PDF за неделю.
- [ ] **Step 4:** Вернуть боевого получателя в `.report_env`/лист; подтвердить с Alex готовность к переключению (снять cron — Task 5, попросить Машу отключить trigger).

## Self-Review

- Spec coverage: A (Task 5 cron + doc), B (Task 4 эндпоинт+ssh, Task 3 отправка — SMTP вместо Apps Script per Alex), C (Task 2 --report), D (Task 1 ВК 2 акк). Тест (Task 6). Google-предусловие (Task 5 doc).
- Placeholder-scan: серверные Tasks 3–5 Step 1 = чтение реального Code.gs/server.js (не placeholder). Агентские Tasks 1–2 — полный код.
- Type consistency: `trigger_report(base,key,week)`, `send_report.py --pdf --week --to`, `ChannelResult.registry_override`, `collect(...,account=)`, `--vk-account` — единообразны.
