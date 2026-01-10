(function () {
  // ---------- Helpers ----------
  function lsGet(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      return v === null ? fallback : v;
    } catch (_) {
      return fallback;
    }
  }

  function lsSet(key, value) {
    try {
      localStorage.setItem(key, String(value));
    } catch (_) {}
  }

  function clampInt(v, min, max, fallback) {
    const n = parseInt(v, 10);
    if (Number.isNaN(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  // ---------- Keys ----------
  const KEYS = {
    theme: "lw_theme",
    cols: "lw_grid_columns",
    gap: "lw_grid_spacing",
    openNewTab: "lw_open_new_tab",
    sortMode: "lw_sort_mode",
    bgMode: "lw_bg_mode",
    bgUrl: "lw_bg_url",
    bgColor: "lw_bg_color",
    textColor: "lw_text_color",
    showSidebar: "lw_show_sidebar",
    sidebarOpen: "lw_sidebar_open",
    collectionId: "lw_collection_id",
  };

  function shouldOpenNewTab() {
    return lsGet(KEYS.openNewTab, "1") === "1";
  }

  async function fetchJson(url, options) {
    if (typeof window.fetchJson === "function") {
      return window.fetchJson(url, options);
    }
    const r = await fetch(url, { credentials: "same-origin", ...(options || {}) });
    let data = null;
    try {
      data = await r.json();
    } catch (_) {}
    return { status: r.status, data };
  }

  function setToggleExpanded(isOpen) {
    const btn = document.getElementById("sidebarToggle");
    if (btn) btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  // ---------- Apply UI prefs ----------
  function applyPrefs() {
    const theme = lsGet(KEYS.theme, "auto");
    const cols = clampInt(lsGet(KEYS.cols, "6"), 4, 12, 6);
    const gap = clampInt(lsGet(KEYS.gap, "14"), 0, 32, 14);

    const bgMode = lsGet(KEYS.bgMode, "image");
    const bgUrl = lsGet(KEYS.bgUrl, "");
    const bgColor = lsGet(KEYS.bgColor, "#0b0b0d");
    const textColor = lsGet(KEYS.textColor, "");

    document.body.dataset.theme = theme;

    if (bgMode === "color") {
      document.body.style.backgroundImage = "none";
      document.body.style.backgroundColor = bgColor || "#0b0b0d";
    } else {
      document.body.style.backgroundColor = "#0b0b0d";
      document.body.style.backgroundImage = bgUrl ? `url("${bgUrl}")` : "none";
      document.body.style.backgroundSize = "cover";
      document.body.style.backgroundPosition = "center";
      document.body.style.backgroundAttachment = "fixed";
    }

    if (textColor) document.body.style.color = textColor;
    else document.body.style.removeProperty("color");

    const grid = document.getElementById("mainGrid");
    if (grid) {
      grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
      grid.style.gap = `${gap}px`;
    }

    const showSidebar = lsGet(KEYS.showSidebar, "0") === "1";
    const sidebar = document.getElementById("sidebar");
    const layout = document.getElementById("layoutRoot");

    if (layout) layout.classList.toggle("has-sidebar", showSidebar);
    if (sidebar) sidebar.style.display = showSidebar ? "block" : "none";

    const isOpen = lsGet(KEYS.sidebarOpen, "0") === "1";
    document.body.classList.toggle("sidebar-open", isOpen);
    setToggleExpanded(isOpen);
  }

  // ---------- Sidebar toggle ----------
  function bindSidebarToggle() {
    const btn = document.getElementById("sidebarToggle");
    if (!btn) return;

    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";

    btn.addEventListener("click", () => {
      const showSidebar = lsGet(KEYS.showSidebar, "0") === "1";
      if (!showSidebar) return;

      const nowOpen = !document.body.classList.contains("sidebar-open");
      document.body.classList.toggle("sidebar-open", nowOpen);
      lsSet(KEYS.sidebarOpen, nowOpen ? "1" : "0");
      setToggleExpanded(nowOpen);
    });
  }

  // ---------- Main grid ----------
  function sortLinks(arr) {
    const mode = lsGet(KEYS.sortMode, "date_desc");

    const byName = (a, b) =>
      String(a.title || a.name || "").toLowerCase()
        .localeCompare(String(b.title || b.name || "").toLowerCase());

    const byCreated = (a, b) => {
      const da = Date.parse(a.createdAt || a.created || 0) || 0;
      const db = Date.parse(b.createdAt || b.created || 0) || 0;
      return da - db;
    };

    const out = arr.slice();
    if (mode === "name_asc") out.sort(byName);
    else if (mode === "name_desc") out.sort((a, b) => -byName(a, b));
    else if (mode === "date_asc") out.sort(byCreated);
    else out.sort((a, b) => -byCreated(a, b));
    return out;
  }

  function pickTitle(item) {
    return item.title || item.name || item.url || "(no title)";
  }

  function pickUrl(item) {
    return item.url || "";
  }

  function pickIcon(item) {
    // Keep your Linkwarden favicon endpoint logic, but make it safe.
    const baseUrl = lsGet("lw_base_url", "").trim();
    const raw = item && item.url ? String(item.url) : "";

    if (!baseUrl || !raw) return item?.favicon || "";

    try {
      const u = new URL(raw);
      return baseUrl.replace(/\/+$/, "") + "/api/v1/getFavicon?url=" + encodeURIComponent(u.origin);
    } catch (_) {
      return item?.favicon || "";
    }
  }

  function renderMainGrid(links) {
    const grid = document.getElementById("mainGrid");
    const noCard = document.getElementById("noCollectionCard");
    if (!grid || !noCard) return;

    grid.innerHTML = "";

    const openNew = shouldOpenNewTab();

    for (const it of links) {
      const title = pickTitle(it);
      const url = pickUrl(it);
      const icon = pickIcon(it);

      const a = document.createElement("a");
      a.className = "tile";
      a.href = url || "#";
      a.title = title;

      if (openNew) {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      }

      a.innerHTML = `
        <div class="tile-icon-wrap">
          <img class="tile-icon" src="${escapeHtml(icon)}" alt="">
        </div>
        <div class="tile-title">${escapeHtml(title)}</div>
      `;

      grid.appendChild(a);
    }

    noCard.style.display = "none";
    grid.style.display = "grid";
  }

  async function loadMainGrid() {
    const grid = document.getElementById("mainGrid");
    const noCard = document.getElementById("noCollectionCard");
    if (!grid || !noCard) return;

    const collectionId = lsGet(KEYS.collectionId, "").trim();

    if (!collectionId) {
      grid.style.display = "none";
      noCard.style.display = "block";
      return;
    }

    const { status, data } = await fetchJson(`/api/links?collection_id=${encodeURIComponent(collectionId)}`);
    if (status !== 200) {
      window.location.href = "/login";
      return;
    }

    const arr = Array.isArray(data?.response) ? data.response : [];
    renderMainGrid(sortLinks(arr));
  }

  // ---------- Sidebar browser ----------
  let collections = [];
  let stack = [];
  let currentId = null;

  function childrenOf(parentId) {
    return collections.filter((c) => (c.parentId ?? null) === (parentId ?? null));
  }

  async function fetchSidebarLinks(collectionId) {
    const { status, data } = await fetchJson(`/api/links?collection_id=${encodeURIComponent(collectionId)}`);
    if (status !== 200) return [];
    return Array.isArray(data?.response) ? data.response : [];
  }

  function clearSidebar() {
    const list = document.getElementById("sidebarList");
    if (list) list.innerHTML = "";
  }

  function addSidebarEl(el) {
    const list = document.getElementById("sidebarList");
    if (list) list.appendChild(el);
  }

  function makeSidebarRow(label, right, onClick) {
    const row = document.createElement("div");
    row.className = "sb-item";
    row.dataset.name = (label || "").toLowerCase();
    row.innerHTML = `
      <span class="sb-name">${escapeHtml(label)}</span>
      <span class="sb-count">${escapeHtml(right || "")}</span>
    `;
    row.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      onClick();
    });
    return row;
  }

  async function renderSidebar() {
    clearSidebar();

    if (currentId !== null) {
      addSidebarEl(makeSidebarRow("..", "", () => {
        currentId = stack.pop() ?? null;
        renderSidebar();
      }));
    }

    const subs = childrenOf(currentId);
    for (const c of subs) {
      const count = typeof c._count?.links === "number" ? String(c._count.links) : "";
      addSidebarEl(makeSidebarRow(c.name || "Untitled", count, () => {
        stack.push(currentId);
        currentId = c.id;
        renderSidebar();
      }));
    }

    if (currentId !== null) {
      const links = await fetchSidebarLinks(currentId);
      if (links.length) {
        const sep = document.createElement("div");
        sep.className = "sb-sep";
        sep.textContent = "Links";
        addSidebarEl(sep);
      }

      for (const l of links) {
        const title = pickTitle(l);
        addSidebarEl(makeSidebarRow(title, "", () => {
          const url = pickUrl(l);
          if (!url) return;

          if (shouldOpenNewTab()) window.open(url, "_blank", "noopener");
          else window.location.href = url;
        }));
      }
    }

    applySidebarSearchFilter();
  }

  function applySidebarSearchFilter() {
    const input = document.getElementById("sidebarSearch");
    const list = document.getElementById("sidebarList");
    if (!input || !list) return;

    const q = input.value.trim().toLowerCase();
    for (const child of list.children) {
      if (!(child instanceof HTMLElement)) continue;
      if (child.classList.contains("sb-sep")) continue;

      if (!q) child.style.display = "";
      else child.style.display = (child.dataset.name || "").includes(q) ? "" : "none";
    }
  }

  function bindSidebarUI() {
    const close = document.getElementById("sidebarClose");
    if (close) {
      close.addEventListener("click", () => {
        document.body.classList.remove("sidebar-open");
        lsSet(KEYS.sidebarOpen, "0");
        setToggleExpanded(false);
      });
    }

    const search = document.getElementById("sidebarSearch");
    if (search) search.addEventListener("input", applySidebarSearchFilter);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.body.classList.remove("sidebar-open");
        lsSet(KEYS.sidebarOpen, "0");
        setToggleExpanded(false);
      }
    });
  }

  async function loadSidebar() {
    const showSidebar = lsGet(KEYS.showSidebar, "0") === "1";
    if (!showSidebar) return;

    const { status, data } = await fetchJson("/api/collections");
    if (status !== 200) {
      window.location.href = "/login";
      return;
    }

    collections = Array.isArray(data?.response) ? data.response : [];
    stack = [];
    currentId = null;

    bindSidebarUI();
    renderSidebar();
  }

  // ---------- Boot ----------
  document.addEventListener("DOMContentLoaded", async function () {
    bindSidebarToggle();
    applyPrefs();
    await loadMainGrid();
    await loadSidebar();
  });
})();