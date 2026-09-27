const Auth = (() => {
  let authMode = 'login'; // 'login' or 'register'

  // Same rules the server enforces in backend/app/routers/auth.py.
  const ALLOWED_EMAIL_DOMAINS = ['@gmail.com', '@outlook.sa', '@hotmail.com', '@athar.gov'];

  function passwordChecks(pw) {
    const val = pw || '';
    return {
      length: val.length >= 8,
      upper: /[A-Z]/.test(val),
      lower: /[a-z]/.test(val),
      number: /[0-9]/.test(val),
      special: /[^A-Za-z0-9]/.test(val),
    };
  }

  function isStrongPassword(pw) {
    return Object.values(passwordChecks(pw)).every(Boolean);
  }

  function isAllowedEmail(email) {
    const val = (email || '').trim().toLowerCase();
    return /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(val) && ALLOWED_EMAIL_DOMAINS.some((d) => val.endsWith(d));
  }

  // Password rules checklist shared by registration and the admin
  // "create user" / "reset password" forms. `input` is the password field.
  function passwordChecklistHtml() {
    return `
      <div class="pwd-checklist-box">
        <div style="font-weight:600; margin-bottom:4px;">${I18n.t('passwordRulesTitle')}</div>
        <div class="pwd-rule-item" data-rule="length"><span class="dot"></span> ${I18n.t('ruleLength')}</div>
        <div class="pwd-rule-item" data-rule="upper"><span class="dot"></span> ${I18n.t('ruleUpper')}</div>
        <div class="pwd-rule-item" data-rule="lower"><span class="dot"></span> ${I18n.t('ruleLower')}</div>
        <div class="pwd-rule-item" data-rule="number"><span class="dot"></span> ${I18n.t('ruleNumber')}</div>
        <div class="pwd-rule-item" data-rule="special"><span class="dot"></span> ${I18n.t('ruleSpecial')}</div>
      </div>
    `;
  }

  function wirePasswordChecklist(rootEl, input) {
    const update = () => {
      const checks = passwordChecks(input.value);
      rootEl.querySelectorAll('.pwd-rule-item').forEach((item) => {
        item.classList.toggle('valid', !!checks[item.dataset.rule]);
      });
    };
    input.addEventListener('input', update);
    update();
  }

  // Maps the server's English validation messages to the current UI
  // language; anything unrecognised is shown as-is.
  function friendlyError(err) {
    if (!err) return I18n.t('genericError');
    if (err.status === 401) return I18n.t('invalidCredentials');
    const msg = String(err.message || '');
    if (/already exists/i.test(msg)) return I18n.t('emailTaken');
    if (/^Password must/i.test(msg)) return I18n.t('passwordTooWeak');
    if (/^Email must/i.test(msg)) return I18n.t('emailNotAllowed');
    return msg || I18n.t('genericError');
  }

  async function renderLogin() {
    const wrap = document.createElement('div');
    wrap.className = 'login-wrap';

    // Top bar with language & theme switch
    const topBar = document.createElement('div');
    topBar.className = 'login-top-bar';

    const langToggle = document.createElement('div');
    langToggle.className = 'lang-toggle-pill';
    const currentLang = I18n.getLang();
    langToggle.innerHTML = `
      <button type="button" class="lang-toggle-btn ${currentLang === 'en' ? 'active' : ''}" id="login-lang-en">EN</button>
      <button type="button" class="lang-toggle-btn ${currentLang === 'ar' ? 'active' : ''}" id="login-lang-ar">عربي</button>
    `;
    langToggle.querySelector('#login-lang-en').onclick = () => {
      I18n.setLang('en');
      State.set({});
    };
    langToggle.querySelector('#login-lang-ar').onclick = () => {
      I18n.setLang('ar');
      State.set({});
    };

    const themeToggle = document.createElement('button');
    themeToggle.type = 'button';
    themeToggle.className = 'theme-toggle-btn';
    const isDark = State.get().theme === 'dark';
    themeToggle.innerHTML = isDark ? UI.icon('sun', '', 18) : UI.icon('moon', '', 18);
    themeToggle.title = I18n.t('theme');
    themeToggle.onclick = toggleTheme;

    topBar.appendChild(langToggle);
    topBar.appendChild(themeToggle);
    wrap.appendChild(topBar);

    const cardContainer = document.createElement('div');
    wrap.appendChild(cardContainer);
    renderCredentialsCard(cardContainer);

    return wrap;
  }

  function renderCredentialsCard(container) {
    container.innerHTML = '';

    const isRegister = authMode === 'register';
    const isDark = State.get().theme === 'dark';
    const symbolSrc = isDark ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';

    const card = document.createElement('div');
    card.className = 'card login-card';

    card.innerHTML = `
      <div class="login-cyber-logo">
        <img src="${symbolSrc}" alt="ATHAR" class="athar-logo-img" />
      </div>
      <div class="login-brand-name">${I18n.t('appName')}</div>
      <div class="login-tagline">${I18n.t('appTagline')}</div>

      <div class="auth-nav-tabs">
        <div class="auth-nav-tab ${!isRegister ? 'active' : ''}" id="tab-login-btn">
          ${I18n.t('signInTab')}
        </div>
        <div class="auth-nav-tab ${isRegister ? 'active' : ''}" id="tab-register-btn">
          ${I18n.t('createAccount')}
        </div>
      </div>

      <div id="login-error"></div>

      <form id="login-form" novalidate>
        ${isRegister ? `
        <div class="field">
          <label for="investigator-fullname">${I18n.t('fullName')}</label>
          <div class="field-with-icon">
            <span class="field-icon">${UI.icon('userCheck', '', 17)}</span>
            <input
              type="text"
              id="investigator-fullname"
              name="full_name"
              class="input-with-icon"
              placeholder="${I18n.t('fullNamePlaceholder')}"
              maxlength="120"
              autocomplete="name"
              required
            />
          </div>
        </div>
        ` : ''}

        <div class="field">
          <label for="investigator-email">${isRegister ? I18n.t('investigatorEmail') : I18n.t('usernameOrEmail')}</label>
          <div class="field-with-icon">
            <span class="field-icon">${UI.icon('user', '', 17)}</span>
            <input
              type="text"
              id="investigator-email"
              name="username"
              class="input-with-icon"
              placeholder="${isRegister ? 'name@gmail.com' : I18n.t('usernameOrEmail')}"
              autocomplete="username"
              required
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
            />
          </div>
          ${isRegister ? `<div class="field-hint-box">${I18n.t('emailHint')}</div>` : ''}
        </div>

        <div class="field">
          <label for="investigator-password">${I18n.t('password')}</label>
          <div class="field-with-icon">
            <span class="field-icon">${UI.icon('key', '', 17)}</span>
            <input
              type="password"
              id="investigator-password"
              name="password"
              class="input-with-icon"
              placeholder="••••••••"
              autocomplete="${isRegister ? 'new-password' : 'current-password'}"
              required
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
            />
          </div>
          ${isRegister ? passwordChecklistHtml() : `
          <div class="forgot-pwd-row">
            <a href="javascript:void(0)" class="forgot-pwd-link" id="forgot-pwd-trigger">
              ${I18n.t('forgotPassword')}
            </a>
          </div>
          `}
        </div>

        <button type="submit" class="btn btn-primary btn-neon w-full" id="login-submit" style="padding:12px; font-size:1rem;">
          <span>${isRegister ? I18n.t('registerBtn') : I18n.t('loginButton')}</span>
        </button>
      </form>

      <div style="text-align:center; margin-top:14px; font-size:0.84rem;">
        <a href="javascript:void(0)" id="switch-mode" style="color:var(--color-cyan); font-weight:600;">
          ${isRegister ? I18n.t('alreadyHaveAccount') : I18n.t('dontHaveAccount')}
        </a>
      </div>

      <div class="restricted-warning-box">
        <span class="warning-icon">${UI.icon('shieldAlert', '', 18)}</span>
        <span>${I18n.t('restrictedAccessWarning')}</span>
      </div>
    `;

    container.appendChild(card);

    const switchTo = (mode) => {
      authMode = mode;
      renderCredentialsCard(container);
    };
    card.querySelector('#tab-login-btn').onclick = () => switchTo('login');
    card.querySelector('#tab-register-btn').onclick = () => switchTo('register');
    card.querySelector('#switch-mode').onclick = () => switchTo(isRegister ? 'login' : 'register');

    const pwdInput = card.querySelector('#investigator-password');
    if (isRegister) wirePasswordChecklist(card, pwdInput);

    const fpTrigger = card.querySelector('#forgot-pwd-trigger');
    if (fpTrigger) fpTrigger.onclick = openForgotPasswordModal;

    const firstField = card.querySelector(isRegister ? '#investigator-fullname' : '#investigator-email');
    setTimeout(() => firstField && firstField.focus(), 0);

    const form = card.querySelector('#login-form');
    const errorBox = card.querySelector('#login-error');
    const submitBtn = card.querySelector('#login-submit');
    const submitLabel = isRegister ? I18n.t('registerBtn') : I18n.t('loginButton');

    const showError = (msg) => {
      errorBox.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 18)} <span>${UI.escapeHtml(msg)}</span></div>`;
    };

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorBox.innerHTML = '';

      const fd = new FormData(form);
      const fullName = String(fd.get('full_name') || '').trim();
      const username = String(fd.get('username') || '').trim();
      const password = String(fd.get('password') || '');

      // Client-side checks mirror the server so the user gets an
      // immediate, translated message instead of a round-trip error.
      if (isRegister) {
        if (fullName.length < 2) return showError(I18n.t('fullNameRequired'));
        if (!isAllowedEmail(username)) return showError(I18n.t('emailNotAllowed'));
        if (!isStrongPassword(password)) return showError(I18n.t('passwordTooWeak'));
      } else if (!username || !password) {
        return showError(I18n.t('fillAllFields'));
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>${I18n.t('loggingIn')}</span>`;

      try {
        const res = isRegister
          ? await Api.register(fullName, username, password)
          : await Api.login(username, password);
        authMode = 'login';
        Api.setToken(res.token);
        State.set({ user: res.user, route: { name: 'cases' } });
        Notifications.refresh();
      } catch (err) {
        showError(friendlyError(err));
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>${submitLabel}</span>`;
      }
    });
  }

  // There is no outgoing mail server, so rather than pretend to send a
  // reset link, tell the user how a reset actually happens here: an
  // admin sets a new password from the Users screen.
  function openForgotPasswordModal() {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="display:flex; align-items:center; gap:8px; margin:0;">
          ${UI.icon('key', '', 20)}
          <span>${I18n.t('forgotPasswordTitle')}</span>
        </h3>
      </div>
      <p>${I18n.t('forgotPasswordContactAdmin')}</p>
      <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
        <button type="button" id="fp-close" class="btn btn-primary">${I18n.t('gotIt')}</button>
      </div>
    `;
    const { close } = UI.openModal(content);
    content.querySelector('#fp-close').onclick = close;
  }

  return { renderLogin, passwordChecklistHtml, wirePasswordChecklist, isStrongPassword, friendlyError };
})();
