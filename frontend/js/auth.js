const Auth = (() => {
  let authMode = 'login'; // 'login' or 'register'

  // Renders the full login/register flow including credentials and MFA verification
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

    // Dynamic container for Login/Register Card or MFA Card
    const cardContainer = document.createElement('div');
    wrap.appendChild(cardContainer);

    // Initial view: credentials form
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

      <!-- Navigation Tabs: Sign In / Create Account -->
      <div class="auth-nav-tabs">
        <div class="auth-nav-tab ${!isRegister ? 'active' : ''}" id="tab-login-btn">
          ${I18n.t('signInTab')}
        </div>
        <div class="auth-nav-tab ${isRegister ? 'active' : ''}" id="tab-register-btn">
          ${I18n.t('createAccount')}
        </div>
      </div>

      <div class="auth-role-badge">
        ${isRegister ? UI.icon('userCheck', '', 16) : UI.icon('lock', '', 16)}
        <span>${isRegister ? I18n.t('createAccount') : I18n.t('investigatorSignIn')}</span>
      </div>

      <div id="login-error"></div>

      <form id="login-form">
        <div class="field">
          <label for="investigator-email">${I18n.t('investigatorEmail')}</label>
          <div class="field-with-icon">
            <span class="field-icon">${UI.icon('user', '', 17)}</span>
            <input 
              type="text" 
              id="investigator-email"
              name="username" 
              class="input-with-icon" 
              placeholder="admin@athar.gov" 
              value="${isRegister ? '' : 'admin@athar.gov'}"
              required 
              autofocus 
              autocapitalize="off" 
              autocorrect="off" 
              spellcheck="false" 
            />
          </div>
          ${isRegister ? `
          <div class="field-hint-box">
            ${I18n.t('emailHint')}
          </div>
          ` : ''}
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
              placeholder="••••••••••••" 
              value="${isRegister ? '' : 'admin1234'}"
              required 
              autocapitalize="off" 
              autocorrect="off" 
              spellcheck="false" 
            />
          </div>
          
          ${isRegister ? `
          <div class="pwd-checklist-box">
            <div style="font-weight:600; margin-bottom:4px;">${I18n.t('passwordRulesTitle')}</div>
            <div class="pwd-rule-item" id="rule-length"><span class="dot"></span> ${I18n.t('ruleLength')}</div>
            <div class="pwd-rule-item" id="rule-upper"><span class="dot"></span> ${I18n.t('ruleUpper')}</div>
            <div class="pwd-rule-item" id="rule-lower"><span class="dot"></span> ${I18n.t('ruleLower')}</div>
            <div class="pwd-rule-item" id="rule-number"><span class="dot"></span> ${I18n.t('ruleNumber')}</div>
            <div class="pwd-rule-item" id="rule-special"><span class="dot"></span> ${I18n.t('ruleSpecial')}</div>
          </div>
          ` : `
          <div class="forgot-pwd-row">
            <a href="javascript:void(0)" class="forgot-pwd-link" id="forgot-pwd-trigger">
              ${I18n.t('forgotPassword')}
            </a>
          </div>
          `}
        </div>

        <div class="auth-status-indicator">
          <span class="status-dot-active"></span>
          <span>${I18n.t('jwtAuthActive')}</span>
        </div>

        <!-- Interactive Neon Action Button -->
        <button type="submit" class="btn btn-primary btn-neon w-full" id="login-submit" style="padding:12px; font-size:1rem;">
          <span>${isRegister ? I18n.t('registerProceedBtn') : I18n.t('authAndProceedMfa')}</span>
        </button>
      </form>

      <!-- Toggle mode prompt -->
      <div style="text-align:center; margin-top:14px; font-size:0.84rem;">
        ${!isRegister ? `
          <a href="javascript:void(0)" id="switch-to-register" style="color:var(--color-cyan); font-weight:600;">
            ${I18n.t('dontHaveAccount')}
          </a>
        ` : `
          <a href="javascript:void(0)" id="switch-to-login" style="color:var(--color-cyan); font-weight:600;">
            ${I18n.t('alreadyHaveAccount')}
          </a>
        `}
      </div>

      <div class="restricted-warning-box">
        <span class="warning-icon">${UI.icon('shieldAlert', '', 18)}</span>
        <span>${I18n.t('restrictedAccessWarning')}</span>
      </div>
    `;

    container.appendChild(card);

    // Tab buttons & mode switcher
    card.querySelector('#tab-login-btn').onclick = () => {
      authMode = 'login';
      renderCredentialsCard(container);
    };
    card.querySelector('#tab-register-btn').onclick = () => {
      authMode = 'register';
      renderCredentialsCard(container);
    };

    const switchReg = card.querySelector('#switch-to-register');
    if (switchReg) {
      switchReg.onclick = () => {
        authMode = 'register';
        renderCredentialsCard(container);
      };
    }
    const switchLog = card.querySelector('#switch-to-login');
    if (switchLog) {
      switchLog.onclick = () => {
        authMode = 'login';
        renderCredentialsCard(container);
      };
    }

    // Live password check interaction (ONLY active in register mode)
    if (isRegister) {
      const pwdInput = card.querySelector('#investigator-password');
      const updatePasswordChecklist = () => {
        const val = (pwdInput && pwdInput.value) || '';
        const rLen = card.querySelector('#rule-length');
        const rUpp = card.querySelector('#rule-upper');
        const rLow = card.querySelector('#rule-lower');
        const rNum = card.querySelector('#rule-number');
        const rSpe = card.querySelector('#rule-special');
        if (rLen) rLen.classList.toggle('valid', val.length >= 8);
        if (rUpp) rUpp.classList.toggle('valid', /[A-Z]/.test(val));
        if (rLow) rLow.classList.toggle('valid', /[a-z]/.test(val));
        if (rNum) rNum.classList.toggle('valid', /[0-9]/.test(val));
        if (rSpe) rSpe.classList.toggle('valid', /[^A-Za-z0-9]/.test(val));
      };
      if (pwdInput) {
        pwdInput.addEventListener('input', updatePasswordChecklist);
        updatePasswordChecklist();
      }
    }

    // Forgot password modal (only rendered in login mode)
    const fpTrigger = card.querySelector('#forgot-pwd-trigger');
    if (fpTrigger) fpTrigger.onclick = openForgotPasswordModal;

    // Login / Register Form Submit
    const form = card.querySelector('#login-form');
    const errorBox = card.querySelector('#login-error');
    const submitBtn = card.querySelector('#login-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorBox.innerHTML = '';
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>${I18n.t('loggingIn')}</span>`;
      
      const fd = new FormData(form);
      const usernameInput = fd.get('username') || '';
      const passwordInput = fd.get('password') || '';

      try {
        if (authMode === 'register') {
          // Register new account
          const res = await Api.register(usernameInput, passwordInput);
          renderMfaCard(container, res);
        } else {
          // Normal login
          const res = await Api.login(usernameInput, passwordInput);
          renderMfaCard(container, res);
        }
      } catch (err) {
        const msg = err.status === 401 
          ? I18n.t('invalidCredentials') 
          : (err.message || I18n.t('genericError'));
        errorBox.innerHTML = `<div class="alert alert-danger">${UI.icon('alertTriangle', '', 18)} <span>${msg}</span></div>`;
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>${authMode === 'register' ? I18n.t('registerProceedBtn') : I18n.t('authAndProceedMfa')}</span>`;
      }
    });
  }

  // Renders the 2-Factor Authentication (MFA) step matching user design
  function renderMfaCard(container, authResult) {
    container.innerHTML = '';

    const isDark = State.get().theme === 'dark';
    const symbolSrc = isDark ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';

    const card = document.createElement('div');
    card.className = 'card mfa-card';

    card.innerHTML = `
      <div class="login-cyber-logo">
        <img src="${symbolSrc}" alt="ATHAR" class="athar-logo-img" />
      </div>
      <div class="login-brand-name">${I18n.t('appName')}</div>
      <h3 style="margin-top:6px; margin-bottom:8px;">${I18n.t('mfaTitle')}</h3>

      <div class="examiner-profile-pill" style="margin-bottom:16px;">
        <span class="examiner-avatar">${UI.icon('user', '', 14)}</span>
        <span>${I18n.t('examinerName')}</span>
      </div>

      <div class="mfa-alert-box">
        <strong>${UI.icon('alertTriangle', '', 15)} ${I18n.t('mfaAlert')}</strong>
        <div style="margin-top:5px;">${I18n.t('mfaPrompt')}</div>
      </div>

      <div id="mfa-error"></div>

      <form id="mfa-form">
        <div class="mfa-digits-wrap">
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="0" value="7" autofocus />
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="1" value="4" />
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="2" value="9" />
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="3" value="2" />
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="4" value="6" />
          <input type="text" maxlength="1" class="mfa-digit-input" data-index="5" value="8" />
        </div>

        <button type="submit" class="btn btn-primary btn-neon w-full" id="mfa-submit" style="padding:12px; margin-top:10px;">
          ${UI.icon('check', '', 18)}
          <span>${I18n.t('confirmSession')}</span>
        </button>
      </form>

      <div class="flex gap-2" style="justify-content:center; margin-top:16px;">
        <button type="button" class="btn btn-ghost btn-sm" id="mfa-resend">
          ${UI.icon('refresh', '', 14)}
          <span>${I18n.t('resendCode')}</span>
        </button>
        <button type="button" class="btn btn-ghost btn-sm" id="mfa-back">
          ${UI.icon('arrowLeft', '', 14)}
          <span>${I18n.t('backToLogin')}</span>
        </button>
      </div>
    `;

    container.appendChild(card);

    const digitInputs = card.querySelectorAll('.mfa-digit-input');
    digitInputs.forEach((inp, idx) => {
      inp.addEventListener('input', (e) => {
        const val = e.target.value;
        if (val.length === 1 && idx < digitInputs.length - 1) {
          digitInputs[idx + 1].focus();
        }
      });
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !e.target.value && idx > 0) {
          digitInputs[idx - 1].focus();
        }
      });
      inp.addEventListener('paste', (e) => {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData).getData('text').trim();
        if (pasted.length >= 6) {
          for (let i = 0; i < 6; i++) {
            digitInputs[i].value = pasted[i] || '';
          }
          digitInputs[5].focus();
        }
      });
    });

    card.querySelector('#mfa-back').onclick = () => renderCredentialsCard(container);

    const mfaForm = card.querySelector('#mfa-form');
    const mfaError = card.querySelector('#mfa-error');

    mfaForm.addEventListener('submit', (e) => {
      e.preventDefault();
      mfaError.innerHTML = '';
      
      const code = Array.from(digitInputs).map(i => i.value).join('');
      if (code.length < 6) {
        mfaError.innerHTML = `<div class="alert alert-danger">${I18n.t('invalidMfaCode')}</div>`;
        return;
      }

      // Complete authentication and launch workspace
      Api.setToken(authResult.token);
      State.set({ user: authResult.user, route: { name: 'cases' } });
      Notifications.refresh();
    });

    card.querySelector('#mfa-resend').onclick = () => {
      mfaError.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('resetSentSuccess')}</span></div>`;
    };
  }

  // Opens the Forgot Password modal dialog
  function openForgotPasswordModal() {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="modal-header">
        <h3 style="display:flex; align-items:center; gap:8px;">
          ${UI.icon('key', '', 20)}
          <span>${I18n.t('forgotPasswordTitle')}</span>
        </h3>
      </div>
      <p class="text-muted" style="font-size:0.88rem;">${I18n.t('forgotPasswordDesc')}</p>
      <div id="fp-error"></div>
      <form id="fp-form">
        <div class="field">
          <label>${I18n.t('investigatorEmail')}</label>
          <input type="email" name="email" required placeholder="admin@athar.gov" value="admin@athar.gov" />
        </div>
        <div class="flex gap-2" style="justify-content:flex-end; margin-top:20px;">
          <button type="button" id="fp-cancel" class="btn">${I18n.t('cancel')}</button>
          <button type="submit" id="fp-submit" class="btn btn-primary btn-neon">
            ${UI.icon('arrowRight', '', 16)}
            <span>${I18n.t('sendResetLink')}</span>
          </button>
        </div>
      </form>
    `;

    const { close } = UI.openModal(content);
    content.querySelector('#fp-cancel').onclick = close;

    content.querySelector('#fp-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const errBox = content.querySelector('#fp-error');
      const submitBtn = content.querySelector('#fp-submit');
      const email = content.querySelector('input[name="email"]').value;

      submitBtn.disabled = true;
      try {
        await Api.forgotPassword(email);
        errBox.innerHTML = `<div class="alert alert-success">${UI.icon('check', '', 16)} <span>${I18n.t('resetSentSuccess')}</span></div>`;
        setTimeout(() => close(), 2200);
      } catch (err) {
        submitBtn.disabled = false;
        errBox.innerHTML = `<div class="alert alert-danger">${UI.escapeHtml(err.message)}</div>`;
      }
    });
  }

  return { renderLogin };
})();