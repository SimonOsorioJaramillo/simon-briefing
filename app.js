(async function () {
  const dateEl = document.getElementById('date');
  const contentEl = document.getElementById('content');
  const updatedEl = document.getElementById('updated');

  const fmtDate = (iso) => {
    try {
      const d = new Date(iso + 'T00:00:00');
      return d.toLocaleDateString('es-ES', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch {
      return iso;
    }
  };

  const fmtUpdated = (iso) => {
    try {
      return new Date(iso).toLocaleString('es-ES', {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch {
      return iso;
    }
  };

  const esc = (s) =>
    String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));

  const actionBadge = (action) => {
    const a = (action || 'Watch').toLowerCase();
    const cls = a === 'consider' ? 'badge-consider' : a === 'avoid' ? 'badge-avoid' : 'badge-watch';
    return `<span class="badge ${cls}">${esc(action)}</span>`;
  };

  const riskClass = (risk) => {
    const r = (risk || '').toLowerCase();
    if (r.startsWith('baj') || r === 'low') return 'risk-low';
    if (r.startsWith('med') || r === 'medium') return 'risk-medium';
    if (r.startsWith('alt') || r === 'high') return 'risk-high';
    return '';
  };

  const renderMacro = (items) => {
    if (!items || !items.length) return '';
    const lis = items
      .map(
        (m) => `
        <li>
          <span class="bullet">•</span>
          <div>
            ${esc(m.point)}
            ${m.source ? `<span class="source">Fuente: ${esc(m.source)}</span>` : ''}
          </div>
        </li>`
      )
      .join('');
    return `
      <section>
        <h2>Contexto macro</h2>
        <ul class="macro-list">${lis}</ul>
      </section>`;
  };

  const renderWatchlist = (items) => {
    if (!items || !items.length) return '';
    const cards = items
      .map(
        (i) => `
        <article class="idea">
          <div class="idea-head">
            <div class="idea-title">
              ${i.ticker ? `<span class="ticker">${esc(i.ticker)}</span>` : ''}
              ${esc(i.name || '')}
            </div>
            ${actionBadge(i.action)}
          </div>
          <div class="idea-body">
            <p>${esc(i.thesis || '')}</p>
          </div>
          <dl class="idea-meta">
            <dt>Riesgo</dt><dd class="${riskClass(i.risk)}">${esc(i.risk || '—')}</dd>
            <dt>Catalizador</dt><dd>${esc(i.catalyst || '—')}</dd>
            <dt>Nivel a vigilar</dt><dd>${esc(i.level || '—')}</dd>
          </dl>
        </article>`
      )
      .join('');
    return `
      <section>
        <h2>Watchlist del día</h2>
        ${cards}
      </section>`;
  };

  const renderTopPicks = (picks) => {
    if (!picks || !picks.length) return '';
    const cards = picks
      .map(
        (p) => `
        <article class="pick">
          <div class="pick-rank">#${esc(p.rank)}</div>
          <div class="pick-body">
            <div class="pick-head">
              <div class="pick-id">
                <div class="pick-ticker-lg">${esc(p.ticker || '—')}</div>
                <div class="pick-name">${esc(p.name || '')}</div>
              </div>
              ${actionBadge(p.action)}
            </div>
            <div class="pick-reason">${esc(p.reason || '')}</div>
            ${p.role ? `<div class="pick-role"><strong>Rol en portafolio:</strong> ${esc(p.role)}</div>` : ''}
          </div>
        </article>`
      )
      .join('');
    return `
      <section class="top-picks-section">
        <h2>Mis mejores ideas del día</h2>
        <div class="picks-disclaimer">
          Selección personal de Simon Osorio basada en el contexto del día. <strong>No es recomendación de inversión ni asesoría financiera.</strong> Cada idea conlleva riesgo de pérdida. Verificar precios, fundamentos y conveniencia personal antes de cualquier decisión.
        </div>
        ${cards}
      </section>`;
  };

  const renderCaution = (c) => {
    if (!c || !c.summary) return '';
    return `
      <section>
        <h2>Señal de cautela</h2>
        <div class="caution">
          <div class="caution-title">${esc(c.summary)}</div>
          ${c.detail ? `<p style="margin:4px 0 0">${esc(c.detail)}</p>` : ''}
        </div>
      </section>`;
  };

  try {
    const data = window.BRIEFING;
    if (!data) throw new Error('window.BRIEFING no está definido. ¿Cargó data/latest.js?');

    dateEl.textContent = fmtDate(data.date);
    updatedEl.textContent = data.generated_at ? fmtUpdated(data.generated_at) : '—';

    contentEl.innerHTML =
      renderMacro(data.macro) +
      renderWatchlist(data.watchlist) +
      renderCaution(data.caution) +
      renderTopPicks(data.top_picks);
  } catch (err) {
    contentEl.innerHTML = `<div class="error">Error cargando briefing: ${esc(err.message)}</div>`;
  }
})();
