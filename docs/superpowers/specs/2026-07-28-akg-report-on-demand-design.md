# АКГ: отчёт по команде Анны + сбор ВК из 2 аккаунтов — дизайн

Дата: 2026-07-28. Статус: финализирован Alex'ом.

## Зачем

Изменить логику отчёта: убрать cron-генерацию и авто-отправку PDF, дать Анне
триггерить формирование+отправку из своего Claude Code. Плюс поддержать сбор ВК
из двух разных аккаунтов клиента (agcapital и irina.ekimovskih) с ручным
перелогином между.

## Недельный цикл (новый)

```
ВС вечер   Сервер наполняет таблицу API-каналами (Метрика/Директ/Битрикс/TG/VK Ads)
           через Apps Script pull → akg-report-rows. ВК-орг/Тенчат/Дзен — свой
           (старый) сбор Pull+map, финализируются агентом в пн (собственный сбор
           НЕ отключаем — оставлено по решению Alex; агент перезапишет).
ПН, Анна   1. «собери ВК аккаунт 1»  → collect.py --channels vk --vk-account 1 (agcapital)
(Claude    2. перелогин ВК → «аккаунт 2» → collect.py --channels vk --vk-account 2 (irina.ekimovskih)
 Code)     3. «собери Дзен и Тенчат» → collect.py --channels dzen,tenchat
           4. «сформируй и отправь отчёт» → агент дёргает native-эндпоинт →
              генерация PDF + отправка собственнику
```

## Что уже есть (сверено 2026-07-27/28)

- Генерация PDF: **178 (team-assistant)** `~/AKG/owner-report-pipeline/` —
  `run_weekly.sh` (cron пн 02:00) → `make_report.py --week --upload` (weasyprint,
  грузит PDF в native storage `POST /webhook/akg-owner-report-upload`).
- Отправка: Apps Script в клиентской таблице — `sendOwnerReportWeekly()` (trigger
  пн 06:00) → `sendOwnerReportFor_(week)` → тянет PDF из native storage
  (`/native/webhook/akg-owner-report`) → `GmailApp.sendEmail` получателям из
  листа «Получатели_отчёта». Есть ручные `sendOwnerReport()`, `sendOwnerReportForWeek()`.
- native: **5.187 (клиентский crm-techno)** `/opt/akg-native/` (docker, роуты
  `/native/webhook/*`, ключ SHARED_KEY). Агент→Реестр_факта интеграция уже сделана.
- Apps Script `pull` (наполнение таблицы) — не трогаем.

## Изменения

### A. Отключить cron-триггеры (перенести под команду)

- `run_weekly.sh` cron на 178 — убрать из crontab (у нас доступ).
- Apps Script `sendOwnerReportWeekly` trigger — отключить в триггерах Apps Script.
  ⚠️ Требует Google-доступа `summonerx222` (Маша/Ирина) — предусловие не под нашим
  контролем.

### B. Native-эндпоинт генерации+отправки

Новый роут на native (5.187): `POST /native/webhook/generate-report?week=&key=`.
Логика (нода `Generate_Report_Code.js` или обработчик в server.js):
1. **Генерация** — ssh 5.187→178, запуск
   `~/AKG/owner-report-pipeline/run_weekly.sh` (или `make_report.py --week <week>
   --upload`) → PDF в native storage. Предусловие: ssh-ключ 5.187→178 (настроим).
2. **Отправка** — HTTP на Apps Script Web App (doPost `{week}`) → обёртка над
   `sendOwnerReportFor_(week)` → GmailApp получателям. Предусловие: публикация
   web-app (Google-доступ `summonerx222`).
Ответ агенту: `{ok, generated, sent, pdf?, recipients?, error?}`.

Обработка ошибок: генерация упала → `{ok:false, error}` (отправки нет); отправка
упала → `{ok:true, generated:true, sent:false, error}`; неверный key → отклонить.

### C. Команда агента для отчёта

`collect.py --report [--week YYYY-Www]` — дёргает `generate-report` эндпоинт
(`config.WEBHOOK_URL` base + `/generate-report`, `WEBHOOK_KEY`), печатает результат.
Анна из Claude: «сформируй и отправь отчёт» → Claude запускает эту команду.

### D. Сбор ВК из 2 аккаунтов

Config (`config_local.py`):
```python
CHANNELS["vk"]["accounts"] = {
    "1": {"screen": "agcapital",
          "registry": {"community": "Корп. ВК-сообщество",
                       "channel": "Корп. ВК блог", "video": "Корп. ВК-видео"}},
    "2": {"screen": "irina.ekimovskih",
          "registry": {"community": "ВК ЛБ"}},
}
```
Команда: `collect.py --channels vk --vk-account N` — собирает сообщества аккаунта
N под текущей ВК-сессией профиля, registry-имена берутся из `accounts[N].registry`.
Два запуска с ручным перелогином Анны между. Агент НЕ проверяет, под каким
аккаунтом сессия (по решению Alex): при перепутанном порядке — `auth_required`/
пустой дашборд → строку не шлёт (не пишет мусор), Анна перелогинивается и повторяет.

Маппер `registry_rows._vk_rows` — брать registry из `accounts[N].registry` (сейчас
из `CHANNELS["vk"]["registry"]`). Обратная совместимость: если `accounts` нет,
использовать старый `registry` (кабинеты Alex, один аккаунт).

## Ошибки

- ВК канал `failed`/`auth_required` (не тот аккаунт/нет прав) → строку не шлём.
- generate-report: понятные статусы генерации/отправки (см. B).
- POST-сбой сбора не рушит прогон (как в существующей интеграции).

## Тест

- `generate-report` — на **тестового получателя** (временно свой email в
  «Получатели_отчёта», не собственника) за тестовую неделю → PDF сгенерился +
  письмо дошло. Затем вернуть боевого получателя.
- 2 аккаунта ВК — тестировщик на клиентских кабинетах: `--vk-account 1` →
  перелогин → `--vk-account 2` → в таблице «Корп. ВК-сообщество» и «ВК ЛБ».
- Убедиться, что cron больше не генерит/шлёт (наступит пн — авто-отправки нет).

## Вне рамок

- Контент/шаблоны PDF (owner-report) — не меняем.
- Apps Script `pull` (наполнение таблицы вс) — не меняем.
- Интеграция агент→Реестр_факта (сделана ранее) — не меняется.
- Отключение собственного сбора ВК/Дзен/Тенчат в Pull+map — НЕ делаем (оставлено).

## Предусловия, требующие не-нашего доступа

1. ssh-ключ 5.187→178 (настроим сами — доступ к обоим есть).
2. Apps Script Web App deployment для отправки + отключение `sendOwnerReportWeekly`
   trigger — **Google-доступ `summonerx222`** (Маша/Ирина).
