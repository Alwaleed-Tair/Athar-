// App shell. Subscribes to State and does a full re-render on every
// change -- topbar, modals, everything -- per spec: no persistent
// singleton components, no location.reload() on language/theme switch.

function applyThemeAndDir() {
  const { theme } = State.get();
  const lang = I18n.getLang();
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('lang', lang);
  document.documentElement.setAttribute('dir', I18n.dirFor(lang));

  // Dynamically update favicon based on active theme
  const fav = document.querySelector('link[rel="icon"]');
  if (fav) {
    fav.href = '/assets/favicon-32.png';
  }
}

function toggleTheme() {
  const next = State.get().theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('athar_theme', next);
  State.set({ theme: next });
}

function toggleLang() {
  const next = I18n.getLang() === 'ar' ? 'en' : 'ar';
  I18n.setLang(next);
  State.set({}); // trigger re-render from in-memory state, no reload
}

function setSpecificLang(targetLang) {
  if (I18n.getLang() === targetLang) return;
  I18n.setLang(targetLang);
  State.set({});
}

function logout() {
  Notifications.stop();
  Api.setToken(null);
  State.set({ user: null, route: { name: 'login' } });
}

function renderTopbar() {
  const { user, theme } = State.get();
  const isDark = theme === 'dark';
  const symbolSrc = '/assets/athar-logo-128.png';

  const bar = document.createElement('div');
  bar.className = 'topbar';

  // Brand container with logo and digital forensics label
  const brand = document.createElement('div');
  brand.className = 'brand';
  brand.innerHTML = `
    <div class="brand-icon-box">
      <img src="${symbolSrc}" alt="ATHAR" class="brand-symbol-img" />
    </div>
    <div class="brand-title">
      <span class="brand-name">${I18n.t('appName')}</span>
      <span class="brand-sub">${I18n.t('appTagline')}</span>
    </div>
  `;
  brand.style.cursor = user ? 'pointer' : 'default';
  if (user) brand.onclick = () => State.set({ route: { name: 'cases' } });

  // Controls container
  const controls = document.createElement('div');
  controls.className = 'controls';

  // Dedicated Language switch pill [ EN | عربي ]
  const currentLang = I18n.getLang();
  const langPill = document.createElement('div');
  langPill.className = 'lang-toggle-pill';
  langPill.innerHTML = `
    <button type="button" class="lang-toggle-btn ${currentLang === 'en' ? 'active' : ''}" id="top-lang-en">English</button>
    <button type="button" class="lang-toggle-btn ${currentLang === 'ar' ? 'active' : ''}" id="top-lang-ar">عربي</button>
  `;
  langPill.querySelector('#top-lang-en').onclick = () => setSpecificLang('en');
  langPill.querySelector('#top-lang-ar').onclick = () => setSpecificLang('ar');

  // Theme switch (SVG icon, no emojis)
  const themeBtn = document.createElement('button');
  themeBtn.type = 'button';
  themeBtn.className = 'theme-toggle-btn';
  themeBtn.innerHTML = theme === 'dark' ? UI.icon('sun', '', 18) : UI.icon('moon', '', 18);
  themeBtn.title = I18n.t('theme');
  themeBtn.onclick = toggleTheme;

  controls.appendChild(langPill);
  controls.appendChild(themeBtn);

  if (user) {
    // Signed-in user: real name (falls back to username) + role
    const displayName = user.full_name || user.username;
    const roleLabel = user.role === 'ADMIN' ? I18n.t('admin') : I18n.t('investigator');
    const examinerCard = document.createElement('button');
    examinerCard.type = 'button';
    examinerCard.className = 'examiner-profile-pill examiner-btn' + (State.get().route.name === 'account' ? ' active' : '');
    examinerCard.title = I18n.t('accountTitle');
    examinerCard.setAttribute('aria-label', I18n.t('accountTitle'));
    examinerCard.onclick = () => State.set({ route: { name: 'account' } });
    examinerCard.innerHTML = `
      <span class="examiner-avatar">${UI.icon('userCheck', '', 14)}</span>
      <span class="examiner-name">${UI.escapeHtml(displayName)} · <span class="text-muted">${roleLabel}</span></span>
    `;

    controls.appendChild(Notifications.renderBell());

    if (user.role === 'ADMIN') {
      const usersBtn = document.createElement('button');
      usersBtn.type = 'button';
      usersBtn.className = 'btn btn-sm btn-ghost' + (State.get().route.name === 'users' ? ' active' : '');
      usersBtn.innerHTML = `${UI.icon('user', '', 15)} <span>${I18n.t('usersNav')}</span><span class="pending-badge bell-badge" style="display:none"></span>`;
      usersBtn.style.position = 'relative';
      setTimeout(Notifications.paintPending, 0);
      usersBtn.onclick = () => State.set({ route: { name: 'users' } });
      controls.appendChild(usersBtn);
    }

    controls.appendChild(examinerCard);

    // Logout button with icon
    const logoutBtn = document.createElement('button');
    logoutBtn.className = 'btn btn-sm btn-ghost';
    logoutBtn.innerHTML = `
      ${UI.icon('arrowRight', '', 15)}
      <span>${I18n.t('logout')}</span>
    `;
    logoutBtn.onclick = logout;
    controls.appendChild(logoutBtn);
  }

  if (!user) {
    const signIn = document.createElement('button');
    signIn.type = 'button';
    signIn.className = 'btn btn-sm btn-primary';
    signIn.innerHTML = `${UI.icon('lock', '', 14)} <span>${I18n.t('signInTab')}</span>`;
    signIn.onclick = () => { try { history.replaceState(null, '', location.pathname); } catch (e) { /* ignore */ } State.set({ route: { name: 'login' } }); };
    controls.appendChild(signIn);
  }

  bar.appendChild(brand);
  bar.appendChild(controls);
  return bar;
}

async function render() {
  applyThemeAndDir();
  const root = document.getElementById('app');
  root.innerHTML = '';

  const { user, route } = State.get();

  const isPublicPage = Pages.PUBLIC.includes(route.name);

  if (!user) {
    if (isPublicPage) {
      root.appendChild(renderTopbar());
      const c = document.createElement('div');
      c.className = 'main-container';
      c.appendChild(Pages.render(route.name));
      root.appendChild(c);
    } else {
      root.appendChild(await Auth.renderLogin());
    }
    root.appendChild(Pages.footer());
    return;
  }

  root.appendChild(renderTopbar());

  const container = document.createElement('div');
  container.className = 'main-container';
  root.appendChild(container);

  if (isPublicPage) {
    container.appendChild(Pages.render(route.name));
  } else if (route.name === 'account') {
    container.appendChild(await Account.renderPage());
  } else if (route.name === 'cases') {
    container.appendChild(await Cases.renderList());
  } else if (route.name === 'case') {
    container.appendChild(await Cases.renderDetail(route.caseId, route.tab || 'overview'));
  } else if (route.name === 'users' && user.role === 'ADMIN') {
    container.appendChild(await Users.renderPage());
  } else {
    container.appendChild(await Cases.renderList());
  }
  root.appendChild(Pages.footer());
}

State.subscribe(() => { render(); });

// --- Bootstrap: validate any stored token before first render ---------
function routeFromLocation() {
  const name = (location.hash || '').replace(/^#\/?/, '');
  return Pages.PUBLIC.includes(name) ? { name } : null;
}

window.addEventListener('hashchange', () => {
  const r = routeFromLocation();
  if (r) State.set({ route: r });
});

(async function bootstrap() {
  applyThemeAndDir();

  const initial = routeFromLocation();
  const token = Api.getToken();
  if (token) {
    try {
      const user = await Api.me();
      State.set({ user, route: initial || { name: 'cases' } });
      Notifications.refresh();
      return;
    } catch (e) {
      Api.setToken(null);
    }
  }
  if (initial) State.set({ route: initial });
  else render();
})();
