// Conversation viewer: parsed chat content, statistics, in-chat search,
// links to other evidence and an optional AI summary. Message text is
// UNTRUSTED DATA: it is only ever inserted escaped (UI.escapeHtml / highlight)
// and presented as "what was written", never as verified fact.
const Conversation = (() => {
  const PAGE = 200;

  const FORMAT_LABEL = {
    TEXT_TIMESTAMPED: 'convFormatText', TEXT_SPEAKERS: 'convFormatSpeakers', JSON: 'convFormatJson',
    CSV: 'convFormatCsv', PDF_TEXT: 'convFormatPdf', DOCX_TEXT: 'convFormatDocx', OCR_TEXT: 'convFormatOcr',
  };

  const LINK_REASON = {
    FILENAME_MENTION: 'linkFilename', DEVICE_MENTION: 'linkDevice', SHARED_PHONE: 'linkPhone',
    SHARED_EMAIL: 'linkEmail', SHARED_URL: 'linkUrl', SHARED_IBAN: 'linkIban',
  };

  async function render(container, evidenceId, { onOpenEvidence } = {}) {
    container.innerHTML = UI.spinner(I18n.t('convLoading'));
    let data;
    try {
      data = await Api.getConversation(evidenceId, { limit: PAGE });
    } catch (e) {
      container.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(UI.errorMessage(e))}</span></div>`;
      return;
    }
    const meta = data.meta;
    const linksByIdx = {};
    (data.links || []).forEach((l) => { (linksByIdx[l.message_idx] = linksByIdx[l.message_idx] || []).push(l); });

    const participants = meta.participants
      .map((p) => `<span class="chip">${UI.escapeHtml(p.name)} <span class="chip-count">${p.messages}</span></span>`)
      .join('');
    const range = meta.first_ts
      ? `<bdi dir="ltr">${UI.escapeHtml(UI.formatLocalStamp(meta.first_ts))}</bdi> → <bdi dir="ltr">${UI.escapeHtml(UI.formatLocalStamp(meta.last_ts))}</bdi>`
      : I18n.t('convNoDates');
    const stats = data.stats || {};
    const terms = (stats.top_terms || []).map((t) => `<span class="chip chip-soft">${UI.escapeHtml(t.term)} <span class="chip-count">${t.count}</span></span>`).join('');
    const ent = stats.entities || {};
    const entHtml = Object.keys(ent).map((k) =>
      `<div class="text-sm"><strong>${I18n.t('entity_' + k)}:</strong> <bdi dir="ltr" class="mono">${ent[k].map(UI.escapeHtml).join(' · ')}</bdi></div>`
    ).join('');

    container.innerHTML = `
      <div class="ai-tag ai-tag-neutral">${UI.icon('info', '', 14)} <span>${I18n.t('convUntrustedNote')}</span></div>
      <div class="conv-meta mt-3">
        <div><span class="text-muted text-xs">${I18n.t('convFormat')}</span><div>${I18n.t(FORMAT_LABEL[meta.format] || 'convFormatText')}</div></div>
        <div><span class="text-muted text-xs">${I18n.t('convMessages')}</span><div><strong>${meta.message_count}</strong>${meta.truncated ? ` <span class="text-muted text-xs">(${I18n.t('convTruncated')})</span>` : ''}</div></div>
        <div><span class="text-muted text-xs">${I18n.t('convRange')}</span><div class="text-sm">${range}</div></div>
      </div>
      <p class="text-muted text-xs" style="margin:6px 0 0;">${I18n.t('convTimeNote')}${data.notes.date_order_assumed ? ' ' + I18n.t('convDateOrderNote') : ''}</p>
      <div class="mt-3"><span class="text-muted text-xs">${I18n.t('convParticipants')}</span><div class="chip-row">${participants || '—'}</div></div>
      ${terms ? `<div class="mt-3"><span class="text-muted text-xs">${I18n.t('convTopTerms')}</span><div class="chip-row">${terms}</div></div>` : ''}
      ${stats.busiest_day ? `<p class="text-sm mt-2">${I18n.t('convBusiestDay', { date: stats.busiest_day.date, count: stats.busiest_day.messages })}</p>` : ''}
      ${entHtml ? `<div class="mt-2">${entHtml}</div>` : ''}

      <div class="conv-summary mt-4">
        <div class="flex gap-2" style="align-items:center; flex-wrap:wrap;">
          <h5 style="margin:0;">${I18n.t('convSummaryTitle')}</h5>
          <button type="button" class="btn btn-sm" id="conv-sum-btn">${UI.icon('cpu', '', 14)} <span>${meta.summary ? I18n.t('convSummaryRefresh') : I18n.t('convSummaryRun')}</span></button>
        </div>
        <div id="conv-sum-body" class="mt-2">${meta.summary ? '' : `<p class="text-muted text-sm">${I18n.t('convSummaryHint')}</p>`}</div>
      </div>

      <div class="conv-search mt-4">
        <div class="search-input-wrap" style="flex:1; min-width:200px;">
          <span class="search-icon">${UI.icon('search', '', 16)}</span>
          <input type="search" id="conv-q" placeholder="${I18n.t('convSearchPlaceholder')}" aria-label="${I18n.t('convSearchPlaceholder')}" maxlength="200" />
        </div>
        <button type="button" class="btn btn-sm btn-ghost" id="conv-clear" style="display:none;">${UI.icon('x', '', 14)} <span>${I18n.t('clear')}</span></button>
      </div>
      <div id="conv-status" class="text-muted text-sm mt-2" aria-live="polite"></div>
      <div id="conv-list" class="conv-list mt-2" dir="auto"></div>
      <div id="conv-more" class="mt-2" style="text-align:center;"></div>
    `;

    const listEl = container.querySelector('#conv-list');
    const statusEl = container.querySelector('#conv-status');
    const moreEl = container.querySelector('#conv-more');
    const qInput = container.querySelector('#conv-q');
    const clearBtn = container.querySelector('#conv-clear');
    let loaded = 0;

    function messageEl(m, q) {
      const el = document.createElement('div');
      el.className = 'conv-msg' + (m.sender ? '' : ' conv-system');
      el.id = `conv-msg-${m.idx}`;
      const links = (linksByIdx[m.idx] || []).map((l) =>
        `<button type="button" class="chip chip-link" data-ev="${l.evidence_id}" title="${UI.escapeHtml(l.value)}">${UI.icon('link', '', 12)} ${I18n.t(LINK_REASON[l.reason] || 'linkGeneric')}: ${UI.escapeHtml(l.evidence_name)}</button>`
      ).join('');
      el.innerHTML = `
        <div class="conv-msg-head">
          <span class="conv-sender">${m.sender ? UI.escapeHtml(m.sender) : I18n.t('convSystemMessage')}</span>
          <span class="conv-time"><bdi dir="ltr">${UI.escapeHtml(m.ts ? UI.formatLocalStamp(m.ts) : m.ts_raw || '')}</bdi></span>
          <span class="conv-ref" title="${I18n.t('convSourceRef')}">#${m.idx} · <bdi dir="ltr">${UI.escapeHtml(m.source_ref)}</bdi></span>
        </div>
        <div class="conv-body">${UI.highlight(m.body, q)}</div>
        ${links ? `<div class="chip-row" style="margin-top:6px;">${links}</div>` : ''}
      `;
      el.querySelectorAll('[data-ev]').forEach((b) => {
        b.onclick = () => onOpenEvidence && onOpenEvidence(Number(b.dataset.ev));
      });
      return el;
    }

    function showMessages(msgs, q, append) {
      if (!append) listEl.innerHTML = '';
      msgs.forEach((m) => listEl.appendChild(messageEl(m, q)));
    }

    function renderMore() {
      moreEl.innerHTML = '';
      if (loaded < meta.message_count && !qInput.value.trim()) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn btn-sm';
        b.textContent = I18n.t('convLoadMore', { shown: loaded, total: meta.message_count });
        b.onclick = async () => {
          b.disabled = true;
          try {
            const next = await Api.getConversation(evidenceId, { offset: loaded, limit: PAGE });
            showMessages(next.messages, '', true);
            loaded += next.messages.length;
          } catch (e) { UI.toast(UI.errorMessage(e), 'error'); }
          renderMore();
        };
        moreEl.appendChild(b);
      }
    }

    async function runSearch() {
      const q = qInput.value.trim();
      clearBtn.style.display = q ? '' : 'none';
      if (q.length < 2) {
        statusEl.textContent = '';
        showMessages(data.messages, '', false);
        loaded = data.messages.length;
        renderMore();
        return;
      }
      statusEl.textContent = I18n.t('convSearching');
      try {
        const res = await Api.getConversation(evidenceId, { q, limit: PAGE });
        statusEl.textContent = res.messages.length
          ? I18n.t('convMatches', { count: res.messages.length })
          : I18n.t('convNoMatches', { q });
        showMessages(res.messages, q, false);
        moreEl.innerHTML = '';
      } catch (e) {
        statusEl.textContent = UI.errorMessage(e);
      }
    }

    let timer;
    qInput.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 260); });
    clearBtn.onclick = () => { qInput.value = ''; runSearch(); };

    showMessages(data.messages, '', false);
    loaded = data.messages.length;
    renderMore();
    if (data.messages.length === 0) listEl.innerHTML = `<p class="text-muted text-sm">${I18n.t('convEmpty')}</p>`;

    // --- AI summary (every point carries message numbers) -------------------
    const sumBody = container.querySelector('#conv-sum-body');
    const sumBtn = container.querySelector('#conv-sum-btn');

    function jumpTo(n) {
      qInput.value = '';
      clearBtn.style.display = 'none';
      statusEl.textContent = '';
      Api.getConversation(evidenceId, { offset: Math.max(0, n - 4), limit: 12 }).then((res) => {
        showMessages(res.messages, '', false);
        moreEl.innerHTML = '';
        const target = listEl.querySelector(`#conv-msg-${n}`);
        if (target) { target.classList.add('conv-flash'); target.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
        statusEl.textContent = I18n.t('convContextView', { n });
      }).catch((e) => UI.toast(UI.errorMessage(e), 'error'));
    }

    function renderSummary(res) {
      if (!res) { sumBody.innerHTML = ''; return; }
      if (res.status === 'DISABLED') { sumBody.innerHTML = `<div class="alert alert-warning">${I18n.t('aiDisabled')}</div>`; return; }
      if (res.status === 'FAILED') {
        sumBody.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(I18n.getLang() === 'ar' ? res.message_ar : res.message_en)}</div>`;
        return;
      }
      const refs = (arr) => arr.map((r) => `<button type="button" class="chip chip-link" data-jump="${r}">#${r}</button>`).join('');
      sumBody.innerHTML = `
        <div class="ai-tag">${UI.icon('alertTriangle', '', 14)} <span>${I18n.t('aiAutomatedEstimate')}</span></div>
        ${res.partial ? `<p class="text-muted text-xs">${I18n.t('convSummaryPartial', { shown: res.messages_shown, total: res.messages_total })}</p>` : ''}
        <p>${UI.escapeHtml(res.summary || '')}</p>
        ${res.topics && res.topics.length ? `<h6>${I18n.t('convTopics')}</h6><ul>${res.topics.map((t) => `<li>${UI.escapeHtml(t.title)} <span class="chip-row inline">${refs(t.refs)}</span></li>`).join('')}</ul>` : ''}
        ${res.key_events && res.key_events.length ? `<h6>${I18n.t('convKeyEvents')}</h6><ul>${res.key_events.map((t) => `<li>${UI.escapeHtml(t.description)} <span class="chip-row inline">${refs(t.refs)}</span></li>`).join('')}</ul>` : ''}
        ${res.generated_at ? `<div class="text-muted text-xs">${I18n.t('lastAnalyzedAt')}: ${UI.dateHtml(res.generated_at)}</div>` : ''}`;
      sumBody.querySelectorAll('[data-jump]').forEach((b) => { b.onclick = () => jumpTo(Number(b.dataset.jump)); });
    }
    renderSummary(meta.summary);

    sumBtn.onclick = async () => {
      sumBtn.disabled = true;
      sumBody.innerHTML = UI.spinner(I18n.t('analyzing'));
      try {
        const res = await Api.summarizeConversation(evidenceId);
        renderSummary(res);
        if (res.status === 'SUCCESS') sumBtn.querySelector('span').textContent = I18n.t('convSummaryRefresh');
      } catch (e) {
        sumBody.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
      }
      sumBtn.disabled = false;
    };
  }

  return { render };
})();
