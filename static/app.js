(function () {
    const cfg = window.APP_CONFIG || {};

    const mainGrid = document.getElementById("mainGrid");
    const noCollectionCard = document.getElementById("noCollectionCard");

    const errorCard = document.getElementById("errorCard");
    const errorText = document.getElementById("errorText");

    // Sidebar elements (may not exist if show_sidebar is false)
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebarBackdrop");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarClose = document.getElementById("sidebarClose");
    const sidebarSearch = document.getElementById("sidebarSearch");
    const sidebarList = document.getElementById("sidebarList");

    function setErr(msg) {
        errorText.textContent = msg || "Unknown error";
        errorCard.style.display = "block";
    }

    function clearErr() {
        errorCard.style.display = "none";
        errorText.textContent = "";
    }

    function setSidebarOpen(open) {
        document.body.classList.toggle("sidebar-open", open);
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    async function fetchJson(url, options) {
        if (typeof window.fetchJson === "function") return window.fetchJson(url, options);

        const r = await fetch(url, {credentials: "same-origin", ...(options || {})});
        let data = null;
        try {
            data = await r.json();
        } catch (_) {
        }
        return {status: r.status, data};
    }

    // -----------------------------
    // Cache: one-shot load of full tree
    // -----------------------------
    // We will fetch all collections once and then lazily fetch links per collection from the backend
    // OR if your backend already has an endpoint returning a full tree, we can swap it here.
    //
    // For now, we cache:
    // - collections list: /api/collections
    // - links per collection: /api/links?collection_id=...
    // This ensures we never refetch collections and avoids duplication between grid & sidebar.
    // -----------------------------

    const cache = {
        collections: null, // array
        linksByCollection: new Map(), // id -> array
    };

    async function getCollections() {
        if (cache.collections) return cache.collections;
        const {status, data} = await fetchJson("/api/collections");
        if (status !== 200) throw new Error("Failed to load collections");
        cache.collections = Array.isArray(data?.response) ? data.response : [];
        return cache.collections;
    }

    async function getLinks(collectionId) {
        const key = String(collectionId);
        if (cache.linksByCollection.has(key)) return cache.linksByCollection.get(key) || [];
        const {status, data} = await fetchJson(`/api/links?collection_id=${encodeURIComponent(key)}`);
        if (status !== 200) throw new Error("Failed to load links");
        const links = Array.isArray(data?.response) ? data.response : [];
        cache.linksByCollection.set(key, links);
        return links;
    }

    // -----------------------------
    // Sorting
    // -----------------------------
    function sortLinks(arr) {
        const mode = (cfg.sort_mode || "date_desc").toLowerCase();

        const byName = (a, b) =>
            String(a.title || a.name || "").toLowerCase()
                .localeCompare(String(b.title || b.name || "").toLowerCase());

        const ts = (x) => Date.parse(x?.createdAt || x?.created_at || x?.created || 0) || 0;
        const byCreated = (a, b) => ts(a) - ts(b);

        const out = (arr || []).slice();
        if (mode === "name_asc") out.sort(byName);
        else if (mode === "name_desc") out.sort((a, b) => -byName(a, b));
        else if (mode === "date_asc") out.sort(byCreated);
        else out.sort((a, b) => -byCreated(a, b));
        return out;
    }

    // -----------------------------
    // UI helpers
    // -----------------------------
    function escapeHtml(s) {
        return String(s)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function pickTitle(item) {
        return item?.title || item?.name || item?.url || "(no title)";
    }

    function pickUrl(item) {
        return item?.url || "";
    }

    // ✅ CHANGE: use Linkwarden getFavicon endpoint, extracting origin (scheme + host)
    function pickIcon(item) {
        const raw = pickUrl(item);
        if (!raw) return "";

        try {
            const u = new URL(raw);
            const origin = u.origin; // scheme + host + optional port
            const base = String(cfg.linkwarden_url || "").replace(/\/+$/, "");
            if (!base) return "";
            return `${base}/api/v1/getFavicon?url=${encodeURIComponent(origin)}`;
        } catch (_) {
            return "";
        }
    }

    // -----------------------------
    // Main grid
    // -----------------------------
    function renderGrid(links) {
        mainGrid.innerHTML = "";
        const openNew = !!cfg.open_new_tab;

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
            mainGrid.appendChild(a);
        }

        noCollectionCard.style.display = "none";
        mainGrid.style.display = "grid";
    }

    async function loadMainGrid() {
        clearErr();

        const col = (cfg.collection_id || "").trim();
        if (!col) {
            mainGrid.style.display = "none";
            noCollectionCard.style.display = "block";
            return;
        }

        try {
            const links = await getLinks(col);
            renderGrid(sortLinks(links));
        } catch (e) {
            setErr("Failed to load links. Check LINKWARDEN_URL / TOKEN and backend connectivity.");
            mainGrid.style.display = "none";
            noCollectionCard.style.display = "none";
        }
    }

    // -----------------------------
    // Sidebar (optional, only when enabled in env)
    // -----------------------------
    let collections = [];
    let stack = [];
    let currentId = null;

    function clearSidebar() {
        sidebarList.innerHTML = "";
    }

    function addSidebarEl(el) {
        sidebarList.appendChild(el);
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

    function childrenOf(parentId) {
        return collections.filter(c => (c.parentId ?? null) === (parentId ?? null));
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
            const count = typeof c?._count?.links === "number" ? String(c._count.links) : "";
            addSidebarEl(makeSidebarRow(c?.name || "Untitled", count, () => {
                stack.push(currentId);
                currentId = c.id;
                renderSidebar();
            }));
        }

        if (currentId !== null) {
            let links = [];
            try {
                links = await getLinks(currentId);
            } catch (_) {
                links = [];
            }

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
                    if (cfg.open_new_tab) window.open(url, "_blank", "noopener");
                    else window.location.href = url;
                }));
            }
        }

        applySidebarSearchFilter();
    }

    function applySidebarSearchFilter() {
        const q = sidebarSearch.value.trim().toLowerCase();
        for (const child of sidebarList.children) {
            if (!(child instanceof HTMLElement)) continue;
            if (child.classList.contains("sb-sep")) continue;
            if (!q) child.style.display = "";
            else child.style.display = (child.dataset.name || "").includes(q) ? "" : "none";
        }
    }

    async function loadSidebar() {
        if (!cfg.show_sidebar) return;

        try {
            collections = await getCollections();
        } catch (_) {
            // Sidebar is optional; don't hard-fail the whole page.
            return;
        }

        stack = [];
        currentId = null;
        await renderSidebar();
    }

    function bindSidebarUI() {
        if (!cfg.show_sidebar) return;

        sidebarToggle.addEventListener("click", () => {
            setSidebarOpen(!document.body.classList.contains("sidebar-open"));
        });

        sidebarClose.addEventListener("click", () => setSidebarOpen(false));
        backdrop.addEventListener("click", () => setSidebarOpen(false));

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") setSidebarOpen(false);
        });

        sidebarSearch.addEventListener("input", applySidebarSearchFilter);

        // default closed on each load
        setSidebarOpen(false);
    }

    // -----------------------------
    // Boot
    // -----------------------------
    (async function boot() {
        // If sidebar disabled, don't include any runtime bindings (HTML not rendered at all)
        await loadMainGrid();

        if (cfg.show_sidebar && sidebar && sidebarToggle && sidebarList && sidebarSearch) {
            bindSidebarUI();
            await loadSidebar();
        }
    })();
})();

(function () {
  const btn = document.getElementById("groupBtn");
  const modal = document.getElementById("groupModal");
  const backdrop = document.getElementById("groupBackdrop");
  const closeBtn = document.getElementById("groupClose");

  if (!btn || !modal || !backdrop || !closeBtn) return;

  function openModal() {
    modal.hidden = false;
    backdrop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
  }

  function closeModal() {
    modal.hidden = true;
    backdrop.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  }

  btn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);
  backdrop.addEventListener("click", closeModal);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
})();