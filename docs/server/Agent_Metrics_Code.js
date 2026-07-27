// ═══════════════════════════════════════════════════════════════════════════════
//  POST /webhook/agent-metrics — приём готовых строк «Реестр_факта» от агента
//  agent-mode (Дзен / ВК-органика / Тенчат). Складывает в
//  staticData.agent_rows[week] = { channel: row }; Pull+map подмешивает их по
//  неделя+канал, замещая собственный сбор этих каналов.
//
//  Payload: { week: "YYYY-Www", source, rows: [
//     { week_start, channel, reach, subs_social, comment,
//       subs_absolute?: true }  // subs_absolute → это ТЕКУЩЕЕ число подписчиков
//                               //   (ВК members), ноду просят посчитать Δ
//  ]}
//  Защита: ?key= совпадает с SHARED_KEY.
// ═══════════════════════════════════════════════════════════════════════════════
const inp = $input.first().json;
const body = inp.body || inp;
const key = (inp.query || {}).key;
// Реальный ключ подставляется при деплое на сервер (тот же SHARED_KEY вебхуков,
// что инлайн в остальных нодах — см. документ доступов проекта). В git — плейсхолдер.
const SHARED_KEY = '<SHARED_KEY>';

if (key !== SHARED_KEY) {
  return [{ json: { ok: false, error: 'bad_key' } }];
}
if (!body || !Array.isArray(body.rows)) {
  return [{ json: { ok: false, error: 'malformed_payload', got: Object.keys(body || {}) } }];
}

const week = String(body.week || '');
if (!/^\d{4}-W\d{2}$/.test(week)) {
  return [{ json: { ok: false, error: 'bad_week', week } }];
}

const sd = $getWorkflowStaticData('global');
sd.agent_rows = sd.agent_rows || {};
sd.agent_subs_history = sd.agent_subs_history || {};

const wk = {};                 // строки этой недели (перезапись последним прогоном)
const stored = [];
for (const raw of body.rows) {
  if (!raw || !raw.channel) continue;
  const r = Object.assign({}, raw);

  // Дельта подписчиков: если прислано ТЕКУЩЕЕ число (subs_absolute), считаем
  // Δ = текущее − прошлонедельное из истории. Иначе значение уже прирост.
  if (r.subs_absolute && r.subs_social != null) {
    const hist = sd.agent_subs_history[r.channel] = sd.agent_subs_history[r.channel] || [];
    const cur = Number(r.subs_social);
    // прошлое = последняя запись НЕ этой недели
    let prev = cur;
    for (let i = hist.length - 1; i >= 0; i--) {
      if (hist[i].week !== week) { prev = Number(hist[i].members); break; }
    }
    r.subs_social = cur - prev;
    const ex = hist.find(h => h.week === week);
    if (ex) ex.members = cur; else hist.push({ week, members: cur });
    if (hist.length > 60) sd.agent_subs_history[r.channel] = hist.slice(-60);
  }
  delete r.subs_absolute;

  wk[r.channel] = r;
  stored.push(r.channel);
}
sd.agent_rows[week] = wk;

return [{ json: {
  ok: true,
  week,
  stored,
  count: stored.length,
  source: body.source || 'agent-mode',
} }];
