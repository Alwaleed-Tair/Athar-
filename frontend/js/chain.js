const Chain = (() => {
  async function renderTab(caseId) {
    const wrap = document.createElement('div');
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="flex" style="justify-content:space-between;align-items:center">
        <h3>${I18n.t('fullChain')}</h3>
        <button class="btn btn-sm" id="chain-verify-btn">${I18n.t('verifyChain')}</button>
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
        listEl.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
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
        item.className = 'chain-item' + (brokenSeq && r.seq >= brokenSeq ? ' broken' : '');
        item.innerHTML = `
          <div class="text-sm">${UI.escapeHtml(r.message)}</div>
          <div class="text-muted text-xs">${UI.escapeHtml(r.ts)} · #${r.seq}</div>
          <div class="chain-hash text-xs mono mt-1">${I18n.t('sha256')}: ${r.event_hash.slice(0, 24)}…</div>
        `;
        list.appendChild(item);
      });
      listEl.innerHTML = '';
      listEl.appendChild(list);
    }

    verifyBtn.onclick = async () => {
      verifyBtn.disabled = true;
      verifyBtn.textContent = I18n.t('verifying');
      try {
        const result = await Api.verifyCaseChain(caseId);
        brokenSeq = result.first_broken_seq;
        Cases.renderVerifyResult(statusEl, result);
        await load();
      } catch (e) {
        statusEl.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
      }
      verifyBtn.disabled = false;
      verifyBtn.textContent = I18n.t('verifyChain');
    };

    await load();
    return wrap;
  }

  return { renderTab };
})();
