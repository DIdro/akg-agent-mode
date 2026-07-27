// ── Замещение каналов данными агента (agent-mode: Дзен / ВК-органика / Тенчат) ──
// По каналам, для которых агент прислал строки (staticData.agent_rows[weekKey]),
// его метрики охвата — источник истины: перезаписываем reach/subs_social/comment
// в строке канала. Битрикс-лиды/сделки/выручка по каналу (смерджены выше) и
// собственный сбор Дзен/ВК (reach) при этом замещаются агентскими значениями.
{
  const __sd = $getWorkflowStaticData('global');
  const __agentWk = (__sd.agent_rows || {})[weekKey] || {};
  for (const __channel of Object.keys(__agentWk)) {
    const __ar = __agentWk[__channel];
    let __row = registry.find(x => x.channel === __channel && x.week_start === weekStartDdmm
                                   && (x.audience || '') === '' && (x.event || '') === '');
    if (!__row) {
      __row = { week_start: weekStartDdmm, audience: '', event: '', channel: __channel,
        expenses: 0, reach: 0, clicks: 0, visits: 0, users: 0,
        subs_social: 0, subs_email: 0, subs_bot: 0, leads: 0, qleads: 0,
        deals: 0, won_deals: 0, participants: 0, revenue: 0, comment: '',
        _unresolved: false, _utm_hint: '' };
      registry.push(__row);
    }
    __row.reach = Math.round(Number(__ar.reach) || 0);
    if (__ar.subs_social !== undefined && __ar.subs_social !== null) __row.subs_social = Number(__ar.subs_social);
    if (__ar.comment) __row.comment = __ar.comment;
    __row._agent = true;
  }
}

