// "Search & related" tab: keyword search over the user's own cases/evidence/
// chat messages, plus the list of related evidence with the concrete reasons
// (shared values) behind every link. Everything is limited server-side to
// cases the signed-in user is a member of.
const Search = (() => {
  const REASON_ICON = {
    IDENTICAL_FILE: 'hash', SAME_DEVICE: 'cpu', SHARED_PHONE: 'user', SHARED_EMAIL: 'mail', SHARED_IBAN: 'key',
    SHARED_URL: 'link', SHARED_PARTICIPANT: 'user', TEXT_SIMILARITY: 'fileText', SHARED_DATE: 'info', SAME_CAPTURE_DAY: 'info',
  };

  function reasonHtml(r) {
    const label = I18n.t('reason_' + r.type);
    let value = UI.escapeHtml(r.value);
    if (r.type === 'TEXT_SIMILARITY' && r.terms && r.terms.length) {
      value += ` <span class="text-muted">(${I18n.t('sharedTerms')}: ${r.terms.map(UI.escapeHtml).join(', ')})</span>`;
    }
    const weak = r.type === 'SHARED_DATE' || r.type === 'SAME_CAPTURE_DAY';
    return `<li class="${weak ? 'reason-weak' : ''}"><span class="reason-icon">${UI.icon(REASON_ICON[r.type] || 'link', '', 13)}</span> <strong>${label}:</strong> <bdi dir="auto">${value}</bdi></li>`;
  }

  async function renderTab(caseId) {
    const wrap = document.createElement('div');

    const searchCard = document.createElement('div');
    searchCard.className = 'card';
    searchCard.innerHTML = `
      <h3 style="display:flex; align-items:center; gap:8px;">${UI.icon('search', '', 20)} <span>${I18n.t('searchTitle')}</span></h3>
      <p class="text-muted text-sm">${I18n.t('searchHint')}</p>
      <form id="search-form" class="search-form" novalidate>
        <div class="search-input-wrap" style="flex:1; min-width:200px;">
          <span class="search-icon">${UI.icon('search', '', 16)}</span>
          <input type="search" id="search-q" placeholder="${I18n.t('searchPlaceholder')}" aria-label="${I18n.t('searchPlaceholder')}" maxlength="200" />
        </div>
        <select id="search-scope" aria-label="${I18n.t('searchScope')}">
          <option value="case">${I18n.t('searchScopeCase')}</option>
          <option value="all">${I18n.t('searchScopeAll')}</option>
        </select>
        <button type="submit" class="btn btn-primary" id="search-go">${UI.icon('search', '', 15)} <span>${I18n.t('search')}</span></button>
      </form>
      <div id="search-results" class="mt-3" aria-live="polite"></div>
    `;
    wrap.appendChild(searchCard);

    const relCard = document.createElement('div');
    relCard.className = 'card mt-4';
    relCard.innerHTML = `
      <h3 style="display:flex; align-items:center; gap:8px;">${UI.icon('link', '', 20)} <span>${I18n.t('relatedTitle')}</span></h3>
      <p class="text-muted text-sm">${I18n.t('relatedHint')}</p>
      <div id="related-body">${UI.spinner()}</div>
    `;
    wrap.appendChild(relCard);

    const results = searchCard.querySelector('#search-results');
    const openEv = (id) => Evidence.openInspectModal(id);

    function section(title, count, inner) {
      return `<div class="result-section"><h4>${title} <span class="chip-count">${count}</span></h4>${inner}</div>`;
    }

    searchCard.querySelector('#search-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const q = searchCard.querySelector('#search-q').value.trim();
      const scope = searchCard.querySelector('#search-scope').value;
      if (q.length < 2) { results.innerHTML = `<div class="alert alert-warning">${I18n.t('searchTooShort')}</div>`; return; }
      const btn = searchCard.querySelector('#search-go');
      btn.disabled = true;
      results.innerHTML = UI.spinner(I18n.t('searching'));
      try {
        const r = await Api.search(q, scope === 'case' ? caseId : null);
        const total = r.cases.length + r.evidence.length + r.messages.length;
        if (!total) {
          results.innerHTML = `<div class="empty-state"><h3>${I18n.t('searchNoResults')}</h3><p>${I18n.t('searchNoResultsBody', { q: UI.escapeHtml(q) })}</p></div>`;
        } else {
          let html = '';
          if (r.cases.length) {
            html += section(I18n.t('searchSectionCases'), r.cases.length, r.cases.map((c) =>
              `<button type="button" class="result-row" data-case="${c.id}"><span class="case-id-badge">${UI.escapeHtml(c.case_identifier || 'CASE-' + String(c.id).padStart(4, '0'))}</span> <strong dir="auto">${UI.highlight(c.name, q)}</strong></button>`).join(''));
          }
          if (r.evidence.length) {
            html += section(I18n.t('searchEvidence'), r.evidence.length, r.evidence.map((x) => `
              <button type="button" class="result-row" data-ev="${x.evidence_id}">
                <div><strong dir="auto">${UI.highlight(x.title || x.filename, q)}</strong>
                  ${scope === 'all' ? `<span class="text-muted text-xs"> — ${UI.escapeHtml(x.case_name)}</span>` : ''}
                  ${x.matched_in.map((m) => `<span class="chip chip-soft">${I18n.t('matchIn_' + m)}</span>`).join('')}</div>
                <div class="text-muted text-sm" dir="auto">${UI.highlight(x.snippet, q)}</div>
              </button>`).join(''));
          }
          if (r.messages.length) {
            html += section(I18n.t('searchMessages'), r.messages.length, r.messages.map((m) => `
              <button type="button" class="result-row" data-ev="${m.evidence_id}">
                <div class="text-xs text-muted"><strong>${UI.escapeHtml(m.sender || I18n.t('convSystemMessage'))}</strong> · <bdi dir="ltr">${UI.escapeHtml(UI.formatLocalStamp(m.ts))}</bdi> · ${UI.escapeHtml(m.filename)} · #${m.idx} <bdi dir="ltr">${UI.escapeHtml(m.source_ref)}</bdi>${scope === 'all' ? ' · ' + UI.escapeHtml(m.case_name) : ''}</div>
                <div class="text-sm" dir="auto">${UI.highlight(m.snippet, q)}</div>
              </button>`).join(''));
          }
          results.innerHTML = html;
          results.querySelectorAll('[data-ev]').forEach((b) => { b.onclick = () => openEv(Number(b.dataset.ev)); });
          results.querySelectorAll('[data-case]').forEach((b) => {
            b.onclick = () => State.set({ route: { name: 'case', caseId: Number(b.dataset.case), tab: 'overview' } });
          });
        }
      } catch (err) {
        results.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(err))}</div>`;
      }
      btn.disabled = false;
    });

    // --- related evidence --------------------------------------------------------
    const relBody = relCard.querySelector('#related-body');
    try {
      const { relations } = await Api.getRelated(caseId);
      if (!relations.length) {
        relBody.innerHTML = `<div class="empty-state"><h3>${I18n.t('relatedNone')}</h3><p>${I18n.t('relatedNoneBody')}</p></div>`;
      } else {
        relBody.innerHTML = `
          <p class="text-muted text-xs">${I18n.t('relatedLexicalNote')}</p>
          ${relations.map((r) => `
          <div class="relation-card">
            <div class="relation-head">
              <button type="button" class="link-btn" data-ev="${r.evidence_id}" dir="auto">${UI.escapeHtml(r.evidence_name)}</button>
              <span class="relation-arrow">${UI.icon('link', '', 14)}</span>
              <button type="button" class="link-btn" data-ev="${r.other_evidence_id}" dir="auto">${UI.escapeHtml(r.other_evidence_name)}</button>
              ${r.same_case ? `<span class="chip chip-soft">${I18n.t('relatedSameCase')}</span>` : `<button type="button" class="chip chip-link" data-case="${r.other_case_id}">${I18n.t('relatedOtherCase')}: ${UI.escapeHtml(r.other_case_name)}</button>`}
            </div>
            <ul class="reason-list">${r.reasons.map(reasonHtml).join('')}</ul>
          </div>`).join('')}`;
        relBody.querySelectorAll('[data-ev]').forEach((b) => { b.onclick = () => openEv(Number(b.dataset.ev)); });
        relBody.querySelectorAll('[data-case]').forEach((b) => {
          b.onclick = () => State.set({ route: { name: 'case', caseId: Number(b.dataset.case), tab: 'overview' } });
        });
      }
    } catch (e) {
      relBody.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
    }
    return wrap;
  }

  return { renderTab, reasonHtml };
})();
