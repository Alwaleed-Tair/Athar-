const Cases = (() => {
  async function renderList() {
    const wrap = document.createElement('div');

    const header = document.createElement('div');
    header.className = 'case-list-header';
    header.innerHTML = `
      <h1>${I18n.t('cases')}</h1>
    `;
    const actions = document.createElement('div');
    actions.className = 'flex gap-2';
    const searchInput = document.createElement('input');
    searchInput.placeholder = I18n.t('searchCases');
    searchInput.style.width = '220px';
    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.textContent = I18n.t('newCase');
    actions.appendChild(searchInput);
    actions.appendChild(newBtn);
    header.appendChild(actions);
    wrap.appendChild(header);

    const listArea = document.createElement('div');
    wrap.appendChild(listArea);

    async function loadAndRenderList(search) {
      listArea.innerHTML = `<p class="text-muted">…</p>`;
      let cases;
      try {
        cases = await Api.listCases(search);
      } catch (e) {
        listArea.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        return;
      }
      listArea.innerHTML = '';
      if (cases.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state card';
        empty.innerHTML = `<h3>${I18n.t('noCasesTitle')}</h3><p>${I18n.t('noCasesBody')}</p>`;
        listArea.appendChild(empty);
        return;
      }
      const grid = document.createElement('div');
      grid.className = 'case-grid';
      cases.forEach((c) => {
        const card = document.createElement('div');
        card.className = 'case-card';
        card.innerHTML = `
          <div class="case-name">${UI.escapeHtml(c.name)}</div>
          <div class="case-meta">${UI.escapeHtml(c.description || '')}</div>
          <div class="mt-3"><span class="badge">${UI.escapeHtml(c.status)}</span></div>
        `;
        card.onclick = () => State.set({ route: { name: 'case', caseId: c.id, tab: 'overview' } });
        grid.appendChild(card);
      });
      listArea.appendChild(grid);
    }

    let debounceTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => loadAndRenderList(searchInput.value), 250);
    });

    newBtn.onclick = () => openCreateCaseModal(() => loadAndRenderList(searchInput.value));

    await loadAndRenderList('');
    return wrap;
  }

  function openDeleteCaseModal(caseId, caseName) {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header"><h3>${I18n.t('deleteCase')}</h3></div>
      <p>${I18n.t('deleteCaseConfirm', { name: UI.escapeHtml(caseName) })}</p>
      <p class="text-muted text-sm">${I18n.t('deleteCaseNote')}</p>
      <div id="dc-error"></div>
      <div class="flex gap-2" style="justify-content:flex-end">
        <button type="button" id="dc-cancel" class="btn">${I18n.t('cancel')}</button>
        <button type="button" id="dc-confirm" class="btn btn-danger">${I18n.t('deleteCase')}</button>
      </div>
    `;
    const { close } = UI.openModal(content);
    content.querySelector('#dc-cancel').onclick = close;
    content.querySelector('#dc-confirm').onclick = async () => {
      const btn = content.querySelector('#dc-confirm');
      btn.disabled = true;
      try {
        await Api.deleteCase(caseId);
        Notifications.refresh();
        close();
        State.set({ route: { name: 'cases' } });
      } catch (err) {
        btn.disabled = false;
        content.querySelector('#dc-error').innerHTML =
          `<div class="alert alert-danger">${UI.escapeHtml(err.message)}</div>`;
      }
    };
  }

  function openCreateCaseModal(onCreated) {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header"><h3>${I18n.t('createCase')}</h3></div>
      <div id="create-case-error"></div>
      <form id="create-case-form">
        <div class="field">
          <label>${I18n.t('caseName')}</label>
          <input type="text" name="name" required />
        </div>
        <div class="field">
          <label>${I18n.t('description')}</label>
          <textarea name="description" rows="3"></textarea>
        </div>
        <div class="flex gap-2" style="justify-content:flex-end">
          <button type="button" id="cc-cancel" class="btn">${I18n.t('cancel')}</button>
          <button type="submit" class="btn btn-primary">${I18n.t('create')}</button>
        </div>
      </form>
    `;
    const { close } = UI.openModal(content);
    content.querySelector('#cc-cancel').onclick = close;
    content.querySelector('#create-case-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await Api.createCase({ name: fd.get('name'), description: fd.get('description') || '' });
        Notifications.refresh();
        close();
        onCreated && onCreated();
      } catch (err) {
        content.querySelector('#create-case-error').innerHTML =
          `<div class="alert alert-danger">${UI.escapeHtml(err.message)}</div>`;
      }
    });
  }

  async function renderDetail(caseId, tab) {
    const wrap = document.createElement('div');
    let caseData;
    try {
      caseData = await Api.getCase(caseId);
    } catch (e) {
      wrap.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>
        <button class="btn" id="back-btn">${I18n.t('back')}</button>`;
      wrap.querySelector('#back-btn').onclick = () => State.set({ route: { name: 'cases' } });
      return wrap;
    }

    const backBtn = document.createElement('button');
    backBtn.className = 'btn btn-ghost btn-sm';
    backBtn.textContent = `← ${I18n.t('back')}`;
    backBtn.onclick = () => State.set({ route: { name: 'cases' } });
    wrap.appendChild(backBtn);

    const heading = document.createElement('div');
    heading.className = 'mt-3 flex';
    heading.style.justifyContent = 'space-between';
    heading.style.alignItems = 'flex-start';
    heading.style.gap = '12px';
    heading.innerHTML = `
      <div>
        <h1>${UI.escapeHtml(caseData.name)}</h1>
        <p class="text-muted">${UI.escapeHtml(caseData.description || '')}</p>
      </div>
    `;
    if (State.get().user && State.get().user.role === 'ADMIN') {
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger btn-sm';
      deleteBtn.textContent = I18n.t('deleteCase');
      deleteBtn.onclick = () => openDeleteCaseModal(caseId, caseData.name);
      heading.appendChild(deleteBtn);
    }
    wrap.appendChild(heading);

    const tabs = document.createElement('div');
    tabs.className = 'tabs';
    const tabDefs = [
      { id: 'overview', label: I18n.t('overview') },
      { id: 'evidence', label: I18n.t('evidenceTab') },
      { id: 'map', label: I18n.t('evidenceMap') },
      { id: 'chain', label: I18n.t('chainTab') },
    ];
    tabDefs.forEach((t) => {
      const el = document.createElement('div');
      el.className = 'tab' + (tab === t.id ? ' active' : '');
      el.textContent = t.label;
      el.onclick = () => State.set({ route: { name: 'case', caseId, tab: t.id } });
      tabs.appendChild(el);
    });
    wrap.appendChild(tabs);

    const body = document.createElement('div');
    wrap.appendChild(body);

    if (tab === 'overview') {
      const alertsEl = await renderCrossCaseAlerts(caseId);
      if (alertsEl) body.appendChild(alertsEl);
      body.appendChild(await renderCaseSummary(caseId));
      body.appendChild(await renderOverview(caseId, caseData));
    } else if (tab === 'evidence') {
      body.appendChild(await Evidence.renderTab(caseId));
    } else if (tab === 'map') {
      body.appendChild(await EvidenceMap.renderTab(caseId));
    } else if (tab === 'chain') {
      body.appendChild(await Chain.renderTab(caseId));
    }

    return wrap;
  }

  async function renderCrossCaseAlerts(caseId) {
    let data;
    try {
      data = await Api.getCrossCaseAlerts(caseId);
    } catch (e) {
      return null; // don't block the whole overview tab over this
    }
    const alerts = data.alerts || [];
    if (alerts.length === 0) return null;

    const el = document.createElement('div');
    el.className = 'card';
    el.style.marginBlockEnd = '16px';

    const title = document.createElement('h3');
    title.textContent = `⚠ ${I18n.t('crossCaseAlertsTitle')}`;
    el.appendChild(title);

    alerts.forEach((a) => {
      const row = document.createElement('div');
      row.className = 'alert alert-warning mt-3';
      row.style.marginBlockEnd = '0';
      if (a.visible) {
        row.textContent = a.other_evidence_filename
          ? I18n.t('crossCaseAlertVisible', {
              filename: a.evidence_filename,
              otherFilename: a.other_evidence_filename,
              caseName: a.other_case_name,
            })
          : I18n.t('crossCaseAlertVisibleCaseOnly', {
              filename: a.evidence_filename,
              caseName: a.other_case_name,
            });
        row.style.cursor = 'pointer';
        row.onclick = () => State.set({ route: { name: 'case', caseId: a.other_case_id, tab: 'overview' } });
      } else {
        row.textContent = I18n.t('crossCaseAlertHidden', { filename: a.evidence_filename });
      }
      el.appendChild(row);
    });

    return el;
  }

  async function renderCaseSummary(caseId) {
    const el = document.createElement('div');
    el.className = 'card mt-4';
    el.innerHTML = `<h3>${I18n.t('caseSummaryTitle')}</h3><div id="summary-body" class="mt-3"><p class="text-muted">…</p></div>`;
    const body = el.querySelector('#summary-body');

    function renderResult(data) {
      body.innerHTML = '';

      if (data.status === 'DISABLED') {
        const div = document.createElement('div');
        div.className = 'alert alert-warning';
        div.textContent = I18n.t('aiDisabled');
        body.appendChild(div);
        return;
      }
      if (data.status === 'NO_EVIDENCE') {
        const p = document.createElement('p');
        p.className = 'text-muted text-sm';
        p.textContent = I18n.t('caseSummaryNoEvidence');
        body.appendChild(p);
        return;
      }
      if (data.status === 'FAILED') {
        const div = document.createElement('div');
        div.className = 'alert alert-danger';
        div.textContent = data.message_en || I18n.t('genericError');
        body.appendChild(div);
        appendRefreshButton();
        return;
      }

      // SUCCESS
      const tag = document.createElement('div');
      tag.className = 'ai-tag';
      tag.textContent = `⚠ ${I18n.t('aiAutomatedEstimate')}`;
      body.appendChild(tag);

      const textEl = document.createElement('div');
      textEl.className = 'mt-2';
      textEl.style.whiteSpace = 'pre-wrap';
      textEl.textContent = data.summary_text;
      body.appendChild(textEl);

      if (data.generated_at) {
        const meta = document.createElement('div');
        meta.className = 'text-muted text-xs mt-3';
        meta.textContent = `${I18n.t('caseSummaryGeneratedAt')}: ${data.generated_at}`;
        body.appendChild(meta);
      }

      appendRefreshButton();
    }

    function appendRefreshButton() {
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm mt-3';
      btn.textContent = I18n.t('caseSummaryRefresh');
      btn.onclick = refresh;
      body.appendChild(btn);
    }

    async function refresh() {
      body.innerHTML = `<p class="text-muted text-sm">${I18n.t('caseSummaryGenerating')}</p>`;
      try {
        const data = await Api.generateCaseSummary(caseId);
        renderResult(data);
      } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
      }
    }

    async function load() {
      let data;
      try {
        data = await Api.getCaseSummary(caseId);
      } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        return;
      }
      const needsGeneration =
        data.status === 'NOT_GENERATED' ||
        (data.status === 'SUCCESS' && data.lang && data.lang !== I18n.getLang());
      if (needsGeneration) {
        // Auto-generate the first time this case has no summary yet, and
        // also when the cached one is in a different language than the
        // current UI (switching AR/EN shouldn't leave a stale-language
        // summary on screen). Every other refresh is manual (the button).
        body.innerHTML = `<p class="text-muted text-sm">${I18n.t('caseSummaryGenerating')}</p>`;
        try {
          data = await Api.generateCaseSummary(caseId);
        } catch (e) {
          body.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
          return;
        }
      }
      renderResult(data);
    }

    await load();
    return el;
  }

  async function renderOverview(caseId, caseData) {
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `
      <div class="flex gap-3" style="flex-wrap:wrap">
        <div style="min-width:160px">
          <div class="text-muted text-sm">${I18n.t('evidenceCount')}</div>
          <div style="font-size:1.6rem;font-weight:700">${caseData.evidence_count}</div>
        </div>
        <div style="min-width:200px">
          <div class="text-muted text-sm">${I18n.t('chainStatus')}</div>
          <div id="overview-chain-status">…</div>
        </div>
      </div>
      <div class="mt-4">
        <button class="btn btn-primary" id="overview-verify-btn">${I18n.t('verifyChain')}</button>
      </div>
    `;

    const statusEl = el.querySelector('#overview-chain-status');
    const verifyBtn = el.querySelector('#overview-verify-btn');

    async function runVerify() {
      verifyBtn.disabled = true;
      verifyBtn.textContent = I18n.t('verifying');
      statusEl.innerHTML = '…';
      try {
        const result = await Api.verifyCaseChain(caseId);
        renderVerifyResult(statusEl, result);
      } catch (e) {
        statusEl.innerHTML = `<span class="badge bad">${I18n.t('genericError')}</span>`;
      }
      verifyBtn.disabled = false;
      verifyBtn.textContent = I18n.t('verifyChain');
    }
    verifyBtn.onclick = runVerify;
    await runVerify();

    return el;
  }

  function renderVerifyResult(el, result) {
    if (result.intact) {
      el.innerHTML = `<span class="badge ok">${I18n.t('intact')}</span> <span class="text-muted text-sm">${result.records_checked} ${I18n.t('recordsChecked')}</span>`;
    } else {
      el.innerHTML = `<span class="badge bad">${I18n.t('broken')}</span> <span class="text-muted text-sm">${I18n.t('firstBrokenAt', { seq: result.first_broken_seq })}</span>`;
    }
  }

  return { renderList, renderDetail, renderVerifyResult };
})();