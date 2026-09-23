// Minimal in-memory state store. Switching language or theme updates this
// state and calls the subscribed render function -- it never calls
// location.reload().
const State = (() => {
  let data = {
    user: null,       // {id, username, role}
    route: { name: 'login' },  // {name: 'login'|'cases'|'case', caseId?}
    theme: localStorage.getItem('athar_theme') || 'light',
  };
  let listeners = [];

  function get() { return data; }
  function set(partial) {
    data = { ...data, ...partial };
    listeners.forEach((fn) => fn(data));
  }
  function subscribe(fn) { listeners.push(fn); }

  return { get, set, subscribe };
})();
