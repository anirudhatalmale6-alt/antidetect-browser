#!/usr/bin/env python3
"""
Anti-Detect Browser Profile Manager — Flask API Backend

Internal tool for managing browser profiles with fingerprint spoofing,
proxy support, and extension loading. Profiles stored in SQLite.

Run:  python server.py
Port: 5070
"""

import json
import os
import random
import sqlite3
import textwrap
import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "profiles.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# Realistic data pools for fingerprint generation
# ---------------------------------------------------------------------------

WEBGL_RENDERERS = [
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) HD Graphics 520 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel(R) Iris(R) Plus Graphics 640 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce GTX 1070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 2060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 2070 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)"},
    {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)"},
    {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)"},
    {"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)"},
]

USER_AGENTS_WINDOWS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

USER_AGENTS_MAC = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

USER_AGENTS_LINUX = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

SCREEN_RESOLUTIONS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1920, "height": 1200},
    {"width": 2560, "height": 1440},
    {"width": 2560, "height": 1600},
    {"width": 3440, "height": 1440},
    {"width": 3840, "height": 2160},
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Toronto",
    "America/Vancouver",
    "America/Mexico_City",
    "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Amsterdam",
    "Europe/Warsaw",
    "Europe/Moscow",
    "Europe/Istanbul",
    "Europe/Zurich",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Singapore",
    "Asia/Seoul",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Bangkok",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Pacific/Auckland",
    "Pacific/Honolulu",
]

LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,de;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8",
    "fr-FR,fr;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en;q=0.8",
    "pt-BR,pt;q=0.9,en;q=0.8",
    "ja-JP,ja;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9,en;q=0.8",
    "ko-KR,ko;q=0.9,en;q=0.8",
    "it-IT,it;q=0.9,en;q=0.8",
    "ru-RU,ru;q=0.9,en;q=0.8",
    "nl-NL,nl;q=0.9,en;q=0.8",
]

PLATFORMS = ["Win32", "MacIntel", "Linux x86_64"]

HARDWARE_CONCURRENCY = [2, 4, 6, 8]
DEVICE_MEMORY = [2, 4, 8, 16]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Return a per-request database connection stored on Flask *g*."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS folders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS profiles (
            id              TEXT    PRIMARY KEY,
            name            TEXT    NOT NULL,
            folder_id       INTEGER,
            proxy           TEXT    DEFAULT '',
            window_width    INTEGER NOT NULL DEFAULT 1920,
            window_height   INTEGER NOT NULL DEFAULT 1080,
            user_agent      TEXT    NOT NULL,
            notes           TEXT    DEFAULT '',
            fingerprint     TEXT    NOT NULL,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            last_launched   TEXT,
            FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
        );

        -- Default folder so new profiles have somewhere to go
        INSERT OR IGNORE INTO folders (id, name) VALUES (1, 'Default');
        """
    )
    conn.commit()
    conn.close()

init_db()


def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Fingerprint generator
# ---------------------------------------------------------------------------

def generate_fingerprint(*, platform_hint=None, user_agent=None):
    """
    Build a realistic browser-fingerprint config.

    If *platform_hint* is given ("Win32", "MacIntel", "Linux x86_64"), the
    generated values will be coherent with that platform.  Otherwise one is
    chosen at random.
    """
    platform = platform_hint or random.choice(PLATFORMS)

    # Pick a user-agent that matches the platform (if none was supplied).
    if user_agent:
        ua = user_agent
    elif platform == "Win32":
        ua = random.choice(USER_AGENTS_WINDOWS)
    elif platform == "MacIntel":
        ua = random.choice(USER_AGENTS_MAC)
    else:
        ua = random.choice(USER_AGENTS_LINUX)

    # WebGL — prefer GPU vendors that match the platform
    if platform == "MacIntel":
        webgl_pool = [r for r in WEBGL_RENDERERS if "Apple" in r["vendor"]]
    else:
        webgl_pool = [r for r in WEBGL_RENDERERS if "Apple" not in r["vendor"]]
    webgl = random.choice(webgl_pool)

    screen = random.choice(SCREEN_RESOLUTIONS)

    # Colour depth / pixel ratio
    color_depth = random.choice([24, 32])
    pixel_ratio = random.choice([1, 1, 1, 1.25, 1.5, 2])  # 1 is most common

    return {
        "canvas": {
            "noise_seed": random.randint(100000, 999999),
            "noise_level": round(random.uniform(0.01, 0.04), 4),
        },
        "webgl": {
            "vendor": webgl["vendor"],
            "renderer": webgl["renderer"],
            "noise_seed": random.randint(100000, 999999),
        },
        "audio": {
            "noise_seed": random.randint(100000, 999999),
            "noise_level": round(random.uniform(0.0001, 0.001), 6),
        },
        "screen": {
            "width": screen["width"],
            "height": screen["height"],
            "avail_width": screen["width"],
            "avail_height": screen["height"] - random.choice([0, 40, 48]),
            "color_depth": color_depth,
            "pixel_ratio": pixel_ratio,
        },
        "navigator": {
            "platform": platform,
            "hardware_concurrency": random.choice(HARDWARE_CONCURRENCY),
            "device_memory": random.choice(DEVICE_MEMORY),
            "max_touch_points": 0 if platform != "MacIntel" else random.choice([0, 0, 5]),
            "language": random.choice(LANGUAGES),
            "languages": None,  # derived from language at runtime
            "do_not_track": random.choice([None, "1"]),
        },
        "timezone": {
            "id": random.choice(TIMEZONES),
        },
        "fonts": {
            "noise_seed": random.randint(100000, 999999),
        },
        "media_devices": {
            "audioinput": random.randint(0, 2),
            "audiooutput": random.randint(1, 3),
            "videoinput": random.randint(0, 2),
        },
        "battery": {
            "charging": random.choice([True, False]),
            "level": round(random.uniform(0.15, 1.0), 2),
        },
        "client_rects": {
            "noise_seed": random.randint(100000, 999999),
            "noise_level": round(random.uniform(0.1, 0.9), 4),
        },
    }


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description)}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(409)
def conflict(e):
    return jsonify({"error": str(e.description)}), 409


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    """List all profiles, optionally filtered by folder_id."""
    db = get_db()
    folder_id = request.args.get("folder_id")
    search = request.args.get("search")

    query = """
        SELECT p.*, f.name AS folder_name
        FROM profiles p
        LEFT JOIN folders f ON p.folder_id = f.id
        WHERE 1=1
    """
    params = []

    if folder_id is not None:
        query += " AND p.folder_id = ?"
        params.append(int(folder_id))

    if search:
        query += " AND (p.name LIKE ? OR p.notes LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY p.updated_at DESC"

    rows = db.execute(query, params).fetchall()
    profiles = []
    for r in rows:
        d = row_to_dict(r)
        d["fingerprint"] = json.loads(d["fingerprint"])
        profiles.append(d)

    return jsonify({"profiles": profiles, "count": len(profiles)})


@app.route("/api/profiles", methods=["POST"])
def create_profile():
    """Create a new browser profile."""
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Profile name is required"}), 400

    profile_id = str(uuid.uuid4())
    folder_id = data.get("folder_id")
    proxy = data.get("proxy", "")
    window_width = int(data.get("window_width", 1920))
    window_height = int(data.get("window_height", 1080))
    user_agent = data.get("user_agent", "")
    notes = data.get("notes", "")
    platform_hint = data.get("platform")

    # Validate folder if provided
    if folder_id is not None:
        folder = db.execute("SELECT id FROM folders WHERE id = ?", (int(folder_id),)).fetchone()
        if not folder:
            return jsonify({"error": f"Folder {folder_id} does not exist"}), 400

    # Generate fingerprint
    fp = generate_fingerprint(platform_hint=platform_hint, user_agent=user_agent or None)

    # If no user_agent was supplied, take the one from the fingerprint
    if not user_agent:
        # Determine from the platform in fingerprint
        plat = fp["navigator"]["platform"]
        if plat == "Win32":
            user_agent = random.choice(USER_AGENTS_WINDOWS)
        elif plat == "MacIntel":
            user_agent = random.choice(USER_AGENTS_MAC)
        else:
            user_agent = random.choice(USER_AGENTS_LINUX)

    ts = now_iso()

    db.execute(
        """
        INSERT INTO profiles
            (id, name, folder_id, proxy, window_width, window_height,
             user_agent, notes, fingerprint, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id,
            name,
            int(folder_id) if folder_id is not None else None,
            proxy,
            window_width,
            window_height,
            user_agent,
            notes,
            json.dumps(fp),
            ts,
            ts,
        ),
    )
    db.commit()

    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    result = row_to_dict(row)
    result["fingerprint"] = json.loads(result["fingerprint"])

    return jsonify({"profile": result}), 201


@app.route("/api/profiles/<profile_id>", methods=["GET"])
def get_profile(profile_id):
    """Get a single profile with full fingerprint config."""
    db = get_db()
    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        return jsonify({"error": "Profile not found"}), 404

    result = row_to_dict(row)
    result["fingerprint"] = json.loads(result["fingerprint"])
    return jsonify({"profile": result})


@app.route("/api/profiles/<profile_id>", methods=["PUT"])
def update_profile(profile_id):
    """Update an existing profile."""
    db = get_db()
    existing = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "Profile not found"}), 404

    data = request.get_json(force=True, silent=True) or {}

    name = data.get("name", existing["name"])
    folder_id = data.get("folder_id", existing["folder_id"])
    proxy = data.get("proxy", existing["proxy"])
    window_width = int(data.get("window_width", existing["window_width"]))
    window_height = int(data.get("window_height", existing["window_height"]))
    user_agent = data.get("user_agent", existing["user_agent"])
    notes = data.get("notes", existing["notes"])

    # Optionally regenerate fingerprint
    if data.get("regenerate_fingerprint"):
        fp = generate_fingerprint(
            platform_hint=data.get("platform"),
            user_agent=user_agent if user_agent != existing["user_agent"] else None,
        )
        fingerprint_json = json.dumps(fp)
    elif "fingerprint" in data and isinstance(data["fingerprint"], dict):
        # Allow manual fingerprint overrides (merge with existing)
        existing_fp = json.loads(existing["fingerprint"])
        _deep_merge(existing_fp, data["fingerprint"])
        fingerprint_json = json.dumps(existing_fp)
    else:
        fingerprint_json = existing["fingerprint"]

    if folder_id is not None:
        folder = db.execute("SELECT id FROM folders WHERE id = ?", (int(folder_id),)).fetchone()
        if not folder:
            return jsonify({"error": f"Folder {folder_id} does not exist"}), 400

    ts = now_iso()

    db.execute(
        """
        UPDATE profiles SET
            name = ?, folder_id = ?, proxy = ?, window_width = ?,
            window_height = ?, user_agent = ?, notes = ?,
            fingerprint = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            name,
            int(folder_id) if folder_id is not None else None,
            proxy,
            window_width,
            window_height,
            user_agent,
            notes,
            fingerprint_json,
            ts,
            profile_id,
        ),
    )
    db.commit()

    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    result = row_to_dict(row)
    result["fingerprint"] = json.loads(result["fingerprint"])
    return jsonify({"profile": result})


@app.route("/api/profiles/<profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
    """Delete a profile."""
    db = get_db()
    existing = db.execute("SELECT id, name FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "Profile not found"}), 404

    db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    db.commit()
    return jsonify({"deleted": profile_id, "name": existing["name"]})


# ---------------------------------------------------------------------------
# Folder endpoints
# ---------------------------------------------------------------------------

@app.route("/api/folders", methods=["GET"])
def list_folders():
    """List all folders with profile counts."""
    db = get_db()
    rows = db.execute(
        """
        SELECT f.*, COUNT(p.id) AS profile_count
        FROM folders f
        LEFT JOIN profiles p ON p.folder_id = f.id
        GROUP BY f.id
        ORDER BY f.name
        """
    ).fetchall()
    return jsonify({"folders": [row_to_dict(r) for r in rows]})


@app.route("/api/folders", methods=["POST"])
def create_folder():
    """Create a new folder."""
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Folder name is required"}), 400

    db = get_db()

    # Check uniqueness
    if db.execute("SELECT id FROM folders WHERE name = ?", (name,)).fetchone():
        return jsonify({"error": f"Folder '{name}' already exists"}), 409

    ts = now_iso()
    cursor = db.execute(
        "INSERT INTO folders (name, created_at, updated_at) VALUES (?, ?, ?)",
        (name, ts, ts),
    )
    db.commit()
    folder_id = cursor.lastrowid

    return jsonify({"folder": {"id": folder_id, "name": name, "created_at": ts, "updated_at": ts, "profile_count": 0}}), 201


@app.route("/api/folders/<int:folder_id>", methods=["PUT"])
def rename_folder(folder_id):
    """Rename a folder."""
    db = get_db()
    existing = db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "Folder not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Folder name is required"}), 400

    # Check uniqueness (excluding self)
    dup = db.execute("SELECT id FROM folders WHERE name = ? AND id != ?", (name, folder_id)).fetchone()
    if dup:
        return jsonify({"error": f"Folder '{name}' already exists"}), 409

    ts = now_iso()
    db.execute("UPDATE folders SET name = ?, updated_at = ? WHERE id = ?", (name, ts, folder_id))
    db.commit()

    return jsonify({"folder": {"id": folder_id, "name": name, "updated_at": ts}})


@app.route("/api/folders/<int:folder_id>", methods=["DELETE"])
def delete_folder(folder_id):
    """Delete a folder. Must be empty (no profiles assigned)."""
    db = get_db()
    existing = db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "Folder not found"}), 404

    profile_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM profiles WHERE folder_id = ?", (folder_id,)
    ).fetchone()["cnt"]

    if profile_count > 0:
        return jsonify({
            "error": f"Cannot delete folder — it still contains {profile_count} profile(s). Move or delete them first."
        }), 409

    db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    db.commit()
    return jsonify({"deleted": folder_id, "name": existing["name"]})


# ---------------------------------------------------------------------------
# Launch config
# ---------------------------------------------------------------------------

@app.route("/api/profiles/<profile_id>/launch", methods=["POST"])
def launch_profile(profile_id):
    """
    Return the full launch configuration needed to start a Chromium instance
    locally with this profile's fingerprint/proxy/settings.
    """
    db = get_db()
    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        return jsonify({"error": "Profile not found"}), 404

    profile = row_to_dict(row)
    fp = json.loads(profile["fingerprint"])

    # Parse proxy string  ip:port:user:pass
    proxy_config = None
    if profile["proxy"]:
        parts = profile["proxy"].split(":")
        if len(parts) == 4:
            proxy_config = {
                "host": parts[0],
                "port": int(parts[1]),
                "username": parts[2],
                "password": parts[3],
                "server": f"{parts[0]}:{parts[1]}",
            }
        elif len(parts) == 2:
            proxy_config = {
                "host": parts[0],
                "port": int(parts[1]),
                "username": None,
                "password": None,
                "server": f"{parts[0]}:{parts[1]}",
            }

    # Build Chromium flags
    chromium_flags = [
        f"--user-data-dir=./browser_profiles/{profile_id}",
        f"--window-size={profile['window_width']},{profile['window_height']}",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-agent={profile['user_agent']}",
    ]

    if proxy_config:
        chromium_flags.append(f"--proxy-server={proxy_config['server']}")

    # Extension paths placeholder
    extension_paths = [
        "./extensions/fingerprint-injector",
    ]
    if extension_paths:
        chromium_flags.append(f"--load-extension={','.join(extension_paths)}")

    # Mark last launched
    ts = now_iso()
    db.execute("UPDATE profiles SET last_launched = ? WHERE id = ?", (ts, profile_id))
    db.commit()

    launch_config = {
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "user_data_dir": f"./browser_profiles/{profile_id}",
        "proxy": proxy_config,
        "window_size": {
            "width": profile["window_width"],
            "height": profile["window_height"],
        },
        "user_agent": profile["user_agent"],
        "extension_paths": extension_paths,
        "chromium_flags": chromium_flags,
        "fingerprint": fp,
        "launched_at": ts,
    }

    return jsonify({"launch_config": launch_config})


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

@app.route("/api/profiles/<profile_id>/export", methods=["GET"])
def export_profile(profile_id):
    """Export a profile's full configuration as JSON."""
    db = get_db()
    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    if row is None:
        return jsonify({"error": "Profile not found"}), 404

    profile = row_to_dict(row)
    profile["fingerprint"] = json.loads(profile["fingerprint"])

    export_data = {
        "version": 1,
        "exported_at": now_iso(),
        "profile": {
            "name": profile["name"],
            "folder_name": profile["folder_name"],
            "proxy": profile["proxy"],
            "window_width": profile["window_width"],
            "window_height": profile["window_height"],
            "user_agent": profile["user_agent"],
            "notes": profile["notes"],
            "fingerprint": profile["fingerprint"],
        },
    }
    return jsonify(export_data)


@app.route("/api/profiles/import", methods=["POST"])
def import_profile():
    """Import a profile from a previously exported JSON payload."""
    data = request.get_json(force=True, silent=True)
    if not data or "profile" not in data:
        return jsonify({"error": "Invalid import data — 'profile' key required"}), 400

    p = data["profile"]
    db = get_db()

    profile_id = str(uuid.uuid4())
    name = p.get("name", "Imported Profile")
    proxy = p.get("proxy", "")
    window_width = int(p.get("window_width", 1920))
    window_height = int(p.get("window_height", 1080))
    user_agent = p.get("user_agent", random.choice(USER_AGENTS_WINDOWS))
    notes = p.get("notes", "")

    # Resolve folder
    folder_id = None
    folder_name = p.get("folder_name")
    if folder_name:
        folder_row = db.execute("SELECT id FROM folders WHERE name = ?", (folder_name,)).fetchone()
        if folder_row:
            folder_id = folder_row["id"]
        else:
            # Auto-create the folder
            ts_f = now_iso()
            cur = db.execute(
                "INSERT INTO folders (name, created_at, updated_at) VALUES (?, ?, ?)",
                (folder_name, ts_f, ts_f),
            )
            folder_id = cur.lastrowid

    # Fingerprint — use provided or generate fresh
    if "fingerprint" in p and isinstance(p["fingerprint"], dict):
        fp_json = json.dumps(p["fingerprint"])
    else:
        fp_json = json.dumps(generate_fingerprint(user_agent=user_agent))

    ts = now_iso()
    db.execute(
        """
        INSERT INTO profiles
            (id, name, folder_id, proxy, window_width, window_height,
             user_agent, notes, fingerprint, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (profile_id, name, folder_id, proxy, window_width, window_height, user_agent, notes, fp_json, ts, ts),
    )
    db.commit()

    row = db.execute(
        "SELECT p.*, f.name AS folder_name FROM profiles p LEFT JOIN folders f ON p.folder_id = f.id WHERE p.id = ?",
        (profile_id,),
    ).fetchone()
    result = row_to_dict(row)
    result["fingerprint"] = json.loads(result["fingerprint"])

    return jsonify({"profile": result, "imported": True}), 201


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def stats():
    """Dashboard statistics."""
    db = get_db()
    total_profiles = db.execute("SELECT COUNT(*) AS cnt FROM profiles").fetchone()["cnt"]
    total_folders = db.execute("SELECT COUNT(*) AS cnt FROM folders").fetchone()["cnt"]
    profiles_with_proxy = db.execute(
        "SELECT COUNT(*) AS cnt FROM profiles WHERE proxy != '' AND proxy IS NOT NULL"
    ).fetchone()["cnt"]
    recently_launched = db.execute(
        "SELECT COUNT(*) AS cnt FROM profiles WHERE last_launched IS NOT NULL"
    ).fetchone()["cnt"]

    # Profiles per folder
    folder_stats = db.execute(
        """
        SELECT f.name, COUNT(p.id) AS profile_count
        FROM folders f LEFT JOIN profiles p ON p.folder_id = f.id
        GROUP BY f.id ORDER BY profile_count DESC
        """
    ).fetchall()

    return jsonify({
        "total_profiles": total_profiles,
        "total_folders": total_folders,
        "profiles_with_proxy": profiles_with_proxy,
        "profiles_launched": recently_launched,
        "profiles_without_proxy": total_profiles - profiles_with_proxy,
        "folder_breakdown": [row_to_dict(r) for r in folder_stats],
    })


# ---------------------------------------------------------------------------
# Launch script endpoint
# ---------------------------------------------------------------------------

LAUNCH_SCRIPT_TEMPLATE = textwrap.dedent(r'''
#!/usr/bin/env python3
"""
Anti-Detect Browser Launcher
=============================
Downloads profile config from the dashboard API, writes a fingerprint-
spoofing Chrome extension on the fly, and launches Chromium with full
isolation and the right flags.

Usage:
    python launch.py <PROFILE_ID> [--api http://localhost:5070]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required.  pip install requests")
    sys.exit(1)


DEFAULT_API = "http://localhost:5070"

# Chromium binary search paths (adjust to your system)
CHROMIUM_CANDIDATES = [
    # Linux
    "chromium-browser",
    "chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
    # Google Chrome
    "google-chrome",
    "google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # Windows (common paths)
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chromium():
    """Locate a usable Chromium/Chrome binary."""
    for candidate in CHROMIUM_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def build_fingerprint_extension(fp: dict, ext_dir: str):
    """Write a minimal Chrome extension that injects fingerprint overrides."""
    manifest = {
        "manifest_version": 3,
        "name": "FP Injector",
        "version": "1.0",
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": ["inject.js"],
                "run_at": "document_start",
                "world": "MAIN",
            }
        ],
    }

    nav = fp.get("navigator", {})
    screen = fp.get("screen", {})
    webgl = fp.get("webgl", {})
    canvas = fp.get("canvas", {})
    audio = fp.get("audio", {})

    inject_js = f"""
// --- Anti-Detect Fingerprint Injection ---
(function() {{
    'use strict';

    // Navigator overrides
    const navProps = {{
        platform: {json.dumps(nav.get('platform', 'Win32'))},
        hardwareConcurrency: {json.dumps(nav.get('hardware_concurrency', 4))},
        deviceMemory: {json.dumps(nav.get('device_memory', 8))},
        maxTouchPoints: {json.dumps(nav.get('max_touch_points', 0))},
        language: {json.dumps(nav.get('language', 'en-US,en;q=0.9').split(',')[0])},
        languages: Object.freeze({json.dumps(nav.get('language', 'en-US,en;q=0.9').split(','))}),
    }};

    for (const [key, value] of Object.entries(navProps)) {{
        try {{
            Object.defineProperty(Navigator.prototype, key, {{
                get: () => value,
                configurable: true,
            }});
        }} catch(e) {{}}
    }}

    // Screen overrides
    const screenOverrides = {{
        width: {screen.get('width', 1920)},
        height: {screen.get('height', 1080)},
        availWidth: {screen.get('avail_width', 1920)},
        availHeight: {screen.get('avail_height', 1040)},
        colorDepth: {screen.get('color_depth', 24)},
        pixelDepth: {screen.get('color_depth', 24)},
    }};

    for (const [key, value] of Object.entries(screenOverrides)) {{
        try {{
            Object.defineProperty(Screen.prototype, key, {{
                get: () => value,
                configurable: true,
            }});
        }} catch(e) {{}}
    }}

    // DevicePixelRatio
    try {{
        Object.defineProperty(window, 'devicePixelRatio', {{
            get: () => {screen.get('pixel_ratio', 1)},
            configurable: true,
        }});
    }} catch(e) {{}}

    // WebGL vendor/renderer spoofing
    const origGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        const UNMASKED_VENDOR = 0x9245;
        const UNMASKED_RENDERER = 0x9246;
        if (param === UNMASKED_VENDOR) return {json.dumps(webgl.get('vendor', 'Google Inc. (Intel)'))};
        if (param === UNMASKED_RENDERER) return {json.dumps(webgl.get('renderer', 'ANGLE (Intel(R) UHD Graphics 620)'))};
        return origGetParameter.call(this, param);
    }};

    const origGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {{
        const UNMASKED_VENDOR = 0x9245;
        const UNMASKED_RENDERER = 0x9246;
        if (param === UNMASKED_VENDOR) return {json.dumps(webgl.get('vendor', 'Google Inc. (Intel)'))};
        if (param === UNMASKED_RENDERER) return {json.dumps(webgl.get('renderer', 'ANGLE (Intel(R) UHD Graphics 620)'))};
        return origGetParameter2.call(this, param);
    }};

    // Canvas noise injection
    const canvasSeed = {canvas.get('noise_seed', 123456)};
    const canvasNoise = {canvas.get('noise_level', 0.02)};
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {{
        const ctx = this.getContext('2d');
        if (ctx) {{
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            const data = imageData.data;
            let s = canvasSeed;
            for (let i = 0; i < data.length; i += 4) {{
                s = (s * 16807 + 0) % 2147483647;
                data[i] = Math.max(0, Math.min(255, data[i] + Math.floor((s / 2147483647 - 0.5) * canvasNoise * 10)));
            }}
            ctx.putImageData(imageData, 0, 0);
        }}
        return origToDataURL.apply(this, arguments);
    }};

    // AudioContext noise
    const audioSeed = {audio.get('noise_seed', 654321)};
    const audioNoise = {audio.get('noise_level', 0.0005)};
    const origCreateOsc = AudioContext.prototype.createOscillator;
    const origCreateAnalyser = AudioContext.prototype.createAnalyser;

    const origGetFloatFreq = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = function(array) {{
        origGetFloatFreq.call(this, array);
        let s = audioSeed;
        for (let i = 0; i < array.length; i++) {{
            s = (s * 16807 + 0) % 2147483647;
            array[i] += (s / 2147483647 - 0.5) * audioNoise;
        }}
    }};

    // Timezone override
    const tz = {json.dumps(fp.get('timezone', {{}}).get('id', 'America/New_York'))};
    const origDTF = Intl.DateTimeFormat;
    const handler = {{
        construct(target, args) {{
            if (args.length === 0) args = [undefined];
            if (!args[1]) args[1] = {{}};
            args[1].timeZone = tz;
            return new target(...args);
        }},
    }};
    window.Intl.DateTimeFormat = new Proxy(origDTF, handler);

    // Battery API
    if (navigator.getBattery) {{
        const batteryData = {{
            charging: {json.dumps(fp.get('battery', {{}}).get('charging', True))},
            chargingTime: Infinity,
            dischargingTime: Infinity,
            level: {fp.get('battery', {{}}).get('level', 0.85)},
            addEventListener: function() {{}},
            removeEventListener: function() {{}},
            dispatchEvent: function() {{ return true; }},
        }};
        navigator.getBattery = () => Promise.resolve(batteryData);
    }}

    // MediaDevices enumeration
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
        const md = {json.dumps(fp.get('media_devices', {'audioinput': 1, 'audiooutput': 1, 'videoinput': 1}))};
        const origEnum = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
        navigator.mediaDevices.enumerateDevices = async () => {{
            const devices = [];
            for (let i = 0; i < md.audioinput; i++)
                devices.push({{ deviceId: 'ai_' + i, kind: 'audioinput', label: '', groupId: 'g' + i }});
            for (let i = 0; i < md.audiooutput; i++)
                devices.push({{ deviceId: 'ao_' + i, kind: 'audiooutput', label: '', groupId: 'g' + i }});
            for (let i = 0; i < md.videoinput; i++)
                devices.push({{ deviceId: 'vi_' + i, kind: 'videoinput', label: '', groupId: 'g' + i }});
            return devices;
        }};
    }}

    console.log('[FP Injector] Fingerprint overrides active');
}})();
"""

    os.makedirs(ext_dir, exist_ok=True)
    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(ext_dir, "inject.js"), "w") as f:
        f.write(inject_js)


def build_proxy_extension(proxy_cfg: dict, ext_dir: str):
    """Build a Chrome extension for authenticated proxy (Manifest V3 compatible)."""
    if not proxy_cfg or not proxy_cfg.get("username"):
        return None

    os.makedirs(ext_dir, exist_ok=True)

    manifest = {
        "manifest_version": 3,
        "name": "Proxy Auth",
        "version": "1.0",
        "permissions": ["webRequest", "webRequestAuthProvider"],
        "host_permissions": ["<all_urls>"],
        "background": {"service_worker": "background.js"},
    }

    background_js = f"""
chrome.webRequest.onAuthRequired.addListener(
    function(details) {{
        return {{
            authCredentials: {{
                username: {json.dumps(proxy_cfg['username'])},
                password: {json.dumps(proxy_cfg['password'])}
            }}
        }};
    }},
    {{ urls: ["<all_urls>"] }},
    ["blocking"]
);
"""

    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(ext_dir, "background.js"), "w") as f:
        f.write(background_js)

    return ext_dir


def main():
    parser = argparse.ArgumentParser(description="Launch anti-detect browser profile")
    parser.add_argument("profile_id", help="UUID of the profile to launch")
    parser.add_argument("--api", default=DEFAULT_API, help="Dashboard API base URL")
    parser.add_argument("--chromium", default=None, help="Path to Chromium/Chrome binary")
    parser.add_argument("--headless", action="store_true", help="Launch in headless mode")
    parser.add_argument("--dry-run", action="store_true", help="Print command without launching")
    args = parser.parse_args()

    # 1) Fetch launch config from dashboard
    url = f"{args.api}/api/profiles/{args.profile_id}/launch"
    print(f"[*] Fetching launch config from {url}")

    try:
        resp = requests.post(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[!] Failed to fetch config: {e}")
        sys.exit(1)

    config = resp.json()["launch_config"]
    fp = config["fingerprint"]
    print(f"[+] Profile: {config['profile_name']}")
    print(f"[+] Platform: {fp['navigator']['platform']}")
    print(f"[+] User-Agent: {config['user_agent'][:80]}...")

    # 2) Locate Chromium
    chromium = args.chromium or find_chromium()
    if not chromium:
        print("[!] Could not find Chromium/Chrome. Specify with --chromium /path/to/chrome")
        sys.exit(1)
    print(f"[+] Browser: {chromium}")

    # 3) Prepare user data directory
    profile_dir = os.path.abspath(config["user_data_dir"])
    os.makedirs(profile_dir, exist_ok=True)
    print(f"[+] Profile dir: {profile_dir}")

    # 4) Build fingerprint injection extension
    ext_base = os.path.join(profile_dir, "_extensions")
    fp_ext_dir = os.path.join(ext_base, "fingerprint-injector")
    build_fingerprint_extension(fp, fp_ext_dir)
    print("[+] Fingerprint extension built")

    extensions = [fp_ext_dir]

    # 5) Build proxy auth extension if needed
    proxy = config.get("proxy")
    if proxy and proxy.get("username"):
        proxy_ext_dir = os.path.join(ext_base, "proxy-auth")
        build_proxy_extension(proxy, proxy_ext_dir)
        extensions.append(proxy_ext_dir)
        print(f"[+] Proxy: {proxy['server']} (auth extension built)")
    elif proxy:
        print(f"[+] Proxy: {proxy['server']} (no auth)")
    else:
        print("[+] Proxy: none")

    # 6) Assemble command
    cmd = [chromium]
    cmd.append(f"--user-data-dir={profile_dir}")
    cmd.append(f"--window-size={config['window_size']['width']},{config['window_size']['height']}")
    cmd.append(f"--user-agent={config['user_agent']}")

    if proxy:
        cmd.append(f"--proxy-server={proxy['server']}")

    cmd.append(f"--load-extension={','.join(extensions)}")

    # Stealth / isolation flags
    cmd.extend([
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-default-browser-check",
    ])

    if args.headless:
        cmd.append("--headless=new")

    if args.dry_run:
        print("\n[DRY RUN] Command:")
        print(" ".join(cmd))
        return

    # 7) Launch
    print(f"\n[*] Launching browser...")
    try:
        proc = subprocess.Popen(cmd)
        print(f"[+] Browser launched (PID {proc.pid})")
        print("[*] Press Ctrl+C to detach (browser keeps running)")
        proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Detached. Browser is still running.")
    except Exception as e:
        print(f"[!] Launch failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
''').strip()


@app.route("/api/launch-script", methods=["GET"])
def get_launch_script():
    """Return a downloadable Python launch script."""
    launcher_path = os.path.join(BASE_DIR, "launcher", "launcher.py")
    if os.path.isfile(launcher_path):
        return send_from_directory(
            os.path.join(BASE_DIR, "launcher"),
            "launcher.py",
            as_attachment=True,
            download_name="antidetect-launcher.py",
        )
    return app.response_class(
        response=LAUNCH_SCRIPT_TEMPLATE,
        status=200,
        mimetype="text/x-python",
        headers={
            "Content-Disposition": "attachment; filename=launch.py",
        },
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict):
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the static index.html or a simple health message."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return send_from_directory(STATIC_DIR, "index.html")
    return jsonify({
        "name": "Anti-Detect Profile Manager",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "profiles": "/api/profiles",
            "folders": "/api/folders",
            "stats": "/api/stats",
            "launch_script": "/api/launch-script",
        },
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    init_db()
    print(f"[*] Anti-Detect Profile Manager starting on http://0.0.0.0:5070")
    print(f"[*] Database: {DB_PATH}")
    print(f"[*] Static files: {STATIC_DIR}")
    app.run(host="0.0.0.0", port=5070, debug=False)
