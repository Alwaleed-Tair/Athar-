// App shell. Subscribes to State and does a full re-render on every
// change -- topbar, modals, everything -- per spec: no persistent
// singleton components, no location.reload() on language/theme switch.

function applyThemeAndDir() {
  const { theme } = State.get();
  const lang = I18n.getLang();
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('lang', lang);
  document.documentElement.setAttribute('dir', I18n.dirFor(lang));
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

function logout() {
  Api.setToken(null);
  State.set({ user: null, route: { name: 'login' } });
}

function renderTopbar() {
  const { user, theme } = State.get();
  const bar = document.createElement('div');
  bar.className = 'topbar';

  const brand = document.createElement('div');
  brand.className = 'brand';
  brand.innerHTML = `<img src="/assets/logo.png" alt="${I18n.t('appName')}" class="brand-logo" />`;
  brand.style.cursor = user ? 'pointer' : 'default';
  if (user) brand.onclick = () => State.set({ route: { name: 'cases' } });

  const controls = document.createElement('div');
  controls.className = 'controls';

  const langBtn = document.createElement('button');
  langBtn.className = 'btn btn-sm';
  langBtn.textContent = I18n.getLang() === 'ar' ? 'EN' : 'AR';
  langBtn.title = I18n.t('language');
  langBtn.onclick = toggleLang;

  const themeBtn = document.createElement('button');
  themeBtn.className = 'btn btn-sm';
  themeBtn.textContent = theme === 'dark' ? '☀︎' : '☾';
  themeBtn.title = I18n.t('theme');
  themeBtn.onclick = toggleTheme;

  controls.appendChild(langBtn);
  controls.appendChild(themeBtn);

  if (user) {
    const who = document.createElement('span');
    who.className = 'text-muted text-sm';
    who.textContent = `${user.username} · ${user.role === 'ADMIN' ? I18n.t('admin') : I18n.t('investigator')}`;

    controls.appendChild(Notifications.renderBell());
    controls.appendChild(who);

    const logoutBtn = document.createElement('button');
    logoutBtn.className = 'btn btn-sm';
    logoutBtn.textContent = I18n.t('logout');
    logoutBtn.onclick = logout;
    controls.appendChild(logoutBtn);
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