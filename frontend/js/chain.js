const Chain = (() => {
  async function renderTab(caseId) {
    const wrap = document.createElement('div');
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="flex" style="justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="color:var(--color-primary); display:flex;">${UI.icon('shieldCheck', '', 22)}</span>
          <h3 style="margin:0;">${I18n.t('fullChain')}</h3>
        </div>
        <button class="btn btn-primary btn-sm" id="chain-verify-btn">
          ${UI.icon('shieldCheck', '', 15)}
          <span>${I18n.t('verifyChain')}</span>
        </button>
      </div>
      <div id="chain-verify-status" class="mt-3"></div>
      <div id="chain-list" class="mt-4"></div>
    `;
    wrap.appendChild(card);

    const listEl = card.querySelector('#chain-list');
    const statusEl = card.querySelector('#chain-verify-status');
    const verifyBtn = card.querySelector('#chain-verify-btn');

    let brokenSeq = null;

    async function load() {
      listEl.innerHTML = `<p class="text-muted">…</p>`;
      let rows;
      try {
        rows = await Api.caseAudit(caseId);
      } catch (e) {
        listEl.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('genericError')}</span></div>`;
        return;
      }
      if (rows.length === 0) {
        listEl.innerHTML = `<p class="text-muted">${I18n.t('chainEmpty')}</p>`;
        return;
      }
      const list = document.createElement('div');
      list.className = 'chain-list';
      rows.forEach((r) => {
        const item = document.createElement('div');
        const isBroken = brokenSeq && r.seq >= brokenSeq;
        item.className = 'chain-item' + (isBroken ? ' broken' : '');
        item.innerHTML = `
          <div style="font-weight:600; font-size:0.9rem; color:var(--color-text);">${UI.escapeHtml(r.message)}</div>
          <div class="text-muted text-xs mt-1" style="display:flex; align-items:center; gap:6px;">
            <span>${UI.escapeHtml(r.ts)}</span>
            <span>·</span>
            <span class="ui-badge" style="padding:1px 6px;">#${r.seq}</span>
          </div>
          <div class="chain-hash text-xs mono mt-1">
            <span style="opacity:0.75;">${I18n.t('sha256')}:</span> ${r.event_hash}
          </div>
        `;
        list.appendChild(item);
      });
      listEl.innerHTML = '';
      listEl.appendChild(list);
    }

    verifyBtn.onclick = async () => {
      verifyBtn.disabled = true;
      verifyBtn.innerHTML = `<span>${I18n.t('verifying')}</span>`;
      try {
        const result = await Api.verifyCaseChain(caseId);
        brokenSeq = result.first_broken_seq;
        Cases.renderVerifyResult(statusEl, result);
        await load();
      } catch (e) {
        statusEl.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('genericError')}</span></div>`;
      }
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = `${UI.icon('shieldCheck', '', 15)} <span>${I18n.t('verifyChain')}</span>`;
    };

    await load();
    return wrap;
  }

  return { renderTab };
})();
