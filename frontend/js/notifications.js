const Notifications = (() => {
  async function refresh() {
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
    const all = perCase.flat();

    // A visible alert between two cases the user belongs to is fetched
    // once from each side -- dedupe those mirrored pairs. A hidden
    // (redacted) alert can only ever be fetched from the one side the
    // user has access to, so it never has a duplicate to begin with.
    const seen = new Set();
    const deduped = [];
    all.forEach((a) => {
      if (!a.visible) {
        deduped.push(a);
        return;
      }
      const endpoints = [
        `${a.fromCaseId}:${a.evidence_id ?? 'case'}`,
        `${a.other_case_id}:${a.other_evidence_id ?? 'case'}`,
      ].sort();
      const key = endpoints.join('|') + a.type;
      if (seen.has(key)) return;
      seen.add(key);
      deduped.push(a);
    });

    State.set({ notifications: { count: deduped.length, alerts: deduped } });
  }

  function renderBell() {
    const { notifications } = State.get();
    const count = (notifications && notifications.count) || 0;

    const wrap = document.createElement('div');
    wrap.style.position = 'relative';
    wrap.style.display = 'inline-block';

    const btn = document.createElement('button');
    btn.className = 'btn btn-sm';
    btn.textContent = '🔔';
    btn.title = I18n.t('notifications');
    btn.onclick = openModal;
    wrap.appendChild(btn);

    if (count > 0) {
      const badge = document.createElement('span');
      badge.textContent = count > 9 ? '9+' : String(count);
      badge.style.position = 'absolute';
      badge.style.top = '-6px';
      badge.style.insetInlineEnd = '-6px';
      badge.style.background = 'var(--color-danger)';
      badge.style.color = '#fff';
      badge.style.borderRadius = '999px';
      badge.style.fontSize = '10px';
      badge.style.lineHeight = '1';
      badge.style.padding = '3px 5px';
      badge.style.minWidth = '14px';
      badge.style.textAlign = 'center';
      wrap.appendChild(badge);
    }

    return wrap;
  }

  function openModal() {
    const { notifications } = State.get();
    const alerts = (notifications && notifications.alerts) || [];

    const content = document.createElement('div');
    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `<h3>${I18n.t('notifications')}</h3>`;
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
          row.onclick = () => {
            close();
            State.set({ route: { name: 'case', caseId: a.fromCaseId, tab: 'overview' } });
          };
        } else {
          row.textContent = I18n.t('crossCaseAlertHidden', { filename: a.evidence_filename });
        }
        content.appendChild(row);
      });
    }

    const { close } = UI.openModal(content);
    closeBtn.onclick = close;
  }

  return { refresh, renderBell };
})();