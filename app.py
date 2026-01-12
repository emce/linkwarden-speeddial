import hmac
import os
import time
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-change-me")

FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "9018"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes", "on")

CACHE_TTL_SECONDS = 30

# Cache layout:
# _cache[key] = (expires_at_epoch, value)
_cache: Dict[str, Tuple[float, Any]] = {}

ALLOWED_SORT_MODES = {
    "date_desc",
    "date_asc",
    "name_asc",
    "name_desc",
}

DEFAULT_TIMEOUT = 15


# =========================
# Env config
# =========================

def env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v if v is not None else default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def normalize_sort_mode(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in ALLOWED_SORT_MODES else "date_desc"


def normalize_theme(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in {"auto", "dark", "light"} else "auto"


def normalize_background(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in {"wallpaper", "color"} else "wallpaper"


def env_int_range(
    name: str,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    """
    Read integer env var and clamp it to a safe range.
    Falls back to default if missing or invalid.
    """
    raw = os.getenv(name)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default

    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


LINKWARDEN_URL = env_str("LINKWARDEN_URL")
LINKWARDEN_USERNAME = env_str("LINKWARDEN_USERNAME")
LINKWARDEN_PASSWORD = env_str("LINKWARDEN_PASSWORD")
LINKWARDEN_TOKEN = env_str("LINKWARDEN_TOKEN")

LINKWARDEN_COLLECTION = env_str("LINKWARDEN_COLLECTION")
LINKWARDEN_COLLECTION_NAME = env_str("LINKWARDEN_COLLECTION_NAME", "Linkwarden SpeedDial")

LINKWARDEN_COLLECTION_COLUMNS = env_int_range(
    "LINKWARDEN_COLLECTION_COLUMNS",
    default=6,
    min_value=4,
    max_value=12,
)

LINKWARDEN_COLLECTION_SPACING = env_int_range(
    "LINKWARDEN_COLLECTION_SPACING",
    default=14,
    min_value=4,
    max_value=36,
)

LINKWARDEN_COLLECTION_SORT = normalize_sort_mode(env_str("LINKWARDEN_COLLECTION_SORT", "date_desc"))

SPEEDDIAL_THEME = normalize_theme(env_str("SPEEDDIAL_THEME", "auto"))
SPEEDDIAL_BACKGROUND = normalize_background(env_str("SPEEDDIAL_BACKGROUND", "wallpaper"))
SPEEDDIAL_WALLPAPER_URL = env_str("SPEEDDIAL_WALLPAPER_URL")
SPEEDDIAL_BACKGROUND_COLOR = env_str("SPEEDDIAL_BACKGROUND_COLOR", "#0b0b0d")
SPEEDDIAL_TEXT_COLOR = env_str("SPEEDDIAL_TEXT_COLOR", "")
SPEEDDIAL_OPEN_IN_NEW_TAB = env_bool("SPEEDDIAL_OPEN_IN_NEW_TAB", False)
SPEEDDIAL_BOOKMARKS = env_bool("SPEEDDIAL_BOOKMARKS", False)

HOSTNAME = env_str("HOSTNAME", "speeddial")

# Password gate (optional)
SPEEDDIAL_PASSWORD = os.getenv("SPEEDDIAL_PASSWORD", "").strip()

# Unlock TTL control:
# 0 = session-only (typically until browser close)
# otherwise N minutes
SPEEDDIAL_UNLOCK_TTL_MINUTES = env_int_range(
    "SPEEDDIAL_UNLOCK_TTL_MINUTES",
    default=0,
    min_value=0,
    max_value=60 * 24 * 365,  # 1 year (in minutes)
)

# If TTL > 0, set cookie lifetime (best-effort) + also enforce via timestamp in session
if SPEEDDIAL_UNLOCK_TTL_MINUTES > 0:
    app.permanent_session_lifetime = timedelta(minutes=SPEEDDIAL_UNLOCK_TTL_MINUTES)


def password_ok(given: str) -> bool:
    if not SPEEDDIAL_PASSWORD:
        return True  # no protection
    if not given:
        return False
    return hmac.compare_digest(given, SPEEDDIAL_PASSWORD)


def set_unlocked_session() -> None:
    """
    Mark this browser as unlocked.
    If TTL is set, store an absolute timestamp and make session permanent.
    If TTL is 0, keep it session-only (until browser close) and no timestamp required.
    """
    session["unlocked"] = True

    if SPEEDDIAL_UNLOCK_TTL_MINUTES > 0:
        session.permanent = True
        session["unlocked_until"] = time.time() + (SPEEDDIAL_UNLOCK_TTL_MINUTES * 60)
    else:
        session.permanent = False
        session.pop("unlocked_until", None)


def is_unlocked() -> bool:
    """
    Returns True if unlocked flag exists and (if TTL used) is not expired.
    """
    if not session.get("unlocked"):
        return False

    until = session.get("unlocked_until")
    if until is None:
        # TTL disabled -> session-only behavior
        return True

    try:
        until_f = float(until)
    except (TypeError, ValueError):
        session.pop("unlocked", None)
        session.pop("unlocked_until", None)
        return False

    if time.time() <= until_f:
        return True

    # expired
    session.pop("unlocked", None)
    session.pop("unlocked_until", None)
    return False


# =========================
# Cache helpers
# =========================

def cache_get(key: str) -> Optional[Any]:
    now = time.time()
    item = _cache.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at <= now:
        _cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    _cache[key] = (time.time() + ttl, value)


def cache_clear(prefix: str = "") -> None:
    if not prefix:
        _cache.clear()
        return
    for k in list(_cache.keys()):
        if k.startswith(prefix):
            _cache.pop(k, None)


# =========================
# Linkwarden client
# =========================

class LinkwardenError(RuntimeError):
    pass


def lw_base_url() -> str:
    return (LINKWARDEN_URL or "").rstrip("/")


def lw_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def extract_token(payload: Any) -> Optional[str]:
    """
    Linkwarden sometimes wraps responses in {"response": {...}}.
    Token may be in response.token or at top-level.
    """
    if not isinstance(payload, dict):
        return None
    resp = payload.get("response")
    if isinstance(resp, dict):
        for k in ("token", "accessToken", "access_token", "jwt"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    for k in ("token", "accessToken", "access_token", "jwt"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def ensure_token() -> str:
    """
    Prefer LINKWARDEN_TOKEN.
    If missing, attempt to login with username/password if provided.
    Cache the resulting token briefly to avoid repeated logins.
    """
    if LINKWARDEN_TOKEN:
        return LINKWARDEN_TOKEN

    cached = cache_get("lw:token")
    if isinstance(cached, str) and cached.strip():
        return cached.strip()

    if not (LINKWARDEN_USERNAME and LINKWARDEN_PASSWORD):
        raise LinkwardenError("Missing LINKWARDEN_TOKEN (or username/password).")

    base = lw_base_url()
    if not base:
        raise LinkwardenError("Missing LINKWARDEN_URL.")

    url = f"{base}/api/v1/session"
    payload = {"username": LINKWARDEN_USERNAME, "password": LINKWARDEN_PASSWORD}

    try:
        r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        raise LinkwardenError(f"Failed to connect to Linkwarden: {e}")

    if r.status_code >= 400:
        raise LinkwardenError(f"Login failed ({r.status_code}): {r.text[:300]}")

    data = r.json()
    token = extract_token(data)
    if not token:
        raise LinkwardenError("Login response did not include a token.")

    cache_set("lw:token", token, ttl=60)
    return token


def lw_get(path: str, params: Optional[Dict[str, str]] = None) -> Any:
    token = ensure_token()
    base = lw_base_url()
    if not base:
        raise LinkwardenError("Missing LINKWARDEN_URL.")
    url = f"{base}{path}"

    try:
        r = requests.get(url, headers=lw_headers(token), params=params, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        raise LinkwardenError(f"Failed to connect to Linkwarden: {e}")

    if r.status_code == 401:
        cache_clear("lw:token")
        raise LinkwardenError("Unauthorized (401) from Linkwarden.")
    if r.status_code >= 400:
        raise LinkwardenError(f"Linkwarden error ({r.status_code}): {r.text[:300]}")

    return r.json()


# =========================
# Password gate
# =========================

@app.before_request
def require_password_if_configured():
    if not SPEEDDIAL_PASSWORD:
        return None

    # allow static + unlock routes
    if request.endpoint in {"static", "unlock_get", "unlock_post"}:
        return None

    # already unlocked (and not expired)
    if is_unlocked():
        return None

    # allow one-time URL param unlock
    given = (request.args.get("p") or "").strip()
    if password_ok(given):
        set_unlocked_session()
        # redirect to same path without querystring to avoid leaking password
        return redirect(request.path)

    return redirect(url_for("unlock_get"))


# =========================
# Backend API (used by JS)
# =========================

@app.get("/api/collections")
def api_collections():
    """
    Returns Linkwarden collections in the same wrapper form your JS expects:
    { "response": [...] }
    """
    cached = cache_get("lw:collections")
    if cached is not None:
        return jsonify({"response": cached})

    data = lw_get("/api/v1/collections")
    resp = data.get("response") if isinstance(data, dict) else None
    if not isinstance(resp, list):
        resp = data if isinstance(data, list) else []

    cache_set("lw:collections", resp)
    return jsonify({"response": resp})


@app.get("/api/links")
def api_links():
    """
    Returns links for a collection:
    /api/links?collection_id=50
    Keeps response wrapper: { "response": [...] }
    """
    collection_id = (request.args.get("collection_id") or "").strip()
    if not collection_id:
        return jsonify({"response": []})

    key = f"lw:links:{collection_id}"
    cached = cache_get(key)
    if cached is not None:
        return jsonify({"response": cached})

    links: list = []

    try:
        data = lw_get("/api/v1/links", params={"collectionId": collection_id})
        resp = data.get("response") if isinstance(data, dict) else None
        if isinstance(resp, list):
            links = resp
        elif isinstance(data, list):
            links = data
    except LinkwardenError:
        data = lw_get(f"/api/v1/collections/{collection_id}/links")
        resp = data.get("response") if isinstance(data, dict) else None
        if isinstance(resp, list):
            links = resp
        elif isinstance(data, list):
            links = data

    cache_set(key, links)
    return jsonify({"response": links})


@app.get("/api/tree")
def api_tree():
    """
    Optional helper endpoint: returns collections plus links for main collection
    (and can be extended later to fetch everything).
    """
    cached = cache_get("lw:tree")
    if cached is not None:
        return jsonify(cached)

    cols = api_collections().get_json().get("response", [])
    out = {"collections": cols, "linksByCollection": {}}

    if LINKWARDEN_COLLECTION:
        # Call internal function logic by querying /api/links with the main collection_id
        # (keeps cache behavior consistent)
        with app.test_request_context(f"/api/links?collection_id={LINKWARDEN_COLLECTION}"):
            links = api_links().get_json().get("response", [])
        out["linksByCollection"][str(LINKWARDEN_COLLECTION)] = links

    cache_set("lw:tree", out)
    return jsonify(out)


# =========================
# Main page
# =========================

@app.get("/")
def index():
    show_sidebar = bool(SPEEDDIAL_BOOKMARKS)

    return render_template(
        "index.html",
        hostname=HOSTNAME,
        title="Linkwarden Speed Dial",
        theme=SPEEDDIAL_THEME,
        background_mode=SPEEDDIAL_BACKGROUND,
        wallpaper_url=SPEEDDIAL_WALLPAPER_URL,
        background_color=SPEEDDIAL_BACKGROUND_COLOR,
        text_color=SPEEDDIAL_TEXT_COLOR,
        linkwarden_url=lw_base_url(),
        collection_id=LINKWARDEN_COLLECTION,
        sort_mode=LINKWARDEN_COLLECTION_SORT,
        open_new_tab=SPEEDDIAL_OPEN_IN_NEW_TAB,
        show_sidebar=show_sidebar,
        grid_columns=LINKWARDEN_COLLECTION_COLUMNS,
        grid_spacing=LINKWARDEN_COLLECTION_SPACING,
        collection_name=LINKWARDEN_COLLECTION_NAME,
    )


@app.get("/unlock")
def unlock_get():
    if not SPEEDDIAL_PASSWORD:
        return redirect(url_for("index"))

    return render_template(
        "unlock.html",
        theme=SPEEDDIAL_THEME,
        background_mode=SPEEDDIAL_BACKGROUND,
        wallpaper_url=SPEEDDIAL_WALLPAPER_URL,
        background_color=SPEEDDIAL_BACKGROUND_COLOR,
        text_color=SPEEDDIAL_TEXT_COLOR,
    )


@app.post("/unlock")
def unlock_post():
    if not SPEEDDIAL_PASSWORD:
        return redirect(url_for("index"))

    given = (request.form.get("password") or "").strip()
    if password_ok(given):
        set_unlocked_session()
        return redirect(url_for("index"))

    return render_template(
        "unlock.html",
        error="Wrong password",
        theme=SPEEDDIAL_THEME,
        background_mode=SPEEDDIAL_BACKGROUND,
        wallpaper_url=SPEEDDIAL_WALLPAPER_URL,
        background_color=SPEEDDIAL_BACKGROUND_COLOR,
        text_color=SPEEDDIAL_TEXT_COLOR,
    )


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)