# Деплой серверной части интеграции (akg-native)

Серверная часть = приём строк от агента + замещение каналов в Pull+map.
Задеплоено на прод **5.187.1.162** (`/opt/akg-native/`, docker) 2026-07-27.

## Что где

- `Agent_Metrics_Code.js` — новая нода: `POST /webhook/agent-metrics?key=<SHARED_KEY>`
  принимает `{week, rows[], source}`, кладёт в `staticData.global.agent_rows[week]`,
  считает Δ подписчиков (по флагу `subs_absolute`) из истории. Копируется в
  `/opt/akg-native/nodes/`.
- `pullmap_agent_block.js` — блок, вставляемый в `Pull_+_map_to_detailed_channels.js`
  ПЕРЕД строкой `// Финальные строки в формате для Apps Script`. Замещает
  reach/subs_social/comment строки канала данными из `agent_rows[weekKey]`
  (Битрикс-лиды/сделки по каналу сохраняются). Пустой `agent_rows` → собственный
  сбор Pull+map (дефолт).
- `server.js` (правка): регистрация `agentMetrics:compileNode('Agent_Metrics_Code.js')`
  в `NODES` + роут `{ m:'POST', p:'/webhook/agent-metrics', node: NODES.agentMetrics }`.

## Процедура (nodes/server.js вшиты в образ — нужен rebuild)

```bash
cd /opt/akg-native
# 0. бэкапы
cp server.js server.js.bak-$(date +%Y%m%d-%H%M%S)
cp "nodes/Pull_+_map_to_detailed_channels.js" "nodes/Pull_+_map_to_detailed_channels.js.bak-$(date +%Y%m%d-%H%M%S)"
# 1. положить Agent_Metrics_Code.js в nodes/ (подставить реальный SHARED_KEY вместо <SHARED_KEY>)
# 2. добавить роут в server.js (2 строки, см. выше)
# 3. вставить pullmap_agent_block.js перед якорем в Pull+map
# 4. проверить синтаксис (обёртка compileNode — файлы нод используют top-level await):
docker run --rm -v /opt/akg-native:/chk:ro -v /tmp/check.js:/check.js:ro node:20-alpine node /check.js
# 5. пересборка + перезапуск (staticData в томе ./data:/data переживёт)
docker compose build && docker compose up -d
# 6. smoke-тесты
curl -s -X POST 'http://127.0.0.1:8088/webhook/agent-metrics?key=<SHARED_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{"week":"2026-W29","rows":[{"channel":"Корп. блог Дзен","reach":87,"subs_social":0,"comment":"тест"}]}'
# → {"ok":true,"stored":["Корп. блог Дзен"]}
curl -s 'http://127.0.0.1:8088/webhook/akg-report-rows?key=<SHARED_KEY>&week=2026-W29' | grep -o 'Корп. блог Дзен'
# очистить тест: тот же POST с "rows":[] за неделю
```

## Откат

Восстановить `server.js` и `Pull_+_map…js` из `.bak-*`, `docker compose build && up -d`.
Либо очистить `agent_rows` (POST rows:[]) — замещение отключится, собственный сбор вернётся.

## Отчёт по команде + ВК 2 аккаунта (2026-07-28)

Файлы (зеркала здесь, реальные секреты — на серверах):
- `send_report.py` → `178:~/AKG/owner-report-pipeline/` — SMTP-отправка PDF из storage.
  Креды в `178:~/AKG/owner-report-pipeline/.report_env` (chmod 600, вне git):
  SMTP_HOST/PORT/USER/PASS/FROM, REPORT_TO, REPORT_CC, SHARED_KEY, STORAGE_URL.
- `gen_and_send.sh` → `178:~/AKG/owner-report-pipeline/` — обёртка: inject_week +
  make_report --upload + send_report. Печатает `GENERATED=1 SENT=1`.
- `generate-report.route.js` — роут в `5.187:/opt/akg-native/server.js` (первым в
  STORAGE_ROUTES): `POST /webhook/generate-report?key=` `{week, test_to?}` → ssh
  5.187→178 → gen_and_send.sh. Требует: openssh-client в образе (Dockerfile
  `apk add openssh-client`), монтирование `/root/.ssh:/root/.ssh:ro` (compose),
  ssh-ключ 5.187→178 (в authorized_keys mariiastar@178).

Деплой правок server.js/Dockerfile/compose — тот же rebuild: `docker compose build && up -d`.

**Проверено 2026-07-28 (полный сквозной путь):** эндпоинт `generate-report` →
ssh 5.187→178 → генерация PDF + upload + SMTP-отправка. 4/4 прогона
`{ok:true, generated:true, sent:true, MINI=1}`. SMTP-ящик `gmdidro@gmail.com`
(Gmail app-password в `178:.report_env`, chmod 600). Отправка изолированно
(`send_report.py`) тоже `SENT=1`. bad key → unauthorized.

### Корневая причина флапа и её фикс (2026-07-28)
Симптом: случайные `ERROR=make_report` / `no_detailed_pdf` / `MINI=0`.
Диагноз: `make_report`, `send_report` и проверка storage все ходят на
`STORAGE_URL=https://n8n.crm-techno.ru/native/webhook/akg-owner-report`, а
**резолвер 178 (systemd-resolved) периодически даёт SERVFAIL на домене
crm-techno.ru** → любое обращение к storage случайно падает. Это НЕ разные
ошибки, а одна.
Фикс: `n8n.crm-techno.ru` прибит к IP в `/etc/hosts` на 178 (домен указывает на
тот же прод-натив 5.187.1.162):
```
5.187.1.162 n8n.crm-techno.ru  # AKG storage: обход флапающего резолвера 178
```
После этого 5/5 резолвов стабильны, эндпоинт 4/4 успешен. Бэкап хостов —
`/etc/hosts.bak-*`. Дополнительно в `gen_and_send.sh` — ретрай генерации×3 с
проверкой, что PDF реально лёг в storage (страховка на случай других сбоев).

**Осталось (не под нашим контролем):**
- Отключить Apps Script trigger `sendOwnerReportWeekly` — **Маша/Ирина** (Google
  `summonerx222`). ⚠️ ВАЖНО: storage теперь наполняется PDF при каждом прогоне
  Анны, поэтому старый триггер, найдя PDF за текущую неделю, ОТПРАВИТ дубль
  собственнику. Отключить обязательно.
- Боевой email получателя (Ирина) → `REPORT_TO` в `178:.report_env` (сейчас там
  тестовый `gmdidro@gmail.com`).

**Сделано:** cron `run_weekly.sh` на 178 снят (бэкап `~/AKG/crontab.bak-*`).

## Проверено на проде (2026-07-27)

- agent-metrics принимает/отклоняет по ключу; кладёт в `global.agent_rows`.
- Замещение: агентский reach перекрывает собственный сбор канала, Битрикс-поля целы, дублей нет, 77 строк, akg-report-rows жив.
- Пустой agent_rows → собственный сбор (Дзен reach=1587) — дефолт сохранён.
