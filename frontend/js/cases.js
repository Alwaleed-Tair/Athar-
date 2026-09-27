const Cases = (() => {
  async function renderList() {
    const wrap = document.createElement('div');

    // Header with Page Title and New Case CTA button
    const header = document.createElement('div');
    header.className = 'case-list-header';
    header.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="color:var(--color-primary); display:flex; align-items:center;">
          ${UI.icon('folder', '', 26)}
        </span>
        <h1 style="margin:0;">${I18n.t('cases')}</h1>
      </div>
      <div>
        <button type="button" class="btn btn-primary btn-neon" id="btn-create-case-main">
          ${UI.icon('plus', '', 18)}
          <span>${I18n.t('newCase')}</span>
        </button>
      </div>
    `;
    wrap.appendChild(header);

    // Filter Section (قسم الفلترة)
    const filterSection = document.createElement('div');
    filterSection.className = 'filter-section-bar';
    filterSection.innerHTML = `
      <div class="filter-title">
        ${UI.icon('filter', '', 17)}
        <span>${I18n.t('filterSection')}</span>
      </div>
      <div class="filter-group">
        <select id="filter-status" class="filter-select">
          <option value="ALL">${I18n.t('allStatuses')}</option>
          <option value="OPEN">${I18n.t('statusActive')}</option>
          <option value="PENDING">${I18n.t('statusPending')}</option>
          <option value="CLOSED">${I18n.t('statusClosed')}</option>
        </select>
        <select id="filter-priority" class="filter-select">
          <option value="ALL">${I18n.t('allPriorities')}</option>
          <option value="CRITICAL">${I18n.t('priorityCritical')}</option>
          <option value="HIGH">${I18n.t('priorityHigh')}</option>
          <option value="MEDIUM">${I18n.t('priorityMedium')}</option>
          <option value="LOW">${I18n.t('priorityLow')}</option>
        </select>
        <div class="search-input-wrap">
          <span style="position:absolute; inset-inline-start:10px; top:50%; transform:translateY(-50%); color:var(--color-text-muted); display:flex; align-items:center; pointer-events:none;">
            ${UI.icon('search', '', 16)}
          </span>
          <input type="text" id="filter-search" placeholder="${I18n.t('searchCases')}" />
        </div>
      </div>
    `;
    wrap.appendChild(filterSection);

    const listArea = document.createElement('div');
    wrap.appendChild(listArea);

    const searchInput = filterSection.querySelector('#filter-search');
    const statusSelect = filterSection.querySelector('#filter-status');
    const prioritySelect = filterSection.querySelector('#filter-priority');
    const newBtn = header.querySelector('#btn-create-case-main');

    async function loadAndRenderList() {
      listArea.innerHTML = `<p class="text-muted" style="text-align:center; padding:30px;">…</p>`;
      let cases;
      try {
        const sVal = searchInput.value.trim();
        const stVal = statusSelect.value;
        const prVal = prioritySelect.value;
        cases = await Api.listCases(sVal, stVal, prVal);
      } catch (e) {
        listArea.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 18)} <span>${I18n.t('genericError')}</span></div>`;
        return;
      }

      listArea.innerHTML = '';
      if (!cases || cases.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state card';
        empty.innerHTML = `
          <div style="color:var(--color-cyan); margin-bottom:12px; display:flex; justify-content:center;">
            ${UI.icon('folder', '', 48)}
          </div>
          <h3>${I18n.t('noCasesTitle')}</h3>
          <p>${I18n.t('noCasesBody')}</p>
        `;
        listArea.appendChild(empty);
        return;
      }

      const grid = document.createElement('div');
      grid.className = 'case-grid';

      cases.forEach((c) => {
        const card = document.createElement('div');
        card.className = 'case-card';

        // Format identifier (e.g. 10 digits or fallback)
        const caseIdDisplay = c.case_identifier ? UI.escapeHtml(c.case_identifier) : `CASE-${String(c.id).padStart(4, '0')}`;
        
        // Status badge class
        let statusClass = 'badge-active';
        let statusLabel = I18n.t('statusActive');
        if (c.status === 'PENDING') {
          statusClass = 'badge-pending';
          statusLabel = I18n.t('statusPending');
        } else if (c.status === 'CLOSED') {
          statusClass = 'badge-closed';
          statusLabel = I18n.t('statusClosed');
        }

        // Priority badge class
        let priorityClass = 'badge-medium';
        let priorityLabel = I18n.t('priorityMedium');
        if (c.priority === 'CRITICAL') {
          priorityClass = 'badge-critical';
          priorityLabel = I18n.t('priorityCritical');
        } else if (c.priority === 'HIGH') {
          priorityClass = 'badge-high';
          priorityLabel = I18n.t('priorityHigh');
        } else if (c.priority === 'LOW') {
          priorityClass = 'badge-low';
          priorityLabel = I18n.t('priorityLow');
        }

        // Classification display
        let classLabel = c.classification || 'RESTRICTED';
        if (classLabel === 'TOP_SECRET') classLabel = I18n.t('classificationTopSecret');
        else if (classLabel === 'RESTRICTED') classLabel = I18n.t('classificationRestricted');
        else if (classLabel === 'CONFIDENTIAL') classLabel = I18n.t('classificationConfidential');
        else if (classLabel === 'INTERNAL') classLabel = I18n.t('classificationInternal');

        card.innerHTML = `
          <div class="case-card-header">
            <span class="case-id-badge">${caseIdDisplay}</span>
            <span class="ui-badge ${statusClass}">
              ${statusLabel}
            </span>
          </div>
          <div class="case-name">${UI.escapeHtml(c.name)}</div>
          <div class="case-meta">${UI.escapeHtml(c.description || '')}</div>
          <div class="case-badges-row">
            <span class="ui-badge ${priorityClass}">
              ${priorityLabel}
            </span>
            <span class="ui-badge" style="background:rgba(0,180,255,0.08); color:var(--color-cyan); border-color:rgba(0,180,255,0.25);">
              ${UI.icon('shield', '', 12)} ${UI.escapeHtml(classLabel)}
            </span>
          </div>
          <div class="case-card-footer">
            <span style="display:flex; align-items:center; gap:5px;">
              ${UI.icon('file', '', 14)}
              <span>${I18n.t('caseFilesCount', { count: c.evidence_count || 0 })}</span>
            </span>
            <span style="display:flex; align-items:center; gap:5px;">
              ${UI.icon('user', '', 13)}
              <span>${UI.escapeHtml(c.creator_full_name || c.creator_username || '')}</span>
            </span>
          </div>
        `;

        card.onclick = () => State.set({ route: { name: 'case', caseId: c.id, tab: 'overview' } });
        grid.appendChild(card);
      });

      listArea.appendChild(grid);
    }

    let debounceTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadAndRenderList, 220);
    });
    statusSelect.addEventListener('change', loadAndRenderList);
    prioritySelect.addEventListener('change', loadAndRenderList);

    newBtn.onclick = () => openCreateCaseModal(loadAndRenderList);

    await loadAndRenderList();
    return wrap;
  }

  function openDeleteCaseModal(caseId, caseName) {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="display:flex; align-items:center; gap:8px;">
          ${UI.icon('trash', '', 20)}
          <span>${I18n.t('deleteCase')}</span>
        </h3>
      </div>
      <p>${I18n.t('deleteCaseConfirm', { name: UI.escapeHtml(caseName) })}</p>
      <p class="text-muted text-sm">${I18n.t('deleteCaseNote')}</p>
      <div id="dc-error"></div>
      <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
        <button type="button" id="dc-cancel" class="btn">${I18n.t('cancel')}</button>
        <button type="button" id="dc-confirm" class="btn btn-danger">
          ${UI.icon('trash', '', 16)}
          <span>${I18n.t('deleteCase')}</span>
        </button>
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

  // Matches Page 3 bottom exact specification
  function openCreateCaseModal(onCreated) {
    // Generate suggested 10-digit numeric ID
    const suggestedId = String(Math.floor(1000000000 + Math.random() * 9000000000));

    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <div>
          <h3 style="margin:0; display:flex; align-items:center; gap:8px;">
            ${UI.icon('folder', '', 20)}
            <span>${I18n.t('initiateForensicCase')}</span>
          </h3>
          <div class="text-muted text-xs" style="margin-top:2px;">
            ${I18n.t('createCaseContainer')}
          </div>
        </div>
      </div>
      <div id="create-case-error"></div>
      <form id="create-case-form">
        <!-- Field 1: Case Identifier (10 digits) -->
        <div class="field">
          <label for="cc-id">${I18n.t('caseIdLabel')}</label>
          <input 
            type="text" 
            id="cc-id"
            name="case_identifier" 
            pattern="[0-9]{10}" 
            maxlength="10" 
            value="${suggestedId}" 
            required 
          />
          <div class="field-hint-box">
            ${I18n.t('caseIdHint')}
          </div>
        </div>

        <!-- Field 2: Case Title / Name -->
        <div class="field">
          <label for="cc-name">${I18n.t('caseTitleLabel')}</label>
          <input 
            type="text" 
            id="cc-name"
            name="name" 
            placeholder="TEST-CASE-001" 
            required 
          />
          <div class="field-hint-box">
            ${I18n.t('caseTitleHint')}
          </div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
          <!-- Field 3: Priority -->
          <div class="field">
            <label for="cc-priority">${I18n.t('prioritySelect')}</label>
            <select id="cc-priority" name="priority">
              <option value="CRITICAL">${I18n.t('priorityCritical')}</option>
              <option value="HIGH">${I18n.t('priorityHigh')}</option>
              <option value="MEDIUM" selected>${I18n.t('priorityMedium')}</option>
              <option value="LOW">${I18n.t('priorityLow')}</option>
            </select>
          </div>

          <!-- Field 4: Classification Tag -->
          <div class="field">
            <label for="cc-classification">${I18n.t('classificationSelect')}</label>
            <select id="cc-classification" name="classification">
              <option value="RESTRICTED" selected>${I18n.t('classificationRestricted')}</option>
              <option value="CONFIDENTIAL">${I18n.t('classificationConfidential')}</option>
              <option value="TOP_SECRET">${I18n.t('classificationTopSecret')}</option>
              <option value="INTERNAL">${I18n.t('classificationInternal')}</option>
            </select>
          </div>
        </div>

        <!-- Field 5: Status -->
        <div class="field">
          <label for="cc-status">${I18n.t('statusSelect')}</label>
          <select id="cc-status" name="status">
            <option value="OPEN" selected>${I18n.t('statusActive')}</option>
            <option value="PENDING">${I18n.t('statusPending')}</option>
            <option value="CLOSED">${I18n.t('statusClosed')}</option>
          </select>
        </div>

        <!-- Field 6: Brief Description -->
        <div class="field">
          <label for="cc-desc">${I18n.t('initialDescription')}</label>
          <textarea id="cc-desc" name="description" rows="3" placeholder="Brief initial description..."></textarea>
        </div>

        <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
          <button type="button" id="cc-cancel" class="btn">${I18n.t('cancel')}</button>
          <button type="submit" class="btn btn-primary btn-neon" id="cc-submit">
            ${UI.icon('plus', '', 16)}
            <span>${I18n.t('create')}</span>
          </button>
        </div>
      </form>
    `;

    const { close } = UI.openModal(content);
    content.querySelector('#cc-cancel').onclick = close;

    content.querySelector('#create-case-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const submitBtn = content.querySelector('#cc-submit');
      const errBox = content.querySelector('#create-case-error');

      const caseIdInput = (fd.get('case_identifier') || '').trim();
      if (!/^\d{10}$/.test(caseIdInput)) {
        errBox.innerHTML = `<div class="alert alert-danger">${I18n.t('caseIdHint')}</div>`;
        return;
      }

      submitBtn.disabled = true;
      try {
        await Api.createCase({
          name: fd.get('name'),
          description: fd.get('description') || '',
          case_identifier: caseIdInput,
          priority: fd.get('priority') || 'MEDIUM',
          classification: fd.get('classification') || 'RESTRICTED',
          status: fd.get('status') || 'OPEN',
        });
        Notifications.refresh();
        close();
        onCreated && onCreated();
      } catch (err) {
        submitBtn.disabled = false;
        errBox.innerHTML =
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
      wrap.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 18)} <span>${I18n.t('genericError')}</span></div>
        <button class="btn" id="back-btn">${UI.icon('arrowLeft', '', 16)} ${I18n.t('back')}</button>`;
      wrap.querySelector('#back-btn').onclick = () => State.set({ route: { name: 'cases' } });
      return wrap;
    }

    const backBtn = document.createElement('button');
    backBtn.className = 'btn btn-ghost btn-sm';
    backBtn.innerHTML = `${UI.icon('arrowLeft', '', 15)} <span>${I18n.t('back')}</span>`;
    backBtn.onclick = () => State.set({ route: { name: 'cases' } });
    wrap.appendChild(backBtn);

    const heading = document.createElement('div');
    heading.className = 'mt-3 flex';
    heading.style.justifyContent = 'space-between';
    heading.style.alignItems = 'flex-start';
    heading.style.gap = '12px';

    const caseIdentifierBadge = caseData.case_identifier 
      ? `<span class="case-id-badge" style="margin-inline-end:8px;">${UI.escapeHtml(caseData.case_identifier)}</span>`
      : '';

    heading.innerHTML = `
      <div>
        <h1 style="display:flex; align-items:center; flex-wrap:wrap; gap:8px;">
          ${caseIdentifierBadge}
          <span>${UI.escapeHtml(caseData.name)}</span>
        </h1>
        <p class="text-muted">${UI.escapeHtml(caseData.description || '')}</p>
      </div>
    `;

    if (State.get().user && State.get().user.role === 'ADMIN') {
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger btn-sm';
      deleteBtn.innerHTML = `${UI.icon('trash', '', 14)} <span>${I18n.t('deleteCase')}</span>`;
      deleteBtn.onclick = () => openDeleteCaseModal(caseId, caseData.name);
      heading.appendChild(deleteBtn);
    }
    wrap.appendChild(heading);

    const tabs = document.createElement('div');
    tabs.className = 'tabs';
    const tabDefs = [
      { id: 'overview', label: I18n.t('overview'), icon: 'folder' },
      { id: 'evidence', label: I18n.t('evidenceTab'), icon: 'file' },
      { id: 'map', label: I18n.t('evidenceMap'), icon: 'link' },
      { id: 'chain', label: I18n.t('chainTab'), icon: 'shieldCheck' },
    ];
    tabDefs.forEach((t) => {
      const el = document.createElement('div');
      el.className = 'tab' + (tab === t.id ? ' active' : '');
      el.innerHTML = `${UI.icon(t.icon, '', 16)} <span>${t.label}</span>`;
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
      body.appendChild(await renderMembers(caseId));
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
      return null;
    }
    const alerts = data.alerts || [];
    if (alerts.length === 0) return null;

    const el = document.createElement('div');
    el.className = 'card';
    el.style.marginBlockEnd = '16px';

    const title = document.createElement('h3');
    title.innerHTML = `${UI.icon('alertTriangle', '', 18)} <span>${I18n.t('crossCaseAlertsTitle')}</span>`;
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
        div.innerHTML = `${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('aiDisabled')}</span>`;
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
      tag.innerHTML = `${UI.icon('alertTriangle', '', 14)} <span>${I18n.t('aiAutomatedEstimate')}</span>`;
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
      btn.innerHTML = `${UI.icon('refresh', '', 14)} <span>${I18n.t('caseSummaryRefresh')}</span>`;
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
          <div style="font-size:1.6rem;font-weight:700; color:var(--color-primary);">${caseData.evidence_count}</div>
        </div>
        <div style="min-width:200px">
          <div class="text-muted text-sm">${I18n.t('chainStatus')}</div>
          <div id="overview-chain-status" style="margin-top:4px;">…</div>
        </div>
      </div>
      <div class="mt-4">
        <button class="btn btn-primary" id="overview-verify-btn">
          ${UI.icon('shieldCheck', '', 16)}
          <span>${I18n.t('verifyChain')}</span>
        </button>
      </div>
    `;

    const statusEl = el.querySelector('#overview-chain-status');
    const verifyBtn = el.querySelector('#overview-verify-btn');

    async function runVerify() {
      verifyBtn.disabled = true;
      verifyBtn.innerHTML = `<span>${I18n.t('verifying')}</span>`;
      statusEl.innerHTML = '…';
      try {
        const result = await Api.verifyCaseChain(caseId);
        renderVerifyResult(statusEl, result);
      } catch (e) {
        statusEl.innerHTML = `<span class="ui-badge badge-critical">${I18n.t('genericError')}</span>`;
      }
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = `${UI.icon('shieldCheck', '', 16)} <span>${I18n.t('verifyChain')}</span>`;
    }
    verifyBtn.onclick = runVerify;
    await runVerify();

    return el;
  }

  // Who can see this case. Membership is what gates every case-scoped
  // endpoint (and which cross-case alerts show full detail), so admins
  // need a way to grant it without using the API by hand.
  async function renderMembers(caseId) {
    const el = document.createElement('div');
    el.className = 'card mt-4';
    const isAdmin = State.get().user && State.get().user.role === 'ADMIN';

    async function load() {
      el.innerHTML = `<h3 style="display:flex; align-items:center; gap:8px; margin-top:0;">${UI.icon('user', '', 18)} <span>${I18n.t('caseMembers')}</span></h3><p class="text-muted">…</p>`;
      let members;
      try {
        members = await Api.listMembers(caseId);
      } catch (e) {
        el.innerHTML += `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        return;
      }

      const chips = members
        .map(
          (m) => `
          <span class="examiner-profile-pill" title="${UI.escapeHtml(m.username)}">
            <span class="examiner-avatar">${UI.icon('user', '', 12)}</span>
            <span>${UI.escapeHtml(m.full_name || m.username)} · <span class="text-muted">${
              m.role === 'ADMIN' ? I18n.t('admin') : I18n.t('investigator')
            }</span></span>
          </span>`
        )
        .join('');

      el.innerHTML = `
        <h3 style="display:flex; align-items:center; gap:8px; margin-top:0;">${UI.icon('user', '', 18)} <span>${I18n.t('caseMembers')}</span></h3>
        <p class="text-muted text-sm">${I18n.t('caseMembersHint')}</p>
        <div class="flex gap-2" style="flex-wrap:wrap;">${chips}</div>
        <div id="members-admin"></div>
      `;

      if (!isAdmin) return;

      let directory = [];
      try {
        directory = await Api.userDirectory();
      } catch (e) {
        return;
      }
      const memberIds = new Set(members.map((m) => m.id));
      const candidates = directory.filter((u) => !memberIds.has(u.id));
      const adminBox = el.querySelector('#members-admin');

      if (candidates.length === 0) {
        adminBox.innerHTML = `<p class="text-muted text-sm mt-3">${I18n.t('allUsersAreMembers')}</p>`;
        return;
      }

      adminBox.innerHTML = `
        <div id="members-error" class="mt-3"></div>
        <div class="flex gap-2 mt-3" style="flex-wrap:wrap; align-items:center;">
          <select id="member-select" style="flex:1; min-width:220px;">
            ${candidates
              .map(
                (u) =>
                  `<option value="${u.id}">${UI.escapeHtml(u.full_name || u.username)} (${UI.escapeHtml(u.username)})</option>`
              )
              .join('')}
          </select>
          <button type="button" class="btn btn-primary" id="member-add-btn">
            ${UI.icon('plus', '', 16)} <span>${I18n.t('addMember')}</span>
          </button>
        </div>
      `;
      const addBtn = adminBox.querySelector('#member-add-btn');
      addBtn.onclick = async () => {
        const userId = Number(adminBox.querySelector('#member-select').value);
        addBtn.disabled = true;
        try {
          await Api.addMember(caseId, userId);
          Notifications.refresh();
          await load();
        } catch (err) {
          addBtn.disabled = false;
          adminBox.querySelector('#members-error').innerHTML =
            `<div class="alert alert-danger">${UI.escapeHtml(err.message)}</div>`;
        }
      };
    }

    await load();
    return el;
  }

  function renderVerifyResult(el, result) {
    if (result.intact) {
      el.innerHTML = `<span class="ui-badge badge-active">${UI.icon('check', '', 13)} ${I18n.t('intact')}</span> <span class="text-muted text-sm">${result.records_checked} ${I18n.t('recordsChecked')}</span>`;
    } else {
      el.innerHTML = `<span class="ui-badge badge-critical">${UI.icon('alertTriangle', '', 13)} ${I18n.t('broken')}</span> <span class="text-muted text-sm">${I18n.t('firstBrokenAt', { seq: result.first_broken_seq })}</span>`;
    }
  }

  return { renderList, renderDetail, renderVerifyResult };
})();
