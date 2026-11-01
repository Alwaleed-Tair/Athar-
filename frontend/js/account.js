// "My account": edit display name, see the registered e-mail, change password.
const Account = (() => {
  function passwordField(id, label, autocomplete) {
    return `
      <div class="field">
        <label for="${id}">${label}</label>
        <div class="field-with-icon">
          <span class="field-icon">${UI.icon('key', '', 17)}</span>
          <input type="password" id="${id}" class="input-with-icon" autocomplete="${autocomplete}" autocapitalize="off" spellcheck="false" />
          <button type="button" class="pw-toggle" data-for="${id}" aria-label="${I18n.t('showPassword')}">${UI.icon('eye', '', 16)}</button>
        </div>
      </div>`;
  }

  function wireToggles(root) {
    root.querySelectorAll('.pw-toggle').forEach((b) => {
      b.onclick = () => {
        const input = root.querySelector('#' + b.dataset.for);
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        b.innerHTML = UI.icon(show ? 'eyeOff' : 'eye', '', 16);
      };
    });
  }

  async function renderPage() {
    const wrap = document.createElement('div');
    let me;
    try {
      me = await Api.me();
    } catch (e) {
      wrap.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e))}</div>`;
      return wrap;
    }

    wrap.innerHTML = `
      <div class="case-list-header">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="color:var(--color-primary); display:flex;">${UI.icon('settings', '', 26)}</span>
          <h1 style="margin:0;">${I18n.t('accountTitle')}</h1>
        </div>
      </div>

      <div class="card">
        <h3>${I18n.t('accountProfile')}</h3>
        <form id="profile-form" novalidate>
          <div id="profile-msg"></div>
          <div class="field">
            <label for="acc-name">${I18n.t('accountName')}</label>
            <input id="acc-name" type="text" maxlength="120" autocomplete="name" value="${UI.escapeHtml(me.full_name || '')}" />
            <div class="field-hint-box">${I18n.t('accountNameHint')}</div>
          </div>
          <div class="field">
            <label for="acc-email">${I18n.t('accountEmail')}</label>
            <input id="acc-email" type="text" value="${UI.escapeHtml(me.email || me.username)}" readonly dir="ltr" />
            <div class="mt-1">
              ${me.email_verified
                ? `<span class="ui-badge badge-active">${UI.icon('check', '', 12)} ${I18n.t('accountVerified')}</span>`
                : `<span class="ui-badge badge-pending">${I18n.t('accountNotVerified')}</span>`}
              <span class="text-muted text-xs">${I18n.t('accountEmailReadonly')}</span>
            </div>
          </div>
          <div class="flex gap-3 text-sm text-muted" style="flex-wrap:wrap;">
            <div>${I18n.t('role')}: ${me.role === 'ADMIN' ? I18n.t('admin') : I18n.t('investigator')}</div>
            <div>${I18n.t('accountJoined')}: ${UI.dateHtml(me.created_at, { time: false })}</div>
          </div>
          <div class="mt-3"><button type="submit" class="btn btn-primary" id="profile-save">${UI.icon('check', '', 15)} <span>${I18n.t('save')}</span></button></div>
        </form>
      </div>

      <div class="card mt-4">
        <h3>${I18n.t('accountPasswordTitle')}</h3>
        <p class="text-muted text-sm">${I18n.t('accountPasswordHint')}</p>
        <form id="pw-form" novalidate>
          <div id="pw-msg"></div>
          ${passwordField('pw-current', I18n.t('accountCurrentPassword'), 'current-password')}
          ${passwordField('pw-new', I18n.t('newPassword'), 'new-password')}
          ${Auth.passwordChecklistHtml()}
          ${passwordField('pw-confirm', I18n.t('accountConfirmPassword'), 'new-password')}
          <div class="mt-3"><button type="submit" class="btn btn-primary" id="pw-save">${UI.icon('key', '', 15)} <span>${I18n.t('accountChangePassword')}</span></button></div>
        </form>
      </div>
    `;
    wireToggles(wrap);
    Auth.wirePasswordChecklist(wrap, wrap.querySelector('#pw-new'));

    // --- profile -------------------------------------------------------------
    wrap.querySelector('#profile-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = wrap.querySelector('#profile-msg');
      const name = wrap.querySelector('#acc-name').value.replace(/\s+/g, ' ').trim();
      if (name.length < 2) { msg.innerHTML = `<div class="alert alert-danger">${I18n.t('fullNameRequired')}</div>`; return; }
      const btn = wrap.querySelector('#profile-save');
      btn.disabled = true;
      try {
        const user = await Api.updateProfile(name);
        State.set({ user: { ...State.get().user, ...user } });
        UI.toast(I18n.t('accountSaved'));
      } catch (err) {
        msg.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(err))}</div>`;
        btn.disabled = false;
      }
    });

    // --- password --------------------------------------------------------------
    wrap.querySelector('#pw-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = wrap.querySelector('#pw-msg');
      const cur = wrap.querySelector('#pw-current').value;
      const nw = wrap.querySelector('#pw-new').value;
      const conf = wrap.querySelector('#pw-confirm').value;
      const fail = (t) => { msg.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(t)}</span></div>`; };
      msg.innerHTML = '';
      if (!cur) return fail(I18n.t('accountCurrentRequired'));
      if (!Auth.isStrongPassword(nw)) return fail(I18n.t('passwordTooWeak'));
      if (nw !== conf) return fail(I18n.t('accountPasswordMismatch'));
      const btn = wrap.querySelector('#pw-save');
      btn.disabled = true;
      try {
        const res = await Api.changePassword(cur, nw);
        Api.setToken(res.token);          // other sessions were signed out by the server
        wrap.querySelector('#pw-form').reset();
        Auth.wirePasswordChecklist(wrap, wrap.querySelector('#pw-new'));
        msg.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('accountPasswordChanged')}</span></div>`;
        UI.toast(I18n.t('accountPasswordChanged'));
      } catch (err) {
        fail(UI.errorMessage(err));
      }
      btn.disabled = false;
    });

    return wrap;
  }

  return { renderPage };
})();
