import os
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-change-me")

FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes", "on")

CACHE_TTL_SECONDS = 30
_links_cache = {}

ALLOWED_SORT_MODES = {
    "date_desc",
    "date_asc",
    "name_asc",
    "name_desc",
}


# -----------------------
# Helpers
# -----------------------

def normalized_base_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def require_login() -> bool:
    return bool(session.get("lw_token") and session.get("lw_base_url"))


def lw_headers() -> dict:
    token = session.get("lw_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def lw_request(method: str, path: str, **kwargs):
    base = session.get("lw_base_url")
    if not base:
        raise RuntimeError("Missing Linkwarden base URL")
    url = f"{base}{path}"
    headers = kwargs.pop("headers", {})
    headers = {**headers, **lw_headers()}
    return requests.request(method, url, headers=headers, timeout=15, **kwargs)


def extract_list_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("response", "data", "items", "collections", "links"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


def favicon_for(url: str) -> str:
    try:
        net_data = urlparse(url)
        host = net_data.netloc
        full_host = net_data.scheme + "://" + host
    except Exception:
        return ""
    base = session.get("lw_base_url")
    return f"{base}/api/v1/getFavicon?url={full_host}"


def guess_image_mimetype(fmt: int) -> str:
    return "image/jpeg" if fmt == 1 else "image/png"


# -----------------------
# Login / Logout
# -----------------------

@app.get("/login")
def login_get():
    return render_template(
        "login.html",
        theme=session.get("theme", "auto"),
        bg_mode=session.get("bg_mode", "image"),
        bg_url=session.get("bg_url", ""),
        bg_color=session.get("bg_color", "#0b0b0d"),
        text_color=session.get("text_color", ""),
    )


@app.post("/login")
def login_post():
    base_url = normalized_base_url(request.form.get("base_url"))
    token = (request.form.get("api_token") or "").strip()

    if not base_url or not token:
        flash("Provide Linkwarden URL and API token", "error")
        return redirect(url_for("login_get"))

    session["lw_base_url"] = base_url
    session["lw_token"] = token

    try:
        r = lw_request("GET", "/api/v1/collections")
        if r.status_code != 200:
            raise RuntimeError("Invalid token")
    except Exception:
        session.clear()
        flash("Invalid Linkwarden token", "error")
        return redirect(url_for("login_get"))

    session.setdefault("collection_id", "")
    session.setdefault("grid_columns", 6)
    session.setdefault("grid_spacing", 14)
    session.setdefault("sort_mode", "date_desc")
    session.setdefault("open_new_tab", True)
    session.setdefault("show_sidebar", False)

    session.setdefault("theme", "auto")
    session.setdefault("bg_mode", "image")
    session.setdefault("bg_url", "")
    session.setdefault("bg_color", "#0b0b0d")
    session.setdefault("text_color", "")

    return redirect(url_for("settings_get"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_get"))


# -----------------------
# Settings
# -----------------------

@app.get("/settings")
def settings_get():
    if not require_login():
        return redirect(url_for("login_get"))

    collections = []
    try:
        r = lw_request("GET", "/api/v1/collections")
        collections = extract_list_payload(r.json())
    except Exception:
        pass

    return render_template(
        "settings.html",
        collections=collections,
        selected_collection_id=session.get("collection_id", ""),
        grid_columns=session.get("grid_columns", 6),
        grid_spacing=session.get("grid_spacing", 14),
        open_new_tab=session.get("open_new_tab", True),
        show_sidebar=session.get("show_sidebar", False),
        sort_mode=session.get("sort_mode", "date_desc"),
        theme=session.get("theme", "auto"),
        bg_mode=session.get("bg_mode", "image"),
        bg_url=session.get("bg_url", ""),
        bg_color=session.get("bg_color", "#0b0b0d"),
        text_color=session.get("text_color", ""),
        lw_base_url=session.get("lw_base_url", ""),
        lw_username=session.get("lw_username", ""),
        lw_token=session.get("lw_token", ""),
    )


@app.post("/settings")
def settings_post():
    if not require_login():
        return redirect(url_for("login_get"))

    session["collection_id"] = request.form.get("collection_id", "")

    try:
        session["grid_columns"] = max(4, min(12, int(request.form.get("grid_columns", 6))))
    except Exception:
        pass

    try:
        gap = int(request.form.get("grid_spacing", 14))
        gap = max(0, min(32, gap))
        session["grid_spacing"] = int(round(gap / 4) * 4)
    except Exception:
        pass

    session["open_new_tab"] = bool(request.form.get("open_new_tab"))
    session["show_sidebar"] = bool(request.form.get("show_sidebar"))

    raw_sort = request.form.get("sort_mode", "date_desc")
    if raw_sort in ALLOWED_SORT_MODES:
        session["sort_mode"] = raw_sort

    session["theme"] = request.form.get("theme", "auto")
    session["bg_mode"] = request.form.get("bg_mode", "image")
    session["bg_url"] = request.form.get("bg_url", "")
    session["bg_color"] = request.form.get("bg_color", "#0b0b0d")
    session["text_color"] = request.form.get("text_color", "")

    session.modified = True
    return redirect(url_for("settings_get"))


# -----------------------
# Sidebar API
# -----------------------

@app.get("/api/collections")
def api_collections():
    if not require_login():
        return jsonify({"error": "Not authenticated"}), 401

    try:
        r = lw_request("GET", "/api/v1/collections")
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# -----------------------
# Links + Thumbnails
# -----------------------

def fetch_links_for_collection(collection_id: str):
    if not collection_id:
        return []

    cache_key = (session.get("lw_base_url"), collection_id)
    now = time.time()
    cached = _links_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    r = lw_request("GET", "/api/v1/links", params={"collectionId": int(collection_id)})
    links = extract_list_payload(r.json())
    links = [l for l in links if isinstance(l, dict)]

    _links_cache[cache_key] = (now, links)
    return links


@app.get("/thumb/<int:link_id>")
def thumb(link_id: int):
    if not require_login():
        return Response(status=401)

    r = lw_request(
        "GET",
        f"/api/v1/archives/{link_id}",
        params={"format": 1, "preview": "true"},
        stream=True,
    )
    if r.status_code != 200:
        return Response(status=404)

    return Response(r.content, mimetype="image/jpeg")


# -----------------------
# Main view
# -----------------------

@app.get("/")
def index():
    if not require_login():
        return redirect(url_for("login_get"))

    collection_id = session.get("collection_id", "")
    links = fetch_links_for_collection(collection_id)

    tiles = []
    for l in links:
        tiles.append(
            {
                "id": l.get("id"),
                "title": l.get("name") or l.get("title") or l.get("url"),
                "url": l.get("url"),
                "favicon": favicon_for(l.get("url", "")),
                "pinned": bool(l.get("pinned", False)),
                "date": l.get("createdAt") or l.get("updatedAt") or "",
            }
        )

    sort_mode = session.get("sort_mode", "date_desc")
    pinned = [t for t in tiles if t["pinned"]]
    rest = [t for t in tiles if not t["pinned"]]

    if sort_mode.startswith("name"):
        key = lambda t: t["title"].lower()
        pinned.sort(key=key, reverse=sort_mode.endswith("desc"))
        rest.sort(key=key, reverse=sort_mode.endswith("desc"))
    else:
        key = lambda t: t["date"]
        pinned.sort(key=key, reverse=sort_mode.endswith("desc"))
        rest.sort(key=key, reverse=sort_mode.endswith("desc"))

    tiles = pinned + rest

    return render_template(
        "index.html",
        tiles=tiles,
        collection_id=collection_id,
        grid_columns=session.get("grid_columns", 6),
        grid_spacing=session.get("grid_spacing", 14),
        open_new_tab=session.get("open_new_tab", True),
        show_sidebar=session.get("show_sidebar", False),
        theme=session.get("theme", "auto"),
        bg_mode=session.get("bg_mode", "image"),
        bg_url=session.get("bg_url", ""),
        bg_color=session.get("bg_color", "#0b0b0d"),
        text_color=session.get("text_color", ""),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=FLASK_DEBUG)