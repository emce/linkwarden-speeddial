(function () {
  const LS = {
    theme: "lw_theme",
    gridColumns: "lw_grid_columns",
    gridSpacing: "lw_grid_spacing",
    openNewTab: "lw_open_new_tab",
    showSidebar: "lw_show_sidebar",
    sortMode: "lw_sort_mode",

    bgMode: "lw_bg_mode",
    bgUrl: "lw_bg_url",
    bgColor: "lw_bg_color",
    textColor: "lw_text_color",

    baseUrl: "lw_base_url",
    token: "lw_token",
    username: "lw_username",

    // ✅ restored for main grid
    collectionId: "lw_collection_id",
  };

  const $ = (id) => document.getElementById(id);
  const get = (k, d = "") => {
    try { return localStorage.getItem(k) ?? d; } catch (_) { return d; }
  };
  const set = (k, v) => {
    try { localStorage.setItem(k, String(v)); } catch (_) {}
  };
  const del = (k) => {
    try { localStorage.removeItem(k); } catch (_) {}
  };

  function apply() {
    if ($("theme")) $("theme").value = get(LS.theme, "auto");

    if ($("grid_columns")) {
      $("grid_columns").value = get(LS.gridColumns, "6");
      if ($("colsVal")) $("colsVal").textContent = $("grid_columns").value;
    }

    if ($("grid_spacing")) {
      $("grid_spacing").value = get(LS.gridSpacing, "14");
      if ($("gapVal")) $("gapVal").textContent = $("grid_spacing").value;
    }

    if ($("open_new_tab")) $("open_new_tab").checked = get(LS.openNewTab, "1") === "1";
    if ($("show_sidebar")) $("show_sidebar").checked = get(LS.showSidebar, "1") === "1";
    if ($("sort_mode")) $("sort_mode").value = get(LS.sortMode, "date_desc");

    const bgMode = get(LS.bgMode, "image");
    if ($("bg_mode_image")) $("bg_mode_image").checked = bgMode === "image";
    if ($("bg_mode_color")) $("bg_mode_color").checked = bgMode === "color";

    if ($("bg_url")) $("bg_url").value = get(LS.bgUrl, "");
    if ($("bg_color")) $("bg_color").value = get(LS.bgColor, "#0b0b0d");
    if ($("text_color")) $("text_color").value = get(LS.textColor, "");

    if ($("lw_base_url")) $("lw_base_url").value = get(LS.baseUrl, "");
    if ($("lw_token")) $("lw_token").value = get(LS.token, "");
    if ($("lw_username")) $("lw_username").value = get(LS.username, "");

    // ✅ restore selected collection for main grid
    if ($("collection_id")) {
      $("collection_id").value = get(LS.collectionId, "");
    }

    if (typeof window.updateBgMode === "function") {
      try { window.updateBgMode(); } catch (_) {}
    }
  }

  function save() {
    if ($("theme")) set(LS.theme, $("theme").value);
    if ($("grid_columns")) set(LS.gridColumns, $("grid_columns").value);
    if ($("grid_spacing")) set(LS.gridSpacing, $("grid_spacing").value);

    if ($("open_new_tab")) set(LS.openNewTab, $("open_new_tab").checked ? "1" : "0");
    if ($("show_sidebar")) set(LS.showSidebar, $("show_sidebar").checked ? "1" : "0");
    if ($("sort_mode")) set(LS.sortMode, $("sort_mode").value);

    if ($("bg_mode_image") && $("bg_mode_color")) {
      set(LS.bgMode, $("bg_mode_image").checked ? "image" : "color");
    }
    if ($("bg_url")) set(LS.bgUrl, $("bg_url").value);
    if ($("bg_color")) set(LS.bgColor, $("bg_color").value);
    if ($("text_color")) set(LS.textColor, $("text_color").value);

    if ($("lw_base_url")) set(LS.baseUrl, $("lw_base_url").value);
    if ($("lw_token")) set(LS.token, $("lw_token").value);
    if ($("lw_username")) set(LS.username, $("lw_username").value);

    // ✅ persist main grid collection
    if ($("collection_id")) set(LS.collectionId, $("collection_id").value);
  }

  async function restoreSession() {
    // make sure latest input values are saved first
    save();

    const base_url = get(LS.baseUrl, "").trim();
    const token = get(LS.token, "").trim();

    if (!base_url || !token) {
      alert("Missing Linkwarden URL or token.");
      return;
    }

    try {
      const r = await fetch("/auth/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ base_url, token }),
      });

      if (r.ok) alert("Session restored.");
      else alert("Restore failed.");
    } catch (e) {
      alert("Restore error.");
    }
  }

  function bind() {
    const ids = [
      "theme",
      "grid_columns",
      "grid_spacing",
      "open_new_tab",
      "show_sidebar",
      "sort_mode",

      "bg_mode_image",
      "bg_mode_color",
      "bg_url",
      "bg_color",
      "text_color",

      "lw_base_url",
      "lw_username",
      "lw_token",

      // ✅ collection select
      "collection_id",
    ];

    ids.forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("change", save);
      el.addEventListener("input", save);
    });

    if ($("grid_columns")) {
      $("grid_columns").addEventListener("input", () => {
        if ($("colsVal")) $("colsVal").textContent = $("grid_columns").value;
      });
    }

    if ($("grid_spacing")) {
      $("grid_spacing").addEventListener("input", () => {
        if ($("gapVal")) $("gapVal").textContent = $("grid_spacing").value;
      });
    }

    const restoreBtn = $("restoreSessionBtn");
    if (restoreBtn) restoreBtn.addEventListener("click", restoreSession);

    const clearBtn = $("clearLocalAuthBtn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        del(LS.baseUrl);
        del(LS.token);
        del(LS.username);
        alert("Local auth cleared.");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    apply();
    bind();
  });
})();