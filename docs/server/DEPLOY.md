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

## Проверено на проде (2026-07-27)

- agent-metrics принимает/отклоняет по ключу; кладёт в `global.agent_rows`.
- Замещение: агентский reach перекрывает собственный сбор канала, Битрикс-поля целы, дублей нет, 77 строк, akg-report-rows жив.
- Пустой agent_rows → собственный сбор (Дзен reach=1587) — дефолт сохранён.
