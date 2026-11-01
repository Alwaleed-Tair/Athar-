// Central API client. This is the ONE place that attaches the auth token
// and the `lang` query parameter to every request, per spec: "الواجهة
// ترسله تلقائياً من مكان مركزي واحد (api.js)".
const Api = (() => {
  const TOKEN_KEY = 'athar_token';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  function withLang(url) {
    const lang = I18n.getLang();
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}lang=${encodeURIComponent(lang)}`;
  }

  async function request(method, path, { body, isForm } = {}) {
    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (body && !isForm) headers['Content-Type'] = 'application/json';

    const res = await fetch(withLang(path), {
      method,
      headers,
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    });

    // A 401 on an authenticated request means the session expired, so
    // drop it and go back to sign-in. A 401 from sign-in itself (wrong
    // password) must NOT do that -- it would redraw the login screen and
    // wipe the "invalid credentials" message before the user sees it.
    if (res.status === 401 && token && !path.startsWith('/api/auth/')) {
      setToken(null);
      State.set({ user: null, token: null, route: { name: 'login' } });
      throw new ApiError('Session expired. Please log in again.', 401);
    }

    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = text; }
    }

    if (!res.ok) {
      let detail = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
      // FastAPI validation errors arrive as a list of objects; flatten to a short string.
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg || '').filter(Boolean).join('; ') || `Request failed (${res.status})`;
      if (typeof detail !== 'string') detail = `Request failed (${res.status})`;
      const err = new ApiError(detail, res.status);
      err.retryAfter = Number(res.headers.get('Retry-After')) || 0;
      throw err;
    }
    return data;
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
      // Server-defined machine codes (EMAIL_NOT_VERIFIED, TOKEN_EXPIRED, ...) are all-caps tokens.
      this.code = /^[A-Z][A-Z_]+$/.test(message) ? message : '';
    }
  }

  // Fetches a binary response with the auth header and saves it (plain
  // <a href> cannot carry the Authorization header).
  async function saveBlob(path, fallbackName) {
    const token = getToken();
    const res = await fetch(withLang(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) {
      let code = '';
      try { code = (await res.json()).detail || ''; } catch (e) { /* not JSON */ }
      throw new ApiError(typeof code === 'string' && code ? code : `Download failed (${res.status})`, res.status);
    }
    const cd = res.headers.get('Content-Disposition') || '';
    const m = /filename="?([^";]+)"?/.exec(cd);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (m && m[1]) || fallbackName || 'download';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return {
    getToken, setToken, ApiError,
    login: (username, password) => request('POST', '/api/auth/login', { body: { username, password } }),
    register: (fullName, username, password) =>
      request('POST', '/api/auth/register', { body: { full_name: fullName, username, password } }),
    verifyEmail: (token) => request('POST', '/api/auth/verify-email', { body: { token } }),
    resendVerification: (email) => request('POST', '/api/auth/resend-verification', { body: { email } }),
    me: () => request('GET', '/api/auth/me'),
    updateProfile: (fullName) => request('PATCH', '/api/auth/me', { body: { full_name: fullName } }),
    changePassword: (currentPassword, newPassword) =>
      request('POST', '/api/auth/change-password', { body: { current_password: currentPassword, new_password: newPassword } }),
    createUser: (payload) => request('POST', '/api/users', { body: payload }),
    listUsers: () => request('GET', '/api/users'),
    adminVerifyUser: (userId) => request('POST', `/api/users/${userId}/verify`),
    resetUserPassword: (userId, newPassword) =>
      request('POST', `/api/users/${userId}/password`, { body: { new_password: newPassword } }),

    sendContact: (payload) => request('POST', '/api/contact', { body: payload }),
    listContactMessages: () => request('GET', '/api/contact/messages'),
    markContactHandled: (id) => request('POST', `/api/contact/messages/${id}/handled`),

    search: (q, caseId) => {
      const p = new URLSearchParams({ q });
      if (caseId) p.append('case_id', caseId);
      return request('GET', `/api/search?${p.toString()}`);
    },
    getRelated: (caseId) => request('GET', `/api/cases/${caseId}/related`),
    downloadReport: (caseId) => saveBlob(`/api/cases/${caseId}/report`, 'athar-report.pdf'),

    listCases: (search = '', status = '', priority = '') => {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (status && status !== 'ALL') params.append('status', status);
      if (priority && priority !== 'ALL') params.append('priority', priority);
      const q = params.toString();
      return request('GET', `/api/cases${q ? `?${q}` : ''}`);
    },
    createCase: (payload) => request('POST', '/api/cases', { body: payload }),
    getCase: (id) => request('GET', `/api/cases/${id}`),
    addMember: (caseId, email) => request('POST', `/api/cases/${caseId}/members`, { body: { email } }),
    removeMember: (caseId, userId) => request('DELETE', `/api/cases/${caseId}/members/${userId}`),
    listMembers: (caseId) => request('GET', `/api/cases/${caseId}/members`),
    caseAudit: (caseId) => request('GET', `/api/cases/${caseId}/audit`),
    verifyCaseChain: (caseId) => request('GET', `/api/cases/${caseId}/verify`),
    getEvidenceMap: (caseId) => request('GET', `/api/cases/${caseId}/evidence-map`),
    getCrossCaseAlerts: (caseId) => request('GET', `/api/cases/${caseId}/cross-case-alerts`),
    deleteCase: (caseId) => request('DELETE', `/api/cases/${caseId}`),
    getCaseSummary: (caseId) => request('GET', `/api/cases/${caseId}/summary`),
    generateCaseSummary: (caseId) => request('POST', `/api/cases/${caseId}/summary/generate`),

    listEvidence: (caseId) => request('GET', `/api/cases/${caseId}/evidence`),
    getEvidence: (id) => request('GET', `/api/evidence/${id}`),
    uploadEvidence: (caseId, file, category, title, description) => {
      const form = new FormData();
      form.append('file', file);
      if (category) form.append('category', category);
      if (title) form.append('title', title);
      if (description) form.append('description', description);
      return request('POST', `/api/cases/${caseId}/evidence`, { body: form, isForm: true });
    },
    updateEvidence: (id, fields) => request('PATCH', `/api/evidence/${id}`, { body: fields }),
    deleteEvidence: (id) => request('DELETE', `/api/evidence/${id}`),
    verifyEvidenceIntegrity: (id) => request('POST', `/api/evidence/${id}/verify-integrity`),
    getConversation: (id, { q = '', offset = 0, limit = 200 } = {}) => {
      const p = new URLSearchParams({ offset, limit });
      if (q) p.append('q', q);
      return request('GET', `/api/evidence/${id}/conversation?${p.toString()}`);
    },
    summarizeConversation: (id) => request('POST', `/api/evidence/${id}/conversation/summary`),
    // Plain <a href> can't carry the Authorization header, so downloads
    // are fetched as a blob and saved via a temporary object URL instead.
    downloadEvidence: (id, suggestedFilename) => saveBlob(`/api/evidence/${id}/download`, suggestedFilename || 'evidence'),
    analyzeEvidence: (id) => request('POST', `/api/evidence/${id}/analyze`),
    checkEvidenceAuthenticity: (id) => request('POST', `/api/evidence/${id}/authenticity-check`),
  };
})();
