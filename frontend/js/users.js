// Admin-only user management: list accounts, create one, reset a
// password. (Resetting from here replaces an e-mailed "forgot password"
// link, which would need an outgoing mail server.)
const Users = (() => {
  async function renderPage() {
    const wrap = document.createElement('div');

    const header = document.createElement('div');
    header.className = 'case-list-header';
    header.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="color:var(--color-primary); display:flex; align-items:center;">${UI.icon('user', '', 26)}</span>
        <h1 style="margin:0;">${I18n.t('usersTitle')}</h1>
      </div>
      <button type="button" class="btn btn-primary btn-neon" id="btn-new-user">
        ${UI.icon('plus', '', 18)} <span>${I18n.t('newUser')}</span>
      </button>
    `;
    wrap.appendChild(header);

    const pendingCard = document.createElement('div');
    wrap.appendChild(pendingCard);

    const listCard = document.createElement('div');
    listCard.className = 'card';
    wrap.appendChild(listCard);

    // Registration requests waiting for an administrator's decision.
    async function loadPending() {
      let list = [];
      try { list = await Api.pendingUsers(); } catch (e) { pendingCard.innerHTML = ''; return; }
      Notifications.setPending(list.length);
      if (!list.length) {
        pendingCard.className = 'card mt-0';
        pendingCard.style.marginBlockEnd = '16px';
        pendingCard.innerHTML = `<h3 style="margin:0; display:flex; align-items:center; gap:8px;">${UI.icon('userCheck', '', 20)} <span>${I18n.t('pendingRequests')}</span></h3>
          <p class="text-muted text-sm" style="margin-block:8px 0;">${I18n.t('pendingNone')}</p>`;
        return;
      }
      pendingCard.className = 'card pending-card';
      pendingCard.style.marginBlockEnd = '16px';
      pendingCard.innerHTML = `
        <h3 style="margin:0; display:flex; align-items:center; gap:8px;">${UI.icon('userCheck', '', 20)} <span>${I18n.t('pendingRequests')}</span>
          <span class="chip chip-warn">${list.length}</span></h3>
        <p class="text-muted text-sm">${I18n.t('pendingExplain')}</p>
        ${list.map((u) => `
          <div class="pending-row">
            <div style="flex:1; min-width:200px;">
              <div><strong dir="auto">${UI.escapeHtml(u.full_name || u.username)}</strong></div>
              <div class="text-muted text-sm"><bdi dir="ltr">${UI.escapeHtml(u.email || u.username)}</bdi> · ${UI.dateHtml(u.created_at)}</div>
            </div>
            <div class="flex gap-2">
              <button type="button" class="btn btn-primary btn-sm" data-approve="${u.id}">${UI.icon('check', '', 14)} <span>${I18n.t('approve')}</span></button>
              <button type="button" class="btn btn-sm btn-danger-ghost" data-reject="${u.id}" data-name="${UI.escapeHtml(u.full_name || u.username)}">${UI.icon('x', '', 14)} <span>${I18n.t('reject')}</span></button>
            </div>
          </div>`).join('')}`;
      pendingCard.querySelectorAll('[data-approve]').forEach((b) => {
        b.onclick = async () => {
          b.disabled = true;
          try { await Api.approveUser(Number(b.dataset.approve)); UI.toast(I18n.t('accountApprovedToast')); await loadPending(); await load(); }
          catch (e) { b.disabled = false; UI.toast(UI.errorMessage(e), 'error'); }
        };
      });
      pendingCard.querySelectorAll('[data-reject]').forEach((b) => {
        b.onclick = async () => {
          const ok = await UI.confirmDialog({
            title: I18n.t('reject'),
            message: I18n.t('rejectConfirm', { name: `<strong dir="auto">${b.dataset.name}</strong>` }),
            confirmLabel: I18n.t('reject'),
          });
          if (!ok) return;
          try { await Api.rejectUser(Number(b.dataset.reject)); UI.toast(I18n.t('requestRejectedToast')); await loadPending(); await load(); }
          catch (e) { UI.toast(UI.errorMessage(e), 'error'); }
        };
      });
    }

    async function load() {
      listCard.innerHTML = UI.spinner();
      let users;
      try {
        users = await Api.listUsers();
      } catch (e) {
        listCard.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
        return;
      }
      const me = State.get().user;
      const rows = users
        .map(
          (u) => `
          <tr>
            <td><strong>${UI.escapeHtml(u.full_name || '—')}</strong>${
              u.id === me.id ? ` <span class="text-muted text-sm">(${I18n.t('you')})</span>` : ''
            }</td>
            <td class="mono" style="font-size:0.82rem;">${UI.escapeHtml(u.username)}</td>
            <td><span class="ui-badge ${u.role === 'ADMIN' ? 'badge-high' : 'badge-active'}">${
              u.role === 'ADMIN' ? I18n.t('admin') : I18n.t('investigator')
            }</span></td>
            <td>${u.email_verified
              ? `<span class="ui-badge badge-active">${UI.icon('check', '', 12)} ${I18n.t('accountApproved')}</span>`
              : `<span class="ui-badge badge-pending">${I18n.t('accountPendingShort')}</span>`}</td>
            <td class="text-muted text-sm">${UI.dateHtml(u.created_at, { time: false })}</td>
            <td style="text-align:end;">
              <button type="button" class="btn btn-sm btn-ghost" data-reset="${u.id}" data-name="${UI.escapeHtml(u.full_name || u.username)}">
                ${UI.icon('key', '', 14)} <span>${I18n.t('resetPassword')}</span>
              </button>
            </td>
          </tr>`
        )
        .join('');
      listCard.innerHTML = `
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>${I18n.t('fullName')}</th>
              <th>${I18n.t('usernameOrEmail')}</th>
              <th>${I18n.t('role')}</th>
              <th>${I18n.t('accountStatus')}</th>
              <th>${I18n.t('createdAt')}</th>
              <th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
      listCard.querySelectorAll('[data-reset]').forEach((btn) => {
        btn.onclick = () => openResetPasswordModal(Number(btn.dataset.reset), btn.dataset.name);
      });
    }

    header.querySelector('#btn-new-user').onclick = () => openCreateUserModal(load);
    await loadPending();
    await load();

    // --- Contact-form inbox (admins only) -----------------------------------------
    const inbox = document.createElement('div');
    inbox.className = 'card mt-4';
    wrap.appendChild(inbox);
    async function loadInbox() {
      inbox.innerHTML = `<h3 style="display:flex; align-items:center; gap:8px;">${UI.icon('mail', '', 20)} <span>${I18n.t('contactInbox')}</span></h3>${UI.spinner()}`;
      let msgs;
      try { msgs = await Api.listContactMessages(); } catch (e) {
        inbox.innerHTML += `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`; return;
      }
      const rows = msgs.length ? msgs.map((m) => `
        <div class="inbox-item ${m.handled ? 'handled' : ''}">
          <div class="flex gap-2" style="justify-content:space-between; flex-wrap:wrap; align-items:center;">
            <div><strong dir="auto">${UI.escapeHtml(m.subject)}</strong> <span class="chip chip-soft">${I18n.t('contactCat' + m.category.charAt(0) + m.category.slice(1).toLowerCase())}</span></div>
            <span class="text-muted text-xs">${UI.dateHtml(m.created_at)}</span>
          </div>
          <div class="text-sm text-muted"><bdi dir="auto">${UI.escapeHtml(m.name)}</bdi> · <bdi dir="ltr">${UI.escapeHtml(m.email)}</bdi></div>
          <div class="mt-1" dir="auto" style="white-space:pre-wrap;">${UI.escapeHtml(m.message)}</div>
          ${m.handled ? `<span class="ui-badge badge-active mt-1">${UI.icon('check', '', 12)} ${I18n.t('contactHandled')}</span>`
            : `<button type="button" class="btn btn-sm mt-2" data-handled="${m.id}">${I18n.t('contactMarkHandled')}</button>`}
        </div>`).join('') : `<p class="text-muted">${I18n.t('contactInboxEmpty')}</p>`;
      inbox.innerHTML = `<h3 style="display:flex; align-items:center; gap:8px;">${UI.icon('mail', '', 20)} <span>${I18n.t('contactInbox')}</span></h3>${rows}`;
      inbox.querySelectorAll('[data-handled]').forEach((b) => {
        b.onclick = async () => { try { await Api.markContactHandled(Number(b.dataset.handled)); loadInbox(); } catch (e) { UI.toast(UI.errorMessage(e), 'error'); } };
      });
    }
    await loadInbox();
    return wrap;
  }

  function openCreateUserModal(onCreated) {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="margin:0; display:flex; align-items:center; gap:8px;">${UI.icon('userCheck', '', 20)} <span>${I18n.t('newUser')}</span></h3>
      </div>
      <div id="cu-error"></div>
      <form id="cu-form" novalidate>
        <div class="field">
          <label for="cu-name">${I18n.t('fullName')}</label>
          <input id="cu-name" name="full_name" type="text" maxlength="120" placeholder="${I18n.t('fullNamePlaceholder')}" required />
        </div>
        <div class="field">
          <label for="cu-username">${I18n.t('usernameOrEmail')}</label>
          <input id="cu-username" name="username" type="text" autocapitalize="off" spellcheck="false" required />
        </div>
        <div class="field">
          <label for="cu-role">${I18n.t('role')}</label>
          <select id="cu-role" name="role">
            <option value="INVESTIGATOR" selected>${I18n.t('investigator')}</option>
            <option value="ADMIN">${I18n.t('admin')}</option>
          </select>
        </div>
        <div class="field">
          <label for="cu-password">${I18n.t('password')}</label>
          <input id="cu-password" name="password" type="password" autocomplete="new-password" required />
          ${Auth.passwordChecklistHtml()}
        </div>
        <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
          <button type="button" id="cu-cancel" class="btn">${I18n.t('cancel')}</button>
          <button type="submit" id="cu-submit" class="btn btn-primary btn-neon">${UI.icon('plus', '', 16)} <span>${I18n.t('create')}</span></button>
        </div>
      </form>
    `;
    const { close } = UI.openModal(content);
    content.querySelector('#cu-cancel').onclick = close;
    Auth.wirePasswordChecklist(content, content.querySelector('#cu-password'));

    const errBox = content.querySelector('#cu-error');
    content.querySelector('#cu-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const fullName = String(fd.get('full_name') || '').trim();
      const username = String(fd.get('username') || '').trim();
      const password = String(fd.get('password') || '');
      const role = String(fd.get('role') || 'INVESTIGATOR');
      const fail = (msg) => (errBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(msg)}</div>`);

      if (fullName.length < 2) return fail(I18n.t('fullNameRequired'));
      if (username.length < 3) return fail(I18n.t('usernameTooShort'));
      if (!Auth.isStrongPassword(password)) return fail(I18n.t('passwordTooWeak'));

      const btn = content.querySelector('#cu-submit');
      btn.disabled = true;
      try {
        await Api.createUser({ full_name: fullName, username, password, role });
        close();
        onCreated && onCreated();
      } catch (err) {
        btn.disabled = false;
        fail(Auth.friendlyError(err));
      }
    });
  }

  function openResetPasswordModal(userId, displayName) {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="margin:0; display:flex; align-items:center; gap:8px;">${UI.icon('key', '', 20)} <span>${I18n.t('resetPassword')}</span></h3>
      </div>
      <p class="text-muted">${I18n.t('resetPasswordFor', { name: UI.escapeHtml(displayName) })}</p>
      <div id="rp-error"></div>
      <form id="rp-form" novalidate>
        <div class="field">
          <label for="rp-password">${I18n.t('newPassword')}</label>
          <input id="rp-password" name="password" type="password" autocomplete="new-password" required />
          ${Auth.passwordChecklistHtml()}
        </div>
        <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
          <button type="button" id="rp-cancel" class="btn">${I18n.t('cancel')}</button>
          <button type="submit" id="rp-submit" class="btn btn-primary">${I18n.t('save')}</button>
        </div>
      </form>
    `;
    const { close } = UI.openModal(content);
    content.querySelector('#rp-cancel').onclick = close;
    const input = content.querySelector('#rp-password');
    Auth.wirePasswordChecklist(content, input);

    const errBox = content.querySelector('#rp-error');
    content.querySelector('#rp-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!Auth.isStrongPassword(input.value)) {
        errBox.innerHTML = `<div class="alert alert-danger">${I18n.t('passwordTooWeak')}</div>`;
        return;
      }
      const btn = content.querySelector('#rp-submit');
      btn.disabled = true;
      try {
        await Api.resetUserPassword(userId, input.value);
        errBox.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('passwordResetDone')}</span></div>`;
        setTimeout(close, 1400);
      } catch (err) {
        btn.disabled = false;
        errBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(Auth.friendlyError(err))}</div>`;
      }
    });
  }

  return { renderPage };
})();
