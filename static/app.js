// static/app.js (loaded as type="module")
// Exposes window.fetchJson so non-module scripts (index.js) can use it.

function lsGet(k, d = "") {
  try { return localStorage.getItem(k) ?? d; } catch (_) { return d; }
}

async function restoreSessionFromLocalStorage() {
  const base_url = lsGet("lw_base_url", "").trim();
  const token = lsGet("lw_token", "").trim();

  if (!base_url || !token) return false;

  try {
    const r = await fetch("/auth/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ base_url, token }),
    });
    return r.ok;
  } catch (_) {
    return false;
  }
}

async function fetchJson(url, options = {}) {
  const opts = { credentials: "same-origin", ...options };

  let r = await fetch(url, opts);

  // If session expired, try restoring once
  if (r.status === 401) {
    const ok = await restoreSessionFromLocalStorage();
    if (!ok) return { status: 401, data: null };
    r = await fetch(url, opts);
  }

  let data = null;
  try { data = await r.json(); } catch (_) {}

  return { status: r.status, data };
}

// Make it available to non-module scripts
window.fetchJson = fetchJson;
window.restoreSessionFromLocalStorage = restoreSessionFromLocalStorage;