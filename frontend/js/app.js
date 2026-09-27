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
    fav.href = theme === 'dark' ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';
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
  Api.setToken(null);
  State.set({ user: null, route: { name: 'login' } });
}

function renderTopbar() {
  const { user, theme } = State.get();
  const isDark = theme === 'dark';
  const symbolSrc = isDark ? '/assets/symbol-dark.png' : '/assets/symbol-light.png';

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

  // Center / dev mode banner
  const centerInfo = document.createElement('div');
  centerInfo.className = 'flex items-center gap-2';
  centerInfo.innerHTML = `
    <span class="dev-mode-pill">
      ${UI.icon('cpu', '', 14)}
      <span>${I18n.t('devModeBanner')}</span>
    </span>
  `;

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
    // Examiner profile card
    const examinerCard = document.createElement('div');
    examinerCard.className = 'examiner-profile-pill';
    examinerCard.innerHTML = `
      <span class="examiner-avatar">${UI.icon('userCheck', '', 14)}</span>
      <span>${I18n.t('examinerName')}</span>
    `;

    controls.appendChild(Notifications.renderBell());
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

  bar.appendChild(brand);
  bar.appendChild(centerInfo);
  bar.appendChild(controls);
  return bar;
}

async function render() {
  applyThemeAndDir();
  const root = document.getElementById('app');
  root.innerHTML = '';

  const { user, route } = State.get();

  if (!user) {
    root.appendChild(await Auth.renderLogin());
    return;
  }

  root.appendChild(renderTopbar());

  const container = document.createElement('div');
  container.className = 'main-container';
  root.appendChild(container);

  if (route.name === 'cases') {
    container.appendChild(await Cases.renderList());
  } else if (route.name === 'case') {
    container.appendChild(await Cases.renderDetail(route.caseId, route.tab || 'overview'));
  } else {
    container.appendChild(await Cases.renderList());
  }
}

State.subscribe(() => { render(); });

// --- Bootstrap: validate any stored token before first render ---------
(async function bootstrap() {
  applyThemeAndDir();
  const token = Api.getToken();
  if (token) {
    try {
      const user = await Api.me();
      State.set({ user, route: { name: 'cases' } });
      Notifications.refresh();
      return;
    } catch (e) {
      Api.setToken(null);
    }
  }
  render();
})();