import os
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
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
        host = urlparse(url).netloc
    except Exception:
        return ""
    base = session.get("lw_base_url")
    return f"{base}/api/v1/getFavicon?url=https://{host}"

@app.get("/login")
def login_get():
    return render_template("login.html")


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
    session.setdefault("show_sidebar", True)

    return redirect(url_for("index"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_get"))


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
    )


@app.post("/settings")
def settings_post():
    if not require_login():
        return redirect(url_for("login_get"))

    session["collection_id"] = request.form.get("collection_id", "")
    session["open_new_tab"] = bool(request.form.get("open_new_tab"))
    session["show_sidebar"] = bool(request.form.get("show_sidebar"))
    session.modified = True

    return redirect(url_for("settings_get"))


@app.get("/api/collections")
def api_collections():
    if not require_login():
        return jsonify({"error": "Not authenticated"}), 401

    r = lw_request("GET", "/api/v1/collections")
    return jsonify(r.json())


@app.get("/api/links")
def api_links():
    if not require_login():
        return jsonify({"error": "Not authenticated"}), 401

    collection_id = (request.args.get("collection_id") or "").strip()
    if not collection_id:
        return jsonify({"response": []})

    try:
        cid = int(collection_id)
    except Exception:
        return jsonify({"response": []})

    cache_key = (session.get("lw_base_url"), cid)
    now = time.time()
    cached = _links_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return jsonify({"response": cached[1]})

    r = lw_request("GET", "/api/v1/links", params={"collectionId": cid})
    links = extract_list_payload(r.json())
    links = [l for l in links if isinstance(l, dict)]

    _links_cache[cache_key] = (now, links)
    return jsonify({"response": links})


@app.get("/")
def index():
    if not require_login():
        return redirect(url_for("login_get"))
    collection_id = session.get("collection_id", "")
    links = []

    if collection_id:
        try:
            cid = int(collection_id)
            r = lw_request("GET", "/api/v1/links", params={"collectionId": cid})
            links = extract_list_payload(r.json())
        except Exception:
            pass

    tiles = []
    for l in links:
        tiles.append(
            {
                "id": l.get("id"),
                "title": l.get("name") or l.get("title") or l.get("url"),
                "url": l.get("url"),
                "favicon": favicon_for(l.get("url", "")),
            }
        )

    return render_template(
        "index.html",
        tiles=tiles,
        grid_columns=session.get("grid_columns", 6),
        grid_spacing=session.get("grid_spacing", 14),
        open_new_tab=session.get("open_new_tab", True),
        show_sidebar=session.get("show_sidebar", False),
    )


@app.post("/auth/restore")
def auth_restore():
    data = request.get_json(silent=True) or {}
    base_url = (data.get("base_url") or "").strip().rstrip("/")
    token = (data.get("token") or "").strip()

    if not base_url or not token:
        return jsonify({"ok": False, "error": "Missing base_url or token"}), 400

    try:
        r = requests.get(
            f"{base_url}/api/v1/collections",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code != 200:
            return jsonify({"ok": False, "error": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    session["lw_base_url"] = base_url
    session["lw_token"] = token
    session.modified = True
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=FLASK_DEBUG)
