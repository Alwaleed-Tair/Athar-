const Auth = (() => {
  async function renderLogin() {
    const wrap = document.createElement('div');
    wrap.className = 'login-wrap';

    const card = document.createElement('div');
    card.className = 'card login-card';

    card.innerHTML = `
      <div class="login-logo-wrap">
        <img src="/assets/logo.png" alt="${I18n.t('appName')}" class="login-logo" />
      </div>
      <p class="text-muted" style="text-align:center">${I18n.t('appTagline')}</p>
      <div id="login-error"></div>
      <form id="login-form">
        <div class="field">
          <label>${I18n.t('username')}</label>
          <input type="text" name="username" required autofocus />
        </div>
        <div class="field">
          <label>${I18n.t('password')}</label>
          <input type="password" name="password" required />
        </div>
        <button type="submit" class="btn btn-primary w-full" id="login-submit">${I18n.t('loginButton')}</button>
      </form>
    `;

    wrap.appendChild(card);

    const form = card.querySelector('#login-form');
    const errorBox = card.querySelector('#login-error');
    const submitBtn = card.querySelector('#login-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorBox.innerHTML = '';
      submitBtn.disabled = true;
      submitBtn.textContent = I18n.t('loggingIn');
      const fd = new FormData(form);
      try {
        const res = await Api.login(fd.get('username'), fd.get('password'));
        Api.setToken(res.token);
        State.set({ user: res.user, route: { name: 'cases' } });
        Notifications.refresh();
      } catch (err) {
        const msg = err.status === 401 ? I18n.t('invalidCredentials') : I18n.t('genericError');
        errorBox.innerHTML = `<div class="alert alert-danger">${msg}</div>`;
        submitBtn.disabled = false;
        submitBtn.textContent = I18n.t('loginButton');
      }
    });

    return wrap;
  }

  return { renderLogin };
})();