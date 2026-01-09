function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getActiveCollectionId() {
  return new URLSearchParams(window.location.search).get("collection_id");
}

let collections = [];
let stack = [];
let currentParent = null;

function hasChildren(id) {
  return collections.some(c => c.parentId === id);
}

function childrenOf(parentId) {
  return collections
    .filter(c => (c.parentId ?? null) === (parentId ?? null))
    .sort((a, b) =>
      (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" })
    );
}

function render(list) {
  const listEl = document.getElementById("sidebarList");
  const active = getActiveCollectionId();
  listEl.innerHTML = "";

  // back navigation
  if (stack.length > 0) {
    const back = document.createElement("div");
    back.className = "sb-item";
    back.innerHTML = `<span class="sb-name">..</span>`;
    back.onclick = () => {
      currentParent = stack.pop() ?? null;
      render(childrenOf(currentParent));
    };
    listEl.appendChild(back);
  }

  for (const c of list) {
    const row = document.createElement("div");
    row.className = "sb-item";
    row.dataset.id = c.id;

    row.innerHTML = `
      <span class="sb-name">${escapeHtml(c.name || "Untitled")}</span>
      <span class="sb-count">${hasChildren(c.id) ? "›" : (c._count?.links ?? "")}</span>
    `;

    if (String(c.id) === String(active)) {
      row.classList.add("active");
    }

    row.onclick = () => {
      if (hasChildren(c.id)) {
        stack.push(currentParent);
        currentParent = c.id;
        render(childrenOf(currentParent));
      } else {
        window.location.href = `/?collection_id=${encodeURIComponent(c.id)}`;
      }
    };

    listEl.appendChild(row);
  }
}

async function loadCollections() {
  const r = await fetch("/api/collections");
  const data = await r.json();
  collections = data.response ?? data;
  render(childrenOf(null));
}

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("sidebarToggle");
  const close = document.getElementById("sidebarClose");
  const search = document.getElementById("sidebarSearch");

  if (!toggle) return;

  function openSidebar(open) {
    document.body.classList.toggle("sidebar-open", open);
    localStorage.setItem("lw_sidebar_open", open ? "1" : "0");
    if (open) loadCollections();
  }

  toggle.onclick = () => openSidebar(true);
  close.onclick = () => openSidebar(false);

  if (localStorage.getItem("lw_sidebar_open") === "1") {
    openSidebar(true);
  }

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") openSidebar(false);
  });

  search.oninput = () => {
    const q = search.value.trim().toLowerCase();
    if (!q) {
      render(childrenOf(currentParent));
      return;
    }
    const hits = collections.filter(c =>
      (c.name || "").toLowerCase().includes(q)
    );
    render(hits);
  };
});