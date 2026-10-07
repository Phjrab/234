// Apply the saved visual preference before CSS/first paint. No API writes or redraws.
const Theme = (() => {
  const key = 'forge.theme';
  let mode = 'light';
  try { if (localStorage.getItem(key) === 'dark') mode = 'dark'; } catch { /* Storage is optional. */ }
  function translate(message) { return typeof t === 'function' ? t(message) : message; }
  function syncControls() {
    const toggle = document.querySelector('#theme-toggle');
    if (toggle) {
      const label = translate(mode === 'dark' ? 'Switch to white mode' : 'Switch to dark mode');
      toggle.textContent = mode === 'dark' ? '☀' : '☾';
      toggle.setAttribute('aria-label', label);
      toggle.setAttribute('title', label);
      toggle.setAttribute('aria-pressed', String(mode === 'dark'));
      toggle.onclick = () => setMode(mode === 'dark' ? 'light' : 'dark');
    }
    const select = document.querySelector('#theme-select');
    if (select) { select.value = mode; select.onchange = event => setMode(event.target.value); }
  }
  function apply() { document.documentElement?.setAttribute('data-theme', mode); }
  function setMode(next, persist = true) {
    if (!['light', 'dark'].includes(next)) return false;
    mode = next;
    if (persist) { try { localStorage.setItem(key, mode); } catch { /* In-memory switching still works. */ } }
    apply(); syncControls();
    return true;
  }
  apply();
  document.addEventListener('DOMContentLoaded', syncControls);
  document.addEventListener('forge:languagechange', syncControls);
  globalThis.addEventListener?.('storage', event => {
    if (event.key === key || event.key === null) setMode(event.newValue === 'dark' ? 'dark' : 'light', false);
  });
  return Object.freeze({setMode, syncControls, get mode() { return mode; }});
})();
