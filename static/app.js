function lsGet(key, fallback = "") {
    try {
        return localStorage.getItem(key) ?? fallback;
    } catch (_) {
        return fallback;
    }
}

async function restoreSessionFromLocalStorage() {
    const base_url = lsGet("lw_base_url", "").trim();
    const token = lsGet("lw_token", "").trim();

    if (!base_url || !token) return false;

    try {
        const r = await fetch("/auth/restore", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify({base_url, token}),
        });
        return r.ok;
    } catch (_) {
        return false;
    }
}

async function fetchJson(url, options = {}) {
    const opts = {credentials: "same-origin", ...options};

    let r = await fetch(url, opts);

    if (r.status === 401) {
        const ok = await restoreSessionFromLocalStorage();
        if (!ok) return {status: 401, data: null};
        r = await fetch(url, opts);
    }

    let data = null;
    try {
        data = await r.json();
    } catch (_) {
    }

    return {status: r.status, data};
}

window.fetchJson = fetchJson;
window.restoreSessionFromLocalStorage = restoreSessionFromLocalStorage;

(function () {
    function updateSidebarToggleVisibility() {
        const btn = document.getElementById("sidebarToggle");
        if (!btn) return;

        const sidebarEl = document.getElementById("sidebar");

        let showSidebar = false;
        try {
            showSidebar = (localStorage.getItem("lw_show_sidebar") || "0") === "1";
        } catch (_) {
            showSidebar = false;
        }
        if (!sidebarEl) {
            btn.style.visibility = "hidden";
            btn.style.pointerEvents = "none";
            btn.setAttribute("aria-expanded", "false");
            return;
        }
        if (!showSidebar) {
            btn.style.visibility = "hidden";
            btn.style.pointerEvents = "none";
            btn.setAttribute("aria-expanded", "false");
            return;
        }
        btn.style.visibility = "visible";
        btn.style.pointerEvents = "auto";

        const isOpen = document.body.classList.contains("sidebar-open");
        btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", updateSidebarToggleVisibility);
    } else {
        updateSidebarToggleVisibility();
    }

    window.addEventListener("storage", (e) => {
        if (e.key === "lw_show_sidebar" || e.key === "lw_sidebar_open") {
            updateSidebarToggleVisibility();
        }
    });

    window.addEventListener("lw:settings-changed", updateSidebarToggleVisibility);
})();