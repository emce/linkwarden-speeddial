import os
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-change-me")

# Runtime configuration (from .env / environment)
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes", "on")

# Simple in-memory cache to avoid hammering Linkwarden on every refresh
CACHE_TTL_SECONDS = 30
_links_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}

ALLOWED_SORT_MODES = {
    "date_desc",  # Data (od najnowszych)
    "date_asc",   # Data (od najstarszych)
    "name_asc",   # Nazwa (A–Z)
    "name_desc",  # Nazwa (Z–A)
}


def normalized_base_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def lw_headers() -> dict:
    token = session.get("lw_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def lw_request(method: str, path: str, **kwargs):
    base = session.get("lw_base_url")
    if not base:
        raise RuntimeError("Not configured: missing Linkwarden base URL")
    url = f"{base}{path}"
    headers = kwargs.pop("headers", {})
    headers = {**headers, **lw_headers()}
    return requests.request(method, url, headers=headers, timeout=15, **kwargs)


def require_login() -> bool:
    return bool(session.get("lw_token") and session.get("lw_base_url"))


def favicon_for(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
    except Exception:
        netloc = ""
    if not netloc:
        return ""
    return f"https://www.google.com/s2/favicons?domain={netloc}&sz=64"


def create_linkwarden_access_token(
    base_url: str,
    session_jwt: str,
    *,
    name: str = "flask-speeddial",
    expires_seconds: int = 0,
) -> str | None:
    """Create a long-lived Linkwarden token using an authenticated session JWT."""
    try:
        r = requests.post(
            f"{base_url}/api/v1/tokens",
            json={"name": name, "expires": int(expires_seconds)},
            headers={"Authorization": f"Bearer {session_jwt}"},
            timeout=15,
        )
    except requests.RequestException:
        return None

    if r.status_code not in (200, 201):
        return None

    data = r.json() or {}
    return data.get("token") or data.get("accessToken") or data.get("jwt")


def guess_image_mimetype(fmt: int) -> str:
    if fmt == 0:
        return "image/png"
    if fmt == 1:
        return "image/jpeg"
    return "application/octet-stream"


def extract_list_payload(payload):
    """Linkwarden responses can be either a list or an object containing a list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("response", "data", "result", "items", "collections", "links"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


@app.get("/login")
def login_get():
    return render_template(
        "login.html",
        dev_instance=os.getenv("DEV_INSTANCE_URL", ""),
        dev_user=os.getenv("DEV_USER", ""),
        dev_token=os.getenv("DEV_TOKEN", ""),
    )


@app.post("/login")
def login_post():
    base_url = normalized_base_url(request.form.get("base_url"))
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    api_token = (request.form.get("api_token") or "").strip()

    if not base_url:
        flash("Please provide Linkwarden URL.", "error")
        return redirect(url_for("login_get"))

    # Token login
    if api_token:
        session["lw_base_url"] = base_url
        session["lw_token"] = api_token
        try:
            vr = lw_request("GET", "/api/v1/collections")
        except requests.RequestException as e:
            session.clear()
            flash(f"Could not reach Linkwarden: {e}", "error")
            return redirect(url_for("login_get"))

        if vr.status_code == 200:
            session.setdefault("wallpaper_url", "")
            session.setdefault("collection_id", "")
            session.setdefault("grid_columns", 6)
            session.setdefault("sort_mode", "date_desc")
            return redirect(url_for("settings_get"))

        session.clear()
        flash(f"API token looks invalid (HTTP {vr.status_code}).", "error")
        return redirect(url_for("login_get"))

    # Username/password login
    if not username or not password:
        flash("Please provide username and password, or paste an API token.", "error")
        return redirect(url_for("login_get"))

    try:
        r = requests.post(
            f"{base_url}/api/v1/session",
            json={"username": username, "password": password, "sessionName": "flask-speeddial"},
            timeout=15,
        )
    except requests.RequestException as e:
        flash(f"Could not reach Linkwarden: {e}", "error")
        return redirect(url_for("login_get"))

    raw_snippet = (r.text or "")[:300]
    try:
        data = r.json()
    except Exception:
        data = None

    if r.status_code != 200:
        flash(f"Login failed (HTTP {r.status_code}). Body starts: {raw_snippet}", "error")
        return redirect(url_for("login_get"))

    session_jwt = None
    if isinstance(data, dict):
        session_jwt = (
            data.get("token")
            or data.get("jwt")
            or data.get("accessToken")
            or data.get("access_token")
        )
        if not session_jwt and isinstance(data.get("response"), dict):
            session_jwt = data["response"].get("token")

    if not session_jwt:
        keys = ", ".join(sorted(list(data.keys()))) if isinstance(data, dict) else str(type(data))
        flash(
            "Login succeeded but Linkwarden did not return a Bearer token in /api/v1/session. "
            f"Please use a Linkwarden API token instead. Response keys: {keys}. "
            f"Body starts: {raw_snippet}",
            "error",
        )
        return redirect(url_for("login_get"))

    access_token = create_linkwarden_access_token(base_url, session_jwt, expires_seconds=0) or session_jwt

    session["lw_base_url"] = base_url
    session["lw_token"] = access_token
    session.setdefault("wallpaper_url", "")
    session.setdefault("collection_id", "")
    session.setdefault("grid_columns", 6)
    session.setdefault("sort_mode", "date_desc")

    return redirect(url_for("settings_get"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_get"))


@app.get("/settings")
def settings_get():
    if not require_login():
        return redirect(url_for("login_get"))

    collections: list[dict] = []
    try:
        r = lw_request("GET", "/api/v1/collections")
        if r.status_code != 200:
            flash(f"Could not load collections from Linkwarden (HTTP {r.status_code}).", "error")
        else:
            payload = r.json()
            collections = [x for x in extract_list_payload(payload) if isinstance(x, dict)]
            if not collections:
                keys = ", ".join(sorted(list(payload.keys()))) if isinstance(payload, dict) else str(type(payload))
                snippet = (r.text or "")[:300]
                flash(f"Linkwarden returned no collections. Response keys: {keys}. Body starts: {snippet}", "error")
    except requests.RequestException as e:
        flash(f"Error fetching collections: {e}", "error")

    return render_template(
        "settings.html",
        collections=collections,
        selected_collection_id=session.get("collection_id", ""),
        wallpaper_url=session.get("wallpaper_url", ""),
        lw_base_url=session.get("lw_base_url", ""),
        grid_columns=session.get("grid_columns", 6),
        sort_mode=session.get("sort_mode", "date_desc"),
    )


@app.post("/settings")
def settings_post():
    if not require_login():
        return redirect(url_for("login_get"))

    session["collection_id"] = (request.form.get("collection_id") or "").strip()
    session["wallpaper_url"] = (request.form.get("wallpaper_url") or "").strip()

    # Grid columns
    raw_cols = (request.form.get("grid_columns") or "").strip()
    try:
        cols = int(raw_cols)
    except Exception:
        cols = session.get("grid_columns", 6)
    cols = max(3, min(12, cols))
    session["grid_columns"] = cols

    # Sorting
    raw_sort = (request.form.get("sort_mode") or "").strip()
    if raw_sort not in ALLOWED_SORT_MODES:
        raw_sort = session.get("sort_mode", "date_desc")
    session["sort_mode"] = raw_sort

    session.modified = True

    key = (session.get("lw_base_url", ""), session.get("collection_id", ""))
    _links_cache.pop(key, None)

    return redirect(url_for("index"))


def fetch_links_for_collection(collection_id: str) -> list[dict]:
    if not collection_id:
        return []

    key = (session.get("lw_base_url", ""), collection_id)
    now = time.time()
    cached = _links_cache.get(key)
    if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        r = lw_request("GET", "/api/v1/links", params={"collectionId": int(collection_id)})
        if r.status_code in (404, 405):
            r = lw_request("GET", "/api/v1/public/collections/links", params={"collectionId": int(collection_id)})

        session["lw_last_links_status"] = r.status_code
        session["lw_last_links_debug"] = (r.text or "")[:500]

        if r.status_code != 200:
            return []

        payload = r.json()
        links = extract_list_payload(payload)
        links = [x for x in links if isinstance(x, dict)]

        _links_cache[key] = (now, links)
        return links
    except Exception:
        return []


@app.get("/thumb/<int:link_id>")
def thumb(link_id: int):
    if not require_login():
        return redirect(url_for("login_get"))

    fmt = 1  # 0=PNG, 1=JPEG
    try:
        r = lw_request(
            "GET",
            f"/api/v1/archives/{link_id}",
            params={"format": fmt, "preview": "true"},
            stream=True,
        )
    except requests.RequestException:
        return Response(status=404)

    if r.status_code != 200:
        return Response(status=404)

    return Response(r.content, status=200, mimetype=guess_image_mimetype(fmt))


@app.get("/")
def index():
    if not require_login():
        return redirect(url_for("login_get"))

    collection_id = session.get("collection_id", "")
    links = fetch_links_for_collection(collection_id)

    if collection_id and not links:
        dbg = session.get("lw_last_links_debug", "")
        st = session.get("lw_last_links_status", "?")
        if dbg:
            flash(f"No links returned for this collection (HTTP {st}). Body starts: {dbg}", "error")

    tiles: list[dict] = []
    for item in links:
        url = item.get("url") or ""
        title = item.get("name") or item.get("title") or url
        tiles.append(
            {
                "id": item.get("id"),
                "title": title,
                "url": url,
                "favicon": favicon_for(url),
                "description": item.get("description") or "",
                "pinned": bool(item.get("pinned", False)),
                "date": item.get("createdAt") or item.get("updatedAt") or item.get("created_at") or item.get("updated_at") or "",
            }
        )

    sort_mode = session.get("sort_mode", "date_desc")

    pinned_tiles = [t for t in tiles if t.get("pinned")]
    other_tiles = [t for t in tiles if not t.get("pinned")]

    def sort_key_name(t):
        return (t.get("title") or "").lower()

    def sort_key_date(t):
        return t.get("date") or ""

    if sort_mode == "name_asc":
        pinned_tiles.sort(key=sort_key_name)
        other_tiles.sort(key=sort_key_name)
    elif sort_mode == "name_desc":
        pinned_tiles.sort(key=sort_key_name, reverse=True)
        other_tiles.sort(key=sort_key_name, reverse=True)
    elif sort_mode == "date_asc":
        pinned_tiles.sort(key=sort_key_date)
        other_tiles.sort(key=sort_key_date)
    else:  # date_desc
        pinned_tiles.sort(key=sort_key_date, reverse=True)
        other_tiles.sort(key=sort_key_date, reverse=True)

    tiles = pinned_tiles + other_tiles

    return render_template(
        "index.html",
        tiles=tiles,
        wallpaper_url=session.get("wallpaper_url", ""),
        collection_id=collection_id,
        grid_columns=session.get("grid_columns", 6),
        sort_mode=sort_mode,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=FLASK_DEBUG)