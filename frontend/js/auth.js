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
    if (err.code) return UI.errorMessage(err);
    if (err.status === 401) return I18n.t('invalidCredentials');
    const msg = String(err.message || '');
    if (/already exists/i.test(msg)) return I18n.t('emailTaken');
    if (/^Password must/i.test(msg)) return I18n.t('passwordTooWeak');
    if (/^Email must/i.test(msg)) return I18n.t('emailNotAllowed');
    return UI.errorMessage(err);
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
            <button type="button" class="pw-toggle" id="pw-toggle" aria-label="${I18n.t('showPassword')}">${UI.icon('eye', '', 16)}</button>
          </div>
          ${isRegister ? passwordChecklistHtml() : `
          <div class="forgot-pwd-row">
            <button type="button" class="link-btn forgot-pwd-link" id="forgot-pwd-trigger">
              ${I18n.t('forgotPassword')}
            </button>
          </div>
          `}
        </div>

        <button type="submit" class="btn btn-primary btn-neon w-full" id="login-submit" style="padding:12px; font-size:1rem;">
          <span>${isRegister ? I18n.t('registerBtn') : I18n.t('loginButton')}</span>
        </button>
      </form>

      <div style="text-align:center; margin-top:14px; font-size:0.84rem;">
        <button type="button" class="link-btn" id="switch-mode" style="color:var(--color-cyan); font-weight:600;">
          ${isRegister ? I18n.t('alreadyHaveAccount') : I18n.t('dontHaveAccount')}
        </button>
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

    try {
      const notice = sessionStorage.getItem('athar_notice');
      if (notice) {
        sessionStorage.removeItem('athar_notice');
        card.querySelector('#login-error').innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 18)} <span>${I18n.t(notice)}</span></div>`;
      }
    } catch (e) { /* storage unavailable */ }
    const pwdInput = card.querySelector('#investigator-password');
    if (isRegister) wirePasswordChecklist(card, pwdInput);
    const pwToggle = card.querySelector('#pw-toggle');
    pwToggle.onclick = () => {
      const show = pwdInput.type === 'password';
      pwdInput.type = show ? 'text' : 'password';
      pwToggle.innerHTML = UI.icon(show ? 'eyeOff' : 'eye', '', 16);
    };

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
      submitBtn.innerHTML = `<span class="spinner"></span> <span>${isRegister ? I18n.t('registering') : I18n.t('loggingIn')}</span>`;

      try {
        if (isRegister) {
          const res = await Api.register(fullName, username, password);
          authMode = 'login';
          renderCheckEmail(container, res.email, res.email_delivery);
          return;
        }
        const res = await Api.login(username, password);
        Api.setToken(res.token);
        State.set({ user: res.user, route: { name: 'cases' } });
        Notifications.refresh();
      } catch (err) {
        if (err.code === 'EMAIL_NOT_VERIFIED') {
          renderCheckEmail(container, username, null, { fromLogin: true });
          return;
        }
        showError(friendlyError(err));
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>${submitLabel}</span>`;
      }
    });
  }

  // "Check your e-mail" screen shown after registering, or when a correct
  // password is used on an account that is not verified yet. It never claims
  // an e-mail was sent unless the server says so.
  function renderCheckEmail(container, email, delivery, { fromLogin = false } = {}) {
    container.innerHTML = '';
    const isDark = State.get().theme === 'dark';
    const symbolSrc = isDark ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';
    const card = document.createElement('div');
    card.className = 'card login-card';
    const canEmail = delivery === 'SENT' || delivery === 'CONSOLE';
    let statusHtml;
    if (fromLogin) {
      statusHtml = `<div class="alert alert-warning">${UI.icon('mail', '', 18)} <span>${I18n.t('verifyNeededBody', { email: `<bdi dir="ltr">${UI.escapeHtml(email)}</bdi>` })}</span></div>`;
    } else if (canEmail) {
      statusHtml = `<div class="alert alert-success">${UI.icon('mail', '', 18)} <span>${I18n.t('verifySentBody', { email: `<bdi dir="ltr">${UI.escapeHtml(email)}</bdi>`, hours: 24 })}</span></div>
        ${delivery === 'CONSOLE' ? `<div class="alert alert-warning mt-2">${I18n.t('verifyConsoleNote')}</div>` : ''}`;
    } else {
      statusHtml = `<div class="alert alert-warning">${UI.icon('alertTriangle', '', 18)} <span>${I18n.t('verifyNotSentBody', { email: `<bdi dir="ltr">${UI.escapeHtml(email)}</bdi>` })}</span></div>`;
    }
    card.innerHTML = `
      <div class="login-cyber-logo"><img src="${symbolSrc}" alt="ATHAR" class="athar-logo-img" /></div>
      <div class="login-brand-name">${fromLogin ? I18n.t('verifyNeededTitle') : I18n.t('verifySentTitle')}</div>
      <div class="mt-3">${statusHtml}</div>
      <p class="text-muted text-sm mt-3">${I18n.t('verifyCheckSpam')}</p>
      <div id="resend-msg" aria-live="polite"></div>
      <div class="flex gap-2 mt-3" style="flex-wrap:wrap;">
        <button type="button" class="btn btn-primary" id="resend-btn">${UI.icon('refresh', '', 15)} <span>${I18n.t('verifyResend')}</span></button>
        <button type="button" class="btn btn-ghost" id="back-login">${UI.icon('arrowLeft', '', 15)} <span>${I18n.t('backToLogin')}</span></button>
      </div>`;
    container.appendChild(card);

    const msg = card.querySelector('#resend-msg');
    const btn = card.querySelector('#resend-btn');
    card.querySelector('#back-login').onclick = () => { authMode = 'login'; renderCredentialsCard(container); };

    function cooldown(seconds) {
      btn.disabled = true;
      const label = btn.querySelector('span:last-child');
      let left = seconds;
      const tick = () => {
        if (left <= 0) { btn.disabled = false; label.textContent = I18n.t('verifyResend'); return; }
        label.textContent = I18n.t('verifyResendIn', { seconds: left });
        left -= 1;
        setTimeout(tick, 1000);
      };
      tick();
    }
    if (!fromLogin) cooldown(60);

    btn.onclick = async () => {
      btn.disabled = true;
      msg.innerHTML = '';
      try {
        const res = await Api.resendVerification(email);
        const ok = res.email_delivery === 'SENT' || res.email_delivery === 'CONSOLE';
        msg.innerHTML = ok
          ? `<div class="alert alert-success mt-2">${UI.icon('check', '', 16)} <span>${I18n.t('verifyResent')}</span></div>`
          : `<div class="alert alert-warning mt-2">${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('verifyNotSentShort')}</span></div>`;
        cooldown(60);
      } catch (err) {
        msg.innerHTML = `<div class="alert alert-danger mt-2">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(UI.errorMessage(err))}</span></div>`;
        cooldown(err.retryAfter || 60);
      }
    };
  }

  // Landing page for the link in the verification e-mail (?verify=TOKEN).
  async function renderVerifyPage(token) {
    const wrap = document.createElement('div');
    wrap.className = 'login-wrap';
    const isDark = State.get().theme === 'dark';
    const symbolSrc = isDark ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';
    const card = document.createElement('div');
    card.className = 'card login-card';
    card.innerHTML = `
      <div class="login-cyber-logo"><img src="${symbolSrc}" alt="ATHAR" class="athar-logo-img" /></div>
      <div class="login-brand-name">${I18n.t('verifyPageTitle')}</div>
      <div id="verify-body" class="mt-3">${UI.spinner(I18n.t('verifyChecking'))}</div>`;
    wrap.appendChild(card);
    const body = card.querySelector('#verify-body');

    const goLogin = () => { authMode = 'login'; State.set({ route: { name: 'login' } }); };
    try {
      const res = await Api.verifyEmail(token);
      body.innerHTML = `
        <div class="alert alert-success">${UI.icon('shieldCheck', '', 18)} <span>${res.status === 'ALREADY_VERIFIED' ? I18n.t('verifyAlready') : I18n.t('verifySuccess')}</span></div>
        <div class="mt-3"><button type="button" class="btn btn-primary btn-neon w-full" id="v-login">${I18n.t('signInTab')}</button></div>`;
      body.querySelector('#v-login').onclick = goLogin;
    } catch (err) {
      const expired = err.code === 'TOKEN_EXPIRED';
      body.innerHTML = `
        <div class="alert alert-danger">${UI.icon('alertTriangle', '', 18)} <span>${expired ? I18n.t('err_TOKEN_EXPIRED') : I18n.t('err_TOKEN_INVALID')}</span></div>
        <p class="text-muted text-sm mt-3">${I18n.t('verifyRequestNew')}</p>
        <div id="v-msg"></div>
        <form id="v-form" class="mt-2" novalidate>
          <div class="field"><label for="v-email">${I18n.t('investigatorEmail')}</label>
            <input id="v-email" type="email" dir="ltr" autocomplete="email" autocapitalize="off" /></div>
          <button type="submit" class="btn btn-primary w-full" id="v-send">${UI.icon('mail', '', 15)} <span>${I18n.t('verifyResend')}</span></button>
        </form>
        <div class="mt-3" style="text-align:center;"><button type="button" class="btn btn-ghost btn-sm" id="v-login">${I18n.t('backToLogin')}</button></div>`;
      body.querySelector('#v-login').onclick = goLogin;
      body.querySelector('#v-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = body.querySelector('#v-email').value.trim();
        const m = body.querySelector('#v-msg');
        if (!email) { m.innerHTML = `<div class="alert alert-danger">${I18n.t('fillAllFields')}</div>`; return; }
        const send = body.querySelector('#v-send');
        send.disabled = true;
        try {
          const r = await Api.resendVerification(email);
          const ok = r.email_delivery === 'SENT' || r.email_delivery === 'CONSOLE';
          m.innerHTML = ok
            ? `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('verifyResent')}</span></div>`
            : `<div class="alert alert-warning">${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('verifyNotSentShort')}</span></div>`;
        } catch (e2) {
          m.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(e2))}</div>`;
        }
        setTimeout(() => { send.disabled = false; }, 4000);
      });
    }
    return wrap;
  }

  // Forgot password: asks for the e-mail and sends a one-hour, single-use
  // reset link. The answer is the same whether or not the account exists, and
  // it says so honestly if the server cannot send e-mail.
  function openForgotPasswordModal() {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="display:flex; align-items:center; gap:8px; margin:0;">${UI.icon('key', '', 20)} <span>${I18n.t('forgotPasswordTitle')}</span></h3>
      </div>
      <p class="text-muted text-sm">${I18n.t('forgotIntro')}</p>
      <div id="fp-msg" aria-live="polite"></div>
      <form id="fp-form" novalidate>
        <div class="field"><label for="fp-email">${I18n.t('investigatorEmail')}</label>
          <input id="fp-email" type="email" dir="ltr" autocomplete="email" autocapitalize="off" /></div>
        <div class="flex gap-2" style="justify-content:flex-end; margin-top:16px;">
          <button type="button" id="fp-close" class="btn">${I18n.t('close')}</button>
          <button type="submit" id="fp-send" class="btn btn-primary">${UI.icon('mail', '', 15)} <span>${I18n.t('forgotSend')}</span></button>
        </div>
      </form>`;
    const { close } = UI.openModal(content);
    content.querySelector('#fp-close').onclick = close;
    content.querySelector('#fp-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = content.querySelector('#fp-email').value.trim();
      const msg = content.querySelector('#fp-msg');
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) { msg.innerHTML = `<div class="alert alert-danger">${I18n.t('contactErrEmail')}</div>`; return; }
      const btn = content.querySelector('#fp-send');
      btn.disabled = true;
      try {
        const r = await Api.forgotPassword(email);
        const ok = r.email_delivery === 'SENT' || r.email_delivery === 'CONSOLE';
        msg.innerHTML = ok
          ? `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('forgotSent')}</span></div>`
          : `<div class="alert alert-warning">${UI.icon('alertTriangle', '', 16)} <span>${I18n.t('forgotNotSent')}</span></div>`;
      } catch (err) {
        msg.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(UI.errorMessage(err))}</div>`;
      }
      setTimeout(() => { btn.disabled = false; }, 3000);
    });
  }

  // Landing page for the link in the reset e-mail (?reset=TOKEN).
  async function renderResetPage(token) {
    const wrap = document.createElement('div');
    wrap.className = 'login-wrap';
    const symbolSrc = State.get().theme === 'dark' ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';
    const card = document.createElement('div');
    card.className = 'card login-card';
    card.innerHTML = `
      <div class="login-cyber-logo"><img src="${symbolSrc}" alt="ATHAR" class="athar-logo-img" /></div>
      <div class="login-brand-name">${I18n.t('resetTitle')}</div>
      <div id="rs-msg" class="mt-3" aria-live="polite"></div>
      <form id="rs-form" novalidate>
        <div class="field"><label for="rs-pw">${I18n.t('newPassword')}</label>
          <div class="field-with-icon"><span class="field-icon">${UI.icon('key', '', 17)}</span>
            <input id="rs-pw" type="password" class="input-with-icon" autocomplete="new-password" autocapitalize="off" spellcheck="false" /></div>
          ${passwordChecklistHtml()}</div>
        <div class="field"><label for="rs-pw2">${I18n.t('accountConfirmPassword')}</label>
          <div class="field-with-icon"><span class="field-icon">${UI.icon('key', '', 17)}</span>
            <input id="rs-pw2" type="password" class="input-with-icon" autocomplete="new-password" autocapitalize="off" spellcheck="false" /></div></div>
        <button type="submit" class="btn btn-primary btn-neon w-full" id="rs-go">${I18n.t('resetSubmit')}</button>
      </form>
      <div class="mt-3" style="text-align:center;"><button type="button" class="btn btn-ghost btn-sm" id="rs-login">${I18n.t('backToLogin')}</button></div>`;
    wrap.appendChild(card);
    wirePasswordChecklist(card, card.querySelector('#rs-pw'));
    const msg = card.querySelector('#rs-msg');
    card.querySelector('#rs-login').onclick = () => { authMode = 'login'; State.set({ route: { name: 'login' } }); };
    card.querySelector('#rs-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const pw = card.querySelector('#rs-pw').value;
      const fail = (t) => { msg.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 16)} <span>${UI.escapeHtml(t)}</span></div>`; };
      if (!isStrongPassword(pw)) return fail(I18n.t('passwordTooWeak'));
      if (pw !== card.querySelector('#rs-pw2').value) return fail(I18n.t('accountPasswordMismatch'));
      const btn = card.querySelector('#rs-go');
      btn.disabled = true;
      try {
        await Api.resetPassword(token, pw);
        card.querySelector('#rs-form').remove();
        msg.innerHTML = `<div class="alert alert-success">${UI.icon('shieldCheck', '', 18)} <span>${I18n.t('resetDone')}</span></div>`;
      } catch (err) {
        fail(err.code === 'TOKEN_EXPIRED' ? I18n.t('resetTokenExpired') : err.code === 'TOKEN_INVALID' ? I18n.t('resetTokenInvalid') : UI.errorMessage(err));
        btn.disabled = false;
      }
    });
    return wrap;
  }

  return { renderLogin, renderVerifyPage, renderResetPage, passwordChecklistHtml, wirePasswordChecklist, isStrongPassword, friendlyError };
})();
