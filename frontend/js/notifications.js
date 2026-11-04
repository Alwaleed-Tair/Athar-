const Notifications = (() => {
  const POLL_MS = 60 * 1000;
  let pollTimer = null;
  let popupOpen = false;
  let refreshing = false;
  // Kept here rather than in State: State.set() re-renders the whole
  // page (and re-opening a case appends a CASE_OPENED custody event), so
  // a background check must only touch the bell badge itself.
  let current = { count: 0, alerts: [] };

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
    if (!a.visible) return `${a.type}|${a.fromCaseId}:${a.evidence_id ?? 'case'}|hidden`;
    const endpoints = [
      `${a.fromCaseId}:${a.evidence_id ?? 'case'}`,
      `${a.other_case_id}:${a.other_evidence_id ?? 'case'}`,
    ].sort();
    return `${a.type}|${endpoints.join('|')}`;
  }

  function alertText(a) {
    if (!a.visible) return I18n.t('crossCaseAlertHidden', { filename: a.evidence_filename });
    const why = (a.reasons || []).slice(0, 2).map((r) => `${I18n.t('reason_' + r.type)}: ${r.value}`).join(' · ');
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

      if (!State.get().user) return; // logged out while loading
      current = { count: alerts.length, alerts };
      updateBellBadges();

      const seen = loadSeen();
      const fresh = alerts.filter((a) => !seen.has(alertKey(a)));
      if (fresh.length > 0 && !popupOpen) {
        fresh.forEach((a) => seen.add(alertKey(a)));
        saveSeen(seen);
        openPopup(fresh);
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
  function openPopup(fresh) {
    popupOpen = true;
    const shown = fresh.slice(0, 3);
    const more = fresh.length - shown.length;

    const content = document.createElement('div');
    content.className = 'alert-popup';
    content.setAttribute('role', 'alertdialog');
    content.innerHTML = `
      <div class="alert-popup-head">
        <span class="alert-popup-icon">${UI.icon('link', '', 22)}</span>
        <div>
          <h3 style="margin:0;">${I18n.t('newCorrelationTitle')}</h3>
          <div class="text-muted text-sm">${I18n.t('newCorrelationSub', { count: fresh.length })}</div>
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

    if (alerts.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-muted text-sm';
      empty.textContent = I18n.t('notificationsEmpty');
      content.appendChild(empty);
    } else {
      alerts.forEach((a) => {
        const row = document.createElement('div');
        row.className = 'alert alert-warning mt-3';
        row.style.marginBlockEnd = '0';
        row.textContent = alertText(a);
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
    current = { count: 0, alerts: [] };
  }

  return { refresh, renderBell, stop, setPending, refreshPending, getPending: () => pendingCount, paintPending };
})();
