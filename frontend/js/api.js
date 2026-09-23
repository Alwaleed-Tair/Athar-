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

    if (res.status === 401) {
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
      const detail = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
      throw new ApiError(detail, res.status);
    }
    return data;
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  return {
    getToken, setToken, ApiError,
    login: (username, password) => request('POST', '/api/auth/login', { body: { username, password } }),
    me: () => request('GET', '/api/auth/me'),
    createUser: (payload) => request('POST', '/api/users', { body: payload }),
    listUsers: () => request('GET', '/api/users'),

    listCases: (search) => request('GET', `/api/cases${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    createCase: (payload) => request('POST', '/api/cases', { body: payload }),
    getCase: (id) => request('GET', `/api/cases/${id}`),
    addMember: (caseId, userId) => request('POST', `/api/cases/${caseId}/members`, { body: { user_id: userId } }),
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
    uploadEvidence: (caseId, file, category) => {
      const form = new FormData();
      form.append('file', file);
      if (category) form.append('category', category);
      return request('POST', `/api/cases/${caseId}/evidence`, { body: form, isForm: true });
    },
    setEvidenceCategory: (id, category) =>
      request('PATCH', `/api/evidence/${id}/category`, { body: { category } }),
    // Plain <a href> can't carry the Authorization header, so downloads
    // are fetched as a blob and saved via a temporary object URL instead.
    downloadEvidence: async (id, suggestedFilename) => {
      const token = getToken();
      const res = await fetch(withLang(`/api/evidence/${id}/download`), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(`Download failed (${res.status})`, res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedFilename || 'evidence';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
    analyzeEvidence: (id) => request('POST', `/api/evidence/${id}/analyze`),
    checkEvidenceAuthenticity: (id) => request('POST', `/api/evidence/${id}/authenticity-check`),
  };
})();