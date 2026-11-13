const Notifications = (() => {
  const POLL_MS = 60 * 1000;
  let pollTimer = null;
  let popupOpen = false;
  let refreshing = false;
  // Kept here rather than in State: State.set() re-renders the whole
  // page (and re-opening a case appends a CASE_OPENED custody event), so
  // a background check must only touch the bell badge itself.
  let current = { count: 0, alerts: [], requests: [] };

  // --- "Already seen" memory -------------------------------------------
  // Remembered per user in this browser so the popup only fires for a
  // correlation the user hasn't been shown yet. Storage can be blocked
  // (private mode etc.), so every access is guarded and falls back to an
  // in-memory set for the current session.
  const memorySeen = {};

  function seenKey() {
    const user = State.get().user;
    return user ? `athar_seen_alerts_${user.id}` : null;
  }

  function loadSeen() {
    const key = seenKey();
    if (!key) return new Set();
    try {
      const raw = localStorage.getItem(key);
      if (raw) return new Set(JSON.parse(raw));
    } catch (e) {
      /* storage unavailable */
    }
    return new Set(memorySeen[key] || []);
  }

  function saveSeen(set) {
    const key = seenKey();
    if (!key) return;
    const arr = Array.from(set).slice(-500);
    memorySeen[key] = arr;
    try {
      localStorage.setItem(key, JSON.stringify(arr));
    } catch (e) {
      /* storage unavailable */
    }
  }

  // Stable identity for one correlation, independent of which of the two
  // cases it was fetched from.
  function alertKey(a) {
    if (!a.visible) return `${a.type}|${a.fromCaseId}:${a.evidence_id ?? 'case'}|restricted|${a.link_id ?? ''}`;
    const endpoints = [
      `${a.fromCaseId}:${a.evidence_id ?? 'case'}`,
      `${a.other_case_id}:${a.other_evidence_id ?? 'case'}`,
    ].sort();
    return `${a.type}|${endpoints.join('|')}`;
  }

  function reasonsText(reasons, n = 2) {
    return (reasons || []).slice(0, n).map((r) => `${I18n.t('reason_' + r.type)}: ${r.value}`).join(' · ');
  }

  function alertText(a) {
    const why = reasonsText(a.reasons);
    if (!a.visible) return (why ? `${why} — ` : '') + I18n.t('crossCaseAlertHidden', { filename: a.evidence_filename });
    return (why ? `${why} — ` : '') + (a.other_evidence_filename
      ? I18n.t('crossCaseAlertVisible', {
          filename: a.evidence_filename,
          otherFilename: a.other_evidence_filename,
          caseName: a.other_case_name,
        })
      : I18n.t('crossCaseAlertVisibleCaseOnly', {
          filename: a.evidence_filename,
          caseName: a.other_case_name,
        }));
  }

  // --- Restricted notices: ask the owner of the matching case for access ---
  function openRequestDialog(a, onSent) {
    const content = document.createElement('div');
    content.innerHTML = `
      <h3 style="margin-top:0;">${I18n.t('requestAccessTitle')}</h3>
      <p class="text-sm text-muted" dir="auto">${UI.escapeHtml(I18n.t('requestAccessBody'))}</p>
      <div class="field">
        <label for="ra-note">${I18n.t('requestAccessNote')}</label>
        <textarea id="ra-note" rows="3" maxlength="500" dir="auto"></textarea>
      </div>
      <div class="flex gap-2" style="justify-content:flex-end; margin-top:16px; flex-wrap:wrap;">
        <button type="button" class="btn btn-ghost" id="ra-cancel">${I18n.t('cancel')}</button>
        <button type="button" class="btn btn-primary" id="ra-send">${I18n.t('requestAccessSend')}</button>
      </div>`;
    const { close } = UI.openModal(content);
    content.querySelector('#ra-cancel').onclick = close;
    const send = content.querySelector('#ra-send');
    send.onclick = async () => {
      send.disabled = true;
      try {
        await Api.requestLinkAccess(a.link_id, content.querySelector('#ra-note').value.trim());
        a.request_status = 'PENDING';
        UI.toast(I18n.t('accessRequestSent'));
        close();
        if (onSent) onSent();
      } catch (e) {
        UI.toast(UI.errorMessage(e), 'error');
        send.disabled = false;
      }
    };
  }

  // Button (or status) shown next to a restricted notice, wherever it is listed.
  function restrictedAction(a) {
    const holder = document.createElement('span');
    holder.className = 'flex gap-2';
    holder.style.alignItems = 'center';
    holder.style.flexWrap = 'wrap';
    const paint = () => {
      holder.innerHTML = '';
      if (a.request_status === 'PENDING') {
        const b = document.createElement('span');
        b.className = 'badge warn';
        b.textContent = I18n.t('accessStatus_PENDING');
        holder.appendChild(b);
        return;
      }
      if (a.request_status === 'DECLINED') {
        const b = document.createElement('span');
        b.className = 'badge bad';
        b.textContent = I18n.t('accessStatus_DECLINED');
        holder.appendChild(b);
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-sm';
      btn.textContent = I18n.t('requestAccess');
      btn.onclick = (ev) => {
        ev.stopPropagation();
        openRequestDialog(a, paint);
      };
      holder.appendChild(btn);
    };
    paint();
    return holder;
  }

  // --- Incoming access requests (case owners decide) ---------------------
  function requestText(r) {
    return I18n.t('accessRequestText', {
      requester: r.requester_name,
      fromCase: r.requester_case_name,
      caseName: r.target_case_name,
      files: (r.matched_files || []).join(I18n.getLang && I18n.getLang() === 'ar' ? '، ' : ', ') || '-',
      reasons: reasonsText(r.reasons, 3) || '-',
    });
  }

  function requestRow(r) {
    const row = document.createElement('div');
    row.className = 'alert alert-success mt-3';
    row.style.marginBlockEnd = '0';
    row.style.flexWrap = 'wrap';
    const body = document.createElement('div');
    body.style.flex = '1';
    body.setAttribute('dir', 'auto');
    const main = document.createElement('div');
    main.textContent = requestText(r);
    body.appendChild(main);
    if (r.note) {
      const n = document.createElement('div');
      n.className = 'text-xs';
      n.style.opacity = '.85';
      n.textContent = I18n.t('accessRequestNote', { note: r.note });
      body.appendChild(n);
    }
    row.appendChild(body);
    const actions = document.createElement('span');
    actions.className = 'flex gap-2';
    const decide = async (approve, btn) => {
      actions.querySelectorAll('button').forEach((b) => (b.disabled = true));
      try {
        if (approve) {
          await Api.approveAccessRequest(r.id);
          UI.toast(I18n.t('accessApproved', { requester: r.requester_name }));
        } else {
          await Api.declineAccessRequest(r.id);
          UI.toast(I18n.t('accessDeclined'));
        }
        row.remove();
        current.requests = current.requests.filter((x) => x.id !== r.id);
        current.count = current.alerts.length + current.requests.length;
        updateBellBadges();
      } catch (e) {
        UI.toast(UI.errorMessage(e), 'error');
        actions.querySelectorAll('button').forEach((b) => (b.disabled = false));
      }
    };
    const ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn btn-sm btn-primary';
    ok.textContent = I18n.t('approve');
    ok.onclick = () => decide(true, ok);
    const no = document.createElement('button');
    no.type = 'button';
    no.className = 'btn btn-sm';
    no.textContent = I18n.t('reject');
    no.onclick = () => decide(false, no);
    actions.appendChild(ok);
    actions.appendChild(no);
    row.appendChild(actions);
    return row;
  }

  const requestKey = (r) => `req|${r.id}`;

  // --- Fetch + dedupe ---------------------------------------------------
  async function refresh() {
    if (refreshing || !State.get().user) return;
    refreshing = true;
    refreshPending();
    try {
      let cases;
      try {
        cases = await Api.listCases();
      } catch (e) {
        return;
      }

      const reqPromise = Api.listAccessRequests().then((r) => r.incoming || []).catch(() => []);
      const perCase = await Promise.all(
        cases.map((c) =>
          Api.getCrossCaseAlerts(c.id)
            .then((r) => (r.alerts || []).map((a) => ({ ...a, fromCaseId: c.id, fromCaseName: c.name })))
            .catch(() => [])
        )
      );

      // A visible alert between two cases the user belongs to is fetched
      // once from each side -- dedupe those mirrored pairs.
      const byKey = new Map();
      perCase.flat().forEach((a) => {
        const k = alertKey(a);
        if (!byKey.has(k)) byKey.set(k, a);
      });
      const alerts = Array.from(byKey.values());

      const requests = await reqPromise;

      if (!State.get().user) return; // logged out while loading
      current = { count: alerts.length + requests.length, alerts, requests };
      updateBellBadges();

      const seen = loadSeen();
      const fresh = alerts.filter((a) => !seen.has(alertKey(a)));
      const freshReq = requests.filter((r) => !seen.has(requestKey(r)));
      if ((fresh.length > 0 || freshReq.length > 0) && !popupOpen) {
        fresh.forEach((a) => seen.add(alertKey(a)));
        freshReq.forEach((r) => seen.add(requestKey(r)));
        saveSeen(seen);
        openPopup(fresh, freshReq);
      }
    } finally {
      refreshing = false;
      schedulePoll();
    }
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!State.get().user) return;
    pollTimer = setTimeout(() => {
      if (document.visibilityState === 'visible') refresh();
      else schedulePoll();
    }, POLL_MS);
  }

  // --- Popup shown the moment a NEW correlation appears -----------------
  function openPopup(fresh, freshReq = []) {
    popupOpen = true;
    const shown = fresh.slice(0, 3);
    const more = fresh.length - shown.length;
    const total = fresh.length + freshReq.length;

    const content = document.createElement('div');
    content.className = 'alert-popup';
    content.setAttribute('role', 'alertdialog');
    content.innerHTML = `
      <div class="alert-popup-head">
        <span class="alert-popup-icon">${UI.icon('link', '', 22)}</span>
        <div>
          <h3 style="margin:0;">${I18n.t('newCorrelationTitle')}</h3>
          <div class="text-muted text-sm">${I18n.t('newCorrelationSub', { count: total })}</div>
        </div>
      </div>
      <div class="alert-popup-list"></div>
      ${more > 0 ? `<p class="text-muted text-sm">${I18n.t('andMore', { count: more })}</p>` : ''}
      <div class="flex gap-2" style="justify-content:flex-end; margin-top:16px; flex-wrap:wrap;">
        <button type="button" class="btn btn-ghost" id="ap-all">${UI.icon('bell', '', 15)} <span>${I18n.t('viewAllNotifications')}</span></button>
        <button type="button" class="btn btn-primary" id="ap-ok">${I18n.t('gotIt')}</button>
      </div>
    `;

    const list = content.querySelector('.alert-popup-list');
    freshReq.slice(0, 3).forEach((r) => list.appendChild(requestRow(r)));
    shown.forEach((a) => {
      const row = document.createElement('div');
      row.className = 'alert alert-warning alert-popup-item';
      row.innerHTML = `<span>${UI.icon('alertTriangle', '', 16)}</span><span style="flex:1;">${UI.escapeHtml(alertText(a))}</span>`;
      if (a.visible && a.other_case_id) {
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'btn btn-sm';
        open.textContent = I18n.t('openCase');
        open.onclick = () => {
          close();
          State.set({ route: { name: 'case', caseId: a.other_case_id, tab: 'overview' } });
        };
        row.appendChild(open);
      } else if (!a.visible && a.link_id) {
        row.appendChild(restrictedAction(a));
      }
      list.appendChild(row);
    });

    const { close } = UI.openModal(content, { onClose: () => (popupOpen = false) });
    content.querySelector('#ap-ok').onclick = close;
    content.querySelector('#ap-all').onclick = () => {
      close();
      openModal();
    };
  }

  // --- Bell + full list -------------------------------------------------
  function badgeText(count) {
    return count > 9 ? '9+' : String(count);
  }

  function updateBellBadges() {
    document.querySelectorAll('.bell-wrap').forEach((wrap) => {
      let badge = wrap.querySelector('.bell-badge');
      if (current.count > 0) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'bell-badge';
          wrap.appendChild(badge);
        }
        badge.textContent = badgeText(current.count);
      } else if (badge) {
        badge.remove();
      }
    });
  }

  function renderBell() {
    const count = current.count;

    const wrap = document.createElement('div');
    wrap.className = 'bell-wrap';

    const btn = document.createElement('button');
    btn.className = 'btn btn-sm';
    btn.innerHTML = UI.icon('bell', '', 16);
    btn.title = I18n.t('notifications');
    btn.onclick = openModal;
    wrap.appendChild(btn);

    if (count > 0) {
      const badge = document.createElement('span');
      badge.className = 'bell-badge';
      badge.textContent = badgeText(count);
      wrap.appendChild(badge);
    }

    return wrap;
  }

  function openModal() {
    const alerts = current.alerts;

    const content = document.createElement('div');
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `<h3 style="margin:0;">${I18n.t('notifications')}</h3>`;
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn btn-sm';
    closeBtn.textContent = I18n.t('close');
    header.appendChild(closeBtn);
    content.appendChild(header);

    const requests = current.requests || [];
    if (requests.length > 0) {
      const h = document.createElement('h4');
      h.style.margin = '8px 0 0';
      h.textContent = I18n.t('accessRequestsTitle');
      content.appendChild(h);
      requests.forEach((r) => content.appendChild(requestRow(r)));
    }

    if (alerts.length === 0 && requests.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-muted text-sm';
      empty.textContent = I18n.t('notificationsEmpty');
      content.appendChild(empty);
    } else {
      alerts.forEach((a) => {
        const row = document.createElement('div');
        row.className = 'alert alert-warning mt-3';
        row.style.marginBlockEnd = '0';
        row.style.flexWrap = 'wrap';
        const txt = document.createElement('span');
        txt.style.flex = '1';
        txt.setAttribute('dir', 'auto');
        txt.textContent = alertText(a);
        row.appendChild(txt);
        if (!a.visible && a.link_id) row.appendChild(restrictedAction(a));
        if (a.visible) {
          row.style.cursor = 'pointer';
          row.onclick = () => {
            close();
            State.set({ route: { name: 'case', caseId: a.fromCaseId, tab: 'overview' } });
          };
        }
        content.appendChild(row);
      });
    }

    const { close } = UI.openModal(content);
    closeBtn.onclick = close;
  }

  // --- Admin: registration requests waiting for approval ---------------------------
  let pendingCount = 0;
  function paintPending() {
    document.querySelectorAll('.pending-badge').forEach((b) => {
      b.textContent = pendingCount > 9 ? '9+' : String(pendingCount);
      b.style.display = pendingCount > 0 ? '' : 'none';
    });
  }
  function setPending(n) { pendingCount = n; paintPending(); }
  async function refreshPending() {
    const u = State.get().user;
    if (!u || u.role !== 'ADMIN') return;
    try { setPending((await Api.pendingUsers()).length); } catch (e) { /* ignore */ }
  }

  function stop() {
    clearTimeout(pollTimer);
    pollTimer = null;
    current = { count: 0, alerts: [], requests: [] };
  }

  return { refresh, renderBell, stop, setPending, refreshPending, getPending: () => pendingCount, paintPending, restrictedAction };
})();
