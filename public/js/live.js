(() => {
  'use strict';
  // Live backend controls. Hidden on static hosting (no /api). The admin token
  // stays in memory only and is sent solely to this origin's /api/runs.
  const panel = document.querySelector('[data-live-panel]');
  if (!panel) return;
  const status = panel.querySelector('[data-live-status]');
  const out = panel.querySelector('[data-live-run]');
  const form = panel.querySelector('[data-live-form]');
  const text = (el, value) => { el.textContent = value; };

  async function health() {
    try {
      const r = await fetch('/api/health', { cache: 'no-store' });
      if (!r.ok) return;
      const h = await r.json();
      panel.hidden = false;
      text(status, `${h.live_llm_available ? `Grok ready (${h.model})` : 'no provider key: offline only'} · ${h.runs_enabled ? 'runs enabled' : 'runs disabled'}${h.active_run ? ` · running ${h.active_run}` : ''}`);
    } catch (_) { /* static site */ }
  }

  async function poll(id) {
    for (let i = 0; i < 180; i++) {
      const r = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: 'no-store' });
      if (!r.ok) { text(out, `Run ${id}: status unavailable`); return; }
      const run = await r.json();
      text(out, `Run ${run.id} · ${run.mode} · ${run.status} · LLM calls ${run.llm_calls}${run.error ? ` · ${run.error}` : ''}`);
      if (run.status !== 'running') {
        document.querySelector('[data-refresh]')?.click();
        health();
        return;
      }
      await new Promise(res => setTimeout(res, 2000));
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const token = String(data.get('token') || '');
    form.elements.token.value = '';
    text(out, 'Starting…');
    try {
      const r = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ mode: data.get('mode') }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { text(out, `Not started (${r.status}): ${body.detail || 'error'}`); return; }
      poll(body.id);
    } catch (_) { text(out, 'Backend unreachable.'); }
  });

  health();
})();
