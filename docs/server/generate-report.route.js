  'POST /webhook/generate-report': async (q, body, res) => {
    if ((q.key || body.key) !== SHARED_KEY_STORAGE) return sendJson(res, { ok: false, error: 'unauthorized' }, 401);
    const week = (body && body.week) || '';
    if (!/^\d{4}-W\d{2}$/.test(week)) return sendJson(res, { ok: false, error: 'bad_week', week }, 400);
    const testTo = (body && body.test_to) || '';
    const cp = require('child_process');
    // Генерация PDF + отправка живут на 178 (owner-report-pipeline). Дёргаем по ssh.
    const remote = 'bash ~/AKG/owner-report-pipeline/gen_and_send.sh ' + week + (testTo ? ' ' + testTo : '');
    await new Promise((resolve) => {
      cp.execFile('ssh',
        ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', 'mariiastar@178.104.156.39', remote],
        { timeout: 170000 }, (err, stdout, stderr) => {
          const out = ((stdout || '') + ' ' + (stderr || '')).trim();
          const generated = /GENERATED=1/.test(out);
          const sent = /SENT=1/.test(out);
          const m = out.match(/ERROR=([^\s]+)/);
          sendJson(res, {
            ok: generated, generated, sent,
            error: m ? m[1] : (err ? String(err.message).slice(0, 150) : null),
            raw: out.slice(0, 300),
          });
          resolve();
        });
    });
  },
